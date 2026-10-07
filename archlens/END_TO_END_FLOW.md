# ArchLens — End-to-End Flow Documentation

## Overview

ArchLens is an AI-powered cloud architecture analysis platform. It accepts architecture diagrams, extracts cloud components, reviews architecture quality, compares pricing across AWS/Azure/GCP, generates modular Terraform, validates the result, and can push the final code to GitHub.

Current product flow:

```text
Upload -> Analysis -> WAF Review -> Pricing -> Terraform -> Validate -> GitHub
```

The public site is served by Nginx at `https://18.215.164.199/`. Local frontend development uses Vite at `http://localhost:5173/`, so production UI changes must be built and copied to the Nginx document root.

---

## Tech Stack

| Layer | Current implementation |
|---|---|
| Public frontend | Nginx HTTPS static site, root `/var/www/html` |
| Frontend dev | React + Vite + Tailwind CSS, `http://localhost:5173/` |
| Backend API | FastAPI + Python 3.12, uvicorn on `127.0.0.1:8000` |
| Public API routing | Nginx proxies `/api/*` to `127.0.0.1:8000` |
| AI analysis/generation | Azure AI Foundry when configured, Azure OpenAI/OpenAI fallback |
| Embeddings/RAG | Azure OpenAI embeddings + local ChromaDB |
| Pricing | Live provider pricing APIs only: AWS Pricing API, Azure Retail Prices API, GCP Cloud Billing Catalog API |
| Terraform tooling | `terraform`, `tflint`, `checkov`, `trivy`, optional HCP Terraform speculative plans |
| Deployment target | EC2 Ubuntu instance with Nginx + local FastAPI backend |

---

## Current User Journey

```text
1. User opens https://18.215.164.199/
2. Upload page displays the enhanced ArchLens hero:
   - AI-Powered Architecture Intelligence
   - subtle enterprise particle background behind the hero/upload area
3. User uploads PNG/JPG/WEBP/SVG or draw.io/XML architecture diagram
4. Backend extracts components and cloud equivalents
5. User reviews WAF findings
6. User compares AWS/Azure/GCP pricing from provider pricing APIs
7. User generates Terraform for AWS, Azure, or GCP
8. Backend enforces modular Terraform hierarchy before returning files
9. User validates/runs Terraform; credentials can come from `.env` or the UI
10. Backend masks credentials as `xxxxxxxx` in validation/run responses
11. User downloads artifacts or pushes Terraform code to GitHub
```

---

## Step 1 — Landing and Upload Page

**Frontend component:** `frontend/src/components/DiagramUpload.jsx`
**Particle component:** `frontend/src/components/ArchLensParticleBackground.jsx`

The upload page keeps the existing ArchLens dark theme, header, and workflow stepper. The hero/upload area now adds a subtle Google Antigravity-inspired dotted particle field adapted for enterprise cloud architecture.

Current visual behavior:

- Canvas-based particle background rendered behind the hero/upload area.
- Blue, cyan, and subtle purple particles.
- Particles are stronger on the left and right sides.
- Center/upload box remains dark, clean, and readable.
- Canvas uses `pointer-events: none` and `aria-hidden="true"`.
- Animation uses `requestAnimationFrame` with cleanup on unmount.
- Resize handling is throttled.
- Mobile and lower-power devices reduce/avoid animation.
- `prefers-reduced-motion` is respected.

Important deployment note:

- `http://localhost:5173/` shows Vite dev output.
- `https://18.215.164.199/` shows Nginx production assets from `/var/www/html`.
- After frontend edits, run `npm run build` and publish `frontend/dist/` to `/var/www/html/`.

---

## Step 2 — Diagram Analysis

**Endpoint:** `POST /api/analyze`
**Router:** `backend/app/routers/analyze.py`
**Service:** `backend/app/services/diagram_analyzer.py`

Supported inputs:

| Input | Handling |
|---|---|
| Image diagrams | PNG, JPG, JPEG, WEBP, GIF, SVG as base64/data URL |
| draw.io/XML | `.drawio`, `.drawio.svg`, `.drawio.xml`, `.xml` |

