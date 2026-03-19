#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard_tooling.deployment import run_terraform, write_terraform_workspace
from dashboard_tooling.io import load_json, write_json
from dashboard_tooling.models import TerraformDashboardPlan, TerraformWidgetPlan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a Terraform workspace from dashboard plans and run terraform init/plan/apply."
    )
    parser.add_argument("--plans-json", required=True, help="Path to terraform_plans.json.")
    parser.add_argument("--work-dir", required=True, help="Terraform working directory.")
    parser.add_argument("--command", choices=["init", "plan", "apply"], default="plan")
    parser.add_argument("--auto-approve", action="store_true", help="Pass -auto-approve when command is apply.")
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
    work_dir = write_terraform_workspace(plans, Path(args.work_dir))
    result = run_terraform(work_dir, args.command, auto_approve=args.auto_approve)
    write_json(work_dir / f"terraform-{args.command}-result.json", {"stdout": result.stdout, "stderr": result.stderr})
    print(result.stdout.strip() or f"terraform {args.command} completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
