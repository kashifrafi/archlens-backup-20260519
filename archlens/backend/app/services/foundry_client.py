"""
Azure AI Foundry Responses API client wrapper.

This client adapts the Azure AI Foundry Responses API to work with 
the standard OpenAI client interface used by ArchLens.
"""
import requests
from typing import List, Dict, Optional, Any


class FoundryResponsesClient:
    """Client for Azure AI Foundry Responses API that mimics OpenAI client interface."""
    
    def __init__(self, endpoint: str, api_key: str, model: str, api_version: str = "2025-04-01-preview"):
        """
        Initialize the Foundry Responses API client.
        
        Args:
            endpoint: Azure endpoint URL (e.g., "https://xxx.openai.azure.com/")
            api_key: API key for authentication
            model: Model deployment name (e.g., "gpt-5.3-codex")
            api_version: API version (default: 2025-04-01-preview)
        """
        self.endpoint = endpoint.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.api_version = api_version
        self.url = f"{self.endpoint}/openai/responses?api-version={api_version}"
        
        # Mimic OpenAI client structure
        self.chat = self
        self.completions = self
    
    def create(
        self,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 1.0,
        top_p: float = 0.98,
        response_format: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> 'FoundryResponse':
        """
        Create a chat completion using the Responses API.
        
        This method signature matches the OpenAI client API for compatibility.
        """
        # Use provided model or default
        model_name = model or self.model
        
        # Convert messages to input format
        input_messages = messages or []
        
        # Build request payload
        payload = {
            "model": model_name,
            "input": input_messages,
            "temperature": temperature,
            "top_p": top_p,
        }
        
        # Add max_output_tokens if specified
        if max_tokens:
            payload["max_output_tokens"] = max_tokens
        
        # Add response format if JSON mode requested
        if response_format and response_format.get("type") == "json_object":
            payload["text"] = {
                "format": {"type": "json_object"},
                "verbosity": "medium"
            }
        
        # Make API request
        response = requests.post(
            self.url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            json=payload,
            timeout=180  # Increased to 3 minutes for complex architectures
        )
        
        if response.status_code != 200:
            raise Exception(f"Foundry API error {response.status_code}: {response.text}")
        
        result = response.json()
        
        # Return wrapped response that mimics OpenAI response structure
        return FoundryResponse(result)


class FoundryResponse:
    """Wrapper for Foundry Responses API response to mimic OpenAI response structure."""
    
    def __init__(self, raw_response: Dict[str, Any]):
        self.raw = raw_response
        self.choices = [FoundryChoice(raw_response)]
        self.model = raw_response.get("model", "")
        self.id = raw_response.get("id", "")
        self.created = raw_response.get("created_at", 0)
        self.usage = raw_response.get("usage", {})


class FoundryChoice:
    """Wrapper for Foundry output to mimic OpenAI choice structure."""
    
    def __init__(self, raw_response: Dict[str, Any]):
        self.raw = raw_response
        
        # Extract content from output[0].content[0].text
        output_list = raw_response.get("output", [])
        if output_list and len(output_list) > 0:
            output = output_list[0]
            content_list = output.get("content", [])
            if content_list and len(content_list) > 0:
                text_content = content_list[0].get("text", "")
            else:
                text_content = ""
            
            self.message = FoundryMessage(text_content)
            self.finish_reason = output.get("status", "completed")
        else:
            self.message = FoundryMessage("")
            self.finish_reason = "error"
        
        self.index = 0


class FoundryMessage:
    """Wrapper for Foundry message to mimic OpenAI message structure."""
    
    def __init__(self, content: str):
        self.content = content
        self.role = "assistant"


def create_foundry_client(endpoint: str, api_key: str, model: str, api_version: str) -> FoundryResponsesClient:
    """
    Factory function to create a Foundry Responses API client.
    
    Args:
        endpoint: Azure endpoint URL
        api_key: API key
        model: Model name
        api_version: API version
    
    Returns:
        FoundryResponsesClient instance
    """
    return FoundryResponsesClient(endpoint, api_key, model, api_version)
