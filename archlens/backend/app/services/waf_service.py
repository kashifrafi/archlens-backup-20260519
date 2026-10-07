import json
from typing import List
from openai import AzureOpenAI, OpenAI

from app.config import settings
from app.models.schemas import (
    DiagramAnalysisResponse,
    CloudProvider,
    WAFReviewResponse,
    WAFPillarScore,
    UserContext,
)
from app.services.context_helper import format_user_context
from app.services import rag_service


def _get_client():
    if settings.azure_openai_endpoint and settings.azure_openai_api_key:
        return AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        ), settings.azure_openai_deployment
    elif settings.openai_api_key:
        return OpenAI(api_key=settings.openai_api_key), settings.openai_model
    else:
        raise ValueError("No AI API credentials configured.")


WAF_PILLARS = {
    CloudProvider.AWS: [
        "Operational Excellence",
        "Security",
        "Reliability",
        "Performance Efficiency",
        "Cost Optimization",
        "Sustainability",
    ],
    CloudProvider.AZURE: [
        "Reliability",
        "Security",
        "Cost Optimization",
        "Operational Excellence",
        "Performance Efficiency",
    ],
    CloudProvider.GCP: [
        "System Design",
        "Operational Excellence",
        "Security, Privacy and Compliance",
        "Reliability",
        "Cost Optimization",
        "Performance Optimization",
    ],
}

WAF_DESCRIPTIONS = {
    CloudProvider.AWS: "AWS Well-Architected Framework",
    CloudProvider.AZURE: "Microsoft Azure Well-Architected Framework",
    CloudProvider.GCP: "Google Cloud Architecture Framework",
}


def _build_waf_prompt(
    cloud: CloudProvider,
    analysis: DiagramAnalysisResponse,
    user_context: 'UserContext | None' = None,
    rag_context: str = "",
) -> str:
    pillars = WAF_PILLARS[cloud]
    framework_name = WAF_DESCRIPTIONS[cloud]
    components_summary = ", ".join(
        [f"{c.name} ({c.type})" for c in analysis.components]
    )
    services = analysis.detected_services.get(cloud.value, [])
    ctx_block = format_user_context(user_context)

    rag_section = (
        f"\n\nRELEVANT {cloud.value.upper()} WAF DOCUMENTATION (retrieved from official docs):\n"
        f"{rag_context}\n"
        if rag_context
        else ""
    )

    return f"""You are a certified {framework_name} expert conducting an architecture review.
{ctx_block}
Architecture Type: {analysis.architecture_type}
Description: {analysis.description}
Detected Components: {components_summary}
{cloud.value.upper()} Services Used: {", ".join(services) if services else "inferred from components"}{rag_section}

Evaluate this architecture against the {framework_name} and return ONLY valid JSON:
{{
  "overall_score": <integer 0-100>,
  "overall_status": "<Excellent|Good|Fair|Poor>",
  "summary": "<2-3 sentence executive summary of the architecture quality>",
  "critical_gaps": ["<list of critical missing elements or risks>"],
  "pillars": [
    {{
      "pillar": "<pillar name>",
      "score": <integer 0-100>,
      "status": "<Excellent|Good|Fair|Poor>",
      "findings": ["<specific finding about this architecture>", ...],
      "recommendations": ["<specific actionable recommendation>", ...]
    }}
  ]
}}

Pillars to evaluate (must include all): {json.dumps(pillars)}
Provide 2-4 findings and 2-4 recommendations per pillar. Be specific to the architecture components shown.
Score: 90-100=Excellent, 70-89=Good, 50-69=Fair, 0-49=Poor"""


def run_waf_review(
    analysis: DiagramAnalysisResponse,
    clouds: List[CloudProvider],
    user_context: 'UserContext | None' = None,
) -> List[WAFReviewResponse]:
    """Run WAF review for each specified cloud provider."""
    client, model = _get_client()
    results = []

    for cloud in clouds:
        # Build a retrieval query from the architecture description and components
        retrieval_query = (
            f"{analysis.architecture_type} {analysis.description} "
            + " ".join([c.name for c in analysis.components])
        )
        rag_context = rag_service.retrieve_waf_context(
            query=retrieval_query,
            provider=cloud.value,
        )

        prompt = _build_waf_prompt(cloud, analysis, user_context, rag_context)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a cloud architecture expert. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

        data = json.loads(response.choices[0].message.content)

        pillars = [
            WAFPillarScore(
                pillar=p["pillar"],
                score=p["score"],
                status=p.get("status", _score_to_status(p["score"])),
                findings=p.get("findings", []),
                recommendations=p.get("recommendations", []),
            )
            for p in data.get("pillars", [])
        ]

        results.append(
            WAFReviewResponse(
                cloud=cloud,
                overall_score=data.get("overall_score", 0),
                overall_status=data.get("overall_status", _score_to_status(data.get("overall_score", 0))),
                pillars=pillars,
                summary=data.get("summary", ""),
                critical_gaps=data.get("critical_gaps", []),
            )
        )

    return results


def _score_to_status(score: int) -> str:
    if score >= 90:
        return "Excellent"
    elif score >= 70:
        return "Good"
    elif score >= 50:
        return "Fair"
    else:
        return "Poor"
