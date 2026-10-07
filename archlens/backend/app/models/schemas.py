from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum


class CloudProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class UserContext(BaseModel):
    """Optional user-provided context to sharpen analysis, WAF, pricing, terraform."""
    workload_description: Optional[str] = None
    expected_scale: Optional[str] = None  # dev | small | medium | large
    compliance: List[str] = []  # HIPAA, PCI-DSS, SOC2, GDPR, FedRAMP
    region_preferences: List[str] = []  # us-east, eu-west, ap-south...
    budget_monthly_usd: Optional[float] = None
    priority: Optional[str] = None  # cost | performance | reliability | security
    constraints: Optional[str] = None  # free-form: "must use Azure", "no serverless"


class ArchComponent(BaseModel):
    name: str
    type: str
    category: str  # compute, storage, network, database, security, messaging, etc.
    description: str
    aws_equivalent: Optional[str] = None
    azure_equivalent: Optional[str] = None
    gcp_equivalent: Optional[str] = None


class DiagramAnalysisResponse(BaseModel):
    components: List[ArchComponent]
    architecture_type: str
    description: str
    detected_services: Dict[str, List[str]]  # cloud -> list of service names
    raw_analysis: str


class WAFPillarScore(BaseModel):
    pillar: str
    score: int  # 0-100
    status: str  # excellent, good, fair, poor
    findings: List[str]
    recommendations: List[str]


class WAFReviewResponse(BaseModel):
    cloud: CloudProvider
    overall_score: int
    overall_status: str
    pillars: List[WAFPillarScore]
    summary: str
    critical_gaps: List[str]


class PricingBreakdownItem(BaseModel):
    service: str
    component: str
    monthly_cost: float
    unit: str
    quantity: float
    unit_price: float


class PricingEstimateResponse(BaseModel):
    cloud: CloudProvider
    monthly_estimate: float
    annual_estimate: float
    currency: str = "USD"
    breakdown: List[PricingBreakdownItem]
    assumptions: List[str]
    region: str


class PricingComparisonResponse(BaseModel):
    aws: Optional[PricingEstimateResponse] = None
    azure: Optional[PricingEstimateResponse] = None
    gcp: Optional[PricingEstimateResponse] = None
    cheapest: Optional[str] = None
    recommendation: str


class TerraformFile(BaseModel):
    filename: str
    content: str
    description: str


class TerraformGenerateResponse(BaseModel):
    cloud: CloudProvider
    files: List[TerraformFile]
    summary: str
    estimated_resources: int


class GithubPushRequest(BaseModel):
    token: str  # GitHub PAT with `repo` scope
    repo_name: str  # e.g. "my-archlens-tf" (no slashes) OR "owner/repo" for existing
    create_if_missing: bool = True
    private: bool = True
    branch: str = "main"
    base_path: str = "terraform"  # subfolder inside repo
    commit_message: str = "ArchLens: initial Terraform commit"
    files: List[TerraformFile]
    include_readme: bool = True
    readme_extra: Optional[str] = None  # appended to default README


class GithubPushResponse(BaseModel):
    repo_url: str
    repo_full_name: str
    branch: str
    commits: List[Dict[str, str]]  # [{path, sha, html_url}]
    created_repo: bool
    files_written: int


class AnalyzeRequest(BaseModel):
    # Provide ONE of: image (base64) OR drawio_xml (raw XML text)
    image_base64: Optional[str] = None
    mime_type: str = "image/png"
    drawio_xml: Optional[str] = None
    source_filename: Optional[str] = None
    user_context: Optional[UserContext] = None


class WAFRequest(BaseModel):
    analysis: DiagramAnalysisResponse
    clouds: List[CloudProvider] = [CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP]
    user_context: Optional[UserContext] = None


class PricingRequest(BaseModel):
    analysis: DiagramAnalysisResponse
    region_preferences: Optional[Dict[str, str]] = None  # cloud -> region
    user_context: Optional[UserContext] = None


class TerraformRequest(BaseModel):
    analysis: DiagramAnalysisResponse
    cloud: CloudProvider
    region: Optional[str] = None
    include_modules: bool = True
    user_context: Optional[UserContext] = None


class WAFFindingSummary(BaseModel):
    cloud: str
    overall_score: int
    critical_gaps: List[str] = []
    top_recommendations: List[str] = []


class GenerateDiagramRequest(BaseModel):
    analysis: DiagramAnalysisResponse
    waf_findings: List[WAFFindingSummary] = []
    target_cloud: Optional[CloudProvider] = None
    user_context: Optional[UserContext] = None


class GenerateDiagramResponse(BaseModel):
    mermaid: str
    drawio_xml: str
    summary: str
    improvements: List[str] = []
    target_cloud: Optional[CloudProvider] = None
