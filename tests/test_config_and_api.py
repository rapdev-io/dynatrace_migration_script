from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dashboard_tooling.api_clients import DatadogDashboardApiClient, DynatraceDashboardApiClient, JsonHttpClient
from dashboard_tooling.config import load_datadog_auth, load_dotenv, load_dynatrace_auth


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.payload


class ConfigAndApiTests(unittest.TestCase):
    def test_load_dotenv_parses_basic_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "DYNATRACE_BASE_URL=https://example.live.dynatrace.com\n"
                "DATADOG_SITE=datadoghq.com\n"
                "export DATADOG_API_KEY=test-key\n",
                encoding="utf-8",
            )
            values = load_dotenv(env_path)
        self.assertEqual(values["DYNATRACE_BASE_URL"], "https://example.live.dynatrace.com")
        self.assertEqual(values["DATADOG_SITE"], "datadoghq.com")
        self.assertEqual(values["DATADOG_API_KEY"], "test-key")

    def test_load_auth_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "DYNATRACE_BASE_URL=https://tenant.live.dynatrace.com\n"
                "DYNATRACE_API_TOKEN=dt-token\n"
                "DATADOG_API_KEY=dd-api\n"
                "DATADOG_APP_KEY=dd-app\n"
                "DATADOG_SITE=us3.datadoghq.com\n",
                encoding="utf-8",
            )
            dt = load_dynatrace_auth(env_path)
            dd = load_datadog_auth(env_path)
        self.assertEqual(dt.base_url, "https://tenant.live.dynatrace.com")
        self.assertEqual(dd.api_url, "https://api.us3.datadoghq.com")

    def test_dynatrace_export_dashboards_fetches_details(self) -> None:
        responses = {
            "https://tenant.live.dynatrace.com/api/config/v1/dashboards": {"dashboards": [{"id": "dt-1"}]},
            "https://tenant.live.dynatrace.com/api/config/v1/dashboards/dt-1": {"id": "dt-1", "name": "Example"},
        }

        def transport(request):
            return _FakeResponse(responses[request.full_url])

        config = type("Cfg", (), {"base_url": "https://tenant.live.dynatrace.com", "api_token": "token"})()
        client = DynatraceDashboardApiClient(config, http=JsonHttpClient(transport=transport))
        payload = client.export_dashboards()
        self.assertEqual(payload["dashboards"][0]["name"], "Example")

    def test_datadog_export_dashboards_fetches_details(self) -> None:
        responses = {
            "https://api.datadoghq.com/api/v1/dashboard": {"dashboards": [{"id": "abc-123", "title": "Example"}]},
            "https://api.datadoghq.com/api/v1/dashboard/abc-123": {"id": "abc-123", "widgets": []},
        }

        def transport(request):
            return _FakeResponse(responses[request.full_url])

        config = type("Cfg", (), {"api_url": "https://api.datadoghq.com", "api_key": "api", "app_key": "app", "site": "datadoghq.com"})()
        client = DatadogDashboardApiClient(config, http=JsonHttpClient(transport=transport))
        payload = client.export_dashboards()
        self.assertEqual(payload["dashboards"][0]["title"], "Example")


if __name__ == "__main__":
    unittest.main()
