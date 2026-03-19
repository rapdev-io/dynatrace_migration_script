from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QueryRecord:
    dashboard_id: str
    dashboard_title: str
    widget_index: int
    widget_title: str
    widget_type: str
    query_text: str
    query_family: str
    heuristic_signals: list[str] = field(default_factory=list)


@dataclass
class DashboardRecord:
    source_system: str
    dashboard_id: str
    title: str
    description: str = ""
    owner: str = ""
    tags: list[str] = field(default_factory=list)
    widget_count: int = 0
    widget_types: list[str] = field(default_factory=list)
    query_count: int = 0
    queries: list[QueryRecord] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    raw_references: dict[str, str] = field(default_factory=dict)
    complexity_score: int = 0
    manual_review_reasons: list[str] = field(default_factory=list)
    heuristic_blockers: list[str] = field(default_factory=list)
    annotation_notes: list[str] = field(default_factory=list)
    annotation_blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_system": self.source_system,
            "dashboard_id": self.dashboard_id,
            "title": self.title,
            "description": self.description,
            "owner": self.owner,
            "tags": self.tags,
            "widget_count": self.widget_count,
            "widget_types": self.widget_types,
            "query_count": self.query_count,
            "variables": self.variables,
            "complexity_score": self.complexity_score,
            "manual_review_reasons": self.manual_review_reasons,
            "heuristic_blockers": self.heuristic_blockers,
            "annotation_notes": self.annotation_notes,
            "annotation_blockers": self.annotation_blockers,
            "raw_references": self.raw_references,
            "queries": [
                {
                    "dashboard_id": item.dashboard_id,
                    "dashboard_title": item.dashboard_title,
                    "widget_index": item.widget_index,
                    "widget_title": item.widget_title,
                    "widget_type": item.widget_type,
                    "query_text": item.query_text,
                    "query_family": item.query_family,
                    "heuristic_signals": item.heuristic_signals,
                }
                for item in self.queries
            ],
        }


@dataclass
class ParityRecord:
    source_dashboard_id: str
    source_title: str
    source_complexity_score: int
    matched_target_id: str = ""
    matched_target_title: str = ""
    title_similarity: float = 0.0
    parity_status: str = "unmatched"
    recommended_action: str = ""
    manual_review_reasons: list[str] = field(default_factory=list)
    heuristic_blockers: list[str] = field(default_factory=list)
    annotation_notes: list[str] = field(default_factory=list)
    annotation_blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_dashboard_id": self.source_dashboard_id,
            "source_title": self.source_title,
            "source_complexity_score": self.source_complexity_score,
            "matched_target_id": self.matched_target_id,
            "matched_target_title": self.matched_target_title,
            "title_similarity": round(self.title_similarity, 3),
            "parity_status": self.parity_status,
            "recommended_action": self.recommended_action,
            "manual_review_reasons": self.manual_review_reasons,
            "heuristic_blockers": self.heuristic_blockers,
            "annotation_notes": self.annotation_notes,
            "annotation_blockers": self.annotation_blockers,
        }


@dataclass
class DashboardRecommendation:
    dashboard_id: str
    title: str
    recommendation_status: str
    suggested_dashboard_tier: str
    proposed_dashboard_description: str
    why_build: list[str] = field(default_factory=list)
    why_not_now: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    required_inputs: list[str] = field(default_factory=list)
    terraform_strategy: str = ""
    terraform_ready: bool = False
    automation_score: int = 0
    value_score: int = 0
    confidence: str = "medium"
    source_widget_count: int = 0
    source_query_count: int = 0
    source_variables: list[str] = field(default_factory=list)
    source_tags: list[str] = field(default_factory=list)
    heuristic_blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "dashboard_id": self.dashboard_id,
            "title": self.title,
            "recommendation_status": self.recommendation_status,
            "suggested_dashboard_tier": self.suggested_dashboard_tier,
            "proposed_dashboard_description": self.proposed_dashboard_description,
            "why_build": self.why_build,
            "why_not_now": self.why_not_now,
            "open_questions": self.open_questions,
            "required_inputs": self.required_inputs,
            "terraform_strategy": self.terraform_strategy,
            "terraform_ready": self.terraform_ready,
            "automation_score": self.automation_score,
            "value_score": self.value_score,
            "confidence": self.confidence,
            "source_widget_count": self.source_widget_count,
            "source_query_count": self.source_query_count,
            "source_variables": self.source_variables,
            "source_tags": self.source_tags,
            "heuristic_blockers": self.heuristic_blockers,
        }


