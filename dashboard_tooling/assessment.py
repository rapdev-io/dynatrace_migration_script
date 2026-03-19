from __future__ import annotations

from collections import Counter

from dashboard_tooling.models import (
    DashboardMenuItem,
    DashboardRecommendation,
    DashboardRecord,
    ParityRecord,
)
from dashboard_tooling.recommendations import recommend_dashboards


def _parity_rationale(record: ParityRecord | None) -> list[str]:
    if record is None:
        return ["No target inventory was provided, so parity could not be evaluated."]
    if record.parity_status == "exact_title_match":
        return [
            f"Matched target dashboard `{record.matched_target_title}` on normalized title equality.",
            "Widget and query parity still require validation; title parity alone is not sufficient.",
        ]
    if record.parity_status == "high_confidence_candidate":
        return [
            f"Closest target dashboard is `{record.matched_target_title}` with strong title similarity.",
            "Human review is required before treating this as parity.",
        ]
    if record.parity_status == "possible_candidate":
        return [
            f"Closest target dashboard is `{record.matched_target_title}` but the match is weak.",
            "Treat this as a candidate for redesign or selective reuse, not parity.",
        ]
    return [
        "No credible target dashboard match was found.",
        "This capability is missing in the target environment unless rebuilt.",
    ]


def _validation_plan(
    dashboard: DashboardRecord,
    recommendation: DashboardRecommendation,
    parity: ParityRecord | None,
) -> list[str]:
    plan = [
        "Confirm the operator or stakeholder who actively uses this dashboard.",
        "Validate that each source widget maps to an agreed Datadog signal, not just a similar title.",
    ]
    if recommendation.terraform_ready:
        plan.append("Generate the dashboard via Terraform in non-prod and review widget usefulness with the owning team.")
    else:
        plan.append("Resolve open questions and signal mappings before committing to Terraform generation.")
    if parity and parity.parity_status in {"exact_title_match", "high_confidence_candidate", "possible_candidate"}:
        plan.append("Review the existing Datadog dashboard to decide whether to keep, improve, or replace it.")
    if dashboard.variables:
        plan.append("Test template variables against real tag values in Datadog to avoid empty widgets.")
    return sorted(set(plan))


def _improvement_opportunities(
    dashboard: DashboardRecord,
    recommendation: DashboardRecommendation,
    parity: ParityRecord | None,
) -> list[str]:
    improvements: list[str] = []
    if recommendation.suggested_dashboard_tier == "service_health":
        improvements.append("Use a Datadog-native service health layout instead of preserving source widget order.")
    if "table_or_list_result_shaping" in recommendation.heuristic_blockers:
        improvements.append("Replace brittle table parity with purpose-built Datadog tables or toplists where possible.")
    if "textual_context_dependency" in recommendation.heuristic_blockers:
        improvements.append("Move durable narrative context into docs or dashboard notes rather than rebuilding every text widget.")
    if dashboard.variables:
        improvements.append("Standardize template variables across dashboards so Terraform modules stay reusable.")
    if parity and parity.parity_status == "exact_title_match":
        improvements.append("Compare the existing Datadog dashboard against the source and remove low-value parity work.")
    return sorted(set(improvements))


def _menu_action(
    recommendation: DashboardRecommendation,
    parity: ParityRecord | None,
) -> tuple[str, str, list[str]]:
    reasons: list[str] = []
    if parity and parity.parity_status == "exact_title_match":
        if recommendation.recommendation_status == "create_with_terraform":
            reasons.append("A similarly named dashboard already exists in Datadog, but it may still need structured improvement.")
            return "validate_and_improve_existing", "Validate existing dashboard, then improve selectively", reasons
        reasons.append("A similarly named dashboard already exists; focus on validation before rebuilding.")
        return "validate_existing_parity", "Validate existing dashboard before making changes", reasons
    if recommendation.recommendation_status == "create_with_terraform":
        reasons.append("This dashboard appears valuable and structured enough to generate through Terraform.")
        return "create_or_rebuild_with_terraform", "Create in Datadog with Terraform", reasons
    if recommendation.recommendation_status == "candidate_pending_answers":
        reasons.append("This dashboard may be worth carrying forward, but key design questions remain unresolved.")
        return "design_before_build", "Refine design before building", reasons
    if recommendation.recommendation_status == "defer_missing_signal":
        reasons.append("There is not enough signal to justify rebuilding this dashboard yet.")
        return "defer_or_drop", "Defer or drop unless stronger need emerges", reasons
    reasons.append("Value is uncertain; confirm the actual operator workflow before rebuilding.")
    return "review_for_value", "Review value before rebuilding", reasons


