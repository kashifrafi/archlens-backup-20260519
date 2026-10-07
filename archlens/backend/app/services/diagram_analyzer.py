import base64
import html
import io
import json
import re
import zipfile
import zlib
import urllib.parse
from typing import Optional, List
import xml.etree.ElementTree as ET

from openai import AzureOpenAI, OpenAI

from app.config import settings
from app.models.schemas import DiagramAnalysisResponse, ArchComponent, UserContext
from app.services.context_helper import format_user_context


def _get_client():
    """Return OpenAI client (Azure preferred, falls back to OpenAI)."""
    if settings.azure_openai_endpoint and settings.azure_openai_api_key:
        return AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        ), settings.azure_openai_deployment
    elif settings.openai_api_key:
        return OpenAI(api_key=settings.openai_api_key), settings.openai_model
    else:
        raise ValueError(
            "No AI API credentials configured. Set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY "
            "or OPENAI_API_KEY in the .env file."
        )


# ── draw.io XML parsing ───────────────────────────────────────────────────────

def _decode_drawio_compressed(b64_data: str) -> Optional[str]:
    """draw.io compressed mxfile diagrams use base64 + raw deflate + URL decode."""
    try:
        raw = base64.b64decode(b64_data)
        decompressed = zlib.decompress(raw, -zlib.MAX_WBITS)
        return urllib.parse.unquote(decompressed.decode("utf-8"))
    except Exception:
        return None


def _try_decode_base64_text(text: str) -> Optional[str]:
    try:
        decoded = base64.b64decode(text, validate=True)
        zipped = _try_extract_zip_xml(decoded)
        if zipped:
            return zipped
        return decoded.decode("utf-8-sig")
    except Exception:
        return None


