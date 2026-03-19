from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path

from dashboard_tooling.api_clients import DatadogDashboardApiClient
from dashboard_tooling.models import TerraformDashboardPlan


class DeploymentError(RuntimeError):
    pass


@dataclass
class DatadogWriteResult:
    plan_title: str
    action: str
    dashboard_id: str
    dashboard_url: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "plan_title": self.plan_title,
            "action": self.action,
            "dashboard_id": self.dashboard_id,
            "dashboard_url": self.dashboard_url,
        }


def upsert_dashboard_plan(
    client: DatadogDashboardApiClient,
    plan: TerraformDashboardPlan,
) -> DatadogWriteResult:
    if plan.terraform_mode == "import_existing_dashboard" and plan.matched_target_id:
        payload = client.update_dashboard(plan.matched_target_id, plan.draft_dashboard_json)
        return DatadogWriteResult(
            plan_title=plan.title,
            action="updated",
            dashboard_id=str(payload.get("id") or plan.matched_target_id),
            dashboard_url=str(payload.get("url") or ""),
        )
    payload = client.create_dashboard(plan.draft_dashboard_json)
    return DatadogWriteResult(
        plan_title=plan.title,
        action="created",
        dashboard_id=str(payload.get("id") or ""),
        dashboard_url=str(payload.get("url") or ""),
    )


def _provider_tf_json() -> dict[str, object]:
    return {
        "terraform": {
            "required_providers": {
                "datadog": {
                    "source": "DataDog/datadog",
                }
            }
        },
        "provider": {
            "datadog": {}
        },
    }


def write_terraform_workspace(plans: list[TerraformDashboardPlan], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "provider.tf.json").write_text(json.dumps(_provider_tf_json(), indent=2) + "\n", encoding="utf-8")
    resources: dict[str, dict[str, object]] = {}
    imports: list[dict[str, str]] = []
    for plan in plans:
        resources[plan.resource_name] = {"dashboard": json.dumps(plan.draft_dashboard_json, indent=2)}
        if plan.terraform_mode == "import_existing_dashboard" and plan.matched_target_id:
            imports.append(
                {
                    "to": f'datadog_dashboard_json.{plan.resource_name}',
                    "id": plan.matched_target_id,
                }
            )
    root: dict[str, object] = {"resource": {"datadog_dashboard_json": resources}}
    if imports:
        root["import"] = imports
    (out_dir / "dashboards.tf.json").write_text(json.dumps(root, indent=2) + "\n", encoding="utf-8")
    return out_dir


def run_terraform(work_dir: Path, command: str, *, auto_approve: bool = False) -> subprocess.CompletedProcess[str]:
    terraform = shutil.which("terraform")
    if not terraform:
        raise DeploymentError("terraform binary not found in PATH")
    if command not in {"init", "plan", "apply"}:
        raise DeploymentError(f"unsupported terraform command: {command}")
    args = [terraform, command]
    if command == "apply" and auto_approve:
        args.append("-auto-approve")
    return subprocess.run(args, cwd=work_dir, check=True, capture_output=True, text=True)  # nosec B603
