"""Shared TeamPolicy budget-rule parsing for the Plan and Task boundaries."""

from typing import Any


class InvalidPolicyError(ValueError):
    """Raised when a TeamPolicy rule group is not validly configured."""


def daily_task_quota(rules: Any) -> int | None:
    """Return the Team's daily Task-start quota, or None when unlimited.

    The quota lives in ``rules["budgets"]["max_tasks_per_day"]`` and is an
    aggregate limit on successful Task starts for one Team during a UTC day.
    An absent quota preserves the existing no-limit behavior. A configured
    quota must be a non-negative integer; booleans, floats, strings, and
    negative values are invalid. This is a Task-start count, not a cost
    limit, and it is unrelated to ``StrategyProposal.constraints.max_tasks``.
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
