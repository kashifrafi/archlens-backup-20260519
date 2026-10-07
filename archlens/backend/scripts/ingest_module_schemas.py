"""
Module Schema Ingestion Script
===============================
Fetches official Terraform module schemas from the Terraform Registry v2 API
and ingest them into ChromaDB (collection: 'module_schemas').

Covers:
  - AWS:   terraform-aws-modules/*
  - Azure: Azure/avm-res-* (Azure Verified Modules)
  - GCP:   terraform-google-modules/*

Run:
  cd backend && source .venv/bin/activate
  python scripts/ingest_module_schemas.py              # all providers
  python scripts/ingest_module_schemas.py --provider aws
  python scripts/ingest_module_schemas.py --provider azure
  python scripts/ingest_module_schemas.py --provider gcp
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import requests

# ── Make sure we can import from backend/app ─────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("module-ingest")

# ── Configuration ─────────────────────────────────────────────────────────────
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
COLLECTION_NAME = "module_schemas"

REGISTRY_BASE = "https://registry.terraform.io"
BATCH_SIZE    = 10   # embeddings per API call (modules have long docs)
REQ_DELAY     = 0.3  # polite delay between Registry requests

HEADERS = {
    "User-Agent": "ArchLens-Module-Schema-Ingestor/1.0",
    "Accept":     "application/json",
}

# ── Modules to Ingest ─────────────────────────────────────────────────────────
# Format:  (namespace, module_name, provider)
# source = "{namespace}/{module_name}/{provider}"

MODULES_TO_INGEST: Dict[str, List[Tuple[str, str, str]]] = {
    "aws": [
        ("terraform-aws-modules", "vpc",            "aws"),
        ("terraform-aws-modules", "ec2-instance",   "aws"),
        ("terraform-aws-modules", "autoscaling",    "aws"),
        ("terraform-aws-modules", "alb",            "aws"),
        ("terraform-aws-modules", "rds",            "aws"),
        ("terraform-aws-modules", "rds-aurora",     "aws"),
        ("terraform-aws-modules", "elasticache",    "aws"),
        ("terraform-aws-modules", "s3-bucket",      "aws"),
        ("terraform-aws-modules", "ecs",            "aws"),
        ("terraform-aws-modules", "eks",            "aws"),
        ("terraform-aws-modules", "lambda",         "aws"),
        ("terraform-aws-modules", "security-group", "aws"),
    ],
    "azure": [
        ("Azure", "avm-res-compute-virtualmachine",                 "azurerm"),
        ("Azure", "avm-res-network-virtualnetwork",                 "azurerm"),
        ("Azure", "avm-res-containerservice-managedcluster",        "azurerm"),
        ("Azure", "avm-res-storage-storageaccount",                 "azurerm"),
        ("Azure", "avm-res-keyvault-vault",                         "azurerm"),
        ("Azure", "avm-res-sql-server",                             "azurerm"),
        ("Azure", "avm-res-web-site",                               "azurerm"),
        ("Azure", "avm-res-containerregistry-registry",             "azurerm"),
        ("Azure", "avm-res-network-loadbalancer",                   "azurerm"),
        ("Azure", "avm-res-network-publicipaddress",                "azurerm"),
    ],
    "gcp": [
        ("terraform-google-modules", "network",            "google"),
        ("terraform-google-modules", "vm",                 "google"),
        ("terraform-google-modules", "kubernetes-engine",  "google"),
        ("terraform-google-modules", "sql-db",             "google"),
        ("terraform-google-modules", "cloud-storage",      "google"),
        ("terraform-google-modules", "lb-http",            "google"),
    ],
}

# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ModuleInput:
    name: str
    description: str = ""
    type: str = "string"
    required: bool = False
    deprecated: bool = False
    replacement: str = ""   # what to use instead if deprecated


@dataclass
class ModuleOutput:
    name: str
    description: str = ""


@dataclass
class ModuleSchema:
    namespace: str
    name: str
    provider: str
    version: str
    source: str                             # "namespace/name/provider"
    required_inputs: List[ModuleInput]      = field(default_factory=list)
    optional_inputs: List[ModuleInput]      = field(default_factory=list)
    deprecated_inputs: List[ModuleInput]    = field(default_factory=list)
    outputs: List[ModuleOutput]             = field(default_factory=list)
    description: str = ""
    readme_example: str = ""


# ── Registry API helpers ──────────────────────────────────────────────────────

def _registry_get(path: str, params: Optional[dict] = None) -> dict:
    url  = REGISTRY_BASE + path
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_latest_module_version(namespace: str, name: str, provider: str) -> str:
    """Return the latest version string for a module."""
    try:
        data = _registry_get(f"/v1/modules/{namespace}/{name}/{provider}")
        ver = data.get("version") or data.get("latest_version")
        if not ver:
            versions = data.get("versions", [])
            if versions:
                # Registry sorts latest first
                ver = versions[0].get("version", "latest")
        return ver or "latest"
    except Exception as exc:
        log.warning("Could not get latest version for %s/%s/%s: %s", namespace, name, provider, exc)
        return "latest"


def get_module_inputs_outputs(namespace: str, name: str, provider: str, version: str) -> Tuple[List[ModuleInput], List[ModuleInput], List[ModuleInput], List[ModuleOutput], str]:
    """
    Fetch module inputs and outputs from the Registry v1 API.
    Returns (required_inputs, optional_inputs, deprecated_inputs, outputs, description).
    """
    required: List[ModuleInput] = []
    optional: List[ModuleInput] = []
    deprecated_list: List[ModuleInput] = []
    outputs_list: List[ModuleOutput] = []
    description = ""

    try:
        ver_path = f"/v1/modules/{namespace}/{name}/{provider}/{version}"
        data = _registry_get(ver_path)

        description = data.get("description", "") or data.get("source", "")

        # Navigate to root module inputs if present
        root = data.get("root", {}) or {}
        inputs = root.get("inputs", []) or data.get("inputs", []) or []
        raw_outputs = root.get("outputs", []) or data.get("outputs", []) or []

        for inp in inputs:
            inp_name = inp.get("name", "")
            if not inp_name:
                continue
            desc = inp.get("description", "")
            typ  = inp.get("type", "string")
            # required if no default is set (default is None or missing)
            has_default = "default" in inp and inp["default"] is not None
            is_required = not has_default

            # Detect deprecation from description text
            desc_lower = (desc or "").lower()
            is_deprecated = any(kw in desc_lower for kw in ["deprecated", "use instead", "replaced by", "will be removed"])

            replacement = ""
            if is_deprecated:
                m = re.search(r"use\s+[`'\"]?(\w+)[`'\"]?\s+instead", desc_lower)
                if m:
                    replacement = m.group(1)

            mi = ModuleInput(
                name=inp_name,
                description=desc,
                type=str(typ),
                required=is_required,
                deprecated=is_deprecated,
                replacement=replacement,
            )
            if is_deprecated:
                deprecated_list.append(mi)
            elif is_required:
                required.append(mi)
            else:
                optional.append(mi)

        for out in raw_outputs:
            out_name = out.get("name", "")
            if out_name:
                outputs_list.append(ModuleOutput(
                    name=out_name,
                    description=out.get("description", ""),
                ))

        time.sleep(REQ_DELAY)
        return required, optional, deprecated_list, outputs_list, description

    except Exception as exc:
        log.warning("Could not fetch inputs/outputs for %s/%s/%s@%s: %s",
                    namespace, name, provider, version, exc)
        return [], [], [], [], description


def fetch_readme_example(namespace: str, name: str, provider: str) -> str:
    """
    Try to extract a usage example block from the module README on GitHub.
    Falls back to empty string on any error.
    """
    # Terraform Registry modules typically mirror GitHub repos.
    # Try the GitHub raw README for terraform-aws-modules and terraform-google-modules.
    github_owner_map = {
        "terraform-aws-modules": "terraform-aws-modules",
        "Azure":                 "Azure",
        "terraform-google-modules": "terraform-google-modules",
    }
    owner = github_owner_map.get(namespace)
    if not owner:
        return ""

    repo = f"terraform-{provider}-{name}" if namespace != "Azure" else name
    readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md"
    try:
        resp = requests.get(readme_url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=15)
        if resp.status_code != 200:
            # Try 'main' branch
            readme_url = readme_url.replace("/master/", "/main/")
            resp = requests.get(readme_url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=15)
        if resp.status_code != 200:
            return ""
        readme = resp.text
        # Extract the first HCL/Terraform code block
        match = re.search(r"```(?:hcl|terraform)\n(.*?)```", readme, re.DOTALL)
        if match:
            example = match.group(1).strip()
            # Truncate long examples to keep doc size manageable
            lines = example.splitlines()
            if len(lines) > 60:
                example = "\n".join(lines[:60]) + "\n  # ... (truncated)"
            return example
    except Exception as exc:
        log.debug("README fetch failed for %s/%s: %s", namespace, name, exc)
    return ""


# ── Document Builder ──────────────────────────────────────────────────────────

def _schema_to_doc(schema: ModuleSchema) -> str:
    """
    Convert a ModuleSchema into a compact text document suitable for embedding.
    """
    lines = [
        f"MODULE: {schema.source}",
        f"VERSION: {schema.version}",
        f"PROVIDER: {schema.provider}",
    ]
    if schema.description:
        lines.append(f"DESCRIPTION: {schema.description}")
    lines.append("")

    if schema.required_inputs:
        lines.append("REQUIRED INPUTS (must be set — no default):")
        for inp in schema.required_inputs:
            desc_part = f"  # {inp.description}" if inp.description else ""
            lines.append(f"  {inp.name} ({inp.type}){desc_part}")
        lines.append("")

    if schema.optional_inputs:
        lines.append("OPTIONAL INPUTS (have defaults):")
        for inp in schema.optional_inputs[:60]:  # cap to 60 to keep doc manageable
            desc_part = f"  # {inp.description}" if inp.description else ""
            lines.append(f"  {inp.name} ({inp.type}){desc_part}")
        if len(schema.optional_inputs) > 60:
            lines.append(f"  ... and {len(schema.optional_inputs) - 60} more optional inputs")
        lines.append("")

    if schema.deprecated_inputs:
        lines.append("DEPRECATED INPUTS (DO NOT USE):")
        for inp in schema.deprecated_inputs:
            replacement_part = f" → use '{inp.replacement}' instead" if inp.replacement else ""
            lines.append(f"  {inp.name}{replacement_part}  # DEPRECATED: {inp.description}")
        lines.append("")

    if schema.outputs:
        lines.append("OUTPUTS:")
        for out in schema.outputs[:40]:
            desc_part = f"  # {out.description}" if out.description else ""
            lines.append(f"  {out.name}{desc_part}")
        if len(schema.outputs) > 40:
            lines.append(f"  ... and {len(schema.outputs) - 40} more outputs")
        lines.append("")

    if schema.readme_example:
        lines.append("USAGE EXAMPLE:")
        lines.append("```hcl")
        lines.append(schema.readme_example)
        lines.append("```")

    return "\n".join(lines)


# ── ChromaDB helpers ─────────────────────────────────────────────────────────

def _get_chroma_collection():
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def _get_embedding_client():
    from openai import AzureOpenAI
    if not AZURE_OAI_ENDPOINT or not AZURE_OAI_KEY:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set")
    return AzureOpenAI(
        azure_endpoint=AZURE_OAI_ENDPOINT,
        api_key=AZURE_OAI_KEY,
        api_version=AZURE_OAI_VERSION,
    )


def embed_texts(oai_client, texts: List[str]) -> List[List[float]]:
    """Embed a list of texts using Azure OpenAI, in batches.

    Truncates each text to ~6000 tokens (≈24000 chars) to stay within the
    8192-token API limit (we use a conservative estimate since tokenisation
    is ~4 chars/token but module docs have many short lines).
    """
    MAX_CHARS = 24_000  # conservative ~6000 tokens
    texts = [t[:MAX_CHARS] if len(t) > MAX_CHARS else t for t in texts]

    all_embeddings: List[List[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        resp = oai_client.embeddings.create(model=EMBED_MODEL, input=batch)
        for item in resp.data:
            all_embeddings.append(item.embedding)
        if i + BATCH_SIZE < len(texts):
            time.sleep(0.1)
    return all_embeddings


# ── Main ingestion pipeline ───────────────────────────────────────────────────

def ingest_provider(provider_key: str) -> None:
    """Fetch and ingest all modules for a given provider key (aws/azure/gcp)."""
    module_list = MODULES_TO_INGEST.get(provider_key, [])
    if not module_list:
        log.error("Unknown provider key: %s", provider_key)
        return

    log.info("=== Ingesting %d modules for provider: %s ===", len(module_list), provider_key)

    oai_client = _get_embedding_client()
    collection = _get_chroma_collection()

    schemas: List[ModuleSchema] = []

    for namespace, name, provider in module_list:
        source = f"{namespace}/{name}/{provider}"
        log.info("Processing %s ...", source)

        version = get_latest_module_version(namespace, name, provider)
        log.info("  Latest version: %s", version)

        required, optional, deprecated_list, outputs, description = get_module_inputs_outputs(
            namespace, name, provider, version
        )
        log.info(
            "  Inputs: %d required, %d optional, %d deprecated | Outputs: %d",
            len(required), len(optional), len(deprecated_list), len(outputs)
        )

        readme_example = fetch_readme_example(namespace, name, provider)
        log.info("  README example: %s chars", len(readme_example))

        schema = ModuleSchema(
            namespace=namespace,
            name=name,
            provider=provider,
            version=version,
            source=source,
            required_inputs=required,
            optional_inputs=optional,
            deprecated_inputs=deprecated_list,
            outputs=outputs,
            description=description,
            readme_example=readme_example,
        )
        schemas.append(schema)
        time.sleep(REQ_DELAY)

    log.info("Fetched %d schemas. Building documents and embeddings ...", len(schemas))

    docs = [_schema_to_doc(s) for s in schemas]
    doc_ids = [
        f"{s.namespace}__{s.name}__{s.provider}__{s.version}".replace("/", "__")
        for s in schemas
    ]

    log.info("Embedding %d documents ...", len(docs))
    embeddings = embed_texts(oai_client, docs)

    metadatas = []
    for s in schemas:
        metadatas.append({
            "type":              "module_schema",
            "provider":          provider_key,        # "aws" | "azure" | "gcp"
            "tf_provider":       s.provider,           # "aws" | "azurerm" | "google"
            "namespace":         s.namespace,
            "name":              s.name,
            "version":           s.version,
            "source":            s.source,
            "required_inputs":   ",".join(i.name for i in s.required_inputs),
            "optional_inputs":   ",".join(i.name for i in s.optional_inputs[:80]),
            "deprecated_inputs": ",".join(i.name for i in s.deprecated_inputs),
            "output_names":      ",".join(o.name for o in s.outputs),
        })

    collection.upsert(
        ids=doc_ids,
        documents=docs,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    log.info("Upserted %d module schemas into '%s'", len(schemas), COLLECTION_NAME)
    log.info("Collection now has %d total documents", collection.count())


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Terraform module schemas into ChromaDB")
    parser.add_argument(
        "--provider",
        choices=["aws", "azure", "gcp", "all"],
        default="all",
        help="Which provider modules to ingest (default: all)",
    )
    args = parser.parse_args()

    # Load .env if present
    env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_file):
        log.info("Loading .env from %s", env_file)
        from dotenv import load_dotenv
        load_dotenv(env_file)
        # Re-read env vars after loading .env
        global AZURE_OAI_ENDPOINT, AZURE_OAI_KEY, AZURE_OAI_VERSION, EMBED_MODEL, CHROMA_DB_PATH
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
        EMBED_MODEL = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
        CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")

    providers = ["aws", "azure", "gcp"] if args.provider == "all" else [args.provider]
    for p in providers:
        ingest_provider(p)

    log.info("Done.")


if __name__ == "__main__":
    main()
