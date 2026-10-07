#!/usr/bin/env python3
"""Test connectivity to Azure OpenAI endpoint."""

import requests

endpoint = "https://terraformtest12.openai.azure.com/"
api_key = "2JY9RGURZZlYgRSq8Wdcl2toakXicBvXmS7qaiHnFct3UGKAf0MUJQQJ99CEACYeBjFXJ3w3AAABACOG6X8p"

print(f"Testing endpoint: {endpoint}")
print("=" * 70)
print()

# Test 1: Basic connectivity
print("Test 1: Basic connectivity (GET /)")
try:
    response = requests.get(endpoint, timeout=10)
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.text[:200]}")
except Exception as e:
    print(f"  Error: {e}")
print()

# Test 2: Try to list models/deployments
print("Test 2: List deployments")
api_versions = ["2024-08-01-preview", "2024-05-01-preview", "2023-05-15"]
for api_version in api_versions:
    url = f"{endpoint.rstrip('/')}/openai/deployments?api-version={api_version}"
    print(f"  Trying: {api_version}")
    try:
        response = requests.get(
            url,
            headers={"api-key": api_key},
            timeout=10
        )
        print(f"    Status: {response.status_code}")
        if response.status_code == 200:
            print(f"    Response: {response.json()}")
            break
        else:
            print(f"    Error: {response.text[:150]}")
    except Exception as e:
        print(f"    Exception: {e}")
print()

# Test 3: Try chat completion with different deployments
print("Test 3: Test chat completion")
test_deployments = ["gpt-5.3-codex", "gpt-4", "gpt-35-turbo", "default"]
for deployment in test_deployments:
    print(f"  Testing deployment: {deployment}")
    for api_version in ["2024-05-01-preview", "2023-05-15"]:
        url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        try:
            response = requests.post(
                url,
                headers={
                    "api-key": api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 5
                },
                timeout=15
            )
            print(f"    API {api_version}: Status {response.status_code}")
            if response.status_code == 200:
                print(f"    ✅ SUCCESS!")
                result = response.json()
                print(f"    Response: {result.get('choices', [{}])[0].get('message', {}).get('content', 'N/A')}")
                print()
                print(f"🎯 Working configuration:")
                print(f"   Endpoint: {endpoint}")
                print(f"   Deployment: {deployment}")
                print(f"   API Version: {api_version}")
                exit(0)
            else:
                error = response.text[:150]
                if "not found" in error.lower() or "404" in str(response.status_code):
                    print(f"      Not found")
                elif "unsupported" in error.lower():
                    print(f"      Unsupported")
                else:
                    print(f"      Error: {error}")
        except Exception as e:
            print(f"      Exception: {str(e)[:80]}")
print()
print("=" * 70)
print("❌ No working configuration found")
