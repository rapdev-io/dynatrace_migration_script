#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard_tooling.api_clients import DatadogDashboardApiClient
from dashboard_tooling.config import load_datadog_auth
from dashboard_tooling.deployment import upsert_dashboard_plan
from dashboard_tooling.io import load_json, write_json
from dashboard_tooling.models import TerraformDashboardPlan, TerraformWidgetPlan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update Datadog dashboards directly from Terraform dashboard plans."
    )
    parser.add_argument("--plans-json", required=True, help="Path to terraform_plans.json.")
    parser.add_argument("--out", required=True, help="Path to write publish results JSON.")
    parser.add_argument("--env-file", help="Optional .env file to load Datadog auth values from.")
    parser.add_argument(
        "--only-ready",
        action="store_true",
        help="Only publish plans marked terraform_ready.",
    )
    return parser.parse_args()


def _load_plans(path: Path) -> list[TerraformDashboardPlan]:
    payload = load_json(path)
    records = payload.get("plans", []) if isinstance(payload, dict) else []
    plans: list[TerraformDashboardPlan] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        plans.append(
            TerraformDashboardPlan(
                dashboard_id=str(item.get("dashboard_id") or ""),
                title=str(item.get("title") or ""),
                resource_name=str(item.get("resource_name") or ""),
                menu_action=str(item.get("menu_action") or ""),
                terraform_mode=str(item.get("terraform_mode") or ""),
                matched_target_id=str(item.get("matched_target_id") or ""),
                matched_target_title=str(item.get("matched_target_title") or ""),
                terraform_ready=bool(item.get("terraform_ready")),
                required_inputs=[str(v) for v in item.get("required_inputs", []) if str(v).strip()],
                open_questions=[str(v) for v in item.get("open_questions", []) if str(v).strip()],
                template_variable_hints=list(item.get("template_variable_hints", [])),
                widget_plans=[
                    TerraformWidgetPlan(
                        widget_index=int(w.get("widget_index") or 0),
                        source_widget_title=str(w.get("source_widget_title") or ""),
                        source_widget_type=str(w.get("source_widget_type") or ""),
                        suggested_datadog_definition_type=str(w.get("suggested_datadog_definition_type") or ""),
                        mapping_status=str(w.get("mapping_status") or ""),
                        source_query_family=str(w.get("source_query_family") or ""),
                        source_query_text=str(w.get("source_query_text") or ""),
                        placeholder_query=str(w.get("placeholder_query") or ""),
                        notes=[str(v) for v in w.get("notes", []) if str(v).strip()],
                    )
                    for w in item.get("widget_plans", [])
                    if isinstance(w, dict)
                ],
                draft_dashboard_json=dict(item.get("draft_dashboard_json") or {}),
                import_instructions=[str(v) for v in item.get("import_instructions", []) if str(v).strip()],
            )
        )
    return plans


def main() -> int:
    args = parse_args()
    plans = _load_plans(Path(args.plans_json))
    if args.only_ready:
        plans = [item for item in plans if item.terraform_ready]
    client = DatadogDashboardApiClient(load_datadog_auth(Path(args.env_file) if args.env_file else None))
    results = [upsert_dashboard_plan(client, plan).to_dict() for plan in plans]
    write_json(Path(args.out), {"results": results})
    print(f"published {len(results)} dashboard(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
