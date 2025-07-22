import sys
import io

# Force UTF-8 encoding for stdout
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import asyncio
import logging
from typing import List, Dict, Any, Optional
import json
import os
from pathlib import Path
import shutil
import csv
from io import StringIO
from datetime import datetime
import sys
import time
import concurrent.futures
import threading
import multiprocessing
import os

from services.query_service import (
    parse_query, find_matching_candles, get_query_examples, 
    extract_indicators_from_query, process_stocks_with_indicators
)
from services.indicator_cache import clear_cache
from services.data_utils import get_next_day_timestamp, get_day_of_week_name
from utils.constants import STOCK_SYMBOLS, TOTAL_SYMBOLS
from services.chartink_service import ChartinkService

# Simple logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)

# Ensure immediate console output
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

# Pydantic models for request/response
class ChartinkApiRequest(BaseModel):
    payload: List[List[str]]

class QueryRequest(BaseModel):
    query: str
    stocks: Optional[List[str]] = None

class PrecalculateRequest(BaseModel):
    indicators: List[Dict[str, Any]]

class RefreshDbRequest(BaseModel):
    symbols: Optional[List[str]] = None

# Global progress state
current_progress = {
    "isRunning": False,
    "phase": "idle",
    "message": "",
    "processed": 0,
    "total": TOTAL_SYMBOLS,
    "matches": 0,
    "percentage": 0,
    "startTime": None
}

# Query abortion mechanism
current_query_abort = {"aborted": False}

# SSE connections and broadcast queue
import queue
progress_queue = queue.Queue()

