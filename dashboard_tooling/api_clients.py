from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dashboard_tooling.config import DatadogAuthConfig, DynatraceAuthConfig


class ApiClientError(RuntimeError):
    pass


Transport = Callable[[Request], object]


def _default_transport(request: Request):
    return urlopen(request, timeout=60)


@dataclass
class JsonHttpClient:
    transport: Transport = _default_transport

    def get_json(self, url: str, headers: dict[str, str], *, query: dict[str, str] | None = None) -> object:
        final_url = url
        if query:
            final_url = f"{url}?{urlencode(query, doseq=True)}"
        request = Request(final_url, headers=headers, method="GET")
        try:
            with self.transport(request) as response:
                payload = response.read().decode("utf-8")
        except Exception as exc:  # pragma: no cover
            raise ApiClientError(f"request failed for {final_url}: {exc}") from exc
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ApiClientError(f"invalid JSON response from {final_url}") from exc

    def request_json(self, method: str, url: str, headers: dict[str, str], *, body: object | None = None) -> object:
        payload_bytes = None
        request_headers = dict(headers)
        if body is not None:
            payload_bytes = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        request = Request(url, headers=request_headers, data=payload_bytes, method=method)
        try:
            with self.transport(request) as response:
                payload = response.read().decode("utf-8")
        except Exception as exc:  # pragma: no cover
            raise ApiClientError(f"request failed for {url}: {exc}") from exc
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ApiClientError(f"invalid JSON response from {url}") from exc


class DynatraceDashboardApiClient:
    def __init__(self, config: DynatraceAuthConfig, http: JsonHttpClient | None = None) -> None:
        self.config = config
        self.http = http or JsonHttpClient()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Api-Token {self.config.api_token}",
            "Accept": "application/json",
        }

    def list_dashboards(self) -> list[dict[str, object]]:
        payload = self.http.get_json(f"{self.config.base_url}/api/config/v1/dashboards", self._headers)
        dashboards = payload.get("dashboards", []) if isinstance(payload, dict) else []
        return [item for item in dashboards if isinstance(item, dict)]

    def get_dashboard(self, dashboard_id: str) -> dict[str, object]:
        payload = self.http.get_json(f"{self.config.base_url}/api/config/v1/dashboards/{dashboard_id}", self._headers)
        if not isinstance(payload, dict):
            raise ApiClientError(f"unexpected dashboard payload for Dynatrace dashboard {dashboard_id}")
        return payload

    def export_dashboards(self) -> dict[str, object]:
        dashboards: list[dict[str, object]] = []
        for item in self.list_dashboards():
            dashboard_id = str(item.get("id") or "")
            if not dashboard_id:
                continue
            full = self.get_dashboard(dashboard_id)
            full.setdefault("id", dashboard_id)
            dashboards.append(full)
        return {"dashboards": dashboards}


class DatadogDashboardApiClient:
    def __init__(self, config: DatadogAuthConfig, http: JsonHttpClient | None = None) -> None:
        self.config = config
        self.http = http or JsonHttpClient()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "DD-API-KEY": self.config.api_key,
            "DD-APPLICATION-KEY": self.config.app_key,
            "Accept": "application/json",
        }

    def list_dashboards(self) -> list[dict[str, object]]:
        payload = self.http.get_json(f"{self.config.api_url}/api/v1/dashboard", self._headers)
        dashboards = payload.get("dashboards", []) if isinstance(payload, dict) else []
        return [item for item in dashboards if isinstance(item, dict)]

    def get_dashboard(self, dashboard_id: str) -> dict[str, object]:
        payload = self.http.get_json(f"{self.config.api_url}/api/v1/dashboard/{dashboard_id}", self._headers)
        if not isinstance(payload, dict):
            raise ApiClientError(f"unexpected dashboard payload for Datadog dashboard {dashboard_id}")
        return payload

    def export_dashboards(self) -> dict[str, object]:
        dashboards: list[dict[str, object]] = []
        for item in self.list_dashboards():
            dashboard_id = str(item.get("id") or "")
            if not dashboard_id:
                continue
            full = self.get_dashboard(dashboard_id)
            full.setdefault("id", dashboard_id)
            for key in ("title", "url", "description", "author_handle", "tags"):
                if key in item and key not in full:
                    full[key] = item[key]
            dashboards.append(full)
        return {"dashboards": dashboards}

    def create_dashboard(self, dashboard: dict[str, object]) -> dict[str, object]:
        payload = self.http.request_json(
            "POST",
            f"{self.config.api_url}/api/v1/dashboard",
            self._headers,
            body=dashboard,
        )
        if not isinstance(payload, dict):
            raise ApiClientError("unexpected Datadog create dashboard response")
        return payload

    def update_dashboard(self, dashboard_id: str, dashboard: dict[str, object]) -> dict[str, object]:
        payload = self.http.request_json(
            "PUT",
            f"{self.config.api_url}/api/v1/dashboard/{dashboard_id}",
            self._headers,
            body=dashboard,
        )
        if not isinstance(payload, dict):
            raise ApiClientError("unexpected Datadog update dashboard response")
        return payload