Draw.io handling has been hardened for multiple real-world formats:

- Raw XML.
- Escaped XML.
- Data URLs from frontend upload.
- Base64-encoded draw.io content.
- Deflate-compressed `<diagram>` content.
- SVG files containing draw.io metadata.
- Object wrappers around mxGraph cells.
- Shape labels and edges/connections.

The analyzer returns a `DiagramAnalysisResponse` with architecture type, description, components, detected services, and cloud-provider equivalents such as `aws_equivalent`, `azure_equivalent`, and `gcp_equivalent`.

---

## Step 3 — WAF Review

**Endpoint:** `POST /api/waf`
**Service:** `backend/app/services/rag_service.py`

The WAF review uses extracted architecture context and RAG guidance from local ChromaDB. It returns pillar scores, findings, recommendations, critical gaps, and an overall score.

Current intent:

- Keep reviews grounded in detected components.
- Use provider-specific guidance where available.
- Present actionable recommendations before Terraform generation.

---

## Step 4 — Pricing Comparison

**Endpoint:** `POST /api/pricing`
**Router:** `backend/app/routers/pricing.py`
**Coordinator:** `backend/app/services/pricing_service.py`

Provider modules:

| Provider | Service module | Pricing source |
|---|---|---|
| AWS | `backend/app/services/aws_pricing.py` | AWS Pricing API via `boto3` |
| Azure | `backend/app/services/azure_pricing.py` | Azure Retail Prices API |
| GCP | `backend/app/services/gcp_pricing.py` | Google Cloud Billing Catalog API |

Current pricing rules:

- Pricing must come from cloud provider pricing APIs, not local static prices or LLM estimates.
- Pricing uses LLM-extracted components and their provider equivalents.
- Components are priced individually so apples-to-apples comparison follows what the diagram actually contains.
- Broad categories are only fallbacks; provider-specific equivalent/name/type are prioritized.
- AWS credentials, GCP API key, and GCP service account settings are read from `backend/.env` where configured.

Load balancer comparison assumptions are standardized across all three providers:

| Assumption | Value |
|---|---:|
| Load balancers | 1 |
| Requests | 50 requests/sec |
| Data transfer | 100 GB/month |
| Runtime | 730 hours/month |

Known validated behavior:

- LB-only monthly comparison is aligned across providers.
- AWS ElastiCache aliases resolve to ElastiCache pricing, not S3/storage fallback.
- Azure pricing uses practical defaults to avoid unexpectedly high Application Gateway/SQL estimates unless the extracted component calls for them.

---

## Step 5 — Terraform Generation

**Endpoints:**

| Endpoint | Purpose |
|---|---|
| `POST /api/terraform` | Synchronous Terraform generation |
| `POST /api/terraform/stream` | Server-sent events progress stream |

**Service:** `backend/app/services/terraform_service.py`

Generation inputs:

| Field | Description |
|---|---|
| `analysis` | Diagram analysis result from Step 2 |
| `cloud` | `aws`, `azure`, or `gcp` |
| `region` | Optional target region |
| `include_modules` | Should be `true` for normal UI flow |
| `user_context` | Optional workload/scale/compliance/cost hints |

### Modular hierarchy requirement

Terraform generation must always preserve module hierarchy.

Required shape:

```text
main.tf
variables.tf
outputs.tf
modules/
  networking/
    main.tf
    variables.tf
    outputs.tf
  compute/
    main.tf
    variables.tf
    outputs.tf
  database/
    main.tf
    variables.tf
    outputs.tf
```

Current backend guard:

- The prompt asks the LLM for root files plus local modules.
- The backend also enforces the structure deterministically with `_ensure_modular_hierarchy()`.
- Root `main.tf` must contain `module` calls.
- Root `main.tf` must not contain raw `resource` or `data` blocks.
- If the LLM returns flat/root-only Terraform, root resources are moved into `modules/core/main.tf`.
- Missing module `variables.tf` and `outputs.tf` files are created.
- If module folders exist but root forgot the calls, root module calls are added.
- The enforcer runs after LLM parsing and again after provider/default post-processing.

