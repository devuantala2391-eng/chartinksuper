# Python API Optimization Strategy

## Current Architecture Analysis

### 1. **API Structure**
- **Framework**: FastAPI with async/await support
- **Server**: Uvicorn ASGI server
- **Endpoints**: 20+ endpoints for data fetching, query processing, and updates
- **Concurrency Model**: Mixed async/sync with ThreadPoolExecutor

### 2. **Current Performance Bottlenecks**

#### A. Data Fetching (ChartinkService)
- **Client Pool**: 50 httpx clients with unlimited connections
- **Semaphore Limit**: 100 concurrent requests (2x pool size)
- **Timeout**: 10 seconds per request
- **Retry Logic**: 1 retry on failure
- **Issue**: Sequential processing in some areas, connection pool overhead

#### B. Query Processing
- **Lock-based**: Single query lock prevents concurrent query processing
- **Synchronous Processing**: Many CPU-bound operations block the event loop
- **Large Data Loading**: Entire JSON files loaded into memory
- **Indicator Calculation**: Sequential processing per stock

#### C. Database Operations
- **File-based Storage**: JSON files for each symbol (~2000 files)
- **No Database Indexing**: Full file scans for queries
- **Memory Overhead**: Loading entire datasets for processing
- **I/O Blocking**: Synchronous file operations

#### D. Indicator Calculations
- **Partial Caching**: Only caches some indicators (SMA, EMA, RSI, BB)
- **Cache Invalidation**: Daily reset loses all cached data
- **Sequential Processing**: Indicators calculated one by one
- **Memory Intensive**: Multiple copies of data during processing

## Optimization Strategy

### Phase 1: Immediate Optimizations (1-2 days)

#### 1.1 **Async/Await Optimization**
```python
# Current (Blocking)
def load_stock_data(symbol):
    with open(f"db/{symbol}.json", 'r') as f:
        return json.load(f)

# Optimized (Non-blocking)
async def load_stock_data(symbol):
    async with aiofiles.open(f"db/{symbol}.json", 'r') as f:
        content = await f.read()
        return json.loads(content)
```

#### 1.2 **Connection Pool Optimization**
```python
# Enhanced connection management
class OptimizedChartinkService:
    def __init__(self):
        self.session = None
        self.semaphore = asyncio.Semaphore(200)  # Increase concurrent limit
        
    async def get_session(self):
        if not self.session:
            connector = aiohttp.TCPConnector(
                limit=0,  # No connection limit
                limit_per_host=100,  # Per-host limit
                ttl_dns_cache=300,
                use_dns_cache=True
            )
            timeout = aiohttp.ClientTimeout(total=5, connect=2)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
        return self.session
```

#### 1.3 **Query Processing Parallelization**
```python
# Remove global lock, use request-specific locks
class QueryProcessor:
    def __init__(self):
        self.active_queries = {}
    
    async def process_query(self, query_id, request):
        # Allow multiple queries with different IDs
        if query_id in self.active_queries:
            raise HTTPException(409, "Query already running")
        
        self.active_queries[query_id] = True
        try:
            # Process query
            result = await self._process(request)
        finally:
            del self.active_queries[query_id]
        return result
```

### Phase 2: Data Layer Optimization (3-5 days)

#### 2.1 **Implement Redis Cache**
```python
import redis.asyncio as redis

class CacheManager:
    def __init__(self):
        self.redis = redis.Redis(
            host='localhost', 
            port=6379,
            decode_responses=True,
            max_connections=50
        )
    
    async def get_stock_data(self, symbol):
        # Try cache first
        cached = await self.redis.get(f"stock:{symbol}")
        if cached:
            return json.loads(cached)
        
        # Load from file and cache
        data = await load_from_file(symbol)
        await self.redis.setex(
            f"stock:{symbol}", 
            300,  # 5 minute TTL
            json.dumps(data)
        )
        return data
```

#### 2.2 **Implement DuckDB for Analytics**
```python
import duckdb

class AnalyticsEngine:
    def __init__(self):
        self.conn = duckdb.connect(':memory:')
        self._init_tables()
    
    def _init_tables(self):
        self.conn.execute("""
            CREATE TABLE candles (
                symbol VARCHAR,
                timestamp BIGINT,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                PRIMARY KEY (symbol, timestamp)
            )
        """)
    
    async def query_stocks(self, condition):
        # Use DuckDB's columnar storage for fast queries
        result = self.conn.execute(f"""
            SELECT * FROM candles
            WHERE {condition}
            ORDER BY timestamp DESC
        """).fetchall()
        return result
```

### Phase 3: Computational Optimization (2-3 days)

#### 3.1 **Vectorized Indicator Calculations**
```python
import numpy as np
from numba import jit

@jit(nopython=True, cache=True)
def calculate_rsi_vectorized(prices, period=14):
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gains = np.convolve(gains, np.ones(period)/period, mode='valid')
    avg_losses = np.convolve(losses, np.ones(period)/period, mode='valid')
    
    rs = avg_gains / (avg_losses + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    
    return np.concatenate([np.full(period, np.nan), rsi])
```

#### 3.2 **Parallel Indicator Processing**
```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

class ParallelIndicatorProcessor:
    def __init__(self):
        self.executor = ProcessPoolExecutor(max_workers=cpu_count())
    
    async def calculate_all_indicators(self, stocks_data):
        loop = asyncio.get_event_loop()
        
        # Split work into chunks
        chunks = np.array_split(stocks_data, cpu_count())
        
        # Process in parallel
        tasks = [
            loop.run_in_executor(
                self.executor,
                self._process_chunk,
                chunk
            )
            for chunk in chunks
        ]
        
        results = await asyncio.gather(*tasks)
        return self._merge_results(results)
```

