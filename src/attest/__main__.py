"""python -m attest "What is the overdraft fee?" [--json] [--dense] [--llm extractive|claude]"""
from __future__ import annotations

import argparse
import json
import logging
import os

from .pipeline import Attest
from .render import render


def main() -> None:
    ap = argparse.ArgumentParser(prog="attest", description="Ask the knowledge base a question.")
    ap.add_argument("query")
    ap.add_argument("--json", action="store_true", help="print the full Answer as JSON")
    ap.add_argument("--llm", choices=["extractive", "claude"], default="extractive",
                    help="answer generator; Claude runs only when asked for")
    ap.add_argument("--dense", action="store_true",
                    help='add semantic search (requires pip install -e ".[dense]")')
    args = ap.parse_args()
    if args.dense:
        os.environ["ATTEST_DENSE"] = "1"
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    try:
        ans = Attest.from_corpus(llm=args.llm).ask(args.query)
    except Exception as e:
        # Surface provider errors (bad key, no credits, unknown model) as one line.
        if type(e).__module__.startswith("anthropic"):
            raise SystemExit(f"Claude API error ({type(e).__name__}): {getattr(e, 'message', e)}")
        raise
    if args.json:
        print(json.dumps(ans.to_dict(), indent=2))
        return

    print(render(ans))

if __name__ == "__main__":
    main()
