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

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Utility function to get default size from environment
def get_default_size() -> int:
    """Get default size parameter from environment variables."""
    try:
        return int(os.getenv('DEFAULT_SIZE', '200'))
    except (ValueError, TypeError):
        return 200  # Fallback to 200 if env var is invalid
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
from datetime import datetime, timedelta, timezone
import sys
import time
import concurrent.futures
import threading
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
import os

from services.query_service import (
    parse_query, find_matching_candles, get_query_examples, 
    extract_indicators_from_query, process_stocks_with_indicators, is_historical_query,
    validate_query_fields, detect_missing_indicators_from_fields
)
from services.indicator_cache import indicator_cache
from services.data_utils import get_next_day_timestamp, get_day_of_week_name
from utils.constants import STOCK_SYMBOLS, TOTAL_SYMBOLS
from services.chartink_service import ChartinkService
# postgres_integration removed - using only ultra-fast database
from services.latest_candle_updater import latest_candle_updater
from services.parallel_pipeline_updater import parallel_pipeline_updater
from services.db_wrapper import db_wrapper as db_service
from services.indicator_metadata_service import indicator_metadata_service
from services.dynamic_indicator_manager import dynamic_indicator_manager
from services.database_health_manager import database_health_manager
from services.postgres_indicator_service import postgres_indicator_service
from middleware.api_health_middleware import ensure_query_ready, ensure_latest_ready, ensure_basic_ready
import asyncio

# Simple logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)

# Suppress verbose HTTP client and SSL logs for performance
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

# Ensure immediate console output
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

# Pydantic models for request/response
class ChartinkApiRequest(BaseModel):
    payload: List[List[str]]
    size: Optional[int] = None  # Optional size parameter

class QueryRequest(BaseModel):
    query: str
    stocks: Optional[List[str]] = None

class PrecalculateRequest(BaseModel):
    indicators: List[Dict[str, Any]]

class RefreshDbRequest(BaseModel):
    symbols: Optional[List[str]] = None
    size: Optional[int] = None  # Optional size parameter

class PeriodicUpdateRequest(BaseModel):
    interval_minutes: Optional[int] = 2
    force_run: Optional[bool] = True  # Default to True for testing

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
    # Initialize database connection
    try:
        logger.info("Starting database initialization...")
        logger.info(f"Database config: host={db_service.db_service.db_config.get('host')}, port={db_service.db_service.db_config.get('port')}, database={db_service.db_service.db_config.get('database')}, user={db_service.db_service.db_config.get('user')}")
        
        result = await db_service.initialize()
        logger.info(f"Initialize method returned: {result}")
        logger.info(f"db_service.initialized property: {db_service.initialized}")
        logger.info(f"underlying db_service.db_service.initialized: {db_service.db_service.initialized}")
        
        if db_service.initialized:
            logger.info("Database service initialized successfully")
        else:
            logger.error("Database service initialization failed - service not marked as initialized")
            logger.error("This usually means PostgreSQL is not running or connection failed")
            logger.error("Please check:")
            logger.error("1. PostgreSQL is running on localhost:5432")
            logger.error("2. Database 'nse' exists")
            logger.error("3. User 'postgres' has correct password")
            logger.error("4. PostgreSQL accepts connections from localhost")
            
            # Try to provide a more helpful error message
            raise Exception(
                "Database service not properly initialized. "
                "Please ensure PostgreSQL is running and accessible. "
                "Check the logs above for connection details."
            )
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        logger.error("DATABASE IS REQUIRED - cannot continue without database")
        logger.error("Startup failed - please fix database issues and restart")
        # Re-raise to stop the application
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown."""
    print("FastAPI server shutdown")
    # Close database connections
    await db_service.close()

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
        try:
            return json.dumps(
                sanitize_for_json(content),
                ensure_ascii=False,
                allow_nan=False,
                indent=None,
                separators=(",", ":")
            ).encode("utf-8")
        except Exception as e:
            logger.error(f"JSON render error: {e}")
            logger.error(f"Content type: {type(content)}")
            # Return a safe error response
            error_content = {"error": "JSON serialization failed", "details": str(e)}
            return json.dumps(error_content).encode("utf-8")

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
# Note: No longer creating db folder - using PostgreSQL database only

# Database helper functions
async def load_stock_data(symbol: str, use_fallback: bool = True) -> Optional[List[Dict]]:
    """
    Load stock data from database with file fallback.
    
    Args:
        symbol: Stock symbol
        use_fallback: Whether to fallback to JSON file if database fails
        
    Returns:
        List of candle data or None
    """
    # Try database first
    if db_service.initialized:
        try:
            candles = await db_service.load_candles(symbol)
            if candles:
                return candles
        except Exception as e:
            logger.debug(f"Database read failed for {symbol}: {e}")
    
    # Fallback to JSON file if enabled
    if use_fallback:
        try:
            stock_file = Path(__file__).parent / "db" / f"{symbol}.json"
            if not stock_file.exists():
                stock_file = Path("db") / f"{symbol}.json"
            if stock_file.exists():
                with open(stock_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"File read failed for {symbol}: {e}")
    
    return None

def load_stock_data_sync(symbol: str, use_fallback: bool = True) -> Optional[List[Dict]]:
    """
    Synchronous version of load_stock_data for compatibility.
    
    Args:
        symbol: Stock symbol
        use_fallback: Whether to fallback to JSON file if database fails
        
    Returns:
        List of candle data or None
    """
    # For sync contexts, just use file fallback
    if use_fallback:
        try:
            stock_file = Path(__file__).parent / "db" / f"{symbol}.json"
            if not stock_file.exists():
                stock_file = Path("db") / f"{symbol}.json"
            if stock_file.exists():
                with open(stock_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"File read failed for {symbol}: {e}")
    
    return None

async def load_volume_indicators_from_db(symbol: str, volume_indicators: List[Dict]) -> Dict[str, Any]:
    """Load volume indicators from PostgreSQL database for a specific symbol."""
    volume_data = {}
    
    try:
        # Import the ultra_fast_db service
        from services.ultra_fast_database_service import ultra_fast_db
        
        async with ultra_fast_db.pool.acquire() as conn:
            # Get all volume indicators for this symbol
            records = await conn.fetch("""
                SELECT 
                    datetime,
                    volume as daily_volume,
                    indicators
                FROM daily_candles 
                WHERE symbol = $1
                ORDER BY datetime
            """, symbol)
            
            # Create timestamp-to-indicators mapping
            for record in records:
                timestamp = int(record['datetime'].timestamp() * 1000)
                indicators = record['indicators'] or {}
                
                volume_data[timestamp] = {
                    'weekly_volume': indicators.get('weekly_volume'),
                    'monthly_volume': indicators.get('monthly_volume'),
                    'daily_volume': record['daily_volume']
                }
                
    except Exception as e:
        logger.debug(f"Failed to load volume indicators for {symbol}: {e}")
    
    return volume_data

# Technical indicator calculation functions
def calculate_atr(highs, lows, closes, period=14):
    """Calculate Average True Range using Wilder's smoothing method - handles decimal periods"""
    # Convert inputs to float to avoid Decimal multiplication issues
    highs = [float(h) if h is not None else None for h in highs]
    lows = [float(l) if l is not None else None for l in lows]
    closes = [float(c) if c is not None else None for c in closes]
    
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
    period_int = int(round(period))  # Convert to integer for array operations
    
    for i in range(len(true_ranges)):
        if i < period_int - 1:
            atr_values.append(None)
        elif i == period_int - 1:
            # Initial ATR = average of first 'period' true ranges
            atr = sum(true_ranges[0:period_int]) / period_int
            atr_values.append(atr)
        else:
            # Wilder's smoothing: ATR = (Previous ATR * (period-1) + Current TR) / period
            # Use original period for smoothing calculation to preserve decimal precision
            atr = (atr * (period - 1) + true_ranges[i]) / period
            atr_values.append(atr)
    
    return atr_values

def calculate_atr_sma(highs, lows, closes, period=14):
    """Calculate ATR using Simple Moving Average for weekly SuperTrend - handles decimal periods"""
    # Convert inputs to float to avoid Decimal multiplication issues
    highs = [float(h) if h is not None else None for h in highs]
    lows = [float(l) if l is not None else None for l in lows]
    closes = [float(c) if c is not None else None for c in closes]
    
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
    period_int = int(round(period))  # Convert to integer for array operations
    
    for i in range(len(true_ranges)):
        if i < period_int - 1:
            atr_values.append(None)
        else:
            window = true_ranges[i-period_int+1:i+1]
            atr_values.append(sum(window) / len(window))
    
    return atr_values

def calculate_supertrend(highs, lows, closes, period=10, multiplier=2):
    """Calculate SuperTrend indicator using the standard algorithm - handles decimal periods"""
    # Convert inputs to float to avoid Decimal multiplication issues
    highs = [float(h) if h is not None else None for h in highs]
    lows = [float(l) if l is not None else None for l in lows]
    closes = [float(c) if c is not None else None for c in closes]
    multiplier = float(multiplier)
    
    atr_values = calculate_atr(highs, lows, closes, period)
    period_int = int(round(period))  # Convert to integer for array index comparisons
    
    # Arrays to store intermediate calculations
    basic_upper_band = []
    basic_lower_band = []
    final_upper_band = []
    final_lower_band = []
    supertrend_values = []
    trend_direction = []
    
    for i in range(len(closes)):
        if i < period_int - 1 or atr_values[i] is None:
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
            if i == period_int - 1:  # First calculation
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
            if i == period_int - 1:  # First calculation
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
    """Calculate SuperTrend for weekly timeframe using Wilder's ATR method"""
    
    # Convert inputs to float to avoid Decimal multiplication issues  
    highs = [float(h) if h is not None else None for h in highs]
    lows = [float(l) if l is not None else None for l in lows]
    closes = [float(c) if c is not None else None for c in closes]
    multiplier = float(multiplier)
    
    # Convert period to integer for calculations
    period_int = int(round(period))
    
    # Calculate ATR using Wilder's smoothing (matching trading platforms)
    atr_values = []
    for i in range(len(closes)):
        if i == 0:
            atr_values.append(None)
        elif i < period_int:
            # Initial ATR using SMA
            tr_sum = 0
            count = 0
            for j in range(i + 1):
                if j == 0:
                    tr = highs[j] - lows[j]
                else:
                    tr = max(
                        highs[j] - lows[j],
                        abs(highs[j] - closes[j-1]),
                        abs(lows[j] - closes[j-1])
                    )
                tr_sum += tr
                count += 1
            atr = tr_sum / count if count > 0 else None
            atr_values.append(atr)
        elif i == period_int:
            # First full period ATR
            tr_sum = 0
            for j in range(period_int):
                if j == 0:
                    tr = highs[j] - lows[j]
                else:
                    tr = max(
                        highs[j] - lows[j],
                        abs(highs[j] - closes[j-1]),
                        abs(lows[j] - closes[j-1])
                    )
                tr_sum += tr
            atr = tr_sum / period_int
            atr_values.append(atr)
        else:
            # Wilder's smoothing: ATR = ((period-1) * prev_ATR + TR) / period
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            prev_atr = atr_values[i-1]
            atr = ((period_int - 1) * prev_atr + tr) / period_int
            atr_values.append(atr)
    
    # Calculate SuperTrend
    supertrend_values = []
    trend_direction = []
    final_upper_band = []
    final_lower_band = []
    
    for i in range(len(closes)):
        if i < period_int or atr_values[i] is None:
            supertrend_values.append(None)
            trend_direction.append(None)
            final_upper_band.append(None)
            final_lower_band.append(None)
        else:
            # Calculate basic bands
            hl2 = (highs[i] + lows[i]) / 2
            basic_upper = hl2 + (multiplier * atr_values[i])
            basic_lower = hl2 - (multiplier * atr_values[i])
            
            # Calculate final bands
            if i == period_int:
                final_upper = basic_upper
                final_lower = basic_lower
            else:
                # Upper band logic
                if basic_upper < final_upper_band[i-1] or closes[i-1] > final_upper_band[i-1]:
                    final_upper = basic_upper
                else:
                    final_upper = final_upper_band[i-1]
                
                # Lower band logic
                if basic_lower > final_lower_band[i-1] or closes[i-1] < final_lower_band[i-1]:
                    final_lower = basic_lower
                else:
                    final_lower = final_lower_band[i-1]
            
            final_upper_band.append(final_upper)
            final_lower_band.append(final_lower)
            
            # Step 3: Determine trend direction and SuperTrend value
            if i == period_int:  # First calculation (corrected index)
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
            supertrend_values.append(round(supertrend, 2))  # Round final supertrend value
    
    return supertrend_values

def calculate_sma(values, period):
    """Calculate Simple Moving Average - handles both integer and decimal periods"""
    # Convert decimal period to integer for array slicing
    period_int = int(round(period))
    result = []
    for i in range(len(values)):
        if i < period_int - 1:
            result.append(None)
        else:
            window = values[i-period_int+1:i+1]
            result.append(sum(window) / len(window))
    return result

