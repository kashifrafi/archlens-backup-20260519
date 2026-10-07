import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
from typing import AsyncGenerator, Dict, List, Optional, Tuple
from openai import AzureOpenAI, OpenAI

logger = logging.getLogger(__name__)

from app.config import settings
from app.services.schema_fixer import apply_aws_schema_fixes
from app.services.schema_fixer_rag import apply_rag_schema_fixes, get_schema_context
from app.services import module_schema_rag
from app.models.schemas import (
    DiagramAnalysisResponse,
    CloudProvider,
    TerraformGenerateResponse,
    TerraformFile,
    UserContext,
)
from app.services.context_helper import format_user_context


from app.services.foundry_client import create_foundry_client


def _get_client():
    """
    Get AI client for Terraform generation.
    Uses Azure AI Foundry (GPT-5.3-codex) if available, falls back to Azure OpenAI or OpenAI.
    """
    # Prefer Azure AI Foundry for Terraform generation (GPT-5.3-codex)
    if settings.azure_foundry_endpoint and settings.azure_foundry_api_key:
        client = create_foundry_client(
            endpoint=settings.azure_foundry_endpoint,
            api_key=settings.azure_foundry_api_key,
            model=settings.azure_foundry_deployment,
            api_version=settings.azure_foundry_api_version
        )
        return client, settings.azure_foundry_deployment
    # Fallback to standard Azure OpenAI
    elif settings.azure_openai_endpoint and settings.azure_openai_api_key:
        return AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        ), settings.azure_openai_deployment
    elif settings.openai_api_key:
        return OpenAI(api_key=settings.openai_api_key), settings.openai_model
    else:
        raise ValueError("No AI API credentials configured.")


_EXTRA_PATH = os.path.expanduser("~/.local/bin")


def _which_tf() -> Optional[str]:
    import shutil
    full = os.path.join(_EXTRA_PATH, "terraform")
    if os.path.isfile(full) and os.access(full, os.X_OK):
        return full
    return shutil.which("terraform")


# ─── Rock-solid HCL Syntax Fixer (must run BEFORE terraform fmt) ───────────────


def _fix_hcl_syntax(files: List[TerraformFile]) -> List[TerraformFile]:
    """
    Rock-solid HCL syntax corrector. Runs BEFORE terraform fmt to ensure that
    LLM-generated invalid syntax is fixed first (terraform fmt is a no-op on
    syntactically broken files and silently returns the original).

    Applies in order:
      1. _hcl_fix_inline_block_opens  – the #1 LLM mistake: attribute on same line as {
      2. _hcl_fix_quoted_types         – type = "string"  →  type = string
      3. _hcl_fix_trailing_commas      – value = "foo",   →  value = "foo"
      4. _hcl_fix_single_quotes        – value = 'foo'    →  value = "foo"
      5. _hcl_fix_semicolons           – value = "foo";   →  value = "foo"
      6. _hcl_fix_missing_equals       – default "val"    →  default = "val"
    """
    result = []
    for f in files:
        if not f.filename.endswith('.tf'):
            result.append(f)
            continue
        content = f.content
        content = _hcl_fix_inline_block_opens(content)
        content = _hcl_fix_quoted_types(content)
        content = _hcl_fix_trailing_commas(content)
        content = _hcl_fix_single_quotes(content)
        content = _hcl_fix_semicolons(content)
        content = _hcl_fix_missing_equals(content)
        result.append(TerraformFile(filename=f.filename, content=content, description=f.description))
    return result


