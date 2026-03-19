from __future__ import annotations

import json
from collections import defaultdict

from dashboard_tooling.models import (
    DashboardMenuItem,
    DashboardRecord,
    QueryRecord,
    TerraformDashboardPlan,
    TerraformWidgetPlan,
)
from dashboard_tooling.normalize import slugify


def _group_queries(dashboard: DashboardRecord) -> list[QueryRecord]:
    return sorted(
        dashboard.queries,
        key=lambda item: (item.widget_index, item.widget_title, item.query_text),
    )


def _suggest_definition_type(query: QueryRecord) -> str:
    widget_type = query.widget_type.lower()
    if "table" in widget_type or query.query_family == "sql_like":
        return "query_table"
    if "markdown" in widget_type or "note" in widget_type:
        return "note"
    return "timeseries"


def _mapping_status(query: QueryRecord) -> tuple[str, list[str]]:
    notes: list[str] = []
    if query.query_family == "unknown":
        notes.append("Source query could not be classified; manual Datadog signal selection required.")
        return "manual_mapping_required", notes
    if query.query_family in {"dynatrace_dql", "sql_like"}:
        notes.append("Translate the source query to Datadog-native telemetry before applying Terraform.")
        return "query_translation_required", notes
    notes.append("Query family already resembles Datadog syntax; validate semantics before apply.")
    return "validate_and_apply", notes


def _placeholder_query(query: QueryRecord, definition_type: str) -> str:
    if definition_type == "query_table":
        return "avg:system.load.1{*} by {host}"
    if definition_type == "note":
        return ""
    return "avg:system.load.1{*}"


def _widget_plan(query: QueryRecord) -> TerraformWidgetPlan:
    definition_type = _suggest_definition_type(query)
    mapping_status, notes = _mapping_status(query)
    return TerraformWidgetPlan(
        widget_index=query.widget_index,
        source_widget_title=query.widget_title,
        source_widget_type=query.widget_type,
        suggested_datadog_definition_type=definition_type,
        mapping_status=mapping_status,
        source_query_family=query.query_family,
        source_query_text=query.query_text,
        placeholder_query=_placeholder_query(query, definition_type),
        notes=notes,
    )


def _template_variable_hints(dashboard: DashboardRecord) -> list[dict[str, str]]:
    return [
        {
            "name": variable,
            "suggested_tag_key": variable.lower(),
            "default": "*",
        }
        for variable in dashboard.variables
    ]


def _draft_note_widget(dashboard: DashboardRecord, menu_item: DashboardMenuItem) -> dict[str, object]:
    content = [
        f"Planned from Dynatrace dashboard: {dashboard.title}",
        f"Source dashboard ID: {dashboard.dashboard_id}",
        f"Menu action: {menu_item.menu_action}",
        f"Recommended tier: {menu_item.suggested_dashboard_tier}",
    ]
    if menu_item.matched_target_title:
        content.append(f"Matched Datadog dashboard: {menu_item.matched_target_title}")
    return {
        "definition": {
            "type": "note",
            "content": "\n".join(content),
            "background_color": "white",
            "font_size": "14",
            "show_tick": False,
            "tick_edge": "left",
            "tick_pos": "50%",
            "has_padding": True,
            "vertical_align": "center",
            "text_align": "left",
        }
    }


def _draft_widget(plan: TerraformWidgetPlan) -> dict[str, object]:
    if plan.suggested_datadog_definition_type == "note":
        return {
            "definition": {
                "type": "note",
                "content": (
                    f"TODO: Replace `{plan.source_widget_title}` with a Datadog-native widget.\n"
                    f"Source query family: {plan.source_query_family}\n"
                    f"Source query: {plan.source_query_text}"
                ),
                "background_color": "yellow",
                "font_size": "14",
                "show_tick": False,
                "tick_edge": "left",
                "tick_pos": "50%",
                "has_padding": True,
                "vertical_align": "center",
                "text_align": "left",
            }
        }
    request_key = "q" if plan.suggested_datadog_definition_type != "query_table" else "q"
    return {
        "definition": {
            "type": plan.suggested_datadog_definition_type,
            "title": plan.source_widget_title,
            "requests": [{request_key: plan.placeholder_query}],
        }
    }


