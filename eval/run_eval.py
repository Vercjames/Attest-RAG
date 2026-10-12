"""Run the query set and write eval/report.md.

    python eval/run_eval.py                 # extractive generator, dense if available
    python eval/run_eval.py --llm claude    # needs ANTHROPIC_API_KEY
    python eval/run_eval.py --no-dense      # force BM25-only

Metrics are deliberately simple and deterministic:
  retrieval@5    an expected doc is in the top 5 retrieved (before gating)
  facts          every must_include string appears in the answer (normalized)
  no wrong fact  no must_not_include string appears
  behavior       refused when it should, answered when it should
No LLM-as-judge: with 19 queries a human can read every answer, and a judge
would add a second model's errors to the first's.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from attest.pipeline import Attest  # noqa: E402


def norm(s: str) -> str:
    s = s.lower().replace("$", "").replace(",", "")
    return re.sub(r"(\d)\.00\b", r"\1", s)


def contains(answer: str, fact: str) -> bool:
    a, f = norm(answer), norm(fact)
    if re.fullmatch(r"[\d.%:]+", f):           # numbers must match as whole tokens
        return re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", a) is not None
    return f in a


def run(llm: str, out: Path) -> list[dict]:
    queries = yaml.safe_load((ROOT / "data" / "queries.yaml").read_text(encoding="utf-8"))
    system = Attest.from_corpus(llm=llm, audit_log=None)
    rows = []
    for q in queries:
        ans = system.ask(q["query"])
        retrieved = [h.chunk.doc_id for h in system.retriever.search(ans.query).hits[:5]]
        text = ans.answer or ""
        expected = q.get("expected_docs") or []
        refused = ans.status != "answered"
        row = {
            "id": q["id"], "query": q["query"], "trap": q["trap"],
            "should_refuse": bool(q.get("should_refuse")),
            "status": ans.status, "reason": ans.refusal_reason,
            "confidence": ans.confidence.level,
            "retrieval_hit": (any(d in retrieved for d in expected) if expected else None),
            "facts_ok": all(contains(text, f) for f in q.get("must_include", [])) if not refused else None,
            "no_wrong_fact": not any(contains(text, f) for f in q.get("must_not_include", [])),
            "behavior_ok": refused == bool(q.get("should_refuse")),
            "answer": text, "cited": [c.chunk_id for c in ans.citations],
            "notices": ans.notices,
        }
        row["pass"] = row["behavior_ok"] and row["no_wrong_fact"] and row["facts_ok"] is not False
        rows.append(row)
    write_report(rows, system, out)
    return rows


def pct(xs: list[bool]) -> str:
    xs = [x for x in xs if x is not None]
    return f"{sum(xs)}/{len(xs)}" if xs else "n/a"


def write_report(rows: list[dict], system: Attest, out: Path) -> None:
    mode = system.retriever.mode
    gen = system.generator.name
    answerable = [r for r in rows if not r["should_refuse"]]
    lines = [
        "# Eval report", "",
        f"Generated {date.today()} · retrieval: **{mode}** · generator: **{gen}** · {len(rows)} queries", "",
        "## Summary", "",
        "| metric | result |", "|---|---|",
        f"| end-to-end pass | {pct([r['pass'] for r in rows])} |",
        f"| retrieval@5 (expected doc retrieved) | {pct([r['retrieval_hit'] for r in rows])} |",
        f"| required facts present (answered queries) | {pct([r['facts_ok'] for r in answerable])} |",
        f"| no stale/wrong fact | {pct([r['no_wrong_fact'] for r in rows])} |",
        f"| correct refuse/answer behavior | {pct([r['behavior_ok'] for r in rows])} |",
        f"| confidence on passing answers: high / medium / low | "
        + " / ".join(str(sum(r['pass'] and r['confidence'] == lv for r in answerable)) for lv in ("high", "medium", "low"))
        + " |",
        f"| confidence on failing answers: high / medium / low | "
        + " / ".join(str(sum((not r['pass']) and r['status'] == 'answered' and r['confidence'] == lv
                            for r in rows)) for lv in ("high", "medium", "low"))
        + " |",
        "",
        "## Per query", "",
        "| id | pass | status | conf | retr@5 | facts | trap |", "|---|---|---|---|---|---|---|",
    ]
    mark = {True: "✅", False: "❌", None: "–"}
    for r in rows:
        lines.append(f"| {r['id']} | {mark[r['pass']]} | {r['status']}"
                     f"{' (' + r['reason'] + ')' if r['reason'] else ''} | {r['confidence']} | "
                     f"{mark[r['retrieval_hit']]} | {mark[r['facts_ok']]} | {r['trap']} |")
    lines += ["", "## Failures", ""]
    for r in rows:
        if r["pass"]:
            continue
        lines += [f"### {r['id']}: {r['query']}", "",
                  f"- trap: {r['trap']}",
                  f"- status: {r['status']} ({r['reason'] or 'answered'}), confidence {r['confidence']}",
                  f"- cited: {', '.join(r['cited']) or 'none'}", "",
                  "```", r["answer"] or "(no answer)", "```", ""]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", choices=["extractive", "claude", "auto"], default="extractive")
    ap.add_argument("--no-dense", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "eval" / "report.md"))
    args = ap.parse_args()
    if args.no_dense:
        os.environ["ATTEST_DENSE"] = "0"
    rows = run(args.llm, Path(args.out))
    passed = sum(r["pass"] for r in rows)
    print(f"{passed}/{len(rows)} passed -> {args.out}")
