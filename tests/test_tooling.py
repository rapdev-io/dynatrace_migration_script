from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import json

from dashboard_tooling.annotations import apply_dashboard_annotations, load_annotation_payload
from dashboard_tooling.assessment import build_dashboard_menu
from dashboard_tooling.compare import compare_dashboards
from dashboard_tooling.normalize import normalize_datadog_dashboards, normalize_dynatrace_dashboards
from dashboard_tooling.recommendations import recommend_dashboard
from dashboard_tooling.scaffold import build_datadog_scaffold, build_review_packet
from dashboard_tooling.terraform_planner import build_terraform_plans


class DashboardToolingTests(unittest.TestCase):
    def test_dynatrace_normalization_extracts_queries(self) -> None:
        payload = {
            "dashboards": [
                {
                    "id": "dt-1",
                    "name": "Orders Overview",
                    "tiles": [
                        {"name": "Latency", "tileType": "DATA_EXPLORER", "queries": ["timeseries avg(dt.service.request.response_time)"]},
                        {"name": "Errors", "tileType": "TABLE", "query": "fetch logs | filter status == \"ERROR\""},
                    ],
                }
            ]
        }
        dashboards = normalize_dynatrace_dashboards(payload)
        self.assertEqual(len(dashboards), 1)
        self.assertEqual(dashboards[0].query_count, 2)
        self.assertEqual(dashboards[0].manual_review_reasons, [])

    def test_datadog_normalization_extracts_widget_queries(self) -> None:
        payload = {
            "dashboards": [
                {
                    "id": "abc",
                    "title": "Orders Overview",
                    "widgets": [
                        {
                            "definition": {
                                "type": "timeseries",
                                "title": "Latency",
                                "requests": [{"q": "avg:trace.http.request{service:orders}"}],
                            }
                        }
                    ],
                }
            ]
        }
        dashboards = normalize_datadog_dashboards(payload)
        self.assertEqual(len(dashboards), 1)
        self.assertEqual(dashboards[0].query_count, 1)

    def test_compare_dashboards_finds_high_confidence_candidate(self) -> None:
        source = normalize_dynatrace_dashboards(
            {"dashboards": [{"id": "dt-1", "name": "Orders Overview", "tiles": [{"name": "Latency", "tileType": "chart", "query": "timeseries avg(x)"}]}]}
        )
        target = normalize_datadog_dashboards(
            {"dashboards": [{"id": "dd-1", "title": "Orders Overview", "widgets": [{"definition": {"type": "timeseries", "requests": [{"q": "avg:foo{*}"}]}}]}]}
        )
        parity = compare_dashboards(source, target)
        self.assertEqual(parity[0].parity_status, "exact_title_match")

    def test_scaffold_contains_manual_rebuild_marker(self) -> None:
        source = normalize_dynatrace_dashboards(
            {"dashboards": [{"id": "dt-1", "name": "Orders Overview", "tiles": [{"name": "Latency", "tileType": "chart", "query": "timeseries avg(x)"}]}]}
        )[0]
        packet = build_review_packet(source)
        scaffold = build_datadog_scaffold(source)
        self.assertIn("Operator Decision", packet)
        self.assertEqual(scaffold["title"], "Orders Overview")

    def test_heuristics_work_without_annotations(self) -> None:
        source = normalize_dynatrace_dashboards(
            {
                "dashboards": [
                    {
                        "id": "dt-1",
                        "name": "Build Health Deep Dive",
                        "dashboardFilter": {"variables": ["BuildStatus", "PullRequestNumber"]},
                        "tiles": [
                            {
                                "name": "Build Success Rate by Pod/Stage",
                                "tileType": "TABLE",
                                "query": "SELECT pod, stage, CASE WHEN success > 0 THEN 1 END FROM runs JOIN stages ON runs.id = stages.run_id",
                            }
                        ],
                    }
                ]
            }
        )[0]
        self.assertIn("dynamic_filter_dependency", source.heuristic_blockers)
        self.assertIn("table_or_list_result_shaping", source.heuristic_blockers)
        self.assertIn("multi_stage_query_logic", source.queries[0].heuristic_signals)

    def test_annotations_are_optional_overlay(self) -> None:
        source = normalize_dynatrace_dashboards(
            {"dashboards": [{"id": "dt-1", "name": "Build Health Deep Dive", "tiles": [{"name": "Latency", "tileType": "chart", "query": "timeseries avg(x)"}]}]}
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "annotations.json"
            path.write_text(
                json.dumps(
                    {
                        "dashboards": [
                            {
                                "dashboard_id": "dt-1",
                                "blockers": ["ddsdl_filter_pushdown_gap"],
                                "notes": ["DDSQL filters apply too late for some widgets."],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            apply_dashboard_annotations(source, load_annotation_payload(path))
        self.assertIn("ddsdl_filter_pushdown_gap", source[0].annotation_blockers)
        self.assertIn("DDSQL filters apply too late for some widgets.", source[0].annotation_notes)

    def test_recommendation_identifies_terraform_ready_service_dashboard(self) -> None:
        dashboard = normalize_dynatrace_dashboards(
            {
                "dashboards": [
                    {
                        "id": "dt-1",
                        "name": "Checkout Service Overview",
                        "dashboardFilter": {"variables": ["env", "service"]},
                        "tags": ["team:payments", "service:checkout"],
                        "tiles": [
                            {"name": "Latency", "tileType": "DATA_EXPLORER", "query": "timeseries avg(dt.service.request.response_time)"},
                            {"name": "Errors", "tileType": "DATA_EXPLORER", "query": "timeseries sum(dt.service.errors)"},
                            {"name": "Throughput", "tileType": "DATA_EXPLORER", "query": "timeseries sum(dt.service.request_count)"},
                        ],
                    }
                ]
            }
        )[0]
        recommendation = recommend_dashboard(dashboard)
        self.assertEqual(recommendation.recommendation_status, "create_with_terraform")
        self.assertTrue(recommendation.terraform_ready)
        self.assertEqual(recommendation.suggested_dashboard_tier, "service_health")

    def test_recommendation_asks_questions_for_low_signal_dashboard(self) -> None:
        dashboard = normalize_dynatrace_dashboards(
            {
                "dashboards": [
                    {
                        "id": "dt-2",
                        "name": "Build Notes",
                        "tiles": [
                            {"name": "Context", "tileType": "MARKDOWN", "markdown": "release notes"},
                        ],
                    }
                ]
            }
        )[0]
        recommendation = recommend_dashboard(dashboard)
        self.assertFalse(recommendation.terraform_ready)
        self.assertIn(recommendation.recommendation_status, {"review_value_before_build", "defer_missing_signal"})
        self.assertTrue(recommendation.open_questions)

    def test_menu_combines_parity_and_recommendation_signals(self) -> None:
        source = normalize_dynatrace_dashboards(
            {
                "dashboards": [
                    {
                        "id": "dt-3",
                        "name": "Orders Overview",
                        "dashboardFilter": {"variables": ["env"]},
                        "tiles": [
                            {"name": "Latency", "tileType": "DATA_EXPLORER", "query": "timeseries avg(dt.service.request.response_time)"},
                            {"name": "Errors", "tileType": "DATA_EXPLORER", "query": "timeseries sum(dt.service.errors)"},
                            {"name": "Traffic", "tileType": "DATA_EXPLORER", "query": "timeseries sum(dt.service.request_count)"},
                        ],
                    }
                ]
            }
        )
        target = normalize_datadog_dashboards(
            {
                "dashboards": [
                    {
                        "id": "dd-3",
                        "title": "Orders Overview",
                        "widgets": [{"definition": {"type": "timeseries", "requests": [{"q": "avg:foo{*}"}]}}],
                    }
                ]
            }
        )
        parity = compare_dashboards(source, target)
        menu = build_dashboard_menu(source, parity)
        self.assertEqual(menu[0].parity_status, "exact_title_match")
        self.assertEqual(menu[0].menu_action, "validate_and_improve_existing")
        self.assertTrue(menu[0].validation_or_test_plan)

    def test_terraform_planner_emits_import_mode_for_existing_dashboard(self) -> None:
        source = normalize_dynatrace_dashboards(
            {
                "dashboards": [
                    {
                        "id": "dt-4",
                        "name": "Checkout Service Overview",
                        "dashboardFilter": {"variables": ["env"]},
                        "tiles": [
                            {"name": "Latency", "tileType": "DATA_EXPLORER", "query": "timeseries avg(dt.service.request.response_time)"},
                            {"name": "Errors", "tileType": "DATA_EXPLORER", "query": "timeseries sum(dt.service.errors)"},
                            {"name": "Throughput", "tileType": "DATA_EXPLORER", "query": "timeseries sum(dt.service.request_count)"},
                        ],
                    }
                ]
            }
        )
        target = normalize_datadog_dashboards(
            {
                "dashboards": [
                    {
                        "id": "dd-4",
                        "title": "Checkout Service Overview",
                        "widgets": [{"definition": {"type": "timeseries", "requests": [{"q": "avg:foo{*}"}]}}],
                    }
                ]
            }
        )
        menu = build_dashboard_menu(source, compare_dashboards(source, target))
        plans = build_terraform_plans(source, menu)
        self.assertEqual(plans[0].terraform_mode, "import_existing_dashboard")
        self.assertEqual(plans[0].matched_target_id, "dd-4")
        self.assertTrue(plans[0].import_instructions)


    def test_ddsql_not_flagged_for_translation(self) -> None:
        # A Datadog dashboard with a DDSQL query should be classified as "ddsql",
        # not "sql_like", and must not receive a translation_review_required signal.
        payload = {
            "dashboards": [
                {
                    "id": "dd-sql",
                    "title": "Cost Overview",
                    "widgets": [
                        {
                            "definition": {
                                "type": "query_table",
                                "title": "Cost by Service",
                                "requests": [{"q": "SELECT service, SUM(cost) FROM usage GROUP BY service"}],
                            }
                        }
                    ],
                }
            ]
        }
        dashboards = normalize_datadog_dashboards(payload)
        query = dashboards[0].queries[0]
        self.assertEqual(query.query_family, "ddsql")
        self.assertNotIn("translation_review_required", query.heuristic_signals)

    def test_dynatrace_usql_still_flagged_for_translation(self) -> None:
        # A Dynatrace dashboard with a USQL query must remain "sql_like" and
        # receive translation_review_required since it targets DT data.
        payload = {
            "dashboards": [
                {
                    "id": "dt-sql",
                    "name": "Session Overview",
                    "tiles": [
                        {
                            "name": "Sessions",
                            "tileType": "TABLE",
                            "query": "SELECT usersession.userType, COUNT(*) FROM usersession GROUP BY usersession.userType",
                        }
                    ],
                }
            ]
        }
        dashboards = normalize_dynatrace_dashboards(payload)
        query = dashboards[0].queries[0]
        self.assertEqual(query.query_family, "sql_like")
        self.assertIn("translation_review_required", query.heuristic_signals)


if __name__ == "__main__":
    unittest.main()
