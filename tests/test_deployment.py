from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard_tooling.deployment import run_terraform, upsert_dashboard_plan, write_terraform_workspace
from dashboard_tooling.models import TerraformDashboardPlan


class _FakeDatadogClient:
    def __init__(self) -> None:
        self.created = []
        self.updated = []

    def create_dashboard(self, dashboard):
        self.created.append(dashboard)
        return {"id": "new-id", "url": "/dashboard/new-id"}

    def update_dashboard(self, dashboard_id, dashboard):
        self.updated.append((dashboard_id, dashboard))
        return {"id": dashboard_id, "url": f"/dashboard/{dashboard_id}"}


class DeploymentTests(unittest.TestCase):
    def _plan(self, *, mode: str, matched_target_id: str = "") -> TerraformDashboardPlan:
        return TerraformDashboardPlan(
            dashboard_id="dt-1",
            title="Checkout Service Overview",
            resource_name="checkout-service-overview",
            menu_action="create_or_rebuild_with_terraform",
            terraform_mode=mode,
            matched_target_id=matched_target_id,
            matched_target_title="Checkout Service Overview" if matched_target_id else "",
            terraform_ready=True,
            draft_dashboard_json={"title": "Checkout Service Overview", "widgets": []},
        )

    def test_upsert_dashboard_plan_creates_when_no_target(self) -> None:
        client = _FakeDatadogClient()
        result = upsert_dashboard_plan(client, self._plan(mode="create_new_dashboard"))
        self.assertEqual(result.action, "created")
        self.assertEqual(client.created[0]["title"], "Checkout Service Overview")

    def test_upsert_dashboard_plan_updates_existing_dashboard(self) -> None:
        client = _FakeDatadogClient()
        result = upsert_dashboard_plan(client, self._plan(mode="import_existing_dashboard", matched_target_id="abc-123"))
        self.assertEqual(result.action, "updated")
        self.assertEqual(client.updated[0][0], "abc-123")

    def test_write_terraform_workspace_emits_provider_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            write_terraform_workspace(
                [
                    self._plan(mode="create_new_dashboard"),
                    self._plan(mode="import_existing_dashboard", matched_target_id="abc-123"),
                ],
                work_dir,
            )
            provider = json.loads((work_dir / "provider.tf.json").read_text(encoding="utf-8"))
            dashboards = json.loads((work_dir / "dashboards.tf.json").read_text(encoding="utf-8"))
        self.assertIn("provider", provider)
        self.assertIn("import", dashboards)

    @patch("dashboard_tooling.deployment.shutil.which", return_value="/usr/bin/terraform")
    @patch("dashboard_tooling.deployment.subprocess.run")
    def test_run_terraform_invokes_binary(self, mock_run, _mock_which) -> None:
        mock_run.return_value.stdout = "ok"
        mock_run.return_value.stderr = ""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_terraform(Path(tmpdir), "plan")
        self.assertEqual(result.stdout, "ok")
        mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
