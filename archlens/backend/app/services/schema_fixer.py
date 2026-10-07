"""
schema_fixer.py — Deterministic AWS provider v5/v6 schema-breaking-change fixer.

All transforms are scoped per-resource-type, applied to raw HCL source text,
and require no `terraform init` or provider download.

Entry points
------------
apply_aws_schema_fixes(files)     → List[TerraformFile]   (for terraform_service.py)
fix_content(filename, content)    → str                   (for validation_service.py)
"""

from __future__ import annotations

import re
import logging
from typing import Callable, Iterator, List, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Primitive transform factories  (all operate on a resource block body: str → str)
# ─────────────────────────────────────────────────────────────────────────────

def _remove_arg(arg: str) -> Callable[[str], str]:
    """
    Remove `arg = <value>` lines from a resource block body.
    Handles:
      - simple scalar values:   arg = "foo"
      - single-line maps:       arg = { Key = "V" }
      - multi-line maps:        arg = {\\n  Key = "V"\\n}
    """
    _esc = re.escape(arg)
    # Phase 1: simple value OR single-line map (anything on one line — but NOT
    # a bare `= {` that is the start of a multi-line map)
    _simple = re.compile(
        r'^[ \t]*' + _esc + r'\s*=[ \t]*(?!\{[ \t]*\n)[^\n]+\n?',
        re.MULTILINE,
    )
    # Phase 2: multi-line map — `arg = {` at end of line
    _multi = re.compile(
        r'^[ \t]*' + _esc + r'\s*=[ \t]*\{[ \t]*$',
        re.MULTILINE,
    )

    def _fn(body: str) -> str:
        # Phase 1 — remove simple / single-line cases
        new, n1 = _simple.subn('', body)
        if n1:
            logger.debug("  [-arg] %r  (×%d)", arg, n1)
            body = new

        # Phase 2 — remove multi-line map blocks with brace tracking
        out: list[str] = []
        pos = 0
        while pos < len(body):
            m = _multi.search(body, pos)
            if not m:
                out.append(body[pos:])
                break
            out.append(body[pos:m.start()])
            # find the opening `{` within the matched line and track depth
            open_brace = body.index('{', m.start())
            depth, i = 0, open_brace
            while i < len(body):
                if body[i] == '{':
                    depth += 1
                elif body[i] == '}':
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            # consume trailing newline
            if i < len(body) and body[i] == '\n':
                i += 1
            logger.debug("  [-arg-map] %r", arg)
            pos = i
        body = ''.join(out)
        return body

    return _fn


def _rename_arg(old: str, new_name: str) -> Callable[[str], str]:
    """Rename a top-level argument inside a resource block body."""
    pat = re.compile(rf'(?m)^([ \t]*){re.escape(old)}(\s*=\s)')
    def _fn(body: str) -> str:
        result, n = pat.subn(rf'\g<1>{new_name}\2', body)
        if n:
            logger.debug("  [~arg] %r → %r  (×%d)", old, new_name, n)
        return result
    return _fn


def _remove_block(block_name: str, reason: str = '') -> Callable[[str], str]:
    """
    Remove a nested block `block_name { … }` (handles arbitrary brace depth).
    Leaves a comment if `reason` is given.
    """
    header_re = re.compile(
        rf'(?m)^([ \t]*){re.escape(block_name)}(?:\s+"[^"]*")?\s*\{{'
    )
    def _fn(body: str) -> str:
        out: list[str] = []
        pos = 0
        while pos < len(body):
            m = header_re.search(body, pos)
            if not m:
                out.append(body[pos:])
                break
            out.append(body[pos:m.start()])
            indent = m.group(1)
            depth, i = 0, m.start()
            while i < len(body):
                ch = body[i]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            # consume trailing newline
            if i < len(body) and body[i] == '\n':
                i += 1
            if reason:
                out.append(f'{indent}# {block_name} removed — {reason}\n')
            logger.debug("  [-blk] %r", block_name)
            pos = i
        return ''.join(out)
    return _fn


def _rename_block(old: str, new_name: str) -> Callable[[str], str]:
    """Rename a nested block header `old {` → `new_name {`."""
    pat = re.compile(rf'(?m)^([ \t]*){re.escape(old)}(\s*\{{)')
    def _fn(body: str) -> str:
        result, n = pat.subn(rf'\g<1>{new_name}\2', body)
        if n:
            logger.debug("  [~blk] %r → %r  (×%d)", old, new_name, n)
        return result
    return _fn


