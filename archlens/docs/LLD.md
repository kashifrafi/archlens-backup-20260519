# ArchLens - Low Level Design (LLD)

## 1. Module Architecture

### 1.1 Frontend Module Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── DiagramUpload.jsx         # Image upload with preview
│   │   ├── AnalysisView.jsx          # Component detection display
│   │   ├── TerraformViewer.jsx       # Code generation UI with SSE
│   │   ├── TerraformRunner.jsx       # Real-time execution panel
│   │   ├── PricingComparison.jsx     # Multi-cloud cost comparison
│   │   ├── WAFReview.jsx             # 6-pillar compliance review
│   │   └── GithubPush.jsx            # GitHub integration
│   ├── App.jsx                        # Main application component
│   ├── main.jsx                       # React entry point
│   └── index.css                      # Tailwind CSS configuration
├── package.json
├── vite.config.js
└── tailwind.config.js
```

### 1.2 Backend Module Structure

```
backend/
├── app/
│   ├── main.py                        # FastAPI application entry
│   ├── config.py                      # Configuration management
│   ├── models/
│   │   └── schemas.py                 # Pydantic data models
│   ├── routers/
│   │   ├── analyze.py                 # POST /api/analyze
│   │   ├── terraform.py               # /api/terraform/* endpoints
│   │   ├── pricing.py                 # POST /api/pricing
│   │   ├── waf.py                     # POST /api/waf-review
│   │   └── github.py                  # POST /api/github/push
│   └── services/
│       ├── analyzer_service.py        # Diagram analysis logic
│       ├── terraform_service.py       # Code generation + streaming
│       ├── terraform_runner.py        # Real-time execution
│       ├── pricing_service.py         # Cost estimation
│       ├── waf_service.py             # WAF compliance analysis
│       ├── schema_fixer.py            # Regex-based schema fixes
│       ├── schema_fixer_rag.py        # ChromaDB RAG validation
│       ├── foundry_client.py          # Cloud AI Platform wrapper
│       ├── github_service.py          # GitHub API integration
│       ├── context_helper.py          # User context formatting
│       └── module_registry.py         # Module catalogue builder
├── requirements.txt
├── .env
└── .env.example
```

---

## 2. Data Models (Pydantic Schemas)

### 2.1 Core Entities

```python
# models/schemas.py

class CloudProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"

class UserContext(BaseModel):
    workload_description: Optional[str] = None
    expected_scale: Optional[str] = None  # dev|small|medium|large
    compliance: List[str] = []            # HIPAA, PCI-DSS, SOC2, GDPR
    region_preferences: List[str] = []
    budget_monthly_usd: Optional[float] = None
    priority: Optional[str] = None        # cost|performance|reliability
    constraints: Optional[str] = None

class ArchComponent(BaseModel):
    name: str
    type: str
    category: str                         # compute, storage, network, etc.
    description: str
    aws_equivalent: Optional[str] = None
    azure_equivalent: Optional[str] = None
    gcp_equivalent: Optional[str] = None

class DiagramAnalysisResponse(BaseModel):
    components: List[ArchComponent]
    architecture_type: str
    description: str
    detected_services: Dict[str, List[str]]  # cloud -> service names
    raw_analysis: str

class TerraformFile(BaseModel):
    filename: str
    content: str
    description: str

class TerraformGenerateResponse(BaseModel):
    cloud: CloudProvider
    files: List[TerraformFile]
    summary: str
    estimated_resources: int
```

---

## 3. Service Layer Design

### 3.1 Terraform Service (`terraform_service.py`)

#### 3.1.1 Core Functions

```python
def _get_client() -> Tuple[Any, str]:
    """
    Returns AI client for Terraform generation.
    Priority: Cloud AI Platform > Cloud AI Platform > OpenAI
    """
    if settings.azure_foundry_endpoint:
        client = create_foundry_client(...)
        return client, settings.azure_foundry_deployment
    elif settings.azure_openai_endpoint:
        return AzureOpenAI(...), settings.azure_openai_deployment
    else:
        return OpenAI(...), settings.openai_model

async def generate_terraform_stream(
    analysis: DiagramAnalysisResponse,
    cloud: CloudProvider,
    region: Optional[str],
    include_modules: bool,
    user_context: Optional[UserContext]
) -> AsyncGenerator[str, None]:
    """
    Streaming Terraform generation with real-time SSE events.
    
    Pipeline:
    1. LLM call (Code Generation LLM, temperature=0.3, 16K tokens)
    2. HCL syntax fixes (_fix_hcl_syntax)
    3. Provider schema fixes (AWS-specific + RAG)
    4. Variable deduplication
    5. Provider version locking
    6. Variable default injection
    7. Final terraform fmt
    
    Events:
    - progress { step, message }
    - done { files, summary, estimated_resources, cloud }
    - error { message }
    """
