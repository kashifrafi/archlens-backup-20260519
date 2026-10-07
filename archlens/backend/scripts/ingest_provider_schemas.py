#!/usr/bin/env python3
"""
Terraform Provider Schema Ingestion Script
==========================================
Fetches every resource's argument schema from the official Terraform Registry
v2 API, parses valid / deprecated / removed arguments from the markdown docs,
and upserts structured documents into a local ChromaDB collection called
'provider_schemas'.

At runtime, schema_fixer_rag.py queries this collection to:
  1. Supply the LLM with authoritative schema context per resource type
  2. Deterministically strip/flag arguments not in the valid set

Usage (from backend/):
    python scripts/ingest_provider_schemas.py
    python scripts/ingest_provider_schemas.py --providers aws
    python scripts/ingest_provider_schemas.py --providers aws,azurerm,google

Cron (installed by scripts/setup_schema_cron.sh):
    0 2 1 * *  cd /path/to/backend && .venv/bin/python scripts/ingest_provider_schemas.py
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Generator, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("schema-ingest")

# ── Config ────────────────────────────────────────────────────────────────────

AZURE_OAI_ENDPOINT = (
    os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT")
    or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
)
AZURE_OAI_KEY = (
    os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY")
    or os.environ.get("AZURE_OPENAI_API_KEY", "")
)
AZURE_OAI_VERSION = os.getenv(
    "AZURE_OPENAI_EMBEDDING_API_VERSION",
    os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
)
EMBED_MODEL    = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
COLLECTION_NAME = "provider_schemas"

REGISTRY_BASE = "https://registry.terraform.io"
BATCH_SIZE    = 20     # embeddings per API call
REQ_DELAY     = 0.15   # seconds between Registry requests (be polite)

HEADERS = {
    "User-Agent": "ArchLens-Schema-Ingestor/1.0",
    "Accept":     "application/json",
}

# Providers: local key → registry namespace/name
PROVIDERS: Dict[str, str] = {
    "aws":     "hashicorp/aws",
    "azurerm": "hashicorp/azurerm",
    "google":  "hashicorp/google",
}


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ResourceSchema:
    provider: str            # "aws"
    resource_type: str       # "aws_autoscaling_group"
    provider_version: str    # "5.90.0"
    doc_text: str            # compact doc for embedding
    valid_args: List[str]         = field(default_factory=list)
    deprecated_args: List[str]    = field(default_factory=list)
    removed_args: List[str]       = field(default_factory=list)


# ── Registry API helpers ───────────────────────────────────────────────────────

def _registry_get(path: str, params: Optional[dict] = None) -> dict:
    url  = REGISTRY_BASE + path
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_latest_version(namespace_name: str) -> str:
    """Return the latest stable version string for a provider."""
    data = _registry_get(f"/v1/providers/{namespace_name}")
    # v1 API may return 'latest_version' or 'version' or derive from 'versions' list
    ver = data.get("latest_version") or data.get("version")
    if not ver:
        versions = data.get("versions", [])
        ver = versions[-1] if versions else "latest"
    return ver


def get_version_id(namespace_name: str, version: str) -> Optional[str]:
    """
    Resolve the numeric provider-version ID required by the v2 docs API.
    Example: hashicorp/aws @ 6.44.0 → "96094"
    """
    try:
        data = _registry_get(
            f"/v2/providers/{namespace_name}",
            params={"include": "provider-versions"},
        )
        for item in data.get("included", []):
            if item.get("type") == "provider-versions":
                if item.get("attributes", {}).get("version") == version:
                    return str(item["id"])
    except Exception as exc:
        log.warning("  get_version_id failed: %s", exc)
    return None


def list_resource_doc_ids(version_id: str) -> List[Tuple[str, str]]:
    """
    Return [(doc_id, slug), ...] for all resource-category docs for a given
    provider-version numeric ID.  Handles Registry pagination automatically.

    The v2 API requires filter[provider-version]=<numeric_id>.  There is no
    pagination metadata in the response — we stop when a page returns fewer
    items than the requested page size.
    """
    PAGE_SIZE = 100
    ids: List[Tuple[str, str]] = []
    page = 1
    while True:
        try:
            data = _registry_get(
                "/v2/provider-docs",
                params={
                    "filter[provider-version]": version_id,
                    "filter[category]":         "resources",
                    "page[size]":               PAGE_SIZE,
                    "page[number]":             page,
                },
            )
        except Exception as exc:
            log.warning("  Listing page %d failed: %s", page, exc)
            break

        items = data.get("data", [])
        for item in items:
            doc_id = str(item["id"])
            slug   = item.get("attributes", {}).get("slug", "")
            if slug:
                ids.append((doc_id, slug))

        # Stop when the page is not full (last page) or empty
        if len(items) < PAGE_SIZE:
            break
        page += 1
        time.sleep(REQ_DELAY)

    return ids


def fetch_doc_content(doc_id: str) -> str:
    """Fetch the full markdown content of a single provider doc entry."""
    try:
        data = _registry_get(f"/v2/provider-docs/{doc_id}")
        return data.get("data", {}).get("attributes", {}).get("content", "")
    except Exception as exc:
        log.warning("    fetch_doc %s failed: %s", doc_id, exc)
        return ""


# ── Markdown parser ────────────────────────────────────────────────────────────

_SECTION_RE    = re.compile(r'^##\s+(.+)$', re.MULTILINE)
_ARG_NAME_RE   = re.compile(r'^\*\s+`(\w+)`', re.MULTILINE)
_DEPRECATED_RE = re.compile(
    r'^\*\s+`(\w+)`[^`\n]*'
    r'(?:deprecated|removed|replaced|no longer|use\s+\S+\s+instead)',
    re.MULTILINE | re.IGNORECASE,
)
_REMOVED_WORDS_RE = re.compile(
    r'^\*\s+`(\w+)`[^`\n]*'
    r'(?:removed in|has been removed|no longer supported|was removed)',
    re.MULTILINE | re.IGNORECASE,
)


def _extract_section(markdown: str, title_fragment: str) -> str:
    sections = list(_SECTION_RE.finditer(markdown))
    for i, m in enumerate(sections):
        if title_fragment.lower() in m.group(1).lower():
            start = m.end()
            end   = sections[i + 1].start() if i + 1 < len(sections) else len(markdown)
            return markdown[start:end]
    return ""


def parse_resource_schema(
    provider: str,
    resource_type: str,
    version: str,
    markdown: str,
) -> ResourceSchema:
    """
    Parse a Registry markdown doc and extract valid / deprecated / removed args.
    Produces a compact text document suitable for embedding.
    """
    arg_section = _extract_section(markdown, "Argument Reference")

    # All argument names in the argument section (includes nested block names)
    valid_args      = list(dict.fromkeys(_ARG_NAME_RE.findall(arg_section)))
    deprecated_args = list(dict.fromkeys(_DEPRECATED_RE.findall(markdown)))
    removed_args    = list(dict.fromkeys(_REMOVED_WORDS_RE.findall(markdown)))

    # Build compact but rich text for embedding
    valid_preview = ", ".join(valid_args[:80]) + ("…" if len(valid_args) > 80 else "")
    dep_str       = ", ".join(deprecated_args) if deprecated_args else "none"
    rem_str       = ", ".join(removed_args)     if removed_args    else "none"

    doc_text = (
        f"Resource: {resource_type}  |  Provider: {provider.upper()} v{version}\n"
        f"\n"
        f"Valid arguments and block types:\n"
        f"  {valid_preview}\n"
        f"\n"
        f"Deprecated arguments (avoid — cause warnings): {dep_str}\n"
        f"Removed arguments (cause Terraform errors if used): {rem_str}\n"
        f"\n"
        f"--- Argument Reference (excerpt) ---\n"
        f"{arg_section[:2000]}"
    )

    return ResourceSchema(
        provider=provider,
        resource_type=resource_type,
        provider_version=version,
        doc_text=doc_text,
        valid_args=valid_args,
        deprecated_args=deprecated_args,
        removed_args=removed_args,
    )


# ── ChromaDB upsert ────────────────────────────────────────────────────────────

def _batches(lst: list, size: int) -> Generator:
    for i in range(0, len(lst), size):
        yield lst[i: i + size]


def upsert_schemas(schemas: List[ResourceSchema], collection, oai: AzureOpenAI) -> int:
    """Embed and upsert all schemas. Returns number upserted."""
    upserted = 0
    for chunk in _batches(schemas, BATCH_SIZE):
        texts = [s.doc_text for s in chunk]
        try:
            embed_resp = oai.embeddings.create(model=EMBED_MODEL, input=texts)
            embeddings = [item.embedding for item in embed_resp.data]
        except Exception as exc:
            log.warning("  Embedding batch failed: %s — skipping batch", exc)
            continue

        # Deterministic ID: sha256 of "provider:resource_type" so re-runs upsert cleanly
        ids = [
            hashlib.sha256(f"{s.provider}:{s.resource_type}".encode()).hexdigest()
            for s in chunk
        ]
        metadatas = [
            {
                "provider":         s.provider,
                "resource_type":    s.resource_type,
                "provider_version": s.provider_version,
                # Stored as comma-separated strings — ChromaDB metadata must be primitives
                "valid_args":       ",".join(s.valid_args),
                "deprecated_args":  ",".join(s.deprecated_args),
                "removed_args":     ",".join(s.removed_args),
            }
            for s in chunk
        ]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        upserted += len(chunk)

    return upserted


# ── Per-provider orchestration ─────────────────────────────────────────────────

def ingest_provider(
    provider_key: str,
    namespace_name: str,
    collection,
    oai: AzureOpenAI,
) -> int:
    log.info("=== %s  (%s) ===", provider_key.upper(), namespace_name)

    # 1. Latest stable version
    try:
        version = get_latest_version(namespace_name)
        log.info("  Latest version: %s", version)
    except Exception as exc:
        log.warning("  Could not resolve version (%s) — using 'latest'", exc)
        version = "latest"

    # 2. Resolve the numeric version ID required by the v2 docs API
    version_id = get_version_id(namespace_name, version)
    if not version_id:
        log.error(
            "  Could not resolve numeric version ID for %s @ %s — aborting.",
            namespace_name, version,
        )
        return 0
    log.info("  Numeric version ID: %s", version_id)

    # 3. All resource doc IDs
    log.info("  Listing resource docs …")
    doc_ids = list_resource_doc_ids(version_id)
    log.info("  Found %d resource docs", len(doc_ids))
    if not doc_ids:
        log.warning("  No docs found — skipping")
        return 0

    # 4. Fetch + parse
    # The Registry slug is the resource name WITHOUT the provider prefix
    # (e.g. "s3_bucket" for "aws_s3_bucket").  Prepend provider prefix so the
    # stored resource_type matches HCL resource block names.
    schemas: List[ResourceSchema] = []
    for i, (doc_id, slug) in enumerate(doc_ids, 1):
        if i % 50 == 0:
            log.info("  Parsing: %d / %d …", i, len(doc_ids))
        markdown = fetch_doc_content(doc_id)
        time.sleep(REQ_DELAY)
        if not markdown.strip():
            continue
        resource_type = f"{provider_key}_{slug}"
        schema = parse_resource_schema(provider_key, resource_type, version, markdown)
        if not schema.valid_args:
            # No argument section found — likely a guide page, not a resource
            continue
        schemas.append(schema)

    log.info("  Parsed %d valid resource schemas", len(schemas))

    # 4. Embed + upsert
    log.info("  Embedding and upserting into ChromaDB …")
    upserted = upsert_schemas(schemas, collection, oai)
    log.info("  Done: %d documents upserted for %s", upserted, provider_key.upper())
    return upserted


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Terraform provider schemas into ChromaDB"
    )
    parser.add_argument(
        "--providers",
        default="aws,azurerm,google",
        help="Comma-separated provider keys (default: aws,azurerm,google)",
    )
    args = parser.parse_args()
    selected = {k.strip() for k in args.providers.split(",")}

    import chromadb
    import warnings
    warnings.filterwarnings("ignore")

    db_path = os.path.abspath(CHROMA_DB_PATH)
    log.info("ChromaDB path: %s", db_path)
    chroma     = chromadb.PersistentClient(path=db_path)
    collection = chroma.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    existing = collection.count()
    log.info("Collection '%s' ready — existing docs: %d", COLLECTION_NAME, existing)

    if not AZURE_OAI_ENDPOINT or not AZURE_OAI_KEY:
        log.error(
            "Azure OpenAI credentials not set. "
            "Export AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY."
        )
        sys.exit(1)

    oai = AzureOpenAI(
        azure_endpoint=AZURE_OAI_ENDPOINT,
        api_key=AZURE_OAI_KEY,
        api_version=AZURE_OAI_VERSION,
    )
    log.info("Azure OpenAI ready (model: %s)", EMBED_MODEL)

    total = 0
    for key, namespace in PROVIDERS.items():
        if key not in selected:
            continue
        try:
            total += ingest_provider(key, namespace, collection, oai)
        except Exception as exc:
            log.error("Failed to ingest %s: %s", key, exc, exc_info=True)

    log.info(
        "=== Ingestion complete. Upserted: %d. Collection total: %d ===",
        total, collection.count(),
    )


if __name__ == "__main__":
    main()
