"""python -m attest "What is the overdraft fee?" [--json] [--llm extractive|claude]"""
from __future__ import annotations

import argparse
import json
import logging

from .pipeline import Attest


def main() -> None:
    ap = argparse.ArgumentParser(prog="attest", description="Ask the knowledge base a question.")
    ap.add_argument("query")
    ap.add_argument("--json", action="store_true", help="print the full Answer as JSON")
    ap.add_argument("--llm", choices=["auto", "extractive", "claude"], default="auto",
                    help="auto uses Claude when ANTHROPIC_API_KEY is set")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    ans = Attest.from_corpus(llm=args.llm).ask(args.query)
    if args.json:
        print(json.dumps(ans.to_dict(), indent=2))
        return

    print(f"\n{ans.status.upper()}  confidence: {ans.confidence.level}")
    if ans.confidence.reasons:
        print("  " + "; ".join(ans.confidence.reasons))
    print()
    if ans.answer:
        print(ans.answer + "\n")
    for label, cites in (("Sources", ans.citations), ("Related / excluded", ans.related)):
        if cites:
            print(f"{label}:")
            for c in cites:
                snippet = " ".join(c.text.split())
                print(f"  [{c.chunk_id}] {c.heading}  ({c.path} chars {c.start}-{c.end})")
                print(f"      \"{snippet[:160]}{'...' if len(snippet) > 160 else ''}\"")
            print()
    for n in ans.notices:
        print(f"note: {n}")


if __name__ == "__main__":
    main()
