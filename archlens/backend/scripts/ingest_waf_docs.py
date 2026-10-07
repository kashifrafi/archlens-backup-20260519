#!/usr/bin/env python3
"""
WAF Documentation Ingestion Script
Crawls official WAF docs, chunks them, embeds with Azure OpenAI,
and stores in ChromaDB (local persistent vector store).

Usage (from backend/):
    python scripts/ingest_waf_docs.py
"""
import hashlib, logging, os, sys, time
from dataclasses import dataclass
from typing import Generator, List

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("ingest")

# Dedicated embedding resource takes priority; fall back to the GPT resource
AZURE_OAI_ENDPOINT = os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT") or os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OAI_KEY      = os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY")  or os.environ["AZURE_OPENAI_API_KEY"]
AZURE_OAI_VERSION  = os.getenv("AZURE_OPENAI_EMBEDDING_API_VERSION", os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"))
EMBED_MODEL        = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
CHROMA_DB_PATH     = os.getenv("CHROMA_DB_PATH", "./chroma_db")
COLLECTION_NAME    = "waf_docs"

CHUNK_SIZE    = 400
CHUNK_OVERLAP = 80
BATCH_SIZE    = 50

HEADERS = {"User-Agent": "ArchLens-WAF-Ingestor/1.0"}

WAF_SOURCES = {
    "aws": [
        "https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html",
        "https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html",
        "https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html",
        "https://docs.aws.amazon.com/wellarchitected/latest/performance-efficiency-pillar/welcome.html",
        "https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html",
        "https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html",
    ],
    "azure": [
        "https://learn.microsoft.com/en-us/azure/well-architected/",
        "https://learn.microsoft.com/en-us/azure/well-architected/reliability/overview",
        "https://learn.microsoft.com/en-us/azure/well-architected/security/overview",
        "https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/overview",
        "https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/overview",
        "https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/overview",
    ],
    "gcp": [
        "https://cloud.google.com/architecture/framework",
        "https://cloud.google.com/architecture/framework/system-design",
        "https://cloud.google.com/architecture/framework/operational-excellence",
        "https://cloud.google.com/architecture/framework/security",
        "https://cloud.google.com/architecture/framework/reliability",
        "https://cloud.google.com/architecture/framework/cost-optimization",
    ],
}


@dataclass
class Chunk:
    id: str
    text: str
    provider: str
    source_url: str


def fetch_page_text(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, verify=False)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("  Could not fetch %s: %s", url, exc)
        return ""
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["nav", "footer", "header", "script", "style", "aside"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.find("div", {"id": "main-content"}) or soup.body
    return main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)


def split_into_chunks(text: str, source_url: str, provider: str) -> List[Chunk]:
    words = text.split()
    chunks: List[Chunk] = []
    start = 0
    while start < len(words):
        end = min(start + CHUNK_SIZE, len(words))
        chunk_text = " ".join(words[start:end])
        chunk_id = hashlib.md5(f"{provider}::{source_url}::{start}".encode()).hexdigest()
        chunks.append(Chunk(id=chunk_id, text=chunk_text, provider=provider, source_url=source_url))
        if end == len(words):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def batch(lst: list, size: int) -> Generator:
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def main():
    import chromadb
    import warnings
    warnings.filterwarnings("ignore")

    db_path = os.path.abspath(CHROMA_DB_PATH)
    log.info("Opening ChromaDB at: %s", db_path)
    chroma = chromadb.PersistentClient(path=db_path)
    collection = chroma.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    log.info("Collection '%s' ready (existing docs: %d)", COLLECTION_NAME, collection.count())

    oai = AzureOpenAI(
        azure_endpoint=AZURE_OAI_ENDPOINT,
        api_key=AZURE_OAI_KEY,
        api_version=AZURE_OAI_VERSION,
    )
    log.info("Azure OpenAI connected (embedding model: %s)", EMBED_MODEL)

    total_upserted = 0

    for provider, urls in WAF_SOURCES.items():
        log.info("=== Provider: %s (%d pages) ===", provider.upper(), len(urls))
        all_chunks: List[Chunk] = []

        for url in urls:
            log.info("  Fetching: %s", url)
            text = fetch_page_text(url)
            if not text.strip():
                log.warning("  Empty content, skipping.")
                continue
            chunks = split_into_chunks(text, url, provider)
            log.info("  -> %d chunks", len(chunks))
            all_chunks.extend(chunks)
            time.sleep(0.5)

        if not all_chunks:
            log.warning("No chunks for %s, skipping.", provider)
            continue

        log.info("Embedding %d chunks for %s ...", len(all_chunks), provider)

        for chunk_batch in batch(all_chunks, BATCH_SIZE):
            texts = [c.text for c in chunk_batch]
            embed_resp = oai.embeddings.create(model=EMBED_MODEL, input=texts)
            embeddings = [item.embedding for item in embed_resp.data]

            collection.upsert(
                ids=[c.id for c in chunk_batch],
                embeddings=embeddings,
                documents=texts,
                metadatas=[{"provider": c.provider, "source_url": c.source_url} for c in chunk_batch],
            )
            total_upserted += len(chunk_batch)
            log.info("  Upserted %d (total: %d)", len(chunk_batch), total_upserted)
            time.sleep(0.1)

    log.info("Ingestion complete. Total chunks: %d", total_upserted)


if __name__ == "__main__":
    main()