def _draft_dashboard_json(dashboard: DashboardRecord, menu_item: DashboardMenuItem, widget_plans: list[TerraformWidgetPlan]) -> dict[str, object]:
    widgets = [_draft_note_widget(dashboard, menu_item)]
    widgets.extend(_draft_widget(plan) for plan in widget_plans)
    return {
        "title": dashboard.title,
        "description": menu_item.proposed_dashboard_description,
        "layout_type": "ordered",
        "template_variables": [
            {"name": variable["name"], "prefix": variable["suggested_tag_key"], "default": variable["default"]}
            for variable in _template_variable_hints(dashboard)
        ],
        "widgets": widgets,
    }


def build_terraform_plan(
    dashboard: DashboardRecord,
    menu_item: DashboardMenuItem,
) -> TerraformDashboardPlan:
    widget_plans = [_widget_plan(query) for query in _group_queries(dashboard)]
    terraform_mode = (
        "import_existing_dashboard"
        if menu_item.menu_action in {"validate_and_improve_existing", "validate_existing_parity"}
        else "create_new_dashboard"
    )
    import_instructions: list[str] = []
    if terraform_mode == "import_existing_dashboard" and menu_item.matched_target_id:
        import_instructions.append(
            f"Import existing Datadog dashboard `{menu_item.matched_target_title}` with ID `{menu_item.matched_target_id}` before apply."
        )
    elif terraform_mode == "import_existing_dashboard":
        import_instructions.append("Locate the existing Datadog dashboard ID before importing into Terraform state.")

    return TerraformDashboardPlan(
        dashboard_id=dashboard.dashboard_id,
        title=dashboard.title,
        resource_name=slugify(dashboard.title),
        menu_action=menu_item.menu_action,
        terraform_mode=terraform_mode,
        matched_target_id=menu_item.matched_target_id,
        matched_target_title=menu_item.matched_target_title,
        terraform_ready=menu_item.terraform_ready,
        required_inputs=list(menu_item.required_inputs),
        open_questions=list(menu_item.open_questions),
        template_variable_hints=_template_variable_hints(dashboard),
        widget_plans=widget_plans,
        draft_dashboard_json=_draft_dashboard_json(dashboard, menu_item, widget_plans),
        import_instructions=import_instructions,
    )


def build_terraform_plans(
    dashboards: list[DashboardRecord],
    menu_items: list[DashboardMenuItem],
    *,
    include_actions: set[str] | None = None,
) -> list[TerraformDashboardPlan]:
    dashboard_map = {item.dashboard_id: item for item in dashboards}
    default_actions = {"create_or_rebuild_with_terraform", "validate_and_improve_existing"}
    default_actions.add("validate_existing_parity")
    allowed_actions = include_actions or default_actions
    plans: list[TerraformDashboardPlan] = []
    for menu_item in menu_items:
        if menu_item.menu_action not in allowed_actions:
            continue
        dashboard = dashboard_map.get(menu_item.dashboard_id)
        if not dashboard:
            continue
        plans.append(build_terraform_plan(dashboard, menu_item))
    return plans


def summarize_terraform_plans(plans: list[TerraformDashboardPlan]) -> dict[str, object]:
    mode_counts = defaultdict(int)
    mapping_counts = defaultdict(int)
    for plan in plans:
        mode_counts[plan.terraform_mode] += 1
        for widget in plan.widget_plans:
            mapping_counts[widget.mapping_status] += 1
    return {
        "dashboard_count": len(plans),
        "terraform_ready_count": sum(int(item.terraform_ready) for item in plans),
        "terraform_mode_counts": dict(sorted(mode_counts.items())),
        "widget_mapping_counts": dict(sorted(mapping_counts.items())),
    }


def build_tf_json_resource(plan: TerraformDashboardPlan) -> dict[str, object]:
    return {
        "resource": {
            "datadog_dashboard_json": {
                plan.resource_name: {
                    "dashboard": json.dumps(plan.draft_dashboard_json, indent=2)
                }
            }
        }
    }
