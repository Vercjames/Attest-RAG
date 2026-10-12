# Attest-RAG

A retrieval-and-grounding layer for customer-support knowledge bases. Given a
question, Attest returns an answer, the exact source passages it is built
from, and a confidence level. When the knowledge base can't support an answer,
it refuses and points to the closest passages instead of guessing.

This repo builds a working slice against a synthetic financial-services
corpus: 24 documents (policies, help-center FAQs, and a fee schedule) for a
fictional company, MerchantBridge. It is written for contact-center agents,
so answers favor exact figures with their source over fluent prose.

> **Draft.** The judgment sections (what I skipped, what's next, how I used AI)
> are being written after hands-on use. See the TODO markers.

## Run it

### Install

Pick one. Each builds on the one before.

**Core (no downloads, no API key)**

```bash
pip install -e ".[dev]"
```

Installs the retrieval pipeline and pytest. Retrieval runs BM25-only, and
answers come from the built-in extractive generator. Everything works offline.

**With semantic search**

```bash
pip install -e ".[dev,dense]"
```

Adds the dense half of hybrid retrieval (bge-small via fastembed). It
downloads a ~70MB embedding model on first run. This is what bridges
vocabulary gaps like "bounced" vs "returned item".

**With Claude (everything)**

```bash
pip install -e ".[dev,dense,claude]"
```

Adds the Anthropic client on top of the above. When `ANTHROPIC_API_KEY` is
set, answers come from Claude instead of the extractive generator.

### Use

```bash
python -m pytest                                # tests, < 1s
python -m attest "What is the overdraft fee?"   # add --json for the full structure
python eval/run_eval.py                         # writes eval/report.md
```

No API key is needed. With `ANTHROPIC_API_KEY` set, answers come from Claude
(force either generator with `--llm claude` or `--llm extractive`). The
Claude prompt is in `src/attest/generation.py`.

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
| Index | BM25 + dense embeddings (bge-small via fastembed), fused with reciprocal rank fusion | Support questions mix exact terms ("Premier", "ACH") with paraphrase ("my payment bounced"). Dense is optional: without the model, it runs BM25-only and says so. |
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

TODO: how the dataset was generated and what I changed by hand.

## Results

See `eval/report.md`. Current run: BM25-only, extractive generator, **13/19** pass.
Retrieval finds an expected source for 16/16 answerable queries, and the stale
$35 overdraft fee never appears.

The failures are where the next work is:

- **Vocabulary gaps** (q07 "bounced", q19 "abroad"): BM25 can't bridge them. This is the case for the dense half of the hybrid.
- **Synthesis** (q04, q05, q16): the extractive generator can quote but can't compare or ask a clarifying question.
- **Confidence miscalibration**: q05 and q16 are wrong but marked *high*. Confidence measures whether the right sources were found, not whether the answer used them well.
- **Partial-match out of scope** (q18): "Premier savings APY" matches a FAQ line about savings accounts. It answers at *low* confidence rather than refusing.

## What I didn't build, and why

TODO

## With more time

TODO

## How I used AI tools

TODO
