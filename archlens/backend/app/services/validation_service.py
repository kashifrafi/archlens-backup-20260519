"""
Terraform Validation Service
Runs terraform fmt, tflint, checkov, terraform validate against generated .tf files
and returns a structured report with per-check results and an overall score.
"""
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from typing import Dict, List, Optional, Tuple

import requests

from app.config import settings

logger = logging.getLogger(__name__)

# Look for tools in user's ~/.local/bin first, then PATH
_EXTRA_PATH = os.path.expanduser("~/.local/bin")


def _sensitive_values() -> List[str]:
    setting_names = [
        "aws_access_key_id",
        "aws_secret_access_key",
        "gcp_api_key",
        "gcp_service_account_key",
        "azure_openai_api_key",
        "azure_foundry_api_key",
        "azure_openai_embedding_api_key",
        "openai_api_key",
        "pinecone_api_key",
        "hcp_terraform_token",
    ]
    env_names = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "ARM_CLIENT_ID",
        "ARM_CLIENT_SECRET",
        "ARM_TENANT_ID",
        "ARM_SUBSCRIPTION_ID",
        "GOOGLE_CREDENTIALS",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GCP_API_KEY",
        "HCP_TERRAFORM_TOKEN",
        "OPENAI_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_FOUNDRY_API_KEY",
    ]
    values = []
    for name in setting_names:
        value = getattr(settings, name, None)
        if value:
            values.append(str(value))
    for name in env_names:
        value = os.environ.get(name)
        if value:
            values.append(str(value))
    return sorted({v for v in values if len(v) >= 4}, key=len, reverse=True)


def _mask_sensitive_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    masked = text
    for value in _sensitive_values():
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