def _sub(pattern: re.Pattern, replacement: str) -> Callable[[str], str]:
    """Generic regex substitution on a block body."""
    def _fn(body: str) -> str:
        return pattern.sub(replacement, body)
    return _fn


# ─────────────────────────────────────────────────────────────────────────────
#  Named special-case transforms (not factories — called directly)
# ─────────────────────────────────────────────────────────────────────────────

_ASG_KV_RE   = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|\d+|true|false|null)')
_ASG_TAGS_RE = re.compile(r'[ \t]*tags\s*=\s*\{([^}]*)\}', re.DOTALL)


def _convert_asg_tags(body: str) -> str:
    """
    aws_autoscaling_group: `tags = { Key = "V" }` map → repeated `tag {}` blocks.
    AWS provider v3+: only `tag {}` block syntax is accepted.
    """
    def _to_blocks(m: re.Match) -> str:
        pairs = _ASG_KV_RE.findall(m.group(1))
        if not pairs:
            return m.group(0)
        blocks = []
        for key, value in pairs:
            if not value.startswith('"'):
                value = f'"{value}"'
            blocks.append(
                f'  tag {{\n'
                f'    key                 = "{key}"\n'
                f'    value               = {value}\n'
                f'    propagate_at_launch = true\n'
                f'  }}'
            )
        result = '\n'.join(blocks)
        logger.debug("  [asg-tags] converted tags map → %d tag blocks", len(blocks))
        return result

    return _ASG_TAGS_RE.sub(_to_blocks, body)


def _hoist_cluster_mode(body: str) -> str:
    """
    aws_elasticache_replication_group v5:
    cluster_mode { num_node_groups = N  replicas_per_node_group = R }
    → num_node_groups = N  and  replicas_per_node_group = R  at top level.
    """
    pat = re.compile(r'([ \t]*)cluster_mode\s*\{([^}]*)\}', re.DOTALL)

    def _expand(m: re.Match) -> str:
        indent = m.group(1)
        inner  = m.group(2)
        parts: list[str] = []
        for attr in ('num_node_groups', 'replicas_per_node_group'):
            am = re.search(rf'{attr}\s*=\s*(\S+)', inner)
            if am:
                parts.append(f'{indent}{attr} = {am.group(1)}')
        return '\n'.join(parts) if parts else ''

    result, n = pat.subn(_expand, body)
    if n:
        logger.debug("  [hoist] cluster_mode args → top-level  (×%d)", n)
    return result


def _eip_vpc_to_domain(body: str) -> str:
    """aws_eip v5: `vpc = true` → `domain = "vpc"`"""
    result, n = re.subn(
        r'(?m)^([ \t]*)vpc\s*=\s*true[ \t]*$',
        r'\1domain = "vpc"',
        body,
    )
    if n:
        logger.debug("  [eip] vpc=true → domain=vpc  (×%d)", n)
    return result


def _fix_cpu_options(body: str) -> str:
    """
    aws_instance: cpu_core_count + cpu_threads_per_core deprecated in v5.
    Wrap them in a cpu_options {} block if both are present as top-level args.
    """
    core_m   = re.search(r'(?m)^([ \t]*)cpu_core_count\s*=\s*(\S+)', body)
    thread_m = re.search(r'(?m)^([ \t]*)cpu_threads_per_core\s*=\s*(\S+)', body)
    if not (core_m and thread_m):
        return body
    indent = core_m.group(1)
    cores   = core_m.group(2)
    threads = thread_m.group(2)
    # Remove old args
    body = re.sub(r'(?m)^[ \t]*cpu_core_count\s*=\s*\S+\n?', '', body)
    body = re.sub(r'(?m)^[ \t]*cpu_threads_per_core\s*=\s*\S+\n?', '', body)
    # Inject cpu_options block
    block = (
        f'{indent}cpu_options {{\n'
        f'{indent}  core_count       = {cores}\n'
        f'{indent}  threads_per_core = {threads}\n'
        f'{indent}}}\n'
    )
    body = body.rstrip('\n') + '\n' + block
    logger.debug("  [cpu] cpu_core_count + cpu_threads_per_core → cpu_options block")
    return body


