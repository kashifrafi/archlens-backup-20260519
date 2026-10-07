# ArchLens - High Level Design (HLD)

## 1. Executive Summary

**ArchLens** is an AI-powered cloud infrastructure platform that analyzes architecture diagrams and automatically generates production-ready Infrastructure as Code (Terraform). The platform provides comprehensive architecture analysis, Well-Architected Framework (WAF) reviews, cost estimation, and validated Terraform code with real-time execution and auto-remediation capabilities.

### Key Capabilities
- **AI-Powered Diagram Analysis**: Automatically identifies cloud components and architecture patterns
- **Multi-Cloud Support**: AWS, Azure, and GCP infrastructure generation
- **Terraform Generation**: Production-ready modular Terraform code with local modules
- **Real-Time Validation**: Automated terraform init/validate/plan with AI-powered error fixing
- **Cost Estimation**: Multi-cloud pricing comparison with detailed breakdowns
- **WAF Review**: Security and compliance analysis across 6 pillars

---

## 2. System Architecture

### 2.1 High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            CLIENT LAYER                                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │          React 18 Frontend (Vite + Tailwind CSS)                 │  │
│  │  • Diagram Upload  • Real-time SSE Streaming  • Code Viewer      │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                            HTTP/SSE (Port 5173)
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                                │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │              FastAPI Backend (Python 3.10)                       │  │
│  │  • REST API Endpoints  • Server-Sent Events  • Async Processing  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         SERVICE LAYER                                    │
│  ┌────────────────┬────────────────┬────────────────┬───────────────┐  │
│  │  Analyzer      │  Terraform     │  Pricing       │  WAF Review   │  │
│  │  Service       │  Service       │  Service       │  Service      │  │
│  └────────────────┴────────────────┴────────────────┴───────────────┘  │
│  ┌────────────────┬────────────────┬────────────────┬───────────────┐  │
│  │  Schema Fixer  │  Runner        │  GitHub Push   │  Context      │  │
│  │  (RAG)         │  Service       │  Service       │  Helper       │  │
│  └────────────────┴────────────────┴────────────────┴───────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         AI LAYER (DUAL MODEL)                            │
│  ┌──────────────────────────────┬────────────────────────────────────┐ │
│  │  Analysis LLM (Cloud AI Platform)     │  Code Generation LLM (Cloud AI Platform)  │ │
│  │  • Diagram Analysis          │  • Terraform Code Generation       │ │
│  │  • WAF Review                │  • Error Remediation               │ │
│  │  • Pricing Estimation        │  • Schema Validation               │ │
│  └──────────────────────────────┴────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         INFRASTRUCTURE LAYER                             │
│  ┌──────────────────┬──────────────────┬────────────────────────────┐  │
│  │  Terraform CLI   │  ChromaDB (RAG)  │  Plugin Cache              │  │
│  │  v1.15.3         │  Schema Store    │  ~/.archlens/              │  │
│  └──────────────────┴──────────────────┴────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Overview

### 3.1 Frontend Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **DiagramUpload** | React 18 | Image upload and preview |
| **AnalysisView** | React + SSE | Real-time architecture analysis |
| **TerraformViewer** | React + Prism | Syntax-highlighted code display |
| **TerraformRunner** | React + SSE | Real-time terraform execution |
| **PricingComparison** | React | Multi-cloud cost comparison |
| **WAFReview** | React | Security compliance scoring |
| **GithubPush** | React + Axios | Repository integration |

### 3.2 Backend Services

| Service | Responsibility | Technology |
|---------|---------------|------------|
| **analyzer_service** | Diagram analysis, component detection | Analysis LLM |
| **terraform_service** | IaC generation, streaming, formatting | Code Generation LLM |
| **terraform_runner** | Real-time execution (fmt/init/validate/plan) | Subprocess + SSE |
| **pricing_service** | Cost estimation, multi-cloud comparison | Analysis LLM |
| **waf_service** | Security review, 6-pillar scoring | Analysis LLM |
| **schema_fixer** | Provider v5/v6 schema fixes | Regex + RAG |
| **schema_fixer_rag** | ChromaDB-based schema validation | Vector DB |
| **github_service** | Repository creation, file push | GitHub API |

### 3.3 AI Model Architecture

| Model | Provider | Use Cases | Key Features |
|-------|----------|-----------|--------------|
| **Analysis LLM** | Cloud AI Platform Standard | Analysis, pricing, WAF | Standard chat.completions API |
| **Code Generation LLM** | Cloud AI Platform | Terraform generation, fixes | Responses API, max_output_tokens |

---

## 4. Technology Stack

### 4.1 Frontend Stack
```
- React 18.2.0
- Vite 5.4.21 (Dev Server + HMR)
- Tailwind CSS 3.x
- Axios (HTTP client)
- Prism (Syntax highlighting)
- react-hot-toast (Notifications)
- JSZip 3.x (ZIP file generation)
```

### 4.2 Backend Stack
```
- Python 3.10
- FastAPI 0.100+
- Uvicorn (ASGI server)
- Pydantic (Data validation)
- AsyncIO (Async processing)
- requests (HTTP client)
- openai (Cloud AI Platform SDK)
- ChromaDB (Vector database)
```