@dataclass
class DashboardMenuItem:
    dashboard_id: str
    title: str
    menu_action: str
    customer_option_label: str
    parity_status: str = "not_evaluated"
    matched_target_id: str = ""
    matched_target_title: str = ""
    parity_rationale: list[str] = field(default_factory=list)
    recommendation_status: str = ""
    terraform_ready: bool = False
    terraform_strategy: str = ""
    suggested_dashboard_tier: str = ""
    proposed_dashboard_description: str = ""
    why_this_option: list[str] = field(default_factory=list)
    improvement_opportunities: list[str] = field(default_factory=list)
    validation_or_test_plan: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    required_inputs: list[str] = field(default_factory=list)
    heuristic_blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "dashboard_id": self.dashboard_id,
            "title": self.title,
            "menu_action": self.menu_action,
            "customer_option_label": self.customer_option_label,
            "parity_status": self.parity_status,
            "matched_target_id": self.matched_target_id,
            "matched_target_title": self.matched_target_title,
            "parity_rationale": self.parity_rationale,
            "recommendation_status": self.recommendation_status,
            "terraform_ready": self.terraform_ready,
            "terraform_strategy": self.terraform_strategy,
            "suggested_dashboard_tier": self.suggested_dashboard_tier,
            "proposed_dashboard_description": self.proposed_dashboard_description,
            "why_this_option": self.why_this_option,
            "improvement_opportunities": self.improvement_opportunities,
            "validation_or_test_plan": self.validation_or_test_plan,
            "open_questions": self.open_questions,
            "required_inputs": self.required_inputs,
            "heuristic_blockers": self.heuristic_blockers,
        }


@dataclass
class TerraformWidgetPlan:
    widget_index: int
    source_widget_title: str
    source_widget_type: str
    suggested_datadog_definition_type: str
    mapping_status: str
    source_query_family: str
    source_query_text: str
    placeholder_query: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "widget_index": self.widget_index,
            "source_widget_title": self.source_widget_title,
            "source_widget_type": self.source_widget_type,
            "suggested_datadog_definition_type": self.suggested_datadog_definition_type,
            "mapping_status": self.mapping_status,
            "source_query_family": self.source_query_family,
            "source_query_text": self.source_query_text,
            "placeholder_query": self.placeholder_query,
            "notes": self.notes,
        }


@dataclass
class TerraformDashboardPlan:
    dashboard_id: str
    title: str
    resource_name: str
    menu_action: str
    terraform_mode: str
    matched_target_id: str = ""
    matched_target_title: str = ""
    terraform_ready: bool = False
    required_inputs: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    template_variable_hints: list[dict[str, str]] = field(default_factory=list)
    widget_plans: list[TerraformWidgetPlan] = field(default_factory=list)
    draft_dashboard_json: dict[str, object] = field(default_factory=dict)
    import_instructions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "dashboard_id": self.dashboard_id,
            "title": self.title,
            "resource_name": self.resource_name,
            "menu_action": self.menu_action,
            "terraform_mode": self.terraform_mode,
            "matched_target_id": self.matched_target_id,
            "matched_target_title": self.matched_target_title,
            "terraform_ready": self.terraform_ready,
            "required_inputs": self.required_inputs,
            "open_questions": self.open_questions,
            "template_variable_hints": self.template_variable_hints,
            "widget_plans": [item.to_dict() for item in self.widget_plans],
            "draft_dashboard_json": self.draft_dashboard_json,
            "import_instructions": self.import_instructions,
        }
