import sys
import io
import os

# Set UTF-8 encoding environment variables
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUNBUFFERED'] = '1'

# Force UTF-8 encoding for stdout/stderr only when not already wrapped
if hasattr(sys.stdout, 'buffer') and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass  # Already wrapped or unavailable

if hasattr(sys.stderr, 'buffer') and sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except:
        pass  # Already wrapped or unavailable

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
import uvicorn
import asyncio
import logging
from typing import List, Dict, Any, Optional
import json
import math
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
from concurrent.futures import ThreadPoolExecutor
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

# Simple query lock to prevent concurrent queries
query_lock = threading.Lock()
current_query_id = None

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

@app.on_event("startup")
async def startup_event():
    """Initialize app state on startup."""
    print("FastAPI server started")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown."""
    print("FastAPI server shutdown")

# Simple request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = None
    
    try:
        # Process request
        response = await call_next(request)
        
        # Log only essential info
        process_time = time.time() - start_time
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
        
        return response
    except Exception as e:
        process_time = time.time() - start_time
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR in {request.method} {request.url.path} - {process_time:.3f}s")
        print(f"Error type: {type(e).__name__}")
        print(f"Error details: {str(e)}")
        
        # If it's an HTTPException, re-raise it
        if isinstance(e, HTTPException):
            raise
        
        # For other exceptions, return a proper error response
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error": str(e)}
        )

# Helper function to sanitize data for JSON serialization
def sanitize_for_json(obj):
    """Recursively sanitize data to ensure JSON compatibility."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif hasattr(obj, '__dict__'):
        return sanitize_for_json(obj.__dict__)
    return obj

# Custom JSON response that handles edge cases
class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            sanitize_for_json(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":")
        ).encode("utf-8")

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
(Path(__file__).parent / "db").mkdir(parents=True, exist_ok=True)

# Technical indicator calculation functions
def calculate_atr(highs, lows, closes, period=14):
    """Calculate Average True Range using Wilder's smoothing method"""
    true_ranges = []
    for i in range(len(closes)):
        if i == 0:
            true_ranges.append(highs[i] - lows[i])
        else:
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i-1])
            lc = abs(lows[i] - closes[i-1])
            true_ranges.append(max(hl, hc, lc))
    
    # Calculate ATR using Wilder's smoothing method
    atr_values = []
    atr = None
    
    for i in range(len(true_ranges)):
        if i < period - 1:
            atr_values.append(None)
        elif i == period - 1:
            # Initial ATR = average of first 'period' true ranges
            atr = sum(true_ranges[0:period]) / period
            atr_values.append(atr)
        else:
            # Wilder's smoothing: ATR = (Previous ATR * (period-1) + Current TR) / period
            atr = (atr * (period - 1) + true_ranges[i]) / period
            atr_values.append(atr)
    
    return atr_values

def calculate_atr_sma(highs, lows, closes, period=14):
    """Calculate ATR using Simple Moving Average for weekly SuperTrend"""
    true_ranges = []
    for i in range(len(closes)):
        if i == 0:
            true_ranges.append(highs[i] - lows[i])
        else:
            hl = highs[i] - lows[i]  
            hc = abs(highs[i] - closes[i-1])
            lc = abs(lows[i] - closes[i-1])
            true_ranges.append(max(hl, hc, lc))
    
    # Calculate ATR using Simple Moving Average
    atr_values = []
    for i in range(len(true_ranges)):
        if i < period - 1:
            atr_values.append(None)
        else:
            window = true_ranges[i-period+1:i+1]
            atr_values.append(sum(window) / len(window))
    
    return atr_values