### Post-processing pipeline

Current generation pipeline includes:

1. `_ensure_modular_hierarchy()` — hard module hierarchy guard.
2. `_fix_hcl_syntax()` — correct common malformed HCL from model output.
3. `apply_aws_schema_fixes()` — AWS-specific provider schema fixes when cloud is AWS.
4. `apply_rag_schema_fixes()` — provider schema RAG-assisted deterministic cleanup.
5. `_deduplicate_variables()` — remove duplicate variable declarations by scope.
6. `_lock_provider_versions()` — ensure required providers/version constraints.
7. `_inject_variable_defaults()` — add defaults so validation can run without manual var files.
8. `_ensure_modular_hierarchy()` — final hierarchy guard after transforms.
9. `_fix_hcl_syntax()` and `_auto_fmt_files()` — final cleanup and formatting.

---

## Step 6 — Validation and Real Terraform Run

### Static validation

**Endpoint:** `POST /api/terraform/validate`
**Service:** `backend/app/services/validation_service.py`

Validation runs in a temporary directory and returns per-tool results plus an overall score.

Checks include:

1. `terraform fmt -check -diff`
2. `terraform validate -json`
3. `tflint --format json`
4. `checkov -d . --framework terraform -o json`
5. `trivy config --format json`
6. Optional HCP Terraform speculative plan

Before checks run, `_sanitize_files()` reapplies schema fixes to reduce avoidable provider errors.

### Real execution stream

**Endpoint:** `POST /api/terraform/run`
**Service:** `backend/app/services/terraform_runner.py`

The UI can run:

```text
terraform fmt -> terraform init -> terraform validate -> terraform plan
```

Execution behavior:

- Streams SSE events for stages, logs, errors, file updates, and final result.
- Uses plugin/module caching under `~/.archlens/` for faster repeated runs.
- Can use credentials from `.env` or credentials submitted through the UI.
- If validation/plan errors occur, an LLM fix loop can update files and retry.
- After retry exhaustion, the UI can enter manual-fix mode.

### Credential visibility and masking

Credentials may be used internally but must never be visible to the user in validation output, HCP output, or live run logs.

Current redaction behavior:

- Values from `backend/.env` and process env are collected as sensitive values.
- UI-submitted run credentials are tracked per SSE stream.
- Validation responses are recursively masked before being returned.
- Terraform runner SSE payloads and command output lines are masked.
- Common secret patterns are masked, including:
  - AWS access key IDs.
  - AWS secret access keys.
  - session tokens.
  - client secrets.
  - API keys.
  - bearer/token values.
  - passwords.
  - private key blocks.
- Visible replacement is `xxxxxxxx`.
- HCP-created `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` workspace variables are marked sensitive.

---

## Step 7 — GitHub Export

**Endpoint:** `POST /api/github`
**Router:** `backend/app/routers/github.py`

The GitHub step publishes generated Terraform files while preserving the module folder hierarchy. The typical final artifact contains root Terraform files plus `modules/...` directories.

---

## Public Deployment Flow

### Backend

The backend runs locally on the EC2 instance:

