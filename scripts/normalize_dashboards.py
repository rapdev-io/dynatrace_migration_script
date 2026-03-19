#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard_tooling.io import ensure_dir, load_json, write_csv, write_json
from dashboard_tooling.annotations import apply_dashboard_annotations, load_annotation_payload
from dashboard_tooling.normalize import (
    normalize_datadog_dashboards,
    normalize_dynatrace_dashboards,
    summarize_dashboards,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize raw dashboard exports into canonical inventory and query extracts."
    )
    parser.add_argument("--source", choices=["dynatrace", "datadog"], required=True)
    parser.add_argument("--input", required=True, help="Path to raw dashboard export JSON.")
    parser.add_argument("--out-dir", required=True, help="Directory for normalized outputs.")
    parser.add_argument(
        "--annotations",
        help="Optional JSON file with dashboard annotations to merge into the normalized inventory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = load_json(Path(args.input))
    if args.source == "dynatrace":
        dashboards = normalize_dynatrace_dashboards(payload)
    else:
        dashboards = normalize_datadog_dashboards(payload)
    if args.annotations:
        apply_dashboard_annotations(dashboards, load_annotation_payload(Path(args.annotations)))

    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)
    write_json(
        out_dir / "inventory.json",
        {
            "source": args.source,
            "summary": summarize_dashboards(dashboards),
            "dashboards": [item.to_dict() for item in dashboards],
        },
    )
    write_csv(
        out_dir / "inventory.csv",
        [
            {
                "dashboard_id": item.dashboard_id,
                "title": item.title,
                "owner": item.owner,
                "widget_count": item.widget_count,
                "query_count": item.query_count,
                "complexity_score": item.complexity_score,
                "widget_types": "|".join(item.widget_types),
                "variables": "|".join(item.variables),
                "manual_review_reasons": "|".join(item.manual_review_reasons),
                "heuristic_blockers": "|".join(item.heuristic_blockers),
                "annotation_blockers": "|".join(item.annotation_blockers),
            }
            for item in dashboards
        ],
        fieldnames=[
            "dashboard_id",
            "title",
            "owner",
            "widget_count",
            "query_count",
            "complexity_score",
            "widget_types",
            "variables",
            "manual_review_reasons",
            "heuristic_blockers",
            "annotation_blockers",
        ],
    )
    write_csv(
        out_dir / "queries.csv",
        [
            {
                "dashboard_id": item.dashboard_id,
                "dashboard_title": item.dashboard_title,
                "widget_index": item.widget_index,
                "widget_title": item.widget_title,
                "widget_type": item.widget_type,
                "query_family": item.query_family,
                "heuristic_signals": "|".join(item.heuristic_signals),
                "query_text": item.query_text,
            }
            for dashboard in dashboards
            for item in dashboard.queries
        ],
        fieldnames=[
            "dashboard_id",
            "dashboard_title",
            "widget_index",
            "widget_title",
            "widget_type",
            "query_family",
            "heuristic_signals",
            "query_text",
        ],
    )
    print(f"wrote normalized dashboard inventory to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