### Phase 4: Infrastructure Optimization (1-2 days)

#### 4.1 **Worker Pool Configuration**
```python
# uvicorn configuration
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        workers=4,  # Multi-worker setup
        loop="uvloop",  # Faster event loop
        limit_max_requests=1000,  # Restart workers periodically
        timeout_keep_alive=5,
        access_log=False  # Disable for performance
    )
```

#### 4.2 **Request Batching**
```python
class BatchProcessor:
    def __init__(self):
        self.batch = []
        self.batch_size = 100
        self.batch_timeout = 0.1  # 100ms
        self.processing = False
    
    async def add_request(self, request):
        self.batch.append(request)
        
        if len(self.batch) >= self.batch_size:
            return await self._process_batch()
        
        # Wait for more requests or timeout
        await asyncio.sleep(self.batch_timeout)
        return await self._process_batch()
    
    async def _process_batch(self):
        if self.processing or not self.batch:
            return
        
        self.processing = True
        batch_to_process = self.batch[:self.batch_size]
        self.batch = self.batch[self.batch_size:]
        
        # Process entire batch together
        results = await self._batch_operation(batch_to_process)
        self.processing = False
        return results
```

### Phase 5: Advanced Optimizations (3-5 days)

#### 5.1 **WebSocket Streaming**
```python
from fastapi import WebSocket

@app.websocket("/ws/live-data")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Stream updates instead of polling
    while True:
        data = await get_latest_updates()
        await websocket.send_json(data)
        await asyncio.sleep(1)  # 1 second updates
```

#### 5.2 **Memory-Mapped Files**
```python
import mmap
import pickle

class MMapStorage:
    def __init__(self, filepath):
        self.filepath = filepath
        self.file = open(filepath, 'r+b')
        self.mmap = mmap.mmap(self.file.fileno(), 0)
    
    def read_stock_data(self, offset, length):
        self.mmap.seek(offset)
        data = self.mmap.read(length)
        return pickle.loads(data)
    
    def close(self):
        self.mmap.close()
        self.file.close()
```

#### 5.3 **Distributed Processing with Ray**
```python
import ray

@ray.remote
class StockProcessor:
    def process_indicators(self, stock_data):
        # Heavy computation
        return calculated_indicators

# Initialize Ray
ray.init(num_cpus=8)

# Distribute work
processors = [StockProcessor.remote() for _ in range(8)]
futures = []

for i, stock_batch in enumerate(stock_batches):
    processor = processors[i % 8]
    futures.append(processor.process_indicators.remote(stock_batch))

results = ray.get(futures)
```

## Performance Targets

### Current Performance
- **Data Fetch**: ~30-60 seconds for 2000 symbols
- **Query Processing**: 20-30 seconds for complex queries
- **Indicator Calculation**: 10-15 seconds for all indicators
- **Concurrent Requests**: Limited by global locks

### Target Performance (After Optimization)
- **Data Fetch**: <10 seconds for 2000 symbols
- **Query Processing**: <5 seconds for complex queries
- **Indicator Calculation**: <2 seconds with caching
- **Concurrent Requests**: 1000+ RPS

## Implementation Priority

1. **Week 1**: Phase 1 & 2 (Immediate optimizations + Redis cache)
2. **Week 2**: Phase 3 & 4 (Computational optimization + Infrastructure)
3. **Week 3**: Phase 5 (Advanced features) + Testing

## Monitoring & Metrics

### Key Metrics to Track
```python
from prometheus_client import Counter, Histogram, Gauge

# Metrics
request_count = Counter('api_requests_total', 'Total API requests')
request_duration = Histogram('api_request_duration_seconds', 'Request duration')
active_connections = Gauge('api_active_connections', 'Active connections')
cache_hit_rate = Gauge('cache_hit_rate', 'Cache hit rate')

@app.middleware("http")
async def track_metrics(request, call_next):
    with request_duration.time():
        response = await call_next(request)
    request_count.inc()
    return response
```

## Testing Strategy

### Load Testing
```bash
# Using locust
locust -f loadtest.py --host=http://localhost:8001 --users=1000 --spawn-rate=100
```

### Benchmark Script
```python
import asyncio
import aiohttp
import time

async def benchmark_api():
    async with aiohttp.ClientSession() as session:
        tasks = []
        for _ in range(1000):
            tasks.append(session.get('http://localhost:8001/api/query'))
        
        start = time.time()
        await asyncio.gather(*tasks)
        end = time.time()
        
        print(f"1000 requests in {end-start:.2f} seconds")
        print(f"RPS: {1000/(end-start):.2f}")

asyncio.run(benchmark_api())
```

## Risk Mitigation

1. **Backward Compatibility**: Maintain existing API contracts
2. **Gradual Rollout**: Use feature flags for new optimizations
3. **Rollback Plan**: Keep previous version ready for quick rollback
4. **Data Integrity**: Implement checksums and validation
5. **Error Handling**: Comprehensive error handling and recovery

## Conclusion

This optimization strategy will transform the Python API from a synchronous, file-based system to a highly concurrent, cache-optimized, distributed processing engine. The phased approach ensures minimal disruption while delivering significant performance improvements at each stage.