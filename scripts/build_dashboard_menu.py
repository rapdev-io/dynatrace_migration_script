#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard_tooling.assessment import build_dashboard_menu, build_menu_report, summarize_menu
from dashboard_tooling.io import ensure_dir, load_json, write_csv, write_json, write_text
from dashboard_tooling.models import DashboardRecord, ParityRecord, QueryRecord


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a combined dashboard migration menu from inventory, parity, and recommendation signals."
    )
    parser.add_argument("--source-inventory", required=True)
    parser.add_argument("--parity-json")
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
        dashboards.append(dashboard)
    return dashboards


def load_parity(path: Path | None) -> list[ParityRecord]:
    if path is None:
        return []
    payload = load_json(path)
    records = payload.get("parity", []) if isinstance(payload, dict) else []
    parity: list[ParityRecord] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        parity.append(
            ParityRecord(
                source_dashboard_id=str(item.get("source_dashboard_id") or ""),
                source_title=str(item.get("source_title") or ""),
                source_complexity_score=int(item.get("source_complexity_score") or 0),
                matched_target_id=str(item.get("matched_target_id") or ""),
                matched_target_title=str(item.get("matched_target_title") or ""),
                title_similarity=float(item.get("title_similarity") or 0.0),
                parity_status=str(item.get("parity_status") or "unmatched"),
                recommended_action=str(item.get("recommended_action") or ""),
                manual_review_reasons=[str(reason) for reason in item.get("manual_review_reasons", []) if str(reason).strip()],
                heuristic_blockers=[str(reason) for reason in item.get("heuristic_blockers", []) if str(reason).strip()],
                annotation_notes=[str(note) for note in item.get("annotation_notes", []) if str(note).strip()],
                annotation_blockers=[str(note) for note in item.get("annotation_blockers", []) if str(note).strip()],
            )
        )
    return parity


def main() -> int:
    args = parse_args()
    dashboards = load_dashboards(Path(args.source_inventory))
    parity = load_parity(Path(args.parity_json) if args.parity_json else None)
    menu = build_dashboard_menu(dashboards, parity)

    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)
    write_json(
        out_dir / "menu.json",
        {"summary": summarize_menu(menu), "menu": [item.to_dict() for item in menu]},
    )
    write_csv(
        out_dir / "menu.csv",
        [
            {
                "dashboard_id": item.dashboard_id,
                "title": item.title,
                "menu_action": item.menu_action,
                "customer_option_label": item.customer_option_label,
                "parity_status": item.parity_status,
                "matched_target_title": item.matched_target_title,
                "recommendation_status": item.recommendation_status,
                "terraform_ready": item.terraform_ready,
                "terraform_strategy": item.terraform_strategy,
                "suggested_dashboard_tier": item.suggested_dashboard_tier,
                "required_inputs": "|".join(item.required_inputs),
                "open_questions": "|".join(item.open_questions),
                "heuristic_blockers": "|".join(item.heuristic_blockers),
            }
            for item in menu
        ],
        fieldnames=[
            "dashboard_id",
            "title",
            "menu_action",
            "customer_option_label",
            "parity_status",
            "matched_target_title",
            "recommendation_status",
            "terraform_ready",
            "terraform_strategy",
            "suggested_dashboard_tier",
            "required_inputs",
            "open_questions",
            "heuristic_blockers",
        ],
    )
    write_text(out_dir / "menu.md", build_menu_report(menu))
    print(f"wrote dashboard migration menu to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
