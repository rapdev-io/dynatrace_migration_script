# Dashboard Migration Tooling

Python tooling for evaluating dashboard migrations between observability platforms, with a current focus on Dynatrace-to-Datadog dashboard analysis and Terraform planning.

The repository is designed to answer four practical questions:
- What dashboards exist in the source environment?
- What parity already exists in the target environment?
- Which dashboards are worth keeping, improving, rebuilding, or dropping?
- Which approved dashboards can move into Terraform planning now, and what still needs human input?

## Features

- Normalize raw dashboard exports into a common inventory model.
- Extract per-widget query text and classify likely query families.
- Infer dashboard complexity and review blockers from source content.
- Compare source and target dashboard inventories for heuristic parity candidates.
- Overlay optional annotations to capture known blockers, caveats, or migration notes.
- Generate review packets and draft Datadog scaffold JSON for manual review.
- Recommend which dashboards should be rebuilt, improved, validated, deferred, or dropped.
- Produce a migration menu that combines inventory, parity, and recommendation signals.
- Generate Terraform-oriented dashboard plans and draft `datadog_dashboard_json` resources.
- Distinguish between creating new dashboards and importing existing Datadog dashboards into Terraform management.

## What This Repo Does Not Do Yet

- It does not prove semantic parity between dashboards.
- It does not fully translate Dynatrace queries into Datadog queries.
- It does not apply Terraform or create Datadog dashboards automatically.
- It does not replace stakeholder review for dashboard value and usability.

## Repository Layout

- `dashboard_tooling/`: core models, normalization, comparison, recommendation, assessment, and Terraform planning logic
- `scripts/`: CLI entry points for each workflow stage
- `tests/`: unit, integration, and end-to-end coverage for the pipeline
- `.github/workflows/`: CI checks for compile, tests, secret scan, and static security

## Prerequisites

- Python 3.14 or newer
- No third-party runtime dependencies are required for the current codebase

## Authentication and Environment Variables

The repo still supports purely local JSON workflows, but it can now also fetch dashboards directly from Dynatrace and Datadog APIs.

Supported auth environment variables:
- Dynatrace:
  - `DYNATRACE_BASE_URL`
  - `DYNATRACE_API_TOKEN`
- Datadog:
  - `DATADOG_API_KEY`
  - `DATADOG_APP_KEY`
  - `DATADOG_SITE` or `DD_SITE`
  - optional `DATADOG_API_URL`

Supported config loading paths:
- direct environment variables
- an optional `.env` file passed with `--env-file`
- a default local `.env` file when present

Environment variables take precedence over values loaded from `.env`.

Example `.env`:

```dotenv
DYNATRACE_BASE_URL=https://example.live.dynatrace.com
DYNATRACE_API_TOKEN=dt0c01.example
DATADOG_API_KEY=example_api_key
DATADOG_APP_KEY=example_app_key
DATADOG_SITE=datadoghq.com
```

Write-back and apply paths:
- direct Datadog API create/update from generated dashboard plans
- Terraform workspace generation plus `terraform init`, `terraform plan`, or `terraform apply`

## Quick Start

Run the full test suite:

```bash
python3 -m unittest discover -s tests -v
```

Inspect the available CLIs:

```bash
for f in scripts/*.py; do
  echo "=== $f ==="
  python3 "$f" --help
done
```

Fetch dashboards directly from the APIs:

```bash
python3 scripts/fetch_dashboards.py --source dynatrace --out out/raw/dynatrace.json
python3 scripts/fetch_dashboards.py --source datadog --out out/raw/datadog.json
```

Run the full assessment directly from live APIs:

```bash
python3 scripts/run_dashboard_assessment.py \
  --fetch-dynatrace \
  --fetch-datadog \
  --out-dir out/live-assessment
```

Publish generated dashboard plans back to Datadog through the API:

```bash
python3 scripts/publish_datadog_dashboards.py \
  --plans-json out/live-assessment/terraform/terraform_plans.json \
  --out out/live-assessment/publish-results.json \
  --only-ready
```

Generate a Terraform workspace and run `terraform plan`:

```bash
python3 scripts/apply_terraform_dashboards.py \
  --plans-json out/live-assessment/terraform/terraform_plans.json \
  --work-dir out/live-assessment/terraform/workspace \
  --command plan
```

## Input Expectations

### Source and target exports

The normalizer accepts JSON exports for:
- `dynatrace`
- `datadog`

The code currently expects dashboard-like payloads with top-level lists such as:
- `dashboards`
- `items`
- `dashboardMetadata`

