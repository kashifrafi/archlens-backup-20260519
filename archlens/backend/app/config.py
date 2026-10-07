from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    # Azure OpenAI — GPT-4.1 resource (for analysis, WAF, pricing)
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_deployment: str = "gpt-4.1"
    azure_openai_api_version: str = "2024-05-01-preview"

    # Azure AI Foundry — GPT-5.3-codex resource (Responses API - for Terraform generation)
    azure_foundry_endpoint: Optional[str] = None
    azure_foundry_api_key: Optional[str] = None
    azure_foundry_deployment: str = "gpt-5.3-codex"
    azure_foundry_api_version: str = "2025-04-01-preview"

    # Azure OpenAI — Embedding resource (separate Foundry deployment)
    azure_openai_embedding_endpoint: Optional[str] = None
    azure_openai_embedding_api_key: Optional[str] = None
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_embedding_api_version: str = "2024-05-01-preview"

    # OpenAI fallback
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"

    # Pinecone kept for reference but replaced by ChromaDB locally
    pinecone_api_key: Optional[str] = None
    pinecone_index_name: str = "archlens-waf-docs"
    pinecone_index_host: Optional[str] = None

    # ChromaDB (local persistent vector store)
    chroma_db_path: str = "./chroma_db"
    chroma_collection_name: str = "waf_docs"
    provider_schemas_collection_name: str = "provider_schemas"
    module_schemas_collection_name: str = "module_schemas"

    # App settings
    max_file_size_mb: int = 20
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

    # HCP Terraform (speculative plan validation)
    hcp_terraform_token: Optional[str] = None
    hcp_org_name: Optional[str] = None
    hcp_workspace: str = "archlens-validator"
    hcp_project: Optional[str] = None

    # AWS credentials (for AWS Pricing API)
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-east-1"

    # GCP credentials (for GCP Pricing API)
    gcp_project_id: Optional[str] = None
    gcp_api_key: Optional[str] = None
    gcp_service_account_key: Optional[str] = None

    # Pricing cache settings
    pricing_cache_ttl_hours: int = 24

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
