from __future__ import annotations

from collections import Counter

from dashboard_tooling.models import DashboardRecord, QueryRecord

# Complexity score at or above this value triggers the high_complexity_dashboard blocker.
# Score is: widget_count + query_count*2 + variable_count + (table_widget_count * 2).
# A value of 12 corresponds roughly to a 4-widget, 3-query dashboard with one table widget.
COMPLEXITY_BLOCKER_THRESHOLD = 12


def infer_query_signals(query: QueryRecord) -> list[str]:
    text = query.query_text.lower()
    signals: list[str] = []
    if any(token in text for token in (" join ", " union ", " append ", " lookup ")):
        signals.append("multi_stage_query_logic")
    if any(token in text for token in ("case when", "if(", " iff(", " coalesce(", " summarize ", "make-series")):
        signals.append("custom_logic_dependency")
    if any(token in text for token in ("$var", "{var:", "template", "placeholder")):
        signals.append("dynamic_filter_dependency")
    if any(token in text for token in ("stopped before", "summary row", "total row", "grand total")):
        signals.append("result_shaping_logic")
    if any(token in text for token in ("timezone", "timestamp", "date_trunc", "bin(", "timeshift")):
        signals.append("time_semantics_risk")
    # ddsql is Datadog-native and does not need translation; sql_like is Dynatrace USQL
    if query.query_family in {"sql_like", "dynatrace_dql"}:
        signals.append("translation_review_required")
    if "select " in text and " from " in text:
        signals.append("tabular_logic_dependency")
    return sorted(set(signals))


def infer_dashboard_blockers(dashboard: DashboardRecord) -> list[str]:
    blockers: Counter[str] = Counter()
    for query in dashboard.queries:
        query.heuristic_signals = infer_query_signals(query)
        blockers.update(query.heuristic_signals)

    if dashboard.variables:
        blockers["dynamic_filter_dependency"] += 1
    if dashboard.query_count == 0:
        blockers["manual_query_capture_required"] += 1
    if dashboard.widget_count == 0:
        blockers["dashboard_export_incomplete"] += 1
    if dashboard.query_count > 1:
        blockers["multi_query_composition"] += 1
    if any(token in item.lower() for item in dashboard.widget_types for token in ("table", "list", "top")):
        blockers["table_or_list_result_shaping"] += 1
    if any(token in item.lower() for item in dashboard.widget_types for token in ("markdown", "note")):
        blockers["textual_context_dependency"] += 1
    if dashboard.complexity_score >= COMPLEXITY_BLOCKER_THRESHOLD:
        blockers["high_complexity_dashboard"] += 1
    return sorted(blockers)