Dynatrace widgets are read from `tiles` or `widgets`.
Datadog widgets are read from `widgets`.

### Optional annotations

Annotations are an optional JSON overlay with this general structure:

```json
{
  "dashboards": [
    {
      "dashboard_id": "example-id",
      "title": "Example Dashboard",
      "blockers": ["known_gap"],
      "notes": ["Some widgets lose filter pushdown in DDSQL."]
    }
  ]
}
```

`dashboard_id` is preferred; `title` can be used as a fallback matcher.

## End-to-End Workflow

### 1. Normalize source and target exports

```bash
python3 scripts/normalize_dashboards.py \
  --source dynatrace \
  --input dynatrace.json \
  --out-dir out/source

python3 scripts/normalize_dashboards.py \
  --source datadog \
  --input datadog.json \
  --out-dir out/target
```

Optional annotations can be applied during normalization:

```bash
python3 scripts/normalize_dashboards.py \
  --source dynatrace \
  --input dynatrace.json \
  --annotations annotations.json \
  --out-dir out/source
```

If you want the tool to fetch from APIs first and then run the full workflow, use:

```bash
python3 scripts/run_dashboard_assessment.py \
  --fetch-dynatrace \
  --fetch-datadog \
  --annotations annotations.json \
  --out-dir out/live-assessment
```

You can also mix API and file inputs:

```bash
python3 scripts/run_dashboard_assessment.py \
  --fetch-dynatrace \
  --datadog-input datadog.json \
  --out-dir out/mixed-assessment
```

### 2. Compare inventories for parity

```bash
python3 scripts/compare_dashboards.py \
  --source-inventory out/source/inventory.json \
  --target-inventory out/target/inventory.json \
  --out-dir out/parity
```

### 3. Apply annotations after parity, if needed

```bash
python3 scripts/annotate_review_queue.py \
  --source-inventory out/source/inventory.json \
  --annotations annotations.json \
  --parity-json out/parity/parity.json \
  --out-dir out/annotated
```

Use `out/annotated/inventory.json` and `out/annotated/parity.json` in later stages when annotations are part of the workflow.

### 4. Generate manual review scaffolds

```bash
python3 scripts/generate_review_scaffolds.py \
  --source-inventory out/annotated/inventory.json \
  --parity-json out/annotated/parity.json \
  --out-dir out/review \
  --status-filter exact_title_match,missing_in_target,possible_candidate,high_confidence_candidate
```

### 5. Analyze dashboard creation candidates

```bash
python3 scripts/analyze_dashboard_candidates.py \
  --source-inventory out/annotated/inventory.json \
  --out-dir out/analysis
```

### 6. Build the migration menu

```bash
python3 scripts/build_dashboard_menu.py \
  --source-inventory out/annotated/inventory.json \
  --parity-json out/annotated/parity.json \
  --out-dir out/menu
```

### 7. Generate Terraform planning artifacts

```bash
python3 scripts/plan_terraform_dashboards.py \
  --source-inventory out/annotated/inventory.json \
  --menu-json out/menu/menu.json \
  --out-dir out/terraform
```

The Terraform planner defaults to these menu actions:
- `create_or_rebuild_with_terraform`
- `validate_and_improve_existing`
- `validate_existing_parity`

You can override the default action filter:

```bash
python3 scripts/plan_terraform_dashboards.py \
  --source-inventory out/annotated/inventory.json \
  --menu-json out/menu/menu.json \
  --out-dir out/terraform \
  --include-actions create_or_rebuild_with_terraform
```

## CLI Reference

### `normalize_dashboards.py`

Purpose:
Normalize raw dashboard exports into canonical inventory and query extracts.

Inputs:
- `--source {dynatrace,datadog}`
- `--input`
- `--out-dir`
- optional `--annotations`

Outputs:
- `inventory.json`
- `inventory.csv`
- `queries.csv`

### `compare_dashboards.py`

Purpose:
Compare normalized source and target inventories and produce a parity queue.

Inputs:
- `--source-inventory`
- `--target-inventory`
- `--out-dir`

Outputs:
- `parity.json`
- `parity.csv`
- `summary.md`

### `annotate_review_queue.py`

Purpose:
Apply annotation overlays to normalized inventory and optional parity results.

Inputs:
- `--source-inventory`
- `--annotations`
- `--out-dir`
- optional `--parity-json`

Outputs:
- `inventory.json`
- optional `parity.json`

