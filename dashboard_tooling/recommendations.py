from __future__ import annotations

from collections import Counter

from dashboard_tooling.models import DashboardRecommendation, DashboardRecord


VALUE_KEYWORDS: dict[str, str] = {
    "overview": "service_health",
    "executive": "executive",
    "summary": "executive",
    "kpi": "executive",
    "slo": "service_health",
    "latency": "service_health",
    "error": "service_health",
    "availability": "service_health",
    "traffic": "service_health",
    "throughput": "service_health",
    "capacity": "platform_operations",
    "infrastructure": "platform_operations",
    "host": "platform_operations",
    "pod": "platform_operations",
    "build": "delivery_operations",
    "deploy": "delivery_operations",
    "pipeline": "delivery_operations",
    "release": "delivery_operations",
    "security": "security",
    "audit": "security",
    "cost": "cost_governance",
}


def _dashboard_text(dashboard: DashboardRecord) -> str:
    query_text = " ".join(query.query_text.lower() for query in dashboard.queries)
    return " ".join(
        [
            dashboard.title.lower(),
            dashboard.description.lower(),
            " ".join(item.lower() for item in dashboard.tags),
            query_text,
        ]
    )


def _suggested_tier(dashboard: DashboardRecord) -> str:
    text = _dashboard_text(dashboard)
    bucket_counts: Counter[str] = Counter()
    for keyword, bucket in VALUE_KEYWORDS.items():
        if keyword in text:
            bucket_counts[bucket] += 1
    if not bucket_counts:
        return "team_operational"
    return bucket_counts.most_common(1)[0][0]


def _value_score(dashboard: DashboardRecord, tier: str) -> tuple[int, list[str], list[str]]:
    score = 0
    why_build: list[str] = []
    why_not_now: list[str] = []
    text = _dashboard_text(dashboard)

    if tier in {"executive", "service_health", "platform_operations"}:
        score += 3
        why_build.append(f"Title and query signals suggest a {tier.replace('_', ' ')} use case.")
    if dashboard.widget_count >= 3:
        score += 1
        why_build.append("Source dashboard combines multiple widgets, which suggests a consolidated workflow.")
    if dashboard.query_count >= 2:
        score += 1
        why_build.append("Source dashboard captures more than one question, so there is likely an active operator workflow.")
    if dashboard.variables:
        score += 1
        why_build.append("Dashboard uses filters, which suggests repeat use across environments or services.")
    if any(tag for tag in dashboard.tags):
        score += 1
        why_build.append("Source metadata includes tags that may support ownership and scoping.")
    if "markdown" in text or "note" in text:
        why_not_now.append("Source includes narrative context; confirm whether that context still adds value in Datadog.")
    if dashboard.query_count == 0:
        score -= 3
        why_not_now.append("No query payload was extracted, so there is no evidence the dashboard can be rebuilt as-is.")
    if dashboard.widget_count <= 1 and dashboard.query_count <= 1:
        why_not_now.append("Very small dashboard footprint; confirm it is not better represented as a monitor or notebook.")
    if "executive" in text or "kpi" in text or "overview" in text:
        score += 2
    if "error" in text or "latency" in text or "availability" in text or "slo" in text:
        score += 2

    return max(score, 0), sorted(set(why_build)), sorted(set(why_not_now))


def _automation_score(dashboard: DashboardRecord) -> tuple[int, bool, str, list[str], list[str], str]:
    blockers = set(dashboard.heuristic_blockers) | set(dashboard.annotation_blockers)
    score = 8
    required_inputs: list[str] = []
    open_questions: list[str] = []

    penalties = {
        "translation_review_required": 1,
        "custom_logic_dependency": 2,
        "multi_stage_query_logic": 2,
        "dynamic_filter_dependency": 1,
        "table_or_list_result_shaping": 1,
        "textual_context_dependency": 1,
        "manual_query_capture_required": 4,
        "high_complexity_dashboard": 2,
    }
    for blocker, penalty in penalties.items():
        if blocker in blockers:
            score -= penalty

    if dashboard.queries and all(query.query_family == "unknown" for query in dashboard.queries):
        score -= 4
        required_inputs.append("Mapped Datadog data sources for widgets that currently contain no recognizable query logic.")

    if dashboard.widget_types and all(
        any(token in widget_type.lower() for token in ("markdown", "note"))
        for widget_type in dashboard.widget_types
    ):
        score -= 4
        open_questions.append("Is this dashboard mostly narrative context that should move to documentation instead of Datadog?")

    if dashboard.variables:
        required_inputs.append("Canonical Datadog template variable definitions and allowed values.")
    if "dynamic_filter_dependency" in blockers:
        open_questions.append("Which tags should drive template variables in Datadog?")
    if "table_or_list_result_shaping" in blockers:
        open_questions.append("Does the table layout need exact parity, or is a simpler Datadog table acceptable?")
    if "textual_context_dependency" in blockers:
        open_questions.append("Should narrative notes be preserved, rewritten, or dropped from the Datadog dashboard?")
    if "translation_review_required" in blockers:
        required_inputs.append("Mapped Datadog metrics, logs, or traces for each Dynatrace query.")
    if "custom_logic_dependency" in blockers or "multi_stage_query_logic" in blockers:
        required_inputs.append("A reviewer-approved Datadog query design for custom aggregations or joins.")
    if dashboard.tags:
        required_inputs.append("Tag normalization plan so Terraform-generated widgets scope consistently.")
    else:
        open_questions.append("Which ownership and scope tags should be applied in Datadog?")

    score = max(score, 0)
    if score >= 6 and "manual_query_capture_required" not in blockers:
        terraform_strategy = "terraform_dashboard_json"
        terraform_ready = True
        confidence = "high"
    elif score >= 4:
        terraform_strategy = "terraform_after_query_mapping"
        terraform_ready = False
        confidence = "medium"
    else:
        terraform_strategy = "manual_design_first"
        terraform_ready = False
        confidence = "low"

    return (
        score,
        terraform_ready,
        terraform_strategy,
        sorted(set(required_inputs)),
        sorted(set(open_questions)),
        confidence,
    )