def calculate_supertrend(highs, lows, closes, period=10, multiplier=2):
    """Calculate SuperTrend indicator using the standard algorithm"""
    atr_values = calculate_atr(highs, lows, closes, period)
    
    # Arrays to store intermediate calculations
    basic_upper_band = []
    basic_lower_band = []
    final_upper_band = []
    final_lower_band = []
    supertrend_values = []
    trend_direction = []
    
    for i in range(len(closes)):
        if i < period - 1 or atr_values[i] is None:
            basic_upper_band.append(None)
            basic_lower_band.append(None)
            final_upper_band.append(None)
            final_lower_band.append(None)
            supertrend_values.append(None)
            trend_direction.append(None)
        else:
            # Step 1: Calculate basic upper and lower bands
            hl2 = (highs[i] + lows[i]) / 2  # Typical price
            basic_upper = hl2 + (multiplier * atr_values[i])
            basic_lower = hl2 - (multiplier * atr_values[i])
            
            basic_upper_band.append(basic_upper)
            basic_lower_band.append(basic_lower)
            
            # Step 2: Calculate final upper and lower bands
            if i == period - 1:  # First calculation
                final_upper = basic_upper
                final_lower = basic_lower
            else:
                # Final Upper Band = Basic Upper Band if Basic Upper Band < Previous Final Upper Band 
                # OR Previous Close > Previous Final Upper Band, else Previous Final Upper Band
                if basic_upper < final_upper_band[i-1] or closes[i-1] > final_upper_band[i-1]:
                    final_upper = basic_upper
                else:
                    final_upper = final_upper_band[i-1]
                
                # Final Lower Band = Basic Lower Band if Basic Lower Band > Previous Final Lower Band 
                # OR Previous Close < Previous Final Lower Band, else Previous Final Lower Band
                if basic_lower > final_lower_band[i-1] or closes[i-1] < final_lower_band[i-1]:
                    final_lower = basic_lower
                else:
                    final_lower = final_lower_band[i-1]
            
            final_upper_band.append(final_upper)
            final_lower_band.append(final_lower)
            
            # Step 3: Determine trend direction and SuperTrend value
            if i == period - 1:  # First calculation
                # Initial SuperTrend calculation
                if closes[i] <= final_lower:
                    trend = -1  # Bearish
                    supertrend = final_upper
                else:
                    trend = 1   # Bullish
                    supertrend = final_lower
            else:
                prev_trend = trend_direction[i-1]
                
                # Classic SuperTrend trend continuation logic
                if prev_trend == 1:  # Previous trend was bullish
                    if closes[i] <= final_lower:
                        trend = -1  # Switch to bearish
                        supertrend = final_upper
                    else:
                        trend = 1   # Continue bullish
                        supertrend = final_lower
                else:  # Previous trend was bearish
                    if closes[i] >= final_upper:
                        trend = 1   # Switch to bullish
                        supertrend = final_lower
                    else:
                        trend = -1  # Continue bearish
                        supertrend = final_upper
            
            trend_direction.append(trend)
            supertrend_values.append(supertrend)
    
    return supertrend_values

def calculate_supertrend_weekly(highs, lows, closes, period=10, multiplier=2):
    """Calculate SuperTrend for weekly timeframe using standard algorithm"""
    # Use standard SuperTrend algorithm with Wilder's ATR for weekly calculations
    return calculate_supertrend(highs, lows, closes, period, multiplier)

def calculate_sma(values, period):
    """Calculate Simple Moving Average"""
    result = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            window = values[i-period+1:i+1]
            result.append(sum(window) / len(window))
    return result

def calculate_ema(values, period):
    """Calculate Exponential Moving Average"""
    result = []
    multiplier = 2 / (period + 1)
    
    for i in range(len(values)):
        if i == 0:
            result.append(values[i])
        elif result[i-1] is None:
            result.append(values[i])
        else:
            ema = (values[i] - result[i-1]) * multiplier + result[i-1]
            result.append(ema)
    
    return result

def calculate_rsi(closes, period=14):
    """Calculate Relative Strength Index"""
    gains = []
    losses = []
    
    for i in range(len(closes)):
        if i == 0:
            gains.append(0)
            losses.append(0)
        else:
            change = closes[i] - closes[i-1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))
    
    avg_gains = calculate_sma(gains, period)
    avg_losses = calculate_sma(losses, period)
    
    rsi_values = []
    for i in range(len(closes)):
        if avg_gains[i] is None or avg_losses[i] is None or avg_losses[i] == 0:
            rsi_values.append(None)
        else:
            rs = avg_gains[i] / avg_losses[i]
            rsi = 100 - (100 / (1 + rs))
            rsi_values.append(rsi)
    
    return rsi_values

def calculate_bollinger_bands(closes, period=20, std_dev=2):
    """Calculate Bollinger Bands"""
    sma_values = calculate_sma(closes, period)
    upper_band = []
    lower_band = []
    
    for i in range(len(closes)):
        if i < period - 1 or sma_values[i] is None:
            upper_band.append(None)
            lower_band.append(None)
        else:
            window = closes[i-period+1:i+1]
            mean = sma_values[i]
            variance = sum((x - mean) ** 2 for x in window) / len(window)
            std = variance ** 0.5
            
            upper_band.append(mean + (std_dev * std))
            lower_band.append(mean - (std_dev * std))
    
    return upper_band, sma_values, lower_band

def get_week_start_timestamp(timestamp):
    """Get the start of the week (Sunday) for a given timestamp"""
    import datetime
    dt = datetime.datetime.fromtimestamp(timestamp / 1000)
    days_since_sunday = dt.weekday() + 1  # Monday is 0, so Sunday becomes 6
    if days_since_sunday == 7:
        days_since_sunday = 0
    week_start = dt - datetime.timedelta(days=days_since_sunday)
    return int(week_start.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)

def get_month_start_timestamp(timestamp):
    """Get the start of the month for a given timestamp"""
    import datetime
    dt = datetime.datetime.fromtimestamp(timestamp / 1000)
    month_start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(month_start.timestamp() * 1000)