def _try_extract_zip_xml(data: bytes) -> Optional[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = sorted(
                name for name in archive.namelist()
                if name.lower().endswith((".drawio", ".xml"))
            ) or archive.namelist()
            for name in names:
                try:
                    content = archive.read(name)
                    text = content.decode("utf-8-sig")
                    if "<mxfile" in text or "<mxGraphModel" in text:
                        return text
                except Exception:
                    continue
    except Exception:
        return None
    return None


def _extract_xml_fragment(text: str) -> str:
    markers = ["<?xml", "<mxfile", "<mxGraphModel", "<svg"]
    positions = [text.find(marker) for marker in markers]
    positions = [pos for pos in positions if pos >= 0]
    if positions:
        return text[min(positions):]
    return text


def _normalize_drawio_xml(xml_text: str) -> str:
    """Normalize common uploaded draw.io payload variants into XML text."""
    text = str(xml_text or "").replace("\x00", "").strip().lstrip("\ufeff")

    if text.startswith("data:") and "," in text:
        header, payload = text.split(",", 1)
        if ";base64" in header.lower():
            decoded = _try_decode_base64_text(payload)
            if decoded:
                text = decoded
        else:
            text = urllib.parse.unquote(payload)

    text = text.strip().lstrip("\ufeff")
    if text.lower().startswith("%3c"):
        text = urllib.parse.unquote(text).strip().lstrip("\ufeff")

    if not text.startswith("<"):
        decoded = _try_decode_base64_text(text)
        if decoded:
            text = decoded.strip().lstrip("\ufeff")

    if ("&lt;mxfile" in text or "&lt;mxGraphModel" in text) and not text.lstrip().startswith("<svg"):
        text = html.unescape(text)

    return _extract_xml_fragment(text).strip()


def _extract_svg_drawio_content(root: ET.Element) -> Optional[str]:
    """diagrams.net SVG exports often store the mxfile XML in a content attribute."""
    for elem in root.iter():
        content = elem.get("content")
        if content and ("mxfile" in content or "mxGraphModel" in content):
            return html.unescape(urllib.parse.unquote(content))
    return None


def _strip_html(text: str) -> str:
    """Remove HTML tags and entities from drawio cell labels."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\s+", " ", text).strip()


def parse_drawio_xml(xml_text: str) -> dict:
    """Parse a .drawio / mxfile XML and extract shape labels, styles, edges."""
    if not xml_text or not xml_text.strip():
        raise ValueError("Empty drawio XML")

    xml_text = _normalize_drawio_xml(xml_text)

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        prefix = re.sub(r"\s+", " ", xml_text[:80]).strip()
        raise ValueError(f"Invalid draw.io XML after normalization: {e}. Content starts with: {prefix!r}")

    svg_content = _extract_svg_drawio_content(root)
    if svg_content:
        try:
            root = ET.fromstring(_normalize_drawio_xml(svg_content))
        except ET.ParseError:
            pass

    # mxfile may contain compressed <diagram>BASE64</diagram>
    diagrams = root.findall(".//diagram")
    decoded_xml = None
    if diagrams:
        for d in diagrams:
            inner = (d.text or "").strip()
            if inner and not inner.startswith("<"):
                decoded_xml = _decode_drawio_compressed(inner)
                if decoded_xml:
                    break
            elif inner.startswith("<"):
                decoded_xml = inner
                break

    if decoded_xml:
        try:
            graph_root = ET.fromstring(decoded_xml)
        except ET.ParseError:
            graph_root = root
    else:
        graph_root = root

    shapes: List[dict] = []
    edges: List[dict] = []

    parent_by_child = {
        child: parent
        for parent in graph_root.iter()
        for child in list(parent)
    }

    def object_parent_for_cell(cell: ET.Element) -> Optional[ET.Element]:
        parent = parent_by_child.get(cell)
        if parent is None or parent.tag != "object":
            return None
        return parent

    def object_label_for_cell(cell: ET.Element) -> str:
        parent = object_parent_for_cell(cell)
        if parent is None:
            return ""
        for attr in ("label", "name", "value"):
            label = _strip_html(parent.get(attr, ""))
            if label:
                return label
        return ""

    for cell in graph_root.iter("mxCell"):
        object_parent = object_parent_for_cell(cell)
        cid = cell.get("id", "") or (object_parent.get("id", "") if object_parent is not None else "")
        value = _strip_html(cell.get("value", "")) or object_label_for_cell(cell)
        style = cell.get("style", "") or ""
        is_edge = cell.get("edge") == "1"
        is_vertex = cell.get("vertex") == "1"
        source = cell.get("source")
        target = cell.get("target")

        if is_edge:
            edges.append({"id": cid, "label": value, "source": source, "target": target})
        elif is_vertex and value:
            shape_hint = ""
            m = re.search(r"shape=([^;]+)", style)
            if m:
                shape_hint = m.group(1)
            elif "mxgraph." in style:
                m2 = re.search(r"mxgraph\.([^;=]+)", style)
                if m2:
                    shape_hint = m2.group(1)
            shapes.append({"id": cid, "label": value, "shape_hint": shape_hint})

    label_by_id = {s["id"]: s["label"] for s in shapes}
    for e in edges:
        e["source_label"] = label_by_id.get(e.get("source"), "")
        e["target_label"] = label_by_id.get(e.get("target"), "")

    return {"shapes": shapes, "edges": edges}


def _build_drawio_prompt(parsed: dict, filename: Optional[str] = None) -> str:
    shape_lines = []
    for s in parsed["shapes"]:
        hint = f" [{s['shape_hint']}]" if s["shape_hint"] else ""
        shape_lines.append(f"- {s['label']}{hint}")

    edge_lines = []
    for e in parsed["edges"]:
        if e["source_label"] or e["target_label"]:
            label = f" ({e['label']})" if e["label"] else ""
            edge_lines.append(f"- {e['source_label']} → {e['target_label']}{label}")

    file_hint = f"\nSource file: {filename}" if filename else ""
    return f"""I extracted this architecture from a draw.io (.drawio) diagram XML.{file_hint}

SHAPES / NODES ({len(parsed['shapes'])}):
{chr(10).join(shape_lines) if shape_lines else '(no labeled shapes found)'}

CONNECTIONS / EDGES ({len(parsed['edges'])}):
{chr(10).join(edge_lines) if edge_lines else '(no edges)'}

Use the shape hints (which often reference cloud icon libraries like aws4, azure2, gcp) to infer the cloud services. Analyze this architecture and return the JSON described in the system prompt."""


# ── System prompt (shared) ────────────────────────────────────────────────────

ANALYSIS_SYSTEM_PROMPT = """You are an expert cloud architect who analyzes architecture diagrams.
Given an architecture diagram (image or extracted draw.io shapes), extract ALL components and return a structured JSON analysis.

Return ONLY valid JSON matching this exact schema:
{
  "architecture_type": "string (e.g. 'Three-Tier Web Application', 'Microservices', 'Event-Driven', 'Serverless', 'Data Pipeline', 'Hybrid Cloud', etc.)",
  "description": "string - concise description of what the architecture does",
  "components": [
    {
      "name": "string - component name as shown in diagram",
      "type": "string - generic type (LoadBalancer, WebServer, Database, Cache, Queue, Storage, CDN, APIGateway, Container, Function, VPN, Firewall, etc.)",
      "category": "string - one of: compute, storage, network, database, security, messaging, monitoring, identity, devops, analytics",
      "description": "string - what this component does in this architecture",
      "aws_equivalent": "string - AWS service equivalent (e.g. ALB, EC2, RDS, ElastiCache, SQS, S3, CloudFront)",
      "azure_equivalent": "string - Azure service equivalent (e.g. Azure Load Balancer, VM, Azure SQL, Redis Cache, Service Bus, Blob Storage, Azure CDN)",
      "gcp_equivalent": "string - GCP service equivalent (e.g. Cloud Load Balancing, Compute Engine, Cloud SQL, Memorystore, Pub/Sub, Cloud Storage, Cloud CDN)"
    }
  ],
  "detected_services": {
    "aws": ["list of AWS service names for this architecture"],
    "azure": ["list of Azure service names for this architecture"],
    "gcp": ["list of GCP service names for this architecture"]
  }
}

Be thorough - identify ALL components including networking, security, monitoring that may be implied."""


# ── JSON repair helper ────────────────────────────────────────────────────────

def _safe_json_loads(raw: str, finish_reason: Optional[str] = None) -> dict:
    """Parse JSON, attempting to repair if the response was truncated."""
    if not raw:
        raise ValueError("Empty response from AI model")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # Attempt to repair truncated JSON (common when finish_reason == 'length')
        repaired = _repair_truncated_json(raw)
        if repaired is not None:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
        hint = ""
        if finish_reason == "length":
            hint = " (response was truncated by max_tokens limit; try a smaller diagram)"
        raise ValueError(f"AI returned malformed JSON{hint}: {e}") from e


def _repair_truncated_json(raw: str) -> Optional[str]:
    """Best-effort repair of JSON truncated mid-string/array/object."""
    s = raw.strip()
    # Trim trailing partial token (incomplete number, true/false/null, etc.)
    # Find the last "safe" position: end of a complete value (}, ], ", digit, e/l)
    # Strategy: walk and track structure, then close open scopes.
    stack = []
    in_string = False
    escape = False
    last_safe = 0
    for i, ch in enumerate(s):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
                last_safe = i + 1
        else:
            if ch == '"':
                in_string = True
            elif ch in "{[":
                stack.append("}" if ch == "{" else "]")
            elif ch in "}]":
                if stack:
                    stack.pop()
                last_safe = i + 1
            elif ch in ",:":
                last_safe = i + 1
            elif ch.isspace():
                pass
            else:
                # value char (digit, t/f/n letters) - mark safe at next delimiter
                pass

    truncated = s[:last_safe].rstrip().rstrip(",")
    # Close any open string
    if in_string:
        truncated += '"'
    # Close open scopes in reverse
    while stack:
        truncated += stack.pop()
    return truncated


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_diagram(
    image_base64: Optional[str] = None,
    mime_type: str = "image/png",
    drawio_xml: Optional[str] = None,
    source_filename: Optional[str] = None,
    user_context: Optional[UserContext] = None,
) -> DiagramAnalysisResponse:
    """Analyze an architecture diagram from either an image or draw.io XML."""
    client, model = _get_client()
    ctx_block = format_user_context(user_context)

    if drawio_xml:
        parsed = parse_drawio_xml(drawio_xml)
        if not parsed["shapes"]:
            raise ValueError("No labeled shapes could be extracted from the draw.io XML")
        user_prompt = _build_drawio_prompt(parsed, source_filename)
        if ctx_block:
            user_prompt = ctx_block + "\n" + user_prompt
        messages = [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    elif image_base64:
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]
        messages = [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_base64}",
                            "detail": "auto",
                        },
                    },
                    {
                        "type": "text",
                        "text": (ctx_block + "\n" if ctx_block else "") + "Analyze this architecture diagram and extract all components as JSON.",
                    },
                ],
            },
        ]
    else:
        raise ValueError("Either image_base64 or drawio_xml must be provided")

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=4000,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    finish_reason = response.choices[0].finish_reason
    data = _safe_json_loads(raw, finish_reason)

    components = [ArchComponent(**c) for c in data.get("components", [])]
    return DiagramAnalysisResponse(
        components=components,
        architecture_type=data.get("architecture_type", "Unknown"),
        description=data.get("description", ""),
        detected_services=data.get("detected_services", {"aws": [], "azure": [], "gcp": []}),
        raw_analysis=raw,
    )
