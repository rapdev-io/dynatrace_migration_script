from __future__ import annotations

import json

from dashboard_tooling.models import DashboardRecord, ParityRecord
from dashboard_tooling.normalize import slugify


def build_review_packet(source: DashboardRecord, parity: ParityRecord | None = None) -> str:
    lines = [
        f"# {source.title}",
        "",
        "## Source Summary",
        f"- Source system: {source.source_system}",
        f"- Source dashboard ID: {source.dashboard_id}",
        f"- Widget count: {source.widget_count}",
        f"- Query count: {source.query_count}",
        f"- Complexity score: {source.complexity_score}",
        f"- Variables: {', '.join(source.variables) if source.variables else 'None'}",
        f"- Tags: {', '.join(source.tags) if source.tags else 'None'}",
        "",
        "## Heuristic Blockers",
    ]
    blockers = source.heuristic_blockers or ["none_inferred"]
    for blocker in blockers:
        lines.append(f"- {blocker}")
    lines.extend(
        [
            "",
        "## Manual Review Signals",
        ]
    )
    reasons = source.manual_review_reasons or ["none_recorded"]
    for reason in reasons:
        lines.append(f"- {reason}")
    if source.annotation_blockers or source.annotation_notes:
        lines.extend(["", "## Optional Annotations"])
        for blocker in source.annotation_blockers or ["none_recorded"]:
            lines.append(f"- blocker: {blocker}")
        for note in source.annotation_notes:
            lines.append(f"- note: {note}")
    if parity:
        lines.extend(
            [
                "",
                "## Target Matching",
                f"- Parity status: {parity.parity_status}",
                f"- Recommended action: {parity.recommended_action}",
                f"- Matched Datadog dashboard: {parity.matched_target_title or 'None'}",
                f"- Title similarity: {round(parity.title_similarity, 3)}",
            ]
        )
        if parity.heuristic_blockers:
            lines.append(f"- Parity blockers: {', '.join(parity.heuristic_blockers)}")
        if parity.annotation_blockers:
            lines.append(f"- Annotated blockers: {', '.join(parity.annotation_blockers)}")
    lines.extend(["", "## Queries To Review"])
    if not source.queries:
        lines.append("- No queries extracted. Capture source widget definitions manually.")
    else:
        for item in source.queries:
            lines.append(
                f"- Widget {item.widget_index} `{item.widget_title}` [{item.widget_type}] ({item.query_family}; signals: {', '.join(item.heuristic_signals) if item.heuristic_signals else 'none'}): `{item.query_text}`"
            )
    lines.extend(
        [
            "",
            "## Operator Decision",
            "- Replace with Datadog native view?",
            "- Rebuild as custom Datadog dashboard?",
            "- Drop as redundant or unused?",
        ]
    )
    return "\n".join(lines) + "\n"


def build_datadog_scaffold(source: DashboardRecord) -> dict[str, object]:
    note_lines = [
        f"Source dashboard: {source.title}",
        f"Source ID: {source.dashboard_id}",
        f"Widgets: {source.widget_count}",
        f"Queries: {source.query_count}",
        "Manual rebuild required.",
    ]
    if source.manual_review_reasons:
        note_lines.append("Review signals: " + ", ".join(source.manual_review_reasons))
    if source.heuristic_blockers:
        note_lines.append("Heuristic blockers: " + ", ".join(source.heuristic_blockers))
    if source.annotation_blockers:
        note_lines.append("Optional annotations: " + ", ".join(source.annotation_blockers))
    return {
        "title": source.title,
        "description": "Manual scaffold for Dynatrace to Datadog dashboard recreation.",
        "layout_type": "ordered",
        "template_variables": [{"name": item, "default": "*"} for item in source.variables],
        "widgets": [
            {
                "definition": {
                    "type": "note",
                    "content": "\n".join(note_lines),
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
        ],
        "source_queries": [
            {
                "widget_index": item.widget_index,
                "widget_title": item.widget_title,
                "widget_type": item.widget_type,
                "query_family": item.query_family,
                "query_text": item.query_text,
            }
            for item in source.queries
        ],
    }


def review_packet_filename(source: DashboardRecord) -> str:
    return f"{slugify(source.title)}.md"


def scaffold_filename(source: DashboardRecord) -> str:
    return f"{slugify(source.title)}.json"


def dump_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2) + "\n"