### `generate_review_scaffolds.py`

Purpose:
Create review packets and draft Datadog scaffold JSON for human review.

Inputs:
- `--source-inventory`
- `--out-dir`
- optional `--parity-json`
- optional `--status-filter`

Outputs:
- `review_packets/*.md`
- `datadog_scaffolds/*.json`

### `analyze_dashboard_candidates.py`

Purpose:
Recommend which dashboards should be created, improved, deferred, or dropped.

Inputs:
- `--source-inventory`
- `--out-dir`

Outputs:
- `recommendations.json`
- `recommendations.csv`
- `recommendations.md`

### `build_dashboard_menu.py`

Purpose:
Combine inventory, parity, and recommendation signals into a customer/delivery decision menu.

Inputs:
- `--source-inventory`
- `--out-dir`
- optional `--parity-json`

Outputs:
- `menu.json`
- `menu.csv`
- `menu.md`

### `plan_terraform_dashboards.py`

Purpose:
Turn approved menu items into Terraform-ready planning artifacts and draft `datadog_dashboard_json` resources.

Inputs:
- `--source-inventory`
- `--out-dir`
- optional `--menu-json`
- optional `--include-actions`

Outputs:
- `terraform_plans.json`
- `plans/*.json`
- `tf_json/*.tf.json`

### `fetch_dashboards.py`

Purpose:
Fetch raw dashboards directly from Dynatrace or Datadog APIs.

Inputs:
- `--source {dynatrace,datadog}`
- `--out`
- optional `--env-file`

Outputs:
- raw JSON export compatible with `normalize_dashboards.py`

### `run_dashboard_assessment.py`

Purpose:
Run the dashboard assessment workflow from local JSON and/or live APIs.

Inputs:
- `--out-dir`
- optional `--dynatrace-input`
- optional `--datadog-input`
- optional `--fetch-dynatrace`
- optional `--fetch-datadog`
- optional `--annotations`
- optional `--env-file`
- optional `--terraform-actions`

Outputs:
- `raw/*.json`
- `source/inventory.json`
- optional `target/inventory.json`
- optional `parity/parity.json`
- `analysis/recommendations.json`
- `menu/menu.json`
- `review/review_packets/*.md`
- `review/datadog_scaffolds/*.json`
- `terraform/terraform_plans.json`
- `terraform/tf_json/*.tf.json`

### `publish_datadog_dashboards.py`

Purpose:
Create or update Datadog dashboards directly from generated Terraform dashboard plans.

Inputs:
- `--plans-json`
- `--out`
- optional `--env-file`
- optional `--only-ready`

Outputs:
- publish results JSON including created or updated dashboard IDs

### `apply_terraform_dashboards.py`

Purpose:
Write a Terraform workspace from generated plans and execute `terraform init`, `terraform plan`, or `terraform apply`.

Inputs:
- `--plans-json`
- `--work-dir`
- optional `--command {init,plan,apply}`
- optional `--auto-approve`

Outputs:
- generated Terraform workspace files
- `terraform-<command>-result.json` with captured stdout and stderr

## Output Summary

- `inventory.json` / `inventory.csv`
  Canonical dashboard inventory, variables, widget counts, and blockers.
- `queries.csv`
  Extracted query text and query-family classification by widget.
- `parity.json` / `parity.csv`
  Heuristic parity records between source and target dashboards.
- `recommendations.json` / `recommendations.csv` / `recommendations.md`
  Dashboard creation recommendations and required inputs.
- `menu.json` / `menu.csv` / `menu.md`
  Combined migration decision menu suitable for customer and delivery review.
- `terraform_plans.json`
  Summary of Terraform planning state for all selected dashboards.
- `plans/*.json`
  Detailed per-dashboard Terraform planning records.
- `tf_json/*.tf.json`
  Draft Terraform resources using `datadog_dashboard_json`.

## Suggested Review Sequence

1. Normalize and inspect the inventory.
2. Review parity as a hypothesis, not as proof.
3. Use recommendations and the menu to decide which dashboards are worth carrying forward.
4. Approve only the dashboards that add clear operational value.
5. Use Terraform plans to structure implementation and identify missing query mappings.
6. Translate source queries into real Datadog telemetry before applying Terraform.

## Publication Notes

This repo is close to public-ready from a content perspective, but two publication decisions still remain:
- decide whether to publish example fixtures or keep users responsible for supplying their own exports

## License Status

No license file has been added. Unless and until a license is added, this repository should be treated as published source code without an open-source license grant.
