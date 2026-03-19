#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard_tooling.api_clients import DatadogDashboardApiClient, DynatraceDashboardApiClient
from dashboard_tooling.assessment import build_dashboard_menu, build_menu_report, summarize_menu
from dashboard_tooling.annotations import apply_dashboard_annotations, apply_parity_annotations, load_annotation_payload
from dashboard_tooling.compare import compare_dashboards
from dashboard_tooling.config import load_datadog_auth, load_dynatrace_auth
from dashboard_tooling.io import ensure_dir, load_json, write_csv, write_json, write_text
from dashboard_tooling.normalize import (
    normalize_datadog_dashboards,
    normalize_dynatrace_dashboards,
    summarize_dashboards,
)
from dashboard_tooling.recommendations import build_recommendation_report, recommend_dashboards, summarize_recommendations
from dashboard_tooling.scaffold import (
    build_datadog_scaffold,
    build_review_packet,
    dump_json,
    review_packet_filename,
    scaffold_filename,
)
from dashboard_tooling.terraform_planner import build_tf_json_resource, build_terraform_plans, summarize_terraform_plans


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the dashboard assessment workflow from local JSON and/or live Dynatrace and Datadog APIs."
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--dynatrace-input", help="Path to raw Dynatrace dashboard export JSON.")
    parser.add_argument("--datadog-input", help="Path to raw Datadog dashboard export JSON.")
    parser.add_argument("--fetch-dynatrace", action="store_true", help="Fetch Dynatrace dashboards from the API.")
    parser.add_argument("--fetch-datadog", action="store_true", help="Fetch Datadog dashboards from the API.")
    parser.add_argument("--annotations", help="Optional annotation JSON overlay.")
    parser.add_argument("--env-file", help="Optional .env file to load auth values from.")
    parser.add_argument(
        "--terraform-actions",
        default="create_or_rebuild_with_terraform,validate_and_improve_existing,validate_existing_parity",
        help="Comma-separated menu actions to convert into Terraform plans.",
    )
    return parser.parse_args()


def _load_source_payload(args: argparse.Namespace):
    env_file = Path(args.env_file) if args.env_file else None
    if args.fetch_dynatrace:
        return DynatraceDashboardApiClient(load_dynatrace_auth(env_file)).export_dashboards()
    if args.dynatrace_input:
        return load_json(Path(args.dynatrace_input))
    raise SystemExit("provide either --dynatrace-input or --fetch-dynatrace")


def _load_target_payload(args: argparse.Namespace):
    env_file = Path(args.env_file) if args.env_file else None
    if args.fetch_datadog:
        return DatadogDashboardApiClient(load_datadog_auth(env_file)).export_dashboards()
    if args.datadog_input:
        return load_json(Path(args.datadog_input))
    return None


def _write_inventory(out_dir: Path, source: str, dashboards) -> None:
    write_json(
        out_dir / "inventory.json",
        {
            "source": source,
            "summary": summarize_dashboards(dashboards),
            "dashboards": [item.to_dict() for item in dashboards],
        },
    )
    write_csv(
        out_dir / "queries.csv",
        [
            {
                "dashboard_id": item.dashboard_id,
                "dashboard_title": item.dashboard_title,
                "widget_index": item.widget_index,
                "widget_title": item.widget_title,
                "widget_type": item.widget_type,
                "query_family": item.query_family,
                "heuristic_signals": "|".join(item.heuristic_signals),
                "query_text": item.query_text,
            }
            for dashboard in dashboards
            for item in dashboard.queries
        ],
        fieldnames=[
            "dashboard_id",
            "dashboard_title",
            "widget_index",
            "widget_title",
            "widget_type",
            "query_family",
            "heuristic_signals",
            "query_text",
        ],
    )


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    raw_dir = out_dir / "raw"
    source_dir = out_dir / "source"
    target_dir = out_dir / "target"
    parity_dir = out_dir / "parity"
    analysis_dir = out_dir / "analysis"
    menu_dir = out_dir / "menu"
    review_dir = out_dir / "review"
    terraform_dir = out_dir / "terraform"
    for path in (raw_dir, source_dir, target_dir, parity_dir, analysis_dir, menu_dir, review_dir, terraform_dir):
        ensure_dir(path)

    source_payload = _load_source_payload(args)
    write_json(raw_dir / "dynatrace.json", source_payload)
    source_dashboards = normalize_dynatrace_dashboards(source_payload)
    if args.annotations:
        apply_dashboard_annotations(source_dashboards, load_annotation_payload(Path(args.annotations)))
    _write_inventory(source_dir, "dynatrace", source_dashboards)

    target_payload = _load_target_payload(args)
    parity = []
    if target_payload is not None:
        write_json(raw_dir / "datadog.json", target_payload)
        target_dashboards = normalize_datadog_dashboards(target_payload)
        _write_inventory(target_dir, "datadog", target_dashboards)
        parity = compare_dashboards(source_dashboards, target_dashboards)
        apply_parity_annotations(parity, source_dashboards)
        write_json(parity_dir / "parity.json", {"parity": [item.to_dict() for item in parity]})

    recommendations = recommend_dashboards(source_dashboards)
    write_json(
        analysis_dir / "recommendations.json",
        {"summary": summarize_recommendations(recommendations), "recommendations": [item.to_dict() for item in recommendations]},
    )
    write_text(analysis_dir / "recommendations.md", build_recommendation_report(recommendations))

    menu = build_dashboard_menu(source_dashboards, parity)
    write_json(menu_dir / "menu.json", {"summary": summarize_menu(menu), "menu": [item.to_dict() for item in menu]})
    write_text(menu_dir / "menu.md", build_menu_report(menu))

    review_packets_dir = review_dir / "review_packets"
    scaffold_dir = review_dir / "datadog_scaffolds"
    ensure_dir(review_packets_dir)
    ensure_dir(scaffold_dir)
    parity_map = {item.source_dashboard_id: item for item in parity}
    for dashboard in source_dashboards:
        parity_record = parity_map.get(dashboard.dashboard_id)
        write_text(review_packets_dir / review_packet_filename(dashboard), build_review_packet(dashboard, parity_record))
        write_text(scaffold_dir / scaffold_filename(dashboard), dump_json(build_datadog_scaffold(dashboard)))

    include_actions = {item.strip() for item in args.terraform_actions.split(",") if item.strip()}
    plans = build_terraform_plans(source_dashboards, menu, include_actions=include_actions)
    plans_dir = terraform_dir / "plans"
    tf_dir = terraform_dir / "tf_json"
    ensure_dir(plans_dir)
    ensure_dir(tf_dir)
    write_json(terraform_dir / "terraform_plans.json", {"summary": summarize_terraform_plans(plans), "plans": [item.to_dict() for item in plans]})
    for plan in plans:
        write_json(plans_dir / f"{plan.resource_name}.json", plan.to_dict())
        write_text(tf_dir / f"{plan.resource_name}.tf.json", json.dumps(build_tf_json_resource(plan), indent=2) + "\n")

    print(f"wrote dashboard assessment outputs to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
