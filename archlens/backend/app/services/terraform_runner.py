"""
terraform_runner.py — Real-time Terraform execution with SSE streaming.

Runs terraform fmt → init → validate → plan in a temp workspace,
streaming every stdout/stderr line as a Server-Sent Event.

All stages use GPT-5.3-CODEX AI FIXES — each stage gets 1 initial attempt
+ max 2 retry attempts with codex fixing errors. If all fail, pipeline either
continues (for validate) or triggers manual fix mode.

Speed optimisations:
- Provider plugin cache  : TF_PLUGIN_CACHE_DIR=~/.archlens/tf-plugin-cache
- Module source cache    : ~/.archlens/module-cache/<hash> — reuses downloaded
                           module sources so terraform init only re-runs registry
                           lookups, not full downloads.
- Plan skipped if no creds: detects missing AWS/Azure/GCP credentials and skips
                           the plan stage with an explanatory message instead of
                           hanging for 60s waiting for a provider auth error.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)

_EXTRA_PATH      = os.path.expanduser("~/.local/bin")
_PLUGIN_CACHE    = os.path.expanduser("~/.archlens/tf-plugin-cache")
_MODULE_ARCHIVE  = os.path.expanduser("~/.archlens/module-archive")
_BASE_LOCKFILE   = os.path.expanduser("~/.archlens/tf-plugin-cache/base.lock.hcl")
_MAX_RETRIES     = 3
_STREAM_SECRET_VALUES = contextvars.ContextVar("stream_secret_values", default=())


def _mask_sensitive_text(text: str, extra_values: Optional[Dict[str, str]] = None) -> str:
    if not isinstance(text, str):
        return text
    values = list(_STREAM_SECRET_VALUES.get(()))
    if extra_values:
        values.extend(str(v) for v in extra_values.values() if v and len(str(v)) >= 4)
    for name in [
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "ARM_CLIENT_ID", "ARM_CLIENT_SECRET", "ARM_TENANT_ID", "ARM_SUBSCRIPTION_ID",
        "GOOGLE_CREDENTIALS", "GOOGLE_APPLICATION_CREDENTIALS", "GCP_API_KEY",
        "HCP_TERRAFORM_TOKEN", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_FOUNDRY_API_KEY",
    ]:
        value = os.environ.get(name)
        if value and len(value) >= 4:
            values.append(value)
    masked = text
    for value in sorted(set(values), key=len, reverse=True):
        masked = masked.replace(value, "xxxxxxxx")
    patterns = [
        r'AKIA[0-9A-Z]{16}',
        r'ASIA[0-9A-Z]{16}',
        r'(?i)(aws_secret_access_key\s*[=:]\s*)[^\s,}\]]+',
        r'(?i)(client_secret\s*[=:]\s*)[^\s,}\]]+',
        r'(?i)(api_key\s*[=:]\s*)[^\s,}\]]+',
        r'(?i)(token\s*[=:]\s*)[^\s,}\]]+',
        r'(?i)(password\s*[=:]\s*)[^\s,}\]]+',
        r'(?is)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
    ]
    for pattern in patterns:
        masked = re.sub(pattern, lambda match: (match.group(1) if match.lastindex else "") + "xxxxxxxx", masked)
    return masked


def _mask_payload(obj, extra_values: Optional[Dict[str, str]] = None):
    if isinstance(obj, str):
        return _mask_sensitive_text(obj, extra_values)
    if isinstance(obj, list):
        return [_mask_payload(item, extra_values) for item in obj]
    if isinstance(obj, dict):
        return {key: _mask_payload(value, extra_values) for key, value in obj.items()}
    return obj


def _which_tf() -> Optional[str]:
    full = os.path.join(_EXTRA_PATH, "terraform")
    if os.path.isfile(full) and os.access(full, os.X_OK):
        return full
    return shutil.which("terraform")


def _which_tool(name: str) -> Optional[str]:
    """Find any tool binary, checking ~/.local/bin first then PATH."""
    full = os.path.join(_EXTRA_PATH, name)
    if os.path.isfile(full) and os.access(full, os.X_OK):
        return full
    return shutil.which(name)


def _env() -> Dict[str, str]:
    e = os.environ.copy()
    e["PATH"] = _EXTRA_PATH + ":" + e.get("PATH", "")
    e["TF_PLUGIN_CACHE_DIR"] = _PLUGIN_CACHE
    e["TF_INPUT"] = "false"
    e["TF_IN_AUTOMATION"] = "true"
    e["CHECKPOINT_DISABLE"] = "1"
    return e


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(_mask_payload(data))}\n\n"


def _write_files(files: List[Dict], tmpdir: str) -> None:
    for f in files:
        path = os.path.join(tmpdir, f["filename"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(f["content"])


def _read_files(tmpdir: str) -> List[Dict]:
    result = []
    for root, dirs, files in os.walk(tmpdir):
        # Skip .terraform cache directory
        dirs[:] = [d for d in sorted(dirs) if d != '.terraform']
        for fname in sorted(files):
            if not fname.endswith(".tf") and fname != ".terraform.lock.hcl" and not fname.endswith(".tfvars.example"):
                continue
            if fname.startswith("."):
                continue
            full = os.path.join(root, fname)
            rel  = os.path.relpath(full, tmpdir)
            with open(full) as fh:
                result.append({"filename": rel, "content": fh.read(), "description": ""})
    return result


# ── Module archive (persistent per-source-version store) ────────────────────

def _archive_key(source: str, version: str) -> str:
    """Filesystem-safe key for one module version.
    e.g. 'terraform-aws-modules/vpc/aws' + '6.6.1' → 'terraform-aws-modules__vpc__aws__6.6.1'
    """
    clean = re.sub(r'^registry\.terraform\.io/', '', source)
    clean = clean.replace("/", "__")
    return f"{clean}__{version}" if version else clean


def _parse_module_blocks(files: List[Dict]) -> List[Dict]:
    """
    Extract all module blocks from .tf files.
    Returns list of {'key': local_name, 'source': '...', 'version': '...'}
    """
    results = []
    for f in files:
        content = f.get("content", "")
        i = 0
        while True:
            m = re.search(r'module\s+"([^"]+)"\s*\{', content[i:])
            if not m:
                break
            key = m.group(1)
            brace_start = i + m.end() - 1
            depth, pos = 1, brace_start + 1
            while pos < len(content) and depth > 0:
                if content[pos] == '{':   depth += 1
                elif content[pos] == '}': depth -= 1
                pos += 1
            block = content[brace_start + 1 : pos - 1]
            src_m = re.search(r'source\s*=\s*"([^"]+)"', block)
            ver_m = re.search(r'version\s*=\s*"([^"]+)"', block)
            if src_m:
                results.append({
                    "key": key,
                    "source": src_m.group(1),
                    "version": ver_m.group(1) if ver_m else "",
                })
            i = i + m.start() + 1
    return results


def _populate_modules_from_archive(module_refs: List[Dict], tmpdir: str) -> bool:
    """
    For each module ref, copy its source tree from the archive into
    .terraform/modules/<key>/ and write modules.json including all sub-modules.
    Returns True if ALL modules were satisfied from the archive.
    """
    if not module_refs:
        return False

    modules_dir = os.path.join(tmpdir, ".terraform", "modules")
    os.makedirs(modules_dir, exist_ok=True)

    entries  = [{"Key": "", "Source": "", "Dir": "."}]
    all_hit  = True

    for ref in module_refs:
        akey        = _archive_key(ref["source"], ref["version"])
        archive_src = os.path.join(_MODULE_ARCHIVE, akey)
        if os.path.isdir(archive_src):
            dst = os.path.join(modules_dir, ref["key"])
            if os.path.exists(dst):
                shutil.rmtree(dst)
            try:
                shutil.copytree(archive_src, dst)
            except Exception as exc:
                logger.warning("archive restore failed for %s: %s", akey, exc)
                all_hit = False
                continue
            # modules.json Source needs the registry.terraform.io/ prefix
            registry_src = ref["source"]
            if "/" in registry_src and not registry_src.startswith("registry."):
                parts = registry_src.split("/")
                if len(parts) == 3:
                    registry_src = f"registry.terraform.io/{registry_src}"
            entries.append({
                "Key":     ref["key"],
                "Source":  registry_src,
                "Version": ref["version"],
                "Dir":     f".terraform/modules/{ref['key']}",
            })
            # Add sub-module entries (e.g. rds/modules/db_instance)
            # Source must be the local relative path (./modules/<name>), no Version field
            sub_root = os.path.join(archive_src, "modules")
            if os.path.isdir(sub_root):
                for sub_name in sorted(os.listdir(sub_root)):
                    sub_path = os.path.join(sub_root, sub_name)
                    if not os.path.isdir(sub_path):
                        continue
                    entries.append({
                        "Key":    f"{ref['key']}.{sub_name}",
                        "Source": f"./modules/{sub_name}",
                        "Dir":    f".terraform/modules/{ref['key']}/modules/{sub_name}",
                    })
        else:
            all_hit = False

    with open(os.path.join(modules_dir, "modules.json"), "w") as fh:
        json.dump({"Modules": entries}, fh)

    # Copy base lock file so provider resolution skips registry queries
    if all_hit and os.path.isfile(_BASE_LOCKFILE):
        shutil.copy2(_BASE_LOCKFILE, os.path.join(tmpdir, ".terraform.lock.hcl"))

    return all_hit


def _save_modules_to_archive(module_refs: List[Dict], tmpdir: str) -> None:
    """After a successful full init, archive each downloaded module source tree."""
    modules_dir = os.path.join(tmpdir, ".terraform", "modules")
    if not os.path.isdir(modules_dir):
        return
    Path(_MODULE_ARCHIVE).mkdir(parents=True, exist_ok=True)
    for ref in module_refs:
        src = os.path.join(modules_dir, ref["key"])
        if not os.path.isdir(src):
            continue
        akey = _archive_key(ref["source"], ref["version"])
        dst  = os.path.join(_MODULE_ARCHIVE, akey)
        if os.path.exists(dst):
            continue  # already archived
        try:
            shutil.copytree(src, dst)
            logger.info("Archived module %s v%s", ref["source"], ref["version"])
        except Exception as exc:
            logger.warning("archive save failed for %s: %s", ref["source"], exc)


# ── Credential detection ───────────────────────────────────────────────────────

def _has_cloud_credentials(cloud: str) -> bool:
    """
    Quick heuristic check: are credentials available for `terraform plan`?
    Without creds the plan will just hang or throw an auth error.
    """
    if cloud == "aws":
        return bool(
            os.environ.get("AWS_ACCESS_KEY_ID")
            or os.environ.get("AWS_PROFILE")
            or os.path.isfile(os.path.expanduser("~/.aws/credentials"))
            or os.path.isfile(os.path.expanduser("~/.aws/config"))
        )
    if cloud == "azure" or cloud == "azurerm":
        return bool(
            os.environ.get("ARM_CLIENT_ID")
            or os.environ.get("ARM_ACCESS_TOKEN")
            or shutil.which("az")
        )
    if cloud == "gcp" or cloud == "google":
        return bool(
            os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            or os.path.isfile(
                os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
            )
        )
    return False


def _is_uninit_error(error: str) -> bool:
    """
    Returns True if the error is solely because terraform is not yet initialized.
    These are expected BEFORE 'terraform init' runs and should not block the pipeline.
    """
    lower = error.lower()
    return any(p in lower for p in (
        "module not installed",
        "not yet installed",
        "run terraform init",
        'run "terraform init"',
        "provider not installed",
        "has not been installed",
        "not initialized",
        "terraform init",
    ))


def _parse_validate_errors(output: str) -> List[str]:
    """Extract error messages from terraform validate -json output."""
    errors = []
    try:
        data = json.loads(output)
        for diag in data.get("diagnostics", []):
            if diag.get("severity") == "error":
                summary = diag.get("summary", "")
                detail  = diag.get("detail", "")
                rng     = diag.get("range", {})
                fname   = rng.get("filename", "")
                line    = rng.get("start", {}).get("line", "?")
                errors.append(f"{fname}:{line} — {summary}. {detail}".strip(". "))
    except (json.JSONDecodeError, Exception):
        # fallback: grab lines starting with "│"
        for line in output.splitlines():
            line = line.strip("│ \t")
            if line.startswith("Error:") or "error" in line.lower():
                errors.append(line)
    return errors


def _parse_plan_summary(plan_json_path: str) -> Dict:
    """Parse terraform plan -json output into a human-readable summary."""
    try:
        changes = {"add": 0, "change": 0, "remove": 0}
        resources = []
        with open(plan_json_path) as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "planned_change":
                    change = obj.get("change", {})
                    action = change.get("action", "")
                    addr   = change.get("resource", {}).get("addr", "")
                    if action == "create":
                        changes["add"] += 1
                        resources.append(f"+ {addr}")
                    elif action in ("update", "replace"):
                        changes["change"] += 1
                        resources.append(f"~ {addr}")
                    elif action == "delete":
                        changes["remove"] += 1
                        resources.append(f"- {addr}")
        return {"changes": changes, "resources": resources[:40]}
    except Exception as exc:
        logger.warning("plan parse failed: %s", exc)
        return {"changes": {}, "resources": []}


async def _run_cmd(
    cmd: List[str],
    cwd: str,
    timeout: int = 300,
    extra_env: Optional[Dict[str, str]] = None,
) -> AsyncGenerator[str, None]:
    """
    Async subprocess that yields output lines in real time.
    Yields a final '__RC__<code>' line with the return code.
    """
    env = _env()
    if extra_env:
        # Inject user-supplied credentials; strip blank values
        for k, v in extra_env.items():
            if k and v and v.strip():
                env[k] = v.strip()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    try:
        # asyncio.timeout() is Python 3.11+ — use wait_for on each readline instead
        while True:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                yield f"[TIMEOUT] Command timed out after {timeout}s"
                break
            if not line:
                break
            yield _mask_sensitive_text(line.decode(errors="replace").rstrip(), extra_env)
        await proc.wait()
    except Exception:
        proc.kill()
        await proc.wait()
        raise
    yield f"__RC__{proc.returncode}"


def _llm_fix_errors(
    files: List[Dict],
    errors: List[str],
    cloud: str,
    stage: str
) -> tuple[List[Dict], List[str]]:
    """
    Use GPT-5.3-codex to fix Terraform errors.
    Returns (fixed_files, change_report).
    
    This replaces the deterministic fixer with AI-based fixes.
    """
    from app.services.terraform_service import _get_client
    
    if not errors:
        return files, []
    
    # Build context about the errors
    errors_text = "\n".join(f"- {e}" for e in errors)
    
    # Build files context  
    files_text = "\n\n".join(
        f"=== {f['filename']} ===\n{f['content']}"
        for f in files
    )
    
    prompt = f"""You are a Terraform expert. The following Terraform configuration has errors in the {stage} stage.

