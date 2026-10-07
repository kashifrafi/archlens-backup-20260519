# ArchLens - End-to-End Workflow Documentation

## Table of Contents
1. [User Journey Overview](#user-journey-overview)
2. [Step-by-Step Workflow](#step-by-step-workflow)
3. [Technical Flow Diagrams](#technical-flow-diagrams)
4. [State Transitions](#state-transitions)
5. [Error Recovery Flows](#error-recovery-flows)
6. [Performance Timeline](#performance-timeline)

---

## 1. User Journey Overview

### 1.1 Complete User Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ARCHLENS USER JOURNEY                              │
└──────────────────────────────────────────────────────────────────────────┘

Phase 1: UPLOAD & ANALYSIS (30-45 seconds)
┌─────────────────────────────────────────────────────────────────────────┐
│ User Action                  │ System Response                           │
├──────────────────────────────┼──────────────────────────────────────────┤
│ 1. Upload diagram image      │ • Display preview                         │
│ 2. Click "Analyze"           │ • Send to Analysis LLM vision model            │
│                              │ • Extract components (EC2, RDS, etc.)     │
│                              │ • Detect architecture pattern             │
│                              │ • Show component cards                    │
└─────────────────────────────────────────────────────────────────────────┘

Phase 2: REVIEW & PLANNING (60-90 seconds)
┌─────────────────────────────────────────────────────────────────────────┐
│ User Action                  │ System Response                           │
├──────────────────────────────┼──────────────────────────────────────────┤
│ 3. Review WAF compliance     │ • Generate 6-pillar security review       │
│ 4. Check pricing             │ • Show AWS/Azure/GCP cost comparison      │
│ 5. Select cloud (AWS/Azure)  │ • Prepare for Terraform generation        │
└─────────────────────────────────────────────────────────────────────────┘

Phase 3: CODE GENERATION (45-90 seconds)
┌─────────────────────────────────────────────────────────────────────────┐
│ User Action                  │ System Response                           │
├──────────────────────────────┼──────────────────────────────────────────┤
│ 6. Click "Generate"          │ • LLM generates modular Terraform         │
│                              │ • Apply HCL syntax fixes                  │
│                              │ • Apply provider schema fixes             │
│                              │ • Run terraform fmt                       │
│                              │ • Display code with syntax highlighting   │
└─────────────────────────────────────────────────────────────────────────┘

Phase 4: VALIDATION & DEPLOYMENT (2-5 minutes)
┌─────────────────────────────────────────────────────────────────────────┐
│ User Action                  │ System Response                           │
├──────────────────────────────┼──────────────────────────────────────────┤
│ 7. Enter AWS credentials     │ • Store in memory (not persisted)         │
│ 8. Enable "Run plan"         │ • Activate plan checkbox                  │
│ 9. Click "Run"               │ • Execute: fmt → init → validate → plan   │
│                              │ • Stream real-time logs                   │
│                              │ • Show green arrows on completion         │
│                              │ • Display plan summary (resources)        │
│                              │ • AI auto-fixes on errors (max 3 tries)   │
│                              │ • Show diff view (before/after fix)       │
└─────────────────────────────────────────────────────────────────────────┘

Phase 5: DOWNLOAD & DEPLOY (30-60 seconds)
┌─────────────────────────────────────────────────────────────────────────┐
│ User Action                  │ System Response                           │
├──────────────────────────────┼──────────────────────────────────────────┤
│ 10. Download as ZIP          │ • Create terraform-aws-<timestamp>.zip    │
│                              │ • Maintain folder structure (modules/)    │
│ 11. Push to GitHub           │ • Create new repo or push to existing     │
│                              │ • Preserve modular structure              │
│ 12. Deploy (manual)          │ • User: terraform apply in local env      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Step-by-Step Workflow

### STEP 1: Diagram Upload

**User Action:**
```
1. Navigate to ArchLens frontend (http://localhost:5173)
2. Click "Upload Architecture Diagram"
3. Select PNG/JPG/WebP file (max 10MB)
4. Preview displays uploaded image
```

**Technical Flow:**
```javascript
// DiagramUpload.jsx
const handleUpload = (file) => {
  setSelectedFile(file);
  setPreviewUrl(URL.createObjectURL(file));
  
  // Convert to base64 for API
  const reader = new FileReader();
  reader.onload = () => {
    setBase64Image(reader.result.split(',')[1]);
  };
  reader.readAsDataURL(file);
};
```

**Backend Processing:**
```python
# routers/analyze.py
@router.post("/api/analyze")
async def analyze_diagram(file: UploadFile):
    contents = await file.read()
    base64_image = base64.b64encode(contents).decode('utf-8')
    
    # Call Analysis LLM vision
    response = analyzer_service.analyze_diagram(base64_image)
    return response
```

---

### STEP 2: Component Analysis

**AI Prompt (Analysis LLM):**
```
Analyze this cloud architecture diagram. Identify all components:
- Cloud resources (EC2, Lambda, RDS, S3, etc.)
- Networking (VPC, subnets, load balancers)
- Security (IAM, security groups, KMS)
- Data flow and connections

For each component, provide:
- Name
- Type
- AWS/Azure/GCP equivalent
- Purpose

Return JSON only.
```

**Response Structure:**
```json
{
  "components": [
    {
      "name": "Web Application",
      "type": "Compute Instance",
      "category": "compute",
      "description": "Frontend application server",
      "aws_equivalent": "EC2 t3.medium",
      "azure_equivalent": "Azure VM Standard_B2s",
      "gcp_equivalent": "Compute Engine e2-medium"
    },
    {
      "name": "Database",
      "type": "Relational Database",
      "category": "database",
      "description": "PostgreSQL database",
      "aws_equivalent": "RDS PostgreSQL db.t3.micro",
      "azure_equivalent": "Azure Database for PostgreSQL",
      "gcp_equivalent": "Cloud SQL for PostgreSQL"
    }
  ],
  "architecture_type": "3-Tier Web Application",
  "description": "Standard web app with ALB, EC2, and RDS"
}
```

**Frontend Display:**
```jsx
// AnalysisView.jsx
{components.map(comp => (
  <div key={comp.name} className="component-card">
    <h3>{comp.name}</h3>
    <Badge>{comp.type}</Badge>
    <p>{comp.description}</p>
    <div className="cloud-equivalents">
      <span>☁️ AWS: {comp.aws_equivalent}</span>
      <span>☁️ Azure: {comp.azure_equivalent}</span>
      <span>☁️ GCP: {comp.gcp_equivalent}</span>
    </div>
  </div>
))}
```

---

### STEP 3: WAF Compliance Review

**Process:**
```python
# waf_service.py
def analyze_waf_compliance(
    components: List[ArchComponent],
    cloud: CloudProvider
) -> WAFReviewResponse:
    """
    Evaluates architecture against 6 WAF pillars:
    1. Operational Excellence (automation, IaC)
    2. Security (encryption, IAM, network isolation)
    3. Reliability (multi-AZ, backups, monitoring)
    4. Performance Efficiency (resource sizing, caching)
    5. Cost Optimization (right-sizing, reserved instances)
    6. Sustainability (efficient resource usage)
    """
```

**Score Calculation:**
```
Each pillar scored 0-100:
- 90-100: Excellent ✅
- 75-89:  Good ✓
- 50-74:  Fair ⚠️
- 0-49:   Poor ❌

Overall Score = Average of 6 pillars
```

**Frontend Display:**
```jsx
// WAFReview.jsx
<div className="waf-pillars">
  {pillars.map(pillar => (
    <PillarCard
      name={pillar.pillar}
      score={pillar.score}
      status={pillar.status}
      findings={pillar.findings}
      recommendations={pillar.recommendations}
    />
  ))}
</div>
```

---

### STEP 4: Cost Estimation

**Pricing API Call:**
```python
# pricing_service.py
async def estimate_pricing(
    components: List[ArchComponent],
    cloud: CloudProvider,
    region: str = "us-east-1"
) -> PricingEstimateResponse:
    """
    Estimates monthly cost based on:
    - Component type → service mapping
    - Default sizing assumptions
    - Regional pricing variations
    - Usage patterns (24/7 vs. on-demand)
    """
```

**Cost Breakdown Example:**
```
AWS Pricing Estimate (us-east-1):

Service          | Component      | Qty | Unit Price | Monthly
-----------------|----------------|-----|------------|--------
EC2 t3.medium    | Web Server     | 2   | $30.37     | $60.74
RDS db.t3.micro  | Database       | 1   | $12.48     | $12.48
ALB              | Load Balancer  | 1   | $16.20     | $16.20
S3 Standard      | Asset Storage  | 1   | $0.023/GB  | $2.30
CloudWatch       | Monitoring     | 1   | $10.00     | $10.00
                                                    ------------
                                        Monthly Total: $101.72
                                         Annual Total: $1,220.64

Assumptions:
- 730 hours/month (24/7 operation)
- Standard On-Demand pricing
- 100GB S3 storage
- 10 CloudWatch metrics
```

---

### STEP 5: Terraform Code Generation (Streaming)

**Frontend SSE Connection:**
```javascript
// TerraformViewer.jsx
const handleGenerate = async () => {
  const response = await fetch('/api/terraform/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      analysis: analysisData,
      cloud: selectedCloud,
      region: selectedRegion,
    }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const events = parseSSE(chunk);

    for (const event of events) {
      if (event.type === 'progress') {
        updateProgressBar(event.data.step, event.data.message);
      } else if (event.type === 'done') {
        displayGeneratedFiles(event.data.files);
      }
    }
  }
};
```

**Backend Generation Pipeline:**
```python
# terraform_service.py
async def generate_terraform_stream(...):
    # Step 1: LLM Call (Code Generation LLM)
    yield sse_event('progress', {
        'step': 'llm',
        'message': 'Generating AWS Terraform code...'
    })
    
    prompt = build_prompt(analysis, cloud='aws')
    response = await client.chat.completions.create(
        model='gpt-5.3-codex',
        messages=[...],
        max_tokens=16000,
        temperature=0.3,
        response_format={'type': 'json_object'}
    )
    
    # Step 2: HCL Syntax Fix
    yield sse_event('progress', {
        'step': 'hcl_fix',
        'message': 'Fixing HCL syntax...'
    })
    files = fix_hcl_syntax(files)
    
    # Step 3: Schema Fixes
    yield sse_event('progress', {
        'step': 'schema',
        'message': 'Applying AWS provider schema fixes...'
    })
    files = apply_aws_schema_fixes(files)
    files = apply_rag_schema_fixes(files, 'aws')
    
    # Step 4: Finalization
    yield sse_event('progress', {
        'step': 'finalize',
        'message': 'Deduplicating variables...'
    })
    files = deduplicate_variables(files)
    files = lock_provider_versions(files)
    files = inject_variable_defaults(files)
    
    # Step 5: Format
    yield sse_event('progress', {
        'step': 'fmt',
        'message': 'Running terraform fmt...'
    })
    files = auto_fmt_files(files)
    
    # Done
    yield sse_event('done', {
        'files': files,
        'summary': 'Generated 12 files',
        'cloud': 'aws'
    })
```

**Generated File Structure:**
```
terraform-aws-<timestamp>/
├── main.tf                        # Module calls, provider config
├── variables.tf                   # Root input variables
├── outputs.tf                     # Root outputs
└── modules/
    ├── networking/
    │   ├── main.tf                # VPC, subnets, IGW, NAT
    │   ├── variables.tf
    │   └── outputs.tf
    ├── compute/
    │   ├── main.tf                # EC2, ALB, ASG
    │   ├── variables.tf
    │   └── outputs.tf
    └── database/
        ├── main.tf                # RDS, subnet group
        ├── variables.tf
        └── outputs.tf
```

---

### STEP 6: Real-Time Terraform Execution

**Stage 1: Format**
```bash
# Executed command
terraform fmt -recursive .

# Expected output (streaming)
main.tf
modules/networking/main.tf
modules/compute/main.tf

# SSE Events
event: stage
data: {"stage": "fmt", "message": "Starting terraform fmt..."}

event: log
data: {"stage": "fmt", "line": "main.tf"}

event: stage_done
data: {"stage": "fmt", "passed": true, "attempts": 1}
```

**Stage 2: Initialize**
```bash
# Executed command
terraform init -upgrade

# Environment variables
TF_PLUGIN_CACHE_DIR=~/.archlens/tf-plugin-cache
TF_INPUT=false
TF_IN_AUTOMATION=true
CHECKPOINT_DISABLE=1

# Expected output (streaming)
Initializing the backend...
Initializing provider plugins...
- Finding hashicorp/aws versions matching "~> 5.0"...
- Using previously-installed hashicorp/aws v5.70.0

Terraform has been successfully initialized!

# SSE Events
event: stage
data: {"stage": "init", "message": "Starting terraform init -upgrade..."}

event: log
data: {"stage": "init", "line": "Initializing the backend..."}

event: log
data: {"stage": "init", "line": "- Using previously-installed hashicorp/aws v5.70.0"}

event: stage_done
data: {"stage": "init", "passed": true, "attempts": 1, "duration": 25.3}
```

**Stage 3: Validate (with AI Fix Loop)**
```bash
# Executed command
terraform validate

# FAIL - Attempt 1 (Original Code)
Error: Invalid argument
  on modules/compute/main.tf line 42:
  42:     target_group_arn = aws_lb_target_group.app.arn
  
  An argument named "target_group_arn" is not expected here.

# SSE Events - Error Detected
event: validate_errors
data: {
  "errors": ["Error: Invalid argument on modules/compute/main.tf line 42..."],
  "attempt": 1
}

# AI Fix Process
event: stage
data: {
  "stage": "llm_fix",
  "message": "🤖 Fixing the code... (attempt 1/2)"
}

# Code Generation LLM analyzes error + file content + schema
# Returns fixed code with nested block:
#   target_group {
#     arn = aws_lb_target_group.app.arn
#   }

event: files_updated
data: {
  "stage": "llm_fix",
  "files": [...updated files...],
  "diff": {
    "before": "target_group_arn = aws_lb_target_group.app.arn",
    "after": "target_group {\n  arn = aws_lb_target_group.app.arn\n}",
    "filename": "modules/compute/main.tf"
  }
}

# RETRY - Attempt 2 (AI-Fixed Code)
terraform validate

# SUCCESS
Success! The configuration is valid.

# SSE Events - Success
event: stage_done
data: {"stage": "validate", "passed": true, "attempts": 2}
```

**Stage 4: Plan (with Credentials)**
```bash
# Environment variables (user-provided credentials)
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_DEFAULT_REGION=us-east-1

# Executed command
terraform plan

# Expected output (streaming)
Terraform will perform the following actions:

  # module.networking.aws_vpc.main will be created
  + resource "aws_vpc" "main" {
      + cidr_block           = "10.0.0.0/16"
      + enable_dns_hostnames = true
      ...
    }

  # module.compute.aws_instance.app[0] will be created
  + resource "aws_instance" "app" {
      + ami                          = "ami-0c55b159cbfafe1f0"
      + instance_type                = "t3.medium"
      ...
    }

Plan: 15 to add, 0 to change, 0 to destroy.

# SSE Events
event: stage
data: {"stage": "plan", "message": "Starting terraform plan..."}

event: log
data: {"stage": "plan", "line": "Terraform will perform the following actions..."}

event: stage_done
data: {
  "stage": "plan",
  "passed": true,
  "attempts": 1,
  "summary": {
    "add": 15,
    "change": 0,
    "destroy": 0,
    "resources": [
      "+ module.networking.aws_vpc.main",
      "+ module.networking.aws_subnet.private[0]",
      "+ module.networking.aws_subnet.private[1]",
      ...
    ]
  }
}

event: done
data: {
  "passed": true,
  "plan_summary": {...},
  "files": [...final files...]
}
```

---

### STEP 7: Download & GitHub Push

**ZIP Download:**
```javascript
// TerraformRunner.jsx
const downloadArtifacts = async () => {
  const zip = new JSZip();
  
  // Add all files maintaining folder structure
  finalFiles.forEach(file => {
    zip.file(file.filename, file.content);
    // e.g., "modules/networking/main.tf"
  });
  
  // Generate ZIP blob
  const blob = await zip.generateAsync({ type: 'blob' });
  
  // Download
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `terraform-${cloud}-${Date.now()}.zip`;
  a.click();
  
  toast.success('Downloaded Terraform artifacts as ZIP');
};
```

**GitHub Push:**
```python
# github_service.py
async def push_to_github(
    token: str,
    repo_name: str,
    branch: str,
    files: List[TerraformFile],
    commit_message: str
):
    """
    1. Check if repo exists
       - If no: Create new repo (GitHub API)
       - If yes: Get existing repo reference
    
    2. Create branch (if needed)
    
    3. Push files maintaining structure
       - For each file: PUT /repos/{owner}/{repo}/contents/{path}
       - Include SHA for updates
       - Use file.filename as path (preserves modules/ structure)
    
    4. Return: repo_url, commit_sha
    """
```

---

## 3. Technical Flow Diagrams

### 3.1 Component Interaction Sequence

```
┌──────┐          ┌──────────┐          ┌──────────┐          ┌─────────┐
│Client│          │ FastAPI  │          │ Services │          │   AI    │
└──┬───┘          └────┬─────┘          └────┬─────┘          └────┬────┘
   │                   │                     │                      │
   │  POST /analyze    │                     │                      │
   ├──────────────────>│                     │                      │
   │                   │  analyze_diagram()  │                      │
   │                   ├────────────────────>│                      │
   │                   │                     │  Analysis LLM API call    │
   │                   │                     ├─────────────────────>│
   │                   │                     │                      │
   │                   │                     │   Component JSON     │
   │                   │                     │<─────────────────────┤
   │                   │   AnalysisResponse  │                      │
   │                   │<────────────────────┤                      │
   │  JSON Response    │                     │                      │
   │<──────────────────┤                     │                      │
   │                   │                     │                      │
   │  POST /terraform/stream (SSE)           │                      │
   ├──────────────────>│                     │                      │
   │                   │  generate_stream()  │                      │
   │                   ├────────────────────>│                      │
   │                   │                     │  Code Generation LLM       │
   │                   │                     ├─────────────────────>│
   │  SSE: progress    │                     │                      │
   │<──────────────────┤                     │   Terraform JSON     │
   │                   │                     │<─────────────────────┤
   │  SSE: progress    │                     │                      │
   │<──────────────────┤  Schema fixes       │                      │
   │                   │                     │                      │
   │  SSE: done        │   Final files       │                      │
   │<──────────────────┤<────────────────────┤                      │
   │                   │                     │                      │
   │  POST /terraform/run (SSE)              │                      │
   ├──────────────────>│                     │                      │
   │                   │  run_stream()       │                      │
   │                   ├────────────────────>│                      │
   │  SSE: stage       │                     │                      │
   │<──────────────────┤  terraform init     │                      │
   │  SSE: log         │                     │                      │
   │<──────────────────┤  terraform validate │                      │
   │  SSE: validate_errors                   │                      │
   │<──────────────────┤                     │  AI fix              │
   │                   │                     ├─────────────────────>│
   │  SSE: files_updated                     │  Fixed code          │
   │<──────────────────┤<────────────────────┤<─────────────────────┤
   │  SSE: stage_done  │                     │                      │
   │<──────────────────┤  terraform plan     │                      │
   │  SSE: done        │                     │                      │
   │<──────────────────┤<────────────────────┤                      │
```

---

## 4. State Transitions

### 4.1 Stage State Machine

```
┌─────────────────────────────────────────────────────────────────┐
│                  TERRAFORM EXECUTION STATE MACHINE               │
└─────────────────────────────────────────────────────────────────┘

Initial State: IDLE
  ├─ User clicks "Run"
  └─> RUNNING

RUNNING (Global)
  ├─ fmt stage
  │   ├─ PENDING → RUNNING → PASSED
  │   └─ (Always succeeds, no retries)
  │
  ├─ init stage
  │   ├─ PENDING → RUNNING → PASSED
  │   └─ (Rarely fails, 300s timeout)
  │
  ├─ validate stage
  │   ├─ PENDING → RUNNING
  │   ├─ [Success] → PASSED
  │   ├─ [Failure] → AI_FIXING (attempt 1/2)
  │   │   ├─ [Fix Success] → RUNNING → PASSED
  │   │   ├─ [Fix Fails] → AI_FIXING (attempt 2/2)
  │   │   │   ├─ [Fix Success] → RUNNING → PASSED
  │   │   │   └─ [Fix Fails] → MANUAL_FIX_REQUIRED
  │   │   └─ [Fix Timeout] → FAILED
  │   └─ [Max retries] → MANUAL_FIX_REQUIRED
  │
  └─ plan stage
      ├─ PENDING → RUNNING
      ├─ [Success] → PASSED
      ├─ [No Creds] → SKIPPED (graceful skip)
      └─ [Failure] → AI_FIXING (same retry logic as validate)

Terminal States:
  • ALL_PASSED: All stages completed successfully
  • PARTIAL_SUCCESS: Validate passed, plan skipped (no creds)
  • MANUAL_FIX_REQUIRED: AI exhausted retries, user intervention needed
  • ABORTED: User clicked "Stop"
```

---

## 5. Error Recovery Flows

### 5.1 Validation Error Recovery

```
┌────────────────────────────────────────────────────────────────┐
│          VALIDATION ERROR AUTO-RECOVERY FLOW                    │
└────────────────────────────────────────────────────────────────┘

[terraform validate fails]
         │
         ▼
┌────────────────────────┐
│  Extract Error Lines   │  ← Parse output for file + line numbers
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│  Store Files Before    │  ← Snapshot original files
│        Fix             │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│   Call Code Generation LLM   │  ← Prompt: "Fix these errors: ..."
│  (temperature = 0.1)   │     Include: files, errors, schema context
└────────┬───────────────┘
         │
         ├─[Success]─────────────────────────┐
         │                                   │
         ▼                                   ▼
┌────────────────────────┐         ┌────────────────────────┐
│   Apply Fixed Files    │         │  Create Diff View      │
└────────┬───────────────┘         │  (before/after)        │
         │                         └────────────────────────┘
         │
         ▼
┌────────────────────────┐
│  Re-run terraform      │
│      validate          │
└────────┬───────────────┘
         │
         ├─[Pass]────> SUCCESS (continue to plan)
         │
         ├─[Fail, attempt < 3]────> RETRY (go back to Code Generation LLM)
         │
         └─[Fail, attempt = 3]────> MANUAL_FIX_MODE
                                         │
                                         ▼
                                    ┌────────────────────────┐
                                    │  Show Inline Editor    │
                                    │  Highlight Error Lines │
                                    │  User Edits + Re-runs  │
                                    └────────────────────────┘
```

### 5.2 Manual Fix Mode UI

```
┌──────────────────────────────────────────────────────────────────┐
│                   🛠 MANUAL FIX REQUIRED                         │
│                                                                   │
│  Auto-fix couldn't resolve all errors after 2 attempts.          │
│  Edit the highlighted lines below, then re-run.                  │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ Validation Errors (3):                                            │
├──────────────────────────────────────────────────────────────────┤
│ ❌ Error: Invalid argument                                       │
│    on modules/compute/main.tf line 42                            │
│    "target_group_arn" is not expected here                       │
│                                                                   │
│ ❌ Error: Missing required argument                              │
│    on modules/database/main.tf line 18                           │
│    "db_subnet_group_name" is required                            │
│                                                                   │
│ ❌ Error: Unsupported argument                                   │
│    on main.tf line 5                                             │
│    "acl" is not supported in AWS provider v5                     │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ File: modules/compute/main.tf                      [➜ Jump to Line]│
├──────────────────────────────────────────────────────────────────┤
│  40 | resource "aws_lb_listener" "http" {                        │
│  41 |   load_balancer_arn = aws_lb.main.arn                      │
│ ▓42▓| target_group_arn = aws_lb_target_group.app.arn ◄─ERROR    │
│  43 |   port              = 80                                   │
│  44 |   protocol          = "HTTP"                               │
└──────────────────────────────────────────────────────────────────┘
       ▲ Red thick border on error line

[💾 Save & Re-run]  [Cancel]
```

---

## 6. Performance Timeline

### 6.1 Typical Execution Times

```
┌──────────────────────────────────────────────────────────────────┐
│                    ARCHLENS PERFORMANCE PROFILE                   │
│                  (AWS 3-Tier Web Application)                     │
└──────────────────────────────────────────────────────────────────┘

Phase 1: Analysis & Review
├─ Diagram Upload          │███                         │  3s
├─ Analysis LLM Analysis        │████████████████████████    │ 25s
├─ WAF Review             │████████████████████████    │ 22s
└─ Cost Estimation        │████████████                │ 12s
                          Total: ~62 seconds

Phase 2: Terraform Generation
├─ Code Generation LLM Call     │████████████████████████████████│ 35s
├─ HCL Syntax Fix         │██                              │  2s
├─ Schema Fixes (regex)   │███                             │  3s
├─ Schema Fixes (RAG)     │█████                           │  5s
├─ Variable Dedup         │██                              │  2s
├─ Version Lock           │█                               │  1s
├─ Default Injection      │███                             │  3s
└─ Terraform fmt          │████                            │  4s
                          Total: ~55 seconds

Phase 3: Validation & Planning
├─ terraform fmt          │███                             │  3s
├─ terraform init         │████████████████████            │ 22s
│                         │  (with plugin cache)           │
├─ terraform validate     │████                            │  4s
│   ├─ [Pass]             │                                │
│   └─ [Fail + AI Fix]    │████████████████                │ 18s
└─ terraform plan         │████████████████████████████████│ 35s
                          Total: ~64-82 seconds (with retry)

Phase 4: Download & Deploy
├─ ZIP Generation         │██                              │  2s
└─ GitHub Push            │█████████                       │  8s
                          Total: ~10 seconds

═══════════════════════════════════════════════════════════════════
TOTAL END-TO-END TIME:     191-209 seconds (3-3.5 minutes)
                           ↓
                           WITHOUT AI FIX: ~173 seconds (2.9 min)
                           WITH 1 AI FIX:  ~191 seconds (3.2 min)
                           WITH 2 AI FIXES: ~209 seconds (3.5 min)
═══════════════════════════════════════════════════════════════════
```

### 6.2 Optimization Opportunities

| Bottleneck | Current | Optimized | Improvement |
|------------|---------|-----------|-------------|
| **terraform init** | 22s | 8s | Pre-warm plugin cache |
| **Code Generation LLM** | 35s | 25s | Reduce max_tokens to 12K |
| **terraform plan** | 35s | 25s | Use speculative plan |
| **Schema RAG** | 5s | 2s | Redis cache for vectors |

**Total Potential:** ~173s → ~120s (30% faster)

---

## Document Version
- **Version**: 1.0
- **Last Updated**: May 19, 2026
- **Author**: ArchLens Development Team
