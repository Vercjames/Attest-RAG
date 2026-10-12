"""python -m attest "What is the overdraft fee?" [--json] [--dense | --claude]"""
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
    ap.add_argument("--dense", action="store_true",
                    help='add semantic search (requires pip install -e ".[dense]")')
    ap.add_argument("--claude", action="store_true",
                    help="full mode: semantic search + Claude answers (needs ANTHROPIC_API_KEY)")
    args = ap.parse_args()
    if args.dense or args.claude:
        os.environ["ATTEST_DENSE"] = "1"
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    try:
        ans = Attest.from_corpus(llm="claude" if args.claude else "extractive").ask(args.query)
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