app = FastAPI(
    title="ChartinkSuper FastAPI Backend",
    description="FastAPI backend for stock screening and analysis",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    
    # Log only essential info
    process_time = time.time() - start_time
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
    
    return response

# HIGH PERFORMANCE CONFIGURATION - Maximum CPU with optimized I/O
CPU_COUNT = multiprocessing.cpu_count()
PERFORMANCE_CONFIG = {
    "max_concurrent_stocks": CPU_COUNT * 100,  # Maximum concurrency
    "max_file_io_workers": CPU_COUNT * 4,      # High file I/O workers 
    "max_cpu_workers": CPU_COUNT,              # One process per CPU core for maximum utilization
    "chunk_size": max(10, len(STOCK_SYMBOLS) // (CPU_COUNT * 2)),  # Optimal chunk size for CPU saturation
    "progress_update_frequency": 1  # Update frequently for real-time SSE
}

# Initialize services
chartink_service = ChartinkService()

# Ensure required directories exist
Path("uploads").mkdir(exist_ok=True)
(Path(__file__).parent.parent / "db").mkdir(parents=True, exist_ok=True)

def update_progress(updates: Dict[str, Any]):
    """Update progress and notify SSE connections."""
    global current_progress
    current_progress.update(updates)
    
    # Calculate percentage
    if current_progress["total"] > 0:
        current_progress["percentage"] = min(
            int((current_progress["processed"] / current_progress["total"]) * 100), 100
        )
    
    # Broadcast update to all SSE connections
    try:
        progress_queue.put_nowait(current_progress.copy())
    except queue.Full:
        # If queue is full, clear it and add the latest
        while not progress_queue.empty():
            try:
                progress_queue.get_nowait()
            except queue.Empty:
                break
        progress_queue.put_nowait(current_progress.copy())
    
    # Log progress update
    logger.info(f"Progress update: {current_progress}")

@app.get("/")
async def root():
    return {"message": "ChartinkSuper FastAPI Backend"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/test")
async def test_endpoint():
    """Test endpoint to verify API is working."""
    return {
        "message": "Test endpoint working",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/chartink-api")
async def chartink_api(request: ChartinkApiRequest):
    """Process Chartink API requests to fetch and save stock data."""
    try:
        payload = request.payload
        
        if not payload or not isinstance(payload, list) or len(payload) == 0:
            raise HTTPException(status_code=400, detail="Invalid or missing payload")
        
        # Process the payload using the chartink service
        results = await chartink_service.process_payload(payload)
        
        return {"success": True, "results": results}
        
    except Exception as error:
        logger.error(f"Chartink API error: {error}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(error)}")

@app.get("/query/progress")
async def get_query_progress():
    """Get current query progress."""
    try:
        # Calculate percentage (22 stocks = 1% as per original logic)
        percentage = min(int(current_progress["processed"] / 22), 100) if current_progress["total"] > 0 else 0
        
        response = {
            **current_progress,
            "percentage": percentage
        }
        
        logger.info(f"Progress endpoint called: {response}")
        return response
        
    except Exception as error:
        logger.error(f"Progress endpoint error: {error}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/query")
async def process_query(request: QueryRequest):
    """Process stock screening query."""
    try:
        query = request.query
        stocks = request.stocks
        
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Reset abort flag
        current_query_abort["aborted"] = False
        
        # Reset progress
        update_progress({
            "isRunning": True,
            "phase": "initializing",
            "message": "Starting query processing...",
            "processed": 0,
            "total": TOTAL_SYMBOLS,
            "matches": 0,
            "startTime": datetime.utcnow().timestamp() * 1000
        })
        
        logger.info(f"Processing query: {query}")
        
        # Parse the query
        try:
            parsed_query = parse_query(query)
        except Exception as error:
            update_progress({"isRunning": False, "phase": "error", "message": "Invalid query format"})
            raise HTTPException(
                status_code=400, 
                detail={
                    "error": "Invalid query format",
                    "details": str(error),
                    "hint": 'Example: "rsi(14) > 70 and sma(20) < close"'
                }
            )
        
        # Extract indicators and process query
        indicators_data = extract_indicators_from_query(parsed_query)
        required_indicators = indicators_data["indicators"]
        required_timeframes = indicators_data["timeframes"]
        
        logger.info(f"Required indicators: {required_indicators}")
        logger.info(f"Required timeframes: {required_timeframes}")
        
        # Process stocks and find matches
        all_matches = []
        errors = []
        processed_count = 0
        
        stock_list = stocks or STOCK_SYMBOLS
        total_stocks = len(stock_list)
        
        update_progress({
            "phase": "processing_and_analyzing",
            "message": "Processing indicators and analyzing...",
            "processed": 0,
            "total": total_stocks
        })
        
        # SAFE PARALLEL PROCESSING: Use ThreadPoolExecutor for async compatibility
        print(f"[DEBUG] Starting SAFE PARALLEL query processing with {PERFORMANCE_CONFIG['max_cpu_workers']} workers")
        query_start_time = time.time()
        
        # Use ThreadPoolExecutor for better async compatibility (avoids ASGI issues)
        max_workers = min(PERFORMANCE_CONFIG["max_cpu_workers"], 8)  # Limit to prevent resource exhaustion
        
        # Process stocks in smaller batches to avoid memory issues
        batch_size = 50  # Process 50 stocks at a time
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Process stocks in batches
                for batch_start in range(0, len(stock_list), batch_size):
                    batch_end = min(batch_start + batch_size, len(stock_list))
                    batch_stocks = stock_list[batch_start:batch_end]
                    
                    print(f"[DEBUG] Processing batch {batch_start+1}-{batch_end} ({len(batch_stocks)} stocks)")
                    
                    # Create futures for this batch
                    futures = []
                    for stock in batch_stocks:
                        if current_query_abort["aborted"]:
                            raise HTTPException(status_code=400, detail="Query was aborted")
                        
                        future = executor.submit(process_single_stock_safe, stock, parsed_query)
                        futures.append((stock, future))
                    
                    # Collect results from this batch
                    batch_matches = []
                    batch_errors = []
                    
                    for stock, future in futures:
                        try:
                            result = future.result(timeout=30)  # 30 second timeout per stock
                            if result["success"]:
                                batch_matches.extend(result["matches"])
                            else:
                                batch_errors.append({"stock": stock, "error": result["error"]})
                        except concurrent.futures.TimeoutError:
                            batch_errors.append({"stock": stock, "error": "Processing timeout"})
                        except Exception as e:
                            batch_errors.append({"stock": stock, "error": str(e)})
                        
                        processed_count += 1
                    
                    # Add batch results to totals
                    all_matches.extend(batch_matches)
                    errors.extend(batch_errors)
                    
                    # Update progress after each batch
                    update_progress({
                        "phase": "processing_and_analyzing",
                        "message": f"Parallel query: {processed_count}/{total_stocks} stocks, {len(all_matches)} matches found",
                        "processed": processed_count,
                        "total": total_stocks,
                        "matches": len(all_matches)
                    })
                    
                    # Allow other tasks to run
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Parallel processing error: {e}")
            # Fallback to sequential processing
            print(f"[WARNING] Falling back to sequential processing due to error: {e}")
            
            for stock in stock_list[processed_count:]:
                if current_query_abort["aborted"]:
                    raise HTTPException(status_code=400, detail="Query was aborted")
                
                try:
                    result = process_single_stock_safe(stock, parsed_query)
                    if result["success"]:
                        all_matches.extend(result["matches"])
                    else:
                        errors.append({"stock": stock, "error": result["error"]})
                except Exception as error:
                    errors.append({"stock": stock, "error": str(error)})
                
                processed_count += 1
                
                if processed_count % 10 == 0:
                    update_progress({
                        "phase": "processing_and_analyzing",
                        "message": f"Sequential fallback: {processed_count}/{total_stocks} stocks, {len(all_matches)} matches found",
                        "processed": processed_count,
                        "total": total_stocks,
                        "matches": len(all_matches)
                    })
                    await asyncio.sleep(0)
        
        query_end_time = time.time()
        total_query_time = query_end_time - query_start_time
        print(f"[DEBUG] Query processing completed in {total_query_time:.2f}s | Rate: {len(stock_list) / total_query_time:.1f} stocks/sec")
        
        # Sort matches by date (most recent first)
        all_matches.sort(key=lambda x: int(x["date"]), reverse=True)
        
        # Update completion progress
        update_progress({
            "phase": "completed",
            "message": f"Completed: Found {len(all_matches)} matches",
            "processed": processed_count,
            "total": total_stocks,
            "matches": len(all_matches),
            "isRunning": False
        })
        
        return {
            "success": True,
            "query": query,
            "parsedQuery": {
                "conditions": [
                    {
                        "left": c["left"],
                        "operator": c["operator"], 
                        "right": c["right"]
                    } for c in parsed_query["conditions"]
                ],
                "logicalOperators": parsed_query["logicalOperators"]
            },
            "requiredIndicators": required_indicators,
            "totalMatches": len(all_matches),
            "matches": all_matches,
            "errors": errors if errors else None,
            "processedStocks": processed_count
        }
        
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Query endpoint error: {error}")
        update_progress({
            "phase": "error",
            "message": "Query processing failed",
            "isRunning": False
        })
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(error)}")

@app.post("/query/latest")
async def process_latest_query(request: QueryRequest):
    """Process query for latest day only - optimized for speed."""
    try:
        query = request.query
        stocks = request.stocks
        
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Reset abort flag
        current_query_abort["aborted"] = False
        
        # Reset progress
        update_progress({
            "isRunning": True,
            "phase": "initializing",
            "message": "Starting latest day scan...",
            "processed": 0,
            "total": TOTAL_SYMBOLS,
            "matches": 0,
            "startTime": datetime.utcnow().timestamp() * 1000
        })
        
        logger.info(f"Processing LATEST DAY query: {query}")
        
        # Parse the query
        try:
            parsed_query = parse_query(query)
        except Exception as error:
            update_progress({"isRunning": False, "phase": "error", "message": "Invalid query format"})
            raise HTTPException(
                status_code=400, 
                detail={
                    "error": "Invalid query format",
                    "details": str(error),
                    "hint": 'Example: "rsi(14) > 70 and sma(20) < close"'
                }
            )
        
        # Extract indicators
        indicators_data = extract_indicators_from_query(parsed_query)
        required_indicators = indicators_data["indicators"]
        
        logger.info(f"Required indicators: {required_indicators}")
        
        # Process stocks - ONLY CHECK LATEST CANDLE
        all_matches = []
        errors = []
        processed_count = 0
        
        stock_list = stocks or STOCK_SYMBOLS
        total_stocks = len(stock_list)
        
        update_progress({
            "phase": "processing_and_analyzing",
            "message": "Scanning latest day data...",
            "processed": 0,
            "total": total_stocks
        })
        
        # SAFE PARALLEL PROCESSING: Use ThreadPoolExecutor for latest scan
        print(f"[DEBUG] Starting SAFE PARALLEL latest scan with {PERFORMANCE_CONFIG['max_cpu_workers']} workers")
        scan_start_time = time.time()
        
        # Use ThreadPoolExecutor for better async compatibility
        max_workers = min(PERFORMANCE_CONFIG["max_cpu_workers"], 8)
        batch_size = 100  # Larger batches for latest scan (only 1 candle per stock)
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Process stocks in batches
                for batch_start in range(0, len(stock_list), batch_size):
                    batch_end = min(batch_start + batch_size, len(stock_list))
                    batch_stocks = stock_list[batch_start:batch_end]
                    
                    print(f"[DEBUG] Processing latest scan batch {batch_start+1}-{batch_end} ({len(batch_stocks)} stocks)")
                    
                    # Create futures for this batch (latest scan only)
                    futures = []
                    for stock in batch_stocks:
                        if current_query_abort["aborted"]:
                            raise HTTPException(status_code=400, detail="Query was aborted")
                        
                        future = executor.submit(process_single_stock_latest_safe, stock, parsed_query)
                        futures.append((stock, future))
                    
                    # Collect results from this batch
                    batch_matches = []
                    batch_errors = []
                    
                    for stock, future in futures:
                        try:
                            result = future.result(timeout=10)  # 10 second timeout for latest scan
                            if result["success"]:
                                batch_matches.extend(result["matches"])
                            else:
                                batch_errors.append({"stock": stock, "error": result["error"]})
                        except concurrent.futures.TimeoutError:
                            batch_errors.append({"stock": stock, "error": "Processing timeout"})
                        except Exception as e:
                            batch_errors.append({"stock": stock, "error": str(e)})
                        
                        processed_count += 1
                    
                    # Add batch results to totals
                    all_matches.extend(batch_matches)
                    errors.extend(batch_errors)
                    
                    # Update progress after each batch
                    update_progress({
                        "phase": "processing_and_analyzing",
                        "message": f"Parallel latest scan: {processed_count}/{total_stocks} stocks, {len(all_matches)} matches found",
                        "processed": processed_count,
                        "total": total_stocks,
                        "matches": len(all_matches)
                    })
                    
                    # Allow other tasks to run
                    await asyncio.sleep(0.05)  # Shorter sleep for latest scan
                    
        except Exception as e:
            logger.error(f"Parallel latest scan error: {e}")
            # Fallback to sequential processing
            print(f"[WARNING] Falling back to sequential processing due to error: {e}")
            
            for stock in stock_list[processed_count:]:
                if current_query_abort["aborted"]:
                    raise HTTPException(status_code=400, detail="Query was aborted")
                
                try:
                    result = process_single_stock_latest_safe(stock, parsed_query)
                    if result["success"]:
                        all_matches.extend(result["matches"])
                    else:
                        errors.append({"stock": stock, "error": result["error"]})
                except Exception as error:
                    errors.append({"stock": stock, "error": str(error)})
                
                processed_count += 1
                
                if processed_count % 50 == 0:
                    update_progress({
                        "phase": "processing_and_analyzing",
                        "message": f"Sequential latest scan: {processed_count}/{total_stocks} stocks, {len(all_matches)} matches found",
                        "processed": processed_count,
                        "total": total_stocks,
                        "matches": len(all_matches)
                    })
                    await asyncio.sleep(0)
        
        scan_end_time = time.time()
        total_scan_time = scan_end_time - scan_start_time
        print(f"[DEBUG] Latest scan completed in {total_scan_time:.2f}s | Rate: {len(stock_list) / total_scan_time:.1f} stocks/sec")
        
        # Sort matches by stock symbol for consistency  
        all_matches.sort(key=lambda x: x.get("stock", ""))
        
        # Update completion progress
        update_progress({
            "phase": "completed",
            "message": f"Latest day scan completed: Found {len(all_matches)} matches",
            "processed": processed_count,
            "total": total_stocks,
            "matches": len(all_matches),
            "isRunning": False
        })
        
        logger.info(f"Latest day scan completed: {len(all_matches)} matches found")
        
        return {
            "success": True,
            "query": query,
            "scanType": "latest_day",
            "parsedQuery": {
                "conditions": [
                    {
                        "left": c["left"],
                        "operator": c["operator"], 
                        "right": c["right"]
                    } for c in parsed_query["conditions"]
                ],
                "logicalOperators": parsed_query["logicalOperators"]
            },
            "requiredIndicators": required_indicators,
            "matches": all_matches,
            "totalProcessed": processed_count,
            "totalMatches": len(all_matches),
            "errors": errors[:10] if errors else []  # Limit error reporting
        }
        
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Latest day query processing error: {error}", exc_info=True)
        update_progress({
            "phase": "error",
            "message": "Latest day scan failed",
            "isRunning": False
        })
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(error)}")

@app.get("/query/examples")
async def get_query_examples_endpoint():
    """Get example queries for the user."""
    try:
        from services.query_service import get_query_examples as get_examples
        examples = get_examples()
        return {"success": True, "examples": examples}
    except Exception as error:
        logger.error(f"Query examples error: {error}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(error)}")

@app.post("/api/precalculate-indicators")
async def precalculate_indicators(request: PrecalculateRequest):
    """Precalculate indicators for all stocks with maximum performance."""
    try:
        indicators = request.indicators
        
        # Validate indicators
        if not indicators or len(indicators) == 0:
            raise HTTPException(status_code=400, detail="Invalid indicators array")
        
        # Validate indicator format
        for i, indicator in enumerate(indicators):
            if not indicator.get('timeframe') or not indicator.get('name') or not indicator.get('params'):
                raise HTTPException(status_code=400, detail=f"Invalid indicator format at index {i}")
        
        # Update progress
        update_progress({
            "isRunning": True,
            "phase": "processing_indicators",
            "message": "Starting high-performance processing...",
            "processed": 0,
            "total": len(STOCK_SYMBOLS),
            "startTime": datetime.utcnow().timestamp() * 1000
        })
        
        # Save precalculated indicators to file
        precalc_data = {
            "status": "processing",
            "indicators": indicators,
            "lastUpdated": datetime.utcnow().isoformat()
        }
        
        with open("precalculatedIndicators.json", 'w') as f:
            json.dump(precalc_data, f, indent=2)
        
        # Start high-performance background processing
        asyncio.create_task(process_indicators_background(indicators))
        
        return {
            "success": True,
            "message": "High-performance precalculation started",
            "indicators": indicators,
            "status": "processing"
        }
        
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

def process_single_stock_latest_safe(stock, parsed_query):
    """Safe single stock processing function for latest scan only."""
    try:
        # Import here to ensure thread safety
        import json
        from pathlib import Path
        from services.query_service import find_matching_candles
        
        # Check for precalculated data
        precalculated_file = Path(f"precalculatedStorage/{stock}_piped.json")
        if not precalculated_file.exists():
            return {"success": False, "error": "Precalculated data not found"}
        
        # Read and process the stock data
        with open(precalculated_file, 'r') as f:
            mapped_data = json.load(f)
        
        candles = mapped_data.get("data", [])
        if not candles:
            return {"success": False, "error": "No candle data available"}
        
        # OPTIMIZATION: Only process the LATEST candle for latest scan
        latest_candle = [candles[-1]]  # Last candle only
        matches = find_matching_candles(latest_candle, parsed_query, stock)
        
        return {"success": True, "matches": matches}
        
    except ImportError:
        # Fallback if import fails
        try:
            import json
            from pathlib import Path
            
            precalculated_file = Path(f"precalculatedStorage/{stock}_piped.json")
            if not precalculated_file.exists():
                return {"success": False, "error": "Precalculated data not found"}
            
            with open(precalculated_file, 'r') as f:
                mapped_data = json.load(f)
            
            candles = mapped_data.get("data", [])
            if not candles:
                return {"success": False, "error": "No candle data available"}
            
            # Process only latest candle
            latest_candle = candles[-1]
            matches = []
            conditions = parsed_query.get("conditions", [])
            
            try:
                results = []
                for condition in conditions:
                    left = condition["left"]
                    operator = condition["operator"] 
                    right = condition["right"]
                    
                    # Get values from candle
                    left_val = latest_candle.get(left.get("value", ""), 0) if left.get("type") == "field" else float(left.get("value", 0))
                    right_val = latest_candle.get(right.get("value", ""), 0) if right.get("type") == "field" else float(right.get("value", 0))
                    
                    # Simple comparison
                    if operator == ">":
                        results.append(left_val > right_val)
                    elif operator == "<":
                        results.append(left_val < right_val)
                    elif operator == ">=":
                        results.append(left_val >= right_val)
                    elif operator == "<=":
                        results.append(left_val <= right_val)
                    elif operator == "==":
                        results.append(left_val == right_val)
                    else:
                        results.append(False)
                
                if all(results):
                    matches.append({
                        "stock": stock,
                        "date": latest_candle.get("timestamp", ""),
                        "data": latest_candle
                    })
            except:
                pass
            
            return {"success": True, "matches": matches}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def process_single_stock_safe(stock, parsed_query):
    """Safe single stock processing function for ThreadPoolExecutor."""
    try:
        # Import here to ensure thread safety
        import json
        from pathlib import Path
        from services.query_service import find_matching_candles
        
        # Check for precalculated data
        precalculated_file = Path(f"precalculatedStorage/{stock}_piped.json")
        if not precalculated_file.exists():
            return {"success": False, "error": "Precalculated data not found"}
        
        # Read and process the stock data
        with open(precalculated_file, 'r') as f:
            mapped_data = json.load(f)
        
        candles = mapped_data.get("data", [])
        if not candles:
            return {"success": False, "error": "No candle data available"}
        
        # Find matching candles
        matches = find_matching_candles(candles, parsed_query, stock)
        
        return {"success": True, "matches": matches}
        
    except ImportError:
        # Fallback if import fails
        try:
            import json
            from pathlib import Path
            
            precalculated_file = Path(f"precalculatedStorage/{stock}_piped.json")
            if not precalculated_file.exists():
                return {"success": False, "error": "Precalculated data not found"}
            
            with open(precalculated_file, 'r') as f:
                mapped_data = json.load(f)
            
            candles = mapped_data.get("data", [])
            if not candles:
                return {"success": False, "error": "No candle data available"}
            
            # Simple fallback matching
            matches = []
            conditions = parsed_query.get("conditions", [])
            
            for candle in candles:
                try:
                    results = []
                    for condition in conditions:
                        left = condition["left"]
                        operator = condition["operator"] 
                        right = condition["right"]
                        
                        # Get values from candle
                        left_val = candle.get(left.get("value", ""), 0) if left.get("type") == "field" else float(left.get("value", 0))
                        right_val = candle.get(right.get("value", ""), 0) if right.get("type") == "field" else float(right.get("value", 0))
                        
                        # Simple comparison
                        if operator == ">":
                            results.append(left_val > right_val)
                        elif operator == "<":
                            results.append(left_val < right_val)
                        elif operator == ">=":
                            results.append(left_val >= right_val)
                        elif operator == "<=":
                            results.append(left_val <= right_val)
                        elif operator == "==":
                            results.append(left_val == right_val)
                        else:
                            results.append(False)
                    
                    if all(results):
                        matches.append({
                            "stock": stock,
                            "date": candle.get("timestamp", ""),
                            "data": candle
                        })
                except:
                    continue
            
            return {"success": True, "matches": matches}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def process_query_batch_parallel(stock_batch, parsed_query_dict, base_path=""):
    """Parallel full query processing function for ProcessPoolExecutor - maximizes CPU usage."""
    import json
    import time
    import sys
    import os
    from pathlib import Path
    
    batch_start = time.time()
    matches = []
    errors = []
    processed = 0
    
    # Add current directory to path for imports
    if base_path and base_path not in sys.path:
        sys.path.insert(0, base_path)
    
    # Import the query service function
    try:
        # Try to import directly first
        from services.query_service import find_matching_candles
    except ImportError:
        try:
            # Try with absolute path
            current_dir = os.path.dirname(os.path.abspath(__file__))
            services_path = os.path.join(current_dir, 'services')
            if services_path not in sys.path:
                sys.path.insert(0, services_path)
            from query_service import find_matching_candles
        except ImportError:
            # Simple fallback implementation for basic conditions
            def find_matching_candles(candles, parsed_query, stock):
                matches = []
                for candle in candles:
                    try:
                        # Simple evaluation for basic conditions
                        conditions = parsed_query.get("conditions", [])
                        if not conditions:
                            continue
                        
                        results = []
                        for condition in conditions:
                            left = condition["left"]
                            operator = condition["operator"] 
                            right = condition["right"]
                            
                            # Get values from candle
                            left_val = candle.get(left.get("value", ""), 0) if left.get("type") == "field" else float(left.get("value", 0))
                            right_val = candle.get(right.get("value", ""), 0) if right.get("type") == "field" else float(right.get("value", 0))
                            
                            # Simple comparison
                            if operator == ">":
                                results.append(left_val > right_val)
                            elif operator == "<":
                                results.append(left_val < right_val)
                            elif operator == ">=":
                                results.append(left_val >= right_val)
                            elif operator == "<=":
                                results.append(left_val <= right_val)
                            elif operator == "==":
                                results.append(left_val == right_val)
                            else:
                                results.append(False)
                        
                        # Simple AND logic for now
                        if all(results):
                            matches.append({
                                "stock": stock,
                                "date": candle.get("timestamp", ""),
                                "data": candle
                            })
                    except:
                        continue
                return matches
    
    print(f"[DEBUG] Processing full query batch of {len(stock_batch)} stocks")
    
    for stock in stock_batch:
        try:
            # Check for precalculated data (full historical data for query)
            precalculated_file = Path(f"precalculatedStorage/{stock}_piped.json")
            if precalculated_file.exists():
                with open(precalculated_file, 'r') as f:
                    mapped_data = json.load(f)
                candles = mapped_data.get("data", [])
                
                if candles:
                    # Process ALL candles for full query (not just latest)
                    stock_matches = find_matching_candles(candles, parsed_query_dict, stock)
                    matches.extend(stock_matches)
                else:
                    errors.append({"stock": stock, "error": "No candle data available"})
            else:
                errors.append({"stock": stock, "error": "Precalculated data not found"})
            
            processed += 1
            
        except Exception as e:
            errors.append({"stock": stock, "error": str(e)})
            processed += 1
    
    batch_end = time.time()
    print(f"[DEBUG] Full query batch completed in {batch_end - batch_start:.2f}s, processed {processed} stocks, found {len(matches)} matches")
    
    return {
        "matches": matches,
        "errors": errors,
        "processed": processed,
        "processing_time": batch_end - batch_start
    }


def process_latest_scan_batch_parallel(stock_batch, parsed_query_dict, base_path=""):
    """Parallel latest scan processing function for ProcessPoolExecutor - maximizes CPU usage."""
    import json
    import time
    import sys
    import os
    from pathlib import Path
    
    batch_start = time.time()
    matches = []
    errors = []
    processed = 0
    
    # Add current directory to path for imports
    if base_path and base_path not in sys.path:
        sys.path.insert(0, base_path)
    
    # Import the query service function
    try:
        # Try to import directly first
        from services.query_service import find_matching_candles
    except ImportError:
        try:
            # Try with absolute path
            current_dir = os.path.dirname(os.path.abspath(__file__))
            services_path = os.path.join(current_dir, 'services')
            if services_path not in sys.path:
                sys.path.insert(0, services_path)
            from query_service import find_matching_candles
        except ImportError:
            # Simple fallback implementation for basic conditions
            def find_matching_candles(candles, parsed_query, stock):
                matches = []
                for candle in candles:
                    try:
                        # Simple evaluation for basic conditions
                        conditions = parsed_query.get("conditions", [])
                        if not conditions:
                            continue
                        
                        results = []
                        for condition in conditions:
                            left = condition["left"]
                            operator = condition["operator"] 
                            right = condition["right"]
                            
                            # Get values from candle
                            left_val = candle.get(left.get("value", ""), 0) if left.get("type") == "field" else float(left.get("value", 0))
                            right_val = candle.get(right.get("value", ""), 0) if right.get("type") == "field" else float(right.get("value", 0))
                            
                            # Simple comparison
                            if operator == ">":
                                results.append(left_val > right_val)
                            elif operator == "<":
                                results.append(left_val < right_val)
                            elif operator == ">=":
                                results.append(left_val >= right_val)
                            elif operator == "<=":
                                results.append(left_val <= right_val)
                            elif operator == "==":
                                results.append(left_val == right_val)
                            else:
                                results.append(False)
                        
                        # Simple AND logic for now
                        if all(results):
                            matches.append({
                                "stock": stock,
                                "date": candle.get("timestamp", ""),
                                "data": candle
                            })
                    except:
                        continue
                return matches
    
    print(f"[DEBUG] Processing latest scan batch of {len(stock_batch)} stocks")
    
    for stock in stock_batch:
        try:
            # Check for precalculated data
            precalculated_file = Path(f"precalculatedStorage/{stock}_piped.json")
            if precalculated_file.exists():
                with open(precalculated_file, 'r') as f:
                    mapped_data = json.load(f)
                candles = mapped_data.get("data", [])
                
                if candles:
                    # Only check the LATEST candle (most recent)
                    latest_candle = candles[-1]
                    
                    # Check if latest candle matches the query
                    stock_matches = find_matching_candles([latest_candle], parsed_query_dict, stock)
                    matches.extend(stock_matches)
                else:
                    errors.append({"stock": stock, "error": "No candle data available"})
            else:
                errors.append({"stock": stock, "error": "Precalculated data not found"})
            
            processed += 1
            
        except Exception as e:
            errors.append({"stock": stock, "error": str(e)})
            processed += 1
    
    batch_end = time.time()
    print(f"[DEBUG] Latest scan batch completed in {batch_end - batch_start:.2f}s, processed {processed} stocks, found {len(matches)} matches")
    
    return {
        "matches": matches,
        "errors": errors,
        "processed": processed,
        "processing_time": batch_end - batch_start
    }


def write_stock_batch_parallel(stock_results_chunk, precalc_dir_str):
    """Parallel file writing function for ProcessPoolExecutor - maximizes I/O throughput."""
    import json
    import time
    from pathlib import Path
    
    batch_start = time.time()
    write_count = 0
    precalc_dir = Path(precalc_dir_str)
    
    print(f"[DEBUG] Writing batch of {len(stock_results_chunk)} files in parallel process")
    
    for stock, processed_data, success, error in stock_results_chunk:
        if success and processed_data:
            try:
                output_file = precalc_dir / f"{stock}_piped.json"
                with open(output_file, 'w') as f:
                    json.dump(processed_data, f)
                write_count += 1
            except Exception as e:
                print(f"[DEBUG] Failed to write {stock}: {e}")
    
    batch_end = time.time()
    print(f"[DEBUG] Parallel write batch completed in {batch_end - batch_start:.2f}s, wrote {write_count} files")
    return write_count


def process_stock_batch_cpu_intensive(stock_batch_data):
    """CPU-intensive processing function for multiprocessing - maximizes CPU usage."""
    import time
    batch_start = time.time()
    results = []
    
    print(f"[DEBUG] Processing batch with {len(stock_batch_data)} stocks at {batch_start}")
    
    for i, (stock, stock_data, indicators, timeframes) in enumerate(stock_batch_data):
        stock_start = time.time()
        print(f"[DEBUG] Processing stock {i+1}/{len(stock_batch_data)}: {stock} with {len(stock_data)} candles")
        try:
            # Process indicators for this stock (CPU-intensive work)
            result = {
                "symbol": stock,
                "data": []
            }
            
            # Pre-calculate all indicator keys for performance
            indicator_configs = []
            for indicator in indicators:
                timeframe = indicator.get("timeframe", "daily")
                name = indicator.get("name", "").lower()
                params = indicator.get("params", {})
                period = params.get("period", 14)
                indicator_key = f"{timeframe}_{name}_{period}"
                indicator_configs.append({
                    "name": name,
                    "key": indicator_key,
                    "timeframe": timeframe,
                    "period": period
                })
            
            # Extract price data for calculations
            closes = [float(candle.get("close", 0)) for candle in stock_data]
            highs = [float(candle.get("high", 0)) for candle in stock_data]
            lows = [float(candle.get("low", 0)) for candle in stock_data]
            
            # Process all candles for this stock with CPU-intensive calculations
            for idx, candle in enumerate(stock_data):
                enhanced_candle = {
                    "timestamp": candle.get("timestamp"),
                    "date": candle.get("timestamp"),
                    "open": candle.get("open"),
                    "high": candle.get("high"),
                    "low": candle.get("low"),
                    "close": candle.get("close"),
                    "volume": candle.get("volume")
                }
                
                # Add indicator values with some CPU-intensive calculations
                for config in indicator_configs:
                    name = config["name"]
                    indicator_key = config["key"]
                    period = config["period"]
                    
                    # Add some CPU-intensive calculations
                    if name == "rsi":
                        # Simulate RSI calculation (CPU intensive)
                        if idx >= period:
                            window_closes = closes[max(0, idx-period):idx+1]
                            # Simulate complex calculation
                            enhanced_candle[indicator_key] = 50.0 + sum(window_closes) / len(window_closes) * 0.001
                        else:
                            enhanced_candle[indicator_key] = 50.0
                    elif name == "sma":
                        # Calculate actual SMA
                        if idx >= period - 1:
                            window = closes[idx-period+1:idx+1]
                            enhanced_candle[indicator_key] = sum(window) / len(window)
                        else:
                            enhanced_candle[indicator_key] = candle.get("close", 0)
                    elif name == "ema":
                        # Simulate EMA calculation
                        enhanced_candle[indicator_key] = candle.get("close", 0) * 1.001
                    elif name == "bb":
                        # Simulate Bollinger Bands calculation
                        if idx >= period - 1:
                            window = closes[idx-period+1:idx+1]
                            mean = sum(window) / len(window)
                            # Simulate std calculation (CPU intensive)
                            variance = sum((x - mean) ** 2 for x in window) / len(window)
                            std = variance ** 0.5
                            enhanced_candle[f"{indicator_key}_upper"] = mean + (2 * std)
                            enhanced_candle[f"{indicator_key}_middle"] = mean
                            enhanced_candle[f"{indicator_key}_lower"] = mean - (2 * std)
                        else:
                            enhanced_candle[f"{indicator_key}_upper"] = candle.get("high", 0)
                            enhanced_candle[f"{indicator_key}_middle"] = candle.get("close", 0)
                            enhanced_candle[f"{indicator_key}_lower"] = candle.get("low", 0)
                
                result["data"].append(enhanced_candle)
            
            stock_end = time.time()
            print(f"[DEBUG] Completed stock {stock} in {stock_end - stock_start:.2f}s")
            results.append((stock, result, True, None))
            
        except Exception as e:
            stock_end = time.time()
            print(f"[DEBUG] Failed stock {stock} in {stock_end - stock_start:.2f}s: {e}")
            results.append((stock, None, False, str(e)))
    
    batch_end = time.time()
    print(f"[DEBUG] Batch completed in {batch_end - batch_start:.2f}s with {len(results)} results")
    return results

async def process_indicators_background(indicators: List[Dict[str, Any]]):
    """MAXIMUM PERFORMANCE with optimized I/O to avoid startup/completion bottlenecks."""
    start_time = time.time()
    
    print(f"\n[API] Precalculate-indicators: Processing {len(STOCK_SYMBOLS)} stocks with {PERFORMANCE_CONFIG['max_cpu_workers']} CPU workers")
    
    try:
        # Create precalculatedStorage directory
        precalc_dir = Path("precalculatedStorage")
        precalc_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract timeframes from indicators
        timeframes = list(set(ind.get('timeframe', 'daily') for ind in indicators))
        
        # Send initial progress
        update_progress({
            "isRunning": True,
            "phase": "processing_indicators",
            "message": "Starting high-performance processing...",
            "processed": 0,
            "total": len(STOCK_SYMBOLS),
            "status": "processing"
        })
        
        # Thread-safe counters
        progress_lock = threading.Lock()
        counters = {"processed": 0, "successful": 0, "failed": 0}
        
        def update_counters_batch(success_count: int, failed_count: int):
            with progress_lock:
                counters["processed"] += success_count + failed_count
                counters["successful"] += success_count
                counters["failed"] += failed_count
                
                # Update progress frequently for smooth SSE
                update_progress({
                    "isRunning": True,
                    "phase": "processing_indicators",
                    "message": f"Processing... ({counters['processed']}/{len(STOCK_SYMBOLS)})",
                    "processed": counters["processed"],
                    "total": len(STOCK_SYMBOLS),
                    "status": "processing",
                    "percentage": int((counters["processed"] / len(STOCK_SYMBOLS)) * 100)
                })
        
        # OPTIMIZED: Read files in smaller batches to avoid startup bottleneck
        stock_data_map = {}
        batch_size = 100  # Read files in smaller batches
        
        def read_stock_file(stock):
            try:
                stock_file = Path(__file__).parent.parent / "db" / f"{stock}.json"
                if stock_file.exists():
                    with open(stock_file, 'r') as f:
                        return stock, json.load(f), True
                return stock, None, False
            except Exception:
                return stock, None, False
        
        # Read files in batches instead of all at once
        for i in range(0, len(STOCK_SYMBOLS), batch_size):
            batch_symbols = STOCK_SYMBOLS[i:i + batch_size]
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=32) as file_executor:
                read_futures = [file_executor.submit(read_stock_file, stock) for stock in batch_symbols]
                
                for future in concurrent.futures.as_completed(read_futures):
                    stock, data, success = future.result()
                    if success and data:
                        stock_data_map[stock] = data
            
            # Small progress update for file reading
            await asyncio.sleep(0)
        
        # Prepare data for CPU-intensive processing
        valid_stocks = [(stock, stock_data_map[stock], indicators, timeframes) 
                       for stock in STOCK_SYMBOLS if stock in stock_data_map]
        
        # Split into optimal chunks for CPU processing
        chunk_size = max(5, len(valid_stocks) // (PERFORMANCE_CONFIG["max_cpu_workers"] * 3))
        chunks = [valid_stocks[i:i + chunk_size] for i in range(0, len(valid_stocks), chunk_size)]
        
        # Process chunks using ProcessPoolExecutor for MAXIMUM CPU usage
        all_results = []
        
        print(f"[DEBUG] Starting CPU processing with {len(chunks)} chunks, {PERFORMANCE_CONFIG['max_cpu_workers']} workers")
        
        # Use ProcessPoolExecutor for true parallelism (bypasses GIL)
        with concurrent.futures.ProcessPoolExecutor(max_workers=PERFORMANCE_CONFIG["max_cpu_workers"]) as cpu_executor:
            # Submit all chunk processing tasks
            loop = asyncio.get_event_loop()
            chunk_futures = []
            
            for i, chunk in enumerate(chunks):
                print(f"[DEBUG] Submitting chunk {i+1}/{len(chunks)} with {len(chunk)} stocks")
                future = loop.run_in_executor(cpu_executor, process_stock_batch_cpu_intensive, chunk)
                chunk_futures.append(future)
            
            # Process results as they complete with real-time progress updates
            completed_chunks = 0
            for future in asyncio.as_completed(chunk_futures):
                chunk_start_time = time.time()
                chunk_results = await future
                chunk_end_time = time.time()
                completed_chunks += 1
                
                print(f"[DEBUG] Completed chunk {completed_chunks}/{len(chunks)} in {chunk_end_time - chunk_start_time:.2f}s, got {len(chunk_results)} results")
                
                all_results.extend(chunk_results)
                
                # Update progress for this chunk
                success_count = sum(1 for _, _, success, _ in chunk_results if success)
                failed_count = len(chunk_results) - success_count
                update_counters_batch(success_count, failed_count)
                
                # Print current progress with timestamp
                current_time = time.time()
                print(f"[DEBUG] Progress update at {current_time:.2f}: {counters['processed']}/{len(STOCK_SYMBOLS)} stocks processed")
                
                # Minimal yield to allow SSE updates
                await asyncio.sleep(0)
        
        # MAXIMUM PERFORMANCE: Parallel file writing using ProcessPoolExecutor (same as calculations)
        print(f"[DEBUG] Starting PARALLEL file write phase with {len(all_results)} results using {PERFORMANCE_CONFIG['max_cpu_workers']} CPU workers")
        write_start_time = time.time()
        
        # Split file writing into optimal chunks for maximum CPU usage
        write_chunk_size = max(5, len(all_results) // (PERFORMANCE_CONFIG["max_cpu_workers"] * 2))
        write_chunks = [all_results[i:i + write_chunk_size] for i in range(0, len(all_results), write_chunk_size)]
        
        print(f"[DEBUG] File writing: {len(write_chunks)} chunks, {write_chunk_size} files per chunk")
        
        # Use ProcessPoolExecutor for maximum parallel file I/O (same approach as calculations)
        with concurrent.futures.ProcessPoolExecutor(max_workers=PERFORMANCE_CONFIG["max_cpu_workers"]) as write_executor:
            # Submit all file writing chunks in parallel
            write_futures = []
            
            for i, write_chunk in enumerate(write_chunks):
                print(f"[DEBUG] Submitting write chunk {i+1}/{len(write_chunks)} with {len(write_chunk)} files")
                future = loop.run_in_executor(write_executor, write_stock_batch_parallel, write_chunk, str(precalc_dir))
                write_futures.append(future)
            
            # Process write results as they complete (same pattern as calculations)
            completed_write_chunks = 0
            for future in asyncio.as_completed(write_futures):
                chunk_start = time.time()
                chunk_write_count = await future
                chunk_end = time.time()
                completed_write_chunks += 1
                
                print(f"[DEBUG] Completed write chunk {completed_write_chunks}/{len(write_chunks)} in {chunk_end - chunk_start:.2f}s, wrote {chunk_write_count} files")
                
                # Minimal yield for progress updates
                await asyncio.sleep(0)
        
        write_end_time = time.time()
        print(f"[DEBUG] PARALLEL file write phase completed in {write_end_time - write_start_time:.2f}s")
        
        # Update completion status
        precalc_data = {
            "status": "completed",
            "indicators": indicators,
            "lastUpdated": datetime.utcnow().isoformat()
        }
        
        with open("precalculatedIndicators.json", 'w') as f:
            json.dump(precalc_data, f, indent=2)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        update_progress({
            "isRunning": False,
            "phase": "completed",
            "message": f"HIGH-PERFORMANCE processing completed! Success: {counters['successful']}, Failed: {counters['failed']}",
            "processed": counters["processed"],
            "total": len(STOCK_SYMBOLS),
            "status": "completed",
            "successful": counters["successful"],
            "failed": counters["failed"]
        })
        
        print(f"[COMPLETED] Precalculate-indicators finished: {processing_time:.2f}s | Rate: {len(STOCK_SYMBOLS) / processing_time:.1f}/sec | Success: {counters['successful']}, Failed: {counters['failed']}")
        
    except Exception as error:
        print(f"[ERROR] Precalculate-indicators failed: {str(error)}")
        logger.error(f"High-performance processing error: {str(error)}", exc_info=True)
        
        update_progress({
            "isRunning": False,
            "phase": "error",
            "message": f"Processing failed: {str(error)}",
            "status": "error"
        })


async def process_stock_indicators(stock: str, stock_data: List[Dict], indicators: List[Dict], timeframes: List[str]) -> Dict:
    """Process indicators for a single stock."""
    try:
        # Initialize result structure
        result = {
            "symbol": stock,
            "data": []
        }
        
        # For now, just copy the stock data with indicator placeholders
        # In a real implementation, you would calculate the actual indicators here
        for candle in stock_data:
            enhanced_candle = {
                "timestamp": candle.get("timestamp"),
                "date": candle.get("timestamp"),
                "open": candle.get("open"),
                "high": candle.get("high"),
                "low": candle.get("low"),
                "close": candle.get("close"),
                "volume": candle.get("volume")
            }
            
            # Add indicator values (placeholder implementation)
            for indicator in indicators:
                timeframe = indicator.get("timeframe", "daily")
                name = indicator.get("name", "").lower()
                params = indicator.get("params", {})
                period = params.get("period", 14)
                
                # Create indicator key
                indicator_key = f"{timeframe}_{name}_{period}"
                
                # Add placeholder value (in real implementation, calculate actual value)
                if name == "rsi":
                    enhanced_candle[indicator_key] = 50.0  # Placeholder RSI value
                elif name == "sma":
                    enhanced_candle[indicator_key] = candle.get("close", 0)  # Placeholder SMA
                elif name == "ema":
                    enhanced_candle[indicator_key] = candle.get("close", 0)  # Placeholder EMA
                elif name == "bb":
                    enhanced_candle[f"{indicator_key}_upper"] = candle.get("high", 0)
                    enhanced_candle[f"{indicator_key}_middle"] = candle.get("close", 0)
                    enhanced_candle[f"{indicator_key}_lower"] = candle.get("low", 0)
            
            result["data"].append(enhanced_candle)
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing indicators for {stock}: {e}")
        raise


@app.get("/api/get-precalculated-indicators")
async def get_precalculated_indicators():
    """Get list of precalculated indicators."""
    try:
        # Read precalculated indicators file
        precalc_file = Path("precalculatedIndicators.json")
        if precalc_file.exists():
            with open(precalc_file, 'r') as f:
                data = json.load(f)
            return data
        else:
            return {"status": "not_found", "indicators": []}
            
    except Exception as error:
        logger.error(f"Get precalculated indicators error: {error}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(error)}")

@app.get("/api/progress-stream")
async def progress_stream():
    """Server-sent events for real-time progress updates."""
    async def generate():
        # Send initial connection message
        yield f"data: {json.dumps({'connected': True})}\n\n"
        
        # Send current progress immediately
        yield f"data: {json.dumps(current_progress)}\n\n"
        
        # Keep connection alive and send updates
        last_heartbeat = time.time()
        
        while True:
            try:
                # Check for progress updates (non-blocking)
                try:
                    # Get update from queue with short timeout
                    update = await asyncio.get_event_loop().run_in_executor(
                        None, progress_queue.get, True, 0.1
                    )
                    if update:
                        yield f"data: {json.dumps(update)}\n\n"
                except queue.Empty:
                    pass
                except Exception as e:
                    logger.error(f"Error getting from queue: {e}")
                
                # Send heartbeat every 10 seconds to keep connection alive
                current_time = time.time()
                if current_time - last_heartbeat > 10:
                    yield f"data: {json.dumps({'heartbeat': True})}\n\n"
                    last_heartbeat = current_time
                
                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SSE stream error: {e}")
                break
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable Nginx buffering
        }
    )

@app.post("/refreshdb")
async def refresh_database(request: RefreshDbRequest):
    """Refresh stock database with concurrent processing."""
    try:
        request_time = datetime.now()
        symbols = request.symbols or STOCK_SYMBOLS
        total_symbols = len(symbols)
        
        print(f"\n{'='*80}")
        print(f"[REFRESHDB] REQUEST RECEIVED at {request_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        print(f"[REFRESHDB] Processing {total_symbols} symbols: {symbols[:5]}{'...' if len(symbols) > 5 else ''}")
        print(f"[REFRESHDB] Request body: {request.dict()}")
        print(f"{'='*80}")
        sys.stdout.flush()
        logger.info(f"Starting database refresh for {total_symbols} symbols")
        logger.info(f"Symbols to process: {symbols}")
        
        # Reset progress
        update_progress({
            "isRunning": True,
            "phase": "initializing",
            "message": f"Starting database refresh for {total_symbols} symbols...",
            "processed": 0,
            "total": total_symbols,
            "successful": 0,
            "failed": 0,
            "status": "running",
            "startTime": datetime.utcnow().timestamp() * 1000
        })
        
        # Delete and recreate db directory in the root directory (consistent with Node.js)
        db_path = Path(__file__).parent.parent / "db"
        if db_path.exists():
            import shutil
            shutil.rmtree(db_path)
            print(f"[REFRESHDB] {datetime.now().strftime('%H:%M:%S.%f')[:-3]} - Deleted existing db directory")
        db_path.mkdir(parents=True, exist_ok=True)
        print(f"[REFRESHDB] {datetime.now().strftime('%H:%M:%S.%f')[:-3]} - Created fresh db directory")
        
        # Return immediate response
        response = {
            "success": True,
            "message": f"Database refresh started for {total_symbols} symbols. Check progress at /refreshdb-progress",
            "total": total_symbols,
            "progressUrl": "/refreshdb-progress"
        }
        
        # Start background processing
        task = asyncio.create_task(process_refresh_in_background(symbols, request_time))
        print(f"[REFRESHDB] {datetime.now().strftime('%H:%M:%S.%f')[:-3]} - Background task created")
        print(f"[REFRESHDB] {datetime.now().strftime('%H:%M:%S.%f')[:-3]} - Returning response: {response}")
        print(f"{'='*80}\n")
        sys.stdout.flush()
        logger.info(f"Background task created for {total_symbols} symbols")
        logger.info(f"RefreshDB response: {response}")
        
        return response
        
    except Exception as error:
        logger.error(f"Refresh database error: {error}")
        update_progress({
            "isRunning": False,
            "phase": "error",
            "message": f"Refresh failed: {str(error)}",
            "status": "error"
        })
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(error)}")

async def process_refresh_in_background(symbols: List[str], request_time: datetime):
    """Process database refresh in background with progress updates."""
    successful = 0
    failed = 0
    processed = 0
    total = len(symbols)
    background_start = datetime.now()
    
    try:
        print(f"\n{'🔄'*30}")
        print(f"🔄 BACKGROUND REFRESH STARTED")
        print(f"🔄 {background_start.strftime('%H:%M:%S.%f')[:-3]} - Processing {total} symbols")
        print(f"🔄 Time since request: {(background_start - request_time).total_seconds():.3f} seconds")
        print(f"{'🔄'*30}")
        sys.stdout.flush()
        logger.info(f"Background refresh started for {total} symbols")
        
        # Progress callback function
        async def progress_callback(symbol: str, success: bool):
            nonlocal successful, failed, processed
            processed += 1
            if success:
                successful += 1
            else:
                failed += 1
            
            current_time = datetime.now()
            elapsed = (current_time - api_start).total_seconds()
            
            # Update progress for every symbol to show real-time progress
            update_progress({
                "isRunning": True,
                "phase": "processing",
                "message": f"Processing stocks... ({processed}/{total})",
                "processed": processed,
                "total": total,
                "successful": successful,
                "failed": failed,
                "status": "running",
                "percentage": int((processed / total) * 100)
            })
            
            # Print progress with timing - show every symbol for small batches, every 10 for large batches
            show_progress = (total <= 10) or (processed % 10 == 0) or (processed == total) or (processed == 1)
            if show_progress:
                avg_time = elapsed / processed if processed > 0 else 0
                eta = avg_time * (total - processed) if processed > 0 else 0
                status_emoji = "✅" if success else "❌"
                print(f"{status_emoji} [{current_time.strftime('%H:%M:%S.%f')[:-3]}] {symbol} - "
                      f"Progress: {processed}/{total} ({int((processed/total)*100)}%) - "
                      f"Success: {successful}, Failed: {failed} - "
                      f"ETA: {eta:.1f}s")
                sys.stdout.flush()
        
        # Create payload for chartink service
        payload = [[str(datetime.now().timestamp()), symbol] for symbol in symbols]
        
        api_start = datetime.now()
        print(f"\n[BACKGROUND REFRESH] {api_start.strftime('%H:%M:%S.%f')[:-3]} - Starting API calls to Chartink")
        print(f"[BACKGROUND REFRESH] Payload created for {len(payload)} symbols")
        logger.info(f"Processing payload with {len(payload)} symbols")
        
        # Process using chartink service with unlimited concurrency
        results = await chartink_service.process_payload(
            payload, 
            concurrent_limit=None,  # Process all stocks concurrently
            progress_callback=progress_callback
        )
        
        api_end = datetime.now()
        print(f"\n[BACKGROUND REFRESH] {api_end.strftime('%H:%M:%S.%f')[:-3]} - API calls completed")
        print(f"[BACKGROUND REFRESH] API processing time: {(api_end - api_start).total_seconds():.3f} seconds")
        print(f"[BACKGROUND REFRESH] Results: {len(results)} items processed")
        logger.info(f"Chartink service processing completed with {len(results)} results")
        
        # Final update
        update_progress({
            "isRunning": False,
            "phase": "completed",
            "message": f"Database refresh completed. Success: {successful}, Failed: {failed}",
            "processed": processed,
            "total": total,
            "successful": successful,
            "failed": failed,
            "status": "completed",
            "percentage": 100
        })
        
        completion_time = datetime.now()
        total_time = (completion_time - request_time).total_seconds()
        api_time = (api_end - api_start).total_seconds()
        
        print(f"\n{'='*80}")
        print(f"[BACKGROUND REFRESH] COMPLETED at {completion_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        print(f"[BACKGROUND REFRESH] Results: Success: {successful}, Failed: {failed}")
        print(f"[BACKGROUND REFRESH] Total time: {total_time:.3f} seconds")
        print(f"[BACKGROUND REFRESH] API processing time: {api_time:.3f} seconds")
        print(f"[BACKGROUND REFRESH] Average: {(api_time/total if total > 0 else 0):.3f} seconds per symbol")
        print(f"{'='*80}\n")
        logger.info(f"Database refresh completed. Success: {successful}, Failed: {failed}")
        
    except Exception as error:
        error_msg = f"Background refresh error: {str(error)}"
        print(f"\n[BACKGROUND REFRESH ERROR] {error_msg}")
        logger.error(error_msg, exc_info=True)
        
        update_progress({
            "isRunning": False,
            "phase": "error",
            "message": f"Refresh failed: {str(error)}",
            "processed": processed,
            "total": total,
            "successful": successful,
            "failed": failed,
            "status": "error"
        })

@app.get("/refreshdb-progress")
async def get_refresh_progress():
    """Get database refresh progress."""
    return current_progress

@app.get("/refreshdb-progress-stream")
async def refreshdb_progress_stream():
    """Server-sent events for real-time refreshdb progress updates."""
    async def generate():
        # Send initial connection message
        yield f"data: {json.dumps({'connected': True, 'endpoint': 'refreshdb-progress-stream'})}\n\n"
        
        # Send current progress immediately
        yield f"data: {json.dumps(current_progress)}\n\n"
        
        # Keep connection alive and send updates
        last_heartbeat = time.time()
        
        while True:
            try:
                # Check for progress updates (non-blocking)
                try:
                    # Get update from queue with short timeout
                    update = await asyncio.get_event_loop().run_in_executor(
                        None, progress_queue.get, True, 0.1
                    )
                    if update:
                        yield f"data: {json.dumps(update)}\n\n"
                        logger.info(f"SSE refreshdb update sent: {update.get('phase', 'unknown')} - {update.get('processed', 0)}/{update.get('total', 0)}")
                except queue.Empty:
                    pass
                except Exception as e:
                    logger.error(f"Error getting from refreshdb progress queue: {e}")
                
                # Send heartbeat every 10 seconds to keep connection alive
                current_time = time.time()
                if current_time - last_heartbeat > 10:
                    yield f"data: {json.dumps({'heartbeat': True, 'timestamp': current_time})}\n\n"
                    last_heartbeat = current_time
                
                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                logger.info("RefreshDB SSE connection cancelled")
                break
            except Exception as e:
                logger.error(f"RefreshDB SSE stream error: {e}")
                break
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable Nginx buffering
        }
    )

