from __future__ import annotations

import re
from collections import Counter

from dashboard_tooling.heuristics import infer_dashboard_blockers
from dashboard_tooling.models import DashboardRecord, QueryRecord


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "dashboard"


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def query_family(query_text: str) -> str:
    lowered = query_text.lower()
    if "select " in lowered:
        return "sql_like"
    if "timeseries " in lowered or "fetch " in lowered:
        return "dynatrace_dql"
    if "avg:" in lowered or "sum:" in lowered or "anomalies(" in lowered:
        return "datadog_metric"
    if "logs(" in lowered or "service:" in lowered or "@http." in lowered:
        return "datadog_logs"
    return "unknown"


def _extract_list_payload(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("dashboards", "dashboardMetadata", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _string_list(values: object) -> list[str]:
    if isinstance(values, list):
        return [str(item).strip() for item in values if str(item).strip()]
    if isinstance(values, str) and values.strip():
        return [values.strip()]
    return []


def _append_query(
    dashboard: DashboardRecord,
    *,
    widget_index: int,
    widget_title: str,
    widget_type: str,
    query_text: str,
) -> None:
    cleaned = str(query_text).strip()
    if not cleaned:
        return
    dashboard.queries.append(
        QueryRecord(
            dashboard_id=dashboard.dashboard_id,
            dashboard_title=dashboard.title,
            widget_index=widget_index,
            widget_title=widget_title,
            widget_type=widget_type,
            query_text=cleaned,
            query_family=query_family(cleaned),
            heuristic_signals=[],
        )
    )


def _dynatrace_widgets(node: dict[str, object]) -> list[dict[str, object]]:
    widgets = node.get("tiles")
    if isinstance(widgets, list):
        return [item for item in widgets if isinstance(item, dict)]
    widgets = node.get("widgets")
    if isinstance(widgets, list):
        return [item for item in widgets if isinstance(item, dict)]
    return []


def _datadog_widgets(node: dict[str, object]) -> list[dict[str, object]]:
    widgets = node.get("widgets")
    if isinstance(widgets, list):
        return [item for item in widgets if isinstance(item, dict)]
    return []


def normalize_dynatrace_dashboards(payload: object) -> list[DashboardRecord]:
    dashboards: list[DashboardRecord] = []
    for node in _extract_list_payload(payload):
        title = str(node.get("name") or node.get("dashboardMetadata", {}).get("name") or "Untitled Dashboard")
        dashboard_id = str(
            node.get("id")
            or node.get("dashboardMetadata", {}).get("id")
            or slugify(title)
        )
        tags = _string_list(node.get("tags"))
        dashboard = DashboardRecord(
            source_system="dynatrace",
            dashboard_id=dashboard_id,
            title=title,
            description=str(node.get("description") or ""),
            owner=str(node.get("owner") or node.get("dashboardMetadata", {}).get("owner") or ""),
            tags=tags,
            variables=_string_list(node.get("dashboardFilter", {}).get("variables")),
            raw_references={
                "dashboard_id": dashboard_id,
            },
        )
        widgets = _dynatrace_widgets(node)
        dashboard.widget_count = len(widgets)
        type_counter: Counter[str] = Counter()
        for index, widget in enumerate(widgets, start=1):
            widget_type = str(widget.get("tileType") or widget.get("visualConfig", {}).get("type") or "unknown")
            widget_title = str(widget.get("name") or widget.get("title") or f"widget-{index}")
            type_counter[widget_type] += 1
            for path in (
                widget.get("queries"),
                widget.get("query"),
                widget.get("metricExpressions"),
                widget.get("metric"),
                widget.get("dql"),
            ):
                if isinstance(path, list):
                    for item in path:
                        _append_query(
                            dashboard,
                            widget_index=index,
                            widget_title=widget_title,
                            widget_type=widget_type,
                            query_text=str(item),
                        )
                elif path:
                    _append_query(
                        dashboard,
                        widget_index=index,
                        widget_title=widget_title,
                        widget_type=widget_type,
                        query_text=str(path),
                    )

            if isinstance(widget.get("markdown"), str):
                _append_query(
                    dashboard,
                    widget_index=index,
                    widget_title=widget_title,
                    widget_type=widget_type,
                    query_text=str(widget["markdown"]),
                )

        dashboard.widget_types = sorted(type_counter)
        dashboard.query_count = len(dashboard.queries)
        dashboard.complexity_score = (
            dashboard.widget_count
            + dashboard.query_count * 2
            + len(dashboard.variables)
            + len([name for name in dashboard.widget_types if "table" in name.lower() or "top" in name.lower()]) * 2
        )
        if dashboard.query_count == 0:
            dashboard.manual_review_reasons.append("no_extracted_queries")
        if dashboard.widget_count == 0:
            dashboard.manual_review_reasons.append("no_widgets")
        if any("markdown" in item.lower() or "note" in item.lower() for item in dashboard.widget_types):
            dashboard.manual_review_reasons.append("contains_textual_context")
        if dashboard.query_count > 5:
            dashboard.manual_review_reasons.append("query_heavy")
        dashboard.heuristic_blockers = infer_dashboard_blockers(dashboard)
        dashboards.append(dashboard)
    return dashboards


def normalize_datadog_dashboards(payload: object) -> list[DashboardRecord]:
    dashboards: list[DashboardRecord] = []
    for node in _extract_list_payload(payload):
        title = str(node.get("title") or node.get("name") or "Untitled Dashboard")
        dashboard_id = str(node.get("id") or node.get("url") or slugify(title))
        tags = _string_list(node.get("tags"))
        template_variables = node.get("template_variables") or node.get("templateVariables") or []
        variables = []
        if isinstance(template_variables, list):
            for item in template_variables:
                if isinstance(item, dict) and item.get("name"):
                    variables.append(str(item["name"]))
        dashboard = DashboardRecord(
            source_system="datadog",
            dashboard_id=dashboard_id,
            title=title,
            description=str(node.get("description") or ""),
            owner=str(node.get("author_handle") or node.get("author") or ""),
            tags=tags,
            variables=variables,
            raw_references={
                "url": str(node.get("url") or ""),
                "dashboard_id": dashboard_id,
            },
        )
        widgets = _datadog_widgets(node)
        dashboard.widget_count = len(widgets)
        type_counter: Counter[str] = Counter()
        for index, widget in enumerate(widgets, start=1):
            definition = widget.get("definition") if isinstance(widget.get("definition"), dict) else {}
            widget_type = str(definition.get("type") or "unknown")
            widget_title = str(definition.get("title") or widget.get("title") or f"widget-{index}")
            type_counter[widget_type] += 1
            requests = definition.get("requests")
            if isinstance(requests, list):
                for request in requests:
                    if not isinstance(request, dict):
                        continue
                    if request.get("q"):
                        _append_query(
                            dashboard,
                            widget_index=index,
                            widget_title=widget_title,
                            widget_type=widget_type,
                            query_text=str(request["q"]),
                        )
                    formulas = request.get("formulas")
                    if isinstance(formulas, list):
                        for formula in formulas:
                            if isinstance(formula, dict) and formula.get("formula"):
                                _append_query(
                                    dashboard,
                                    widget_index=index,
                                    widget_title=widget_title,
                                    widget_type=widget_type,
                                    query_text=str(formula["formula"]),
                                )
            if definition.get("query"):
                _append_query(
                    dashboard,
                    widget_index=index,
                    widget_title=widget_title,
                    widget_type=widget_type,
                    query_text=str(definition["query"]),
                )

        dashboard.widget_types = sorted(type_counter)
        dashboard.query_count = len(dashboard.queries)
        dashboard.complexity_score = (
            dashboard.widget_count
            + dashboard.query_count * 2
            + len(dashboard.variables)
        )
        dashboard.heuristic_blockers = infer_dashboard_blockers(dashboard)
        dashboards.append(dashboard)
    return dashboards


def summarize_dashboards(dashboards: list[DashboardRecord]) -> dict[str, object]:
    widget_type_counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    for dashboard in dashboards:
        widget_type_counts.update(dashboard.widget_types)
        reasons.update(dashboard.manual_review_reasons)
        blockers.update(dashboard.heuristic_blockers)
    return {
        "dashboard_count": len(dashboards),
        "total_widgets": sum(item.widget_count for item in dashboards),
        "total_queries": sum(item.query_count for item in dashboards),
        "widget_type_counts": dict(widget_type_counts.most_common()),
        "manual_review_reason_counts": dict(reasons.most_common()),
        "heuristic_blocker_counts": dict(blockers.most_common()),
    }
