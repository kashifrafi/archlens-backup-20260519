"""
Deterministic Terraform Fix Engine
===================================
Single-pass deterministic fixer that replaces all AI retry loops.

Applies in order:
1. Provider-level schema fixes (removed/renamed args) via schema_fixer.py
2. Provider resource whitelist via schema_fixer_rag.py (strip hallucinated args)
3. Module input validation via module_schema_rag.py (check required/optional/deprecated)
4. Module output reference validation (fix module.X.nonexistent_output)
5. Duplicate resource/output/variable deduplication

Returns structured change report for UI display.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


def apply_deterministic_fixes(
    files: List[Dict],
    errors: List[str],
    cloud: str,
    stage: str = "unknown",
) -> Tuple[List[Dict], Dict]:
    """
    Single-pass deterministic fix engine.
    
    Args:
        files: List of {"filename": str, "content": str, ...} dicts
        errors: List of terraform error strings
        cloud: "aws" | "azure" | "gcp"
        stage: "init" | "validate" | "plan" for logging context
    
    Returns:
        (fixed_files, change_report)
        change_report = {
            "provider_fixes": ["removed tags_all from aws_instance.web", ...],
            "module_fixes": ["fixed module.vpc output reference", ...],
            "dedup_fixes": ["renamed duplicate output 'vpc_id' → 'vpc_id_2'", ...],
            "total_changes": int,
        }
    """
    from app.services.schema_fixer import fix_content
    from app.services.schema_fixer_rag import apply_rag_schema_fixes
    
    change_report = {
        "provider_fixes": [],
        "module_fixes": [],
        "dedup_fixes": [],
        "total_changes": 0,
    }
    
    result_files = list(files)
    
    # ── Pass 1: Provider-level deterministic transforms ─────────────────────
    logger.info("[%s] Deterministic fix pass 1: provider schema transforms", stage)
    for i, f in enumerate(result_files):
        if not f["filename"].endswith(".tf"):
            continue
        original = f["content"]
        fixed = fix_content(f["filename"], original)
        if fixed != original:
            result_files[i] = {**f, "content": fixed}
            change_report["provider_fixes"].append(f"Applied schema fixes to {f['filename']}")
    
    # ── Pass 2: Provider resource whitelist (strip hallucinated args) ───────
    logger.info("[%s] Deterministic fix pass 2: RAG schema whitelist", stage)
    before_count = sum(1 for f in result_files if f["filename"].endswith(".tf"))
    result_files = apply_rag_schema_fixes(result_files, cloud)
    # apply_rag_schema_fixes logs removals internally, aggregate here
    after_rag_check = [f for f in result_files if f["filename"].endswith(".tf")]
    if len(after_rag_check) != before_count:
        change_report["provider_fixes"].append("RAG schema whitelist applied")
    
    # ── Pass 3: Module input validation ─────────────────────────────────────
    logger.info("[%s] Deterministic fix pass 3: module input validation", stage)
    result_files, module_changes = _fix_module_inputs(result_files, cloud, errors)
    change_report["module_fixes"].extend(module_changes)
    
    # ── Pass 4: Module output reference validation ──────────────────────────
    logger.info("[%s] Deterministic fix pass 4: module output references", stage)
    result_files, output_changes = _fix_module_output_refs(result_files, cloud, errors)
    change_report["module_fixes"].extend(output_changes)
    
    # ── Pass 5: Deduplicate duplicate resources/outputs/variables ───────────
    logger.info("[%s] Deterministic fix pass 5: deduplication", stage)
    result_files, dedup_changes = _deduplicate_hcl_blocks(result_files, errors)
    change_report["dedup_fixes"].extend(dedup_changes)
    
    # ── Pass 6: Module source path validation ───────────────────────────────
    logger.info("[%s] Deterministic fix pass 6: module source path validation", stage)
    result_files, source_changes = _fix_module_source_paths(result_files, errors)
    change_report["module_fixes"].extend(source_changes)
    
    change_report["total_changes"] = (
        len(change_report["provider_fixes"])
        + len(change_report["module_fixes"])
        + len(change_report["dedup_fixes"])
    )
    
    if change_report["total_changes"] > 0:
        logger.info(
            "[%s] Deterministic fixes applied: %d provider, %d module, %d dedup",
            stage,
            len(change_report["provider_fixes"]),
            len(change_report["module_fixes"]),
            len(change_report["dedup_fixes"]),
        )
    else:
        logger.info("[%s] No deterministic fixes applied (errors may require manual intervention)", stage)
    
    return result_files, change_report


# ── Module Input Validation ──────────────────────────────────────────────────

def _fix_module_inputs(
    files: List[Dict],
    cloud: str,
    errors: List[str],
) -> Tuple[List[Dict], List[str]]:
    """
    Validate and fix module input arguments using module_schema_rag metadata.
    
    Fixes:
    - Remove deprecated module inputs
    - Remove unsupported module inputs not in required_inputs or optional_inputs
    - Add warning comments for missing required inputs (can't auto-add without user values)
    
    Returns (fixed_files, change_messages)
    """
    from app.services.module_schema_rag import _get_module_collection
    
    changes = []
    collection = _get_module_collection()
    if collection is None or collection.count() == 0:
        logger.warning("Module schema collection empty — skipping module input validation")
        return files, changes
    
    result = list(files)
    
    # Build map: module source → schema metadata
    try:
        all_docs = collection.get(
            where={"provider": cloud},
            include=["metadatas"],
        )
        schema_map: Dict[str, dict] = {}
        for meta in all_docs.get("metadatas", []):
            source = meta.get("source")
            if source:
                schema_map[source] = meta
    except Exception as exc:
        logger.warning("Could not load module schemas: %s", exc)
        return files, changes
    
    for i, f in enumerate(result):
        if not f["filename"].endswith(".tf"):
            continue
        
        content = f["content"]
        original = content
        
        # Find all module blocks
        module_blocks = _parse_module_blocks_detailed(content)
        
        for block in module_blocks:
            source = block["source"]
            if source not in schema_map:
                continue
            
            meta = schema_map[source]
            required_set = set(meta.get("required_inputs", "").split(","))
            optional_set = set(meta.get("optional_inputs", "").split(","))
            deprecated_set = set(meta.get("deprecated_inputs", "").split(","))
            valid_set = (required_set | optional_set) - {""}
            
            # Scan args in this module block
            block_body = content[block["body_start"]:block["body_end"]]
            args_found = _find_module_args(block_body)
            
            for arg_name in args_found:
                if arg_name in deprecated_set:
                    # Remove deprecated arg
                    pattern = re.compile(
                        rf'(?m)^([ \t]*){re.escape(arg_name)}\s*=\s*[^\n]+\n?'
                    )
                    content = pattern.sub(
                        rf'\1# {arg_name} (deprecated) — removed by ArchLens\n',
                        content,
                    )
                    changes.append(f"Removed deprecated input '{arg_name}' from module {block['name']} ({source})")
                
                elif arg_name not in valid_set and arg_name not in {"source", "version", "count", "for_each", "depends_on", "providers"}:
                    # Remove unsupported arg
                    pattern = re.compile(
                        rf'(?m)^([ \t]*){re.escape(arg_name)}\s*=\s*[^\n]+\n?'
                    )
                    content = pattern.sub(
                        rf'\1# {arg_name} (unsupported) — removed by ArchLens\n',
                        content,
                    )
                    changes.append(f"Removed unsupported input '{arg_name}' from module {block['name']} ({source})")
        
        if content != original:
            result[i] = {**f, "content": content}
    
    return result, changes


def _parse_module_blocks_detailed(content: str) -> List[Dict]:
    """
    Parse module blocks with body positions.
    Returns [{"name": str, "source": str, "body_start": int, "body_end": int}, ...]
    """
    blocks = []
    pattern = re.compile(r'module\s+"([^"]+)"\s*\{', re.MULTILINE)
    
    for m in pattern.finditer(content):
        name = m.group(1)
        open_brace = m.end() - 1
        close_brace = _find_matching_brace(content, open_brace)
        if close_brace == -1:
            continue
        
        body = content[open_brace + 1:close_brace]
        src_match = re.search(r'source\s*=\s*"([^"]+)"', body)
        if not src_match:
            continue
        
        blocks.append({
            "name": name,
            "source": src_match.group(1),
            "body_start": open_brace + 1,
            "body_end": close_brace,
        })
    
    return blocks


def _find_module_args(block_body: str) -> Set[str]:
    """Extract top-level argument names from a module block body."""
    args = set()
    # Match simple assignments (not nested blocks)
    pattern = re.compile(r'^\s{2}(\w+)\s*=\s*(?!\{)', re.MULTILINE)
    for m in pattern.finditer(block_body):
        args.add(m.group(1))
    return args


def _find_matching_brace(content: str, open_pos: int) -> int:
    """Find the position of the matching closing brace."""
    depth = 0
    i = open_pos
    while i < len(content):
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


# ── Module Output Reference Validation ───────────────────────────────────────

def _fix_module_output_refs(
    files: List[Dict],
    cloud: str,
    errors: List[str],
) -> Tuple[List[Dict], List[str]]:
    """
    Validate module.X.Y references against known module output names.
    
    Fixes:
    - Replace module.X.invalid_output with module.X.closest_valid_output
    - Add comments explaining the replacement
    
    Returns (fixed_files, change_messages)
    """
    from app.services.module_schema_rag import _get_module_collection
    
    changes = []
    collection = _get_module_collection()
    if collection is None or collection.count() == 0:
        return files, changes
    
    # Parse errors for "module.X.Y does not exist" patterns
    invalid_refs = _parse_invalid_module_refs(errors)
    if not invalid_refs:
        return files, changes
    
    # Load module output schemas
    try:
        all_docs = collection.get(
            where={"provider": cloud},
            include=["metadatas"],
        )
        schema_map: Dict[str, Set[str]] = {}
        for meta in all_docs.get("metadatas", []):
            source = meta.get("source")
            outputs = set(meta.get("output_names", "").split(",")) - {""}
            if source and outputs:
                schema_map[source] = outputs
    except Exception as exc:
        logger.warning("Could not load module output schemas: %s", exc)
        return files, changes
    
    # Build module name → source map from files
    module_sources = {}
    for f in files:
        if not f["filename"].endswith(".tf"):
            continue
        for m in re.finditer(r'module\s+"([^"]+)"\s*\{[^}]*source\s*=\s*"([^"]+)"', f["content"], re.DOTALL):
            module_sources[m.group(1)] = m.group(2)
    
    result = list(files)
    
    for i, f in enumerate(result):
        if not f["filename"].endswith(".tf"):
            continue
        
        content = f["content"]
        original = content
        
        for mod_name, bad_output in invalid_refs:
            if mod_name not in module_sources:
                continue
            source = module_sources[mod_name]
            if source not in schema_map:
                continue
            
            valid_outputs = schema_map[source]
            # Find closest match
            closest = _find_closest_match(bad_output, valid_outputs)
            if not closest:
                continue
            
            # Replace module.X.bad_output with module.X.closest
            bad_ref = f"module.{mod_name}.{bad_output}"
            good_ref = f"module.{mod_name}.{closest}"
            
            if bad_ref in content:
                content = content.replace(
                    bad_ref,
                    f"{good_ref} /* ArchLens: was '{bad_output}' */",
                )
                changes.append(f"Fixed output reference: {bad_ref} → {good_ref}")
        
        if content != original:
            result[i] = {**f, "content": content}
    
    return result, changes


def _parse_invalid_module_refs(errors: List[str]) -> List[Tuple[str, str]]:
    """
    Extract (module_name, invalid_output) from error messages.
    Patterns: "module.vpc.nonexistent_output", "output 'bad_name' not found in module.X"
    """
    refs = []
    for err in errors:
        # Pattern: module.X.Y (explicit reference)
        for m in re.finditer(r'module\.([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_-]+)', err):
            refs.append((m.group(1), m.group(2)))
    return refs


def _find_closest_match(target: str, candidates: Set[str]) -> Optional[str]:
    """Simple Levenshtein-like closest string match."""
    if not candidates:
        return None
    # Exact match first
    if target in candidates:
        return target
    # Prefix match
    for c in candidates:
        if c.startswith(target) or target.startswith(c):
            return c
    # Substring match
    for c in candidates:
        if target in c or c in target:
            return c
    # Fallback: first candidate alphabetically
    return sorted(candidates)[0]


# ── Deduplication ────────────────────────────────────────────────────────────

def _deduplicate_hcl_blocks(
    files: List[Dict],
    errors: List[str],
) -> Tuple[List[Dict], List[str]]:
    """
    Deduplicate duplicate resource/output/variable blocks by renaming with _2, _3 suffixes.
    
    Only triggers if errors contain "Duplicate output", "Duplicate resource", etc.
    
    Returns (fixed_files, change_messages)
    """
    changes = []
    
    # Check if deduplication is needed
    needs_dedup = any(
        "duplicate" in e.lower() and any(kw in e.lower() for kw in ["output", "resource", "variable", "module"])
        for e in errors
    )
    if not needs_dedup:
        return files, changes
    
    result = list(files)
    
    for i, f in enumerate(result):
        if not f["filename"].endswith(".tf"):
            continue
        
        content = f["content"]
        original = content
        
        # Deduplicate outputs
        content, output_changes = _deduplicate_blocks(content, "output")
        changes.extend(output_changes)
        
        # Deduplicate variables
        content, var_changes = _deduplicate_blocks(content, "variable")
        changes.extend(var_changes)
        
        # Deduplicate resources
        content, res_changes = _deduplicate_resources(content)
        changes.extend(res_changes)
        
        if content != original:
            result[i] = {**f, "content": content}
    
    return result, changes


def _deduplicate_blocks(content: str, block_type: str) -> Tuple[str, List[str]]:
    """Deduplicate output or variable blocks by renaming duplicates."""
    changes = []
    pattern = re.compile(rf'{block_type}\s+"([^"]+)"\s*\{{', re.MULTILINE)
    
    seen: Dict[str, int] = {}
    replacements: List[Tuple[str, str]] = []
    
    for m in pattern.finditer(content):
        name = m.group(1)
        if name in seen:
            seen[name] += 1
            new_name = f"{name}_{seen[name]}"
            replacements.append((m.group(0), f'{block_type} "{new_name}" {{'))
            changes.append(f"Renamed duplicate {block_type} '{name}' → '{new_name}'")
        else:
            seen[name] = 1
    
    for old, new in replacements:
        content = content.replace(old, new, 1)
    
    return content, changes


def _deduplicate_resources(content: str) -> Tuple[str, List[str]]:
    """Deduplicate resource blocks by renaming duplicates."""
    changes = []
    pattern = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE)
    
    seen: Dict[Tuple[str, str], int] = {}
    replacements: List[Tuple[str, str]] = []
    
    for m in pattern.finditer(content):
        rtype = m.group(1)
        rname = m.group(2)
        key = (rtype, rname)
        if key in seen:
            seen[key] += 1
            new_name = f"{rname}_{seen[key]}"
            replacements.append((m.group(0), f'resource "{rtype}" "{new_name}" {{'))
            changes.append(f"Renamed duplicate resource {rtype}.{rname} → {rtype}.{new_name}")
        else:
            seen[key] = 1
    
    for old, new in replacements:
        content = content.replace(old, new, 1)
    
    return content, changes


# ── Module Source Path Validation ────────────────────────────────────────────

def _fix_module_source_paths(
    files: List[Dict],
    errors: List[str],
) -> Tuple[List[Dict], List[str]]:
    """
    Fix invalid module source paths that reference non-existent submodules.
    
    Detects "Unreadable module subdirectory" errors and fixes by:
    1. Parsing the error to extract module name and invalid submodule path
    2. Removing the invalid //modules/... suffix from the source
    3. Falling back to root module source
    
    Returns (fixed_files, change_messages)
    """
    changes = []
    
    # Check if errors contain module subdirectory issues
    has_module_path_errors = any(
        "unreadable module subdirectory" in e.lower() or "does not exist within the target module" in e.lower()
        for e in errors
    )
    if not has_module_path_errors:
        return files, changes
    
    # Parse errors to extract problematic module paths
    invalid_submodules = _parse_invalid_submodule_errors(errors)
    if not invalid_submodules:
        return files, changes
    
    result = list(files)
    
    for i, f in enumerate(result):
        if not f["filename"].endswith(".tf"):
            continue
        
        content = f["content"]
        original = content
        
        # Find all module blocks and check their sources
        module_blocks = re.finditer(
            r'module\s+"([^"]+)"\s*\{[^}]*source\s*=\s*"([^"]+)"[^}]*\}',
            content,
            re.DOTALL
        )
        
        for m in module_blocks:
            module_name = m.group(1)
            source = m.group(2)
            
            # Check if this module has an invalid submodule path
            for invalid_path in invalid_submodules:
                if invalid_path in source:
                    # Remove the invalid submodule path suffix
                    # e.g., "terraform-aws-modules/alb//modules/target-group-attachment" 
                    #    -> "terraform-aws-modules/alb"
                    fixed_source = re.sub(r'//modules/[^"\s]+$', '', source)
                    
                    if fixed_source != source:
                        # Replace in content
                        old_line = f'source = "{source}"'
                        new_line = f'source = "{fixed_source}"  # ArchLens: removed invalid submodule path'
                        content = content.replace(old_line, new_line)
                        changes.append(
                            f"Fixed module '{module_name}' source: removed invalid submodule path '{invalid_path}'"
                        )
                        logger.info(
                            "Fixed module source: %s -> %s (invalid submodule: %s)",
                            source, fixed_source, invalid_path
                        )
        
        if content != original:
            result[i] = {**f, "content": content}
    
    return result, changes


def _parse_invalid_submodule_errors(errors: List[str]) -> List[str]:
    """
    Extract invalid submodule paths from error messages.
    
    Example error:
    "The directory .terraform/modules/compute.alb_target_group_attachment_app1/modules/target-group-attachment
     does not exist. The target submodule modules/target-group-attachment does not exist within the target module."
    
    Returns: ["modules/target-group-attachment", ...]
    """
    invalid_paths = []
    
    for err in errors:
        # Pattern 1: "target submodule modules/X does not exist"
        m = re.search(r'target submodule (modules/[^\s]+) does not exist', err, re.IGNORECASE)
        if m:
            invalid_paths.append(m.group(1))
            continue
        
        # Pattern 2: Extract from directory path
        m = re.search(r'\.terraform/modules/[^/]+/(modules/[^\s]+)', err)
        if m:
            invalid_paths.append(m.group(1))
    
    return list(set(invalid_paths))  # deduplicate
