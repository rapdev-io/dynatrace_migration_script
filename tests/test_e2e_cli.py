from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class EndToEndCliTests(unittest.TestCase):
    def test_full_cli_pipeline_with_optional_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dynatrace_input = tmp_path / "dynatrace.json"
            datadog_input = tmp_path / "datadog.json"
            annotations_input = tmp_path / "annotations.json"

            dynatrace_input.write_text(
                json.dumps(
                    {
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
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            datadog_input.write_text(
                json.dumps(
                    {
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
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            annotations_input.write_text(
                json.dumps(
                    {
                        "dashboards": [
                            {
                                "title": "Build Health Deep Dive",
                                "blockers": ["ddsdl_filter_pushdown_gap", "partial_parity_acceptable"],
                                "notes": ["Some widgets lose filter pushdown in DDSQL."],
                            }
                        ]
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            source_out = tmp_path / "source"
            target_out = tmp_path / "target"
            parity_out = tmp_path / "parity"
            annotated_out = tmp_path / "annotated"
            review_out = tmp_path / "review"
            analysis_out = tmp_path / "analysis"
            menu_out = tmp_path / "menu"
            terraform_out = tmp_path / "terraform"

            commands = [
                [
                    "python3",
                    "scripts/normalize_dashboards.py",
                    "--source",
                    "dynatrace",
                    "--input",
                    str(dynatrace_input),
                    "--out-dir",
                    str(source_out),
                ],
                [
                    "python3",
                    "scripts/normalize_dashboards.py",
                    "--source",
                    "datadog",
                    "--input",
                    str(datadog_input),
                    "--out-dir",
                    str(target_out),
                ],
                [
                    "python3",
                    "scripts/compare_dashboards.py",
                    "--source-inventory",
                    str(source_out / "inventory.json"),
                    "--target-inventory",
                    str(target_out / "inventory.json"),
                    "--out-dir",
                    str(parity_out),
                ],
                [
                    "python3",
                    "scripts/annotate_review_queue.py",
                    "--source-inventory",
                    str(source_out / "inventory.json"),
                    "--annotations",
                    str(annotations_input),
                    "--parity-json",
                    str(parity_out / "parity.json"),
                    "--out-dir",
                    str(annotated_out),
                ],
                [
                    "python3",
                    "scripts/generate_review_scaffolds.py",
                    "--source-inventory",
                    str(annotated_out / "inventory.json"),
                    "--parity-json",
                    str(annotated_out / "parity.json"),
                    "--out-dir",
                    str(review_out),
                    "--status-filter",
                    "exact_title_match",
                ],
                [
                    "python3",
                    "scripts/analyze_dashboard_candidates.py",
                    "--source-inventory",
                    str(annotated_out / "inventory.json"),
                    "--out-dir",
                    str(analysis_out),
                ],
                [
                    "python3",
                    "scripts/build_dashboard_menu.py",
                    "--source-inventory",
                    str(annotated_out / "inventory.json"),
                    "--parity-json",
                    str(annotated_out / "parity.json"),
                    "--out-dir",
                    str(menu_out),
                ],
                [
                    "python3",
                    "scripts/plan_terraform_dashboards.py",
                    "--source-inventory",
                    str(annotated_out / "inventory.json"),
                    "--menu-json",
                    str(menu_out / "menu.json"),
                    "--out-dir",
                    str(terraform_out),
                ],
            ]

            for command in commands:
                subprocess.run(command, cwd=REPO_ROOT, check=True, capture_output=True, text=True)

            source_inventory = json.loads((source_out / "inventory.json").read_text(encoding="utf-8"))
            parity_inventory = json.loads((annotated_out / "parity.json").read_text(encoding="utf-8"))
            review_packet = (review_out / "review_packets" / "build-health-deep-dive.md").read_text(encoding="utf-8")
            scaffold = json.loads(
                (review_out / "datadog_scaffolds" / "build-health-deep-dive.json").read_text(encoding="utf-8")
            )
            recommendations = json.loads((analysis_out / "recommendations.json").read_text(encoding="utf-8"))
            menu = json.loads((menu_out / "menu.json").read_text(encoding="utf-8"))
            terraform = json.loads((terraform_out / "terraform_plans.json").read_text(encoding="utf-8"))

            self.assertEqual(source_inventory["source"], "dynatrace")
            self.assertIn("dynamic_filter_dependency", source_inventory["dashboards"][0]["heuristic_blockers"])
            self.assertEqual(parity_inventory["parity"][0]["parity_status"], "exact_title_match")
            self.assertIn("ddsdl_filter_pushdown_gap", parity_inventory["parity"][0]["annotation_blockers"])
            self.assertIn("Optional Annotations", review_packet)
            self.assertEqual(scaffold["title"], "Build Health Deep Dive")
            self.assertEqual(recommendations["recommendations"][0]["title"], "Build Health Deep Dive")
            self.assertIn(
                recommendations["recommendations"][0]["recommendation_status"],
                {"candidate_pending_answers", "review_value_before_build", "create_with_terraform"},
            )
            self.assertEqual(menu["menu"][0]["parity_status"], "exact_title_match")
            self.assertIn(
                menu["menu"][0]["menu_action"],
                {"validate_and_improve_existing", "validate_existing_parity"},
            )
            self.assertTrue(terraform["plans"])
            self.assertIn(terraform["plans"][0]["terraform_mode"], {"create_new_dashboard", "import_existing_dashboard"})


if __name__ == "__main__":
    unittest.main()
