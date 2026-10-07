#!/usr/bin/env python3
"""Verify that all pricing service dependencies and configurations are set up correctly."""

import sys
import os

def check_imports():
    """Check if all required imports are available."""
    print("Checking imports...")
    try:
        import boto3
        print("✓ boto3 available")
    except ImportError as e:
        print("✗ boto3 not available:", e)
        return False
    
    try:
        import httpx
        print("✓ httpx available")
    except ImportError as e:
        print("✗ httpx not available:", e)
        return False
    
    try:
        from app.services.aws_pricing import fetch_aws_prices
        print("✓ aws_pricing module imports successfully")
    except ImportError as e:
        print("✗ aws_pricing module import failed:", e)
        return False
    
    try:
        from app.services.gcp_pricing import fetch_gcp_prices
        print("✓ gcp_pricing module imports successfully")
    except ImportError as e:
        print("✗ gcp_pricing module import failed:", e)
        return False

    try:
        from app.services.azure_pricing import fetch_azure_prices
        print("✓ azure_pricing module imports successfully")
    except ImportError as e:
        print("✗ azure_pricing module import failed:", e)
        return False
    
    try:
        from app.services.pricing_service import estimate_pricing
        print("✓ pricing_service module imports successfully")
    except ImportError as e:
        print("✗ pricing_service module import failed:", e)
        return False
    
    return True

def check_config():
    """Check if configuration is set up correctly."""
    print("\nChecking configuration...")
    try:
        from app.config import settings
        
        if settings.aws_access_key_id:
            print("✓ AWS_ACCESS_KEY_ID configured")
        else:
            print("⚠ AWS_ACCESS_KEY_ID not configured")
        
        if settings.aws_secret_access_key:
            print("✓ AWS_SECRET_ACCESS_KEY configured")
        else:
            print("⚠ AWS_SECRET_ACCESS_KEY not configured")
        
        ok = True

        if settings.gcp_project_id:
            print("✓ GCP_PROJECT_ID configured")
        else:
            print("✗ GCP_PROJECT_ID not configured")
            ok = False
        
        if settings.gcp_api_key:
            print("✓ GCP_API_KEY configured")
        else:
            print("✗ GCP_API_KEY not configured")
            ok = False

        if settings.gcp_service_account_key:
            print("ℹ GCP_SERVICE_ACCOUNT_KEY configured (not required for public catalog pricing)")
        
        return ok
    except Exception as e:
        print("✗ Configuration check failed:", e)
        return False

def main():
    """Run all verification checks."""
    print("=" * 50)
    print("Pricing Service Setup Verification")
    print("=" * 50 + "\n")
    
    imports_ok = check_imports()
    config_ok = check_config()
    
    print("\n" + "=" * 50)
    if imports_ok and config_ok:
        print("✓ All checks passed! Pricing service is ready.")
        print("=" * 50)
        return 0
    else:
        print("✗ Some checks failed. See above for details.")
        print("=" * 50)
        return 1

if __name__ == "__main__":
    sys.exit(main())