ERRORS:
{errors_text}

CURRENT FILES:
{files_text}

Fix ALL the errors above. Common issues:
- Module output references: Check module outputs.tf files and ensure references match
- Module input variables: Ensure module variables.tf has all required variables
- Resource references: Verify resource names and attributes exist
- Syntax errors: Fix HCL syntax mistakes

Return ONLY valid JSON with this structure:
{{
  "fixed_files": [
    {{"filename": "path/to/file.tf", "content": "<complete fixed HCL>", "description": "what was fixed"}},
    ...
  ],
  "changes": [
    "Fixed module.compute.instances reference - changed to module.compute.instance_ids",
    "Added missing db_security_group_ids variable to database module",
    ...
  ]
}}

Generate COMPLETE files - never use placeholders like "... rest of file ...".
"""

    try:
        client, model = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Terraform expert specializing in fixing configuration errors. "
                        "Analyze errors carefully and fix them precisely. Return complete, valid files."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=16000,
            temperature=0.1,  # Low temperature for more deterministic fixes
            response_format={"type": "json_object"}
        )
        
        data = json.loads(response.choices[0].message.content)
        fixed_files = data.get("fixed_files", [])
        changes = data.get("changes", [])
        
        logger.info(f"Codex fixed {len(fixed_files)} files with {len(changes)} changes")
        return fixed_files, changes
        
    except Exception as exc:
        logger.error(f"LLM fix failed: {exc}")
        # Return original files if LLM fix fails
        return files, [f"LLM fix failed: {exc}"]


async def run_terraform_stream(
    files: List[Dict],
    cloud: str = "aws",
    run_plan: bool = True,
    env_vars: Optional[Dict[str, str]] = None,
) -> AsyncGenerator[str, None]:
    """
    Pipeline: fmt -recursive → init -upgrade → validate → plan

    All stages (init, validate, plan) use GPT-5.3-codex AI-fix retry loop:
    - Max 3 attempts per stage (1 initial + 2 AI fix retries)
    - Codex analyzes errors and fixes them
    - If all 3 attempts fail, triggers manual fix mode (except validate - continues to plan)

    Validate is non-blocking: if validation fails after 3 attempts, pipeline 
    continues to plan anyway so resources without errors can still be validated.
    Persistent validation errors are reported in the final summary.

    Pre-init validate was intentionally removed: the HCL syntax fixer runs at
    generation time and 'terraform validate' before init always fails with
    spurious "Module not installed" errors that add latency without value.
    """
    tf = _which_tf()
    if not tf:
        yield _sse("error", {"message": "terraform binary not found — install terraform >= 1.5"})
        return

    Path(_PLUGIN_CACHE).mkdir(parents=True, exist_ok=True)
    Path(_MODULE_ARCHIVE).mkdir(parents=True, exist_ok=True)

    stream_secret_token = _STREAM_SECRET_VALUES.set(tuple(
        str(value) for value in (env_vars or {}).values() if value and len(str(value)) >= 4
    ))

    env_creds_present = bool(env_vars and any(v and v.strip() for v in env_vars.values()))
    has_creds   = _has_cloud_credentials(cloud) or env_creds_present
    actual_plan = run_plan and has_creds

    tmpdir = tempfile.mkdtemp(prefix="archlens_run_")
    try:
        _write_files(files, tmpdir)
        current_files = list(files)

        # ── STAGE 1: terraform fmt -recursive ────────────────────────────
        yield _sse("stage", {"stage": "fmt", "message": "Formatting HCL (recursive)..."})
        async for line in _run_cmd([tf, "fmt", "-no-color", "-recursive", "."], tmpdir, timeout=30):
            if not line.startswith("__RC__"):
                yield _sse("log", {"stage": "fmt", "line": line})
        current_files = _read_files(tmpdir)
        yield _sse("files_updated", {
            "stage": "fmt",
            "files": [{"filename": f["filename"], "content": f["content"]} for f in current_files],
        })
        yield _sse("stage_done", {"stage": "fmt", "passed": True})

        # ── STAGE 2: terraform init (with codex fix, max 2 retries) ────
        module_refs  = _parse_module_blocks(current_files)
        archive_full = _populate_modules_from_archive(module_refs, tmpdir)

        init_success      = False

        for init_attempt in range(1, 4):  # max 3 attempts: 1 initial + 2 AI fix retries
            if archive_full:
                msg = ("Initializing Terraform (modules from local archive)..."
                       if init_attempt == 1
                       else f"Re-initializing after AI fix (attempt {init_attempt}/3)...")
                yield _sse("stage", {"stage": "init", "attempt": init_attempt, "message": msg})
                init_cmd = [tf, "init", "-no-color", "-upgrade=false", "-get=false"]
            else:
                new_mods = [
                    r["source"] for r in module_refs
                    if not os.path.isdir(os.path.join(_MODULE_ARCHIVE, _archive_key(r["source"], r["version"])))
                ]
                msg = (
                    f"Initializing Terraform (downloading {len(new_mods)} new module(s) — first time only, ~30s)..."
                    if new_mods else "Initializing Terraform..."
                )
                yield _sse("stage", {"stage": "init", "attempt": init_attempt, "message": msg})
                init_cmd = [tf, "init", "-no-color", "-upgrade"]

            init_output = []
            rc = 0
            async for line in _run_cmd(init_cmd, tmpdir, timeout=300):
                if line.startswith("__RC__"):
                    rc = int(line[6:])
                else:
                    init_output.append(line)
                    yield _sse("log", {"stage": "init", "line": line})

            # If -get=false failed (provider constraint change), retry once with full init
            if rc != 0 and archive_full and init_attempt == 1:
                yield _sse("log", {"stage": "init", "line": "[cache miss] retrying with full init -upgrade..."})
                shutil.rmtree(os.path.join(tmpdir, ".terraform"), ignore_errors=True)
                init_output = []
                rc = 0
                async for line in _run_cmd([tf, "init", "-no-color", "-upgrade"], tmpdir, timeout=300):
                    if line.startswith("__RC__"):
                        rc = int(line[6:])
                    else:
                        init_output.append(line)
                        yield _sse("log", {"stage": "init", "line": line})

            if rc == 0:
                init_success = True
                _save_modules_to_archive(module_refs, tmpdir)
                yield _sse("stage_done", {"stage": "init", "passed": True, "attempts": init_attempt})
                break

            init_errors = _parse_init_code_errors(init_output)
            if not init_errors:
                yield _sse("error", {
                    "stage": "init",
                    "message": "terraform init failed — check module sources or network connectivity",
                    "output": "\n".join(init_output[-20:]),
                })
                return

            yield _sse("init_errors", {"errors": init_errors, "attempt": init_attempt, "stage": "init"})

            if init_attempt >= 3:
                _last_files = _read_files(tmpdir)
                yield _sse("error", {
                    "stage": "init",
                    "message": f"Init still failing after {init_attempt-1} AI fix attempts — manual intervention required",
                    "errors": init_errors,
                    "output": "\n".join(init_output[-20:]),
                    "files": [{"filename": f["filename"], "content": f["content"]} for f in _last_files],
                })
                return

            yield _sse("stage", {
                "stage": "codex_fix", "attempt": init_attempt,
                "message": f"🤖 Fixing the code...",
            })
            try:
                current_files = _read_files(tmpdir)
                fixed_files, change_report = _llm_fix_errors(current_files, init_errors, cloud, "init")
                _write_files(fixed_files, tmpdir)
                current_files = fixed_files
                yield _sse("files_updated", {
                    "stage": "codex_fix", "attempt": init_attempt,
                    "files": [{"filename": f["filename"], "content": f["content"]} for f in fixed_files],
                    "changes": change_report,
                })
                yield _sse("stage_done", {"stage": "codex_fix", "passed": True, "attempt": init_attempt})
            except Exception as exc:
                yield _sse("error", {"stage": "codex_fix", "message": f"Codex fix failed: {exc}", "errors": init_errors})
                return

        if not init_success:
            return

        # ── STAGE 3: terraform validate (with codex fix, max 2 retries) ─
        # After 2 AI fix attempts, we continue to plan anyway so resources
        # without errors can be deployed. Persistent validation errors are
        # forwarded to the final 'done' event for manual fix UI.
        persistent_validate_errors: List[str] = []

        for attempt in range(1, 4):  # max 3 attempts: 1 initial + 2 AI fix retries
            yield _sse("stage", {
                "stage": "validate", "attempt": attempt,
                "message": f"Validating configuration (attempt {attempt}/3)...",
            })
            validate_out = []
            rc = 0
            async for line in _run_cmd([tf, "validate", "-no-color", "-json"], tmpdir, timeout=30):
                if line.startswith("__RC__"):
                    rc = int(line[6:])
                else:
                    validate_out.append(line)
                    yield _sse("log", {"stage": "validate", "line": line})

            errors = _parse_validate_errors("\n".join(validate_out))
            if rc == 0:
                yield _sse("stage_done", {"stage": "validate", "passed": True, "attempts": attempt})
                break

            yield _sse("validate_errors", {"errors": errors, "attempt": attempt})

            if attempt >= 3:
                # AI fix exhausted — warn and continue to plan
                persistent_validate_errors = errors
                yield _sse("stage_done", {
                    "stage": "validate",
                    "passed": False,
                    "attempts": attempt,
                    "partial": True,   # signals frontend: continuing despite errors
                    "message": (
                        f"Validation has {len(errors)} error(s) that could not be auto-fixed after 2 AI attempts — "
                        "continuing to plan for other resources. Manual intervention required."
                    ),
                    "errors": errors,
                })
                break

            yield _sse("stage", {
                "stage": "codex_fix", "attempt": attempt,
                "message": f"🤖 Fixing the code...",
            })
            try:
                current_files = _read_files(tmpdir)
                fixed_files, change_report = _llm_fix_errors(current_files, errors, cloud, "validate")
                _write_files(fixed_files, tmpdir)
                current_files = fixed_files
                yield _sse("files_updated", {
                    "stage": "codex_fix", "attempt": attempt,
                    "files": [{"filename": f["filename"], "content": f["content"]} for f in fixed_files],
                    "changes": change_report,
                })
                yield _sse("stage_done", {"stage": "codex_fix", "passed": True, "attempt": attempt})
            except Exception as exc:
                yield _sse("log", {"stage": "validate", "line": f"[Codex fix error: {exc} — retrying validate as-is]"})
                yield _sse("stage_done", {"stage": "codex_fix", "passed": False, "attempt": attempt})

        # ── STAGE 4: terraform plan (with AI-fix retry loop) ─────────────
        if not actual_plan:
            msg = (
                "Plan skipped — no cloud credentials detected. "
                "Use the 🔑 Credentials panel to enter your cloud credentials, then enable 'Run plan'."
                if not has_creds else
                "Plan skipped by request."
            )
            yield _sse("stage", {"stage": "plan", "message": msg})
            yield _sse("stage_done", {"stage": "plan", "passed": True, "skipped": True, "message": msg})
            final_files = _read_files(tmpdir)
            yield _sse("done", {
                "passed": True,
                "plan_summary": None,
                "plan_skipped": True,
                "plan_skip_reason": msg,
                "validate_errors_persistent": persistent_validate_errors,
                "files": [{"filename": f["filename"], "content": f["content"], "description": ""} for f in final_files],
            })
            return

        plan_json_path = os.path.join(tmpdir, "_archlens_plan.json")
        plan_summary   = {}
        plan_passed    = False

        for plan_attempt in range(1, 4):  # max 3 attempts: 1 initial + 2 AI fix retries
            yield _sse("stage", {
                "stage": "plan",
                "attempt": plan_attempt,
                "message": "Running terraform plan..." if plan_attempt == 1 else f"Re-running terraform plan (attempt {plan_attempt}/3)...",
            })

            plan_out = []
            rc       = 0

            # Write dummy tfvars (may be updated if current_files changed)
            current_files = _read_files(tmpdir)
            _write_dummy_tfvars(current_files, tmpdir)

            async for line in _run_cmd(
                [
                    tf, "plan",
                    "-no-color",
                    "-json",
                    f"-out={os.path.join(tmpdir, 'tfplan')}",
                    f"-var-file={os.path.join(tmpdir, 'archlens_auto.tfvars')}",
                ],
                tmpdir,
                timeout=300,
                extra_env=env_vars,
            ):
                if line.startswith("__RC__"):
                    rc = int(line[6:])
                else:
                    plan_out.append(line)
                    yield _sse("log", {"stage": "plan", "line": line})

            with open(plan_json_path, "w") as fh:
                fh.write("\n".join(plan_out))

            plan_summary = _parse_plan_summary(plan_json_path)
            plan_passed  = rc == 0

            if plan_passed:
                yield _sse("stage_done", {
                    "stage": "plan",
                    "passed": True,
                    "attempts": plan_attempt,
                    "summary": plan_summary,
                })
                break

            # Plan failed — extract errors from JSON output
            plan_errors = _parse_plan_errors(plan_out)
            yield _sse("plan_errors", {"errors": plan_errors, "attempt": plan_attempt})

            if plan_attempt >= 3:
                yield _sse("stage_done", {
                    "stage": "plan",
                    "passed": False,
                    "rc": rc,
                    "attempts": plan_attempt,
                    "summary": plan_summary,
                })
                break

            # Run codex fix for plan errors
            yield _sse("stage", {
                "stage": "codex_fix",
                "attempt": plan_attempt,
                "message": f"🤖 Fixing the code...",
            })
            try:
                current_files = _read_files(tmpdir)
                fixed_files, change_report = _llm_fix_errors(current_files, plan_errors, cloud, "plan")
                _write_files(fixed_files, tmpdir)
                yield _sse("files_updated", {
                    "stage": "codex_fix",
                    "attempt": plan_attempt,
                    "files": [{"filename": f["filename"], "content": f["content"]} for f in fixed_files],
                    "changes": change_report,
                })
                yield _sse("stage_done", {
                    "stage": "codex_fix",
                    "passed": True,
                    "attempt": plan_attempt,
                })
            except Exception as exc:
                yield _sse("error", {
                    "stage": "codex_fix",
                    "message": f"Codex fix failed: {exc}",
                    "errors": plan_errors,
                })
                break

        # Final done
        final_files = _read_files(tmpdir)
        yield _sse("done", {
            "passed": plan_passed,
            "plan_summary": plan_summary,
            "validate_errors_persistent": persistent_validate_errors,
            "files": [{"filename": f["filename"], "content": f["content"], "description": f.get("description", "")} for f in final_files],
        })

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        _STREAM_SECRET_VALUES.reset(stream_secret_token)


# ── LLM fix helper ─────────────────────────────────────────────────────────────

async def _llm_fix_validate_errors(
    files: List[Dict],
    errors: List[str],
    cloud: str,
) -> List[Dict]:
    """
    Call the LLM (async) to fix terraform validate errors.
    Returns updated files dict list.
    """
    from app.services.terraform_service import _get_client
    from app.services.schema_fixer import fix_content
    from app.services.schema_fixer_rag import apply_rag_schema_fixes, get_schema_context

    client, model = _get_client()
    files_content = "\n\n".join(f"=== {f['filename']} ===\n{f['content']}" for f in files)
    errors_text   = "\n".join(f"- {e}" for e in errors)

    # Inject RAG schema context for resource types in the files
    rag_ctx = ""
    try:
        all_tf = "\n".join(f["content"] for f in files)
        rtypes = list(dict.fromkeys(re.findall(
            r'^resource\s+"([^"]+)"\s+"[^"]+"\s*\{', all_tf, re.MULTILINE
        )))
        if rtypes:
            rag_ctx = get_schema_context(rtypes, cloud)
    except Exception:
        pass

    schema_section = f"\n{rag_ctx}\n" if rag_ctx else ""

    prompt = f"""You are a Terraform expert. The following Terraform files FAILED `terraform validate` with these exact errors. Fix ONLY what is needed to make validation pass — do not restructure or rewrite unnecessarily.
{schema_section}
VALIDATION ERRORS (exact, from terraform validate):
{errors_text}

