# Working in this repo (for AI agents and humans)

Attest answers support questions from a knowledge base with cited source spans,
a confidence level, and refusals. Read `src/attest/pipeline.py` first; it is the
whole flow in ~150 lines.

## Invariants (tests enforce these; don't weaken them to make something pass)

- `chunk.text == chunk.doc.text[chunk.start:chunk.end]`. Citations are exact spans.
  For markdown and CSV, offsets are raw file offsets.
- Superseded policy versions never reach the generator.
- Every number in an answer must appear in a passage that answer cites.
  Answers that fail this are withheld (`status="unverified"`), not shown.
- Raw queries are never logged or sent to an LLM; `redact()` runs first.
- Confidence comes from measurable signals in `confidence.py`, never from
  the LLM rating itself.

## Conventions

- Python 3.10+, standard library first. New dependencies need a reason in the README.
- No network at import time. Dense retrieval and Claude are optional and must
  degrade cleanly when unavailable.
- Prefer explicit, reviewable rules (pattern lists, thresholds as named
  constants) over clever ones. Every heuristic gets a comment saying what
  it misses.
- Tests cover behavior that would hurt an agent if it broke (wrong fee,
  stale fee, uncited number, PII in logs), not line coverage.

## Commands

    pip install -e ".[dev]"            # add ,dense and/or ,claude as needed
    python -m pytest
    python -m attest "What is the overdraft fee?"
    python eval/run_eval.py            # writes eval/report-dev.md (--dense / --claude for the others)

## When changing retrieval or generation

Run the eval before and after and compare `eval/report-<mode>.md` with `git diff`. If a change was
made to fix a specific eval query, say so in the commit message: the eval
set is small enough to overfit by accident.
