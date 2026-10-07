"""
Module Schema RAG Service
==========================
Runtime service that queries the 'module_schemas' ChromaDB collection
(populated by scripts/ingest_module_schemas.py) to supply authoritative
module input/output schemas to the LLM prompt.

Usage:
    from app.services.module_schema_rag import get_module_context_for_cloud

    context = get_module_context_for_cloud("aws")   # returns formatted string

Degrades gracefully if the collection is empty or ChromaDB is unavailable.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_module_collection = None
_embedding_client  = None


def _get_embedding_client():
    global _embedding_client
    if _embedding_client is not None:
        return _embedding_client
    try:
        from openai import AzureOpenAI, OpenAI

        endpoint = settings.azure_openai_embedding_endpoint or settings.azure_openai_endpoint
        api_key  = settings.azure_openai_embedding_api_key  or settings.azure_openai_api_key
        api_ver  = settings.azure_openai_embedding_api_version

        if endpoint and api_key:
            _embedding_client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_ver,
            )
        elif settings.openai_api_key:
            _embedding_client = OpenAI(api_key=settings.openai_api_key)
        else:
            logger.warning("module_schema_rag: No embedding credentials configured; RAG disabled.")
            return None
        return _embedding_client
    except Exception as exc:
        logger.warning("module_schema_rag: Could not create embedding client: %s", exc)
        return None


def _get_module_collection():
    global _module_collection
    if _module_collection is not None:
        return _module_collection
    try:
        import chromadb
        chroma_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")
        )
        # Prefer env override
        chroma_path = os.environ.get("CHROMA_DB_PATH", chroma_path)
        client = chromadb.PersistentClient(path=chroma_path)
        _module_collection = client.get_or_create_collection(
            name=settings.module_schemas_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        count = _module_collection.count()
        if count == 0:
            logger.warning(
                "module_schema_rag: Collection '%s' is empty. "
                "Run scripts/ingest_module_schemas.py to populate it.",
                settings.module_schemas_collection_name,
            )
        else:
            logger.info(
                "module_schema_rag: Loaded collection '%s' with %d documents.",
                settings.module_schemas_collection_name,
                count,
            )
        return _module_collection
    except Exception as exc:
        logger.warning("module_schema_rag: Could not open ChromaDB collection: %s", exc)
        return None


def _embed(text: str) -> Optional[List[float]]:
    client = _get_embedding_client()
    if client is None:
        return None
    try:
        resp = client.embeddings.create(
            model=settings.azure_openai_embedding_deployment,
            input=[text],
        )
        return resp.data[0].embedding
    except Exception as exc:
        logger.warning("module_schema_rag: Embedding failed: %s", exc)
        return None


def get_module_context_for_cloud(cloud: str, top_k: int = 15) -> str:
    """
    Return a formatted string with module schemas for the given cloud provider.

    Tries two strategies:
    1. Metadata filter: get ALL documents where provider == cloud (fast, exact)
    2. Semantic search fallback if metadata filter returns nothing

    Args:
        cloud: "aws" | "azure" | "gcp"
        top_k: max number of module docs to retrieve (semantic search path only)

    Returns:
        Formatted text block, or "" if collection is empty / unavailable.
    """
    collection = _get_module_collection()
    if collection is None:
        return ""

    try:
        count = collection.count()
        if count == 0:
            return ""

        # Strategy 1: metadata filter — get every module for this cloud
        try:
            result = collection.get(
                where={"provider": cloud},
                include=["documents", "metadatas"],
            )
            docs = result.get("documents") or []
            metas = result.get("metadatas") or []
        except Exception as exc:
            logger.debug("module_schema_rag: metadata filter failed (%s), falling back to semantic", exc)
            docs = []
            metas = []

        # Strategy 2: semantic search fallback
        if not docs:
            query = f"{cloud} terraform module inputs outputs required optional"
            embedding = _embed(query)
            if embedding:
                result = collection.query(
                    query_embeddings=[embedding],
                    n_results=min(top_k, count),
                    where={"provider": cloud} if count >= 2 else None,
                    include=["documents", "metadatas"],
                )
                docs  = (result.get("documents") or [[]])[0]
                metas = (result.get("metadatas") or [[]])[0]

        if not docs:
            return ""

        return _format_module_context(docs, metas, cloud)

    except Exception as exc:
        logger.warning("module_schema_rag: get_module_context_for_cloud failed: %s", exc)
        return ""


def get_module_context_for_sources(sources: List[str]) -> str:
    """
    Return schemas for specific module sources (e.g. ["terraform-aws-modules/vpc/aws"]).
    Uses metadata filter by 'source' field.

    Args:
        sources: list of "namespace/name/provider" strings

    Returns:
        Formatted text block.
    """
    collection = _get_module_collection()
    if collection is None or not sources:
        return ""

    try:
        all_docs: List[str] = []
        all_metas: List[dict] = []
        for source in sources:
            try:
                result = collection.get(
                    where={"source": source},
                    include=["documents", "metadatas"],
                )
                d = result.get("documents") or []
                m = result.get("metadatas") or []
                all_docs.extend(d)
                all_metas.extend(m)
            except Exception as exc:
                logger.debug("module_schema_rag: source lookup failed for %s: %s", source, exc)

        if not all_docs:
            return ""
        return _format_module_context(all_docs, all_metas, cloud="")
    except Exception as exc:
        logger.warning("module_schema_rag: get_module_context_for_sources failed: %s", exc)
        return ""


def _format_module_context(docs: List[str], metas: List[dict], cloud: str) -> str:
    """
    Format a list of module schema documents into a prompt-ready string block.
    """
    if not docs:
        return ""

    header_map = {
        "aws":   "AWS Official Modules (terraform-aws-modules)",
        "azure": "Azure Verified Modules / AVM",
        "gcp":   "GCP Official Modules (terraform-google-modules)",
    }
    header = header_map.get(cloud, "Official Terraform Module Schemas")

    lines = [
        f"=== MODULE INPUT SCHEMAS: {header} ===",
        "CRITICAL RULES:",
        "  1. ONLY use input names listed under REQUIRED INPUTS and OPTIONAL INPUTS.",
        "  2. NEVER use any input listed under DEPRECATED INPUTS.",
        "  3. All REQUIRED INPUTS must be provided — they have no default.",
        "  4. Reference outputs using the exact names listed under OUTPUTS.",
        "",
    ]

    for doc, meta in zip(docs, metas):
        source = meta.get("source", "") if meta else ""
        if source:
            lines.append(f"{'─' * 60}")
        lines.append(doc)
        lines.append("")

    lines.append("=== END MODULE SCHEMAS ===")
    return "\n".join(lines)
