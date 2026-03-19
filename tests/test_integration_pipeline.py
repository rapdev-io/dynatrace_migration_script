from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dashboard_tooling.annotations import apply_dashboard_annotations, apply_parity_annotations
from dashboard_tooling.compare import compare_dashboards
from dashboard_tooling.io import load_json, write_json
from dashboard_tooling.models import DashboardRecord, ParityRecord, QueryRecord
from dashboard_tooling.normalize import normalize_datadog_dashboards, normalize_dynatrace_dashboards


def _dynatrace_payload() -> dict[str, object]:
    return {
        "dashboards": [
            {
                "id": "dt-policy-center",
                "name": "Build Health Deep Dive",
                "dashboardFilter": {"variables": ["BuildStatus", "ServiceName", "TargetBranch"]},
                "tiles": [
                    {
                        "name": "Build Success Rate by Pod/Stage",
                        "tileType": "TABLE",
                        "query": "SELECT pod, stage, CASE WHEN success > 0 THEN 1 END FROM runs JOIN stages ON runs.id = stages.run_id",
                    },
                    {
                        "name": "Wait time by Reason",
                        "tileType": "DATA_EXPLORER",
                        "query": "timeseries avg(build.wait_time), by:{reason} | timeshift 1h",
                    },
                ],
            }
        ]
    }


def _datadog_payload() -> dict[str, object]:
    return {
        "dashboards": [
            {
                "id": "dd-policy-center",
                "title": "Build Health Deep Dive",
                "template_variables": [{"name": "ServiceName"}],
                "widgets": [
                    {
                        "definition": {
                            "type": "query_table",
                            "title": "Build Success Rate by Pod/Stage",
                            "query": "SELECT pod, stage FROM ci_pipeline_runs",
                        }
                    }
                ],
            }
        ]
    }


def _hydrate_inventory(path: Path) -> list[DashboardRecord]:
    payload = load_json(path)
    assert isinstance(payload, dict)
    dashboards = []
    for item in payload["dashboards"]:
        dashboard = DashboardRecord(
            source_system=str(item["source_system"]),
            dashboard_id=str(item["dashboard_id"]),
            title=str(item["title"]),
            description=str(item.get("description") or ""),
            owner=str(item.get("owner") or ""),
            tags=[str(tag) for tag in item.get("tags", [])],
            widget_count=int(item.get("widget_count") or 0),
            widget_types=[str(tag) for tag in item.get("widget_types", [])],
            query_count=int(item.get("query_count") or 0),
            variables=[str(tag) for tag in item.get("variables", [])],
            raw_references=dict(item.get("raw_references") or {}),
            complexity_score=int(item.get("complexity_score") or 0),
            manual_review_reasons=[str(reason) for reason in item.get("manual_review_reasons", [])],
            heuristic_blockers=[str(reason) for reason in item.get("heuristic_blockers", [])],
            annotation_notes=[str(note) for note in item.get("annotation_notes", [])],
            annotation_blockers=[str(note) for note in item.get("annotation_blockers", [])],
        )
        for query in item.get("queries", []):
            dashboard.queries.append(
                QueryRecord(
                    dashboard_id=str(query["dashboard_id"]),
                    dashboard_title=str(query["dashboard_title"]),
                    widget_index=int(query["widget_index"]),
                    widget_title=str(query["widget_title"]),
                    widget_type=str(query["widget_type"]),
                    query_text=str(query["query_text"]),
                    query_family=str(query["query_family"]),
                    heuristic_signals=[str(sig) for sig in query.get("heuristic_signals", [])],
                )
            )
        dashboards.append(dashboard)
    return dashboards


class IntegrationPipelineTests(unittest.TestCase):
    def test_annotation_and_parity_overlay_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_dashboards = normalize_dynatrace_dashboards(_dynatrace_payload())
            target_dashboards = normalize_datadog_dashboards(_datadog_payload())

            annotation_payload = {
                "dashboards": [
                    {
                        "dashboard_id": "dt-policy-center",
                        "blockers": ["ddsdl_filter_pushdown_gap", "partial_parity_acceptable"],
                        "notes": ["Some widgets lose filter pushdown in DDSQL."],
                    }
                ]
            }
            apply_dashboard_annotations(source_dashboards, annotation_payload)

            source_inventory_path = tmp_path / "source_inventory.json"
            target_inventory_path = tmp_path / "target_inventory.json"
            write_json(
                source_inventory_path,
                {"source": "dynatrace", "dashboards": [item.to_dict() for item in source_dashboards]},
            )
            write_json(
                target_inventory_path,
                {"source": "datadog", "dashboards": [item.to_dict() for item in target_dashboards]},
            )

            rehydrated_source = _hydrate_inventory(source_inventory_path)
            rehydrated_target = _hydrate_inventory(target_inventory_path)
            parity = compare_dashboards(rehydrated_source, rehydrated_target)
            apply_parity_annotations(parity, rehydrated_source)

            self.assertEqual(len(parity), 1)
            self.assertEqual(parity[0].parity_status, "exact_title_match")
            self.assertIn("dynamic_filter_dependency", parity[0].heuristic_blockers)
            self.assertIn("ddsdl_filter_pushdown_gap", parity[0].annotation_blockers)
            self.assertIn("Some widgets lose filter pushdown in DDSQL.", parity[0].annotation_notes)

            parity_path = tmp_path / "parity.json"
            write_json(parity_path, {"parity": [item.to_dict() for item in parity]})
            parity_payload = json.loads(parity_path.read_text(encoding="utf-8"))
            self.assertEqual(
                parity_payload["parity"][0]["annotation_blockers"],
                ["ddsdl_filter_pushdown_gap", "partial_parity_acceptable"],
            )


if __name__ == "__main__":
    unittest.main()
