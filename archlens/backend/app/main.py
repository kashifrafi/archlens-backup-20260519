from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.config import settings
from app.routers import analyze, waf, pricing, terraform, github, validation

app = FastAPI(
    title="ArchLens API",
    description="Intelligent Architecture Diagram Analyzer with WAF review, pricing comparison and Terraform generation",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
from app.metrics import router as metrics_router
app.include_router(metrics_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze.router, prefix="/api", tags=["Analyze"])
app.include_router(waf.router, prefix="/api", tags=["WAF Review"])
app.include_router(pricing.router, prefix="/api", tags=["Pricing"])
app.include_router(terraform.router, prefix="/api", tags=["Terraform"])
app.include_router(github.router, prefix="/api", tags=["GitHub"])
app.include_router(validation.router, prefix="/api", tags=["Validation"])

# Serve sample .drawio files
SAMPLES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "samples"))
if os.path.isdir(SAMPLES_DIR):
    app.mount("/samples", StaticFiles(directory=SAMPLES_DIR), name="samples")


@app.get("/api/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    azure_configured = bool(settings.azure_openai_endpoint and settings.azure_openai_api_key)
    openai_configured = bool(settings.openai_api_key)
    return {
        "status": "ok",
        "ai_provider": "azure_openai" if azure_configured else ("openai" if openai_configured else "not_configured"),
        "version": "1.0.0",
    }
