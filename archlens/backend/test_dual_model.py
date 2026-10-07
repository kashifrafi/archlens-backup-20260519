#!/usr/bin/env python3
"""Test that both models are configured correctly."""

import sys
sys.path.insert(0, '/home/mdrafi/projects/project-kashif/archlens/backend')

from app.config import settings
from app.services.diagram_analyzer import _get_client as get_analyzer_client
from app.services.terraform_service import _get_client as get_terraform_client

print("=" * 70)
print("ArchLens Dual-Model Configuration Test")
print("=" * 70)
print()

print("📊 Analysis/WAF/Pricing Services (GPT-4.1):")
print(f"  Endpoint: {settings.azure_openai_endpoint}")
print(f"  Deployment: {settings.azure_openai_deployment}")
print(f"  API Version: {settings.azure_openai_api_version}")
print()

print("🛠️  Terraform Generation Service (GPT-5.3-codex):")
print(f"  Endpoint: {settings.azure_foundry_endpoint}")
print(f"  Deployment: {settings.azure_foundry_deployment}")
print(f"  API Version: {settings.azure_foundry_api_version}")
print()

print("=" * 70)
print("Testing Client Initialization...")
print("=" * 70)
print()

try:
    print("1. Testing Analysis Client (GPT-4.1)...")
    analyzer_client, analyzer_model = get_analyzer_client()
    print(f"   ✅ Client type: {type(analyzer_client).__name__}")
    print(f"   ✅ Model: {analyzer_model}")
    print()
except Exception as e:
    print(f"   ❌ Error: {e}")
    print()

try:
    print("2. Testing Terraform Client (GPT-5.3-codex)...")
    terraform_client, terraform_model = get_terraform_client()
    print(f"   ✅ Client type: {type(terraform_client).__name__}")
    print(f"   ✅ Model: {terraform_model}")
    print()
except Exception as e:
    print(f"   ❌ Error: {e}")
    print()

print("=" * 70)
print("Testing Simple Completions...")
print("=" * 70)
print()

try:
    print("1. Testing GPT-4.1 (Analysis)...")
    response = analyzer_client.chat.completions.create(
        model=analyzer_model,
        messages=[{"role": "user", "content": "Say 'GPT-4.1 working' in JSON with a status field"}],
        max_tokens=50
    )
    content = response.choices[0].message.content
    print(f"   ✅ Response: {content}")
    print()
except Exception as e:
    print(f"   ❌ Error: {e}")
    print()

try:
    print("2. Testing GPT-5.3-codex (Terraform)...")
    response = terraform_client.chat.completions.create(
        model=terraform_model,
        messages=[{"role": "user", "content": "Say 'GPT-5.3-codex working' in JSON with a status field"}],
        max_tokens=50
    )
    content = response.choices[0].message.content
    print(f"   ✅ Response: {content}")
    print()
except Exception as e:
    print(f"   ❌ Error: {e}")
    print()

print("=" * 70)
print("✅ Dual-Model Configuration Test Complete!")
print("=" * 70)
