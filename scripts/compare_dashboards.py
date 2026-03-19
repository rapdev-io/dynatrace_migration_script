#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard_tooling.compare import compare_dashboards
from dashboard_tooling.io import ensure_dir, load_json, write_csv, write_json, write_text
from dashboard_tooling.models import DashboardRecord, QueryRecord


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare normalized source and target dashboard inventories and build a parity queue."
    )
    parser.add_argument("--source-inventory", required=True)
    parser.add_argument("--target-inventory", required=True)
    parser.add_argument("--out-dir", required=True)
    return parser.parse_args()


def load_dashboards(path: Path) -> list[DashboardRecord]:
    payload = load_json(path)
    records = payload.get("dashboards", []) if isinstance(payload, dict) else []
    dashboards: list[DashboardRecord] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        dashboard = DashboardRecord(
            source_system=str(item.get("source_system") or ""),
            dashboard_id=str(item.get("dashboard_id") or ""),
            title=str(item.get("title") or ""),
            description=str(item.get("description") or ""),
            owner=str(item.get("owner") or ""),
            tags=[str(tag) for tag in item.get("tags", []) if str(tag).strip()],
            widget_count=int(item.get("widget_count") or 0),
            widget_types=[str(tag) for tag in item.get("widget_types", []) if str(tag).strip()],
            query_count=int(item.get("query_count") or 0),
            variables=[str(tag) for tag in item.get("variables", []) if str(tag).strip()],
            raw_references=dict(item.get("raw_references") or {}),
            complexity_score=int(item.get("complexity_score") or 0),
            manual_review_reasons=[
                str(reason) for reason in item.get("manual_review_reasons", []) if str(reason).strip()
            ],
            heuristic_blockers=[str(reason) for reason in item.get("heuristic_blockers", []) if str(reason).strip()],
            annotation_notes=[str(note) for note in item.get("annotation_notes", []) if str(note).strip()],
            annotation_blockers=[str(note) for note in item.get("annotation_blockers", []) if str(note).strip()],
        )
        for query in item.get("queries", []):
            if not isinstance(query, dict):
                continue
            dashboard.queries.append(
                QueryRecord(
                    dashboard_id=str(query.get("dashboard_id") or dashboard.dashboard_id),
                    dashboard_title=str(query.get("dashboard_title") or dashboard.title),
                    widget_index=int(query.get("widget_index") or 0),
                    widget_title=str(query.get("widget_title") or ""),
                    widget_type=str(query.get("widget_type") or ""),
                    query_text=str(query.get("query_text") or ""),
                    query_family=str(query.get("query_family") or "unknown"),
                    heuristic_signals=[str(sig) for sig in query.get("heuristic_signals", []) if str(sig).strip()],
                )
            )
        dashboards.append(dashboard)
    return dashboards


def main() -> int:
    args = parse_args()
    source_dashboards = load_dashboards(Path(args.source_inventory))
    target_dashboards = load_dashboards(Path(args.target_inventory))
    parity = compare_dashboards(source_dashboards, target_dashboards)

    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)
    write_json(out_dir / "parity.json", {"parity": [item.to_dict() for item in parity]})
    write_csv(
        out_dir / "parity.csv",
        [
            {
                "source_dashboard_id": item.source_dashboard_id,
                "source_title": item.source_title,
                "source_complexity_score": item.source_complexity_score,
                "matched_target_id": item.matched_target_id,
                "matched_target_title": item.matched_target_title,
                "title_similarity": round(item.title_similarity, 3),
                "parity_status": item.parity_status,
                "recommended_action": item.recommended_action,
                "manual_review_reasons": "|".join(item.manual_review_reasons),
                "heuristic_blockers": "|".join(item.heuristic_blockers),
                "annotation_blockers": "|".join(item.annotation_blockers),
            }
            for item in parity
        ],
        fieldnames=[
            "source_dashboard_id",
            "source_title",
            "source_complexity_score",
            "matched_target_id",
            "matched_target_title",
            "title_similarity",
            "parity_status",
            "recommended_action",
            "manual_review_reasons",
            "heuristic_blockers",
            "annotation_blockers",
        ],
    )
    summary_lines = [
        "# Dashboard Parity Summary",
        "",
        f"- Source dashboards: {len(source_dashboards)}",
        f"- Target dashboards: {len(target_dashboards)}",
    ]
    counts: dict[str, int] = {}
    for record in parity:
        counts[record.parity_status] = counts.get(record.parity_status, 0) + 1
    for key in sorted(counts):
        summary_lines.append(f"- {key}: {counts[key]}")
    write_text(out_dir / "summary.md", "\n".join(summary_lines) + "\n")
    print(f"wrote parity queue to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
