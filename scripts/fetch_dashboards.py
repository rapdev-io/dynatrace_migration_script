#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard_tooling.api_clients import DatadogDashboardApiClient, DynatraceDashboardApiClient
from dashboard_tooling.config import load_datadog_auth, load_dynatrace_auth
from dashboard_tooling.io import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch dashboards directly from Dynatrace or Datadog APIs and write raw JSON exports."
    )
    parser.add_argument("--source", choices=["dynatrace", "datadog"], required=True)
    parser.add_argument("--out", required=True, help="Path to write the raw export JSON.")
    parser.add_argument("--env-file", help="Optional .env file to load auth values from.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_file = Path(args.env_file) if args.env_file else None
    if args.source == "dynatrace":
        payload = DynatraceDashboardApiClient(load_dynatrace_auth(env_file)).export_dashboards()
    else:
        payload = DatadogDashboardApiClient(load_datadog_auth(env_file)).export_dashboards()
    write_json(Path(args.out), payload)
    print(f"wrote {args.source} dashboards to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