```

#### 3.1.2 HCL Syntax Fixer

```python
def _fix_hcl_syntax(files: List[TerraformFile]) -> List[TerraformFile]:
    """
    Rock-solid HCL syntax corrector chain:
    1. _hcl_fix_inline_block_opens  - Fix `variable "x" { type = string`
    2. _hcl_fix_quoted_types        - type = "string" → type = string
    3. _hcl_fix_trailing_commas     - value = "foo", → value = "foo"
    4. _hcl_fix_single_quotes       - value = 'foo' → value = "foo"
    5. _hcl_fix_semicolons          - value = "foo"; → value = "foo"
    6. _hcl_fix_missing_equals      - default "val" → default = "val"
    """
```

#### 3.1.3 Variable Default Injection

```python
def _inject_variable_defaults(files: List[TerraformFile]) -> List[TerraformFile]:
    """
    Smart dummy default generator for every variable without default.
    Pattern matching on variable names:
    
    - ami_id         → "ami-00000000000000000"
    - vpc_id         → "vpc-00000000000000000"
    - subnet_ids     → ["subnet-00...", "subnet-11..."]
    - bucket_name    → "placeholder-bucket-123456"
    - db_password    → "Placeholder@12345!"
    - instance_type  → "t3.micro"
    - region         → "us-east-1"
    - cidr_block     → "10.0.0.0/16"
    
    Goal: terraform validate passes without -var flags
    """
```

### 3.2 Terraform Runner Service (`terraform_runner.py`)

#### 3.2.1 Execution Pipeline

```python
async def run_terraform_stream(
    files: List[Dict],
    cloud: str,
    run_plan: bool,
    env_vars: Dict[str, str]
) -> AsyncGenerator[str, None]:
    """
    Real-time terraform execution with SSE streaming.
    
    Pipeline: fmt → init (-upgrade) → validate → plan
    
    Each stage:
    - Max 3 attempts (1 initial + 2 AI retries)
    - Code Generation LLM fixes errors (temperature=0.1)
    - SSE events: stage, log, stage_done, files_updated, error
    
    Timeouts:
    - fmt: 30s
    - init: 300s (5 min, with plugin cache)
    - validate: 30s
    - plan: 300s (5 min)
    
    Manual Fix Mode:
    - Triggered after 3 failed attempts
    - Shows error lines with red borders
    - User edits inline, saves, re-runs
    """
```

#### 3.2.2 AI Error Fixing

```python
async def _llm_fix_errors(
    files: List[Dict],
    errors: List[str],
    cloud: str,
    stage: str
) -> List[Dict]:
    """
    Code Generation LLM error remediation.
    
    Prompt includes:
    - Full file contents
    - Error messages
    - Provider schema context (ChromaDB RAG)
    - Stage-specific instructions
    
    Returns:
    - Fixed files (JSON response)
    - Applied automatically, no user review
    
    Temperature: 0.1 (highly deterministic fixes)
    Max tokens: 16000
    """
```

### 3.3 Schema Fixer Services

#### 3.3.1 Regex Schema Fixer (`schema_fixer.py`)

```python
# AWS Provider v5/v6 breaking changes

_S3_TRANSFORMS = {
    'aws_s3_bucket': [
        _remove_arg('acl'),
        _remove_arg('lifecycle_rule'),
        _remove_arg('cors_rule'),
        _remove_arg('website'),
        _remove_arg('server_side_encryption_configuration'),
    ]
}

_EC2_TRANSFORMS = {
    'aws_instance': [
        _ensure_ami_set(),
        _fix_user_data_base64(),
    ],
    'aws_launch_configuration': [
        _migrate_to_launch_template(),  # Removed in v5
    ]
}

_ELB_TRANSFORMS = {
    'aws_lb_listener': [
        _fix_target_group_arn(),  # nested block, not attribute
    ]
}
```

#### 3.3.2 RAG Schema Fixer (`schema_fixer_rag.py`)

```python
def get_schema_context(
    resource_types: List[str],
    provider: str
) -> str:
    """
    Retrieves authoritative schema from ChromaDB vector store.
    
    Vector DB Structure:
    - Collection: terraform_schemas_{provider}
    - Documents: Official provider documentation
    - Metadata: resource_type, valid_args, deprecated_args
    
    Query:
    - Semantic search on resource types
    - Returns top 5 matches per resource
    - Formats as markdown reference
    
    Fallback: Empty string if ChromaDB unavailable
    """
