#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard_tooling.annotations import (  # noqa: E402
    apply_dashboard_annotations,
    apply_parity_annotations,
    load_annotation_payload,
)
from dashboard_tooling.io import ensure_dir, load_json, write_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Optionally enrich a normalized inventory and parity queue with dashboard annotations."
    )
    parser.add_argument("--source-inventory", required=True)
    parser.add_argument("--annotations", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--parity-json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = load_json(Path(args.source_inventory))
    if not isinstance(inventory, dict):
        raise SystemExit("source inventory must be a JSON object")
    dashboards = inventory.get("dashboards", [])
    if not isinstance(dashboards, list):
        raise SystemExit("source inventory missing dashboards list")

    payload = load_annotation_payload(Path(args.annotations))
    # Reuse the persisted dictionaries to avoid rehydrating the whole model in this helper.
    for item in dashboards:
        if not isinstance(item, dict):
            continue
        item.setdefault("annotation_notes", [])
        item.setdefault("annotation_blockers", [])

    from dashboard_tooling.models import DashboardRecord, QueryRecord  # noqa: E402

    hydrated: list[DashboardRecord] = []
    for item in dashboards:
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
            manual_review_reasons=[str(reason) for reason in item.get("manual_review_reasons", []) if str(reason).strip()],
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
        hydrated.append(dashboard)

    apply_dashboard_annotations(hydrated, payload)
    inventory["dashboards"] = [item.to_dict() for item in hydrated]

    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)
    write_json(out_dir / "inventory.json", inventory)

    if args.parity_json:
        parity = load_json(Path(args.parity_json))
        if isinstance(parity, dict) and isinstance(parity.get("parity"), list):
            from dashboard_tooling.models import ParityRecord  # noqa: E402

            hydrated_parity: list[ParityRecord] = []
            for item in parity["parity"]:
                if not isinstance(item, dict):
                    continue
                hydrated_parity.append(
                    ParityRecord(
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
                        heuristic_blockers=[
                            str(reason) for reason in item.get("heuristic_blockers", []) if str(reason).strip()
                        ],
                        annotation_notes=[
                            str(note) for note in item.get("annotation_notes", []) if str(note).strip()
                        ],
                        annotation_blockers=[
                            str(note) for note in item.get("annotation_blockers", []) if str(note).strip()
                        ],
                    )
                )
            apply_parity_annotations(hydrated_parity, hydrated)
            write_json(out_dir / "parity.json", {"parity": [item.to_dict() for item in hydrated_parity]})

    print(f"wrote annotated outputs to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