### 4.3 Infrastructure
```
- Terraform v1.15.3
- Provider Plugin Cache (~/.archlens/tf-plugin-cache)
- Module Archive (~/.archlens/module-archive)
- Base Lockfile (base.lock.hcl)
```

---

## 5. Data Flow Architecture

### 5.1 End-to-End Flow

```
User Upload → Analysis → Generation → Validation → Deployment
     │            │           │            │            │
     │            ▼           │            │            │
     │      Component         │            │            │
     │      Detection         │            │            │
     │            │           │            │            │
     │            ├──→ WAF Review          │            │
     │            │                        │            │
     │            └──→ Cost Estimate       │            │
     │                        │            │            │
     │                        ▼            │            │
     │              Terraform Generation   │            │
     │                   (Code Generation LLM)   │            │
     │                        │            │            │
     │                        └──→ Schema Fixes         │
     │                                     │            │
     │                                     ▼            │
     │                          fmt → init → validate   │
     │                                     │            │
     │                                     ├─[Pass]─→ plan
     │                                     │            │
     │                                     └─[Fail]──→ AI Fix
     │                                           │      │
     │                                     (Max 3 attempts)
     │                                                  │
     └──────────────────────────────────────────→ GitHub Push
```

---

## 6. Security Architecture

### 6.1 Authentication & Authorization
- API Key-based authentication for AI models
- GitHub Personal Access Token (PAT) for repository operations
- No persistent storage of credentials
- Environment variable configuration

### 6.2 Data Security
- All cloud credentials transmitted via HTTPS only
- In-memory processing (no disk persistence)
- Terraform state files stored locally (user-controlled)
- Temporary directories cleaned after execution

### 6.3 API Security
- CORS configuration for frontend origin
- Input validation via Pydantic models
- Rate limiting on AI API calls
- Timeout controls on long-running operations

---

## 7. Scalability & Performance

### 7.1 Performance Optimizations

| Optimization | Impact |
|-------------|--------|
| **Plugin Cache** | Avoids re-downloading providers (saves 30-60s per init) |
| **Module Archive** | Reuses module sources (saves 10-20s per init) |
| **Base Lockfile** | Pre-locked provider versions |
| **Async Processing** | Non-blocking AI calls and subprocess execution |
| **SSE Streaming** | Real-time progress updates, better UX |
| **Temperature 0.3** | Faster, more deterministic AI responses |

### 7.2 Scalability Considerations
- Stateless backend design (horizontal scaling ready)
- Async FastAPI for high concurrency
- Subprocess isolation for terraform execution
- Vector DB caching for schema lookups

---

## 8. Deployment Architecture

### 8.1 Current Setup
```
Development Environment:
- Backend: Uvicorn --reload on port 8000
- Frontend: Vite dev server on port 5173
- Virtual Environment: .venv (Python 3.10)
- Node Modules: npm dependencies
```

### 8.2 Production Considerations
- Containerization (Docker/Kubernetes)
- Load balancing for backend instances
- CDN for frontend static assets
- Persistent plugin cache volume
- Centralized logging and monitoring

---

## 9. Integration Points

### 9.1 External Services

| Service | Purpose | Protocol |
|---------|---------|----------|
| **Cloud AI Platform** | Analysis LLM analysis | HTTPS REST |
| **Cloud AI Platform** | Code Generation LLM generation | HTTPS Responses API |
| **GitHub API** | Repository management | HTTPS REST + PAT |
| **ChromaDB** | Schema vector store | Local/Embedded |

### 9.2 Internal APIs

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/analyze` | POST | Diagram analysis |
| `/api/waf-review` | POST | WAF compliance review |
| `/api/pricing` | POST | Cost estimation |
| `/api/terraform/stream` | POST | Terraform generation (SSE) |
| `/api/terraform/run` | POST | Terraform execution (SSE) |
| `/api/github/push` | POST | Push to GitHub |

---

## 10. Disaster Recovery & Reliability

### 10.1 Error Handling
- AI API timeout controls (180s for generation)
- Automatic retry on transient failures
- Fallback to original files on fix failures
- Manual fix mode when AI exhausts retries

### 10.2 Data Backup
- User-uploaded diagrams (temporary, not persisted)
- Generated Terraform files (downloadable as ZIP)
- GitHub push creates permanent backup

---

## 11. Future Enhancements

### 11.1 Planned Features
- Multi-diagram project support
- Terraform state management
- CI/CD pipeline integration
- Custom module library
- Team collaboration features
- Advanced cost optimization recommendations

### 11.2 Technical Debt
- ChromaDB initialization failures (needs fix)
- Model name references cleanup
- Enhanced cache invalidation strategy
- Comprehensive error recovery tests

---

## 12. Compliance & Standards

### 12.1 Terraform Standards
- HashiCorp Configuration Language (HCL) 2.0
- Provider version constraints (required_providers)
- Module-based architecture
- Variable validation and defaults
- Output documentation

### 12.2 Cloud Provider Standards
- AWS Provider v5.x
- Azure Provider (azurerm) v3.x
- GCP Provider v5.x

---

## Document Version
- **Version**: 1.0
- **Last Updated**: May 19, 2026
- **Author**: ArchLens Development Team