```bash
cd /home/ubuntu/archlens-backup-20260519/archlens/backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Nginx proxies `/api/*` requests to `http://127.0.0.1:8000`.

### Frontend development

For local development:

```bash
cd /home/ubuntu/archlens-backup-20260519/archlens/frontend
npm run dev -- --host 0.0.0.0 --force
```

This serves Vite at:

```text
http://localhost:5173/
```

### Frontend production publish

For the public EC2 IP:

```bash
cd /home/ubuntu/archlens-backup-20260519/archlens/frontend
npm run build
cd /home/ubuntu/archlens-backup-20260519/archlens
sudo rsync -a --delete frontend/dist/ /var/www/html/
sudo nginx -t
sudo systemctl reload nginx
```

Verification commands:

```bash
curl -k -I https://18.215.164.199/
curl -k -s https://18.215.164.199/ | grep '/assets/index-'
```

The latest production deployment should contain the new upload hero assets and text:

```bash
curl -k -s https://18.215.164.199/assets/<current-js>.js \
  | grep 'AI-Powered Architecture Intelligence'
```

---

## Environment and Credentials

Primary configuration file:

```text
backend/.env
```

Common settings:

| Variable | Purpose |
|---|---|
| `AZURE_OPENAI_*` | Analysis, WAF, fallback LLM calls |
| `AZURE_FOUNDRY_*` | Terraform generation when configured |
| `OPENAI_API_KEY` | Optional fallback |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | AWS Pricing API and optional HCP workspace vars |
| `GCP_PROJECT_ID` | GCP project context |
| `GCP_API_KEY` | GCP Cloud Billing Catalog API |
| `GCP_SERVICE_ACCOUNT_KEY` | Optional GCP service account credential content/path |
| `HCP_TERRAFORM_TOKEN` / `HCP_ORG_NAME` | Optional HCP speculative plans |

Security rule:

- `.env` credentials are internal runtime configuration.
- They may be used for pricing, HCP, and Terraform runs.
- They must be masked as `xxxxxxxx` anywhere the user can see validation details, logs, or API responses.

---

## API Endpoint Summary

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Backend health/config check |
| `POST` | `/api/analyze` | Diagram image/draw.io -> architecture analysis |
| `POST` | `/api/waf` | Well-Architected review |
| `POST` | `/api/pricing` | Provider API pricing comparison |
| `POST` | `/api/terraform` | Generate Terraform synchronously |
| `POST` | `/api/terraform/stream` | Generate Terraform with SSE progress |
| `POST` | `/api/terraform/validate` | Static validation and score |
| `POST` | `/api/terraform/hcp-plan` | HCP speculative plan only |
| `POST` | `/api/terraform/run` | Real Terraform fmt/init/validate/plan stream |
| `POST` | `/api/terraform/fix` | Fix validation/security findings |
| `POST` | `/api/github` | Push generated files to GitHub |
| `GET` | `/api/docs` | FastAPI Swagger UI |

---

## File Map

```text
archlens/
├── END_TO_END_FLOW.md
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models/schemas.py
│   │   ├── routers/
│   │   │   ├── analyze.py
│   │   │   ├── waf.py
│   │   │   ├── pricing.py
│   │   │   ├── terraform.py
│   │   │   ├── validation.py
│   │   │   └── github.py
│   │   └── services/
│   │       ├── diagram_analyzer.py
│   │       ├── pricing_service.py
│   │       ├── aws_pricing.py
│   │       ├── azure_pricing.py
│   │       ├── gcp_pricing.py
│   │       ├── terraform_service.py
│   │       ├── terraform_runner.py
│   │       ├── validation_service.py
│   │       ├── schema_fixer.py
│   │       ├── schema_fixer_rag.py
│   │       └── rag_service.py
│   ├── chroma_db/
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   └── components/
│   │       ├── DiagramUpload.jsx
│   │       ├── ArchLensParticleBackground.jsx
│   │       ├── AnalysisResult.jsx
│   │       ├── WAFReview.jsx
│   │       ├── PricingComparison.jsx
│   │       ├── TerraformViewer.jsx
│   │       ├── TerraformValidation.jsx
│   │       ├── TerraformRunner.jsx
│   │       └── GithubPush.jsx
│   └── dist/                 # Built frontend copied to /var/www/html for public HTTPS
└── docs/
```

---

## Operational Checklist

After backend changes:

```bash
cd backend
.venv/bin/python -m py_compile app/services/<changed-file>.py
pgrep -f 'uvicorn app.main:app' | xargs -r kill
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
curl -s http://127.0.0.1:8000/api/health
```

After frontend changes:

```bash
cd frontend
npm run build
cd ..
sudo rsync -a --delete frontend/dist/ /var/www/html/
sudo nginx -t
sudo systemctl reload nginx
curl -k -I https://18.215.164.199/
```

Browser verification:

- For Vite dev, open `http://localhost:5173/`.
- For public EC2, open `https://18.215.164.199/`.
- If the public page looks stale, hard refresh with `Ctrl+Shift+R` and verify Nginx is serving the latest `/assets/index-*.js` and `/assets/index-*.css` files.
