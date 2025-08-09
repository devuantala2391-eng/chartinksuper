#!/usr/bin/env python3
"""Simple test server to verify our optimization works"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'python-api'))

from services.query_service import parse_query, validate_query_fields
from fastapi import FastAPI
import uvicorn
import json

app = FastAPI()

@app.post("/test/query")
async def test_query(request: dict):
    """Test query processing without the heavy stock processing"""
    
    query = request.get("query", "")
    if not query:
        return {"error": "Query is required"}
    
    try:
        # Parse the query
        parsed_query = parse_query(query)
        print(f"Parsed query: {parsed_query}")
        
        # Validate fields
        validation_result = validate_query_fields(parsed_query)
        print(f"Validation result: {validation_result}")
        
        if validation_result["valid"]:
            return {
                "success": True, 
                "message": "Query validation passed",
                "parsed_query": parsed_query,
                "validation": validation_result
            }
        else:
            return {
                "success": False,
                "error": "Validation failed",
                "details": validation_result
            }
            
    except Exception as e:
        return {"success": False, "error": f"Query processing failed: {str(e)}"}

if __name__ == "__main__":
    print("Starting simple test server on port 8002...")
    uvicorn.run(app, host="127.0.0.1", port=8002)