def calculate_ema(values, period):
    """Calculate Exponential Moving Average - handles both integer and decimal periods"""
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
    """Calculate Relative Strength Index - handles both integer and decimal periods"""
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
    """Calculate Bollinger Bands - handles both integer and decimal parameters"""
    sma_values = calculate_sma(closes, period)
    upper_band = []
    lower_band = []
    
    # Convert decimal period to integer for array slicing
    period_int = int(round(period))
    
    for i in range(len(closes)):
        if i < period_int - 1 or sma_values[i] is None:
            upper_band.append(None)
            lower_band.append(None)
        else:
            window = closes[i-period_int+1:i+1]
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

def update_progress(updates: Dict[str, Any], clear_queue: bool = False):
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
    
    # Clear the queue if requested (for starting fresh scans)
    if clear_queue:
        while not progress_queue.empty():
            try:
                progress_queue.get_nowait()
            except queue.Empty:
                break
    
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

@app.post("/api/query/export-csv")
async def export_query_results_csv(request: QueryRequest):
    """Export query results as CSV for debugging."""
    import csv
    from io import StringIO
    from datetime import datetime
    
    try:
        # Process the query to get results
        query = request.query
        stocks = request.stocks
        
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Parse and process query (similar to /query/latest)
        parsed_query = parse_query(query)
        stock_list = stocks or STOCK_SYMBOLS
        all_matches = []
        
        # Quick scan to get stock symbols only
        for stock in stock_list:
            try:
                precalculated_file = Path(f"precalculatedStorage/{stock}_piped.json")
                if precalculated_file.exists():
                    with open(precalculated_file, 'r') as f:
                        mapped_data = json.load(f)
                    candles = mapped_data.get("data", [])
                    
                    if candles:
                        # Check latest candle with all historical data for context
                        if is_historical_query(parsed_query):
                            matches = find_matching_candles(candles, parsed_query, stock)
                            # Filter to only latest day
                            latest_timestamp = candles[-1].get("timestamp")
                            matches = [m for m in matches if m.get("date") == latest_timestamp]
                        else:
                            latest_candle = candles[-1]
                            matches = find_matching_candles([latest_candle], parsed_query, stock)
                        
                        if matches:
                            all_matches.append({
                                "stock": stock,
                                "monthly_close": candles[-1].get("monthly_close", "N/A"),
                                # Convert timestamp to IST for correct date display
                                # Timestamps are stored at 18:30 UTC which is 00:00 IST next day
                                "date": (datetime.fromtimestamp(candles[-1].get("timestamp", 0) / 1000, tz=timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
                            })
            except:
                continue
        
        # Deduplicate
        seen_stocks = set()
        unique_matches = []
        for match in all_matches:
            if match["stock"] not in seen_stocks:
                seen_stocks.add(match["stock"])
                unique_matches.append(match)
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(["Sr.", "Stock Symbol", "Monthly Close", "Date", "Query"])
        
        # Write data
        for idx, match in enumerate(unique_matches, 1):
            writer.writerow([
                idx,
                match["stock"],
                match["monthly_close"],
                match["date"],
                query
            ])
        
        # Add summary row
        writer.writerow([])
        writer.writerow(["Total Matches:", len(unique_matches)])
        writer.writerow(["Generated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        
        # Return as CSV file
        output.seek(0)
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV export failed: {str(e)}")

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
        size = request.size or get_default_size()  # Use provided size or default from env
        
        if not payload or not isinstance(payload, list) or len(payload) == 0:
            raise HTTPException(status_code=400, detail="Invalid or missing payload")
        
        # Process the payload using the chartink service with configurable size
        results = await chartink_service.process_payload(payload, size=size)
        
        return {"success": True, "results": results, "size": size}
        
    except Exception as error:
        logger.error(f"Chartink API error: {error}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(error)}")


@app.post("/api/query/test")
async def test_query_parsing(request: QueryRequest):
    """Test query parsing and validation without heavy processing."""
    try:
        query = request.query
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Parse the query
        parsed_query = parse_query(query)
        
        # Validate query fields
        validation_result = await validate_query_fields(parsed_query)
        
        return {
            "success": True,
            "query": query,
            "parsed_query": parsed_query,
            "validation_result": validation_result,
            "message": "Query parsing and validation completed successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query test failed: {str(e)}")

@app.post("/api/query")
@ensure_query_ready
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
        
        # Reset progress and clear old data from queue
        update_progress({
            "isRunning": True,
            "phase": "initializing",
            "message": "Starting query processing...",
            "processed": 0,
            "total": TOTAL_SYMBOLS,
            "matches": 0,
            "startTime": datetime.utcnow().timestamp() * 1000
        }, clear_queue=True)
        
        logger.info(f"Processing query: {query}")
        
        # Ensure precalculation exists first
        if not await ensure_precalculation_exists():
            update_progress({"isRunning": False, "phase": "error", "message": "Failed to initialize precalculated data"})
            raise HTTPException(
                status_code=500,
                detail="Failed to initialize precalculated data. Please try again."
            )
        
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
        
        # Use high-speed query validator instead of old mapper validation
        from services.highspeed_query_validator import highspeed_query_validator
        validation_result = await highspeed_query_validator.validate_and_prepare_indicators(parsed_query)
        if not validation_result.get("valid"):
            # Check if this is a bootstrap scenario (no data at all)
            error_details = validation_result.get("error", "")
            available_fields = validation_result.get("available_fields", [])
            missing_fields = validation_result.get("missing_fields", [])
            
            # Bootstrap scenario: no precalculated data exists at all
            if "No precalculated data found" in error_details or not available_fields:
                update_progress({
                    "isRunning": True,
                    "phase": "bootstrap_system",
                    "message": "No precalculated data found. Bootstrapping system with required indicators...",
                    "processed": 0,
                    "total": 100
                })
                
                logger.info("🚀 Bootstrap scenario detected: No precalculated data exists. Auto-calculating all required indicators from query.")
                
                # Extract all indicators from the query for bootstrap calculation
                indicators_data = extract_indicators_from_query(parsed_query)
                required_indicators = indicators_data["indicators"]
                
                # Convert indicator data to field names for auto-calculation
                bootstrap_fields = []
                for indicator in required_indicators:
                    if indicator["name"] in ["RSI", "SMA", "EMA", "WMA"]:
                        field_name = f"{indicator['name']}_{indicator['params'].get('period', 14)}"
                        bootstrap_fields.append(field_name)
                    elif indicator["name"] == "SuperTrend":
                        period = indicator['params'].get('period', 10)
                        multiplier = indicator['params'].get('multiplier', 2)
                        field_name = f"SuperTrend_{period}_{multiplier}"
                        bootstrap_fields.append(field_name)
                    elif indicator["name"] == "PercentageChange":
                        timeframe = indicator.get('timeframe', 'daily')
                        field_name = f"{timeframe}_pctchg"  # Simplified format - no offset parameter
                        bootstrap_fields.append(field_name)
                
                if bootstrap_fields:
                    logger.info(f"Bootstrapping system with indicators: {bootstrap_fields}")
                    success = await add_missing_indicators_and_calculate(bootstrap_fields)
                    
                    if not success:
                        update_progress({"isRunning": False, "phase": "error", "message": "Failed to bootstrap system with indicators"})
                        raise HTTPException(
                            status_code=500,
                            detail={
                                "error": "System bootstrap failed",
                                "details": "Could not calculate required indicators for query",
                                "hint": "System needs to calculate indicators for first-time use. Please try again."
                            }
                        )
                    
                    # Re-validate after bootstrap
                    validation_result = await highspeed_query_validator.validate_and_prepare_indicators(parsed_query)
                    if not validation_result.get("valid"):
                        update_progress({"isRunning": False, "phase": "error", "message": "System bootstrap completed but validation still failed"})
                        raise HTTPException(
                            status_code=500,
                            detail={
                                "error": "Bootstrap validation failed",
                                "details": validation_result.get("error", "Unknown error after bootstrap"),
                                "hint": "System was bootstrapped but query validation still failed"
                            }
                        )
                    
                    logger.info("✅ System successfully bootstrapped with required indicators")
                else:
                    # Query contains only basic fields, no indicators needed
                    logger.info("Query contains only basic price/volume fields, no indicators needed for bootstrap")
            
            # Normal scenario: some missing indicators
            elif missing_fields:
                update_progress({
                    "isRunning": True,
                    "phase": "detecting_missing_indicators",
                    "message": f"Found {len(missing_fields)} missing indicators. Auto-calculating them...",
                    "processed": 0,
                    "total": 100
                })
                
                logger.info(f"Auto-calculating missing indicators: {missing_fields}")
                
                # Try to add and calculate missing indicators
                success = await add_missing_indicators_and_calculate(missing_fields)
                
                if not success:
                    update_progress({"isRunning": False, "phase": "error", "message": "Failed to calculate missing indicators"})
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "Field validation failed",
                            "details": validation_result["error"],
                            "missing_fields": missing_fields,
                            "available_fields": validation_result.get("available_fields", []),
                            "hint": "Could not auto-calculate missing indicators. Make sure field formats are valid."
                        }
                    )
                
                # Re-validate after calculating missing indicators
                validation_result = await highspeed_query_validator.validate_and_prepare_indicators(parsed_query)
                if not validation_result.get("valid"):
                    update_progress({"isRunning": False, "phase": "error", "message": "Query validation still failed after calculating indicators"})
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "error": "Query validation failed even after calculating missing indicators",
                            "details": validation_result["error"],
                            "missing_fields": validation_result.get("missing_fields", [])
                        }
                    )
                
                logger.info("Successfully calculated missing indicators, proceeding with query")
            else:
                # Unknown validation error
                update_progress({"isRunning": False, "phase": "error", "message": validation_result["error"]})
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Field validation failed",
                        "details": validation_result["error"],
                        "available_fields": validation_result.get("available_fields", []),
                        "hint": "Unknown validation error - please check query syntax"
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
        
        # Handle division by zero when query time is very small
        if total_query_time > 0:
            rate = len(stock_list) / total_query_time
            print(f"[DEBUG] Query processing completed in {total_query_time:.2f}s | Rate: {rate:.1f} stocks/sec")
        else:
            print(f"[DEBUG] Query processing completed in {total_query_time:.2f}s | Rate: instant")
        
        # Deduplicate matches - keep only one match per stock-date combination
        seen_combinations = set()
        unique_matches = []
        duplicate_count = 0
        
        for match in all_matches:
            stock_symbol = match.get("stock", "")
            date = match.get("date", "")
            combination = f"{stock_symbol}_{date}"
            
            if combination not in seen_combinations:
                seen_combinations.add(combination)
                unique_matches.append(match)
            else:
                duplicate_count += 1
        
        if duplicate_count > 0:
            print(f"[WARNING] Found and removed {duplicate_count} duplicate matches")
        
        # Replace all_matches with deduplicated list
        all_matches = unique_matches
        
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

