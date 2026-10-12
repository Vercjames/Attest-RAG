"""Hybrid retrieval: BM25 always, dense embeddings when available, fused with RRF.

Why hybrid: contact-center questions mix exact terms that BM25 nails
("Premier", "ACH", "$35") with paraphrase it misses ("my payment bounced"
vs "returned item"). Reciprocal rank fusion combines the two without having
to calibrate their score scales against each other.

Dense is optional so the project runs anywhere with zero downloads. When the
embedding model can't be loaded we log it and run lexical-only; the eval
report records which mode produced it.
"""
from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from rank_bm25 import BM25Okapi

from .chunking import Chunk
from .documents import AUTHORITY_RANK_PENALTY

log = logging.getLogger(__name__)

RRF_K = 60          # standard RRF constant; dampens the head of each ranking
CANDIDATES = 30     # how deep each ranker contributes to fusion

# ---------------------------------------------------------------- tokenizing

_STOP = set("""a an and are as at be by can do does for from get how i if in is it
its me my of on or our so that the this to was we what when where which who why
will with you your am im much any there their them they have has had about would
should could been being""".split())

# Words that describe the shape of a customer's question rather than its topic.
# Excluded from coverage only (BM25 still sees them), otherwise "how much does
# it cost" reads as an unknown topic because the corpus says "fee", not "cost".
_QUESTION_WORDS = set("""cost price time long many sent send sending getting pay paid
need know let tell money customer current currently happen take want""".split())

_TOKEN = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?|[a-z]+")


def normalize_number(tok: str) -> str:
    """'$25.00' -> '25', '5,000' -> '5000', '3%' -> '3%'."""
    tok = tok.replace("$", "").replace(",", "")
    if tok.endswith(".00"):
        tok = tok[:-3]
    return tok


def _stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokenize(text: str) -> list[str]:
    out = []
    for t in _TOKEN.findall(text.lower()):
        if t[0].isdigit() or t[0] == "$":
            out.append(normalize_number(t))
        elif t not in _STOP and len(t) > 1:
            out.append(_stem(t))
    return out


# ---------------------------------------------------------------- dense

class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray: ...


class FastEmbedEmbedder:
    MODEL = "BAAI/bge-small-en-v1.5"

    def __init__(self) -> None:
        from fastembed import TextEmbedding
        self._model = TextEmbedding(self.MODEL)

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.array(list(self._model.embed(texts)), dtype=np.float32)


def load_default_embedder() -> Embedder | None:
    if os.getenv("ATTEST_DENSE", "1") == "0":
        return None
    try:
        return FastEmbedEmbedder()
    except Exception as e:  # ImportError, no network, missing model files
        log.warning("dense retrieval unavailable, running BM25 only (%s)", type(e).__name__)
        return None


# ---------------------------------------------------------------- retrieval

@dataclass
class Hit:
    chunk: Chunk
    score: float                  # fused RRF score (authority applied as a rank penalty)
    bm25_score: float
    bm25_rank: int | None
    dense_rank: int | None


@dataclass
class RetrievalResult:
    hits: list[Hit]
    coverage: float               # idf-weighted share of query terms found in top hits
    missing_terms: list[str]      # salient query terms the top hits don't contain
    suppressed: list[str] = field(default_factory=list)   # superseded doc ids filtered out
    mode: str = "bm25"


class Retriever:
    def __init__(self, chunks: list[Chunk], embedder: Embedder | None = None):
        self.chunks = chunks
        self._tokens = [tokenize(c.index_text) for c in chunks]
        self.bm25 = BM25Okapi(self._tokens)
        self.embedder = embedder
        self._vecs = None
        if embedder is not None:
            v = embedder.embed([c.index_text for c in chunks])
            self._vecs = v / np.linalg.norm(v, axis=1, keepdims=True)
        # idf for coverage; terms the corpus never uses get the maximum weight
        n = len(chunks)
        df: dict[str, int] = {}
        for toks in self._tokens:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self._idf = {t: math.log(1 + n / d) for t, d in df.items()}
        self._max_idf = math.log(1 + n)

    @property
    def mode(self) -> str:
        return "hybrid" if self._vecs is not None else "bm25"

    def search(self, query: str, k: int = 6) -> RetrievalResult:
        q_tokens = tokenize(query)
        bm25 = self.bm25.get_scores(q_tokens)
        bm25_order = [i for i in np.argsort(-bm25) if bm25[i] > 0][:CANDIDATES]
        rankings = [bm25_order]

        dense_order: list[int] = []
        if self._vecs is not None:
            q = self.embedder.embed([query])[0]
            sims = self._vecs @ (q / np.linalg.norm(q))
            dense_order = list(np.argsort(-sims)[:CANDIDATES])
            rankings.append(dense_order)

        penalty = [AUTHORITY_RANK_PENALTY.get(c.doc.doc_type, 0) for c in self.chunks]
        fused = rrf(rankings, penalty)
        bm25_rank = {i: r for r, i in enumerate(bm25_order)}
        dense_rank = {i: r for r, i in enumerate(dense_order)}

        hits, suppressed = [], []
        for i, s in sorted(fused.items(), key=lambda kv: -kv[1]):
            c = self.chunks[i]
            if c.doc.superseded_by:
                if c.doc_id not in suppressed:
                    suppressed.append(c.doc_id)
                continue
            hits.append(Hit(c, s, float(bm25[i]), bm25_rank.get(i), dense_rank.get(i)))
            if len(hits) == k:
                break

        coverage, missing = self._coverage(q_tokens, hits[:3])
        return RetrievalResult(hits, coverage, missing, suppressed, self.mode)

    def best_fee_row(self, text: str) -> Chunk | None:
        """BM25 restricted to fee-schedule rows; used to resolve 'see the fee schedule'."""
        scores = self.bm25.get_scores(tokenize(text))
        rows = [(scores[i], c) for i, c in enumerate(self.chunks) if c.doc.doc_type == "fee_schedule"]
        best = max(rows, key=lambda r: r[0], default=(0, None))
        return best[1] if best[0] > 0 else None

    def salient_terms(self, query: str) -> list[str]:
        """Query terms specific enough to identify a topic (in <20% of chunks)."""
        cutoff = math.log(1 + 5)
        return [t for t in dict.fromkeys(tokenize(query))
                if t not in _QUESTION_WORDS and self._idf.get(t, self._max_idf) >= cutoff]

    def _coverage(self, q_tokens: list[str], hits: list[Hit]) -> tuple[float, list[str]]:
        """How much of what the user asked about shows up in what we found.

        idf-weighted so 'mortgage' (never in the corpus) counts for far more
        than 'fee' (everywhere). This is the main out-of-scope signal and it
        is model-free, so it works in BM25-only mode too.
        """
        terms = [t for t in dict.fromkeys(q_tokens) if t not in _QUESTION_WORDS]
        if not terms or not hits:
            return 0.0, terms
        found = set().union(*(set(tokenize(h.chunk.index_text)) for h in hits))
        weight = {t: self._idf.get(t, self._max_idf) for t in terms}
        total = sum(weight.values())
        missing = [t for t in terms if t not in found]
        return 1 - sum(weight[t] for t in missing) / total, missing


def rrf(rankings: list[list[int]], penalty: list[int] | None = None,
        k: int = RRF_K) -> dict[int, float]:
    """Reciprocal rank fusion. `penalty[idx]` pushes an item down each ranking."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            p = penalty[idx] if penalty else 0
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1 + p)
    return scores