def _mask_result(obj):
    if isinstance(obj, str):
        return _mask_sensitive_text(obj)
    if isinstance(obj, list):
        return [_mask_result(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _mask_result(value) for key, value in obj.items()}
    return obj


def _which(cmd: str) -> Optional[str]:
    full = os.path.join(_EXTRA_PATH, cmd)
    if os.path.isfile(full) and os.access(full, os.X_OK):
        return full
    return shutil.which(cmd)


def _run(cmd: List[str], cwd: str, timeout: int = 60) -> Tuple[int, str, str]:
    env = os.environ.copy()
    env["PATH"] = _EXTRA_PATH + ":" + env.get("PATH", "")
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"Command timed out after {timeout}s"
    except FileNotFoundError:
        return 1, "", f"Tool not found: {cmd[0]}"


def _write_tf_files(files: List[Dict], tmpdir: str):
    """Write TerraformFile list to a temp directory."""
    for f in files:
        path = os.path.join(tmpdir, f["filename"])
        with open(path, "w") as fh:
            fh.write(f["content"])


# ─── Individual checks ────────────────────────────────────────────────────────

def _run_fmt(tmpdir: str) -> Dict:
    tf = _which("terraform")
    if not tf:
        return {"passed": False, "tool": "terraform fmt", "skipped": True,
                "message": "terraform not installed", "details": [], "score": 0}

    rc, stdout, stderr = _run([tf, "fmt", "-check", "-diff", "."], tmpdir)
    passed = rc == 0
    details = []
    if not passed:
        for line in stdout.splitlines():
            if line.strip():
                details.append(line.strip())
    return {
        "passed": passed,
        "tool": "terraform fmt",
        "skipped": False,
        "message": "Syntax formatting OK" if passed else f"{len(details)} formatting issue(s)",
        "details": details,
        "score": 100 if passed else max(0, 100 - len(details) * 20),
    }


def _run_tflint(tmpdir: str) -> Dict:
    tflint = _which("tflint")
    if not tflint:
        return {"passed": False, "tool": "tflint", "skipped": True,
                "message": "tflint not installed", "details": [], "score": 0}

    # init (ignore network errors - we just want rule checks)
    _run([tflint, "--init"], tmpdir, timeout=30)
    rc, stdout, stderr = _run([tflint, "--format", "json", "."], tmpdir)

    details = []
    try:
        result = json.loads(stdout)
        issues = result.get("issues", [])
        for issue in issues:
            sev = issue.get("rule", {}).get("severity", "warning")
            msg = issue.get("message", "")
            rng = issue.get("range", {})
            fname = rng.get("filename", "")
            line = rng.get("start", {}).get("line", "?")
            details.append(f"[{sev.upper()}] {fname}:{line} — {msg}")
        errors = [i for i in issues if i.get("rule", {}).get("severity") == "error"]
        passed = len(errors) == 0
    except (json.JSONDecodeError, Exception):
        # fallback plain text
        passed = rc == 0
        out = (stdout + stderr).strip()
        if out:
            details = [l for l in out.splitlines() if l.strip()]

    score = max(0, 100 - len(details) * 15) if not passed else 100
    return {
        "passed": passed,
        "tool": "tflint",
        "skipped": False,
        "message": "No linting issues" if passed else f"{len(details)} issue(s) found",
        "details": details,
        "score": score,
    }


def _run_checkov(tmpdir: str) -> Dict:
    checkov = _which("checkov")
    # also check venv
    venv_checkov = os.path.join(
        os.path.dirname(__file__), "..", "..", ".venv", "bin", "checkov"
    )
    venv_checkov = os.path.abspath(venv_checkov)
    if not checkov and os.path.isfile(venv_checkov):
        checkov = venv_checkov

    if not checkov:
        return {"passed": False, "tool": "checkov", "skipped": True,
                "message": "checkov not installed", "details": [], "score": 0,
                "passed_checks": 0, "failed_checks": 0}

    rc, stdout, stderr = _run(
        [checkov, "-d", tmpdir, "--framework", "terraform", "-o", "json", "--quiet"],
        tmpdir, timeout=120,
    )

    passed_count = 0
    failed_count = 0
    details = []
    try:
        # checkov may output multiple JSON objects; take the last valid one
        data = None
        for chunk in stdout.split("\n\n"):
            chunk = chunk.strip()
            if chunk.startswith("{"):
                try:
                    data = json.loads(chunk)
                except Exception:
                    pass
        if data is None:
            data = json.loads(stdout)

        results = data.get("results", {})
        passed_count = len(results.get("passed_checks", []))
        failed_count = len(results.get("failed_checks", []))
        for chk in results.get("failed_checks", []):
            chk_id = chk.get("check_id", "")
            # checkov v3.x uses 'check_name' for the human-readable description;
            # 'check' is None in v3.x, a dict in older versions, a string in some.
            chk_name = chk.get("check_name") or ""
            if not chk_name:
                check_field = chk.get("check", "")
                if isinstance(check_field, dict):
                    chk_name = check_field.get("name", "") or ""
                elif isinstance(check_field, str):
                    chk_name = check_field
            if not chk_name:
                chk_name = chk.get("description") or chk.get("short_description") or ""
            resource = chk.get("resource", "")
            severity = chk.get("severity") or "MEDIUM"   # can be None
            file_path = os.path.basename(chk.get("file_path", ""))
            file_line = chk.get("file_line_range", ["?", "?"])
            line_info = f"{file_path}:L{file_line[0]}" if file_path else ""
            details.append(f"[{severity}] {chk_id} — {chk_name} | resource: {resource} | {line_info}")
    except (json.JSONDecodeError, Exception):
        out = (stdout + stderr).strip()
        details = [l for l in out.splitlines() if l.strip() and "passed" not in l.lower()]
        failed_count = len(details)

    total = passed_count + failed_count
    score = int((passed_count / total) * 100) if total > 0 else 100
    passed = failed_count == 0

    return {
        "passed": passed,
        "tool": "checkov",
        "skipped": False,
        "message": f"{passed_count} passed, {failed_count} failed" if total > 0 else "No checks run",
        "details": details,
        "score": score,
        "passed_checks": passed_count,
        "failed_checks": failed_count,
    }


def _run_validate(tmpdir: str) -> Dict:
    tf = _which("terraform")
    if not tf:
        return {"passed": False, "tool": "terraform validate", "skipped": True,
                "message": "terraform not installed", "details": [], "score": 0}

    # terraform init with -backend=false to skip real provider auth
    rc_init, _, err_init = _run(
        [tf, "init", "-backend=false", "-no-color", "-input=false"], tmpdir, timeout=60
    )

    rc, stdout, stderr = _run([tf, "validate", "-no-color", "-json"], tmpdir)

    details = []
    passed = False
    try:
        data = json.loads(stdout)
        passed = data.get("valid", False)
        for diag in data.get("diagnostics", []):
            sev = diag.get("severity", "error").upper()
            summary = diag.get("summary", "")
            detail = diag.get("detail", "")
            rng = diag.get("range", {})
            fname = rng.get("filename", "")
            line = rng.get("start", {}).get("line", "")
            loc = f" {fname}:{line}" if fname else ""
            details.append(f"[{sev}]{loc} {summary}" + (f" — {detail}" if detail else ""))
    except (json.JSONDecodeError, Exception):
        out = (stdout + stderr).strip()
        passed = rc == 0
        if out:
            details = [l for l in out.splitlines() if l.strip()][:15]

    return {
        "passed": passed,
        "tool": "terraform validate",
        "skipped": False,
        "message": "Configuration is valid" if passed else f"{len(details)} error(s)",
        "details": details,
        "score": 100 if passed else 0,
    }


def _run_trivy(tmpdir: str) -> Dict:
    trivy = _which("trivy")
    if not trivy:
        return {
            "passed": False, "tool": "trivy", "skipped": True,
            "message": "trivy not installed — install via: brew install trivy or apt-get install trivy",
            "details": [], "score": 0,
        }

    rc, stdout, stderr = _run(
        [trivy, "config", "--format", "json", "--quiet", "."],
        tmpdir, timeout=120,
    )

    details = []
    passed = False
    try:
        data = json.loads(stdout)
        for res in data.get("Results", []) or []:
            for m in res.get("Misconfigurations", []) or []:
                sev = m.get("Severity", "UNKNOWN")
                title = m.get("Title", "")
                chk_id = m.get("ID", "")
                resource = res.get("Target", "")
                details.append(f"[{sev}] {chk_id} — {title} | {resource}")
        passed = len(details) == 0
    except (json.JSONDecodeError, Exception):
        out = (stdout + stderr).strip()
        passed = rc == 0
        if out:
            details = [l for l in out.splitlines() if l.strip()][:20]

    score = max(0, 100 - len(details) * 10) if not passed else 100
    return {
        "passed": passed,
        "tool": "trivy",
        "skipped": False,
        "message": "No misconfigurations found" if passed else f"{len(details)} misconfiguration(s) found",
        "details": details,
        "score": score,
    }



def _sanitize_files(files: List[Dict]) -> List[Dict]:
    """
    Apply all AWS v5/v6 provider schema fixes to file content before validation.
    Pass 1: hardcoded schema_fixer transforms (known breaking changes).
    Pass 2: RAG-based strip of removed_args + deprecated_args from ChromaDB registry docs.
    Returns a new list; originals are not mutated.
    """
    from app.services.schema_fixer import fix_content
    from app.services.schema_fixer_rag import apply_rag_schema_fixes

    result = []
    for f in files:
        filename = f.get("filename", "")
        if not filename.endswith(".tf"):
            result.append(f)
            continue
        fixed = fix_content(filename, f["content"])
        if fixed != f["content"]:
            logger.info("_sanitize_files: patched schema issues in %s", filename)
            result.append({**f, "content": fixed})
        else:
            result.append(f)

    # RAG pass: deterministically strip removed/deprecated args for all resource types
    result = apply_rag_schema_fixes(result, "aws")
    return result


def _inject_dummy_tfvars(tmpdir: str) -> None:
    """
    Parse all variable blocks in .tf files. For any variable with no 'default',
    write a smart dummy entry into archlens_auto.tfvars so HCP speculative plans
    don't fail with 'No value for required variable'.
    """
    var_block_re = re.compile(r'variable\s+"([^"]+)"\s*\{([^}]*)\}', re.DOTALL)
    required_vars: Dict[str, str] = {}

    for fname in os.listdir(tmpdir):
        if not fname.endswith(".tf"):
            continue
        try:
            content = open(os.path.join(tmpdir, fname)).read()
        except OSError:
            continue
        for m in var_block_re.finditer(content):
            var_name, body = m.group(1), m.group(2)
            if re.search(r'\bdefault\b', body):
                continue
            type_m   = re.search(r'type\s*=\s*(\S+)', body)
            var_type = type_m.group(1).lower() if type_m else "string"
            required_vars[var_name] = var_type

    if not required_vars:
        return

    def _dummy(name: str, vtype: str) -> str:  # noqa: C901
        n = name.lower()

        # ── AWS resource identifiers ──────────────────────────────────────────
        if re.search(r'ami[_\-]?id|_ami$|^ami$', n):
            return '"ami-00000000000000000"'
        if re.search(r'certificate_arn|certificate', n):
            return '"arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000000"'
        if re.search(r'kms.*arn|kms.*key', n):
            return '"arn:aws:kms:us-east-1:123456789012:key/00000000-0000-0000-0000-000000000000"'
        if re.search(r'iam.*arn|role.*arn|instance.*profile', n):
            return '"arn:aws:iam::123456789012:role/placeholder-role"'
        if re.search(r'sns.*arn|topic.*arn', n):
            return '"arn:aws:sns:us-east-1:123456789012:placeholder-topic"'
        if re.search(r'sqs.*arn|queue.*arn', n):
            return '"arn:aws:sqs:us-east-1:123456789012:placeholder-queue"'
        if re.search(r'lambda.*arn|function.*arn', n):
            return '"arn:aws:lambda:us-east-1:123456789012:function:placeholder"'
        if re.search(r'arn', n):
            return '"arn:aws:iam::123456789012:role/placeholder"'

        # ── IDs ───────────────────────────────────────────────────────────────
        if re.search(r'vpc_id$|^vpc_id', n):
            return '"vpc-00000000000000000"'
        if re.search(r'subnet_ids|private_subnets|public_subnets', n):
            return '["subnet-00000000000000000", "subnet-11111111111111111"]'
        if re.search(r'subnet_id$', n):
            return '"subnet-00000000000000000"'
        if re.search(r'security_group_ids|sg_ids', n):
            return '["sg-00000000000000000"]'
        if re.search(r'security_group_id$', n):
            return '"sg-00000000000000000"'
        if re.search(r'route_table_id', n):
            return '"rtb-00000000000000000"'
        if re.search(r'internet_gateway_id|igw_id', n):
            return '"igw-00000000000000000"'
        if re.search(r'nat_gateway_id', n):
            return '"nat-00000000000000000"'
        if re.search(r'load_balancer_id|alb_id|elb_id|nlb_id', n):
            return '"arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/placeholder/0000000000000000"'
        if re.search(r'target_group_arn|tg_arn', n):
            return '"arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/placeholder/0000000000000000"'
        if re.search(r'instance_id', n):
            return '"i-00000000000000000"'
        if re.search(r'snapshot_id', n):
            return '"snap-00000000000000000"'
        if re.search(r'volume_id', n):
            return '"vol-00000000000000000"'
        if re.search(r'cluster_id', n):
            return '"placeholder-cluster-id"'
        if re.search(r'hosted_zone_id|zone_id', n):
            return '"Z00000000000000000000"'
        if re.search(r'log_group', n):
            return '"/aws/placeholder/log-group"'
        if re.search(r'account_id|aws_account', n):
            return '"123456789012"'
        if re.search(r'organization_id|org_id', n):
            return '"o-0000000000"'

        # ── Credentials ───────────────────────────────────────────────────────
        if re.search(r'password|passwd', n):
            return '"Placeholder@12345"'
        if re.search(r'secret_key|access_key|api_key|auth_token|token', n):
            return '"placeholder_secret_key_000000000000"'
        if re.search(r'secret', n):
            return '"placeholder_secret_value"'
        if re.search(r'username|user_name|db_user', n):
            return '"placeholder_user"'
        if re.search(r'private_key|pem', n):
            return '"placeholder_private_key"'

        # ── Networking ────────────────────────────────────────────────────────
        if re.search(r'allowed_cidr|ingress_cidr|egress_cidr|whitelist|cidr_blocks', n):
            return '["10.0.0.0/8"]'
        if re.search(r'cidr_block|cidr', n):
            return '"10.0.0.0/16"'
        if re.search(r'ip_address|public_ip|private_ip|elastic_ip', n):
            return '"10.0.0.1"'
        if re.search(r'dns_name|fqdn|endpoint', n):
            return '"placeholder.us-east-1.elb.amazonaws.com"'
        if re.search(r'port$|_port$', n):
            return '8080'
        if re.search(r'ports', n):
            return '[80, 443]'
        if re.search(r'protocol', n):
            return '"HTTP"'

        # ── Storage / S3 ──────────────────────────────────────────────────────
        if re.search(r'bucket_name|bucket', n):
            return '"placeholder-bucket-123456"'
        if re.search(r's3_key|object_key|prefix', n):
            return '"placeholder/key"'
        if re.search(r'storage_class', n):
            return '"STANDARD"'

        # ── Database ──────────────────────────────────────────────────────────
        if re.search(r'db_name|database_name', n):
            return '"placeholder_db"'
        if re.search(r'db_port|database_port', n):
            return '5432'
        if re.search(r'db_engine|engine_version', n):
            return '"postgres"'
        if re.search(r'db_instance_class|instance_class', n):
            return '"db.t3.micro"'
        if re.search(r'db_storage|allocated_storage', n):
            return '20'
        if re.search(r'db_identifier|db_id', n):
            return '"placeholder-db"'
        if re.search(r'db_host|rds_host|database_host', n):
            return '"placeholder.rds.amazonaws.com"'

        # ── Compute ───────────────────────────────────────────────────────────
        if re.search(r'instance_type', n):
            return '"t3.micro"'
        if re.search(r'key_name|key_pair', n):
            return '"placeholder-keypair"'
        if re.search(r'ecs_cluster|cluster_name', n):
            return '"placeholder-cluster"'
        if re.search(r'container_image|image_uri|ecr_image|docker_image', n):
            return '"123456789012.dkr.ecr.us-east-1.amazonaws.com/placeholder:latest"'
        if re.search(r'container_name', n):
            return '"placeholder-container"'
        if re.search(r'task_definition', n):
            return '"placeholder-task:1"'
        if re.search(r'launch_type', n):
            return '"FARGATE"'
        if re.search(r'cpu$|^cpu|vcpu', n):
            return '256'
        if re.search(r'memory$|mem$', n):
            return '512'
        if re.search(r'gpu', n):
            return '0'

        # ── Auto Scaling ──────────────────────────────────────────────────────
        if re.search(r'min_size|min_capacity|min_count', n):
            return '1'
        if re.search(r'max_size|max_capacity|max_count', n):
            return '3'
        if re.search(r'desired_capacity|desired_count', n):
            return '1'
        if re.search(r'health_check_interval|interval', n):
            return '30'
        if re.search(r'health_check_threshold|threshold', n):
            return '2'
        if re.search(r'cooldown|grace_period', n):
            return '300'
        if re.search(r'timeout', n):
            return '60'

        # ── DNS / Domain ──────────────────────────────────────────────────────
        if re.search(r'domain_name|domain|hosted_zone_name', n):
            return '"example.com"'
        if re.search(r'subdomain', n):
            return '"app.example.com"'
        if re.search(r'email', n):
            return '"placeholder@example.com"'

        # ── Location / Cloud ──────────────────────────────────────────────────
        if re.search(r'region|aws_region', n):
            return '"us-east-1"'
        if re.search(r'availability_zone$', n):
            return '"us-east-1a"'
        if re.search(r'availability_zones', n):
            return '["us-east-1a", "us-east-1b"]'
        if re.search(r'environment|env$', n):
            return '"dev"'
        if re.search(r'namespace', n):
            return '"placeholder-ns"'
        if re.search(r'^name$|_name$|resource_name', n):
            return '"placeholder-name"'
        if re.search(r'tags$', n):
            return '{}'

        # ── Lambda / Serverless ───────────────────────────────────────────────
        if re.search(r'runtime', n):
            return '"python3.11"'
        if re.search(r'handler', n):
            return '"index.handler"'
        if re.search(r'function_name|lambda_name', n):
            return '"placeholder-function"'
        if re.search(r'layer_arn', n):
            return '"arn:aws:lambda:us-east-1:123456789012:layer:placeholder:1"'

        # ── Monitoring ────────────────────────────────────────────────────────
        if re.search(r'alarm_name', n):
            return '"placeholder-alarm"'
        if re.search(r'metric_name', n):
            return '"CPUUtilization"'
        if re.search(r'namespace', n):
            return '"AWS/EC2"'
        if re.search(r'evaluation_period', n):
            return '2'
        if re.search(r'statistic', n):
            return '"Average"'

        # ── Misc flags / counts ───────────────────────────────────────────────
        if re.search(r'enable|enabled|create|use_|allow|force|multi_az|deletion_protection|encrypt', n):
            return 'false'
        if re.search(r'count$|_count$|size$|num$|number_of', n):
            return '1'
        if re.search(r'retention|days|ttl|expiry', n):
            return '7'
        if re.search(r'version$|engine_version', n):
            return '"1.0"'
        if re.search(r'log_level|level', n):
            return '"INFO"'

        # ── Type-based fallbacks ──────────────────────────────────────────────
        if 'number' in vtype:   return '0'
        if 'bool'   in vtype:   return 'false'
        if vtype.startswith('list'):             return '[]'
        if vtype.startswith(('map', 'object')):  return '{}'
        return '"placeholder"'

    lines = ['# Auto-generated by ArchLens for HCP speculative plan\n']
    for var_name, var_type in sorted(required_vars.items()):
        lines.append(f'{var_name} = {_dummy(var_name, var_type)}\n')

    with open(os.path.join(tmpdir, "archlens_auto.tfvars"), "w") as fh:
        fh.writelines(lines)
    logger.info("Injected dummy tfvars for %d variable(s): %s",
                len(required_vars), list(required_vars.keys()))


def _run_hcp_plan(tmpdir: str) -> Dict:
    """
    Run a speculative plan on HCP Terraform (Terraform Cloud).
    Flow:
      1. Get or create workspace
      2. Ensure AWS vars are set on workspace
      3. Create a speculative configuration version
      4. Upload .tf files as tar.gz
      5. Poll for the plan to complete
      6. Fetch and return plan output logs
    """
    token    = settings.hcp_terraform_token or os.environ.get("HCP_TERRAFORM_TOKEN")
    org      = settings.hcp_org_name or os.environ.get("HCP_ORG_NAME", "")
    ws_name  = settings.hcp_workspace or os.environ.get("HCP_WORKSPACE", "archlens-validator")

    if not token or not org:
        return {
            "passed": True, "tool": "HCP plan", "skipped": True,
            "message": "Pro tier — set HCP_TERRAFORM_TOKEN + HCP_ORG_NAME to enable",
            "details": [], "score": 100,
        }

    BASE = "https://app.terraform.io/api/v2"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/vnd.api+json",
    }

    def api(method, path, **kwargs):
        resp = requests.request(method, f"{BASE}{path}", headers=headers, timeout=30, **kwargs)
        if resp.status_code not in (200, 201, 202, 204):
            raise RuntimeError(f"HCP API {method} {path} → {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    try:
        # 1. Get or create workspace
        ws_id = None
        try:
            data = api("GET", f"/organizations/{org}/workspaces/{ws_name}")
            ws_id = data["data"]["id"]
        except RuntimeError:
            # Create workspace with auto-apply=false, execution-mode=remote
            body = {"data": {"type": "workspaces", "attributes": {
                "name": ws_name,
                "auto-apply": False,
                "execution-mode": "remote",
                "terraform-version": "1.7.5",
            }}}
            data = api("POST", f"/organizations/{org}/workspaces", json=body)
            ws_id = data["data"]["id"]

        # 2. Ensure AWS env vars are set on the workspace
        aws_key    = settings.aws_access_key_id or os.environ.get("AWS_ACCESS_KEY_ID", "")
        aws_secret = settings.aws_secret_access_key or os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        if aws_key and aws_secret:
            # List existing vars
            existing = api("GET", f"/workspaces/{ws_id}/vars")
            existing_keys = {v["attributes"]["key"]: v["id"] for v in existing.get("data", [])}
            for var_key, var_val, sensitive in [
                ("AWS_ACCESS_KEY_ID",     aws_key,    True),
                ("AWS_SECRET_ACCESS_KEY", aws_secret, True),
            ]:
                payload = {"data": {"type": "vars", "attributes": {
                    "key": var_key, "value": var_val,
                    "category": "env", "sensitive": sensitive, "hcl": False,
                }}}
                if var_key not in existing_keys:
                    # Only create — never PATCH sensitive vars (HCP disallows it)
                    api("POST", f"/workspaces/{ws_id}/vars", json=payload)

        # 3. Create a speculative configuration version
        cv_body = {"data": {"type": "configuration-versions", "attributes": {
            "auto-queue-runs": False,
            "speculative": True,
        }}}
        cv_data   = api("POST", f"/workspaces/{ws_id}/configuration-versions", json=cv_body)
        cv_id     = cv_data["data"]["id"]
        upload_url = cv_data["data"]["attributes"]["upload-url"]

        # 4. Inject dummy tfvars for any required variables that have no default
        _inject_dummy_tfvars(tmpdir)

        # 5. Build tar.gz of .tf files and upload
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tf_archive:
            archive_path = tf_archive.name
        with tarfile.open(archive_path, "w:gz") as tar:
            for fname in os.listdir(tmpdir):
                if fname.endswith(".tf") or fname.endswith(".tfvars"):
                    tar.add(os.path.join(tmpdir, fname), arcname=fname)
        with open(archive_path, "rb") as fh:
            upload_resp = requests.put(
                upload_url,
                data=fh,
                headers={"Content-Type": "application/octet-stream"},
                timeout=60,
            )
        os.unlink(archive_path)
        if upload_resp.status_code not in (200, 201, 204):
            raise RuntimeError(f"Config upload failed: {upload_resp.status_code}")

        # 5. Trigger a speculative run
        run_body = {"data": {"type": "runs", "attributes": {
            "is-destroy": False,
            "message": "ArchLens speculative plan",
        }, "relationships": {
            "workspace":             {"data": {"type": "workspaces", "id": ws_id}},
            "configuration-version": {"data": {"type": "configuration-versions", "id": cv_id}},
        }}}
        run_data = api("POST", "/runs", json=run_body)
        run_id   = run_data["data"]["id"]

        # 6. Poll until plan finishes (max 3 min)
        terminal = {"planned", "planned_and_finished", "errored", "canceled", "force_canceled", "discarded"}
        status = ""
        for _ in range(36):  # 36 × 5s = 3 min
            time.sleep(5)
            rd = api("GET", f"/runs/{run_id}")
            status = rd["data"]["attributes"]["status"]
            if status in terminal:
                break

        # 7. Fetch plan log — always retrieve full text log for inline display
        plan_id = rd["data"]["relationships"].get("plan", {}).get("data", {}).get("id")
        details = []
        plan_log = ""
        if plan_id:
            # Always fetch the full human-readable text log
            try:
                plan_meta = api("GET", f"/plans/{plan_id}")
                log_link = plan_meta["data"]["attributes"].get("log-read-url", "")
                if log_link:
                    plan_log = requests.get(log_link, timeout=30).text
            except Exception:
                pass

            # Try structured resource change summary
            try:
                log_resp = api("GET", f"/plans/{plan_id}/json-output")
                for chg in log_resp.get("resource_changes", []):
                    actions = chg.get("change", {}).get("actions", [])
                    if set(actions) - {"no-op", "read"}:
                        res = chg.get("address", "")
                        details.append(f"[CHANGE] {res}: {' + '.join(actions)}")
            except Exception:
                # Fall back to key lines from text log when json-output unavailable
                if plan_log:
                    details = [l for l in plan_log.splitlines() if l.strip()][:50]

        errored = status == "errored"
        passed  = not errored
        score   = 100 if passed else 50
        msg     = f"Speculative plan {status}" + (f" — {len(details)} change(s)" if details else "")

        run_url = f"https://app.terraform.io/app/{org}/workspaces/{ws_name}/runs/{run_id}"
        details.insert(0, f"Run: {run_url}")

        return {
            "passed": passed, "tool": "HCP plan", "skipped": False,
            "message": msg, "details": details, "score": score,
            "plan_log": plan_log,
        }

    except Exception as exc:
        logger.exception("HCP plan failed")
        return {
            "passed": False, "tool": "HCP plan", "skipped": False,
            "message": f"HCP plan error: {str(exc)[:120]}",
            "details": [], "score": 0,
        }


# ─── Public API ───────────────────────────────────────────────────────────────

def validate_terraform(files: List[Dict]) -> Dict:
    """
    Run all 6 validation tools against the provided Terraform files.
    Returns a structured report with per-check results and overall_score.
    """
    with tempfile.TemporaryDirectory(prefix="archlens_tf_") as tmpdir:
        _write_tf_files(_sanitize_files(files), tmpdir)

        fmt_result      = _run_fmt(tmpdir)
        validate_result = _run_validate(tmpdir)
        tflint_result   = _run_tflint(tmpdir)
        checkov_result  = _run_checkov(tmpdir)
        trivy_result    = _run_trivy(tmpdir)
        hcp_result      = _run_hcp_plan(tmpdir)

    checks = [fmt_result, validate_result, tflint_result, checkov_result, trivy_result, hcp_result]

    # Weighted overall score: fmt 10%, validate 15%, tflint 15%, checkov 35%, trivy 15%, hcp 10%
    weights = [0.10, 0.15, 0.15, 0.35, 0.15, 0.10]
    scores = [c["score"] for c in checks]
    overall_score = int(sum(s * w for s, w in zip(scores, weights)))

    passed_all = all(c["passed"] or c.get("skipped") for c in checks)

    return _mask_result({
        "fmt":           fmt_result,
        "validate":      validate_result,
        "tflint":        tflint_result,
        "checkov":       checkov_result,
        "trivy":         trivy_result,
        "hcp_plan":      hcp_result,
        "overall_score": overall_score,
        "passed":        passed_all,
        "summary":       _build_summary(checks, overall_score),
    })


def run_hcp_plan(files: List[Dict]) -> Dict:
    """Run only the HCP speculative plan — used for fast re-runs from the UI."""
    with tempfile.TemporaryDirectory(prefix="archlens_hcp_") as tmpdir:
        _write_tf_files(_sanitize_files(files), tmpdir)
        return _mask_result(_run_hcp_plan(tmpdir))


def _build_summary(checks: List[Dict], score: int) -> str:
    failed = [c["tool"] for c in checks if not c["passed"] and not c.get("skipped")]
    if not failed:
        return f"All checks passed — overall score {score}/100"
    return f"{len(failed)} check(s) need attention: {', '.join(failed)} — score {score}/100"
