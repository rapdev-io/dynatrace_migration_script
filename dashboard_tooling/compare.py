from __future__ import annotations

from difflib import SequenceMatcher

from dashboard_tooling.heuristics import COMPLEXITY_BLOCKER_THRESHOLD
from dashboard_tooling.models import DashboardRecord, ParityRecord
from dashboard_tooling.normalize import normalize_title

# SequenceMatcher ratio thresholds for dashboard title matching.
# STRONG (0.92): titles that differ only by minor word reordering or punctuation
#   e.g. "Service Latency Overview" vs "Service Latency - Overview"
# WEAK (0.72): titles that share most tokens but have one meaningful difference
#   e.g. "Host CPU Usage" vs "Host Memory Usage" — useful for flagging candidates,
#   not for automatic matching.
# Values below WEAK are treated as no match (missing_in_target).
DEFAULT_STRONG_MATCH_THRESHOLD: float = 0.92
DEFAULT_WEAK_MATCH_THRESHOLD: float = 0.72


def _title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_title(left), normalize_title(right)).ratio()


def compare_dashboards(
    source_dashboards: list[DashboardRecord],
    target_dashboards: list[DashboardRecord],
    *,
    strong_match_threshold: float = DEFAULT_STRONG_MATCH_THRESHOLD,
    weak_match_threshold: float = DEFAULT_WEAK_MATCH_THRESHOLD,
) -> list[ParityRecord]:
    parity_records: list[ParityRecord] = []
    for source in source_dashboards:
        best_target = None
        best_score = 0.0
        for target in target_dashboards:
            score = _title_similarity(source.title, target.title)
            if score > best_score:
                best_score = score
                best_target = target

        record = ParityRecord(
            source_dashboard_id=source.dashboard_id,
            source_title=source.title,
            source_complexity_score=source.complexity_score,
            manual_review_reasons=list(source.manual_review_reasons),
            heuristic_blockers=list(source.heuristic_blockers),
        )
        if best_target is None:
            record.parity_status = "missing_in_target"
            record.recommended_action = "review_for_rebuild_or_drop"
        else:
            record.matched_target_id = best_target.dashboard_id
            record.matched_target_title = best_target.title
            record.title_similarity = best_score
            if normalize_title(source.title) == normalize_title(best_target.title):
                record.parity_status = "exact_title_match"
                record.recommended_action = "validate_widget_and_query_parity"
            elif best_score >= strong_match_threshold:
                record.parity_status = "high_confidence_candidate"
                record.recommended_action = "human_confirm_same_dashboard"
            elif best_score >= weak_match_threshold:
                record.parity_status = "possible_candidate"
                record.recommended_action = "review_mapping_before_rebuild"
            else:
                record.parity_status = "missing_in_target"
                record.recommended_action = "review_for_rebuild_or_drop"

        if source.query_count == 0:
            record.manual_review_reasons.append("source_needs_manual_query_capture")
        if source.complexity_score >= COMPLEXITY_BLOCKER_THRESHOLD:
            record.manual_review_reasons.append("high_complexity")
        if source.variables and not best_target:
            record.heuristic_blockers.append("dynamic_filter_mapping_required")
        record.heuristic_blockers = sorted(set(record.heuristic_blockers))
        record.manual_review_reasons = sorted(set(record.manual_review_reasons))
        parity_records.append(record)
    return parity_records
