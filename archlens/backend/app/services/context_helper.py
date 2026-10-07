"""Helpers to inject UserContext into LLM prompts."""
from typing import Optional
from app.models.schemas import UserContext


SCALE_HINTS = {
    "dev": "Development/test environment, single region, minimal HA",
    "small": "<1K active users, single region, basic HA",
    "medium": "1K-100K active users, multi-AZ, autoscaling",
    "large": ">100K active users, multi-region, full HA/DR",
}


def format_user_context(ctx: Optional[UserContext]) -> str:
    """Return a markdown block to append to prompts. Empty string if no context."""
    if not ctx:
        return ""
    lines = ["", "USER-PROVIDED CONTEXT (incorporate into your analysis):"]
    if ctx.workload_description:
        lines.append(f"- Workload: {ctx.workload_description}")
    if ctx.expected_scale:
        hint = SCALE_HINTS.get(ctx.expected_scale, ctx.expected_scale)
        lines.append(f"- Scale: {ctx.expected_scale} ({hint})")
    if ctx.compliance:
        lines.append(f"- Compliance requirements: {', '.join(ctx.compliance)}")
    if ctx.region_preferences:
        lines.append(f"- Preferred regions: {', '.join(ctx.region_preferences)}")
    if ctx.budget_monthly_usd:
        lines.append(f"- Monthly budget ceiling: ${ctx.budget_monthly_usd:,.2f} USD")
    if ctx.priority:
        lines.append(f"- Optimization priority: {ctx.priority}")
    if ctx.constraints:
        lines.append(f"- Constraints: {ctx.constraints}")
    if len(lines) == 2:
        return ""
    return "\n".join(lines) + "\n"
