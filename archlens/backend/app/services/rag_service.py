"""
RAG (Retrieval-Augmented Generation) service for ArchLens.

Uses ChromaDB (local persistent vector store) + Azure OpenAI embeddings
to retrieve relevant WAF documentation chunks when analysing architecture
diagrams. No external SaaS vector DB required - everything runs on disk.
"""
import logging
import os

from openai import AzureOpenAI, OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_chroma_collection = None
_embedding_client = None


def _get_embedding_client():
    global _embedding_client
    if _embedding_client is None:
        # Prefer the dedicated embedding resource; fall back to the GPT resource
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
            raise ValueError("No AI API credentials configured for embeddings.")
    return _embedding_client


def _get_chroma_collection():
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection
    try:
        import chromadb
        db_path = os.path.abspath(settings.chroma_db_path)
        client = chromadb.PersistentClient(path=db_path)
        _chroma_collection = client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        count = _chroma_collection.count()
        if count == 0:
            logger.warning("ChromaDB collection empty. Run scripts/ingest_waf_docs.py first.")
        else:
            logger.info("ChromaDB loaded: %d chunks.", count)
    except Exception as exc:
        logger.error("Failed to open ChromaDB: %s", exc)
        return None
    return _chroma_collection


def embed_text(text: str) -> list:
    client = _get_embedding_client()
    response = client.embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=text,
    )
    return response.data[0].embedding


def retrieve_waf_context(query: str, provider: str, top_k: int = 6) -> str:
    collection = _get_chroma_collection()
    if collection is None or collection.count() == 0:
        return ""
    try:
        query_embedding = embed_text(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"provider": provider},
            include=["documents"],
        )
        chunks = results.get("documents", [[]])[0]
        return "\n\n---\n\n".join(chunks) if chunks else ""
    except Exception as exc:
        logger.error("ChromaDB query failed: %s", exc)
        return ""
