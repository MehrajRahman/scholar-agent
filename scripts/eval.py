"""Run the eval metrics over a saved pipeline result + a golden set.

    python scripts/eval.py result.json eval/golden.json

golden.json: {"gold_opportunity_ids": ["<id>", ...], "k": 5}
Produce result.json with:  scholar run cv.pdf --out result.json
"""
from __future__ import annotations

import json
import sys

from scholar.eval import evaluate


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: python scripts/eval.py <result.json> <golden.json>")
        sys.exit(1)
    result = json.loads(open(sys.argv[1]).read())
    golden = json.loads(open(sys.argv[2]).read())
    scores = evaluate(result, set(golden.get("gold_opportunity_ids", [])), golden.get("k", 5))
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()
