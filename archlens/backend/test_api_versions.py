#!/usr/bin/env python3
"""Try different API versions to find the working one."""

import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
api_key = os.getenv("AZURE_OPENAI_API_KEY")
deployment = "gpt-5.3-codex"

# Try different API versions
api_versions = [
    "2024-08-01-preview",
    "2024-06-01",
    "2024-05-01-preview",
    "2024-02-01",
    "2023-12-01-preview",
    "2023-05-15",
]

print(f"Testing deployment: {deployment}")
print(f"Endpoint: {endpoint}")
print("=" * 60)
print()

for api_version in api_versions:
    print(f"Trying API version: {api_version}...")
    try:
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "user", "content": "Say 'test' in JSON with a message field"}
            ],
            max_tokens=50,
            temperature=0,
        )
        
        print(f"✅ SUCCESS with {api_version}!")
        print(f"   Response: {response.choices[0].message.content}")
        print(f"   Finish reason: {response.choices[0].finish_reason}")
        print()
        print(f"🎯 USE THIS IN .env:")
        print(f"   AZURE_OPENAI_API_VERSION={api_version}")
        break
        
    except Exception as e:
        error_msg = str(e)
        if "unsupported" in error_msg.lower():
            print(f"   ❌ Unsupported")
        elif "not found" in error_msg.lower() or "404" in error_msg:
            print(f"   ❌ Not found (wrong deployment name?)")
        elif "unauthorized" in error_msg.lower() or "401" in error_msg:
            print(f"   ❌ Unauthorized (wrong API key?)")
        else:
            print(f"   ❌ Error: {error_msg[:80]}")
    print()

print("=" * 60)
print("Test complete")
