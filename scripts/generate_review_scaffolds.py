#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard_tooling.io import ensure_dir, load_json, write_text
from dashboard_tooling.models import DashboardRecord, ParityRecord, QueryRecord
from dashboard_tooling.scaffold import (
    build_datadog_scaffold,
    build_review_packet,
    dump_json,
    review_packet_filename,
    scaffold_filename,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate manual review packets and Datadog scaffold JSON for dashboards."
    )
    parser.add_argument("--source-inventory", required=True)
    parser.add_argument("--parity-json", required=False)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--status-filter",
        default="missing_in_target,possible_candidate,high_confidence_candidate",
        help="Comma-separated parity statuses to scaffold. Leave empty to scaffold all.",
    )
    return parser.parse_args()


def load_source_dashboards(path: Path) -> dict[str, DashboardRecord]:
    payload = load_json(path)
    records = payload.get("dashboards", []) if isinstance(payload, dict) else []
    dashboards: dict[str, DashboardRecord] = {}
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
        dashboards[dashboard.dashboard_id] = dashboard
    return dashboards


def load_parity(path: Path | None) -> dict[str, ParityRecord]:
    if path is None:
        return {}
    payload = load_json(path)
    records = payload.get("parity", []) if isinstance(payload, dict) else []
    parity: dict[str, ParityRecord] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        record = ParityRecord(
            source_dashboard_id=str(item.get("source_dashboard_id") or ""),
            source_title=str(item.get("source_title") or ""),
            source_complexity_score=int(item.get("source_complexity_score") or 0),
            matched_target_id=str(item.get("matched_target_id") or ""),
            matched_target_title=str(item.get("matched_target_title") or ""),
            title_similarity=float(item.get("title_similarity") or 0.0),
            parity_status=str(item.get("parity_status") or "unmatched"),
            recommended_action=str(item.get("recommended_action") or ""),
            manual_review_reasons=[
                str(reason) for reason in item.get("manual_review_reasons", []) if str(reason).strip()
            ],
            heuristic_blockers=[str(reason) for reason in item.get("heuristic_blockers", []) if str(reason).strip()],
            annotation_notes=[str(note) for note in item.get("annotation_notes", []) if str(note).strip()],
            annotation_blockers=[str(note) for note in item.get("annotation_blockers", []) if str(note).strip()],
        )
        parity[record.source_dashboard_id] = record
    return parity



def main() -> int:
    args = parse_args()
    dashboards = load_source_dashboards(Path(args.source_inventory))
    parity = load_parity(Path(args.parity_json) if args.parity_json else None)
    allowed_statuses = {item.strip() for item in args.status_filter.split(",") if item.strip()}

    out_dir = Path(args.out_dir)
    review_dir = out_dir / "review_packets"
    scaffold_dir = out_dir / "datadog_scaffolds"
    ensure_dir(review_dir)
    ensure_dir(scaffold_dir)

    emitted = 0
    for dashboard_id, dashboard in dashboards.items():
        parity_record = parity.get(dashboard_id)
        status = parity_record.parity_status if parity_record else ""
        should_emit = not allowed_statuses or status in allowed_statuses or dashboard.complexity_score >= 12
        if not should_emit:
            continue
        write_text(review_dir / review_packet_filename(dashboard), build_review_packet(dashboard, parity_record))
        write_text(scaffold_dir / scaffold_filename(dashboard), dump_json(build_datadog_scaffold(dashboard)))
        emitted += 1

    print(f"generated {emitted} review packet(s) in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