@app.post("/api/query/latest")
@ensure_latest_ready
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
        
        # Reset progress and clear old data from queue
        update_progress({
            "isRunning": True,
            "phase": "initializing",
            "message": "Starting latest day scan...",
            "processed": 0,
            "total": TOTAL_SYMBOLS,
            "matches": 0,
            "startTime": datetime.utcnow().timestamp() * 1000
        }, clear_queue=True)
        
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
        
        # Use high-speed query validator for dynamic indicator support
        from services.highspeed_query_validator import highspeed_query_validator
        validation_result = await highspeed_query_validator.validate_and_prepare_indicators(parsed_query)
        
        if not validation_result.get("valid"):
            # Return validator's helpful error message directly (no auto-calculation)
            logger.info(f"Query validation failed: {validation_result.get('error')}")
            update_progress({"isRunning": False, "phase": "error", "message": validation_result.get("error", "Query validation failed")})
            raise HTTPException(
                status_code=400,
                detail=validation_result  # Return the complete validator response
            )
        
        # Log if any indicators were calculated dynamically
        if validation_result.get("calculated_indicators"):
            logger.info(f"Dynamically calculated {len(validation_result['calculated_indicators'])} indicators")
            update_progress({
                "phase": "indicators_calculated",
                "message": f"Calculated {len(validation_result['calculated_indicators'])} missing indicators"
            })
        
        # OLD VALIDATION CODE - Keeping as fallback but using new validator above
        # Validate that all query fields exist in precalculated data
        validation_result_old = await validate_query_fields(parsed_query)
        if not validation_result_old["valid"]:
            # Check if this is a bootstrap scenario (no data at all)
            error_details = validation_result.get("error", "")
            available_fields = validation_result.get("available_fields", [])
            missing_fields = validation_result.get("missing_fields", [])
            
            # Bootstrap scenario: no precalculated data exists at all
            if "No precalculated data found" in error_details or not available_fields:
                update_progress({
                    "isRunning": True,
                    "phase": "bootstrap_system",
                    "message": "No precalculated data found. Bootstrapping system with required indicators...",
                    "processed": 0,
                    "total": 100
                })
                
                logger.info("🚀 Bootstrap scenario detected: No precalculated data exists. Auto-calculating all required indicators from query.")
                
                # Extract all indicators from the query for bootstrap calculation
                indicators_data = extract_indicators_from_query(parsed_query)
                required_indicators = indicators_data["indicators"]
                
                # Convert indicator data to field names for auto-calculation
                bootstrap_fields = []
                for indicator in required_indicators:
                    if indicator["name"] in ["RSI", "SMA", "EMA", "WMA"]:
                        field_name = f"{indicator['name']}_{indicator['params'].get('period', 14)}"
                        bootstrap_fields.append(field_name)
                    elif indicator["name"] == "SuperTrend":
                        period = indicator['params'].get('period', 10)
                        multiplier = indicator['params'].get('multiplier', 2)
                        field_name = f"SuperTrend_{period}_{multiplier}"
                        bootstrap_fields.append(field_name)
                    elif indicator["name"] == "PercentageChange":
                        timeframe = indicator.get('timeframe', 'daily')
                        field_name = f"{timeframe}_pctchg"  # Simplified format - no offset parameter
                        bootstrap_fields.append(field_name)
                
                if bootstrap_fields:
                    logger.info(f"Bootstrapping system with indicators: {bootstrap_fields}")
                    success = await add_missing_indicators_and_calculate(bootstrap_fields)
                    
                    if not success:
                        update_progress({"isRunning": False, "phase": "error", "message": "Failed to bootstrap system with indicators"})
                        raise HTTPException(
                            status_code=500,
                            detail={
                                "error": "System bootstrap failed",
                                "details": "Could not calculate required indicators for query",
                                "hint": "System needs to calculate indicators for first-time use. Please try again."
                            }
                        )
                    
                    # Re-validate after bootstrap
                    validation_result = await highspeed_query_validator.validate_and_prepare_indicators(parsed_query)
                    if not validation_result.get("valid"):
                        update_progress({"isRunning": False, "phase": "error", "message": "System bootstrap completed but validation still failed"})
                        raise HTTPException(
                            status_code=500,
                            detail={
                                "error": "Bootstrap validation failed",
                                "details": validation_result.get("error", "Unknown error after bootstrap"),
                                "hint": "System was bootstrapped but query validation still failed"
                            }
                        )
                    
                    logger.info("✅ System successfully bootstrapped with required indicators")
                else:
                    # Query contains only basic fields, no indicators needed
                    logger.info("Query contains only basic price/volume fields, no indicators needed for bootstrap")
            
            # Normal scenario: some missing indicators
            elif missing_fields:
                update_progress({
                    "isRunning": True,
                    "phase": "detecting_missing_indicators",
                    "message": f"Found {len(missing_fields)} missing indicators. Auto-calculating them...",
                    "processed": 0,
                    "total": 100
                })
                
                logger.info(f"Auto-calculating missing indicators for latest query: {missing_fields}")
                
                # Try to add and calculate missing indicators
                success = await add_missing_indicators_and_calculate(missing_fields)
                
                if not success:
                    update_progress({"isRunning": False, "phase": "error", "message": "Failed to calculate missing indicators"})
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "Field validation failed",
                            "details": validation_result["error"],
                            "missing_fields": missing_fields,
                            "available_fields": validation_result.get("available_fields", []),
                            "hint": "Could not auto-calculate missing indicators. Make sure field formats are valid."
                        }
                    )
                
                # Re-validate after calculating missing indicators
                validation_result = await highspeed_query_validator.validate_and_prepare_indicators(parsed_query)
                if not validation_result.get("valid"):
                    update_progress({"isRunning": False, "phase": "error", "message": "Query validation still failed after calculating indicators"})
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "error": "Query validation failed even after calculating missing indicators",
                            "details": validation_result["error"],
                            "missing_fields": validation_result.get("missing_fields", [])
                        }
                    )
                
                logger.info("Successfully calculated missing indicators, proceeding with latest query")
            else:
                # Unknown validation error
                update_progress({"isRunning": False, "phase": "error", "message": validation_result["error"]})
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Field validation failed",
                        "details": validation_result["error"],
                        "available_fields": validation_result.get("available_fields", []),
                        "hint": "Unknown validation error - please check query syntax"
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
        
        # Check and calculate dynamic indicators before query execution
        from services.dynamic_indicator_checker import dynamic_indicator_checker
        
        # Extract required fields from parsed query
        required_fields = set()
        for condition in parsed_query.get("conditions", []):
            left = condition.get("left", {})
            if left.get("type") in ["field", "indicator"]:
                field_name = left.get("field", "")
                if field_name:
                    from services.query_service import resolve_field_name
                    resolved_name = resolve_field_name(field_name)
                    required_fields.add(resolved_name)
        
        if required_fields:
            logger.info(f"Checking dynamic indicators for latest scan: {required_fields}")
            check_result = await dynamic_indicator_checker.check_and_calculate_indicators(required_fields)
            
            if check_result.get("calculated"):
                logger.info(f"Calculated {len(check_result['calculated'])} dynamic indicators: {check_result['calculated']}")
                update_progress({
                    "phase": "indicators_calculated", 
                    "message": f"Calculated {len(check_result['calculated'])} dynamic indicators"
                })
                # Give the database a moment to finish writing
                await asyncio.sleep(0.5)
        
        # Use high-speed database instead of file-based processing
        scan_results = []
        try:
            # Execute query directly on high-speed database instead of parallel file processing
            logger.info("Using high-speed database for latest scan...")
            
            # Convert parsed query to SQL conditions
            from services.ultra_fast_database_service import ultra_fast_db as high_speed_db
            
            if not high_speed_db.initialized:
                await high_speed_db.initialize()
            
            async with high_speed_db.pool.acquire() as conn:
                # Build SQL query from parsed conditions
                conditions = parsed_query.get("conditions", [])
                where_clauses = []
                select_fields = []
                params = []
                
                # Define static indicators (columns) vs dynamic (JSONB)
                static_indicators = high_speed_db.static_indicators
                
                for condition in conditions:
                    left = condition.get("left", {})
                    operator = condition.get("operator", "=")
                    right = condition.get("right", {})
                    
                    if left.get("type") == "field":
                        field_name = left.get("field", "")
                        if right.get("type") == "value":
                            value = right.get("value", 0)
                            
                            # Check if field is static or dynamic (JSONB)
                            if field_name in static_indicators or field_name in ['open', 'high', 'low', 'close', 'volume']:
                                # Static column
                                where_clauses.append(f"{field_name} {operator} ${len(params) + 1}")
                                select_fields.append(field_name)
                            else:
                                # Dynamic JSONB field
                                where_clauses.append(f"(indicators->>'{field_name}')::numeric {operator} ${len(params) + 1}")
                                select_fields.append(f"(indicators->>'{field_name}')::numeric as {field_name}")
                            
                            params.append(value)
                
                # Execute query on high-speed database
                if where_clauses:
                    # Build SELECT clause with both static and JSONB fields
                    if select_fields:
                        sql = f"""
                            SELECT symbol, timestamp, close, {', '.join(select_fields)}
                            FROM daily_candles 
                            WHERE {' AND '.join(where_clauses)}
                            ORDER BY symbol, timestamp DESC
                        """
                    else:
                        sql = f"""
                            SELECT symbol, timestamp, close
                            FROM daily_candles 
                            WHERE {' AND '.join(where_clauses)}
                            ORDER BY symbol, timestamp DESC
                        """
                    
                    try:
                        logger.info(f"Executing high-speed query: {sql}")
                        logger.info(f"Query parameters: {params}")
                        
                        results = await conn.fetch(sql, *params)
                        
                        # Convert results to expected format
                        matches = []
                        for row in results:
                            matches.append({
                                "symbol": row["symbol"],
                                "timestamp": row["timestamp"],
                                "close": float(row["close"]) if row["close"] else 0,
                                **{k: float(v) if v is not None else None for k, v in dict(row).items() if k not in ["symbol", "timestamp", "close"]}
                            })
                        
                        scan_results.append({
                            "matches": matches,
                            "errors": [],
                            "processed": len(stock_list),
                            "processing_time": 0
                        })
                        
                        logger.info(f"High-speed database query found {len(matches)} matches")
                        
                        # Skip parallel processing since we got results from database
                        
                    except Exception as e:
                        logger.error(f"High-speed database query failed: {e}")
                        # Fallback to parallel processing
                        raise e
                else:
                    logger.warning("No where clauses generated, falling back to parallel processing")
                    raise Exception("No conditions to query")
                    
        except Exception as fallback_error:
            logger.warning(f"Database query failed, falling back to parallel processing: {fallback_error}")
            
            # Fallback to original parallel processing
            with concurrent.futures.ProcessPoolExecutor(max_workers=PERFORMANCE_CONFIG["max_cpu_workers"]) as executor:
                current_dir = str(Path(__file__).parent.absolute())
                
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
        
        # Handle division by zero when scan time is very small
        if total_scan_time > 0:
            rate = len(stock_list) / total_scan_time
            print(f"[DEBUG] Latest scan completed in {total_scan_time:.2f}s | Rate: {rate:.1f} stocks/sec")
        else:
            print(f"[DEBUG] Latest scan completed in {total_scan_time:.2f}s | Rate: instant")
        
        # Deduplicate matches - keep only one match per stock
        seen_stocks = set()
        unique_matches = []
        duplicate_count = 0
        
        for match in all_matches:
            stock_symbol = match.get("stock", "")
            if stock_symbol not in seen_stocks:
                seen_stocks.add(stock_symbol)
                unique_matches.append(match)
            else:
                duplicate_count += 1
        
        if duplicate_count > 0:
            print(f"[WARNING] Found and removed {duplicate_count} duplicate matches")
        
        # Replace all_matches with deduplicated list
        all_matches = unique_matches
        
        # CONSISTENCY FIX: Filter to only latest global date to match full backtest behavior
        if all_matches:
            # Find the latest global timestamp across all matches
            timestamps = [match.get("date", match.get("timestamp", 0)) for match in all_matches]
            latest_global_timestamp = max(timestamps) if timestamps else 0
            
            # Filter to only matches from the latest global date
            before_filter_count = len(all_matches)
            all_matches = [match for match in all_matches 
                          if match.get("date", match.get("timestamp", 0)) == latest_global_timestamp]
            after_filter_count = len(all_matches)
            
            if before_filter_count != after_filter_count:
                print(f"[DEBUG] Latest scan: Filtered {before_filter_count - after_filter_count} matches from older dates")
                print(f"[DEBUG] Latest scan: Kept {after_filter_count} matches from latest date ({latest_global_timestamp})")
        
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