CURRENT FILES:
{files_content}

Rules:
1. Fix every error listed. Each error shows filename:line — use it to locate the issue.
2. If an argument is unsupported: remove it or replace it with the correct argument name.
3. If a reference is broken (e.g., module.foo.bar doesn't exist): fix the reference or use the correct output name.
4. NEVER remove the 'policy' argument from aws_iam_role_policy or aws_iam_policy resources.
5. Community modules: if using terraform-aws-modules/*, ensure module input names match the module's published interface.
6. Return COMPLETE file contents — all files, even unchanged ones.

Return ONLY valid JSON:
{{"files": [{{"filename": "<name>", "description": "<desc>", "content": "<full corrected HCL>"}}]}}"""

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a Terraform expert. Fix validation errors. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=16000,
            response_format={"type": "json_object"},
        ),
    )
    data = json.loads(response.choices[0].message.content)
    fixed = data.get("files", [])
    if not fixed:
        return files

    # Apply deterministic fixes on top of LLM output
    result = []
    for f in fixed:
        content = fix_content(f["filename"], f["content"])
        result.append({**f, "content": content})

    result = apply_rag_schema_fixes(result, cloud)
    return result


# ── Dummy tfvars ────────────────────────────────────────────────────────────────


def _parse_init_code_errors(output_lines: List[str]) -> List[str]:
    """
    Detect HCL code errors in terraform init output (duplicate outputs, bad refs, etc.)
    Returns non-empty list only when the error is a code problem we can AI-fix,
    not a module/provider download issue.
    """
    text = "\n".join(output_lines)
    # Patterns that indicate user-code errors (fixable by AI), not infra/download errors
    _CODE_ERROR_RE = re.compile(
        r"Duplicate (output|resource|variable|provider|module)\b"
        r"|An argument named .{1,80} is not expected"
        r"|Reference to undeclared"
        r"|Invalid expression"
        r"|Missing required argument"
        r"|Unsupported argument"
        r"|A single, reusable"
        r"|Output names must be unique"
        r"|Unreadable module subdirectory"
        r"|does not exist within the target module",
        re.IGNORECASE,
    )
    if not _CODE_ERROR_RE.search(text):
        return []  # Not a fixable code error

    errors: List[str] = []
    # Parse the box-drawing error blocks terraform emits
    lines = output_lines
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("╷") or ln.startswith("│ Error"):
            block: List[str] = []
            while i < len(lines):
                inner = lines[i].strip().lstrip("│╷╵╰ ").strip()
                if inner:
                    block.append(inner)
                if lines[i].strip().startswith("╵"):
                    break
                i += 1
            msg = " ".join(block).strip()
            if msg and msg not in errors:
                errors.append(msg)
        i += 1

    # Fallback: grab lines starting with "Error:"
    if not errors:
        for ln in lines:
            s = ln.strip()
            if s.startswith("Error:") or s.startswith("│ Error:"):
                errors.append(s.lstrip("│ ").strip())
    return errors


def _parse_plan_errors(plan_out: List[str]) -> List[str]:
    """Extract error diagnostics from terraform plan -json output lines."""
    errors = []
    for raw in plan_out:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("@level") != "error":
            continue
        diag    = obj.get("diagnostic", {})
        addr    = diag.get("address", "")
        summary = diag.get("summary", "")
        detail  = diag.get("detail", "")
        rng     = diag.get("range", {})
        fname   = rng.get("filename", "")
        line_no = rng.get("start", {}).get("line", "?")
        parts   = []
        if addr:
            parts.append(addr)
        if summary:
            parts.append(summary)
        if detail and detail.strip() != summary.strip():
            parts.append(detail.strip())
        if fname:
            parts.append(f"(in {fname}:{line_no})")
        msg = " — ".join(parts)
        if msg and msg not in errors:
            errors.append(msg)
    return errors


def _write_dummy_tfvars(files: List[Dict], tmpdir: str) -> None:
    """Write archlens_auto.tfvars with dummy values for all variables without defaults."""
    import re as _re
    var_block_re = _re.compile(r'variable\s+"([^"]+)"\s*\{([^}]*)\}', _re.DOTALL)
    required: Dict[str, str] = {}

    for f in files:
        if not f["filename"].endswith(".tf"):
            continue
        for m in var_block_re.finditer(f["content"]):
            name, body = m.group(1), m.group(2)
            if _re.search(r'\bdefault\b', body):
                continue
            t = _re.search(r'type\s*=\s*(\S+)', body)
            required[name] = t.group(1).lower() if t else "string"

    tfvars_path = os.path.join(tmpdir, "archlens_auto.tfvars")

    if not required:
        # Always create the file — plan command references it unconditionally
        with open(tfvars_path, "w") as fh:
            fh.write("# No variables require overrides — all have defaults\n")
        return

    lines = ["# Auto-generated dummy tfvars by ArchLens — replace before applying\n"]
    for name, vtype in required.items():
        n = name.lower()
        if "ami" in n:
            val = '"ami-00000000000000000"'
        elif "arn" in n:
            val = '"arn:aws:iam::123456789012:role/placeholder"'
        elif "password" in n or "secret" in n:
            val = '"ChangeMe123!"'
        elif "cidr" in n:
            val = '"10.0.0.0/16"'
        elif "domain" in n or "zone" in n:
            val = '"example.com"'
        elif "bucket" in n:
            val = '"archlens-placeholder-bucket"'
        elif "number" in vtype or "port" in n or "size" in n or "count" in n:
            val = "1"
        elif "bool" in vtype:
            val = "false"
        elif "list" in vtype or "set" in vtype:
            val = '["placeholder"]'
        elif "map" in vtype:
            val = '{"key" = "value"}'
        else:
            val = f'"{name}-placeholder"'
        lines.append(f"{name} = {val}")

    with open(tfvars_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