def calculate_weekly_monthly_ohlcv(stock_data):
    """Calculate weekly and monthly OHLCV data from daily data with proper day-of-week logic"""
    if not stock_data:
        return {}, {}
    
    import datetime
    
    weekly_data = {}
    monthly_data = {}
    
    # Group candles by week first, then process in chronological order
    weekly_candles = {}
    
    for candle in stock_data:
        timestamp = candle.get("timestamp", 0)
        week_key = get_week_start_timestamp(timestamp)
        
        if week_key not in weekly_candles:
            weekly_candles[week_key] = []
        weekly_candles[week_key].append(candle)
    
    # Process each week's candles in chronological order
    for week_key, candles in weekly_candles.items():
        # Sort candles by timestamp to ensure proper order
        candles.sort(key=lambda x: x.get("timestamp", 0))
        
        # Initialize weekly data with first candle (Monday or first trading day)
        first_candle = candles[0]
        last_candle = candles[-1]
        
        weekly_data[week_key] = {
            "open": first_candle.get("open"),  # Open of first trading day
            "high": max(candle.get("high", 0) for candle in candles),  # Highest high of the week
            "low": min((candle.get("low") for candle in candles if candle.get("low") is not None), default=0),  # Lowest low of the week
            "close": last_candle.get("close"),  # Close of last trading day in the data
            "volume": sum(candle.get("volume", 0) for candle in candles),  # Total volume
            "count": len(candles),
            "days": []  # Track which days are included
        }
        
        # Add day of week information for debugging
        for candle in candles:
            candle_dt = datetime.datetime.fromtimestamp(candle.get("timestamp", 0) / 1000)
            day_of_week = candle_dt.strftime('%A')  # Monday, Tuesday, etc.
            weekly_data[week_key]["days"].append(day_of_week)
        
        # Monthly aggregation (unchanged logic)
        for candle in candles:
            timestamp = candle.get("timestamp", 0)
            month_key = get_month_start_timestamp(timestamp)
            
            if month_key not in monthly_data:
                monthly_data[month_key] = {
                    "open": candle.get("open"),
                    "high": candle.get("high"),
                    "low": candle.get("low"),
                    "close": candle.get("close"),
                    "volume": candle.get("volume", 0),
                    "count": 1
                }
            else:
                monthly_data[month_key]["high"] = max(monthly_data[month_key]["high"], candle.get("high", 0))
                low_value = candle.get("low")
                if low_value is not None:
                    monthly_data[month_key]["low"] = min(monthly_data[month_key]["low"], low_value)
                monthly_data[month_key]["close"] = candle.get("close")  # Last close in the month
                monthly_data[month_key]["volume"] += candle.get("volume", 0)
                monthly_data[month_key]["count"] += 1
    
    return weekly_data, monthly_data

def update_progress(updates: Dict[str, Any]):
    """Update progress and notify SSE connections with rate limiting."""
    global current_progress
    current_progress.update(updates)
    
    # Calculate percentage
    if current_progress["total"] > 0:
        current_progress["percentage"] = min(
            int((current_progress["processed"] / current_progress["total"]) * 100), 100
        )
    
    # Add timestamp for client-side deduplication
    current_progress["timestamp"] = time.time()
    
    # Broadcast update to all SSE connections with queue management
    try:
        # Only add to queue if it's not too full (prevent flooding)
        if progress_queue.qsize() < 10:
            progress_queue.put_nowait(current_progress.copy())
        else:
            # If queue is getting full, clear old items and add latest
            while progress_queue.qsize() > 5:
                try:
                    progress_queue.get_nowait()
                except queue.Empty:
                    break
            progress_queue.put_nowait(current_progress.copy())
    except queue.Full:
        # If queue is full, clear it and add the latest
        while not progress_queue.empty():
            try:
                progress_queue.get_nowait()
            except queue.Empty:
                break
        progress_queue.put_nowait(current_progress.copy())
    
    # Log progress update (less verbose)
    if current_progress.get("processed", 0) % 10 == 0 or current_progress.get("isRunning") == False:
        logger.info(f"Progress: {current_progress.get('phase', 'unknown')} - {current_progress.get('processed', 0)}/{current_progress.get('total', 0)} ({current_progress.get('percentage', 0)}%)")

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


