"""
API Health Middleware - Ensures system readiness before processing API requests
"""

import asyncio
import logging
from functools import wraps
from typing import Dict, List, Optional, Callable, Any
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from services.database_health_manager import database_health_manager

logger = logging.getLogger(__name__)

def ensure_system_ready(extract_indicators_func: Optional[Callable] = None):
    """
    Decorator to ensure system is ready before processing API requests.
    
    Args:
        extract_indicators_func: Optional function to extract required indicators from request
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Extract request data to find required indicators
                required_indicators = []
                
                # Try to find request data in args (FastAPI passes request as first argument)
                request_data = None
                for arg in args:
                    if hasattr(arg, 'query'):  # QueryRequest object
                        request_data = {'query': arg.query}
                        if hasattr(arg, 'stocks') and arg.stocks:
                            request_data['stocks'] = arg.stocks
                        break
                    elif isinstance(arg, dict):
                        request_data = arg
                        break
                
                # Also check kwargs for query parameters
                if not request_data and kwargs:
                    request_data = kwargs
                
                # Extract indicators if we have data and extraction function
                if request_data and extract_indicators_func:
                    required_indicators = extract_indicators_func(request_data)
                elif request_data:
                    # Default extraction logic
                    required_indicators = database_health_manager.extract_indicators_from_query(request_data)
                
                logger.info(f"🔍 API Health Check - Required indicators: {required_indicators}")
                
                # Ensure system is ready
                health_status = await database_health_manager.ensure_system_ready(required_indicators)
                
                if not health_status['ready_for_queries']:
                    logger.error(f"System not ready: {health_status}")
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "error": "System not ready",
                            "details": health_status.get('error', 'Database initialization failed'),
                            "actions_taken": health_status.get('actions_taken', []),
                            "retry_advice": "Please try again in a few moments"
                        }
                    )
                
                # Log actions taken if any
                if health_status['actions_taken']:
                    logger.info(f"✅ System auto-fixed - Actions taken: {health_status['actions_taken']}")
                
                # System is ready, proceed with original function
                return await func(*args, **kwargs)
                
            except HTTPException:
                # Re-raise HTTP exceptions as-is
                raise
            except Exception as e:
                logger.error(f"API Health Middleware error: {e}")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "System health check failed",
                        "details": str(e),
                        "retry_advice": "Please contact support if this persists"
                    }
                )
        
        return wrapper
    return decorator

def extract_indicators_from_query_request(query_data: Dict) -> List[str]:
    """
    Extract indicators from a query request.
    
    Args:
        query_data: Query parameters from request
        
    Returns:
        List of indicator names needed for the query
    """
    indicators = []
    
    # Check if there's a raw query string
    query_string = query_data.get('query', '')
    if query_string:
        # Parse the query string to find indicator references
        # Look for patterns like "daily supertrend (30,5)" or "supertrend_30_5"
        import re
        
        # Pattern for indicators with parameters
        patterns = [
            r'daily\s+supertrend\s*\(\s*(\d+)\s*,\s*(\d+(?:\.\d+)?)\s*\)',  # daily supertrend (30,5)
            r'supertrend_(\d+)_(\d+(?:_\d+)?)',  # supertrend_30_5
            r'daily_supertrend_(\d+)_(\d+(?:_\d+)?)',  # daily_supertrend_30_5
            r'rsi\s*\(\s*(\d+)\s*\)',  # rsi(14)
            r'sma\s*\(\s*(\d+)\s*\)',  # sma(20)
            r'ema\s*\(\s*(\d+)\s*\)',  # ema(12)
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, query_string, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                if 'supertrend' in pattern:
                    if len(groups) >= 2:
                        period = groups[0]
                        # Convert decimal dots to "dot" for unambiguous naming, remove redundant "daily"
                        multiplier = groups[1].replace('.', 'dot') if '.' in groups[1] else groups[1]
                        indicators.append(f'supertrend_{period}_{multiplier}')
                elif 'rsi' in pattern and len(groups) >= 1:
                    indicators.append(f'daily_rsi_{groups[0]}')
                elif 'sma' in pattern and len(groups) >= 1:
                    indicators.append(f'daily_sma_{groups[0]}')
                elif 'ema' in pattern and len(groups) >= 1:
                    indicators.append(f'daily_ema_{groups[0]}')
    
    # Also check for structured query data
    conditions = query_data.get('conditions', [])
    if isinstance(conditions, list):
        for condition in conditions:
            if isinstance(condition, dict):
                field = condition.get('field', '').lower()
                if any(ind in field for ind in ['supertrend', 'rsi', 'sma', 'ema', 'bollinger']):
                    indicators.append(field)
    
    # Check sort fields
    sort_field = query_data.get('sort', {}).get('field', '').lower()
    if sort_field and any(ind in sort_field for ind in ['supertrend', 'rsi', 'sma', 'ema', 'bollinger']):
        indicators.append(sort_field)
    
    # Check select fields
    select_fields = query_data.get('select', [])
    if isinstance(select_fields, list):
        for field in select_fields:
            if isinstance(field, str) and any(ind in field.lower() for ind in ['supertrend', 'rsi', 'sma', 'ema', 'bollinger']):
                indicators.append(field.lower())
    
    return list(set(indicators))  # Remove duplicates

def extract_indicators_from_latest_request(request_data: Dict) -> List[str]:
    """
    Extract indicators from a latest data request.
    
    Args:
        request_data: Request parameters
        
    Returns:
        List of indicator names needed for the request
    """
    indicators = []
    
    # Check if specific indicators are requested
    fields = request_data.get('fields', [])
    if isinstance(fields, list):
        for field in fields:
            if isinstance(field, str) and any(ind in field.lower() for ind in ['supertrend', 'rsi', 'sma', 'ema', 'bollinger']):
                indicators.append(field.lower())
    
    # If no specific fields, assume common indicators might be needed
    if not indicators:
        # We could add default indicators here, or leave empty to skip indicator check
        pass
    
    return indicators

class HealthStatusResponse:
    """Helper class for health status responses."""
    
    @staticmethod
    def success_response(actions_taken: List[str] = None) -> JSONResponse:
        """Return a success response with optional actions taken."""
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "ready": True,
                "actions_taken": actions_taken or [],
                "timestamp": str(asyncio.get_event_loop().time())
            }
        )
    
    @staticmethod
    def error_response(error: str, actions_taken: List[str] = None) -> JSONResponse:
        """Return an error response with actions attempted."""
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "ready": False,
                "error": error,
                "actions_taken": actions_taken or [],
                "retry_advice": "Please try again in a few moments",
                "timestamp": str(asyncio.get_event_loop().time())
            }
        )

# Pre-configured decorators for common endpoints
ensure_query_ready = ensure_system_ready(extract_indicators_from_query_request)
ensure_latest_ready = ensure_system_ready(extract_indicators_from_latest_request)
ensure_basic_ready = ensure_system_ready()  # No specific indicator extraction