```

---

## 4. API Endpoints

### 4.1 Analysis Endpoint

```python
# routers/analyze.py

@router.post("/api/analyze")
async def analyze_diagram(file: UploadFile) -> DiagramAnalysisResponse:
    """
    Analyzes architecture diagram using Analysis LLM vision.
    
    Input: Image file (PNG, JPG, WebP)
    Output: Component list + architecture description
    
    Process:
    1. Read uploaded file as base64
    2. Call Analysis LLM with vision prompt
    3. Parse JSON response
    4. Return structured analysis
    
    Timeout: 60s
    """
```

### 4.2 Terraform Generation (SSE)

```python
# routers/terraform.py

@router.post("/api/terraform/stream")
async def stream_terraform_generation(
    request: TerraformGenerateRequest
) -> StreamingResponse:
    """
    Server-Sent Events stream for Terraform generation.
    
    SSE Events:
    - event: progress
      data: { "step": "llm", "message": "Generating code..." }
    
    - event: done
      data: { "files": [...], "summary": "...", "cloud": "aws" }
    
    - event: error
      data: { "message": "Error details" }
    
    Content-Type: text/event-stream
    Cache-Control: no-cache
    """
```

### 4.3 Terraform Execution (SSE)

```python
# routers/terraform.py

@router.post("/api/terraform/run")
async def run_terraform_execution(
    request: TerraformRunRequest
) -> StreamingResponse:
    """
    Real-time terraform execution with SSE streaming.
    
    SSE Events:
    - stage: { "stage": "init", "message": "Starting..." }
    - log: { "stage": "init", "line": "Initializing..." }
    - stage_done: { "stage": "init", "passed": true, "attempts": 1 }
    - validate_errors: { "errors": [...], "attempt": 2 }
    - files_updated: { "stage": "llm_fix", "files": [...] }
    - done: { "passed": true, "plan_summary": {...}, "files": [...] }
    - error: { "stage": "plan", "message": "..." }
    """
```

---

## 5. Frontend Component Design

### 5.1 TerraformRunner Component

```jsx
// TerraformRunner.jsx

const STAGES = [
  { key: 'fmt',      label: 'Format',   icon: '📝' },
  { key: 'init',     label: 'Init',     icon: '🔧' },
  { key: 'validate', label: 'Validate', icon: '✅' },
  { key: 'plan',     label: 'Plan',     icon: '📋' },
];

// State Management
const [stageState, setStageState] = useState({});
// { fmt: { status: 'passed', attempts: 1 }, ... }

const [logs, setLogs] = useState([]);
// [{ stage: 'init', line: 'Initializing...' }, ...]

const [valDiffData, setValDiffData] = useState(null);
// { before: "...", after: "...", filename: "main.tf" }

