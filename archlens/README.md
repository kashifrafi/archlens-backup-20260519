# ArchLens — Intelligent Architecture Diagram Analyzer

Upload any cloud architecture diagram → get instant WAF review (AWS · Azure · GCP), pricing comparison, and Terraform generation.

## Features

| Feature | Description |
|---|---|
| **Diagram Analysis** | GPT-4o Vision extracts all components with cloud service mappings |
| **WAF Review** | Full Well-Architected Framework assessment (all 3 clouds, scored per pillar) |
| **Pricing Comparison** | Side-by-side monthly cost estimates with per-service breakdown |
| **Terraform Generation** | Production-ready HCL code (main.tf, variables.tf, outputs.tf, provider.tf) |

## Quick Start

### 1. Configure API Keys

```bash
cp backend/.env.example backend/.env
# Edit backend/.env and add:
#   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
#   AZURE_OPENAI_API_KEY=your-key
# OR
#   OPENAI_API_KEY=sk-...
```

### 2. Run (single command)

```bash
chmod +x start.sh
./start.sh
```

Open **http://localhost:5173** in your browser.

### Manual Start (two terminals)

**Terminal 1 — Backend:**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## Architecture

```
archlens/
├── backend/                 # FastAPI Python backend
│   ├── app/
│   │   ├── main.py          # App entrypoint + CORS
│   │   ├── config.py        # Settings (Azure OpenAI / OpenAI)
│   │   ├── routers/         # API routes: analyze, waf, pricing, terraform
│   │   ├── services/        # Core AI services
│   │   └── models/          # Pydantic schemas
│   ├── requirements.txt
│   └── .env.example
├── frontend/                # React + Vite + Tailwind
│   └── src/
│       ├── App.jsx          # Step-wizard shell
│       └── components/      # DiagramUpload, AnalysisResult, WAFReview, PricingComparison, TerraformViewer
└── start.sh                 # One-command dev launcher
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/analyze` | Analyze diagram image (base64) |
| POST | `/api/waf-review` | WAF review for AWS/Azure/GCP |
| POST | `/api/pricing` | Pricing comparison across all clouds |
| POST | `/api/terraform` | Generate Terraform for chosen cloud |
| GET | `/api/health` | Health + AI provider status |
| GET | `/api/docs` | Interactive Swagger UI |
