"""Command-line entry point: ``scholar run cv.pdf --query "EU, machine learning"``."""
from __future__ import annotations

import argparse
import asyncio
import json

from .graph_app import run_pipeline
from .ingest import load_documents
from .observability import configure_logging


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(prog="scholar", description="Academic matchmaking pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the full pipeline on CV/transcript files")
    run.add_argument("files", nargs="+", help="Paths to CV / transcript (pdf, txt, md)")
    run.add_argument("--query", default="", help="Free-text constraints/steer")
    run.add_argument(
        "--mode",
        choices=["fast", "deep"],
        default="deep",
        help="fast = DB-only (instant); deep = live web research + DB write-back",
    )
    run.add_argument(
        "--artifacts",
        default="",
        help="Comma-separated extra kit items for the best match, e.g. "
        "motivation_letter,professor_dossier,interview_prep,deadline_checklist",
    )
    run.add_argument("--out", default=None, help="Write result JSON to this path")

    args = parser.parse_args()
    if args.command == "run":
        docs = load_documents(args.files)
        artifacts = [a.strip() for a in args.artifacts.split(",") if a.strip()]
        final = asyncio.run(run_pipeline(docs, args.query, mode=args.mode, artifacts=artifacts))
        result = {
            "profile": final.get("profile").model_dump() if final.get("profile") else None,
            "matches": [m.model_dump() for m in final.get("matches", [])],
            "bundles": [b.model_dump() for b in final.get("bundles", [])],
            "kit_artifacts": [a.model_dump() for a in final.get("kit_artifacts", [])],
            "suggest_deep_research": final.get("suggest_deep_research", False),
            "errors": final.get("errors", []),
        }
        text = json.dumps(result, indent=2, default=str)
        if args.out:
            with open(args.out, "w") as f:
                f.write(text)
            print(f"wrote {args.out}")
        else:
            print(text)


if __name__ == "__main__":
    main()