// SSE Stream Handling
const run = async () => {
  const response = await fetch('/api/terraform/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files, cloud, run_plan, env_vars: creds }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  
  while (running) {
    const { value, done } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');
    
    for (const line of lines) {
      if (line.startsWith('event:')) {
        const event = line.substring(7).trim();
        // Handle: stage, log, stage_done, validate_errors, done, error
      }
    }
  }
};
```

### 5.2 CodeDiffView Component

```jsx
// Side-by-side diff viewer for AI fixes

function CodeDiffView({ beforeCode, afterCode, filename }) {
  return (
    <div className="grid grid-cols-2 divide-x divide-gray-700">
      {/* Before (Error) - Red background */}
      <div className="bg-red-950/20">
        <div className="bg-red-900/40 px-3 py-1.5">
          <span className="text-red-300">❌ Before (Error)</span>
        </div>
        <pre className="text-xs font-mono text-red-200 p-3">
          <code>{beforeCode}</code>
        </pre>
      </div>
      
      {/* After (Fixed) - Green background */}
      <div className="bg-green-950/20">
        <div className="bg-green-900/40 px-3 py-1.5">
          <span className="text-green-300">✅ After (Fixed)</span>
        </div>
        <pre className="text-xs font-mono text-green-200 p-3">
          <code>{afterCode}</code>
        </pre>
      </div>
    </div>
  );
}
```

---

## 6. Configuration Management

### 6.1 Backend Configuration (`config.py`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Cloud AI Platform (Analysis LLM)
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_deployment: str = "gpt-4.1"
    azure_openai_api_version: str = "2024-02-15-preview"
    
    # Cloud AI Platform (Code Generation LLM)
    azure_foundry_endpoint: Optional[str] = None
    azure_foundry_api_key: Optional[str] = None
    azure_foundry_deployment: str = "gpt-5.3-codex"
    azure_foundry_api_version: str = "2025-04-01-preview"
    
    # Fallback OpenAI
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
```

### 6.2 Frontend Configuration (`vite.config.js`)

```javascript
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    },
    hmr: {
      overlay: true
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: true
  }
});
```

---

## 7. Caching Strategy

### 7.1 Terraform Plugin Cache

```bash
# ~/.archlens/tf-plugin-cache/
# Stores downloaded provider binaries

Directory Structure:
registry.terraform.io/
  hashicorp/
    aws/
      5.70.0/
        linux_amd64/
          terraform-provider-aws_v5.70.0_x5
    azurerm/
      3.110.0/
        linux_amd64/
          terraform-provider-azurerm_v3.110.0_x5

Benefit: 30-60s saved on every terraform init
```

### 7.2 Module Archive

```bash
# ~/.archlens/module-archive/
# Caches downloaded module sources

Format: <module-source-hash>/
  .terraform/modules/modules.json
  registry.terraform.io/terraform-aws-modules/vpc/aws/5.1.2/

Benefit: 10-20s saved on module downloads
```

### 7.3 Base Lockfile

```bash
# ~/.archlens/tf-plugin-cache/base.lock.hcl
# Pre-locked provider versions

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

Benefit: Consistent versions across all generations
```

---

## 8. Error Handling

### 8.1 AI API Errors

```python
# Timeout handling
try:
    response = await asyncio.wait_for(
        llm_call(...),
        timeout=180  # 3 minutes
    )
except asyncio.TimeoutError:
    logger.error("AI API timeout")
    yield sse_event('error', {'message': 'Generation timeout'})
    return

# Retry logic
for attempt in range(MAX_RETRIES):
    try:
        result = await ai_fix_errors(...)
        break
    except Exception as exc:
        if attempt == MAX_RETRIES - 1:
            trigger_manual_fix_mode()
        logger.warning(f"Retry {attempt+1}/{MAX_RETRIES}: {exc}")
```

### 8.2 Terraform Execution Errors

```python
# Process timeout
try:
    proc = await asyncio.create_subprocess_exec(
        'terraform', 'init', '-upgrade',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=tmpdir,
        env=env_with_cache
    )
    await asyncio.wait_for(proc.wait(), timeout=300)
except asyncio.TimeoutError:
    proc.kill()
    yield sse_event('error', {'message': 'Init timeout (5min)'})
```

---

## 9. Database Schema (ChromaDB)

### 9.1 Schema Collections

```python
# Collection: terraform_schemas_aws
{
  "id": "aws_s3_bucket_v5",
  "document": "AWS S3 Bucket resource...",
  "metadata": {
    "resource_type": "aws_s3_bucket",
    "provider": "aws",
    "version": "5.0",
    "valid_args": ["bucket", "bucket_prefix", "force_destroy", "tags"],
    "deprecated_args": ["acl", "lifecycle_rule", "website"],
    "required_args": []
  }
}

# Collection: terraform_schemas_azurerm
# Collection: terraform_schemas_google
```

---

## 10. Testing Strategy

### 10.1 Unit Tests
```python
# tests/test_hcl_syntax.py
def test_fix_inline_block_opens():
    input_hcl = 'variable "x" { type = string\n  default = "y"\n}'
    expected = 'variable "x" {\n  type = string\n  default = "y"\n}'
    assert _hcl_fix_inline_block_opens(input_hcl) == expected

# tests/test_schema_fixer.py
def test_remove_s3_acl():
    input_tf = 'resource "aws_s3_bucket" "x" {\n  acl = "private"\n}'
    expected = 'resource "aws_s3_bucket" "x" {\n}'
    assert apply_aws_schema_fixes([...]) == [...]
```

### 10.2 Integration Tests
```python
# tests/test_terraform_pipeline.py
@pytest.mark.asyncio
async def test_full_pipeline():
    analysis = DiagramAnalysisResponse(...)
    files = await generate_terraform_stream(analysis, CloudProvider.AWS)
    
    # Verify generated files
    assert 'main.tf' in [f.filename for f in files]
    assert 'modules/networking/main.tf' in [f.filename for f in files]
    
    # Verify syntax
    for file in files:
        assert 'type = "string"' not in file.content
```

---

## Document Version
- **Version**: 1.0
- **Last Updated**: May 19, 2026
- **Author**: ArchLens Development Team