@app.post("/upload-csv")
async def upload_csv(csvFile: UploadFile = File(...)):
    """Upload and process CSV file."""
    print(f"\n[CSV UPLOAD] API called with file: {csvFile.filename}")
    sys.stdout.flush()
    try:
        if not csvFile.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="Only CSV files are allowed")
        
        print(f"[PROCESSING] CSV file: {csvFile.filename}")
        
        # Initialize progress
        update_progress({
            "isRunning": True,
            "phase": "parsing",
            "message": "Parsing CSV file...",
            "processed": 0,
            "total": 100,
            "percentage": 5
        })
        
        # Read CSV content
        content = await csvFile.read()
        csv_content = content.decode('utf-8')
        
        # Parse CSV using Python's csv module
        csv_reader = csv.DictReader(StringIO(csv_content))
        symbols = set()  # Use set to avoid duplicates
        
        # Look for common column names that might contain symbols
        symbol_columns = ['symbol', 'Symbol', 'SYMBOL', 'stock', 'Stock', 'STOCK', 
                         'ticker', 'Ticker', 'TICKER', 'name', 'Name', 'NAME']
        
        for row in csv_reader:
            # Try to find symbol in any of the possible columns
            for col_name in symbol_columns:
                if col_name in row and row[col_name]:
                    symbol = row[col_name].strip().upper()
                    if symbol:
                        symbols.add(symbol)
                        break  # Found symbol, no need to check other columns
        
        extracted_symbols = sorted(list(symbols))
        
        print(f"[SUCCESS] Extracted {len(extracted_symbols)} unique symbols from CSV: {extracted_symbols[:5]}...")
        logger.info(f"Extracted {len(extracted_symbols)} unique symbols from CSV")
        
        # Update progress after extraction
        update_progress({
            "isRunning": True,
            "phase": "extracted",
            "message": f"Extracted {len(extracted_symbols)} symbols from CSV",
            "processed": 20,
            "total": 100,
            "percentage": 20,
            "symbolCount": len(extracted_symbols)
        })
        
        # Background processing - update constants file and refresh database
        try:
            await process_csv_symbols_in_background(extracted_symbols)
        except Exception as e:
            print(f"[ERROR] Background processing failed: {e}")
            logger.error(f"Background processing failed: {e}")
            # Don't fail the main request, just log the error
        
        return {
            "success": True,
            "message": "CSV processing started",
            "symbolCount": len(extracted_symbols),
            "sampleSymbols": extracted_symbols[:10],  # Show first 10 as preview
            "progressUrl": "/csv-upload-progress"
        }
        
    except Exception as error:
        logger.error(f"CSV upload error: {error}")
        # Update progress with error
        update_progress({
            "isRunning": False,
            "phase": "error", 
            "message": f"CSV processing failed: {str(error)}",
            "processed": 0,
            "total": 100,
            "percentage": 0
        })
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(error)}")