def build_dashboard_menu(
    dashboards: list[DashboardRecord],
    parity_records: list[ParityRecord] | None = None,
) -> list[DashboardMenuItem]:
    parity_map = {item.source_dashboard_id: item for item in (parity_records or [])}
    recommendations = {item.dashboard_id: item for item in recommend_dashboards(dashboards)}

    menu: list[DashboardMenuItem] = []
    for dashboard in dashboards:
        recommendation = recommendations[dashboard.dashboard_id]
        parity = parity_map.get(dashboard.dashboard_id)
        menu_action, label, action_reasons = _menu_action(recommendation, parity)
        menu.append(
            DashboardMenuItem(
                dashboard_id=dashboard.dashboard_id,
                title=dashboard.title,
                menu_action=menu_action,
                customer_option_label=label,
                parity_status=parity.parity_status if parity else "not_evaluated",
                matched_target_id=parity.matched_target_id if parity else "",
                matched_target_title=parity.matched_target_title if parity else "",
                parity_rationale=_parity_rationale(parity),
                recommendation_status=recommendation.recommendation_status,
                terraform_ready=recommendation.terraform_ready,
                terraform_strategy=recommendation.terraform_strategy,
                suggested_dashboard_tier=recommendation.suggested_dashboard_tier,
                proposed_dashboard_description=recommendation.proposed_dashboard_description,
                why_this_option=sorted(set(action_reasons + recommendation.why_build + recommendation.why_not_now)),
                improvement_opportunities=_improvement_opportunities(dashboard, recommendation, parity),
                validation_or_test_plan=_validation_plan(dashboard, recommendation, parity),
                open_questions=list(recommendation.open_questions),
                required_inputs=list(recommendation.required_inputs),
                heuristic_blockers=sorted(set(recommendation.heuristic_blockers + (parity.heuristic_blockers if parity else []))),
            )
        )
    return menu


def summarize_menu(menu: list[DashboardMenuItem]) -> dict[str, object]:
    action_counts: Counter[str] = Counter()
    parity_counts: Counter[str] = Counter()
    terraform_ready_count = 0
    for item in menu:
        action_counts[item.menu_action] += 1
        parity_counts[item.parity_status] += 1
        terraform_ready_count += int(item.terraform_ready)
    return {
        "dashboard_count": len(menu),
        "terraform_ready_count": terraform_ready_count,
        "menu_action_counts": dict(action_counts.most_common()),
        "parity_status_counts": dict(parity_counts.most_common()),
    }


def build_menu_report(menu: list[DashboardMenuItem]) -> str:
    summary = summarize_menu(menu)
    lines = [
        "# Dashboard Migration Menu",
        "",
        "This report combines source inventory, target parity, and dashboard creation recommendations.",
        "Use it to decide what to keep, what to improve, what to rebuild, and what to defer.",
        "",
        f"- Dashboards analyzed: {summary['dashboard_count']}",
        f"- Terraform-ready candidates: {summary['terraform_ready_count']}",
    ]
    for key, count in summary["menu_action_counts"].items():
        lines.append(f"- {key}: {count}")
    lines.append("")
    for item in menu:
        lines.extend(
            [
                f"## {item.title}",
                f"- Customer option: {item.customer_option_label}",
                f"- Menu action: {item.menu_action}",
                f"- Parity status: {item.parity_status}",
                f"- Existing Datadog match: {item.matched_target_title or 'None'}",
                f"- Recommendation status: {item.recommendation_status}",
                f"- Terraform ready: {'yes' if item.terraform_ready else 'no'}",
                f"- Terraform strategy: {item.terraform_strategy}",
                f"- Suggested dashboard tier: {item.suggested_dashboard_tier}",
                f"- Proposed dashboard: {item.proposed_dashboard_description}",
            ]
        )
        if item.parity_rationale:
            lines.append("- Parity rationale:")
            for reason in item.parity_rationale:
                lines.append(f"  - {reason}")
        if item.why_this_option:
            lines.append("- Why this option:")
            for reason in item.why_this_option:
                lines.append(f"  - {reason}")
        if item.improvement_opportunities:
            lines.append("- Improvements or changes to consider:")
            for reason in item.improvement_opportunities:
                lines.append(f"  - {reason}")
        if item.required_inputs:
            lines.append("- Required inputs:")
            for reason in item.required_inputs:
                lines.append(f"  - {reason}")
        if item.open_questions:
            lines.append("- Open questions:")
            for reason in item.open_questions:
                lines.append(f"  - {reason}")
        if item.validation_or_test_plan:
            lines.append("- Validation and test plan:")
            for reason in item.validation_or_test_plan:
                lines.append(f"  - {reason}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
