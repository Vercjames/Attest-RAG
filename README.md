# Attest-RAG

A retrieval-and-grounding layer for customer-support knowledge bases. Given a
question, Attest returns an answer, the exact source passages it is built
from, and a confidence level. When the knowledge base can't support an answer,
it refuses and points to the closest passages instead of guessing.

This repo builds a working slice against a synthetic financial-services
corpus: 24 documents (policies, help-center FAQs, and a fee schedule) for a
fictional company, MerchantBridge. It is written for contact-center agents,
so answers favor exact figures with their source over fluent prose.

## Run it

Three modes, each building on the one before. No flags means Dev mode; each
flag turns on one layer. `--dense` adds semantic search and `--llm claude`
switches answers to Claude. Nothing switches on just because it's installed
or a key is set. Add `--json` to any query for the full answer structure.

### 1. Dev

BM25 retrieval and extractive answers. No downloads, no API key: the
reproducible baseline.

```bash
pip install -e ".[dev]"
python -m pytest
python -m attest "What is the overdraft fee?"
python eval/run_eval.py
```

### 2. Dense

Adds semantic search, which matches meaning rather than exact words
("bounced" vs "returned item"). Downloads a ~70MB embedding model on first run.

```bash
pip install -e ".[dev,dense]"
python -m attest "What is the overdraft fee?" --dense
python eval/run_eval.py --dense
```

### 3. Claude