# ─────────────────────────────────────────────────────────────────────────────
#  AWS v5 / v6  per-resource transform table
# ─────────────────────────────────────────────────────────────────────────────

_S3_RM_ARGS: list[str] = ['acl', 'policy', 'request_payer', 'acceleration_status']
_S3_RM_BLOCKS: list[tuple[str, str]] = [
    ('cors_rule',                            'use aws_s3_bucket_cors_configuration'),
    ('grant',                                'use aws_s3_bucket_acl with grants'),
    ('lifecycle_rule',                       'use aws_s3_bucket_lifecycle_configuration'),
    ('logging',                              'use aws_s3_bucket_logging'),
    ('object_lock_configuration',            'use aws_s3_bucket_object_lock_configuration'),
    ('replication_configuration',            'use aws_s3_bucket_replication_configuration'),
    ('server_side_encryption_configuration', 'use aws_s3_bucket_server_side_encryption_configuration'),
    ('versioning',                           'use aws_s3_bucket_versioning'),
    ('website',                              'use aws_s3_bucket_website_configuration'),
]

# tags_all is a COMPUTED attribute — never settable; LLMs sometimes hallucinate it
_RM_TAGS_ALL = _remove_arg('tags_all')

_TRANSFORMS: dict[str, list[Callable[[str], str]]] = {

    # ── S3 ───────────────────────────────────────────────────────────────────
    'aws_s3_bucket': (
        [_remove_arg(a) for a in _S3_RM_ARGS]
        + [_remove_block(b, r) for b, r in _S3_RM_BLOCKS]
        + [_RM_TAGS_ALL]
    ),

    # ── EC2 ──────────────────────────────────────────────────────────────────
    'aws_instance':   [_fix_cpu_options, _RM_TAGS_ALL],
    'aws_ebs_volume': [_RM_TAGS_ALL],
    'aws_ami':        [_RM_TAGS_ALL],
    # vpc = true → domain = "vpc" (v5 breaking change)
    'aws_eip': [_eip_vpc_to_domain, _RM_TAGS_ALL],

    # ── Auto Scaling ─────────────────────────────────────────────────────────
    # tags map → tag {} blocks
    'aws_autoscaling_group':       [_convert_asg_tags, _RM_TAGS_ALL],
    'aws_autoscaling_policy':      [_RM_TAGS_ALL],
    'aws_autoscaling_schedule':    [_RM_TAGS_ALL],
    # aws_launch_configuration: resource REMOVED in v5 — handled as special case

    # ── RDS ──────────────────────────────────────────────────────────────────
    # 'name' renamed to 'db_name' for initial DB name in aws_db_instance v5
    'aws_db_instance':        [_rename_arg('name', 'db_name'), _RM_TAGS_ALL],
    'aws_rds_cluster':        [_RM_TAGS_ALL],
    'aws_db_subnet_group':    [_RM_TAGS_ALL],
    'aws_db_parameter_group': [_RM_TAGS_ALL],
    'aws_db_option_group':    [_RM_TAGS_ALL],
    'aws_rds_cluster_instance': [_RM_TAGS_ALL],

    # ── ElastiCache ──────────────────────────────────────────────────────────
    'aws_elasticache_cluster': [
        _rename_arg('availability_zones', 'preferred_availability_zones'),
        _RM_TAGS_ALL,
    ],
    'aws_elasticache_replication_group': [
        _rename_arg('availability_zones', 'preferred_cache_cluster_azs'),
        _rename_arg('number_cache_clusters', 'num_cache_clusters'),
        _hoist_cluster_mode,          # cluster_mode {} → top-level attrs
        _RM_TAGS_ALL,
    ],
    'aws_elasticache_subnet_group':    [_RM_TAGS_ALL],
    'aws_elasticache_parameter_group': [_RM_TAGS_ALL],

    # ── WAFv2 ────────────────────────────────────────────────────────────────
    # managed_rule_group → managed_rule_group_statement
    'aws_wafv2_web_acl': [
        _rename_block('managed_rule_group', 'managed_rule_group_statement'),
        _RM_TAGS_ALL,
    ],
    'aws_wafv2_rule_group': [
        _rename_block('managed_rule_group', 'managed_rule_group_statement'),
        _RM_TAGS_ALL,
    ],
    'aws_wafv2_ip_set':            [_RM_TAGS_ALL],
    'aws_wafv2_regex_pattern_set': [_RM_TAGS_ALL],
    'aws_wafv2_web_acl_association': [],

    # ── random provider ──────────────────────────────────────────────────────
    # override_characters removed — correct arg is override_special
    'random_password': [_sub(re.compile(r'\boverride_characters\b'), 'override_special')],
    'random_string':   [_sub(re.compile(r'\boverride_characters\b'), 'override_special')],
    'random_pet':      [],
    'random_id':       [],

    # ── VPC / Networking ─────────────────────────────────────────────────────
    'aws_vpc':                     [_RM_TAGS_ALL],
    'aws_subnet':                  [_RM_TAGS_ALL],
    'aws_security_group':          [_RM_TAGS_ALL],
    'aws_internet_gateway':        [_RM_TAGS_ALL],
    'aws_nat_gateway':             [_RM_TAGS_ALL],
    'aws_route_table':             [_RM_TAGS_ALL],
    'aws_network_acl':             [_RM_TAGS_ALL],
    'aws_vpc_peering_connection':  [_RM_TAGS_ALL],
    'aws_vpn_gateway':             [_RM_TAGS_ALL],
    'aws_customer_gateway':        [_RM_TAGS_ALL],
    'aws_vpc_endpoint':            [_RM_TAGS_ALL],
    'aws_flow_log':                [_RM_TAGS_ALL],

    # ── Load Balancers ───────────────────────────────────────────────────────
    'aws_lb':                [_RM_TAGS_ALL],
    'aws_alb':               [_RM_TAGS_ALL],
    'aws_lb_target_group':   [_RM_TAGS_ALL],
    'aws_lb_listener':       [_RM_TAGS_ALL],
    'aws_lb_listener_rule':  [_RM_TAGS_ALL],

    # ── IAM ──────────────────────────────────────────────────────────────────
    'aws_iam_role':             [_RM_TAGS_ALL],
    'aws_iam_policy':           [_RM_TAGS_ALL],
    'aws_iam_user':             [_RM_TAGS_ALL],
    'aws_iam_group':            [_RM_TAGS_ALL],
    'aws_iam_instance_profile': [_RM_TAGS_ALL],

    # ── Lambda ───────────────────────────────────────────────────────────────
    'aws_lambda_function':             [_RM_TAGS_ALL],
    'aws_lambda_layer_version':        [_RM_TAGS_ALL],
    'aws_lambda_event_source_mapping': [_RM_TAGS_ALL],
    'aws_lambda_permission':           [],

    # ── ECS ──────────────────────────────────────────────────────────────────
    'aws_ecs_service':          [_RM_TAGS_ALL],
    'aws_ecs_task_definition':  [_RM_TAGS_ALL],
    'aws_ecs_cluster':          [_RM_TAGS_ALL],
    'aws_ecs_capacity_provider':[_RM_TAGS_ALL],

    # ── EKS ──────────────────────────────────────────────────────────────────
    'aws_eks_cluster':    [_RM_TAGS_ALL],
    'aws_eks_node_group': [_RM_TAGS_ALL],
    'aws_eks_addon':      [_RM_TAGS_ALL],

    # ── Route53 ──────────────────────────────────────────────────────────────
    'aws_route53_zone':         [_RM_TAGS_ALL],
    'aws_route53_health_check': [_RM_TAGS_ALL],

    # ── CloudFront ────────────────────────────────────────────────────────────
    'aws_cloudfront_distribution':              [_RM_TAGS_ALL],
    'aws_cloudfront_origin_access_identity':    [_RM_TAGS_ALL],
    'aws_cloudfront_origin_access_control':     [_RM_TAGS_ALL],

    # ── ACM ──────────────────────────────────────────────────────────────────
    'aws_acm_certificate':            [_RM_TAGS_ALL],
    'aws_acm_certificate_validation': [],

    # ── KMS ──────────────────────────────────────────────────────────────────
    'aws_kms_key':   [_RM_TAGS_ALL],
    'aws_kms_alias': [],

    # ── SNS / SQS ────────────────────────────────────────────────────────────
    'aws_sns_topic':              [_RM_TAGS_ALL],
    'aws_sns_topic_subscription': [],
    'aws_sqs_queue':              [_RM_TAGS_ALL],

    # ── DynamoDB ─────────────────────────────────────────────────────────────
    'aws_dynamodb_table': [_RM_TAGS_ALL],

    # ── CloudWatch ────────────────────────────────────────────────────────────
    'aws_cloudwatch_log_group':    [_RM_TAGS_ALL],
    'aws_cloudwatch_metric_alarm': [_RM_TAGS_ALL],
    'aws_cloudwatch_dashboard':    [_RM_TAGS_ALL],

    # ── Secrets Manager / SSM ─────────────────────────────────────────────────
    'aws_secretsmanager_secret': [_RM_TAGS_ALL],
    'aws_ssm_parameter':         [_RM_TAGS_ALL],

    # ── ECR ──────────────────────────────────────────────────────────────────
    'aws_ecr_repository':         [_RM_TAGS_ALL],
    'aws_ecr_lifecycle_policy':   [],

    # ── MSK (Kafka) ───────────────────────────────────────────────────────────
    'aws_msk_cluster':       [_RM_TAGS_ALL],
    'aws_msk_configuration': [_RM_TAGS_ALL],

    # ── OpenSearch / Elasticsearch ────────────────────────────────────────────
    'aws_opensearch_domain':    [_RM_TAGS_ALL],
    'aws_elasticsearch_domain': [_RM_TAGS_ALL],

    # ── API Gateway ───────────────────────────────────────────────────────────
    'aws_api_gateway_rest_api': [_RM_TAGS_ALL],
    'aws_api_gateway_stage':    [_RM_TAGS_ALL],
    'aws_apigatewayv2_api':     [_RM_TAGS_ALL],
    'aws_apigatewayv2_stage':   [_RM_TAGS_ALL],

    # ── Elastic Beanstalk ─────────────────────────────────────────────────────
    'aws_elastic_beanstalk_application': [_RM_TAGS_ALL],
    'aws_elastic_beanstalk_environment': [_RM_TAGS_ALL],

    # ── CodeBuild / CodePipeline ──────────────────────────────────────────────
    'aws_codebuild_project':  [_RM_TAGS_ALL],
    'aws_codepipeline':       [_RM_TAGS_ALL],
}