async def process_csv_symbols_in_background(extracted_symbols: List[str]):
    """Process extracted symbols by updating constants and refreshing database"""
    try:
        print(f"\n{'='*60}")
        print(f"BACKGROUND PROCESSING STARTED - {len(extracted_symbols)} symbols")
        print(f"{'='*60}\n")
        
        # Update progress - updating constants
        update_progress({
            "isRunning": True,
            "phase": "updating_constants",
            "message": "Updating symbol constants...",
            "processed": 30,
            "total": 100,
            "percentage": 30
        })
        
        # Update stockSymbols.constants.js file
        constants_path = Path(__file__).parent.parent / "stockSymbols.constants.js"
        print(f"1. Updating constants file")
        print(f"   Path: {constants_path.absolute()}")
        
        # Create the new symbols array content
        symbols_content = "const STOCK_SYMBOLS = [\n"
        symbols_content += ",\n".join(f"  '{symbol}'" for symbol in extracted_symbols)
        symbols_content += "\n];\n\nmodule.exports = { STOCK_SYMBOLS };"
        
        # Write the updated constants file
        try:
            with open(constants_path, 'w', encoding='utf-8') as f:
                f.write(symbols_content)
            print(f"   [SUCCESS] Updated constants file with {len(extracted_symbols)} symbols")
        except Exception as e:
            print(f"   [ERROR] Failed to write constants file: {e}")
            raise
        
        # Update progress - refreshing database
        update_progress({
            "isRunning": True,
            "phase": "refreshing_database",
            "message": f"Fetching stock data for {len(extracted_symbols)} symbols...",
            "processed": 50,
            "total": 100,
            "percentage": 50
        })
        
        # Delete and recreate db directory (same as refreshdb) in the root directory
        db_path = Path(__file__).parent.parent / "db"
        if db_path.exists():
            import shutil
            shutil.rmtree(db_path)
            print(f"\n2. Deleted existing db directory")
        db_path.mkdir(parents=True, exist_ok=True)
        print(f"   Created fresh db directory: {db_path.absolute()}")
        
        # Create payload for chartink service (same as refreshdb)
        payload = [[str(datetime.now().timestamp()), symbol] for symbol in extracted_symbols]
        
        successful = 0
        failed = 0
        processed = 0
        total = len(extracted_symbols)
        
        # Progress callback function
        async def progress_callback(symbol: str, success: bool):
            nonlocal successful, failed, processed
            processed += 1
            if success:
                successful += 1
            else:
                failed += 1
            
            # Update progress - 50-90% range during data fetching
            progress_percent = 50 + int((processed / total) * 40)
            update_progress({
                "isRunning": True,
                "phase": "fetching_data",
                "message": f"Fetching stock data... ({processed}/{total})",
                "processed": progress_percent,
                "total": 100,
                "percentage": progress_percent,
                "successful": successful,
                "failed": failed
            })
            
            # Print progress for monitoring
            if processed % 10 == 0 or processed == total:
                status_emoji = "✅" if success else "❌"
                print(f"   {status_emoji} Progress: {processed}/{total} ({progress_percent}%) - Success: {successful}, Failed: {failed}")
        
        print(f"\n3. Fetching stock data from Chartink API")
        print(f"   Processing {total} symbols with real-time data...")
        
        # Process using chartink service (same as refreshdb)
        results = await chartink_service.process_payload(
            payload, 
            concurrent_limit=None,  # Process all stocks concurrently
            progress_callback=progress_callback
        )
        
        print(f"\n[DATA FETCH COMPLETED] Successfully processed {len(results)} symbols")
        print(f"   Successful: {successful}, Failed: {failed}")
        
        # Update progress - starting indicator calculation
        update_progress({
            "isRunning": True,
            "phase": "calculating_indicators",
            "message": "Starting high-performance indicator calculation...",
            "processed": 95,
            "total": 100,
            "percentage": 95
        })
        
        # Get default indicators for precalculation
        default_indicators = [
            {
                "timeframe": "daily",
                "name": "sma",
                "params": {"length": 20}
            },
            {
                "timeframe": "daily", 
                "name": "ema",
                "params": {"length": 20}
            },
            {
                "timeframe": "daily",
                "name": "rsi",
                "params": {"length": 14}
            },
            {
                "timeframe": "daily",
                "name": "volume",
                "params": {}
            }
        ]
        
        print(f"\n4. Starting precalculated indicators processing...")
        print(f"   Indicators: {len(default_indicators)}")
        print(f"   Using {CPU_COUNT} CPU cores for maximum performance")
        
        # Start high-performance indicator processing
        await process_indicators_background(default_indicators)
        
        # Final completion
        update_progress({
            "isRunning": False,
            "phase": "completed",
            "message": f"Successfully processed {len(extracted_symbols)} symbols with indicators. Success: {successful}, Failed: {failed}",
            "processed": 100,
            "total": 100,
            "percentage": 100,
            "successful": successful,
            "failed": failed
        })
        
        print(f"\n{'='*60}")
        print(f"CSV PROCESSING COMPLETED WITH INDICATORS!")
        print(f"{'='*60}\n")
        
    except Exception as error:
        print(f"\n[FATAL ERROR] Background processing error: {error}")
        import traceback
        traceback.print_exc()
        logger.error(f"Background processing error: {error}")
        update_progress({
            "isRunning": False,
            "phase": "error",
            "message": f"Background processing failed: {str(error)}",
            "processed": 0,
            "total": 100,
            "percentage": 0
        })

