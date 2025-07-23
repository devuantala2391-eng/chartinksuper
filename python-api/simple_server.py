#!/usr/bin/env python3
"""
Simple server runner for ChartinkSuper FastAPI
This runs the server with minimal logging overhead
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the app
from main import app

if __name__ == "__main__":
    import uvicorn
    
    print("="*60)
    print("🚀 CHARTINKSUPER SIMPLE SERVER")
    print("="*60)
    print("🌐 Server: http://127.0.0.1:8001")
    print("📚 API Docs: http://127.0.0.1:8001/docs")
    print("🔄 RefreshDB: POST /refreshdb")
    print("📡 SSE Stream: GET /refreshdb-progress-stream")
    print("="*60)
    print("🎯 API Logs will appear below...")
    print("="*60)
    sys.stdout.flush()
    
    # Run with minimal uvicorn configuration
    uvicorn.run(
        app,
        host="127.0.0.1", 
        port=8001,
        log_level="error",      # Only show errors from uvicorn
        access_log=False,       # Disable uvicorn access logs
        reload=False,           # No auto-reload 
        use_colors=False        # No colors to avoid interference
    )