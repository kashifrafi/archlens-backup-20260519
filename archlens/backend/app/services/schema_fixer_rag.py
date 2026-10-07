"""
Schema Fixer RAG Service
========================
Runtime service that queries the 'provider_schemas' ChromaDB collection
(populated by scripts/ingest_provider_schemas.py) to:

1. Supply authoritative schema context strings for LLM prompts
2. Perform deterministic removal of removed/invalid arguments at runtime

The service degrades gracefully: if the collection is empty (not yet
ingested) or ChromaDB is unavailable, every public function returns a
safe empty/no-op result and logs a warning. This keeps the main
generation pipeline working without requiring a pre-populated collection.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ── Singletons ─────────────────────────────────────────────────────────────────

_schema_collection = None
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
            raise ValueError("No AI credentials configured for schema embeddings.")
    except Exception as exc:
        logger.warning("schema_fixer_rag: embedding client unavailable — %s", exc)
        return None
    return _embedding_client


def _get_schema_collection():
    """Return the provider_schemas ChromaDB collection, or None on failure."""
    global _schema_collection
    if _schema_collection is not None:
        return _schema_collection
    try:
        import chromadb

        db_path = os.path.abspath(settings.chroma_db_path)
        client  = chromadb.PersistentClient(path=db_path)
        coll    = client.get_or_create_collection(
            name=settings.provider_schemas_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        count = coll.count()
        if count == 0:
            logger.warning(
                "provider_schemas ChromaDB collection is empty. "
                "Run scripts/ingest_provider_schemas.py to populate it."
            )
        else:
            logger.info("provider_schemas: %d docs loaded from ChromaDB.", count)
        _schema_collection = coll
    except Exception as exc:
        logger.error("schema_fixer_rag: ChromaDB unavailable — %s", exc)
        return None
    return _schema_collection


def _embed(text: str) -> Optional[list]:
    client = _get_embedding_client()
    if client is None:
        return None
    try:
        resp = client.embeddings.create(
            model=settings.azure_openai_embedding_deployment,
            input=text,
        )
        return resp.data[0].embedding
    except Exception as exc:
        logger.warning("schema_fixer_rag: embedding failed — %s", exc)
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def get_schema_context(resource_types: List[str], provider: str = "aws") -> str:
    """
    Build a multi-resource schema context block for injection into LLM prompts.

    For each resource type in the list the nearest schema document is retrieved
    from ChromaDB. The returned string is ready to prepend/append to any prompt.

    Degrades gracefully to an empty string when the collection is not populated.
    """
    collection = _get_schema_collection()
    if collection is None or collection.count() == 0:
        return ""

    blocks: List[str] = []
    for rtype in resource_types:
        query  = f"valid arguments and blocks for {rtype} {provider} provider v5 terraform"
        vector = _embed(query)
        if vector is None:
            continue
        try:
            results = collection.query(
                query_embeddings=[vector],
                n_results=1,
                where={"provider": provider},
                include=["documents", "metadatas"],
            )
        except Exception as exc:
            logger.warning("schema_fixer_rag: query failed for %s — %s", rtype, exc)
            continue

        docs  = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        if not docs:
            continue

        doc     = docs[0]
        meta    = metas[0] if metas else {}
        matched = meta.get("resource_type", rtype)

        # Only include if the top hit is actually for this resource type
        # (guards against spurious hits when the collection is sparsely populated)
        if matched != rtype and not doc.startswith(f"Resource: {rtype}"):
            continue

        blocks.append(doc)

    if not blocks:
        return ""

    separator = "\n" + "═" * 60 + "\n"
    return (
        "PROVIDER SCHEMA REFERENCE (authoritative — from Terraform Registry):\n"
        + separator.join(blocks)
        + "\n"
    )


def get_resource_valid_args(
    resource_type: str,
    provider: str = "aws",
) -> Optional[Dict[str, List[str]]]:
    """
    Exact metadata lookup by resource_type.

    Returns a dict with keys valid_args, deprecated_args, removed_args
    (all as lists), or None when the resource is not in the collection.
    """
    collection = _get_schema_collection()
    if collection is None or collection.count() == 0:
        return None
    try:
        results = collection.get(
            where={"$and": [{"provider": provider}, {"resource_type": resource_type}]},
            include=["metadatas"],
        )
    except Exception as exc:
        logger.warning(
            "schema_fixer_rag: metadata lookup failed for %s/%s — %s",
            provider, resource_type, exc,
        )
        return None

    metas = results.get("metadatas", [])
    if not metas:
        return None

    m = metas[0]
    return {
        "valid_args":      [a for a in m.get("valid_args", "").split(",")      if a],
        "deprecated_args": [a for a in m.get("deprecated_args", "").split(",") if a],
        "removed_args":    [a for a in m.get("removed_args", "").split(",")    if a],
    }


# ── Deterministic RAG-based fixes ─────────────────────────────────────────────

_RESOURCE_BLOCK_RE = re.compile(
    r'^resource\s+"([^"]+)"\s+"([^"]+)"\s*\{',
    re.MULTILINE,
)

# Standard Terraform meta-arguments — valid in every resource, never in Registry docs
_TF_META_ARGS = frozenset({
    "provider", "count", "for_each", "depends_on", "lifecycle",
    "connection", "provisioner", "timeouts", "region",
})

# Pattern: exactly 2-space-indented simple assignment (not a block opener)
# Matches the top-level args inside a resource block after `terraform fmt`
_TOP_LEVEL_ARG_RE = re.compile(r'^  (\w+)\s*=\s*(?!\{)', re.MULTILINE)


def _find_block_end(content: str, open_brace_pos: int) -> int:
    """Return the index just after the matching closing brace."""
    depth = 0
    i = open_brace_pos
    while i < len(content):
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(content)


def apply_rag_schema_fixes(files, provider: str = "aws"):
    """
    Deterministically strip hallucinated / unsupported arguments from .tf files
    using the Terraform Registry schema stored in ChromaDB as a whitelist.

    Strategy (correct for Registry v6 docs which never list removed args):
    ─────────────────────────────────────────────────────────────────────
    • For every resource block, fetch valid_args from ChromaDB.
    • Scan top-level simple assignments (2-space indent after terraform fmt).
    • If an arg is NOT in valid_args AND NOT a Terraform meta-arg, strip it.
      → catches LLM hallucinations and args removed across provider versions.
    • deprecated_args are NOT stripped here — they're still valid HCL, just
      trigger warnings. schema_fixer.py handles the complex conversions.

    Accepts both TerraformFile objects and plain dicts.
    Falls back to a no-op when the ChromaDB collection is empty.
    """
    collection = _get_schema_collection()
    if collection is None or collection.count() == 0:
        logger.warning("apply_rag_schema_fixes: ChromaDB empty — skipping RAG fix pass")
        return files

    try:
        from app.services.schema_fixer import _remove_arg  # type: ignore[attr-defined]
    except ImportError:
        logger.warning("schema_fixer_rag: could not import _remove_arg; skipping")
        return files

    result = []
    for f in files:
        # Support both TerraformFile objects and plain dicts
        is_obj  = hasattr(f, "filename")
        fname   = f.filename if is_obj else f.get("filename", "")
        content = f.content  if is_obj else f.get("content",  "")

        if not fname.endswith(".tf"):
            result.append(f)
            continue

        changed = False

        # Iterative scan: re-scan from scratch after every modification so that
        # byte-positions never go stale (stripping one arg shifts all later offsets).
        _MAX_PASSES = 100  # safety cap
        for _pass in range(_MAX_PASSES):
            made_change_this_pass = False

            for m in _RESOURCE_BLOCK_RE.finditer(content):
                rtype = m.group(1)
                if not rtype.startswith(f"{provider}_"):
                    continue

                schema = get_resource_valid_args(rtype, provider)
                if schema is None or not schema.get("valid_args"):
                    continue

                valid_set = set(schema["valid_args"]) | _TF_META_ARGS

                # Find the block body using brace counting
                brace_pos = content.find('{', m.start())
                if brace_pos == -1:
                    continue
                block_end = _find_block_end(content, brace_pos)
                block_body = content[brace_pos:block_end]

                # Find first unsupported top-level arg in this block
                for arg_match in _TOP_LEVEL_ARG_RE.finditer(block_body):
                    arg = arg_match.group(1)
                    if arg not in valid_set:
                        new_content = _remove_arg(arg)(content)
                        if new_content != content:
                            logger.info(
                                "RAG-fix [%s/%s]: stripped unsupported arg '%s' from %s",
                                provider, rtype, arg, fname,
                            )
                            content = new_content
                            changed = True
                            made_change_this_pass = True
                            break  # restart inner loop with updated block_body

                if made_change_this_pass:
                    break  # restart outer finditer with updated content

            if not made_change_this_pass:
                break  # no more changes needed for this file

        if changed:
            if is_obj:
                from app.models.schemas import TerraformFile
                result.append(TerraformFile(
                    filename=fname,
                    content=content,
                    description=f.description,
                ))
            else:
                result.append({**f, "content": content})
        else:
            result.append(f)

    return result
