from __future__ import annotations

from pathlib import Path

from dashboard_tooling.io import load_json
from dashboard_tooling.models import DashboardRecord, ParityRecord
from dashboard_tooling.normalize import normalize_title


def load_annotation_payload(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def _dashboard_matches(dashboard: DashboardRecord, item: dict[str, object]) -> bool:
    dashboard_id = str(item.get("dashboard_id") or "")
    title = str(item.get("title") or "")
    if dashboard_id and dashboard_id == dashboard.dashboard_id:
        return True
    if title and normalize_title(title) == normalize_title(dashboard.title):
        return True
    return False


def apply_dashboard_annotations(dashboards: list[DashboardRecord], payload: dict[str, object]) -> None:
    entries = payload.get("dashboards", [])
    if not isinstance(entries, list):
        return
    for dashboard in dashboards:
        for item in entries:
            if not isinstance(item, dict) or not _dashboard_matches(dashboard, item):
                continue
            dashboard.annotation_notes.extend(
                [str(note) for note in item.get("notes", []) if str(note).strip()]
            )
            dashboard.annotation_blockers.extend(
                [str(note) for note in item.get("blockers", []) if str(note).strip()]
            )
        dashboard.annotation_notes = sorted(set(dashboard.annotation_notes))
        dashboard.annotation_blockers = sorted(set(dashboard.annotation_blockers))


def apply_parity_annotations(
    parity_records: list[ParityRecord],
    source_dashboards: list[DashboardRecord],
) -> None:
    dashboard_map = {item.dashboard_id: item for item in source_dashboards}
    for record in parity_records:
        dashboard = dashboard_map.get(record.source_dashboard_id)
        if not dashboard:
            continue
        record.annotation_notes = list(dashboard.annotation_notes)
        record.annotation_blockers = list(dashboard.annotation_blockers)

