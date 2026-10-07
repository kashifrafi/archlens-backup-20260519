#!/usr/bin/env python3
"""Check available deployments at the Azure OpenAI endpoint."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT").rstrip('/')
api_key = os.getenv("AZURE_OPENAI_API_KEY")
api_version = os.getenv("AZURE_OPENAI_API_VERSION")

print(f"Checking deployments at: {endpoint}")
print()

# Try to list deployments using Azure OpenAI management API
url = f"{endpoint}/openai/deployments?api-version={api_version}"
headers = {
    "api-key": api_key
}

print(f"Request URL: {url}")
print()

try:
    response = requests.get(url, headers=headers)
    print(f"Status: {response.status_code}")
    print()
    
    if response.status_code == 200:
        data = response.json()
        print("✅ Available deployments:")
        if 'data' in data:
            for dep in data['data']:
                print(f"  - {dep.get('id')} (model: {dep.get('model')})")
        else:
            print("Response:", data)
    else:
        print(f"❌ Error: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"❌ Exception: {type(e).__name__}")
    print(f"   {str(e)}")