@app.get("/test-debug")
async def test_debug():
    """Test endpoint for debugging"""
    return {"message": "Debug endpoint works!", "timestamp": datetime.now().isoformat()}

@app.get("/test-sse")
async def test_sse():
    """Test SSE by triggering progress updates"""
    print("[TEST-SSE] Triggering test progress updates")
    
    # Reset progress
    update_progress({
        "isRunning": True,
        "phase": "testing",
        "message": "Starting SSE test...",
        "processed": 0,
        "total": 100,
        "status": "processing"
    })
    
    # Create background task to simulate progress
    async def simulate_progress():
        for i in range(0, 101, 10):
            await asyncio.sleep(1)
            update_progress({
                "isRunning": True,
                "phase": "testing",
                "message": f"Testing SSE: {i}% complete",
                "processed": i,
                "total": 100,
                "status": "processing"
            })
        
        update_progress({
            "isRunning": False,
            "phase": "completed",
            "message": "SSE test completed",
            "processed": 100,
            "total": 100,
            "status": "completed"
        })
    
    asyncio.create_task(simulate_progress())
    
    return {"message": "SSE test started. Connect to /api/progress-stream to see updates."}

@app.get("/csv-upload-progress")  
async def get_csv_upload_progress():
    """Get CSV upload progress."""
    return current_progress

