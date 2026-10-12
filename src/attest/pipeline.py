"""query -> Answer. The one entry point everything else calls.

    redact -> scope gate -> retrieve -> coverage gate -> build context
           -> generate -> validate -> confidence -> audit

Each gate can stop the pipeline with a refusal that still returns the
closest passages, so an agent always gets somewhere to look.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from .chunking import Chunk, chunk_documents
from .confidence import MIN_COVERAGE, Confidence, assess
from .documents import load_corpus
from .generation import ClaudeGenerator, ExtractiveGenerator, Generator
from .redaction import redact
from .retrieval import Hit, Retriever, load_default_embedder, tokenize
from .validation import validate

FEE_POINTER = "Fee and Rate Schedule"

DEFAULT_CORPUS = Path(__file__).resolve().parents[2] / "data" / "corpus"
DEFAULT_AUDIT_LOG = Path(__file__).resolve().parents[2] / "logs" / "audit.jsonl"

# Questions about one customer's own account. The knowledge base can't answer
# these and shouldn't try; the agent console can. Kept as an explicit list
# so it is reviewable. Brittle by design: a classifier is the next step.
_ACCOUNT_SPECIFIC = [
    re.compile(p, re.I) for p in [
        r"\bmy (current |available )?(account )?balance\b",
        r"\bhow much (money )?(do i have|is in my)\b",
        r"\b(my|this) (last|latest|recent) (transaction|deposit|payment|charge)s?\b",
        r"\bwhy (was|were|did) (i|my|account|\[ACCOUNT_NUMBER\]).*\bcharged?\b",
        r"\[ACCOUNT_NUMBER\]",
    ]
]


@dataclass
class Citation:
    chunk_id: str
    doc_id: str
    title: str
    heading: str
    path: str
    start: int
    end: int
    text: str

    @classmethod
    def of(cls, c: Chunk) -> "Citation":
        return cls(c.chunk_id, c.doc_id, c.doc.title, c.heading, c.doc.path, c.start, c.end, c.text)


@dataclass
class Answer:
    query: str                         # redacted
    status: str                        # answered | refused | unverified
    answer: str | None
    citations: list[Citation]
    confidence: Confidence
    refusal_reason: str | None = None
    related: list[Citation] = field(default_factory=list)   # closest passages when not answered
    notices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class Attest:
    def __init__(self, chunks: list[Chunk], generator: Generator | None = None,
                 embedder="auto", audit_log: Path | None = DEFAULT_AUDIT_LOG):
        self.chunks = chunks
        self.retriever = Retriever(chunks, load_default_embedder() if embedder == "auto" else embedder)
        self.generator = generator or ExtractiveGenerator(self.retriever._idf)
        self.audit_log = audit_log
        self._fee_rows = [c for c in chunks if c.doc.doc_type == "fee_schedule"]

    @classmethod
    def from_corpus(cls, root: str | Path = DEFAULT_CORPUS, llm: str = "auto",
                    today: date | None = None, **kw) -> "Attest":
        chunks = chunk_documents(load_corpus(root, today))
        inst = cls(chunks, **kw)
        if llm == "claude" or (llm == "auto" and _claude_available()):
            inst.generator = ClaudeGenerator()
        return inst

    # ------------------------------------------------------------ main path

    def ask(self, raw_query: str) -> Answer:
        query, redactions = redact(raw_query)
        trace: dict = {"redactions": redactions}

        if any(p.search(query) for p in _ACCOUNT_SPECIFIC):
            ans = self._refuse(query, "account_specific",
                               "This is about a specific customer's account. Verify the caller and use "
                               "the agent console; the knowledge base doesn't hold account data.", [])
            return self._audit(ans, trace)

        res = self.retriever.search(query)
        trace["retrieval"] = {
            "mode": res.mode, "coverage": round(res.coverage, 3), "missing": res.missing_terms,
            "suppressed": res.suppressed,
            "hits": [(h.chunk.chunk_id, round(h.score, 5), h.bm25_rank, h.dense_rank) for h in res.hits],
        }
        notices = [f"Superseded version excluded: {d}" for d in res.suppressed]

        if res.coverage < MIN_COVERAGE:
            ans = self._refuse(query, "insufficient_context",
                               "The knowledge base doesn't appear to cover this. Closest passages are "
                               "listed; escalate if none apply.", res.hits[:3])
            ans.confidence.signals = {"coverage": round(res.coverage, 2), "missing": res.missing_terms}
            return self._audit(ans, trace)

        context, stale = self._build_context(query, res.hits)
        notices += [f"Excluded {c.chunk_id}: FAQ last reviewed {c.doc.meta.get('last-reviewed')}, "
                    f"before the current policy took effect" for c in stale]

        draft = self.generator.generate(query, context)
        trace["generator"] = self.generator.name
        trace["draft"] = draft.text
        if draft.abstained:
            ans = self._refuse(query, "model_abstained",
                               "The retrieved passages don't answer this question.", res.hits[:3])
            return self._audit(ans, trace)

        v = validate(draft, context)
        trace["validation"] = asdict(v)
        cited = [c for c in context if c.chunk_id in draft.cited_ids]
        conf = assess(
            coverage=res.coverage, missing_terms=res.missing_terms,
            cited_doc_types=[c.doc.doc_type for c in cited],
            rankers_agree=_rankers_agree(res.hits) if res.mode == "hybrid" else None,
            stale_excluded=list(dict.fromkeys(c.doc_id for c in stale)), validation_ok=v.ok,
        )
        if not v.ok:
            # Don't show an answer we can't back up. Show the passages instead.
            ans = Answer(query, "unverified", None, [], conf, "failed_grounding",
                         [Citation.of(c) for c in context[:3]], notices + v.problems())
        else:
            ans = Answer(query, "answered", draft.text, [Citation.of(c) for c in cited], conf,
                         related=[Citation.of(c) for c in stale], notices=notices)
        return self._audit(ans, trace)

    # ------------------------------------------------------------ helpers

    def _build_context(self, query: str, hits: list[Hit]) -> tuple[list[Chunk], list[Chunk]]:
        """Pick what the generator sees.

        - Drop a FAQ chunk when a retrieved policy chunk on the same topic took
          effect after the FAQ was last reviewed. FAQs drift when policies
          change; the 2024 overdraft FAQ still says $35. "Same topic" means
          both chunks contain a distinctive query term (one that appears in
          under 20% of chunks), so an unrelated new policy doesn't knock out a
          FAQ that is still the best source.
        - Follow pointers. Policies say "see the Fee and Rate Schedule"
          instead of stating amounts, so for each top policy chunk that does,
          pull the fee row that best matches that chunk's heading.
        - Expand fee rows to all tiers of the same fee, so "what's the
          overdraft fee" gets every tier instead of whichever row ranked first.
        """
        chunks = [h.chunk for h in hits]
        salient = set(self.retriever.salient_terms(query))
        toks = {c.chunk_id: set(tokenize(c.index_text)) & salient for c in chunks}
        policies = [c for c in chunks if c.doc.doc_type == "policy"]

        def is_stale(faq: Chunk) -> bool:
            reviewed = _d(faq.doc.meta.get("last-reviewed"))
            return any(_d(p.doc.meta.get("effective")) > reviewed and toks[p.chunk_id] & toks[faq.chunk_id]
                       for p in policies)

        stale = [c for c in chunks if c.doc.doc_type == "faq" and is_stale(c)]
        context = [c for c in chunks if c not in stale]

        for c in context[:3]:
            if c.doc.doc_type == "policy" and FEE_POINTER in c.text:
                row = self.retriever.best_fee_row(f"{c.heading} {query}")
                if row and row not in context:   # may already be there via retrieval
                    context.append(row)

        fee_names = {c.heading for c in context if c.doc.doc_type == "fee_schedule"}
        for row in self._fee_rows:
            if row.heading in fee_names and row not in context:
                context.append(row)
        return context, stale

    def _refuse(self, query: str, reason: str, message: str, hits: list[Hit]) -> Answer:
        return Answer(query, "refused", message, [], Confidence("none", [reason]), reason,
                      [Citation.of(h.chunk) for h in hits])

    def _audit(self, ans: Answer, trace: dict) -> Answer:
        """Every answer is reconstructable: what was asked (redacted), what was
        retrieved and why, what was generated, and what the checks said."""
        if self.audit_log is None:
            return ans
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "query": ans.query, "status": ans.status, "refusal_reason": ans.refusal_reason,
            "cited": [c.chunk_id for c in ans.citations],
            "confidence": {"level": ans.confidence.level, "reasons": ans.confidence.reasons},
            "notices": ans.notices, **trace,
        }
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return ans


def _rankers_agree(hits: list[Hit]) -> bool:
    by_bm25 = min((h for h in hits if h.bm25_rank is not None), key=lambda h: h.bm25_rank, default=None)
    by_dense = min((h for h in hits if h.dense_rank is not None), key=lambda h: h.dense_rank, default=None)
    return bool(by_bm25 and by_dense and by_bm25.chunk.doc_id == by_dense.chunk.doc_id)


def _d(v) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        return date.min


def _claude_available() -> bool:
    import os
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False
