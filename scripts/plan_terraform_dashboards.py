#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard_tooling.assessment import build_dashboard_menu
from dashboard_tooling.io import ensure_dir, load_json, write_json, write_text
from dashboard_tooling.models import DashboardMenuItem, DashboardRecord, QueryRecord
from dashboard_tooling.terraform_planner import (
    build_tf_json_resource,
    build_terraform_plans,
    summarize_terraform_plans,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create Terraform-ready dashboard plans from inventory and dashboard menu decisions."
    )
    parser.add_argument("--source-inventory", required=True)
    parser.add_argument("--menu-json")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--include-actions",
        default="create_or_rebuild_with_terraform,validate_and_improve_existing,validate_existing_parity",
        help="Comma-separated menu actions to convert into Terraform plans.",
    )
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


def load_menu(path: Path | None, dashboards: list[DashboardRecord]) -> list[DashboardMenuItem]:
    if path is None:
        return build_dashboard_menu(dashboards)
    payload = load_json(path)
    records = payload.get("menu", []) if isinstance(payload, dict) else []
    menu: list[DashboardMenuItem] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        menu.append(
            DashboardMenuItem(
                dashboard_id=str(item.get("dashboard_id") or ""),
                title=str(item.get("title") or ""),
                menu_action=str(item.get("menu_action") or ""),
                customer_option_label=str(item.get("customer_option_label") or ""),
                parity_status=str(item.get("parity_status") or "not_evaluated"),
                matched_target_id=str(item.get("matched_target_id") or ""),
                matched_target_title=str(item.get("matched_target_title") or ""),
                parity_rationale=[str(reason) for reason in item.get("parity_rationale", []) if str(reason).strip()],
                recommendation_status=str(item.get("recommendation_status") or ""),
                terraform_ready=bool(item.get("terraform_ready")),
                terraform_strategy=str(item.get("terraform_strategy") or ""),
                suggested_dashboard_tier=str(item.get("suggested_dashboard_tier") or ""),
                proposed_dashboard_description=str(item.get("proposed_dashboard_description") or ""),
                why_this_option=[str(reason) for reason in item.get("why_this_option", []) if str(reason).strip()],
                improvement_opportunities=[str(reason) for reason in item.get("improvement_opportunities", []) if str(reason).strip()],
                validation_or_test_plan=[str(reason) for reason in item.get("validation_or_test_plan", []) if str(reason).strip()],
                open_questions=[str(reason) for reason in item.get("open_questions", []) if str(reason).strip()],
                required_inputs=[str(reason) for reason in item.get("required_inputs", []) if str(reason).strip()],
                heuristic_blockers=[str(reason) for reason in item.get("heuristic_blockers", []) if str(reason).strip()],
            )
        )
    return menu


def main() -> int:
    args = parse_args()
    dashboards = load_dashboards(Path(args.source_inventory))
    menu = load_menu(Path(args.menu_json) if args.menu_json else None, dashboards)
    include_actions = {item.strip() for item in args.include_actions.split(",") if item.strip()}
    plans = build_terraform_plans(dashboards, menu, include_actions=include_actions)

    out_dir = Path(args.out_dir)
    plan_dir = out_dir / "plans"
    tf_dir = out_dir / "tf_json"
    ensure_dir(out_dir)
    ensure_dir(plan_dir)
    ensure_dir(tf_dir)

    write_json(out_dir / "terraform_plans.json", {"summary": summarize_terraform_plans(plans), "plans": [item.to_dict() for item in plans]})
    for plan in plans:
        write_json(plan_dir / f"{plan.resource_name}.json", plan.to_dict())
        write_text(tf_dir / f"{plan.resource_name}.tf.json", json.dumps(build_tf_json_resource(plan), indent=2) + "\n")

    print(f"wrote terraform dashboard plans to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