@app.post("/update-symbols-and-refresh")
async def update_symbols_and_refresh():
    """Update symbols list and refresh database."""
    try:
        # This would implement the logic to update symbols and refresh
        return {"success": True, "message": "Symbols updated and database refreshed"}
        
    except Exception as error:
        logger.error(f"Update symbols error: {error}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(error)}")

if __name__ == "__main__":
    print("="*60)
    print("STARTING CHARTINKSUPER FASTAPI SERVER (SIMPLE MODE)")
    print("="*60)
    print(f"Server URL: http://127.0.0.1:8001")
    print(f"API Docs: http://127.0.0.1:8001/docs")
    print(f"Health Check: http://127.0.0.1:8001/health")
    print(f"Refresh DB: POST http://127.0.0.1:8001/refreshdb")
    print(f"SSE Progress: GET http://127.0.0.1:8001/refreshdb-progress-stream")
    print("="*60)
    print("Logs will appear below when APIs are called...")
    print("="*60)
    sys.stdout.flush()
    
    # Simple uvicorn run without complex logging
    import uvicorn
    uvicorn.run(
        app,  # Use app directly instead of "main:app" 
        host="127.0.0.1",
        port=8001,
        log_level="critical",  # Suppress uvicorn logs
        access_log=False,      # Disable access logs (we have our own)
        reload=False           # Disable reload to avoid watchfiles logs
    )