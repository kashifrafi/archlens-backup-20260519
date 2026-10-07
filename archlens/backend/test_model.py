#!/usr/bin/env python3
"""Quick test of the new GPT-5.3-codex model configuration."""

import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
api_key = os.getenv("AZURE_OPENAI_API_KEY")
deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
api_version = os.getenv("AZURE_OPENAI_API_VERSION")

print(f"Testing Azure OpenAI configuration:")
print(f"  Endpoint: {endpoint}")
print(f"  Deployment: {deployment}")
print(f"  API Version: {api_version}")
print()

try:
    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )
    
    print("Attempting simple completion...")
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'Hello, World!' in JSON format with a 'message' field."}
        ],
        max_tokens=100,
        temperature=0.7,
    )
    
    print("✅ SUCCESS!")
    print(f"Response: {response.choices[0].message.content}")
    print(f"Finish reason: {response.choices[0].finish_reason}")
    
except Exception as e:
    print(f"❌ ERROR: {type(e).__name__}")
    print(f"   {str(e)}")
    import traceback
    traceback.print_exc()