Claude writes the answer from the same retrieved passages, and the answer
passes the same grounding checks. Requires an
[Anthropic Console](https://console.anthropic.com) account with **API credits**.
A Claude.ai subscription (Pro, Max, Team) does not include API usage.

```bash
pip install -e ".[dev,dense,claude]"
python -m attest "What is the overdraft fee?" --dense --llm claude
python eval/run_eval.py --dense --llm claude
```

Set these first. They last only for the current terminal window:

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Console API key |
| `ATTEST_MODEL` | no | Model (default `claude-sonnet-5-5`) |

```bash
export ANTHROPIC_API_KEY="sk-ant-..."     # macOS / Linux;  check: echo $ANTHROPIC_API_KEY
$env:ANTHROPIC_API_KEY = "sk-ant-..."     # PowerShell;     check: echo $env:ANTHROPIC_API_KEY
```

`--llm claude` fails loudly rather than falling back. API problems print as
one line, `Claude API error (...)`. The usual causes are no credits, an
invalid key, or a model the account can't access. The prompt is in
`src/attest/generation.py`.

### Reading eval output

The eval prints one line per query as it runs (PASS in green, FAIL in red),
with a one-line reason for each failure, then writes the full
`eval/report.md`. The first line shows which retrieval mode and generator
actually ran.

Add `-v` (or `--verbose`) to also print, for each failing query, the answer
the system gave. When an answer failed grounding and was withheld, it prints
the **withheld draft** instead, so you can see what the generator produced
before validation stopped it.

```bash
python eval/run_eval.py --dense --llm claude -v
```

`-v` exists only on `eval/run_eval.py`. For a single question, use
`python -m attest "..." --json` to see the full answer structure.

## What it returns

```python
from attest.pipeline import Attest
ans = Attest.from_corpus().ask("Is the international wire fee waived for Premier?")
ans.status          # "answered" | "refused" | "unverified"
ans.answer          # text with inline [chunk_id] citations
ans.citations       # doc, heading, file path, char offsets, exact passage text
ans.confidence      # level (high/medium/low/none) + the reasons behind it
ans.related         # closest passages when refused; excluded stale passages when answered
ans.notices         # e.g. "Superseded version excluded: overdraft-policy-2025"
```

## How it works

```
redact PII -> account-question gate -> hybrid retrieval -> coverage gate
  -> build context (drop stale FAQs, follow fee-schedule pointers, expand fee tiers)
  -> generate -> grounding checks -> confidence -> audit log
```

| Decision | Choice | Why |
|---|---|---|
| Index | BM25 + dense embeddings (bge-small via fastembed), fused with reciprocal rank fusion | Support questions mix exact terms ("Premier", "ACH") with paraphrase ("my payment bounced"). Dense is opt-in (`--dense`) so the default needs no downloads; if requested and unavailable, it fails loudly instead of silently running BM25-only. |
| Chunking | By document structure: markdown/HTML headings, one CSV row per chunk | Sections in a policy are already the unit an agent wants cited. |
| Tables | Fee rows are cited as the raw CSV line but indexed as a sentence with column names. Markdown tables are rendered the same way. | A bare row (`WIO-PRM,...,$45.00,...`) retrieves badly; the rendered row matches queries; the raw row is what an agent should see. |
| Versions | Older versions of a policy (same `policy_id`, earlier effective date) are detected and excluded | Real KBs keep old files around; the 2025 overdraft policy still says $35. |
| Stale FAQs | A FAQ chunk is excluded when a retrieved policy on the same topic took effect after the FAQ was last reviewed | FAQs drift. The overdraft FAQ was never updated after the fee changed. |
| Authority | FAQs get a small rank penalty in fusion | Breaks near-ties toward policy without hiding a FAQ that is the best match. |
| Grounding | Every number in an answer must appear in a passage it cites; failures are withheld | A confidently wrong fee is the costliest failure in this domain. |
| Confidence | Query coverage (idf-weighted), ranker agreement, source type, stale-source flag, grounding result | Measurable and explainable. The LLM never grades itself. |
| Refusal | Account-specific questions (pattern list), low coverage, model abstention, failed grounding | Each refusal still returns the closest passages so the agent has somewhere to look. |
| Audit | One JSONL record per question: redacted query, retrieval trace, draft, checks, confidence | Any answer can be reconstructed after the fact. |

## Dataset

`data/corpus/` holds 15 markdown policies, 8 HTML FAQ pages, and `fees.csv`.
`data/queries.yaml` holds 19 questions, each with expected sources, required
facts, facts that indicate a wrong answer, and the trap it probes.

The traps are the ones that show up on their own in a real knowledge base,
rather than adversarial ones:

- A superseded policy version still in the corpus, and a FAQ that was never updated after the fee changed
- A FAQ that paraphrases a policy loosely ("about 10 days" vs "10 business days ... up to 45 days")
- Facts that exist only in the fee table, or only in a table's notes column
- Policies that say "see the Fee and Rate Schedule" instead of stating the amount
- Help-center boilerplate (nav, cookie banner, footer) on every HTML page
- CSV export junk: a blank line, a trailing comment row, quoted commas
- Customer vocabulary that differs from the documents ("bounced", "abroad")
- Out-of-scope questions that share words with in-scope content ("Premier savings APY")
- Account-specific questions, one containing an account number

**How it was generated.** An AI assistant drafted the documents and queries
from a spec of the traps above, then I reviewed every file and query. Choices
made along the way:

- Traps were limited to ones that occur on their own in real knowledge bases. A planted prompt injection was proposed and dropped as contrived.
- Fees live in the CSV, with policies pointing to it, the way a policy team and a pricing team actually split ownership. That split is what made pointer-following necessary.
- q08 (mortgage rates) was changed from "should refuse" to "should route to the Partner Products line" after the system found the routing rule in the escalation guide. A routed answer is more useful to an agent than a refusal.
- Expected facts are checked by normalized substring match, which is crude but deterministic. With 19 queries, every answer can be read by hand.

## Results

Full output in `eval/report.md` (regenerated on each run).

| Mode | Retrieval | Generator | Pass |
|---|---|---|---|
| Dev | BM25 | extractive | 13/19 |
| Dense | BM25 + embeddings | extractive | 14/19 |
| Claude | BM25 + embeddings | Claude | 16/19 |

In every mode, retrieval finds an expected source for the answerable queries,
and the stale $35 overdraft fee never appears in an answer. Claude scores vary
slightly run to run; the figure above is one run after the token-limit fix.

What the modes show:

- **Dense helps where words differ.** It fixes the ambiguous wire question (q05) and correctly refuses "Premier savings APY" (q18), which BM25 answered at low confidence from a FAQ line about savings accounts.
- **Dense also improves calibration.** In BM25 mode, two wrong answers were marked *high*. In hybrid mode, none were.
- **Claude helps where answers need synthesis.** It compares business and personal wire fees (q16) and states the dispute deadline that the extractive generator retrieved but didn't quote.
- **Claude's 3 misses happen before Claude runs.** q07 ("bounced"), q19 ("abroad") and q08 (mortgage) are refused by the coverage gate. For q07 and q19, dense retrieval found the right document; see "With more time".

## What I didn't build, and why

The brief is deliberately larger than an hour. I spent the time on grounding,
refusal and auditability, because a wrong fee quoted to a customer is the
failure that costs money, and skipped the following:

- **Cross-encoder reranker.** It would sharpen the top results, but retrieval already finds the right source for the answerable queries; the failures are downstream of it.
- **Query rewriting.** It overlaps with what dense retrieval already does for vocabulary gaps, and adds an LLM call to every query.
- **Multi-turn conversation.** Agents ask one question at a time against a knowledge base; conversation state is a product decision, not a retrieval one.
- **Index persistence.** The corpus builds in under a second. Persistence matters at production size, not here.
- **LLM-as-judge evaluation.** With 19 queries, every answer can be read. A judge would add a second model's errors to the first's.
- **HTTP endpoint (FastAPI).** Cut in favor of the audit log and PII redaction. The deliverable is the `Attest.ask()` function and a CLI; an endpoint is a thin wrapper around it.
- **UI and auth.** Out of scope per the brief.

## With more time

In priority order, each grounded in an eval failure:

1. **Make the coverage gate trust semantic matches.** The gate measures word overlap between the query and the results. On q07 and q19, dense retrieval finds the right document, then the gate refuses because the words differ. Loosening the gate trades hallucination safety for recall, so I'd accept a strong embedding similarity as a second way to pass, and measure the false-answer rate on out-of-scope queries before shipping it.
2. **Ask clarifying questions.** "How much is a wire?" has eight answers by direction, destination and tier. Listing them is a workaround; asking which one is the right behavior for an agent tool.
3. **Separate retrieval confidence from answer confidence.** Confidence currently reflects whether good sources were found, not whether the answer used them well. A per-claim check (does each sentence's cited passage entail it) would close that gap.
4. **Fix two noisy signals.** The "superseded version excluded" notice fires when an old version appears anywhere in the candidate pool, even on unrelated questions. And correctly excluding a stale FAQ lowers confidence, which penalizes the system for doing the right thing.
5. **Replace the account-question pattern list with a classifier.** The regex list is reviewable but brittle; it misses phrasings it hasn't seen.

## How I used AI tools

Claude generated most of the code and the synthetic dataset under my
direction. My work was deciding what to build, reviewing the output, and
running the system to find where it broke.

- **Conventions before code.** I had `CLAUDE.md` written first: the invariants the system must keep (exact citation spans, no ungrounded numbers, no raw queries in logs), each enforced by a test.
- **Dataset.** AI-drafted from a spec of realistic traps, then reviewed by hand; the changes I made are listed under Dataset.
- **Bugs found by running it, not by reading it.**
  - A "prefer policy over FAQ" weight was implemented as a score multiplier. Because RRF scores are tightly compressed, it buried a FAQ that was clearly the best match. Rebuilt as a small rank penalty.
  - Using the CLI showed the same fee row cited twice. A failing test was written first, then the fix.
  - The Claude eval first scored 12/19. Reading the withheld drafts with `-v` showed answers cut off mid-list: the token limit was too low. Raising it, and flagging truncation as its own failure, took Claude to 16/19.
- **Where I overrode the AI.** It proposed a venv-heavy setup, a contrived prompt-injection trap, and at one point described the Claude failures as "Claude dropping citations". The drafts showed truncation instead.