# ── Resource types RENAMED in v5 (applied globally — both declaration + references) ──
_RESOURCE_TYPE_RENAMES: dict[str, str] = {
    'aws_s3_bucket_object': 'aws_s3_object',
}

# ── Resource types REMOVED in v5 (replaced by a different resource) ───────────
_REMOVED_RESOURCE_TYPES: set[str] = {
    'aws_launch_configuration',   # → aws_launch_template
}


# ─────────────────────────────────────────────────────────────────────────────
#  HCL resource block iterator
# ─────────────────────────────────────────────────────────────────────────────

_RESOURCE_HDR = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{')


def _iter_resource_blocks(content: str) -> Iterator[tuple[int, int, str, str, int, str]]:
    """
    Yield (start, end, resource_type, resource_name, body_start, body) for
    every resource block in `content`.

    start      – position of the `resource` keyword
    end        – position just AFTER the closing `}`
    body_start – position just AFTER the opening `{`
    body       – text between `{` and `}`
    """
    for m in _RESOURCE_HDR.finditer(content):
        # m.end()-1 is the opening '{' (last char of the regex match)
        depth = 0
        i = m.end() - 1
        body_start = m.end()
        while i < len(content):
            ch = content[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    yield (
                        m.start(), i + 1,
                        m.group(1), m.group(2),
                        body_start, content[body_start:i],
                    )
                    break
            i += 1


# ─────────────────────────────────────────────────────────────────────────────
#  Core apply functions
# ─────────────────────────────────────────────────────────────────────────────

def _apply_resource_transforms(content: str) -> str:
    """Apply all registered per-resource-type transforms to `content`."""
    blocks = list(_iter_resource_blocks(content))
    if not blocks:
        return content

    # Process in REVERSE order so byte offsets of earlier blocks stay valid
    for start, end, rtype, rname, body_start, body in reversed(blocks):

        # Special: resource type fully removed in v5
        if rtype in _REMOVED_RESOURCE_TYPES:
            replacement = (
                f'# NOTE: resource type "{rtype}" was removed in AWS provider v5.\n'
                f'# Rewrite "{rname}" as aws_launch_template. Docs:\n'
                f'# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/launch_template\n'
            )
            logger.info("schema_fixer: stub out removed resource %r/%r", rtype, rname)
            content = content[:start] + replacement + content[end:]
            continue

        transforms = _TRANSFORMS.get(rtype)
        if not transforms:
            continue

        new_body = body
        for t in transforms:
            new_body = t(new_body)

        if new_body != body:
            logger.info("schema_fixer: patched %r / %r", rtype, rname)
            # Splice: keep header, replace body, keep closing brace + rest
            content = content[:body_start] + new_body + content[body_start + len(body):]

    return content


def _apply_global_renames(content: str) -> str:
    """
    Apply resource-type renames globally (both `resource "TYPE"` declarations
    AND all `TYPE.name.attr` reference expressions).
    """
    for old, new in _RESOURCE_TYPE_RENAMES.items():
        pat = re.compile(rf'\b{re.escape(old)}\b')
        new_content, n = pat.subn(new, content)
        if n:
            logger.info(
                "schema_fixer: renamed resource type %r → %r  (×%d)", old, new, n
            )
        content = new_content
    return content


# ─────────────────────────────────────────────────────────────────────────────
#  Public entry points
# ─────────────────────────────────────────────────────────────────────────────

def _repair_broken_iam_policy(content: str) -> str:
    """
    Detect and repair the specific breakage where `policy = jsonencode({` was
    stripped by an LLM pass, leaving orphaned JSON-like content inside an IAM
    resource block:

      resource "aws_iam_role_policy" "x" {
        name = "..."
        role = ...
          Version = "2012-10-17"     ← broken: no 'policy = jsonencode({' opener
          Statement = [...]
        })                           ← dangling closing paren+brace

    Repairs by re-inserting the missing `  policy = jsonencode({` wrapper.
    """
    # Detect: aws_iam_role_policy / aws_iam_policy block whose body contains
    # orphaned JSON-like keys (Version, Statement) that are more deeply indented
    # than the surrounding args, without a 'policy = jsonencode(' line before them.
    _orphan_re = re.compile(
        r'^(resource\s+"aws_iam(?:_role)?_policy"\s+"([^"]+)"\s*\{)\n'
        r'((?:  [ \t]*\w[^\n]*\n)*?)'   # leading args (name, role, path) at 2-space indent
        r'(    +)(Version\s*=)',         # orphaned JSON content indented at 4+ spaces
        re.MULTILINE,
    )

    def _repair(m: re.Match) -> str:
        header    = m.group(1)   # resource "..." "..." {
        rname     = m.group(2)
        leading   = m.group(3)   # name/role/path args
        indent    = m.group(4)   # indentation of Version line
        ver_start = m.group(5)   # "Version ="
        # Skip if policy = jsonencode( is already present before Version
        if 'jsonencode' in leading:
            return m.group(0)
        logger.info(
            "schema_fixer: repairing broken policy=jsonencode block in '%s'", rname,
        )
        return f"{header}\n{leading}  policy = jsonencode({{\n{indent}{ver_start}"

    patched, n = _orphan_re.subn(_repair, content)
    if n:
        # Fix dangling `  })` closing — ensure it closes the jsonencode call properly
        patched = re.sub(r'^[ \t]*\}\)', r'  })', patched, flags=re.MULTILINE)
    return patched


def fix_content(filename: str, content: str) -> str:
    """
    Apply all AWS v5/v6 schema fixes to a single .tf file's content string.
    Safe to call on non-.tf files (returns unchanged).
    """
    if not filename.endswith('.tf'):
        return content
    content = _repair_broken_iam_policy(content)
    content = _apply_global_renames(content)
    content = _apply_resource_transforms(content)
    return content


def apply_aws_schema_fixes(files: list) -> list:
    """
    Apply all AWS v5/v6 schema fixes to a list of TerraformFile objects.
    Returns a new list; originals are not mutated.
    """
    from app.models.schemas import TerraformFile  # local import to avoid circular
    result = []
    for f in files:
        fixed = fix_content(f.filename, f.content)
        result.append(TerraformFile(
            filename=f.filename,
            content=fixed,
            description=f.description,
        ))
    return result
