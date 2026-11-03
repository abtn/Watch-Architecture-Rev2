"""Shared TeamPolicy budget and review-rule parsing."""

from typing import Any


class InvalidPolicyError(ValueError):
    """Raised when a TeamPolicy rule group is not validly configured."""


def daily_task_quota(rules: Any) -> int | None:
    """Return the Team's daily Task-start quota, or None when unlimited.

    The quota lives in rules["budgets"]["max_tasks_per_day"] and is an
    aggregate limit on successful Task starts for one Team during a UTC day.
    An absent quota preserves the existing no-limit behavior. A configured
    quota must be a non-negative integer; booleans, floats, strings, and
    negative values are invalid. This is a Task-start count, not a cost
    limit, and it is unrelated to StrategyProposal.constraints.max_tasks.
    """
    if not isinstance(rules, dict):
        raise InvalidPolicyError("invalid_team_policy_rules")
    budgets = rules.get("budgets", {})
    if not isinstance(budgets, dict):
        raise InvalidPolicyError("invalid_team_policy_budgets")
    if "max_tasks_per_day" not in budgets:
        return None
    limit = budgets["max_tasks_per_day"]
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise InvalidPolicyError("invalid_team_policy_daily_task_quota")
    return limit


def knowledge_item_review_interval_days(
    rules: Any, schema_version: Any
) -> int | None:
    """Read the optional D7 interval from the versioned TeamPolicy schema.

    Schema v1 remains unchanged. Schema v2 adds the optional
    review.knowledge_item_interval_days key, which has no default. The interval
    is pinned to the TeamPolicy version captured by the approval Task.
    """
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version not in {1, 2}
    ):
        raise InvalidPolicyError("unsupported_team_policy_schema_version")
    if not isinstance(rules, dict):
        raise InvalidPolicyError("invalid_team_policy_rules")
    review = rules.get("review", {})
    if not isinstance(review, dict):
        raise InvalidPolicyError("invalid_team_policy_review")
    key = "knowledge_item_interval_days"
    if key not in review:
        return None
    if schema_version < 2:
        raise InvalidPolicyError("review_interval_requires_team_policy_schema_v2")
    interval = review[key]
    if isinstance(interval, bool) or not isinstance(interval, int) or interval <= 0:
        raise InvalidPolicyError("invalid_knowledge_item_review_interval")
    return interval
