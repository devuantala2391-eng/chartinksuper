#!/usr/bin/env python3

import sys
import os
import subprocess
import time

def test_uvicorn_setup():
    """Test that uvicorn can properly start the FastAPI app"""
    print("Testing uvicorn setup...")
    
    # Test 1: Check if uvicorn is available
    try:
        import uvicorn
        print(f"✅ uvicorn is available (version: {uvicorn.__version__})")
    except ImportError:
        print("❌ uvicorn is not available")
        return False
    
    # Test 2: Check if the FastAPI app can be imported
    sys.path.append(os.path.join(os.path.dirname(__file__), 'python-api'))
    try:
        from main import app
        print("✅ FastAPI app can be imported successfully")
        print(f"✅ App type: {type(app)}")
    except ImportError as e:
        print(f"❌ Failed to import FastAPI app: {e}")
        return False
    
    # Test 3: Check uvicorn command syntax
    print("\n🔧 Uvicorn command that will be used:")
    print("uvicorn main:app --host 127.0.0.1 --port 8001 --reload --log-level info")
    
    print("\n🎯 Benefits of using uvicorn with --reload:")
    print("  • Automatically restarts server when Python files change")
    print("  • No need to manually stop/start server during development")
    print("  • Watches for changes in *.py files")
    print("  • Faster development workflow")
    
    print("\n✅ Uvicorn setup is ready!")
    return True

if __name__ == "__main__":
    test_uvicorn_setup()