from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


def load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def merged_env(env_file: Path | None = None) -> dict[str, str]:
    merged = dict(os.environ)
    file_values = {}
    if env_file is not None:
        file_values = load_dotenv(env_file)
    else:
        default_path = Path(".env")
        if default_path.exists():
            file_values = load_dotenv(default_path)
    for key, value in file_values.items():
        merged.setdefault(key, value)
    return merged


def require_env(values: dict[str, str], *keys: str) -> tuple[str, ...]:
    missing = [key for key in keys if not values.get(key)]
    if missing:
        raise ConfigError(f"missing required environment variables: {', '.join(missing)}")
    return tuple(values[key] for key in keys)


@dataclass(frozen=True)
class DynatraceAuthConfig:
    base_url: str
    api_token: str


@dataclass(frozen=True)
class DatadogAuthConfig:
    api_url: str
    api_key: str
    app_key: str
    site: str


def load_dynatrace_auth(env_file: Path | None = None) -> DynatraceAuthConfig:
    values = merged_env(env_file)
    base_url, api_token = require_env(values, "DYNATRACE_BASE_URL", "DYNATRACE_API_TOKEN")
    return DynatraceAuthConfig(base_url=base_url.rstrip("/"), api_token=api_token)


def _site_to_api_url(site: str) -> str:
    cleaned = site.strip().lower().removeprefix("https://").removeprefix("http://").rstrip("/")
    if cleaned.startswith("api."):
        return f"https://{cleaned}"
    return f"https://api.{cleaned}"


def load_datadog_auth(env_file: Path | None = None) -> DatadogAuthConfig:
    values = merged_env(env_file)
    api_key, app_key = require_env(values, "DATADOG_API_KEY", "DATADOG_APP_KEY")
    site = values.get("DATADOG_SITE") or values.get("DD_SITE") or "datadoghq.com"
    api_url = values.get("DATADOG_API_URL", "").strip() or _site_to_api_url(site)
    return DatadogAuthConfig(api_url=api_url.rstrip("/"), api_key=api_key, app_key=app_key, site=site)