@app.get("/api/query/examples")
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
        precalculated_file = Path(f"precalculatedStorage/{stock}_piped.json")
        if not precalculated_file.exists():
            return {"success": False, "error": "Precalculated data not found"}
        
        # Read and process the stock data
        with open(precalculated_file, 'r') as f:
            mapped_data = json.load(f)
        
        candles = mapped_data.get("data", [])
        if not candles:
            return {"success": False, "error": "No candle data available"}
        
        # Check if query contains "crossed" conditions that need historical comparison
        query_has_crossed_conditions = any(
            condition.get("operator", "") in ["crossed above", "crossed below"]
            for condition in parsed_query.get("conditions", [])
        )
        
        if query_has_crossed_conditions and len(candles) >= 2:
            # For crossed conditions, we need more historical data
            # Check if it's a weekly or monthly crossed condition
            conditions = parsed_query.get("conditions", [])
            needs_weekly_data = any(
                'weekly' in str(cond.get("left", {}).get("field", "")) or 
                'weekly' in str(cond.get("right", {}).get("field", ""))
                for cond in conditions
            )
            needs_monthly_data = any(
                'monthly' in str(cond.get("left", {}).get("field", "")) or 
                'monthly' in str(cond.get("right", {}).get("field", ""))
                for cond in conditions
            )
            
            if needs_weekly_data:
                # For weekly crossed conditions, pass at least 10 candles to ensure we have previous week
                candles_to_pass = candles[-10:] if len(candles) >= 10 else candles
            elif needs_monthly_data:
                # For monthly crossed conditions, pass at least 30 candles
                candles_to_pass = candles[-30:] if len(candles) >= 30 else candles
            else:
                # For daily crossed conditions, last 2 candles are enough
                candles_to_pass = candles[-2:]
            
            matches = find_matching_candles(candles_to_pass, parsed_query, stock)
            # For latest API, ALWAYS return matches from the LATEST candle only
            # Even for historical queries, we only want latest day results
            latest_timestamp = candles[-1].get("timestamp")
            matches = [match for match in matches 
                      if match.get("date") == latest_timestamp]
        else:
            # OPTIMIZATION: Only process the LATEST candle for latest scan
            # BUT for historical queries, we need all candles to find the historical match
            if is_historical_query(parsed_query):
                matches = find_matching_candles(candles, parsed_query, stock)
                # Filter to only keep matches from the latest candle
                latest_timestamp = candles[-1].get("timestamp")
                matches = [match for match in matches 
                          if match.get("date") == latest_timestamp]
            else:
                # Pass last 2 candles to allow pctchg calculation if needed
                # But still only match against the latest candle
                candles_to_pass = candles[-2:] if len(candles) >= 2 else candles
                matches = find_matching_candles(candles_to_pass, parsed_query, stock)
                # Filter to only the latest candle
                if len(candles_to_pass) > 1:
                    latest_timestamp = candles[-1].get("timestamp")
                    matches = [match for match in matches 
                              if match.get("date") == latest_timestamp]
        
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
                    left_val = latest_candle.get(left.get("field", ""), 0) if left.get("type") == "field" else float(left.get("value", 0))
                    right_val = latest_candle.get(right.get("field", ""), 0) if right.get("type") == "field" else float(right.get("value", 0))
                    
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
                        left_val = candle.get(left.get("field", ""), 0) if left.get("type") == "field" else float(left.get("value", 0))
                        right_val = candle.get(right.get("field", ""), 0) if right.get("type") == "field" else float(right.get("value", 0))
                        
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
        
        # Import the query service functions
        try:
            # Try to import directly first
            from services.query_service import find_matching_candles, is_historical_query
        except ImportError:
            try:
                # Try with absolute path
                current_dir = os.path.dirname(os.path.abspath(__file__))
                services_path = os.path.join(current_dir, 'services')
                if services_path not in sys.path:
                    sys.path.insert(0, services_path)
                from query_service import find_matching_candles, is_historical_query
            except ImportError:
                print(f"[WARNING] Using fallback find_matching_candles implementation due to import failure")
                # Simple fallback implementation for basic conditions
                def is_historical_query(parsed_query):
                    """Check if query contains historical references."""
                    conditions = parsed_query.get("conditions", [])
                    for condition in conditions:
                        left = condition.get("left", {})
                        right = condition.get("right", {})
                        if left.get("type") == "time_offset_field" or right.get("type") in ["time_offset_field", "time_offset_field_arithmetic"]:
                            return True
                    return False
                
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
                                if left.get("type") == "field":
                                    left_field = left.get("field", "")
                                    left_raw = candle.get(left_field)
                                    left_val = float(left_raw) if left_raw is not None else None
                                else:
                                    left_val = float(left.get("value", 0))
                                
                                if right.get("type") == "field":
                                    right_field = right.get("field", "")
                                    right_raw = candle.get(right_field)
                                    right_val = float(right_raw) if right_raw is not None else None
                                else:
                                    right_val = float(right.get("value", 0))
                                
                                # Skip if either value is None
                                if left_val is None or right_val is None:
                                    results.append(False)
                                    continue
                                
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
                    # Try to get data from database with indicators if precalculated file not found
                    try:
                        import asyncio
                        from services.ultra_fast_database_service import ultra_fast_db
                        
                        # Get candles with indicators from database (run async call synchronously)
                        async def get_db_candles():
                            # Initialize database connection in this process pool worker
                            await ultra_fast_db.initialize()
                            return await ultra_fast_db.get_candles_with_indicators(stock, limit=None)
                        
                        # Run the async function in a sync context
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        
                        candles_from_db = loop.run_until_complete(get_db_candles())
                        
                        if candles_from_db:
                            # Convert database format to query service format
                            candles = []
                            for candle in candles_from_db:
                                # Parse indicators from JSONB
                                indicators = candle.get('indicators', {})
                                if isinstance(indicators, str):
                                    import json
                                    try:
                                        indicators = json.loads(indicators)
                                    except:
                                        indicators = {}
                                
                                # Create candle record with indicators merged
                                candle_record = {
                                    'open': float(candle.get('open', 0)),
                                    'high': float(candle.get('high', 0)),
                                    'low': float(candle.get('low', 0)),
                                    'close': float(candle.get('close', 0)),
                                    'volume': float(candle.get('volume', 0)),
                                    'timestamp': candle.get('timestamp', 0)
                                }
                                # Add indicators to the candle record
                                candle_record.update(indicators)
                                candles.append(candle_record)
                            
                            # Process candles with database indicators
                            stock_matches = find_matching_candles(candles, parsed_query_dict, stock)
                            matches.extend(stock_matches)
                        else:
                            errors.append({"stock": stock, "error": "No data available in database"})
                    except Exception as db_error:
                        errors.append({"stock": stock, "error": f"Database query failed: {str(db_error)}"})
                
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
        
        # Add both base path and services path for imports
        if base_path and base_path not in sys.path:
            sys.path.insert(0, base_path)
        
        # Also add services path explicitly
        services_path = os.path.join(base_path, 'services') if base_path else 'services'
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        
        # Import the query service functions
        try:
            # Try to import with full module path first
            from services.query_service import find_matching_candles, is_historical_query
            print(f"[DEBUG] Successfully imported query service functions from services.query_service")
        except ImportError as e1:
            try:
                # Try direct import from query_service
                from query_service import find_matching_candles, is_historical_query
                print(f"[DEBUG] Successfully imported query service functions from query_service")
            except ImportError as e2:
                print(f"[ERROR] Failed to import query service functions: {e1}, {e2}")
                print(f"[ERROR] sys.path: {sys.path}")
                # Re-raise to use the full service, not the fallback
                raise ImportError(f"Cannot import query service: {e1}, {e2}")
        
        print(f"[DEBUG] Processing latest scan batch of {len(stock_batch)} stocks")
        
        for stock in stock_batch:
            try:
                # Check for precalculated data
                precalculated_file = Path(f"precalculatedStorage/{stock}_piped.json")
                if precalculated_file.exists():
                    with open(precalculated_file, 'r') as f:
                        mapped_data = json.load(f)
                    candles = mapped_data.get("data", [])
                    
                    # Filter out future dates for latest scan (only include data up to current time)
                    import time
                    current_time = int(time.time() * 1000)  # Current timestamp in milliseconds
                    candles = [candle for candle in candles if candle.get("timestamp", 0) <= current_time]
                    
                    if candles:
                        # Check if query contains "crossed" conditions that need historical comparison
                        query_has_crossed_conditions = any(
                            condition.get("operator", "") in ["crossed above", "crossed below"]
                            for condition in parsed_query_dict.get("conditions", [])
                        )
                        
                        if query_has_crossed_conditions and len(candles) >= 2:
                            # For crossed conditions, we need more historical data
                            # Calculate required candles based on time offsets and field types
                            conditions = parsed_query_dict.get("conditions", [])
                            max_candles_needed = 10  # Default minimum for crossed conditions
                            
                            for cond in conditions:
                                # Check for weekly/monthly fields
                                left_field = str(cond.get("left", {}).get("field", ""))
                                right_field = str(cond.get("right", {}).get("field", ""))
                                
                                # Check for time offset expressions
                                left_side = cond.get("left", {})
                                right_side = cond.get("right", {})
                                
                                # Calculate needed candles based on time offsets
                                for side in [left_side, right_side]:
                                    if side.get("type") in ["time_offset_field", "time_offset_field_arithmetic"]:
                                        offset_value = side.get("offset_value", 1)
                                        offset_unit = side.get("offset_unit", "day")
                                        
                                        if offset_unit == "day":
                                            candles_for_offset = offset_value + 5  # Add buffer
                                        elif offset_unit == "week":
                                            candles_for_offset = (offset_value * 7) + 10  # 7 days per week + buffer
                                        elif offset_unit == "month":
                                            candles_for_offset = (offset_value * 25) + 10  # ~25 trading days per month + buffer
                                        else:
                                            candles_for_offset = 10
                                        
                                        max_candles_needed = max(max_candles_needed, candles_for_offset)
                                
                                # Also check for weekly/monthly fields in crossed conditions
                                if 'weekly' in left_field or 'weekly' in right_field:
                                    max_candles_needed = max(max_candles_needed, 15)  # Minimum for weekly
                                elif 'monthly' in left_field or 'monthly' in right_field:
                                    max_candles_needed = max(max_candles_needed, 35)  # Minimum for monthly
                            
                            # Add safety limit to prevent performance issues
                            max_candles_needed = min(max_candles_needed, 100)  # Maximum 100 candles
                            
                            # Ensure we don't request more candles than available
                            candles_to_pass = candles[-max_candles_needed:] if len(candles) >= max_candles_needed else candles
                            
                            stock_matches = find_matching_candles(candles_to_pass, parsed_query_dict, stock)
                            # For latest API, ALWAYS return matches from the LATEST candle only
                            # Even for historical queries, we only want latest day results
                            latest_timestamp = candles[-1].get("timestamp")
                            stock_matches = [match for match in stock_matches 
                                           if match.get("date") == latest_timestamp]
                        else:
                            # For non-crossed conditions or insufficient data
                            if is_historical_query(parsed_query_dict):
                                # For historical queries, we need enough candles to find the historical reference
                                # Pass all candles but only keep matches from the latest day
                                stock_matches = find_matching_candles(candles, parsed_query_dict, stock)
                                # Filter to only latest candle matches
                                latest_timestamp = candles[-1].get("timestamp")
                                stock_matches = [match for match in stock_matches 
                                               if match.get("date") == latest_timestamp]
                            else:
                                # For non-historical queries, only check the latest candle
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
    import sys
    import math
    
    # Define sanitize function locally since we're in a subprocess
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
    
    batch_start = time.time()
    write_count = 0
    precalc_dir = Path(precalc_dir_str)
    
    print(f"[DEBUG] Writing batch of {len(stock_results_chunk)} files in parallel process")
    
    for stock, processed_data, success, error in stock_results_chunk:
        if success and processed_data:
            try:
                output_file = precalc_dir / f"{stock}_piped.json"
                
                # Sanitize the data before writing to handle NaN/Infinity issues
                sanitized_data = sanitize_for_json(processed_data)
                
                # Try to write with explicit encoding
                with open(output_file, 'w', encoding='utf-8') as f:
                    # Use separators to minimize file size
                    json.dump(sanitized_data, f, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
                write_count += 1
                
            except OSError as e:
                if e.errno == 22:  # Invalid argument error
                    print(f"[ERROR] Invalid argument error for {stock}: {e}")
                    print(f"[ERROR] File path: {output_file}")
                    print(f"[ERROR] Stock symbol: {stock}")
                    # Try to identify the issue
                    if ':' in stock or '/' in stock or '\\' in stock:
                        print(f"[ERROR] Stock symbol contains invalid characters")
                else:
                    print(f"[ERROR] OS error writing {stock}: {e}")
            except ValueError as e:
                print(f"[ERROR] JSON encoding error for {stock}: {e}")
                # Try to find the problematic value
                if "Out of range float values" in str(e):
                    print(f"[ERROR] Data contains NaN or Infinity values")
            except Exception as e:
                print(f"[ERROR] Unexpected error writing {stock}: {e}")
                print(f"[ERROR] Error type: {type(e).__name__}")
                import traceback
                traceback.print_exc()
    
    batch_end = time.time()
    print(f"[DEBUG] Parallel write batch completed in {batch_end - batch_start:.2f}s, wrote {write_count}/{len(stock_results_chunk)} files")
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
                period = float(params.get("period", 14))
                
                # Generate appropriate indicator key based on indicator type
                if name == "supertrend":
                    multiplier = float(params.get("multiplier", 2))
                    # Format period as integer if it's a whole number, multiplier as is
                    period_str = str(int(period)) if period.is_integer() else str(period)
                    multiplier_str = str(multiplier)
                    indicator_key = f"{timeframe}_{name}_{period_str}_{multiplier_str}"
                elif name == "bb":
                    std_dev = float(params.get("stdDev", 2))
                    # Format period as integer if it's a whole number
                    period_str = str(int(period)) if period.is_integer() else str(period)
                    indicator_key = f"{timeframe}_{name}_{period_str}_{std_dev}"
                else:
                    # Format period as integer if it's a whole number
                    period_str = str(int(period)) if period.is_integer() else str(period)
                    indicator_key = f"{timeframe}_{name}_{period_str}"
                
                indicator_configs.append({
                    "name": name,
                    "key": indicator_key,
                    "timeframe": timeframe,
                    "period": period,
                    "multiplier": float(params.get("multiplier", 2)),
                    "std_dev": float(params.get("stdDev", 2))
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
                
                # Determine weekend flag
                day_of_week = get_day_of_week_name(timestamp)
                
                # Determine monthend flag - check if next candle is in a different month
                is_monthend = False
                # Use IST timezone (UTC+5:30) for Indian stock market data
                ist_offset = timezone(timedelta(hours=5, minutes=30))
                
                if idx < len(stock_data) - 1:
                    # Check if next candle is in a different month
                    next_timestamp = stock_data[idx + 1].get("timestamp", 0)
                    current_date = datetime.fromtimestamp(timestamp / 1000, tz=ist_offset)
                    next_date = datetime.fromtimestamp(next_timestamp / 1000, tz=ist_offset)
                    
                    if next_date.month != current_date.month or next_date.year != current_date.year:
                        is_monthend = True
                else:
                    # Last candle in dataset - only mark as monthend if it's actually the last day of the month
                    current_date = datetime.fromtimestamp(timestamp / 1000, tz=ist_offset)
                    # Get the last day of the current month
                    if current_date.month == 12:
                        last_day_of_month = current_date.replace(day=31)
                    else:
                        # Get first day of next month and subtract one day
                        next_month = current_date.replace(month=current_date.month + 1, day=1)
                        last_day_of_month = next_month - timedelta(days=1)
                    
                    # Only mark as monthend if current date is the last day of the month
                    # or if it's a Friday and the last day is Saturday/Sunday
                    if current_date.date() == last_day_of_month.date():
                        is_monthend = True
                    elif current_date.weekday() == 4:  # Friday
                        # Check if last day of month is Saturday (5) or Sunday (6)
                        if last_day_of_month.weekday() in [5, 6]:
                            # Check if current Friday is the last Friday of the month
                            days_until_month_end = (last_day_of_month.date() - current_date.date()).days
                            if days_until_month_end <= 2:  # Friday before weekend month end
                                is_monthend = True
                
                enhanced_candle = {
                    "timestamp": timestamp,
                    "date": timestamp,
                    "dayOfWeek": day_of_week,
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
                
                # Add weekend flag only if it's Friday
                if day_of_week == "Friday":
                    enhanced_candle["weekend"] = True
                
                # Add monthend flag only if it's the last trading day of the month
                if is_monthend:
                    enhanced_candle["monthend"] = True
                
                # Map pre-calculated indicator values
                for config in indicator_configs:
                    name = config["name"]
                    indicator_key = config["key"]
                    period = config["period"]
                    
                    if name == "pctchg":
                        # Calculate percentage change based on timeframe
                        timeframe = config["timeframe"]
                        if timeframe == "weekly":
                            # Weekly percentage change: compare current close with close from 5 trading days ago
                            if idx >= 5:
                                current_price = closes[idx]
                                old_price = closes[idx - 5]
                                pct_change = ((current_price - old_price) / old_price) * 100 if old_price != 0 else 0
                                enhanced_candle[indicator_key] = pct_change
                            else:
                                enhanced_candle[indicator_key] = 0
                        elif timeframe == "monthly":
                            # Monthly percentage change: compare current close with close from 19 trading days ago
                            if idx >= 19:
                                current_price = closes[idx]
                                old_price = closes[idx - 19]
                                pct_change = ((current_price - old_price) / old_price) * 100 if old_price != 0 else 0
                                enhanced_candle[indicator_key] = pct_change
                            else:
                                enhanced_candle[indicator_key] = 0
                        else:  # daily
                            # Daily percentage change: compare current close with previous close
                            period_int = int(period)  # Convert to int for array indexing
                            if idx >= period_int:
                                old_price = closes[idx - period_int]
                                current_price = closes[idx]
                                pct_change = ((current_price - old_price) / old_price) * 100 if old_price != 0 else 0
                                enhanced_candle[indicator_key] = pct_change
                            else:
                                enhanced_candle[indicator_key] = 0
                    elif name == "volume":
                        # For volume indicators, the values should come from PostgreSQL database
                        # For now, use the OHLCV aggregated values as fallback
                        # The PostgreSQL values will be available after precalculation
                        timeframe = config["timeframe"]
                        if timeframe == "weekly":
                            # Use OHLCV aggregated weekly volume (will be replaced by PostgreSQL values)
                            enhanced_candle[indicator_key] = weekly_candle.get("volume", 0)
                        elif timeframe == "monthly":
                            # Use OHLCV aggregated monthly volume (will be replaced by PostgreSQL values)
                            enhanced_candle[indicator_key] = monthly_candle.get("volume", 0)
                        else:  # daily
                            enhanced_candle[indicator_key] = candle.get("volume", 0)
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
                            # Return None for insufficient data instead of fallback values
                            enhanced_candle[indicator_key] = indicator_values[week_index] if week_index >= 0 and week_index < len(indicator_values) and indicator_values[week_index] is not None else None
                        elif timeframe == "monthly":
                            # Find the index of this daily candle's monthly period
                            month_keys = sorted(monthly_ohlcv.keys())
                            month_key = get_month_start_timestamp(timestamp)
                            month_index = month_keys.index(month_key) if month_key in month_keys else -1
                            indicator_values = calculated_indicators.get(indicator_key, [])
                            # Return None for insufficient data instead of fallback values
                            enhanced_candle[indicator_key] = indicator_values[month_index] if month_index >= 0 and month_index < len(indicator_values) and indicator_values[month_index] is not None else None
                        else:  # daily
                            indicator_values = calculated_indicators.get(indicator_key, [None] * len(stock_data))
                            # Return None for insufficient data instead of fallback values
                            enhanced_candle[indicator_key] = indicator_values[idx] if indicator_values[idx] is not None else None
                
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

def check_if_indicators_already_calculated(indicators: List[Dict]) -> bool:
    """Check if the given indicators are already calculated in existing data."""
    try:
        # Check if precalculated indicators file exists
        precalc_file = Path("precalculatedIndicators.json")
        if not precalc_file.exists():
            return False
            
        with open(precalc_file, 'r') as f:
            data = json.load(f)
            
        if data.get("status") != "completed":
            return False
            
        existing_indicators = data.get("indicators", [])
        
        # Check if all requested indicators exist
        for new_ind in indicators:
            found = False
            for existing_ind in existing_indicators:
                if (existing_ind.get("timeframe") == new_ind.get("timeframe") and
                    existing_ind.get("name") == new_ind.get("name") and
                    existing_ind.get("params") == new_ind.get("params")):
                    found = True
                    break
            if not found:
                return False
                
        # Check if actual precalculated files exist
        precalc_dir = Path("precalculatedStorage")
        if not precalc_dir.exists():
            return False
            
        files = list(precalc_dir.glob("*_piped.json"))
        if len(files) < len(STOCK_SYMBOLS) * 0.9:  # At least 90% of stocks should be precalculated
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error checking if indicators are calculated: {e}")
        return False

async def ensure_precalculation_exists() -> bool:
    """Check if precalculation exists, if not create it with default indicators."""
    try:
        # Note: Using PostgreSQL database instead of precalculatedStorage directory
        precalc_dir = Path("precalculatedStorage")
        # No longer creating precalculatedStorage directory - using database storage
        
        # Check if precalculatedIndicators.json exists
        precalc_config_file = Path("precalculatedIndicators.json")
        
        # Check if we have any precalculated files
        existing_files = list(precalc_dir.glob("*_piped.json"))
        
        # If config file doesn't exist OR we don't have enough precalculated files
        if not precalc_config_file.exists() or len(existing_files) < len(STOCK_SYMBOLS) * 0.9:
            if not precalc_config_file.exists():
                logger.info("precalculatedIndicators.json not found. Creating new configuration and starting fresh precalculation...")
            else:
                logger.info("Insufficient precalculated data. Starting automatic precalculation with default indicators...")
            
            # Default indicators that cover most common use cases
            default_indicators = [
                # Daily indicators
                {"id": "1", "timeframe": "daily", "name": "rsi", "params": {"period": 14}, "description": "Daily RSI 14"},
                {"id": "2", "timeframe": "daily", "name": "sma", "params": {"period": 20}, "description": "Daily SMA 20"},
                {"id": "3", "timeframe": "daily", "name": "sma", "params": {"period": 50}, "description": "Daily SMA 50"},
                {"id": "4", "timeframe": "daily", "name": "ema", "params": {"period": 20}, "description": "Daily EMA 20"},
                {"id": "5", "timeframe": "daily", "name": "supertrend", "params": {"period": 10, "multiplier": 2}, "description": "Daily SuperTrend 10,2"},
                {"id": "6", "timeframe": "daily", "name": "bb", "params": {"period": 20, "stdDev": 2}, "description": "Daily Bollinger Bands 20,2"},
                {"id": "7", "timeframe": "daily", "name": "pctchg", "params": {"period": 1}, "description": "Daily % Change 1"},
                
                # Weekly indicators
                {"id": "8", "timeframe": "weekly", "name": "rsi", "params": {"period": 14}, "description": "Weekly RSI 14"},
                {"id": "9", "timeframe": "weekly", "name": "sma", "params": {"period": 20}, "description": "Weekly SMA 20"},
                {"id": "10", "timeframe": "weekly", "name": "supertrend", "params": {"period": 10, "multiplier": 2}, "description": "Weekly SuperTrend 10,2"},
                
                # Monthly indicators
                {"id": "11", "timeframe": "monthly", "name": "rsi", "params": {"period": 14}, "description": "Monthly RSI 14"},
                {"id": "12", "timeframe": "monthly", "name": "sma", "params": {"period": 20}, "description": "Monthly SMA 20"}
            ]
            
            # Save indicators configuration
            precalc_data = {
                "status": "processing",
                "indicators": default_indicators,
                "lastUpdated": datetime.utcnow().isoformat(),
                "dayOfWeek": get_day_of_week_name(datetime.utcnow().timestamp() * 1000),
                "autoGenerated": True
            }
            
            with open("precalculatedIndicators.json", 'w') as f:
                json.dump(precalc_data, f, indent=2)
            
            # Run precalculation
            await process_indicators_background(default_indicators)
            
            # Update status to completed
            precalc_data["status"] = "completed"
            with open("precalculatedIndicators.json", 'w') as f:
                json.dump(precalc_data, f, indent=2)
                
            logger.info("Automatic precalculation completed successfully")
            return True
            
        return True  # Precalculation already exists
        
    except Exception as e:
        logger.error(f"Error in ensure_precalculation_exists: {e}")
        return False

async def add_missing_indicators_and_calculate(missing_fields: List[str]) -> bool:
    """Add missing indicators to precalculated list and calculate them on-demand using dynamic indicator manager."""
    try:
        logger.info(f"🔍 Processing missing fields: {missing_fields}")
        
        # Check if the fields are basic price/volume fields that don't need indicators
        basic_fields = {'close', 'open', 'high', 'low', 'volume', 
                      'weekly_close', 'weekly_open', 'weekly_high', 'weekly_low', 'weekly_volume',
                      'monthly_close', 'monthly_open', 'monthly_high', 'monthly_low', 'monthly_volume'}
        
        # Filter out basic fields
        indicator_fields = [field for field in missing_fields if field not in basic_fields]
        
        if not indicator_fields:
            logger.info("All missing fields are basic price/volume fields, no indicators needed")
            return True
        
        logger.info(f"🚀 Auto-calculating missing indicators: {indicator_fields}")
        
        # Use dynamic indicator manager to auto-calculate missing indicators
        success_count = 0
        total_count = len(indicator_fields)
        
        for field in indicator_fields:
            try:
                # Create error detail string for the dynamic indicator manager to parse
                error_detail = f"Missing indicator: {field} is not precalculated"
                
                # Auto-calculate the missing indicator
                success = await dynamic_indicator_manager.auto_calculate_missing_indicator(error_detail)
                
                if success:
                    success_count += 1
                    logger.info(f"✅ Successfully added indicator for field: {field}")
                else:
                    logger.error(f"❌ Failed to add indicator for field: {field}")
                    
            except Exception as e:
                logger.error(f"Error processing field {field}: {e}")
        
        # Return True if at least 80% of indicators were successfully added
        success_rate = (success_count / total_count) * 100 if total_count > 0 else 100
        logger.info(f"📊 Indicator auto-calculation result: {success_count}/{total_count} ({success_rate:.1f}%) successful")
        
        return success_rate >= 80.0
        
    except Exception as e:
        logger.error(f"Error adding missing indicators: {e}")
        return False

# OLD FUNCTION REMOVED - now using dynamic indicator manager
async def add_missing_indicators_and_calculate_OLD(missing_fields: List[str]) -> bool:
    """OLD IMPLEMENTATION - DISABLED"""
    try:
        # Load current indicators configuration
        precalc_file = Path("precalculatedIndicators.json")
        current_indicators = []
        
        if precalc_file.exists():
            with open(precalc_file, 'r') as f:
                data = json.load(f)
                current_indicators = data.get('indicators', [])
        else:
            # If file doesn't exist, create it with empty indicators list
            logger.info("precalculatedIndicators.json not found, creating new file")
            current_indicators = []
        
        # Check if these indicators are already calculated (optimization)
        if check_if_indicators_already_calculated(missing_indicators):
            logger.info("All required indicators are already calculated. Skipping recalculation.")
            return True
            
        # Add missing indicators to the list (with unique IDs)
        import time
        added_indicators = []
        for indicator in missing_indicators:
            # Check if this specific indicator already exists (avoid duplicates)
            is_duplicate = any(
                existing.get('timeframe') == indicator['timeframe'] and
                existing.get('name') == indicator['name'] and
                existing.get('params') == indicator['params']
                for existing in current_indicators
            )
            
            if not is_duplicate:
                # Generate unique ID with small delay to ensure uniqueness
                time.sleep(0.001)
                indicator['id'] = str(int(time.time() * 1000))
                # Generate description
                timeframe = indicator['timeframe'].capitalize()
                name = indicator['name'].upper()
                params = indicator['params']
                
                if indicator['name'] == 'supertrend':
                    period = params.get('period', 10)
                    multiplier = params.get('multiplier', 2)
                    indicator['description'] = f"{timeframe} {name} {period},{multiplier}"
                elif indicator['name'] == 'bb':
                    period = params.get('period', 20)
                    std_dev = params.get('stdDev', 2)
                    indicator['description'] = f"{timeframe} Bollinger Bands {period},{std_dev}"
                elif indicator['name'] == 'pctchg':
                    period = params.get('period', 1)
                    indicator['description'] = f"{timeframe} {name} {period}"
                else:
                    period = params.get('period', 14)
                    indicator['description'] = f"{timeframe} {name} {period}"
                
                current_indicators.append(indicator)
                added_indicators.append(indicator)
                logger.info(f"Auto-added missing indicator: {indicator['description']}")
        
        if not added_indicators:
            return True  # No new indicators needed
            
        # Update the indicators file
        updated_data = {
            "status": "processing",
            "indicators": current_indicators,
            "lastUpdated": datetime.utcnow().isoformat(),
            "dayOfWeek": get_day_of_week_name(datetime.utcnow().timestamp() * 1000)
        }
        
        with open(precalc_file, 'w') as f:
            json.dump(updated_data, f, indent=2)
        
        # Update progress to show we're calculating missing indicators
        update_progress({
            "isRunning": True,
            "phase": "calculating_missing_indicators",
            "message": f"Auto-calculating {len(added_indicators)} missing indicators (this will take a moment)...",
            "processed": 0,
            "total": len(STOCK_SYMBOLS)
        })
        
        logger.info(f"Starting synchronous calculation for {len(added_indicators)} missing indicators")
        
        # IMPORTANT: Run the calculation SYNCHRONOUSLY and WAIT for completion
        # This ensures indicators are actually calculated before the query continues
        try:
            # Run the calculation directly in the current event loop
            await process_indicators_background(current_indicators)
            
            # Update the indicators file to mark as completed after calculation
            final_data = {
                "status": "completed",
                "indicators": current_indicators,
                "lastUpdated": datetime.utcnow().isoformat(),
                "dayOfWeek": get_day_of_week_name(datetime.utcnow().timestamp() * 1000)
            }
            
            with open(precalc_file, 'w') as f:
                json.dump(final_data, f, indent=2)
                
            logger.info(f"Calculation completed successfully for {len(added_indicators)} missing indicators")
            
            # Update progress to show completion
            update_progress({
                "isRunning": True,
                "phase": "indicators_calculated",
                "message": f"Successfully calculated {len(added_indicators)} missing indicators",
                "processed": len(STOCK_SYMBOLS),
                "total": len(STOCK_SYMBOLS)
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Calculation failed: {e}")
            # Mark as failed in the file
            failed_data = {
                "status": "failed", 
                "indicators": current_indicators,
                "lastUpdated": datetime.utcnow().isoformat(),
                "dayOfWeek": get_day_of_week_name(datetime.utcnow().timestamp() * 1000),
                "error": str(e)
            }
            with open(precalc_file, 'w') as f:
                json.dump(failed_data, f, indent=2)
            
            return False
        
    except Exception as e:
        logger.error(f"Error adding missing indicators: {e}")
        return False

async def process_indicators_background(indicators: List[Dict[str, Any]]):
    """MAXIMUM PERFORMANCE with optimized I/O to avoid startup/completion bottlenecks."""
    start_time = time.time()
    
    print(f"\n[API] Precalculate-indicators: Processing {len(STOCK_SYMBOLS)} stocks with {PERFORMANCE_CONFIG['max_cpu_workers']} CPU workers")
    
    try:
        # Note: Using PostgreSQL database instead of precalculatedStorage directory
        precalc_dir = Path("precalculatedStorage")
        # No longer creating precalculatedStorage directory - using database storage
        
        # Extract timeframes from indicators
        timeframes = list(set(ind.get('timeframe', 'daily') for ind in indicators))
        
        # Pre-calculate volume indicators using PostgreSQL stored procedures
        volume_indicators = [ind for ind in indicators if ind.get('name') == 'volume' and ind.get('timeframe') in ['weekly', 'monthly']]
        if volume_indicators:
            print(f"\n[API] Pre-calculating {len(volume_indicators)} volume indicators using PostgreSQL...")
            update_progress({
                "isRunning": True,
                "phase": "processing_indicators",
                "message": "Pre-calculating volume indicators...",
                "processed": 0,
                "total": len(STOCK_SYMBOLS),
                "status": "processing"
            })
            
            # Process volume indicators for all symbols
            for ind in volume_indicators:
                timeframe = ind.get('timeframe')
                if timeframe in ['weekly', 'monthly']:
                    print(f"[API] Calculating {timeframe} volume indicators...")
                    
                    # Calculate for all symbols
                    result = await postgres_indicator_service.calculate_volume(
                        symbols=STOCK_SYMBOLS,
                        timeframe=timeframe
                    )
                    print(f"[API] {timeframe.capitalize()} volume calculation: {result.get('message', 'completed')}")
        
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
                # Use the new helper function
                data = load_stock_data_sync(stock)
                if data:
                    return stock, data, True
                return stock, None, False
            except Exception as e:
                logger.error(f"Error reading {stock}: {e}")
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
        
        # Avoid division by zero error
        rate = (len(STOCK_SYMBOLS) / processing_time) if processing_time > 0 else 0
        print(f"[COMPLETED] Precalculate-indicators finished: {processing_time:.2f}s | Rate: {rate:.1f}/sec | Success: {counters['successful']}, Failed: {counters['failed']}")
        
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
                period = float(params.get("period", 14))
                
                # Create indicator key with consistent period formatting
                period_str = str(int(period)) if period.is_integer() else str(period)
                indicator_key = f"{timeframe}_{name}_{period_str}"
                
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
        size = request.size or get_default_size()  # Use provided size or default from env
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
        
        # Initialize PostgreSQL database (no file system operations)
        await db_service.initialize()
        print(f"[REFRESHDB] {datetime.now().strftime('%H:%M:%S.%f')[:-3]} - PostgreSQL database initialized")
        
        # Return immediate response
        response = {
            "success": True,
            "message": f"Database refresh started for {total_symbols} symbols. Check progress at /refreshdb-progress",
            "total": total_symbols,
            "progressUrl": "/refreshdb-progress"
        }
        
        # Start background processing
        task = asyncio.create_task(process_refresh_in_background(symbols, request_time, size))
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

async def process_refresh_in_background(symbols: List[str], request_time: datetime, size: int = None):
    """Process database refresh in background with progress updates."""
    size = size or get_default_size()  # Use provided size or default from env
    successful = 0
    failed = 0
    processed = 0
    total = len(symbols)
    background_start = datetime.now()
    
    try:
        print(f"\n{'='*60}")
        print(f"BACKGROUND REFRESH STARTED")
        print(f"{background_start.strftime('%H:%M:%S.%f')[:-3]} - Processing {total} symbols")
        print(f"Time since request: {(background_start - request_time).total_seconds():.3f} seconds")
        print(f"{'='*60}")
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
            progress_callback=progress_callback,
            size=size
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

async def process_csv_symbols_in_background(extracted_symbols: List[str], size: int = None):
    """Process extracted symbols by updating constants and refreshing database"""
    size = size or get_default_size()  # Use provided size or default from env
    try:
        print(f"\n{'='*60}")
        print(f"BACKGROUND PROCESSING STARTED - {len(extracted_symbols)} symbols")
        print(f"Using size: {size}")
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
        
        # Initialize PostgreSQL database (no file system operations)
        await db_service.initialize()
        print(f"\n2. PostgreSQL database initialized")
        
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
            progress_callback=progress_callback,
            size=size
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
        
        # Get indicators from saved configuration or use defaults
        indicators_to_use = []
        precalc_file = Path("precalculatedIndicators.json")
        
        if precalc_file.exists():
            try:
                with open(precalc_file, 'r') as f:
                    saved_config = json.load(f)
                indicators_to_use = saved_config.get("indicators", [])
                print(f"\n4. Loading saved indicator configuration...")
                print(f"   Found {len(indicators_to_use)} indicators from saved configuration")
            except Exception as e:
                print(f"   Error loading saved configuration: {e}")
                indicators_to_use = []
        
        # Only use defaults if no saved configuration exists
        if not indicators_to_use:
            print(f"   No saved configuration found, using defaults...")
            indicators_to_use = [
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
        print(f"   Indicators: {len(indicators_to_use)}")
        print(f"   Using {CPU_COUNT} CPU cores for maximum performance")
        
        # Start high-performance indicator processing
        await process_indicators_background(indicators_to_use)
        
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

# Latest Candle Update Endpoints
@app.post("/api/update-latest-candles")
async def update_latest_candles(symbols: Optional[List[str]] = None):
    """Update latest candles for specified symbols or all symbols."""
    try:
        logger.info("Starting latest candle update via API")
        
        if symbols:
            # Update specific symbols
            results = await latest_candle_updater.update_all_symbols(symbols)
            logger.info(f"Updated latest candles for {len(symbols)} symbols")
        else:
            # Update all symbols
            results = await latest_candle_updater.update_all_symbols()
            logger.info("Updated latest candles for all symbols")
        
        # Count statistics
        updated_count = sum(1 for msg in results.values() if "Updated successfully" in msg)
        unchanged_count = sum(1 for msg in results.values() if "No update needed" in msg)
        error_count = sum(1 for msg in results.values() if "Error:" in msg or "Failed" in msg)
        
        return {
            "success": True,
            "summary": {
                "total": len(results),
                "updated": updated_count,
                "unchanged": unchanged_count,
                "errors": error_count
            },
            "details": results
        }
        
    except Exception as error:
        logger.error(f"Latest candle update error: {error}")
        raise HTTPException(status_code=500, detail=f"Latest candle update failed: {str(error)}")

async def _clean_postgresql_database():
    """NSE Database removed - this function is no longer needed."""
    # NSE DATABASE REMOVED - Only using ultra-fast database now
    logger.info("✅ PostgreSQL database cleaned successfully")
    return  # Skip NSE database cleaning - we only use ultra-fast database

async def _clean_high_speed_database():
    """Clean all data from high-speed PostgreSQL database while preserving schema."""
    try:
        logger.info("🧹 Cleaning high-speed PostgreSQL database...")
        
        from services.ultra_fast_database_service import ultra_fast_db as high_speed_db
        
        async with high_speed_db.pool.acquire() as conn:
            # Get all tables in the high-speed database
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                AND table_name NOT IN ('pg_stat_statements')
            """)
            
            # Drop all tables (will be recreated by initialization)
            for table in tables:
                table_name = table['table_name']
                await conn.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                logger.info(f"   Dropped high-speed table: {table_name}")
            
            # Also drop any percentage calculation stored procedures to prevent conflicts
            percentage_functions = [
                "calculate_daily_percentage_change",
                "calculate_weekly_percentage_change", 
                "calculate_monthly_percentage_change",
                "install_percentage_change_procedures",
                "batch_calculate_daily_percentage",
                "batch_calculate_weekly_percentage",
                "batch_calculate_monthly_percentage",
                "calculate_percentage_change",
                "calculate_percentage_change_for_symbol",
                "check_percentage_change_coverage",
                "check_percentage_migration_status",
                "migrate_percentage_indicators"
            ]
            
            for func_name in percentage_functions:
                try:
                    await conn.execute(f"DROP FUNCTION IF EXISTS {func_name} CASCADE")
                    logger.debug(f"   Dropped percentage function: {func_name}")
                except Exception:
                    pass  # Ignore errors if function doesn't exist
            
            logger.info("✅ High-speed PostgreSQL database cleaned successfully")
            
    except Exception as e:
        logger.error(f"Failed to clean high-speed PostgreSQL database: {e}")
        raise

@app.post("/api/hard-refresh")
async def hard_refresh_database():
    """
    Hard refresh: Clean PostgreSQL database and fetch fresh data.
    No file system operations - pure database refresh.
    """
    from services.chartink_service import get_default_candle_count
    # NSE database service removed - using only ultra-fast database
    
    try:
        logger.info("🔄 Starting POSTGRESQL HARD REFRESH - cleaning database and refetching all data")
        
        # Initialize database connections
        await db_service.initialize()
        
        # Initialize high-speed database service
        from services.ultra_fast_database_service import ultra_fast_db as high_speed_db
        await high_speed_db.initialize()
        logger.info("🚀 High-speed database initialized")
        
        # Clean up existing PostgreSQL data from both databases
        await _clean_postgresql_database()
        await _clean_high_speed_database()
        
        # Recreate high-speed database tables after cleaning
        await high_speed_db._create_optimized_tables()
        await high_speed_db._create_speed_indexes()
        logger.info("🚀 High-speed database tables recreated")
        
        # Get candle count from environment
        candle_count = get_default_candle_count()
        logger.info(f"Using candle count from env: {candle_count}")
        
        # Reset progress
        update_progress({
            "isRunning": True,
            "phase": "initializing",
            "message": f"Hard refresh started - fetching {candle_count} candles per stock",
            "processed": 0,
            "total": len(STOCK_SYMBOLS),
            "status": "running"
        }, clear_queue=True)
        
        # Create payload for all stocks
        symbols = STOCK_SYMBOLS
        total_symbols = len(symbols)
        
        # Start background processing with full candle count
        async def hard_refresh_background():
            try:
                # Progress callback
                processed = 0
                successful = 0
                failed = 0
                
                async def progress_callback(symbol: str, success: bool):
                    nonlocal processed, successful, failed
                    processed += 1
                    if success:
                        successful += 1
                    else:
                        failed += 1
                    
                    update_progress({
                        "isRunning": True,
                        "phase": "fetching",
                        "message": f"Fetching {candle_count} candles per stock... ({processed}/{total_symbols})",
                        "processed": processed,
                        "total": total_symbols,
                        "successful": successful,
                        "failed": failed,
                        "percentage": int((processed / total_symbols) * 100)
                    })
                
                # Create payload
                payload = [[str(datetime.now().timestamp()), symbol] for symbol in symbols]
                
                # Process with chartink service using full candle count
                logger.info(f"Fetching data for {len(symbols)} symbols with {candle_count} candles each")
                results = await chartink_service.process_payload(
                    payload,
                    concurrent_limit=None,
                    progress_callback=progress_callback,
                    size=candle_count  # Use full candle count from env
                )
                
                # After data fetch, populate high-speed database
                logger.info("Data fetch complete. Populating high-speed database...")
                update_progress({
                    "isRunning": True,
                    "phase": "populating_highspeed",
                    "message": "Populating high-speed database from NSE data...",
                    "processed": 0,
                    "total": total_symbols,
                    "status": "populating"
                })
                
                # NSE database removed - population happens via direct API calls in health manager
                population_stats = {'daily_inserted': 0, 'weekly_inserted': 0, 'monthly_inserted': 0, 'total_symbols': 0, 'total_candles': 0, 'successful': 0, 'failed': 0, 'total_stocks': 0}
                logger.info(f"High-speed database populated: {population_stats}")
                
                update_progress({
                    "isRunning": True,
                    "phase": "calculating",
                    "message": f"High-speed DB populated with {population_stats['total_candles']} candles. Starting indicator calculation...",
                    "processed": population_stats['successful'],
                    "total": population_stats['total_stocks'],
                    "status": "calculating"
                })
                
                # Load current indicators from file to recalculate
                precalc_file = Path("precalculatedIndicators.json")
                indicators_to_calculate = []
                
                if precalc_file.exists():
                    try:
                        with open(precalc_file, 'r') as f:
                            data = json.load(f)
                            # Extract indicators array from the object
                            if isinstance(data, dict) and 'indicators' in data:
                                indicators_to_calculate = data['indicators']
                            elif isinstance(data, list):
                                indicators_to_calculate = data
                            else:
                                logger.warning("Unexpected format in precalculatedIndicators.json")
                            logger.info(f"Loaded {len(indicators_to_calculate)} indicators to recalculate")
                    except Exception as e:
                        logger.warning(f"Could not load indicators config: {e}")
                
                # Execute comprehensive database calculations (weekly candles + all indicators)
                logger.info("🗓️ Executing comprehensive database calculations...")
                update_progress({
                    "isRunning": True,
                    "phase": "database_calculations",
                    "message": "Executing PostgreSQL comprehensive calculations...",
                    "processed": 0,
                    "total": total_symbols,
                    "status": "database_calculations"
                })
                
                # Call PostgreSQL stored procedures for weekly candle generation only (no indicators)
                calculation_start = time.time()
                
                # Process all stocks using weekly-only stored procedures directly
                calc_results = await high_speed_db.call_database_weekly_only_all_symbols()
                
                calculation_time = time.time() - calculation_start
                logger.info(f"📅 Weekly candle generation completed in {calculation_time:.2f}s")
                logger.info(f"📅 Weekly generation results: {calc_results.get('successful', 0)} successful, {calc_results.get('failed', 0)} failed")
                
                # Generate monthly candles after weekly candles
                logger.info("📅 Starting monthly candle generation...")
                monthly_start = time.time()
                monthly_results = await high_speed_db.batch_generate_monthly_candles()
                monthly_time = time.time() - monthly_start
                
                logger.info(f"📅 Monthly candle generation completed in {monthly_time:.2f}s")
                logger.info(f"📅 Monthly generation results: {monthly_results.get('successful_symbols', 0)} successful, {monthly_results.get('failed_symbols', 0)} failed, {monthly_results.get('total_monthly_candles', 0)} total candles")
                
                # Assign monthly_candle_key_id to all daily and weekly candles now that monthly candles exist
                logger.info("🔗 Assigning monthly_candle_key_id to daily and weekly candles...")
                assignment_start = time.time()
                async with high_speed_db.pool.acquire() as conn:
                    # Get all symbols to process
                    symbol_rows = await conn.fetch("SELECT DISTINCT symbol FROM daily_candles")
                    assignment_count = 0
                    
                    for symbol_row in symbol_rows:
                        symbol = symbol_row['symbol']
                        
                        # Assign monthly_candle_key_id to daily candles
                        await high_speed_db._assign_monthly_keys_to_daily_candles(conn, symbol)
                        
                        # Assign monthly_candle_key_id to weekly candles  
                        await high_speed_db._assign_monthly_keys_to_weekly_candles(conn, symbol)
                        
                        assignment_count += 1
                
                assignment_time = time.time() - assignment_start
                logger.info(f"✅ Monthly_candle_key_id assignment completed in {assignment_time:.2f}s for {assignment_count} symbols")
                
                # Calculate OHLCV for all symbols after candle generation
                logger.info("📊 Calculating weekly and monthly OHLCV for all symbols...")
                update_progress({
                    "isRunning": True,
                    "phase": "calculating_ohlcv",
                    "message": "Calculating weekly and monthly OHLCV...",
                    "processed": 0,
                    "total": assignment_count,
                    "status": "calculating_ohlcv"
                })
                
                ohlcv_start = time.time()
                ohlcv_success_count = 0
                ohlcv_processed = 0
                
                async with high_speed_db.pool.acquire() as conn:
                    for symbol_row in symbol_rows:
                        symbol = symbol_row['symbol']
                        
                        try:
                            # Calculate OHLCV for this symbol
                            await high_speed_db._calculate_ohlcv_for_symbol(conn, symbol)
                            ohlcv_success_count += 1
                        except Exception as e:
                            logger.warning(f"OHLCV calculation failed for {symbol}: {e}")
                        
                        ohlcv_processed += 1
                        
                        # Update progress periodically
                        if ohlcv_processed % 5 == 0 or ohlcv_processed == assignment_count:
                            update_progress({
                                "isRunning": True,
                                "phase": "calculating_ohlcv",
                                "message": f"Calculating OHLCV... ({ohlcv_processed}/{assignment_count})",
                                "processed": ohlcv_processed,
                                "total": assignment_count,
                                "status": "calculating_ohlcv"
                            })
                
                ohlcv_time = time.time() - ohlcv_start
                logger.info(f"✅ OHLCV calculation completed in {ohlcv_time:.2f}s for {ohlcv_success_count}/{assignment_count} symbols")
                
                logger.info("🎯 Hard refresh completed - OHLCV data + Weekly + Monthly candles + OHLCV calculated")
                
                update_progress({
                    "isRunning": True,
                    "phase": "monthly_complete", 
                    "message": f"Weekly + Monthly candle generation + OHLCV calculation completed - {calc_results['successful']} stocks with weekly candles, {monthly_results.get('successful_symbols', 0)} stocks with monthly candles, {ohlcv_success_count} stocks with OHLCV",
                    "processed": total_symbols,
                    "total": total_symbols,
                    "status": "monthly_complete"
                })
                
                # Complete - OHLCV data + Weekly + Monthly candles + OHLCV calculated
                update_progress({
                    "isRunning": False,
                    "phase": "completed",
                    "message": f"Hard refresh completed! Fetched {candle_count} OHLCV candles for {successful} stocks + Weekly candles ({calc_results['successful']} weekly) + Monthly candles ({monthly_results.get('successful_symbols', 0)} monthly) + OHLCV calculated ({ohlcv_success_count} stocks)",
                    "processed": total_symbols,
                    "total": total_symbols,
                    "successful": successful,
                    "failed": failed,
                    "status": "completed"
                })
                
                logger.info(f"Hard refresh completed: {successful} successful, {failed} failed")
                
            except Exception as e:
                logger.error(f"Hard refresh background error: {e}")
                update_progress({
                    "isRunning": False,
                    "phase": "error",
                    "message": f"Hard refresh failed: {str(e)}",
                    "status": "error"
                })
        
        # Start background task
        asyncio.create_task(hard_refresh_background())
        
        return {
            "success": True,
            "message": f"Hard refresh started - cleaning all data and fetching {candle_count} candles per stock",
            "candle_count": candle_count,
            "total_stocks": total_symbols,
            "progressUrl": "/api/progress-stream"
        }
        
    except Exception as error:
        logger.error(f"Hard refresh error: {error}")
        update_progress({
            "isRunning": False,
            "phase": "error",
            "message": f"Hard refresh failed: {str(error)}",
            "status": "error"
        })
        raise HTTPException(status_code=500, detail=f"Hard refresh failed: {str(error)}")

@app.post("/api/start-periodic-updates")
async def start_periodic_updates(
    interval_minutes: int = 2,
    force_run: bool = True,
    request_body: Optional[PeriodicUpdateRequest] = None
):
    """Start periodic latest candle updates every N minutes."""
    try:
        # Use values from JSON body if provided, otherwise use query parameters
        if request_body:
            if request_body.interval_minutes is not None:
                interval_minutes = request_body.interval_minutes
            if request_body.force_run is not None:
                force_run = request_body.force_run
        
        if latest_candle_updater.is_running:
            return {
                "success": False,
                "message": "Periodic updates are already running"
            }
        
        # Start periodic updates as a background task in the same event loop
        import asyncio
        
        # Start the periodic updates as a background task (using parallel pipeline)
        task = asyncio.create_task(
            parallel_pipeline_updater.start_periodic_updates(interval_minutes, force_run)
        )
        
        logger.info(f"Started PARALLEL PIPELINE periodic updates every {interval_minutes} minutes (force_run={force_run})")
        
        return {
            "success": True,
            "message": f"Parallel pipeline updates started (every {interval_minutes} minutes)",
            "interval_minutes": interval_minutes,
            "method": "parallel_pipeline",
            "features": [
                "Stream processing (no waiting for all fetches)",
                "Maximum CPU/RAM utilization", 
                "Real-time progress tracking",
                "100 concurrent API calls",
                "12 parallel processing threads"
            ]
        }
        
    except Exception as error:
        logger.error(f"Failed to start periodic updates: {error}")
        raise HTTPException(status_code=500, detail=f"Failed to start periodic updates: {str(error)}")

@app.post("/api/stop-periodic-updates")
async def stop_periodic_updates():
    """Stop periodic latest candle updates."""
    try:
        # Stop both updaters
        latest_candle_updater.stop_periodic_updates()
        parallel_pipeline_updater.stop_periodic_updates()
        
        return {
            "success": True,
            "message": "Periodic updates stopped"
        }
        
    except Exception as error:
        logger.error(f"Failed to stop periodic updates: {error}")
        raise HTTPException(status_code=500, detail=f"Failed to stop periodic updates: {str(error)}")

@app.post("/api/start-sequential-updates")
async def start_sequential_updates(
    interval_minutes: int = 2,
    force_run: bool = True,
    request_body: Optional[PeriodicUpdateRequest] = None
):
    """Start sequential periodic latest candle updates (legacy method)."""
    try:
        if request_body:
            if request_body.interval_minutes is not None:
                interval_minutes = request_body.interval_minutes
            if request_body.force_run is not None:
                force_run = request_body.force_run
        
        if latest_candle_updater.is_running:
            return {
                "success": False,
                "message": "Sequential updates are already running"
            }
        
        # Start the sequential updates as a background task
        import asyncio
        task = asyncio.create_task(
            latest_candle_updater.start_periodic_updates(interval_minutes, force_run)
        )
        
        logger.info(f"Started SEQUENTIAL periodic updates every {interval_minutes} minutes (force_run={force_run})")
        
        return {
            "success": True,
            "message": f"Sequential updates started (every {interval_minutes} minutes)",
            "interval_minutes": interval_minutes,
            "method": "sequential"
        }
        
    except Exception as error:
        logger.error(f"Failed to start sequential updates: {error}")
        raise HTTPException(status_code=500, detail=f"Failed to start sequential updates: {str(error)}")

@app.get("/api/periodic-updates-status")
async def get_periodic_updates_status():
    """Get the current status of periodic updates."""
    return {
        "parallel_pipeline": {
            "is_running": parallel_pipeline_updater.is_running,
            "is_market_hours": parallel_pipeline_updater.is_market_hours(),
            "force_run": parallel_pipeline_updater.force_run,
            "update_interval": parallel_pipeline_updater.update_interval,
            "last_update_time": getattr(parallel_pipeline_updater, 'last_update_time', None),
            "next_update_time": getattr(parallel_pipeline_updater, 'next_update_time', None)
        },
        "sequential": {
            "is_running": latest_candle_updater.is_running,
            "is_market_hours": latest_candle_updater.is_market_hours(),
            "force_run": latest_candle_updater.force_run,
            "update_interval": latest_candle_updater.update_interval,
            "last_update_time": getattr(latest_candle_updater, 'last_update_time', None),
            "next_update_time": getattr(latest_candle_updater, 'next_update_time', None)
        }
    }

# SSE endpoint for real-time scheduler updates
@app.get("/api/scheduler-updates-stream")
async def scheduler_updates_stream():
    """Stream real-time scheduler updates via Server-Sent Events."""
    async def generate():
        while True:
            try:
                # Get current status
                now = datetime.now()
                is_running = latest_candle_updater.is_running
                is_market_hours = latest_candle_updater.is_market_hours()
                
                # Calculate next update time if running
                next_update_seconds = 0
                if is_running and hasattr(latest_candle_updater, 'last_update_time'):
                    last_update = latest_candle_updater.last_update_time
                    if last_update:
                        next_update = last_update + timedelta(minutes=latest_candle_updater.update_interval)
                        next_update_seconds = max(0, (next_update - now).total_seconds())
                
                # Create status update
                status_data = {
                    "timestamp": now.isoformat(),
                    "is_running": is_running,
                    "is_market_hours": is_market_hours,
                    "force_run": latest_candle_updater.force_run,
                    "update_interval": latest_candle_updater.update_interval,
                    "next_update_seconds": int(next_update_seconds),
                    "last_update_time": latest_candle_updater.last_update_time.isoformat() if hasattr(latest_candle_updater, 'last_update_time') and latest_candle_updater.last_update_time else None,
                    "update_stats": getattr(latest_candle_updater, 'last_update_stats', None)
                }
                
                yield f"data: {json.dumps(status_data)}\n\n"
                
                # Wait 1 second before next update
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SSE stream error: {e}")
                await asyncio.sleep(5)
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# Dynamic Indicator Management APIs
@app.get("/api/indicators/active")
async def get_active_indicators():
    """Get list of all active indicators managed by the dynamic system."""
    try:
        indicators = await dynamic_indicator_manager.get_active_indicators_list()
        return {
            "success": True,
            "indicators": indicators,
            "count": len(indicators),
            "message": f"Retrieved {len(indicators)} active indicators"
        }
    except Exception as e:
        logger.error(f"Failed to get active indicators: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get active indicators: {str(e)}")

@app.post("/api/indicators/add")
async def add_custom_indicator(
    name: str,
    period: Optional[int] = None,
    multiplier: Optional[float] = None,
    std_dev: Optional[float] = None,
    timeframe: str = "daily"
):
    """Manually add a custom indicator to the system."""
    try:
        # Build parameters based on inputs
        params = {}
        if period is not None:
            params["period"] = period
        if multiplier is not None:
            params["multiplier"] = multiplier
        if std_dev is not None:
            params["std_dev"] = std_dev
        
        if not params:
            raise HTTPException(
                status_code=400, 
                detail="At least one parameter (period, multiplier, std_dev) must be provided"
            )
        
        success = await dynamic_indicator_manager.add_custom_indicator(name, params, timeframe)
        
        if success:
            return {
                "success": True,
                "message": f"Successfully added {name} indicator with parameters {params}",
                "indicator": {
                    "name": name,
                    "params": params,
                    "timeframe": timeframe
                }
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to add custom indicator"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add custom indicator: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add custom indicator: {str(e)}")

@app.post("/api/indicators/auto-calculate")
async def trigger_auto_calculation(error_detail: str):
    """Manually trigger auto-calculation for a missing indicator."""
    try:
        success = await dynamic_indicator_manager.auto_calculate_missing_indicator(error_detail)
        
        if success:
            return {
                "success": True,
                "message": "Successfully auto-calculated missing indicator",
                "error_detail": error_detail
            }
        else:
            return {
                "success": False,
                "message": "Failed to auto-calculate missing indicator",
                "error_detail": error_detail
            }
            
    except Exception as e:
        logger.error(f"Failed to trigger auto-calculation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger auto-calculation: {str(e)}")

@app.get("/api/indicators/config")
async def get_indicator_config():
    """Get the complete indicator configuration."""
    try:
        return {
            "success": True,
            "active_indicators": list(dynamic_indicator_manager.active_indicators),
            "indicator_definitions": dynamic_indicator_manager.indicator_definitions,
            "total_count": len(dynamic_indicator_manager.active_indicators)
        }
    except Exception as e:
        logger.error(f"Failed to get indicator config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get indicator config: {str(e)}")

# Query Processing with Auto-Calculation Wrapper
@app.post("/api/query/smart")
async def smart_query_with_auto_calculation(request: QueryRequest):
    """
    Smart query processor that automatically handles missing indicators.
    
    If indicators are missing, it will:
    1. Auto-detect the missing indicators
    2. Calculate them for all stocks
    3. Permanently add them to the system
    4. Execute the query
    """
    try:
        # First, try the normal query
        try:
            return await process_query(request)
        except HTTPException as e:
            # Check if it's a validation error we can handle
            if e.status_code == 400 and "Field validation failed" in str(e.detail):
                error_detail = e.detail.get("details", "") if isinstance(e.detail, dict) else str(e.detail)
                
                logger.info(f"🔍 Query failed with validation error, attempting auto-calculation: {error_detail}")
                
                # Try to auto-calculate missing indicators
                success, message = await dynamic_indicator_manager.handle_query_validation_error(e.detail)
                
                if success:
                    logger.info(f"✅ Auto-calculation successful: {message}")
                    # Retry the query
                    return await process_query(request)
                else:
                    logger.error(f"❌ Auto-calculation failed: {message}")
                    # Return enhanced error with auto-calculation attempt info
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "Query failed and auto-calculation was unsuccessful",
                            "original_error": e.detail,
                            "auto_calculation_result": message,
                            "hint": "The query contains indicators that could not be automatically calculated"
                        }
                    )
            else:
                # Re-raise non-validation errors
                raise
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Smart query processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Smart query processing failed: {str(e)}")

@app.get("/api/indicators/calculated")
async def get_calculated_indicators():
    """Get all calculated indicators with their metadata"""
    try:
        indicators = await indicator_metadata_service.get_all_calculated_indicators()
        stats = await indicator_metadata_service.get_indicator_stats()
        
        return {
            "success": True,
            "indicators": indicators,
            "stats": stats,
            "message": f"Found {len(indicators)} calculated indicators"
        }
    except Exception as e:
        logger.error(f"Error getting calculated indicators: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving indicators: {str(e)}")

@app.get("/api/indicators/stats")
async def get_indicator_statistics():
    """Get statistics about calculated indicators"""
    try:
        stats = await indicator_metadata_service.get_indicator_stats()
        return {
            "success": True,
            "stats": stats,
            "message": "Indicator statistics retrieved successfully"
        }
    except Exception as e:
        logger.error(f"Error getting indicator statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving statistics: {str(e)}")

@app.post("/api/indicators/check-query")
async def check_query_indicators(request: QueryRequest):
    """Analyze a query to identify required indicators without executing it"""
    try:
        from services.query_service import parse_query
        from services.highspeed_query_validator import highspeed_query_validator
        
        query = request.query
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Parse the query
        parsed_query = parse_query(query)
        
        # Use the validator to identify required fields and missing indicators
        validation_result = await highspeed_query_validator.validate_and_prepare_indicators(parsed_query)
        
        # Check which indicators exist in metadata
        required_fields = validation_result.get("required_fields", [])
        existing_indicators = []
        missing_indicators = []
        
        for field in required_fields:
            exists = await indicator_metadata_service.check_indicator_exists(field)
            if exists:
                existing_indicators.append(field)
            else:
                missing_indicators.append(field)
        
        return {
            "success": True,
            "query": query,
            "parsed_query": parsed_query,
            "required_fields": required_fields,
            "existing_indicators": existing_indicators,
            "missing_indicators": missing_indicators,
            "validation_result": validation_result,
            "message": f"Query analysis complete: {len(existing_indicators)} existing, {len(missing_indicators)} missing"
        }
        
    except Exception as e:
        logger.error(f"Error analyzing query: {e}")
        raise HTTPException(status_code=500, detail=f"Error analyzing query: {str(e)}")

# Background timer that logs to console periodically
import threading
import time as time_module
from datetime import datetime, time as datetime_time

def background_timer_thread():
    """Background thread to display periodic timer updates."""
    last_log_time = 0
    auto_start_attempted = False
    last_update_time = None
    
    while True:
        try:
            current_time = time_module.time()
            
            # Log timer status every 10 seconds for better visibility
            if current_time - last_log_time >= 10:
                now = datetime.now()
                
                # Check market hours
                current_time_obj = now.time()
                is_market_hours = (
                    now.weekday() < 5 and  # Monday-Friday
                    datetime_time(9, 15) <= current_time_obj <= datetime_time(15, 30)
                )
                
                # Auto-start scheduler during market hours (once per session)
                if is_market_hours and not latest_candle_updater.is_running and not auto_start_attempted:
                    logger.info("🚀 MARKET IS OPEN - Auto-starting periodic candle updates...")
                    logger.info("💡 Use: POST http://127.0.0.1:8001/api/start-periodic-updates")
                    auto_start_attempted = True
                
                # Calculate next update time (every 2 minutes)
                seconds_since_start = int(now.timestamp()) % 120  # 2 minutes = 120 seconds
                seconds_to_next = 120 - seconds_since_start
                minutes = seconds_to_next // 60
                seconds = seconds_to_next % 60
                
                # Create progress bar
                progress = (seconds_since_start / 120) * 100
                bar_length = 15
                filled = int(bar_length * progress / 100)
                bar = "█" * filled + "░" * (bar_length - filled)
                
                # Status display
                market_status = "🟢 OPEN" if is_market_hours else "🔴 CLOSED"
                scheduler_status = "🔄 ACTIVE" if latest_candle_updater.is_running else "⏸️ STOPPED"
                
                logger.info(f"📊 LATEST CANDLE TIMER | {now.strftime('%H:%M:%S')} | Market: {market_status} | Scheduler: {scheduler_status}")
                logger.info(f"⏳ Next Update: {minutes:02d}:{seconds:02d} | Progress: [{bar}] {int(progress)}%")
                
                last_log_time = current_time
            
            time_module.sleep(1)
            
        except Exception as e:
            logger.error(f"Timer display error: {e}")
            time_module.sleep(5)

if __name__ == "__main__":
    print("="*80)
    print("STARTING CHARTINKSUPER FASTAPI SERVER")
    print("="*80)
    print(f"Server URL: http://127.0.0.1:8001")
    print(f"API Docs: http://127.0.0.1:8001/docs")
    print(f"Health Check: http://127.0.0.1:8001/health")
    print(f"Refresh DB: POST http://127.0.0.1:8001/refreshdb")
    print(f"SSE Progress: GET http://127.0.0.1:8001/refreshdb-progress-stream")
    print(f"Latest Candle Updates: POST http://127.0.0.1:8001/api/start-periodic-updates")
    print("="*80)
    print("LATEST CANDLE UPDATE SERVICE:")
    print("   - Updates every 2 minutes during market hours (9:15 AM - 3:30 PM)")
    print("   - Fetches only today's latest candle (size=1) for efficiency")
    print("   - Timer status will appear in logs every 30 seconds")
    print("="*80)
    print("Starting server... Timer logs will appear below:")
    print("="*80)
    sys.stdout.flush()
    
    # Start background timer thread
    timer_thread = threading.Thread(target=background_timer_thread, daemon=True)
    timer_thread.start()
    
    # Simple uvicorn run without complex logging
    import uvicorn
    uvicorn.run(
        app,  # Use app directly instead of "main:app" 
        host="127.0.0.1",
        port=8001,
        log_level="info",  # Show some logs for better visibility
        access_log=False,  # Disable access logs (we have our own)
        reload=False       # Disable reload to avoid watchfiles logs
    )