def _find_block_end(content: str, brace_start: int) -> int:
    depth = 0
    in_string = False
    escape = False
    for idx in range(brace_start, len(content)):
        ch = content[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return idx + 1
    return len(content)


def _extract_top_level_blocks(content: str, block_types: Tuple[str, ...]) -> Tuple[str, List[str]]:
    pattern = re.compile(r'(?m)^\s*(' + "|".join(block_types) + r')\s+"[^"]+"(?:\s+"[^"]+")?\s*\{')
    blocks: List[Tuple[int, int, str]] = []
    for match in pattern.finditer(content):
        brace_start = content.find("{", match.start())
        if brace_start == -1:
            continue
        end = _find_block_end(content, brace_start)
        blocks.append((match.start(), end, content[match.start():end].strip()))
    if not blocks:
        return content, []
    parts = []
    cursor = 0
    extracted = []
    for start, end, block in blocks:
        parts.append(content[cursor:start])
        extracted.append(block)
        cursor = end
    parts.append(content[cursor:])
    remaining = re.sub(r'\n{3,}', '\n\n', "".join(parts)).strip() + "\n"
    return remaining, extracted


def _variable_default_for_name(name: str) -> str:
    n = name.lower()
    if "tags" in n:
        return "{}"
    if "count" in n or "size" in n or "number" in n:
        return "1"
    if "cidr" in n:
        return '"10.0.0.0/16"'
    if "region" in n:
        return '"us-east-1"'
    if "zone" in n:
        return '["us-east-1a", "us-east-1b"]' if n.endswith("s") else '"us-east-1a"'
    if "password" in n or "secret" in n or "token" in n or "key" in n:
        return '"xxxxxxxx"'
    return '"placeholder"'


def _variable_block(name: str) -> str:
    default = _variable_default_for_name(name)
    if default in ("{}", "[]") or default.startswith("["):
        type_line = "  type    = any"
    elif default in ("1", "0"):
        type_line = "  type    = number"
    elif default in ("true", "false"):
        type_line = "  type    = bool"
    else:
        type_line = "  type    = string"
    return f'variable "{name}" {{\n{type_line}\n  default = {default}\n}}'


def _file_map(files: List[TerraformFile]) -> Dict[str, TerraformFile]:
    return {f.filename.replace("\\", "/"): f for f in files}


def _ensure_modular_hierarchy(files: List[TerraformFile]) -> List[TerraformFile]:
    """Guarantee root/module hierarchy even when the LLM returns flat Terraform."""
    mapped = _file_map(files)
    root_main = mapped.get("main.tf")
    if not root_main:
        return files

    main_without_resources, root_blocks = _extract_top_level_blocks(root_main.content, ("resource", "data"))
    has_module_dir = any(name.startswith("modules/") and name.endswith(".tf") for name in mapped)
    has_module_call = re.search(r'(?m)^\s*module\s+"[^"]+"\s*\{', root_main.content) is not None
    if not root_blocks and has_module_dir and has_module_call:
        return files

    result = [TerraformFile(filename=f.filename, content=f.content, description=f.description) for f in files]
    result_map = _file_map(result)

    if root_blocks:
        module_main_name = "modules/core/main.tf"
        module_vars_name = "modules/core/variables.tf"
        module_outputs_name = "modules/core/outputs.tf"

        moved_content = "\n\n".join(root_blocks)
        moved_content = moved_content.replace("local.name_prefix", "var.name_prefix")
        moved_content = moved_content.replace("local.common_tags", "var.tags")

        existing_module_main = result_map.get(module_main_name)
        if existing_module_main:
            existing_module_main.content = existing_module_main.content.rstrip() + "\n\n" + moved_content + "\n"
        else:
            result.append(TerraformFile(
                filename=module_main_name,
                content=moved_content + "\n",
                description="Core resources moved from root to preserve module hierarchy",
            ))

        root_main_obj = result_map.get("main.tf")
        if root_main_obj:
            root_content = main_without_resources
            if 'module "core"' not in root_content:
                var_refs = sorted(set(re.findall(r'\bvar\.([A-Za-z_][A-Za-z0-9_]*)', moved_content)))
                assignments = "\n".join(f"  {name} = var.{name}" for name in var_refs)
                root_content = root_content.rstrip() + f'\n\nmodule "core" {{\n  source = "./modules/core"\n{assignments}\n}}\n'
            root_main_obj.content = root_content

        root_outputs = result_map.get("outputs.tf")
        if root_outputs:
            _, output_blocks = _extract_top_level_blocks(root_outputs.content, ("output",))
            if output_blocks:
                module_outputs = result_map.get(module_outputs_name)
                content = "\n\n".join(output_blocks) + "\n"
                if module_outputs:
                    module_outputs.content = module_outputs.content.rstrip() + "\n\n" + content
                else:
                    result.append(TerraformFile(
                        filename=module_outputs_name,
                        content=content,
                        description="Core module outputs",
                    ))
                output_names = re.findall(r'output\s+"([^"]+)"', root_outputs.content)
                root_outputs.content = "\n\n".join(
                    f'output "{name}" {{\n  value = module.core.{name}\n}}' for name in output_names
                ) + "\n"

        all_module_content = "\n".join(f.content for f in result if f.filename.startswith("modules/"))
        var_names = sorted(set(re.findall(r'\bvar\.([A-Za-z_][A-Za-z0-9_]*)', all_module_content)))
        for extra in ("name_prefix", "tags"):
            if extra in all_module_content and extra not in var_names:
                var_names.append(extra)
        module_vars = result_map.get(module_vars_name)
        declared = set(re.findall(r'variable\s+"([^"]+)"', module_vars.content if module_vars else ""))
        additions = [name for name in sorted(set(var_names)) if name not in declared]
        if additions:
            content = "\n\n".join(_variable_block(name) for name in additions) + "\n"
            if module_vars:
                module_vars.content = module_vars.content.rstrip() + "\n\n" + content
            else:
                result.append(TerraformFile(
                    filename=module_vars_name,
                    content=content,
                    description="Core module input variables",
                ))

    module_dirs = sorted({"/".join(f.filename.split("/")[:2]) for f in result if f.filename.startswith("modules/")})
    for module_dir in module_dirs:
        current = _file_map(result)
        for base, desc in (("main.tf", "Module resources"), ("variables.tf", "Module input variables"), ("outputs.tf", "Module outputs")):
            filename = f"{module_dir}/{base}"
            if filename not in current:
                result.append(TerraformFile(filename=filename, content="", description=desc))

    final_root = _file_map(result).get("main.tf")
    if final_root:
        if not re.search(r'(?m)^\s*module\s+"[^"]+"\s*\{', final_root.content):
            if module_dirs:
                module_blocks = []
                for module_dir in module_dirs:
                    module_name = module_dir.split("/", 1)[1].replace("-", "_")
                    module_blocks.append(f'module "{module_name}" {{\n  source = "./{module_dir}"\n}}')
                final_root.content = final_root.content.rstrip() + "\n\n" + "\n\n".join(module_blocks) + "\n"
            else:
                final_root.content = final_root.content.rstrip() + '\n\nmodule "core" {\n  source = "./modules/core"\n}\n'
                result.extend([
                    TerraformFile(filename="modules/core/main.tf", content="", description="Core module resources"),
                    TerraformFile(filename="modules/core/variables.tf", content="", description="Core module input variables"),
                    TerraformFile(filename="modules/core/outputs.tf", content="", description="Core module outputs"),
                ])
        if re.search(r'(?m)^\s*(resource|data)\s+"', final_root.content):
            raise ValueError("Terraform generation failed module hierarchy enforcement: root main.tf still contains resource/data blocks")
    return result


def _hcl_fix_inline_block_opens(content: str) -> str:
    """
    Fix the #1 LLM mistake: an HCL block that puts arguments on the same line
    as the opening brace WITHOUT closing the block on the same line.

    INVALID:
        variable "db_instance_class" { type = string
          default = "db.t3.micro"
        }

    FIXED:
        variable "db_instance_class" {
          type    = string
          default = "db.t3.micro"
        }

    Safe guards (leave unchanged):
      - Single-line COMPLETE blocks:  variable "x" { default = "y" }
      - Map/object value openings:    tags = {
      - Function-call argument:       jsonencode({
      - Comments after brace:         resource "x" "y" {  # comment
      - Heredoc markers:              <<-EOF
    """
    # Pattern:
    #   ^(indent)(everything-before-{-no-braces){ (attr-content-no-closing-})<EOL>
    # The key: [^\n}]*? at end means "no } before end of line" → block not closed here
    _INLINE_BLOCK_RE = re.compile(
        r'^([ \t]*)([^\n{}]*?)\{\s+(\w[\w-]*\s*(?:=|\{)[^\n}]*?)\s*$',
        re.MULTILINE,
    )

    def _replacer(m: re.Match) -> str:
        indent  = m.group(1)
        before  = m.group(2).rstrip()
        inline  = m.group(3).strip()

        # Guard: skip if "before" ends with = ( , [ — it's a value, not a block decl
        stripped = before.rstrip()
        if stripped and stripped[-1] in ('=', '(', ',', '['):
            return m.group(0)

        # Guard: skip comments
        if inline.lstrip().startswith(('#', '//')):
            return m.group(0)

        # Guard: skip if inline looks like a for-expression  e.g.  for k, v in ...
        if re.match(r'^for\s+\w', inline):
            return m.group(0)

        # Apply fix
        return f'{indent}{before} {{\n{indent}  {inline}'

    return _INLINE_BLOCK_RE.sub(_replacer, content)


def _hcl_fix_quoted_types(content: str) -> str:
    """
    Fix quoted type constraints — HCL type system never uses string quotes.

    BAD:   type = "string"  /  type = "list(string)"  /  type = "map(any)"
    GOOD:  type = string    /  type = list(string)    /  type = map(any)
    """
    # Primitive types
    for primitive in ('string', 'number', 'bool', 'any'):
        content = re.sub(
            rf'\btype\s*=\s*"{primitive}"',
            f'type = {primitive}',
            content,
        )
    # Complex types wrapped in quotes: "list(...)", "map(...)", "set(...)", etc.
    content = re.sub(
        r'\btype\s*=\s*"((?:list|map|set|object|tuple)\s*[\(\[{][^"]*?[\)\]}])"',
        r'type = \1',
        content,
    )
    return content


def _hcl_fix_trailing_commas(content: str) -> str:
    """
    Remove trailing commas from HCL attribute lines (JSON habit, invalid in HCL).

    BAD:   name = "foo",
    GOOD:  name = "foo"

    Safely skips commas inside string literals and multi-value lines.
    """
    content = re.sub(
        r'^(\s*[\w-]+\s*=\s*(?:"[^"\n]*"|[^\n",\[{]+?))\s*,\s*$',
        r'\1',
        content,
        flags=re.MULTILINE,
    )
    return content


def _hcl_fix_single_quotes(content: str) -> str:
    """
    Replace single-quoted string values with double-quoted.
    HCL requires double quotes; single quotes are invalid.

    BAD:   name = 'my-value'
    GOOD:  name = "my-value"

    Does NOT modify single quotes that appear inside double-quoted strings.
    """
    content = re.sub(
        r"(=\s*)'([^'\n]*)'",
        r'\1"\2"',
        content,
    )
    return content


def _hcl_fix_semicolons(content: str) -> str:
    """
    Strip trailing semicolons from HCL assignment lines (not valid in HCL).

    BAD:   name = "foo";
    GOOD:  name = "foo"
    """
    # Match any assignment line ending with ; — works with quoted strings too
    content = re.sub(
        r'^(\s*[\w-]+\s*=\s*.+?)\s*;\s*$',
        r'\1',
        content,
        flags=re.MULTILINE,
    )
    return content


def _hcl_fix_missing_equals(content: str) -> str:
    """
    Fix missing '=' in common variable block attributes.

    BAD:   default "foo"
    GOOD:  default = "foo"

    Only applied to known attribute keywords inside variable/output blocks
    to avoid false positives.
    """
    for attr in ('default', 'description', 'sensitive', 'nullable'):
        content = re.sub(
            rf'^(\s*{attr})\s+(?!=)(\S)',
            rf'\1 = \2',
            content,
            flags=re.MULTILINE,
        )
    return content


# ────────────────────────────────────────────────────────────────────────────────


def _auto_fmt_files(files: list) -> list:
    """Run terraform fmt -recursive on files in-place and return reformatted content."""
    tf = _which_tf()
    if not tf:
        return files
    with tempfile.TemporaryDirectory(prefix="archlens_fmt_") as tmpdir:
        for f in files:
            path = os.path.join(tmpdir, f.filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                fh.write(f.content)
        env = os.environ.copy()
        env["PATH"] = _EXTRA_PATH + ":" + env.get("PATH", "")
        subprocess.run([tf, "fmt", "-recursive", "."], cwd=tmpdir, capture_output=True, env=env, timeout=30)
        result = []
        for f in files:
            path = os.path.join(tmpdir, f.filename)
            if os.path.exists(path):
                with open(path) as fh:
                    content = fh.read()
                result.append(TerraformFile(filename=f.filename, content=content, description=f.description))
            else:
                result.append(f)
    return result


def _inject_variable_defaults(files: List[TerraformFile]) -> List[TerraformFile]:
    """
    Post-process generated Terraform files: for every variable block that has no
    'default', inject a smart dummy default so that terraform validate, tflint,
    checkov and HCP speculative plans all pass without needing -var flags.
    A comment is added so users know to replace these values.
    """
    def _dummy(name: str, vtype: str) -> str:
        n = name.lower()
        # AWS resource identifiers
        if re.search(r'ami[_\-]?id|_ami$|^ami$', n):              return '"ami-00000000000000000"  # TODO: replace with real AMI ID'
        if re.search(r'certificate', n):                           return '"arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000000"  # TODO: replace'
        if re.search(r'kms.*arn|kms.*key', n):                    return '"arn:aws:kms:us-east-1:123456789012:key/00000000-0000-0000-0000-000000000000"  # TODO: replace'
        if re.search(r'iam.*arn|role.*arn|instance.*profile', n): return '"arn:aws:iam::123456789012:role/placeholder-role"  # TODO: replace'
        if re.search(r'sns.*arn|topic.*arn', n):                   return '"arn:aws:sns:us-east-1:123456789012:placeholder-topic"  # TODO: replace'
        if re.search(r'sqs.*arn|queue.*arn', n):                   return '"arn:aws:sqs:us-east-1:123456789012:placeholder-queue"  # TODO: replace'
        if re.search(r'lambda.*arn|function.*arn', n):             return '"arn:aws:lambda:us-east-1:123456789012:function:placeholder"  # TODO: replace'
        if re.search(r'target_group_arn|tg_arn', n):              return '"arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/placeholder/0000000000000000"  # TODO: replace'
        if re.search(r'load_balancer.*arn|alb.*arn|elb.*arn', n): return '"arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/placeholder/0000"  # TODO: replace'
        if re.search(r'layer_arn', n):                             return '"arn:aws:lambda:us-east-1:123456789012:layer:placeholder:1"  # TODO: replace'
        if re.search(r'arn', n):                                   return '"arn:aws:iam::123456789012:role/placeholder"  # TODO: replace'
        # Resource IDs
        if re.search(r'vpc_id$|^vpc_id', n):                      return '"vpc-00000000000000000"  # TODO: replace'
        if re.search(r'subnet_ids|private_subnets|public_subnets', n): return '["subnet-00000000000000000", "subnet-11111111111111111"]  # TODO: replace'
        if re.search(r'subnet_id$', n):                           return '"subnet-00000000000000000"  # TODO: replace'
        if re.search(r'security_group_ids|sg_ids', n):            return '["sg-00000000000000000"]  # TODO: replace'
        if re.search(r'security_group_id$', n):                   return '"sg-00000000000000000"  # TODO: replace'
        if re.search(r'route_table_id', n):                       return '"rtb-00000000000000000"  # TODO: replace'
        if re.search(r'internet_gateway_id|igw_id', n):           return '"igw-00000000000000000"  # TODO: replace'
        if re.search(r'nat_gateway_id', n):                       return '"nat-00000000000000000"  # TODO: replace'
        if re.search(r'instance_id', n):                          return '"i-00000000000000000"  # TODO: replace'
        if re.search(r'snapshot_id', n):                          return '"snap-00000000000000000"  # TODO: replace'
        if re.search(r'volume_id', n):                            return '"vol-00000000000000000"  # TODO: replace'
        if re.search(r'hosted_zone_id|zone_id', n):               return '"Z00000000000000000000"  # TODO: replace'
        if re.search(r'cluster_id', n):                           return '"placeholder-cluster-id"  # TODO: replace'
        if re.search(r'log_group', n):                            return '"/aws/placeholder/log-group"  # TODO: replace'
        if re.search(r'account_id|aws_account', n):               return '"123456789012"  # TODO: replace'
        if re.search(r'organization_id|org_id', n):               return '"o-0000000000"  # TODO: replace'
        # Credentials
        if re.search(r'password|passwd', n):                      return '"Placeholder@12345!"  # TODO: replace with real password'
        if re.search(r'secret_key|access_key|api_key|auth_token|token', n): return '"placeholder_secret_000000000000"  # TODO: replace'
        if re.search(r'secret', n):                               return '"placeholder_secret_value"  # TODO: replace'
        if re.search(r'username|user_name|db_user', n):           return '"placeholder_user"  # TODO: replace'
        if re.search(r'private_key|pem', n):                      return '"placeholder_private_key"  # TODO: replace'
        # Networking
        if re.search(r'allowed_cidr|ingress_cidr|egress_cidr|whitelist|cidr_blocks', n): return '["10.0.0.0/8"]  # TODO: restrict'
        if re.search(r'cidr_block|cidr', n):                      return '"10.0.0.0/16"  # TODO: replace'
        if re.search(r'ip_address|public_ip|private_ip|elastic_ip', n): return '"10.0.0.1"  # TODO: replace'
        if re.search(r'dns_name|fqdn|endpoint', n):               return '"placeholder.us-east-1.elb.amazonaws.com"  # TODO: replace'
        if re.search(r'port$|_port$', n):                         return '8080'
        if re.search(r'ports$', n):                               return '[80, 443]'
        if re.search(r'protocol', n):                             return '"HTTP"'
        # Storage
        if re.search(r'bucket_name|bucket', n):                   return '"placeholder-bucket-123456"  # TODO: replace (must be globally unique)'
        if re.search(r's3_key|object_key|prefix', n):             return '"placeholder/key"'
        if re.search(r'storage_class', n):                        return '"STANDARD"'
        # Database
        if re.search(r'db_name|database_name', n):                return '"placeholder_db"'
        if re.search(r'db_port|database_port', n):                return '5432'
        if re.search(r'db_engine|engine_version', n):             return '"postgres"'
        if re.search(r'db_instance_class|instance_class', n):     return '"db.t3.micro"'
        if re.search(r'db_storage|allocated_storage', n):         return '20'
        if re.search(r'db_identifier|db_id', n):                  return '"placeholder-db"'
        if re.search(r'db_host|rds_host|database_host', n):       return '"placeholder.rds.amazonaws.com"  # TODO: replace'
        # Compute
        if re.search(r'instance_type', n):                        return '"t3.micro"'
        if re.search(r'key_name|key_pair', n):                    return '"placeholder-keypair"  # TODO: replace'
        if re.search(r'ecs_cluster|cluster_name', n):             return '"placeholder-cluster"'
        if re.search(r'container_image|image_uri|ecr_image|docker_image', n): return '"123456789012.dkr.ecr.us-east-1.amazonaws.com/placeholder:latest"  # TODO: replace'
        if re.search(r'container_name', n):                       return '"placeholder-container"'
        if re.search(r'task_definition', n):                      return '"placeholder-task:1"'
        if re.search(r'launch_type', n):                          return '"FARGATE"'
        if re.search(r'cpu$|^cpu|vcpu', n):                       return '256'
        if re.search(r'memory$|mem$', n):                         return '512'
        if re.search(r'gpu', n):                                  return '0'
        # Auto Scaling
        if re.search(r'min_size|min_capacity|min_count', n):      return '1'
        if re.search(r'max_size|max_capacity|max_count', n):      return '3'
        if re.search(r'desired_capacity|desired_count', n):       return '1'
        if re.search(r'health_check_interval|interval', n):       return '30'
        if re.search(r'health_check_threshold|threshold', n):     return '2'
        if re.search(r'cooldown|grace_period', n):                return '300'
        if re.search(r'timeout', n):                              return '60'
        # DNS / Domain
        if re.search(r'domain_name|domain|hosted_zone_name', n):  return '"example.com"  # TODO: replace'
        if re.search(r'subdomain', n):                            return '"app.example.com"  # TODO: replace'
        if re.search(r'email', n):                                return '"placeholder@example.com"  # TODO: replace'
        # Location
        if re.search(r'region|aws_region', n):                    return '"us-east-1"'
        if re.search(r'availability_zone$', n):                   return '"us-east-1a"'
        if re.search(r'availability_zones', n):                   return '["us-east-1a", "us-east-1b"]'
        if re.search(r'environment|env$', n):                     return '"dev"'
        if re.search(r'namespace', n):                            return '"placeholder-ns"'
        if re.search(r'^name$|_name$|resource_name', n):          return '"placeholder-name"'
        if re.search(r'tags$', n):                                return '{}'
        # Lambda
        if re.search(r'runtime', n):                              return '"python3.11"'
        if re.search(r'handler', n):                              return '"index.handler"'
        if re.search(r'function_name|lambda_name', n):            return '"placeholder-function"'
        # Monitoring
        if re.search(r'alarm_name', n):                           return '"placeholder-alarm"'
        if re.search(r'metric_name', n):                          return '"CPUUtilization"'
        if re.search(r'evaluation_period', n):                    return '2'
        if re.search(r'statistic', n):                            return '"Average"'
        # Flags / counts
        if re.search(r'enable|enabled|create|use_|allow|force|multi_az|deletion_protection|encrypt', n): return 'false'
        if re.search(r'count$|_count$|num$|number_of', n):        return '1'
        if re.search(r'size$', n):                                return '1'
        if re.search(r'retention|days|ttl|expiry', n):            return '7'
        if re.search(r'version$|engine_version', n):              return '"1.0"'
        if re.search(r'log_level|level', n):                      return '"INFO"'
        if re.search(r'path$', n):                                return '"/"'
        # Type-based fallbacks
        if 'number' in vtype:                                     return '0'
        if 'bool'   in vtype:                                     return 'false'
        if vtype.startswith('list'):                              return '[]'
        if vtype.startswith(('map', 'object')):                   return '{}'
        return '"placeholder"  # TODO: replace'

    var_block_re = re.compile(r'(variable\s+"([^"]+)"\s*\{)([^}]*)(\})', re.DOTALL)

    result = []
    for f in files:
        if not f.filename.endswith('.tf'):
            result.append(f)
            continue

        def _patch_block(m: re.Match) -> str:
            header   = m.group(1)   # variable "foo" {
            var_name = m.group(2)   # foo
            body     = m.group(3)   # contents between braces
            close    = m.group(4)   # }
            # skip if default already present
            if re.search(r'\bdefault\b', body):
                return m.group(0)
            type_m   = re.search(r'type\s*=\s*(\S+)', body)
            var_type = type_m.group(1).lower() if type_m else 'string'
            dummy    = _dummy(var_name, var_type)
            # append default before closing brace, indented
            patched_body = body.rstrip()
            patched_body += f'\n  default = {dummy}\n'
            return header + patched_body + close

        new_content = var_block_re.sub(_patch_block, f.content)
        result.append(TerraformFile(
            filename=f.filename,
            content=new_content,
            description=f.description,
        ))
    return result


# _fix_known_hallucinations and _fix_asg_tags are now handled by schema_fixer.apply_aws_schema_fixes


def _deduplicate_variables(files: List[TerraformFile]) -> List[TerraformFile]:
    """
    Remove duplicate variable declarations within each directory scope.
    Each module directory is independent: root/variables.tf is authoritative for root,
    modules/compute/variables.tf is authoritative for that module, etc.
    """
    var_block_re = re.compile(r'(variable\s+"([^"]+)"\s*\{[^}]*\})', re.DOTALL)

    # Group files by directory
    from collections import defaultdict
    by_dir: dict = defaultdict(list)
    for f in files:
        d = os.path.dirname(f.filename) or '.'
        by_dir[d].append(f)

    result = []
    for d, dir_files in by_dir.items():
        # variables.tf in this dir is authoritative for this scope
        authoritative: set = set()
        for f in dir_files:
            if os.path.basename(f.filename) == 'variables.tf':
                for _, name in var_block_re.findall(f.content):
                    authoritative.add(name)

        for f in dir_files:
            if not f.filename.endswith('.tf'):
                result.append(f)
                continue
            if os.path.basename(f.filename) == 'variables.tf':
                # Deduplicate within variables.tf itself
                seen: set = set()
                def _strip(content, seen=seen):
                    def _sub(m):
                        name = m.group(2)
                        if name in seen:
                            return ''
                        seen.add(name)
                        return m.group(0)
                    return var_block_re.sub(_sub, content)
                new_content = _strip(f.content)
            else:
                # Strip anything already in this dir's variables.tf
                auth_copy = set(authoritative)
                def _strip_auth(content, auth_copy=auth_copy):
                    def _sub(m):
                        name = m.group(2)
                        if name in auth_copy:
                            logger.debug("Removing duplicate variable %r in %s", name, f.filename)
                            return ''
                        return m.group(0)
                    return var_block_re.sub(_sub, content)
                new_content = _strip_auth(f.content)
            result.append(TerraformFile(filename=f.filename, content=new_content, description=f.description))

    return result


def _lock_provider_versions(files: List[TerraformFile]) -> List[TerraformFile]:
    """
    Ensure a terraform { required_version + required_providers } block exists in versions.tf
    (root level only). Detects which cloud provider(s) are used and pins their versions.
    """
    _PROVIDER_VERSIONS = {
        'aws':    ('hashicorp/aws',    '~> 5.0'),
        'azurerm':('hashicorp/azurerm','~> 3.0'),
        'google': ('hashicorp/google', '~> 5.0'),
        'random': ('hashicorp/random', '~> 3.5'),
        'tls':    ('hashicorp/tls',    '~> 4.0'),
        'local':  ('hashicorp/local',  '~> 2.4'),
        'null':   ('hashicorp/null',   '~> 3.2'),
        'archive':('hashicorp/archive','~> 2.4'),
        'time':   ('hashicorp/time',   '~> 0.9'),
    }

    # Only inspect root-level files for provider detection
    root_content = '\n'.join(
        f.content for f in files
        if '/' not in f.filename.replace('\\', '/') and f.filename.endswith('.tf')
    )

    # Find which providers are declared at root level
    used_providers = [
        p for p in _PROVIDER_VERSIONS
        if re.search(rf'\bprovider\s+"{p}"', root_content)
        or re.search(rf'\bresource\s+"(?:{p}_[^"]+)"', root_content)
        or re.search(rf'\bdata\s+"(?:{p}_[^"]+)"', root_content)
        or re.search(rf'\bmodule\b', root_content)  # modules inherit provider
    ]
    # deduplicate, keep order
    seen_p: set = set()
    used_providers = [p for p in used_providers if not (p in seen_p or seen_p.add(p))]
    # Only keep cloud providers (first match) plus helpers
    cloud_providers  = [p for p in used_providers if p in ('aws', 'azurerm', 'google')]
    helper_providers = [p for p in used_providers if p not in ('aws', 'azurerm', 'google')]
    used_providers   = (cloud_providers or ['aws']) + helper_providers

    if not used_providers:
        return files

    # Check if required_providers already exists in root-level versions.tf or providers.tf
    if re.search(r'required_providers', root_content):
        return files

    provider_lines = '\n'.join(
        f'    {p} = {{\n      source  = "{src}"\n      version = "{ver}"\n    }}'
        for p in used_providers
        for src, ver in [_PROVIDER_VERSIONS[p]]
    )
    lock_block = (
        'terraform {\n'
        '  required_version = ">= 1.5.0"\n'
        '  required_providers {\n'
        f'{provider_lines}\n'
        '  }\n'
        '}\n\n'
    )

    result = []
    versions_found = False
    for f in files:
        if f.filename == 'versions.tf':
            versions_found = True
            result.append(TerraformFile(
                filename=f.filename,
                content=lock_block + f.content,
                description=f.description,
            ))
        else:
            result.append(f)

    if not versions_found:
        # Inject into providers.tf as fallback, or create versions.tf
        providers_found = False
        new_result = []
        for f in result:
            if f.filename in ('providers.tf', 'provider.tf') and not providers_found:
                providers_found = True
                new_result.append(TerraformFile(
                    filename=f.filename,
                    content=lock_block + f.content,
                    description=f.description,
                ))
            else:
                new_result.append(f)
        if not providers_found:
            new_result.insert(0, TerraformFile(
                filename='versions.tf',
                content=lock_block,
                description='Terraform version constraints and required providers',
            ))
        result = new_result

    return result





def _llm_schema_verify(files: List[TerraformFile], cloud: CloudProvider) -> List[TerraformFile]:
    """
    Final LLM pass to catch schema errors that regex fixes cannot handle:
    - ACM domain_validation_options set indexing (use for_each instead of count.index)
    - WAFv2 block naming
    - Duplicate locals/outputs
    - launch_configuration → launch_template
    - inline S3 blocks that survived earlier fixes
    Returns originals if the LLM call fails.
    """
    try:
        client, model = _get_client()
        files_content = '\n\n'.join(f'=== {f.filename} ===\n{f.content}' for f in files)

        # --- RAG: fetch authoritative schema context from ChromaDB ---
        rag_schema_context = ""
        try:
            from app.services.schema_fixer_rag import get_schema_context
            all_content = "\n".join(f.content for f in files)
            rtype_matches = re.findall(
                r'^resource\s+"([^"]+)"\s+"[^"]+"\s*\{',
                all_content,
                re.MULTILINE,
            )
            resource_types = list(dict.fromkeys(rtype_matches))  # deduplicated, ordered
            provider_key   = cloud.value.lower()  # "aws" / "azurerm" / "google"
            if resource_types:
                rag_schema_context = get_schema_context(resource_types, provider_key)
        except Exception as _rag_exc:
            logger.debug("_llm_schema_verify: RAG schema context unavailable — %s", _rag_exc)
        # -------------------------------------------------------

        schema_section = (
            f"\n{rag_schema_context}\n" if rag_schema_context else ""
        )

        prompt = f"""You are a Terraform schema expert for {cloud.value.upper()} provider v5.
{schema_section}
Fix ONLY the specific issues listed below in the Terraform files. Do not rewrite or restructure code beyond what is needed.

CRITICAL RULE — IAM POLICY FORMAT: aws_iam_role_policy and aws_iam_policy resources MUST have their 'policy' argument as a proper jsonencode() call. If you see JSON-like content (Version, Statement, Effect, Action, Resource keys) appearing directly inside a resource block WITHOUT being wrapped in 'policy = jsonencode({{...}})', you MUST add the wrapper back:
  policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [...]
  }})
NEVER remove the 'policy' argument from aws_iam_role_policy or aws_iam_policy resources.

1. UNSUPPORTED ARGUMENTS: ONLY for resource types that appear explicitly in the PROVIDER SCHEMA REFERENCE above, remove any top-level argument that is not listed in that resource's valid_args. Do NOT apply this rule to resource types that are absent from the schema reference — leave them untouched.

2. DEPRECATED ARGUMENTS: For resources explicitly in the schema reference above, if an argument is listed under deprecated_args, remove it only when a documented replacement exists and is shown. Do NOT blindly strip all deprecated args — deprecated does not mean the argument causes a Terraform error.

3. ACM domain_validation_options: It is a SET (not a list). Never use [count.index] on it.
   Correct pattern:
     resource "aws_acm_certificate_validation" "this" {{
       certificate_arn         = aws_acm_certificate.this.arn
       validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
     }}
     resource "aws_route53_record" "cert_validation" {{
       for_each = {{for dvo in aws_acm_certificate.this.domain_validation_options : dvo.domain_name => dvo}}
       zone_id  = each.value.hosted_zone_id
       name     = each.value.resource_record_name
       type     = each.value.resource_record_type
       records  = [each.value.resource_record_value]
       ttl      = 60
     }}

2. WAFv2: Use 'managed_rule_group_statement' (not 'managed_rule_group').

3. S3 AWS v5: Remove any inline 'acl', 'lifecycle_rule', 'cors_rule', 'website',
   'server_side_encryption_configuration' blocks inside aws_s3_bucket resources.

4. EC2 launch_configuration is removed in AWS provider v5 — replace with launch_template.

5. Ensure no variable is declared twice across all files.

6. aws_autoscaling_group does NOT support 'tags = {{}}' map syntax. Convert to repeated
   tag blocks with propagate_at_launch:
     tag {{
       key                 = "Name"
       value               = "web-asg"
       propagate_at_launch = true
     }}

7. Ensure every resource block has tags (using the appropriate syntax for the resource type).

TERRAFORM FILES:
{files_content}

Return ONLY valid JSON with ALL files:
{{"files": [{{"filename": "<name>", "description": "<desc>", "content": "<full corrected HCL>"}}]}}"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a Terraform schema expert. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=16000,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        verified = [
            TerraformFile(
                filename=f["filename"],
                content=f["content"],
                description=f.get("description", ""),
            )
            for f in data.get("files", [])
        ]
        if verified:
            return verified
        return files
    except Exception as exc:
        logger.warning("_llm_schema_verify failed (%s) — using original files", exc)
        return files


DEFAULT_REGIONS = {
    CloudProvider.AWS: "us-east-1",
    CloudProvider.AZURE: "East US",
    CloudProvider.GCP: "us-central1",
}

TERRAFORM_PROVIDERS = {
    CloudProvider.AWS: 'hashicorp/aws version ~> 5.0',
    CloudProvider.AZURE: 'hashicorp/azurerm version ~> 3.0',
    CloudProvider.GCP: 'hashicorp/google version ~> 5.0',
}


def _build_terraform_prompt(
    analysis: DiagramAnalysisResponse,
    cloud: CloudProvider,
    region: Optional[str],
    include_modules: bool,
    user_context: Optional[UserContext] = None,
) -> str:
    from app.services.module_registry import build_module_catalogue

    target_region = region or DEFAULT_REGIONS[cloud]
    provider_info = TERRAFORM_PROVIDERS[cloud]
    ctx_block = format_user_context(user_context)

    components_detail = "\n".join(
        f"- {c.name} ({c.type}): "
        + ({CloudProvider.AWS: c.aws_equivalent or c.name,
           CloudProvider.AZURE: c.azure_equivalent or c.aws_equivalent or c.name,
           CloudProvider.GCP: c.gcp_equivalent or c.aws_equivalent or c.name}[cloud] or c.name)
        for c in analysis.components
    )

    module_catalogue = build_module_catalogue(cloud.value) if cloud == CloudProvider.AWS else ""

    # Fetch module schemas from ChromaDB RAG (populated by ingest_module_schemas.py)
    module_schema_context = module_schema_rag.get_module_context_for_cloud(cloud.value)

    # Determine which functional modules are needed based on components
    comp_types = " ".join(c.type.lower() + " " + c.name.lower() for c in analysis.components)
    needs_networking = any(k in comp_types for k in ["vpc", "subnet", "network", "nat", "igw", "gateway", "route", "security group", "firewall"])
    needs_compute    = any(k in comp_types for k in ["ec2", "instance", "ecs", "lambda", "eks", "kubernetes", "fargate", "container", "autoscal", "asg", "function", "app"])
    needs_database   = any(k in comp_types for k in ["rds", "database", "db", "dynamo", "elasticache", "redis", "postgres", "mysql", "aurora", "sql", "cache"])
    needs_storage    = any(k in comp_types for k in ["s3", "bucket", "storage", "efs", "fsx", "blob"])
    needs_security   = any(k in comp_types for k in ["iam", "kms", "acm", "certificate", "waf", "secret", "vault", "role"])
    needs_monitoring = any(k in comp_types for k in ["cloudwatch", "monitor", "alarm", "sns", "log", "metric", "alert"])

    # Always enable at least networking + compute + database for non-trivial architectures
    if len(analysis.components) >= 3:
        needs_networking = True
        needs_compute    = needs_compute or True
        needs_database   = needs_database

    modules_to_generate = []
    if needs_networking: modules_to_generate.append("networking")
    if needs_compute:    modules_to_generate.append("compute")
    if needs_database:   modules_to_generate.append("database")
    if needs_storage:    modules_to_generate.append("storage")
    if needs_security:   modules_to_generate.append("security")
    if needs_monitoring: modules_to_generate.append("monitoring")
    if not modules_to_generate:
        modules_to_generate = ["compute"]

    modules_list = ", ".join(f"modules/{m}/" for m in modules_to_generate)

    # Build the expected files list for JSON output (MODULAR STRUCTURE with modules/)
    root_files_spec = """\
    {"filename": "main.tf",                    "description": "Module calls and root configuration",          "content": "<full HCL>"},
    {"filename": "variables.tf",               "description": "Root input variables",                          "content": "<full HCL>"},
    {"filename": "outputs.tf",                 "description": "Root output values",                            "content": "<full HCL>"}"""

    # Module folders - each module gets main.tf, variables.tf, outputs.tf
    module_files_list = []
    for m in modules_to_generate:
        module_files_list.append(f'''
    {{"filename": "modules/{m}/main.tf",       "description": "{m.capitalize()} resources",                     "content": "<full HCL>"}},
    {{"filename": "modules/{m}/variables.tf",  "description": "{m.capitalize()} input variables",               "content": "<full HCL>"}},
    {{"filename": "modules/{m}/outputs.tf",    "description": "{m.capitalize()} outputs",                       "content": "<full HCL>"}}''')
    
    module_files_spec = ",".join(module_files_list) if module_files_list else ""

    return f"""You are a senior Terraform engineer. Generate production-ready Terraform IaC for {cloud.value.upper()}.
{ctx_block}
Architecture: {analysis.architecture_type}
Description: {analysis.description}
Region: {target_region}
Provider: {provider_info}

Components to implement:
{components_detail}

{module_catalogue}

═══════════════════════════════════════════════════
DIRECTORY STRUCTURE — MODULAR WITH LOCAL MODULES
═══════════════════════════════════════════════════

Generate EXACTLY this MODULAR structure:

  main.tf           ← Module calls, terraform{{}}, provider{{}}
  variables.tf      ← Root input variables with default values
  outputs.tf        ← Root outputs (from module outputs)
  modules/
    {modules_list.replace('modules/', '').replace('/', '')}
      Each module has:
        main.tf       ← Resource blocks for this module
        variables.tf  ← Module input variables
        outputs.tf    ← Module outputs

═══════════════════════════════════════════════════
GENERATION RULES
═══════════════════════════════════════════════════

1. FILE RESPONSIBILITIES
   ROOT LEVEL:
   - main.tf       → terraform{{}} block, provider{{}} blocks, locals, module calls
   - variables.tf  → Root-level variables with sensible default values
   - outputs.tf    → Root-level outputs (reference module outputs)
   
   MODULE LEVEL (modules/networking/, modules/compute/, etc.):
   - main.tf       → Resource blocks for this functional area
   - variables.tf  → Input variables this module needs
   - outputs.tf    → Values this module exposes (IDs, ARNs, etc.)

2. STRUCTURE
   - Root main.tf should be LEAN - just module calls and configuration
   - Each module contains the actual resource blocks
   - Use raw resources only (no external terraform-aws-modules, AVM, etc.)
   - Every variable MUST have a default value so terraform validate passes

3. RAW RESOURCES IN MODULES - NO EXTERNAL MODULES
   To avoid version conflicts, generate ONLY raw resource blocks inside modules.
   Do NOT use terraform-aws-modules, Azure AVM modules, or terraform-google-modules.
   
   {'''NETWORKING MODULE (modules/networking/main.tf):
   resource "aws_vpc" "main" {{
     cidr_block           = var.vpc_cidr
     enable_dns_hostnames = true
     enable_dns_support   = true
     tags                 = var.tags
   }}
   
   resource "aws_subnet" "private" {{
     count             = length(var.private_subnet_cidrs)
     vpc_id            = aws_vpc.main.id
     cidr_block        = var.private_subnet_cidrs[count.index]
     availability_zone = var.availability_zones[count.index]
     tags              = merge(var.tags, {{
       Name = "${{var.name_prefix}}-private-${{count.index + 1}}"
     }})
   }}
   
   resource "aws_internet_gateway" "main" {{
     vpc_id = aws_vpc.main.id
     tags   = var.tags
   }}
   
   COMPUTE MODULE (modules/compute/main.tf):
   resource "aws_instance" "app" {{
     count                  = var.instance_count
     ami                    = var.ami_id
     instance_type          = var.instance_type
     subnet_id              = var.subnet_ids[count.index % length(var.subnet_ids)]
     vpc_security_group_ids = var.security_group_ids
     
     tags = merge(var.tags, {{
       Name = "${{var.name_prefix}}-app-${{count.index + 1}}"
     }})
   }}
   
   resource "aws_lb" "main" {{
     name               = "${{var.name_prefix}}-alb"
     internal           = false
     load_balancer_type = "application"
     security_groups    = var.security_group_ids
     subnets            = var.public_subnet_ids
     tags               = var.tags
   }}
   
   DATABASE MODULE (modules/database/main.tf):
   resource "aws_db_subnet_group" "main" {{
     name       = "${{var.name_prefix}}-db-subnet-group"
     subnet_ids = var.private_subnet_ids
     tags       = var.tags
   }}
   
   resource "aws_db_instance" "main" {{
     identifier             = "${{var.name_prefix}}-db"
     engine                 = "postgres"
     engine_version         = var.db_engine_version
     instance_class         = var.db_instance_class
     allocated_storage      = var.db_allocated_storage
     storage_encrypted      = true
     multi_az               = true
     db_subnet_group_name   = aws_db_subnet_group.main.name
     vpc_security_group_ids = var.db_security_group_ids
     skip_final_snapshot    = var.skip_final_snapshot
     tags                   = var.tags
   }}''' if cloud == CloudProvider.AWS else
    '''NETWORKING MODULE (modules/networking/main.tf):
   resource "azurerm_virtual_network" "main" {{
     name                = "${{var.name_prefix}}-vnet"
     location            = var.location
     resource_group_name = var.resource_group_name
     address_space       = [var.vnet_cidr]
     tags                = var.tags
   }}
   
   resource "azurerm_subnet" "app" {{
     name                 = "${{var.name_prefix}}-app-subnet"
     resource_group_name  = var.resource_group_name
     virtual_network_name = azurerm_virtual_network.main.name
     address_prefixes     = [var.app_subnet_cidr]
   }}
   
   COMPUTE MODULE (modules/compute/main.tf):
   resource "azurerm_network_interface" "main" {{
     count               = var.instance_count
     name                = "${{var.name_prefix}}-nic-${{count.index}}"
     location            = var.location
     resource_group_name = var.resource_group_name
     
     ip_configuration {{
       name                          = "internal"
       subnet_id                     = var.subnet_id
       private_ip_address_allocation = "Dynamic"
     }}
     tags = var.tags
   }}
   
   resource "azurerm_linux_virtual_machine" "main" {{
     count               = var.instance_count
     name                = "${{var.name_prefix}}-vm-${{count.index}}"
     location            = var.location
     resource_group_name = var.resource_group_name
     size                = var.vm_size
     network_interface_ids = [azurerm_network_interface.main[count.index].id]
     
     os_disk {{
       caching              = "ReadWrite"
       storage_account_type = "Premium_LRS"
     }}
     
     source_image_reference {{
       publisher = "Canonical"
       offer     = "UbuntuServer"
       sku       = "18.04-LTS"
       version   = "latest"
     }}
     tags = var.tags
   }}''' if cloud == CloudProvider.AZURE else
    '''NETWORKING MODULE (modules/networking/main.tf):
   resource "google_compute_network" "main" {{
     name                    = "${{var.name_prefix}}-vpc"
     auto_create_subnetworks = false
     project                 = var.project_id
   }}
   
   resource "google_compute_subnetwork" "app" {{
     name          = "${{var.name_prefix}}-app-subnet"
     ip_cidr_range = var.subnet_cidr
     region        = var.region
     network       = google_compute_network.main.id
     project       = var.project_id
   }}
   
   COMPUTE MODULE (modules/compute/main.tf):
   resource "google_compute_instance" "app" {{
     count        = var.instance_count
     name         = "${{var.name_prefix}}-vm-${{count.index}}"
     machine_type = var.machine_type
     zone         = "${{var.region}}-a"
     project      = var.project_id
     
     boot_disk {{
       initialize_params {{
         image = "ubuntu-os-cloud/ubuntu-1804-lts"
       }}
     }}
     
     network_interface {{
       subnetwork = var.subnet_id
     }}
     
     labels = var.labels
   }}'''}

{module_schema_context if module_schema_context else ""}

4. STRUCTURE OF ROOT main.tf:
     # Terraform block with required providers
     terraform {{
       required_version = ">= 1.5.0"
       required_providers {{
         {cloud.value} = {{
           source  = "{TERRAFORM_PROVIDERS[cloud].split(' ')[0].replace('hashicorp/', 'registry.terraform.io/hashicorp/')}"
           version = "~> {'5.0' if cloud == CloudProvider.AWS else '3.0' if cloud == CloudProvider.AZURE else '5.0'}"
         }}
       }}
     }}

     # Provider block
     provider "{cloud.value if cloud != CloudProvider.AZURE else 'azurerm'}" {{
       region = var.region   # or features{{}} for Azure
     }}

     # Locals
     locals {{
       common_tags = {{
         project     = var.project
         environment = var.environment
         managed_by  = "archlens"
       }}
       name_prefix = "${{var.project}}-${{var.environment}}"
     }}

     # Module calls (source = "./modules/...")
     module "networking" {{
       source = "./modules/networking"
       
       # Pass variables to module
       vpc_cidr               = var.vpc_cidr
       private_subnet_cidrs   = var.private_subnet_cidrs
       public_subnet_cidrs    = var.public_subnet_cidrs
       availability_zones     = var.availability_zones
       name_prefix            = local.name_prefix
       tags                   = local.common_tags
     }}
     
     module "compute" {{
       source = "./modules/compute"
       
       # Reference outputs from other modules
       vpc_id             = module.networking.vpc_id
       subnet_ids         = module.networking.private_subnet_ids
       security_group_ids = [module.networking.app_security_group_id]
       
       # Pass variables
       instance_count = var.instance_count
       instance_type  = var.instance_type
       name_prefix    = local.name_prefix
       tags           = local.common_tags
     }}
     
     module "database" {{
       source = "./modules/database"
       
       vpc_id                 = module.networking.vpc_id
       private_subnet_ids     = module.networking.private_subnet_ids
       db_security_group_ids  = [module.networking.db_security_group_id]
       
       db_engine_version     = var.db_engine_version
       db_instance_class     = var.db_instance_class
       db_allocated_storage  = var.db_allocated_storage
       skip_final_snapshot   = var.skip_final_snapshot
       name_prefix           = local.name_prefix
       tags                  = local.common_tags
     }}

5. MODULE OUTPUTS — Each module should output critical values that other modules or root need:
   - networking: vpc_id, private_subnet_ids, public_subnet_ids, security_group_ids
   - compute: instance_ids, instance_private_ips, load_balancer_dns
   - database: db_endpoint, db_connection_string, db_instance_id

6. VARIABLES — every variable MUST have a default value so terraform validate passes without -var flags.
   Use realistic defaults. Add # TODO: replace on sensitive values.

7. OUTPUTS — Root outputs.tf should reference module outputs:
   output "vpc_id" {{
     value = module.networking.vpc_id
   }}
   
   output "app_load_balancer_dns" {{
     value = module.compute.load_balancer_dns
   }}
   
   output "database_endpoint" {{
     value = module.database.db_endpoint
   }}

8. SECURITY
    - All storage encrypted at rest.
    - No public IPs on compute unless explicitly required.
    - Multi-AZ for databases.
    - Tags on every resource using var.tags.

Return ONLY valid JSON (no markdown, no code fences):
{{
  "summary": "<one-sentence description>",
  "estimated_resources": <integer>,
  "files": [
    {root_files_spec}{module_files_spec}
  ]
}}

Generate COMPLETE, valid HCL. Never use placeholder comments like "# ... more resources"."""


def generate_terraform(
    analysis: DiagramAnalysisResponse,
    cloud: CloudProvider,
    region: Optional[str] = None,
    include_modules: bool = True,
    user_context: Optional[UserContext] = None,
) -> TerraformGenerateResponse:
    """Generate Terraform code using local modular structure for the specified cloud provider."""
    client, model = _get_client()
    prompt = _build_terraform_prompt(analysis, cloud, region, include_modules, user_context)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior Terraform engineer specializing in cloud infrastructure. "
                    "Generate complete, production-ready modular Terraform code with local modules. "
                    "Use ONLY raw resource blocks (aws_*, azurerm_*, google_*) inside modules. "
                    "DO NOT use external terraform-aws-modules, AVM, or terraform-google-modules. "
                    "Organize resources into logical modules (networking, compute, database, etc.). "
                    "Root main.tf should contain module calls with proper variable passing. "
                    "Never put resource or data blocks in root main.tf. "
                    "Return only valid JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=16000,
        temperature=0.3,  # Lower temperature for more consistent, faster generation
        response_format={"type": "json_object"},
    )

    data = json.loads(response.choices[0].message.content)

    tf_files = [
        TerraformFile(
            filename=f["filename"],
            content=f["content"],
            description=f.get("description", ""),
        )
        for f in data.get("files", [])
    ]

    # Post-processor pipeline (single _auto_fmt_files at the end — one subprocess is enough):
    # 0. Enforce root/module hierarchy even if the model returns flat Terraform
    # 1. HCL syntax fix  – correct invalid LLM syntax
    # 1. schema fixes on root + module .tf files (cloud-specific)
    # 2. dedup variables per directory scope
    # 3. inject provider version block into versions.tf
    # 4. inject variable defaults
    # 5. HCL syntax fix again  – catch any issues introduced by earlier transforms
    # 6. final fmt pass
    tf_files = _ensure_modular_hierarchy(tf_files)
    tf_files = _fix_hcl_syntax(tf_files)
    # Only apply AWS-specific schema fixes for AWS
    if cloud == CloudProvider.AWS:
        tf_files = apply_aws_schema_fixes(tf_files)
    tf_files = apply_rag_schema_fixes(tf_files, cloud.value.lower())
    tf_files = _deduplicate_variables(tf_files)
    tf_files = _lock_provider_versions(tf_files)
    tf_files = _inject_variable_defaults(tf_files)
    tf_files = _ensure_modular_hierarchy(tf_files)
    tf_files = _fix_hcl_syntax(tf_files)
    tf_files = _auto_fmt_files(tf_files)

    return TerraformGenerateResponse(
        cloud=cloud,
        files=tf_files,
        summary=data.get("summary", ""),
        estimated_resources=data.get("estimated_resources", len(analysis.components)),
    )


def _sse_gen(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def generate_terraform_stream(
    analysis: DiagramAnalysisResponse,
    cloud: CloudProvider,
    region: Optional[str] = None,
    include_modules: bool = True,
    user_context: Optional[UserContext] = None,
) -> AsyncGenerator[str, None]:
    """
    Streaming version of generate_terraform — yields SSE events so the frontend
    can show real-time step progress instead of a frozen spinner.

    Events:
      progress  { step, message }   — step is starting / running
      done      { files, summary, estimated_resources, cloud }
      error     { message }
    """
    loop = asyncio.get_event_loop()

    # ── Step 1: LLM call (the slowest part) ────────────────────────────────
    yield _sse_gen("progress", {
        "step": "llm",
        "message": f"Generating {cloud.value.upper()} Terraform code with modular structure…",
    })

    try:
        client, model = _get_client()
        prompt = _build_terraform_prompt(analysis, cloud, region, include_modules, user_context)
        
        logger.info(f"Starting Terraform generation for {cloud.value.upper()} with {len(analysis.components)} components")

        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior Terraform engineer specializing in cloud infrastructure. "
                            "Generate complete, production-ready modular Terraform code with local modules. "
                            "Use ONLY raw resource blocks (aws_*, azurerm_*, google_*) inside modules. "
                            "DO NOT use external terraform-aws-modules, AVM, or terraform-google-modules. "
                            "Organize resources into logical modules (networking, compute, database, etc.). "
                            "Root main.tf should contain module calls with proper variable passing. "
                            "Never put resource or data blocks in root main.tf. "
                            "Return only valid JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=16000,
                temperature=0.3,  # Lower temperature for more consistent, faster generation
                response_format={"type": "json_object"},
            ),
        )
        logger.info(f"LLM generation completed for {cloud.value.upper()}")
    except Exception as exc:
        logger.error(f"LLM generation failed for {cloud.value.upper()}: {exc}")
        yield _sse_gen("error", {"message": f"LLM generation failed: {exc}"})
        return

    try:
        raw_data = json.loads(response.choices[0].message.content)
    except Exception as exc:
        yield _sse_gen("error", {"message": f"Failed to parse LLM response: {exc}"})
        return

    tf_files = [
        TerraformFile(
            filename=f["filename"],
            content=f["content"],
            description=f.get("description", ""),
        )
        for f in raw_data.get("files", [])
    ]

    # ── Step 2: HCL syntax fix ────────────────────────────────────────────
    yield _sse_gen("progress", {"step": "hcl_fix", "message": "Fixing HCL syntax errors…"})
    tf_files = _ensure_modular_hierarchy(tf_files)
    tf_files = _fix_hcl_syntax(tf_files)

    # ── Step 3: Provider schema fixes (regex + ChromaDB) ─────────────────
    yield _sse_gen("progress", {"step": "schema", "message": f"Applying {cloud.value.upper()} provider schema fixes…"})
    # Only apply AWS-specific schema fixes for AWS
    if cloud == CloudProvider.AWS:
        tf_files = apply_aws_schema_fixes(tf_files)
    try:
        tf_files = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: apply_rag_schema_fixes(tf_files, cloud.value.lower())),
            timeout=30,  # Increased timeout for RAG schema fixes
        )
    except asyncio.TimeoutError:
        logger.warning("generate_terraform_stream: apply_rag_schema_fixes timed out — skipping")

    # ── Step 4: Dedup, lock versions, inject defaults ─────────────────────
    yield _sse_gen("progress", {"step": "finalize", "message": "Deduplicating variables and locking provider versions…"})
    tf_files = _deduplicate_variables(tf_files)
    tf_files = _lock_provider_versions(tf_files)
    tf_files = _inject_variable_defaults(tf_files)
    tf_files = _ensure_modular_hierarchy(tf_files)
    tf_files = _fix_hcl_syntax(tf_files)

    # ── Step 5: terraform fmt ─────────────────────────────────────────────
    yield _sse_gen("progress", {"step": "fmt", "message": "Running terraform fmt…"})
    try:
        tf_files = await asyncio.wait_for(
            loop.run_in_executor(None, _auto_fmt_files, tf_files),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.warning("generate_terraform_stream: _auto_fmt_files timed out — skipping")

    # ── Done ──────────────────────────────────────────────────────────────
    yield _sse_gen("done", {
        "cloud": cloud.value,
        "summary": raw_data.get("summary", ""),
        "estimated_resources": raw_data.get("estimated_resources", len(analysis.components)),
        "files": [
            {"filename": f.filename, "content": f.content, "description": f.description}
            for f in tf_files
        ],
    })



def fix_security_issues(
    files: List[TerraformFile],
    cloud: CloudProvider,
    findings: List[str],
) -> List[TerraformFile]:
    """Ask GPT-4.1 to fix security issues found by checkov/tflint and return corrected files."""
    client, model = _get_client()

    files_content = "\n\n".join(
        [f"=== {f.filename} ===\n{f.content}" for f in files]
    )
    findings_text = "\n".join(f"- {d}" for d in findings) if findings else "General security hardening required."

    # RAG: fetch authoritative schema context for all resource types in these files
    rag_schema_context = ""
    try:
        all_content = "\n".join(f.content for f in files)
        rtype_matches = re.findall(
            r'^resource\s+"([^"]+)"\s+"[^"]+"\s*\{', all_content, re.MULTILINE
        )
        resource_types = list(dict.fromkeys(rtype_matches))
        if resource_types:
            rag_schema_context = get_schema_context(resource_types, cloud.value.lower())
    except Exception as _e:
        logger.debug("fix_security_issues: RAG context unavailable — %s", _e)

    schema_section = f"\n{rag_schema_context}\n" if rag_schema_context else ""

    prompt = f"""You are a Terraform expert. Fix ALL the issues listed below in the provided {cloud.value.upper()} Terraform files.
{schema_section}
ISSUES TO FIX:
{findings_text}

CURRENT TERRAFORM FILES:
{files_content}

Rules:
1. Fix EVERY issue listed — syntax errors, unsupported arguments, provider schema errors, and security issues.
2. SCHEMA ENFORCEMENT: Using the PROVIDER SCHEMA REFERENCE above as the authoritative source, remove any argument not present in valid_args and remove or replace any argument listed in deprecated_args or removed_args for each resource type.
3. For "Unsupported argument" errors: remove the invalid argument or replace it with the correct one.
   - 'override_characters' does NOT exist on random_password/random_string — replace with 'override_special'.
4. AWS provider v5 breaking changes to fix if present:
   - aws_s3_bucket: remove inline 'acl', 'lifecycle_rule', 'cors_rule', 'website', 'server_side_encryption_configuration' — use separate resources.
   - aws_acm_certificate domain_validation_options is a SET — never use [count.index]; use for_each.
   - aws_wafv2: 'managed_rule_group_statement' not 'managed_rule_group'.
   - aws_launch_configuration removed — use aws_launch_template.
5. If a variable is declared in multiple files, keep only the variables.tf declaration.
6. Do not remove any existing resources or functionality.
7. Return COMPLETE file contents (not diffs).
8. Use only valid HCL syntax and arguments that exist in the provider schema.
9. Add security hardening where findings request it (encryption, TLS, logging, etc.).

Return ONLY valid JSON:
{{"files": [{{"filename": "<name>", "description": "<desc>", "content": "<full HCL>"}}]}}"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a Terraform security expert. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=16000,
        response_format={"type": "json_object"},
    )

    data = json.loads(response.choices[0].message.content)
    fixed = [
        TerraformFile(
            filename=f["filename"],
            content=f["content"],
            description=f.get("description", ""),
        )
        for f in data.get("files", [])
    ]
    provider_key = cloud.value.lower()
    fixed = _fix_hcl_syntax(fixed)
    fixed = apply_aws_schema_fixes(_auto_fmt_files(fixed))
    fixed = apply_rag_schema_fixes(fixed, provider_key)
    fixed = _fix_hcl_syntax(fixed)
    return _inject_variable_defaults(_deduplicate_variables(fixed))