@app.post("/query")
async def process_query(request: QueryRequest):
    """Process stock screening query."""
    global current_query_id
    
    # Check if another query is already running
    if not query_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409, 
            detail="Another query is already running. Please wait for it to complete."
        )
    
    try:
        query = request.query
        stocks = request.stocks
        
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Generate unique query ID
        import uuid
        current_query_id = str(uuid.uuid4())[:8]
        
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
        
        # MAXIMUM PERFORMANCE: Use ProcessPoolExecutor for true parallelism
        print(f"[DEBUG] Starting MAXIMUM PERFORMANCE query processing with {PERFORMANCE_CONFIG['max_cpu_workers']} workers")
        query_start_time = time.time()
        
        # Use ProcessPoolExecutor for maximum CPU utilization (bypasses GIL)
        max_workers = PERFORMANCE_CONFIG["max_cpu_workers"]  # Use all available CPU workers
        
        # Split stocks into optimal chunks for maximum CPU usage
        chunk_size = max(10, len(stock_list) // (max_workers * 2))
        chunks = [stock_list[i:i + chunk_size] for i in range(0, len(stock_list), chunk_size)]
        
        print(f"[DEBUG] Full query: {len(chunks)} chunks, {chunk_size} stocks per chunk")
        
        try:
            # SAFE ProcessPoolExecutor usage with proper async handling
            def run_parallel_chunks():
                """Run chunks in separate processes safely"""
                try:
                    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                        current_dir = str(Path(__file__).parent.absolute())
                        
                        # Submit all chunks
                        futures = [
                            executor.submit(process_query_batch_parallel, chunk, parsed_query, current_dir)
                            for chunk in chunks
                        ]
                        
                        # Collect results as they complete
                        results = []
                        for i, future in enumerate(concurrent.futures.as_completed(futures)):
                            try:
                                result = future.result(timeout=120)  # 2 minute timeout per chunk
                                results.append(result)
                                print(f"[DEBUG] Completed chunk {i+1}/{len(chunks)}")
                            except Exception as e:
                                print(f"[ERROR] Chunk {i+1} failed: {e}")
                                results.append({"matches": [], "errors": [], "processed": 0, "processing_time": 0})
                        
                        return results
                except Exception as e:
                    print(f"[ERROR] ProcessPoolExecutor failed: {e}")
                    return []
            
            # Run parallel processing in thread pool to avoid ASGI issues
            loop = asyncio.get_event_loop()
            chunk_results = await loop.run_in_executor(None, run_parallel_chunks)
            
            # Process results
            completed_chunks = 0
            for chunk_result in chunk_results:
                completed_chunks += 1
                
                print(f"[DEBUG] Processing result from chunk {completed_chunks}/{len(chunks)}")
                print(f"[DEBUG] Chunk results: {chunk_result['processed']} processed, {len(chunk_result['matches'])} matches, {len(chunk_result['errors'])} errors")
                
                # Aggregate results
                all_matches.extend(chunk_result["matches"])
                errors.extend(chunk_result["errors"])
                processed_count += chunk_result["processed"]
                
                # Update progress for this chunk
                update_progress({
                    "phase": "processing_and_analyzing",
                    "message": f"Parallel query: {processed_count}/{total_stocks} stocks, {len(all_matches)} matches found",
                    "processed": processed_count,
                    "total": total_stocks,
                    "matches": len(all_matches)
                })
                
                # Check for abort
                if current_query_abort["aborted"]:
                    raise HTTPException(status_code=400, detail="Query was aborted")
                
                # Allow progress updates
                await asyncio.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Parallel processing error: {e}")
            print(f"[WARNING] Parallel processing failed: {e}")
            # Fallback to safe ThreadPoolExecutor
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
        logger.error(f"Query endpoint error: {error}", exc_info=True)
        error_msg = f"Query processing failed: {str(error)}"
        update_progress({
            "phase": "error",
            "message": error_msg,
            "isRunning": False,
            "error_details": str(error)
        })
        raise HTTPException(status_code=500, detail={
            "error": "Query processing failed",
            "details": str(error),
            "type": "processing_error"
        })
    finally:
        # Always release the query lock
        try:
            query_lock.release()
            current_query_id = None
        except:
            pass  # Lock may not be held in some error cases

@app.post("/query/latest")
async def process_latest_query(request: QueryRequest):
    """Process query for latest day only - optimized for speed."""
    global current_query_id
    
    # Check if another query is already running
    if not query_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409, 
            detail="Another query is already running. Please wait for it to complete."
        )
    
    try:
        query = request.query
        stocks = request.stocks
        
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Generate unique query ID
        import uuid
        current_query_id = str(uuid.uuid4())[:8]
        
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
        
        # MAXIMUM PERFORMANCE: Parallel latest scan processing using ProcessPoolExecutor
        print(f"[DEBUG] Starting PARALLEL latest scan with {PERFORMANCE_CONFIG['max_cpu_workers']} CPU workers")
        scan_start_time = time.time()
        
        # Split stocks into optimal chunks for maximum CPU usage
        scan_chunk_size = max(10, len(stock_list) // (PERFORMANCE_CONFIG["max_cpu_workers"] * 2))
        scan_chunks = [stock_list[i:i + scan_chunk_size] for i in range(0, len(stock_list), scan_chunk_size)]
        
        print(f"[DEBUG] Latest scan: {len(scan_chunks)} chunks, {scan_chunk_size} stocks per chunk")
        
        # Run processing synchronously to avoid async executor issues
        scan_results = []
        try:
            with concurrent.futures.ProcessPoolExecutor(max_workers=PERFORMANCE_CONFIG["max_cpu_workers"]) as executor:
                current_dir = str(Path(__file__).parent.absolute())
                
                # Submit all chunks
                futures = [
                    executor.submit(process_latest_scan_batch_parallel, chunk, parsed_query, current_dir)
                    for chunk in scan_chunks
                ]
                
                # Collect results as they complete
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    try:
                        result = future.result(timeout=60)  # 1 minute timeout per chunk for latest scan
                        scan_results.append(result)
                        print(f"[DEBUG] Completed scan chunk {i+1}/{len(scan_chunks)}")
                        
                        # Yield control periodically to keep async loop responsive
                        if i % 5 == 0:
                            await asyncio.sleep(0)
                    except Exception as e:
                        print(f"[ERROR] Scan chunk {i+1} failed: {e}")
                        scan_results.append({"matches": [], "errors": [], "processed": 0, "processing_time": 0})
            
            # Process scan results
            completed_chunks = 0
            for chunk_result in scan_results:
                completed_chunks += 1
                
                print(f"[DEBUG] Processing scan result from chunk {completed_chunks}/{len(scan_chunks)}")
                print(f"[DEBUG] Chunk results: {chunk_result['processed']} processed, {len(chunk_result['matches'])} matches, {len(chunk_result['errors'])} errors")
                
                # Aggregate results
                all_matches.extend(chunk_result["matches"])
                errors.extend(chunk_result["errors"])
                processed_count += chunk_result["processed"]
                
                # Update progress for this chunk
                update_progress({
                    "phase": "processing_and_analyzing",
                    "message": f"Parallel latest scan: {processed_count}/{total_stocks} stocks, {len(all_matches)} matches found",
                    "processed": processed_count,
                    "total": total_stocks,
                    "matches": len(all_matches)
                })
                
                # Check for abort
                if current_query_abort["aborted"]:
                    raise HTTPException(status_code=400, detail="Query was aborted")
                
                # Allow progress updates
                await asyncio.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Latest scan parallel processing error: {e}")
            print(f"[WARNING] Latest scan parallel processing failed: {e}")
            # Continue without error - results will be empty but won't crash
        
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
        
        response_data = {
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
        
        return SafeJSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Latest day query processing error: {error}", exc_info=True)
        error_msg = f"Latest day scan failed: {str(error)}"
        update_progress({
            "phase": "error",
            "message": error_msg,
            "isRunning": False,
            "error_details": str(error)
        })
        raise HTTPException(status_code=500, detail={
            "error": "Latest day scan failed",
            "details": str(error),
            "type": "scan_error"
        })
    finally:
        # Always release the query lock
        try:
            query_lock.release()
            current_query_id = None
        except:
            pass  # Lock may not be held in some error cases

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
        current_time = datetime.utcnow()
        precalc_data = {
            "status": "processing",
            "indicators": indicators,
            "lastUpdated": current_time.isoformat(),
            "dayOfWeek": get_day_of_week_name(current_time.timestamp() * 1000)
        }
        
        with open("precalculatedIndicators.json", 'w') as f:
            json.dump(precalc_data, f, indent=2)
        
        # Start high-performance background processing in a separate thread
        # This avoids ASGI task group issues completely
        def run_background_task():
            """Run the async task in a new event loop in a separate thread."""
            try:
                # Create a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(process_indicators_background(indicators))
                loop.close()
            except Exception as e:
                print(f"Background task error: {e}")
        
        # Start the background thread
        thread = threading.Thread(target=run_background_task, daemon=True)
        thread.start()
        
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
        precalculated_file = Path(f"../precalculatedStorage/{stock}_piped.json")
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
            
            precalculated_file = Path(f"../precalculatedStorage/{stock}_piped.json")
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
                    timestamp = latest_candle.get("timestamp", "")
                    matches.append({
                        "stock": stock,
                        "date": timestamp,
                        "dayOfWeek": get_day_of_week_name(timestamp),
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
        precalculated_file = Path(f"../precalculatedStorage/{stock}_piped.json")
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
            
            precalculated_file = Path(f"../precalculatedStorage/{stock}_piped.json")
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
                        timestamp = candle.get("timestamp", "")
                        matches.append({
                            "stock": stock,
                            "date": timestamp,
                            "dayOfWeek": get_day_of_week_name(timestamp),
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
    try:
        import json
        import time
        import sys
        import os
        from pathlib import Path
        import traceback
        
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
                                timestamp = candle.get("timestamp", "")
                                matches.append({
                                    "stock": stock,
                                    "date": timestamp,
                                    "dayOfWeek": get_day_of_week_name(timestamp),
                                    "data": candle
                                })
                        except:
                            continue
                    return matches
        
        print(f"[DEBUG] Processing full query batch of {len(stock_batch)} stocks")
        
        for stock in stock_batch:
            try:
                # Check for precalculated data (full historical data for query)
                precalculated_file = Path(f"../precalculatedStorage/{stock}_piped.json")
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
        
    except Exception as e:
        print(f"[ERROR] Critical error in process_query_batch_parallel: {e}")
        traceback.print_exc()
        return {
            "matches": [],
            "errors": [{"error": f"Batch processing failed: {str(e)}"}],
            "processed": 0,
            "processing_time": 0
        }


def process_latest_scan_batch_parallel(stock_batch, parsed_query_dict, base_path=""):
    """Parallel latest scan processing function for ProcessPoolExecutor - maximizes CPU usage."""
    try:
        import json
        import time
        import sys
        import os
        from pathlib import Path
        import traceback
        
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
                                timestamp = candle.get("timestamp", "")
                                matches.append({
                                    "stock": stock,
                                    "date": timestamp,
                                    "dayOfWeek": get_day_of_week_name(timestamp),
                                    "data": candle
                                })
                        except:
                            continue
                    return matches
        
        print(f"[DEBUG] Processing latest scan batch of {len(stock_batch)} stocks")
        
        for stock in stock_batch:
            try:
                # Check for precalculated data
                precalculated_file = Path(f"../precalculatedStorage/{stock}_piped.json")
                if precalculated_file.exists():
                    with open(precalculated_file, 'r') as f:
                        mapped_data = json.load(f)
                    candles = mapped_data.get("data", [])
                    
                    if candles:
                        # For "crossed above/below" conditions, we need the last TWO candles
                        # For other conditions, just the latest candle is sufficient
                        if len(candles) >= 2:
                            # Pass last two candles to enable crossed above/below comparisons
                            last_two_candles = candles[-2:]
                            stock_matches = find_matching_candles(last_two_candles, parsed_query_dict, stock)
                        else:
                            # Fallback to single candle if only one available
                            latest_candle = candles[-1]
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
        
    except Exception as e:
        print(f"[ERROR] Critical error in process_latest_scan_batch_parallel: {e}")
        traceback.print_exc()
        return {
            "matches": [],
            "errors": [{"error": f"Scan batch processing failed: {str(e)}"}],
            "processed": 0,
            "processing_time": 0
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
                
                # Generate appropriate indicator key based on indicator type
                if name == "supertrend":
                    multiplier = params.get("multiplier", 2)
                    indicator_key = f"{timeframe}_{name}_{period}_{multiplier}"
                elif name == "bb":
                    std_dev = params.get("stdDev", 2)
                    indicator_key = f"{timeframe}_{name}_{period}_{std_dev}"
                else:
                    indicator_key = f"{timeframe}_{name}_{period}"
                
                indicator_configs.append({
                    "name": name,
                    "key": indicator_key,
                    "timeframe": timeframe,
                    "period": period,
                    "multiplier": params.get("multiplier", 2),
                    "std_dev": params.get("stdDev", 2)
                })
            
            # Extract price data for calculations
            closes = [float(candle.get("close", 0)) for candle in stock_data]
            highs = [float(candle.get("high", 0)) for candle in stock_data]
            lows = [float(candle.get("low", 0)) for candle in stock_data]
            
            # Always calculate weekly and monthly OHLCV data regardless of indicators
            weekly_ohlcv, monthly_ohlcv = calculate_weekly_monthly_ohlcv(stock_data)
            
            # Pre-calculate all indicators ONCE per stock for performance
            calculated_indicators = {}
            
            # Prepare weekly and monthly data arrays for indicator calculations
            weekly_candles = []
            monthly_candles = []
            
            # Convert weekly_ohlcv dict to ordered list for calculations
            for week_key in sorted(weekly_ohlcv.keys()):
                weekly_candles.append(weekly_ohlcv[week_key])
            
            # Convert monthly_ohlcv dict to ordered list for calculations  
            for month_key in sorted(monthly_ohlcv.keys()):
                monthly_candles.append(monthly_ohlcv[month_key])
            
            # Extract price arrays for different timeframes
            weekly_highs = [float(candle.get("high", 0)) for candle in weekly_candles]
            weekly_lows = [float(candle.get("low", 0)) for candle in weekly_candles]
            weekly_closes = [float(candle.get("close", 0)) for candle in weekly_candles]
            
            monthly_highs = [float(candle.get("high", 0)) for candle in monthly_candles]
            monthly_lows = [float(candle.get("low", 0)) for candle in monthly_candles]
            monthly_closes = [float(candle.get("close", 0)) for candle in monthly_candles]
            
            for config in indicator_configs:
                name = config["name"]
                indicator_key = config["key"]
                timeframe = config["timeframe"]
                period = config["period"]
                
                # Choose the correct data arrays based on timeframe
                if timeframe == "weekly":
                    calc_highs, calc_lows, calc_closes = weekly_highs, weekly_lows, weekly_closes
                elif timeframe == "monthly":
                    calc_highs, calc_lows, calc_closes = monthly_highs, monthly_lows, monthly_closes
                else:  # daily
                    calc_highs, calc_lows, calc_closes = highs, lows, closes
                
                if name == "rsi":
                    calculated_indicators[indicator_key] = calculate_rsi(calc_closes, period)
                elif name == "sma":
                    calculated_indicators[indicator_key] = calculate_sma(calc_closes, period)
                elif name == "ema":
                    calculated_indicators[indicator_key] = calculate_ema(calc_closes, period)
                elif name == "bb":
                    std_dev = config.get("std_dev", 2)
                    upper, middle, lower = calculate_bollinger_bands(calc_closes, period, std_dev)
                    calculated_indicators[f"{indicator_key}_upper"] = upper
                    calculated_indicators[f"{indicator_key}_middle"] = middle
                    calculated_indicators[f"{indicator_key}_lower"] = lower
                elif name == "supertrend":
                    multiplier = config.get("multiplier", 2)
                    if timeframe == "weekly":
                        # Use optimized weekly SuperTrend calculation
                        calculated_indicators[indicator_key] = calculate_supertrend_weekly(calc_highs, calc_lows, calc_closes, period, multiplier)
                    else:
                        # Use standard SuperTrend for daily/monthly
                        calculated_indicators[indicator_key] = calculate_supertrend(calc_highs, calc_lows, calc_closes, period, multiplier)
            
            # Process all candles for this stock - just map pre-calculated values
            for idx, candle in enumerate(stock_data):
                timestamp = candle.get("timestamp", 0)
                
                # Find corresponding weekly and monthly data
                week_key = get_week_start_timestamp(timestamp)
                month_key = get_month_start_timestamp(timestamp)
                
                weekly_candle = weekly_ohlcv.get(week_key, {})
                monthly_candle = monthly_ohlcv.get(month_key, {})
                
                enhanced_candle = {
                    "timestamp": timestamp,
                    "date": timestamp,
                    "dayOfWeek": get_day_of_week_name(timestamp),
                    "open": candle.get("open"),
                    "high": candle.get("high"),
                    "low": candle.get("low"),
                    "close": candle.get("close"),
                    "volume": candle.get("volume"),
                    # Always include weekly OHLCV
                    "weekly_open": weekly_candle.get("open"),
                    "weekly_high": weekly_candle.get("high"),
                    "weekly_low": weekly_candle.get("low"),
                    "weekly_close": weekly_candle.get("close"),
                    "weekly_volume": weekly_candle.get("volume"),
                    # Always include monthly OHLCV
                    "monthly_open": monthly_candle.get("open"),
                    "monthly_high": monthly_candle.get("high"),
                    "monthly_low": monthly_candle.get("low"),
                    "monthly_close": monthly_candle.get("close"),
                    "monthly_volume": monthly_candle.get("volume")
                }
                
                # Map pre-calculated indicator values
                for config in indicator_configs:
                    name = config["name"]
                    indicator_key = config["key"]
                    period = config["period"]
                    
                    if name == "pctchg":
                        # Calculate percentage change directly (simple calculation)
                        if idx >= period:
                            old_price = closes[idx - period]
                            current_price = closes[idx]
                            pct_change = ((current_price - old_price) / old_price) * 100 if old_price != 0 else 0
                            enhanced_candle[indicator_key] = pct_change
                        else:
                            enhanced_candle[indicator_key] = 0
                    elif name == "volume":
                        # Volume doesn't need calculation - it's already available as "volume" key
                        # Skip adding duplicate indicator_key since volume is already present
                        pass
                    elif name == "bb":
                        # Map Bollinger Bands values based on timeframe
                        timeframe = config["timeframe"]
                        if timeframe == "weekly":
                            # Find the index of this daily candle's weekly period
                            week_index = next((i for i, wc in enumerate(weekly_candles) if get_week_start_timestamp(timestamp) == sorted(weekly_ohlcv.keys())[i]), -1)
                            enhanced_candle[f"{indicator_key}_upper"] = calculated_indicators.get(f"{indicator_key}_upper", [])[week_index] if week_index >= 0 and week_index < len(calculated_indicators.get(f"{indicator_key}_upper", [])) else None
                            enhanced_candle[f"{indicator_key}_middle"] = calculated_indicators.get(f"{indicator_key}_middle", [])[week_index] if week_index >= 0 and week_index < len(calculated_indicators.get(f"{indicator_key}_middle", [])) else None
                            enhanced_candle[f"{indicator_key}_lower"] = calculated_indicators.get(f"{indicator_key}_lower", [])[week_index] if week_index >= 0 and week_index < len(calculated_indicators.get(f"{indicator_key}_lower", [])) else None
                        elif timeframe == "monthly":
                            # Find the index of this daily candle's monthly period
                            month_index = next((i for i, mc in enumerate(monthly_candles) if get_month_start_timestamp(timestamp) == sorted(monthly_ohlcv.keys())[i]), -1)
                            enhanced_candle[f"{indicator_key}_upper"] = calculated_indicators.get(f"{indicator_key}_upper", [])[month_index] if month_index >= 0 and month_index < len(calculated_indicators.get(f"{indicator_key}_upper", [])) else None
                            enhanced_candle[f"{indicator_key}_middle"] = calculated_indicators.get(f"{indicator_key}_middle", [])[month_index] if month_index >= 0 and month_index < len(calculated_indicators.get(f"{indicator_key}_middle", [])) else None
                            enhanced_candle[f"{indicator_key}_lower"] = calculated_indicators.get(f"{indicator_key}_lower", [])[month_index] if month_index >= 0 and month_index < len(calculated_indicators.get(f"{indicator_key}_lower", [])) else None
                        else:  # daily
                            enhanced_candle[f"{indicator_key}_upper"] = calculated_indicators.get(f"{indicator_key}_upper", [None] * len(stock_data))[idx]
                            enhanced_candle[f"{indicator_key}_middle"] = calculated_indicators.get(f"{indicator_key}_middle", [None] * len(stock_data))[idx]
                            enhanced_candle[f"{indicator_key}_lower"] = calculated_indicators.get(f"{indicator_key}_lower", [None] * len(stock_data))[idx]
                    else:
                        # Map other indicator values based on timeframe
                        timeframe = config["timeframe"]
                        if timeframe == "weekly":
                            # Find the index of this daily candle's weekly period
                            week_keys = sorted(weekly_ohlcv.keys())
                            week_key = get_week_start_timestamp(timestamp)
                            week_index = week_keys.index(week_key) if week_key in week_keys else -1
                            indicator_values = calculated_indicators.get(indicator_key, [])
                            enhanced_candle[indicator_key] = indicator_values[week_index] if week_index >= 0 and week_index < len(indicator_values) and indicator_values[week_index] is not None else (50.0 if name == "rsi" else candle.get("close", 0))
                        elif timeframe == "monthly":
                            # Find the index of this daily candle's monthly period
                            month_keys = sorted(monthly_ohlcv.keys())
                            month_key = get_month_start_timestamp(timestamp)
                            month_index = month_keys.index(month_key) if month_key in month_keys else -1
                            indicator_values = calculated_indicators.get(indicator_key, [])
                            enhanced_candle[indicator_key] = indicator_values[month_index] if month_index >= 0 and month_index < len(indicator_values) and indicator_values[month_index] is not None else (50.0 if name == "rsi" else candle.get("close", 0))
                        else:  # daily
                            indicator_values = calculated_indicators.get(indicator_key, [None] * len(stock_data))
                            enhanced_candle[indicator_key] = indicator_values[idx] if indicator_values[idx] is not None else (50.0 if name == "rsi" else candle.get("close", 0))
                
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
        precalc_dir = Path("../precalculatedStorage")
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
        current_time = datetime.utcnow()
        precalc_data = {
            "status": "completed",
            "indicators": indicators,
            "lastUpdated": current_time.isoformat(),
            "dayOfWeek": get_day_of_week_name(current_time.timestamp() * 1000)
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
                "dayOfWeek": get_day_of_week_name(candle.get("timestamp")),
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
        
        # Delete and recreate db directory in the python directory
        db_path = Path(__file__).parent / "db"
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
        constants_path = Path(__file__).parent / "stockSymbols.constants.js"
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
        
        # Delete and recreate db directory (same as refreshdb) in the python directory
        db_path = Path(__file__).parent / "db"
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

@app.get("/csv-upload-progress-stream")
async def csv_upload_progress_stream():
    """SSE endpoint for CSV upload progress updates."""
    async def generate():
        # Send initial connection message
        yield f"data: {json.dumps({'connected': True, 'endpoint': 'csv-upload-progress-stream'})}\n\n"
        
        while True:
            try:
                if not progress_queue.empty():
                    # Get update from queue with short timeout
                    update = await asyncio.get_event_loop().run_in_executor(
                        None, progress_queue.get, True, 0.1
                    )
                    if update:
                        # Format SSE message
                        yield f"data: {json.dumps(update)}\n\n"
                else:
                    # Send heartbeat to keep connection alive
                    yield f": heartbeat\n\n"
                
                # Small delay to prevent CPU spinning
                await asyncio.sleep(0.1)
                
            except queue.Empty:
                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"SSE CSV upload stream error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

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
    print(f"CSV Upload SSE: GET http://127.0.0.1:8001/csv-upload-progress-stream")
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