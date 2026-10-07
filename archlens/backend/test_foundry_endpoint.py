#!/usr/bin/env python3
"""Test Azure AI Foundry serverless inference endpoint."""

import requests

endpoint = "https://terraformtest12.openai.azure.com/openai/responses?api-version=2025-04-01-preview"
api_key = "2JY9RGURZZlYgRSq8Wdcl2toakXicBvXmS7qaiHnFct3UGKAf0MUJQQJ99CEACYeBjFXJ3w3AAABACOG6X8p"

print("Testing Azure AI Foundry Serverless Inference Endpoint")
print("=" * 70)
print(f"Endpoint: {endpoint}")
print()

try:
    response = requests.post(
        endpoint,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        json={
            "input": [
                {
                    "role": "user",
                    "content": "Say 'Hello, World!' in JSON format with a message field"
                }
            ],
            "max_output_tokens": 100,
            "model": "gpt-5.3-codex"
        },
        timeout=30
    )
    
    print(f"Status: {response.status_code}")
    print()
    
    if response.status_code == 200:
        print("✅ SUCCESS!")
        print()
        result = response.json()
        print("Response:")
        print(result)
        print()
        
        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0].get('message', {}).get('content', '')
            print(f"Message content: {content}")
        
    else:
        print(f"❌ ERROR: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"❌ Exception: {type(e).__name__}")
    print(f"   {str(e)}")
    import traceback
    traceback.print_exc()