def _proposed_description(dashboard: DashboardRecord, tier: str) -> str:
    if tier == "executive":
        return (
            "High-level operational dashboard that summarizes service health and major KPI trends "
            "for leadership review, using Datadog-native widgets and consistent tag scoping."
        )
    if tier == "service_health":
        return (
            "Operational service dashboard focused on latency, errors, throughput, and availability "
            "to support triage and validate service behavior in Datadog."
        )
    if tier == "platform_operations":
        return (
            "Platform operations dashboard for infrastructure or runtime health, grouped by canonical "
            "environment and ownership tags to support ongoing operations."
        )
    if tier == "delivery_operations":
        return (
            "Engineering workflow dashboard oriented around build, deploy, or pipeline health, rebuilt "
            "only if those signals cannot be handled better by CI analytics or monitors."
        )
    return (
        "Team-oriented Datadog dashboard rebuilt only for the parts of the source workflow that still "
        "support active decisions, with low-value parity work intentionally removed."
    )


def recommend_dashboard(dashboard: DashboardRecord) -> DashboardRecommendation:
    tier = _suggested_tier(dashboard)
    value_score, why_build, why_not_now = _value_score(dashboard, tier)
    (
        automation_score,
        terraform_ready,
        terraform_strategy,
        required_inputs,
        open_questions,
        confidence,
    ) = _automation_score(dashboard)

    if value_score >= 5 and terraform_ready:
        status = "create_with_terraform"
    elif value_score >= 4:
        status = "candidate_pending_answers"
    elif dashboard.query_count == 0:
        status = "defer_missing_signal"
    else:
        status = "review_value_before_build"

    if value_score < 4:
        open_questions.append("What operator decision would be worse if this dashboard did not exist in Datadog?")
    if dashboard.query_count <= 1:
        open_questions.append("Should this be replaced by a monitor, SLO, or notebook instead of a dashboard?")

    return DashboardRecommendation(
        dashboard_id=dashboard.dashboard_id,
        title=dashboard.title,
        recommendation_status=status,
        suggested_dashboard_tier=tier,
        proposed_dashboard_description=_proposed_description(dashboard, tier),
        why_build=why_build,
        why_not_now=why_not_now,
        open_questions=sorted(set(open_questions)),
        required_inputs=required_inputs,
        terraform_strategy=terraform_strategy,
        terraform_ready=terraform_ready,
        automation_score=automation_score,
        value_score=value_score,
        confidence=confidence,
        source_widget_count=dashboard.widget_count,
        source_query_count=dashboard.query_count,
        source_variables=list(dashboard.variables),
        source_tags=list(dashboard.tags),
        heuristic_blockers=sorted(set(dashboard.heuristic_blockers + dashboard.annotation_blockers)),
    )


def recommend_dashboards(dashboards: list[DashboardRecord]) -> list[DashboardRecommendation]:
    return [recommend_dashboard(item) for item in dashboards]


def summarize_recommendations(recommendations: list[DashboardRecommendation]) -> dict[str, object]:
    status_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    terraform_ready = 0
    for item in recommendations:
        status_counts[item.recommendation_status] += 1
        tier_counts[item.suggested_dashboard_tier] += 1
        terraform_ready += int(item.terraform_ready)
    return {
        "dashboard_count": len(recommendations),
        "terraform_ready_count": terraform_ready,
        "status_counts": dict(status_counts.most_common()),
        "tier_counts": dict(tier_counts.most_common()),
    }


def build_recommendation_report(recommendations: list[DashboardRecommendation]) -> str:
    lines = [
        "# Dashboard Creation Recommendations",
        "",
        "This report recommends which Dynatrace dashboards are worth rebuilding in Datadog,",
        "which ones are Terraform-ready, and which questions must be answered before implementation.",
        "",
    ]
    summary = summarize_recommendations(recommendations)
    lines.append(f"- Dashboards analyzed: {summary['dashboard_count']}")
    lines.append(f"- Terraform-ready candidates: {summary['terraform_ready_count']}")
    for status, count in summary["status_counts"].items():
        lines.append(f"- {status}: {count}")
    lines.append("")
    for item in recommendations:
        lines.extend(
            [
                f"## {item.title}",
                f"- Recommendation: {item.recommendation_status}",
                f"- Suggested tier: {item.suggested_dashboard_tier}",
                f"- Value score: {item.value_score}/10",
                f"- Automation score: {item.automation_score}/10",
                f"- Terraform strategy: {item.terraform_strategy}",
                f"- Terraform ready: {'yes' if item.terraform_ready else 'no'}",
                f"- Description: {item.proposed_dashboard_description}",
            ]
        )
        if item.why_build:
            lines.append("- Why build:")
            for reason in item.why_build:
                lines.append(f"  - {reason}")
        if item.why_not_now:
            lines.append("- Risks or reasons to pause:")
            for reason in item.why_not_now:
                lines.append(f"  - {reason}")
        if item.required_inputs:
            lines.append("- Required inputs:")
            for req in item.required_inputs:
                lines.append(f"  - {req}")
        if item.open_questions:
            lines.append("- Open questions:")
            for question in item.open_questions:
                lines.append(f"  - {question}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
