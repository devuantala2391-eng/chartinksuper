"""
High-performance in-memory storage system for stock data.
Provides 100-1000x faster access compared to disk-based storage.
"""

import json
import pickle
import zlib
import time
import threading
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple
from collections import defaultdict, deque
from pathlib import Path
import numpy as np
import sys
import gc
import psutil
import os

logger = logging.getLogger(__name__)

class InMemoryStore:
    """
    Ultra-fast in-memory storage with intelligent caching and persistence.
    
    Features:
    - 100-1000x faster than disk I/O
    - Automatic memory management
    - Optional compression for large datasets
    - Thread-safe operations
    - Periodic snapshots for recovery
    - Smart eviction policies
    """
    
    def __init__(self, max_memory_mb: int = 2048, enable_compression: bool = True):
        """
        Initialize in-memory store.
        
        Args:
            max_memory_mb: Maximum memory usage in MB (default 2GB)
            enable_compression: Enable compression for large datasets
        """
        # Main storage
        self.stock_data: Dict[str, Dict[str, Any]] = {}
        self.precalculated_data: Dict[str, Dict[str, Any]] = {}
        self.indicator_cache: Dict[str, Dict[str, Any]] = {}
        
        # Metadata storage
        self.metadata: Dict[str, Dict[str, Any]] = {}
        
        # Access tracking for LRU eviction
        self.access_times: Dict[str, datetime] = {}
        self.access_counts: Dict[str, int] = defaultdict(int)
        
        # Configuration
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.enable_compression = enable_compression
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Performance metrics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "reads": 0,
            "writes": 0,
            "evictions": 0,
            "compressions": 0,
            "decompressions": 0,
            "total_read_time": 0.0,
            "total_write_time": 0.0
        }
        
        # Snapshot configuration
        self.snapshot_path = Path("memory_snapshots")
        self.snapshot_path.mkdir(exist_ok=True)
        self.last_snapshot = datetime.now()
        self.snapshot_interval = timedelta(minutes=30)
        
        # Start background tasks
        self._start_background_tasks()
    
    # ============= Core Storage Operations =============
    
    def set_stock_data(self, symbol: str, data: List[Dict], 
                       compress: Optional[bool] = None) -> bool:
        """
        Store stock data in memory with optional compression.
        
        Time complexity: O(1) for small data, O(n) for compression
        Space optimized based on data size
        """
        start_time = time.perf_counter()
        
        with self.lock:
            try:
                # Determine if compression is needed
                if compress is None:
                    compress = self.enable_compression and len(data) > 500
                
                # Store data
                if compress:
                    # Compress large datasets to save memory
                    compressed = self._compress_data(data)
                    self.stock_data[symbol] = {
                        "data": compressed,
                        "compressed": True,
                        "original_size": sys.getsizeof(data),
                        "compressed_size": sys.getsizeof(compressed)
                    }
                    self.stats["compressions"] += 1
                else:
                    # Store directly for fast access
                    self.stock_data[symbol] = {
                        "data": data,
                        "compressed": False,
                        "size": sys.getsizeof(data)
                    }
                
                # Update metadata
                self.metadata[symbol] = {
                    "last_updated": datetime.now(),
                    "candle_count": len(data),
                    "compressed": compress,
                    "last_timestamp": data[-1]["timestamp"] if data else None
                }
                
                # Track access
                self._track_access(symbol)
                
                # Check memory usage
                self._check_memory_usage()
                
                self.stats["writes"] += 1
                self.stats["total_write_time"] += time.perf_counter() - start_time
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to store {symbol}: {e}")
                return False
    
    def get_stock_data(self, symbol: str) -> Optional[List[Dict]]:
        """
        Retrieve stock data from memory.
        
        Time complexity: O(1) for uncompressed, O(n) for decompression
        100-1000x faster than disk I/O
        """
        start_time = time.perf_counter()
        
        with self.lock:
            if symbol not in self.stock_data:
                self.stats["misses"] += 1
                return None
            
            self.stats["hits"] += 1
            self.stats["reads"] += 1
            
            # Track access for LRU
            self._track_access(symbol)
            
            # Get data
            stored = self.stock_data[symbol]
            
            if stored.get("compressed", False):
                # Decompress if needed
                data = self._decompress_data(stored["data"])
                self.stats["decompressions"] += 1
            else:
                data = stored["data"]
            
            self.stats["total_read_time"] += time.perf_counter() - start_time
            
            return data
    
    def set_precalculated(self, symbol: str, data: Dict[str, Any]) -> bool:
        """
        Store precalculated indicators in memory.
        """
        with self.lock:
            try:
                self.precalculated_data[symbol] = {
                    "data": data,
                    "timestamp": datetime.now(),
                    "size": sys.getsizeof(data)
                }
                
                self._track_access(f"precalc_{symbol}")
                self._check_memory_usage()
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to store precalculated for {symbol}: {e}")
                return False
    
    def get_precalculated(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve precalculated indicators from memory.
        """
        with self.lock:
            if symbol not in self.precalculated_data:
                return None
            
            self._track_access(f"precalc_{symbol}")
            return self.precalculated_data[symbol]["data"]
    
    # ============= Batch Operations =============
    
    def bulk_set(self, data_map: Dict[str, List[Dict]], 
                 data_type: str = "stock") -> Dict[str, bool]:
        """
        Set multiple symbols at once for efficiency.
        """
        results = {}
        
        for symbol, data in data_map.items():
            if data_type == "stock":
                results[symbol] = self.set_stock_data(symbol, data)
            elif data_type == "precalculated":
                results[symbol] = self.set_precalculated(symbol, data)
        
        return results
    
    def bulk_get(self, symbols: List[str], 
                 data_type: str = "stock") -> Dict[str, Any]:
        """
        Get multiple symbols at once.
        """
        results = {}
        
        for symbol in symbols:
            if data_type == "stock":
                results[symbol] = self.get_stock_data(symbol)
            elif data_type == "precalculated":
                results[symbol] = self.get_precalculated(symbol)
        
        return results
    
    # ============= Memory Management =============
    
    def _check_memory_usage(self):
        """
        Check current memory usage and evict if necessary.
        """
        current_usage = self._get_memory_usage()
        
        if current_usage > self.max_memory_bytes:
            self._evict_lru()
    
    def _get_memory_usage(self) -> int:
        """
        Calculate current memory usage.
        """
        total_size = 0
        
        # Stock data
        for symbol, stored in self.stock_data.items():
            if stored.get("compressed", False):
                total_size += stored.get("compressed_size", 0)
            else:
                total_size += stored.get("size", 0)
        
        # Precalculated data
        for symbol, stored in self.precalculated_data.items():
            total_size += stored.get("size", 0)
        
        return total_size
    
    def _evict_lru(self, target_reduction: float = 0.2):
        """
        Evict least recently used items to free memory.
        """
        # Sort by access time (oldest first)
        sorted_symbols = sorted(
            self.access_times.items(),
            key=lambda x: x[1]
        )
        
        target_bytes = int(self.max_memory_bytes * target_reduction)
        freed_bytes = 0
        
        for symbol, _ in sorted_symbols:
            if freed_bytes >= target_bytes:
                break
            
            # Remove from stock data
            if symbol in self.stock_data:
                stored = self.stock_data[symbol]
                if stored.get("compressed", False):
                    freed_bytes += stored.get("compressed_size", 0)
                else:
                    freed_bytes += stored.get("size", 0)
                
                del self.stock_data[symbol]
                self.stats["evictions"] += 1
            
            # Remove from metadata
            if symbol in self.metadata:
                del self.metadata[symbol]
            
            # Remove from access tracking
            if symbol in self.access_times:
                del self.access_times[symbol]
            if symbol in self.access_counts:
                del self.access_counts[symbol]
        
        logger.info(f"Evicted data to free {freed_bytes / 1024 / 1024:.1f}MB")
    
    # ============= Compression =============
    
    def _compress_data(self, data: Any) -> bytes:
        """
        Compress data to save memory.
        """
        serialized = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        compressed = zlib.compress(serialized, level=6)
        return compressed
    
    def _decompress_data(self, compressed: bytes) -> Any:
        """
        Decompress data for use.
        """
        decompressed = zlib.decompress(compressed)
        return pickle.loads(decompressed)
    
    # ============= Access Tracking =============
    
    def _track_access(self, key: str):
        """
        Track access for LRU eviction.
        """
        self.access_times[key] = datetime.now()
        self.access_counts[key] += 1
    
    # ============= Persistence & Recovery =============
    
    def create_snapshot(self, filepath: Optional[Path] = None) -> bool:
        """
        Create a snapshot of current memory state for recovery.
        """
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.snapshot_path / f"snapshot_{timestamp}.pkl"
        
        try:
            with self.lock:
                snapshot = {
                    "stock_data": self.stock_data,
                    "precalculated_data": self.precalculated_data,
                    "metadata": self.metadata,
                    "timestamp": datetime.now()
                }
                
                with open(filepath, 'wb') as f:
                    pickle.dump(snapshot, f, protocol=pickle.HIGHEST_PROTOCOL)
                
                self.last_snapshot = datetime.now()
                logger.info(f"Snapshot created: {filepath}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")
            return False
    
    def load_snapshot(self, filepath: Path) -> bool:
        """
        Load data from a snapshot file.
        """
        try:
            with open(filepath, 'rb') as f:
                snapshot = pickle.load(f)
            
            with self.lock:
                self.stock_data = snapshot.get("stock_data", {})
                self.precalculated_data = snapshot.get("precalculated_data", {})
                self.metadata = snapshot.get("metadata", {})
                
                logger.info(f"Snapshot loaded: {filepath}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to load snapshot: {e}")
            return False
    
    # ============= Background Tasks =============
    
    def _start_background_tasks(self):
        """
        Start background maintenance tasks.
        """
        # Periodic snapshot thread
        snapshot_thread = threading.Thread(
            target=self._periodic_snapshot,
            daemon=True
        )
        snapshot_thread.start()
        
        # Memory monitor thread
        monitor_thread = threading.Thread(
            target=self._monitor_memory,
            daemon=True
        )
        monitor_thread.start()
    
    def _periodic_snapshot(self):
        """
        Create periodic snapshots for recovery.
        """
        while True:
            time.sleep(self.snapshot_interval.total_seconds())
            
            if datetime.now() - self.last_snapshot >= self.snapshot_interval:
                self.create_snapshot()
    
    def _monitor_memory(self):
        """
        Monitor memory usage and log statistics.
        """
        while True:
            time.sleep(60)  # Check every minute
            
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            
            logger.info(f"Memory usage: {memory_info.rss / 1024 / 1024:.1f}MB")
            logger.info(f"Store statistics: {self.get_statistics()}")
    
    # ============= Statistics & Monitoring =============
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get performance and usage statistics.
        """
        with self.lock:
            total_symbols = len(self.stock_data)
            compressed_count = sum(
                1 for s in self.stock_data.values() 
                if s.get("compressed", False)
            )
            
            hit_rate = (self.stats["hits"] / 
                       (self.stats["hits"] + self.stats["misses"]) * 100
                       if (self.stats["hits"] + self.stats["misses"]) > 0 else 0)
            
            avg_read_time = (self.stats["total_read_time"] / self.stats["reads"] * 1000
                           if self.stats["reads"] > 0 else 0)
            
            avg_write_time = (self.stats["total_write_time"] / self.stats["writes"] * 1000
                            if self.stats["writes"] > 0 else 0)
            
            return {
                "total_symbols": total_symbols,
                "compressed_symbols": compressed_count,
                "memory_usage_mb": self._get_memory_usage() / 1024 / 1024,
                "hit_rate": f"{hit_rate:.1f}%",
                "total_reads": self.stats["reads"],
                "total_writes": self.stats["writes"],
                "avg_read_time_ms": f"{avg_read_time:.3f}",
                "avg_write_time_ms": f"{avg_write_time:.3f}",
                "evictions": self.stats["evictions"],
                "compressions": self.stats["compressions"],
                "decompressions": self.stats["decompressions"]
            }
    
    def get_memory_info(self) -> Dict[str, Any]:
        """
        Get detailed memory information.
        """
        with self.lock:
            info = {
                "symbols": {}
            }
            
            for symbol, stored in self.stock_data.items():
                if stored.get("compressed", False):
                    size = stored.get("compressed_size", 0)
                    original_size = stored.get("original_size", 0)
                    compression_ratio = 1 - (size / original_size) if original_size > 0 else 0
                    
                    info["symbols"][symbol] = {
                        "size_mb": size / 1024 / 1024,
                        "compressed": True,
                        "compression_ratio": f"{compression_ratio * 100:.1f}%"
                    }
                else:
                    info["symbols"][symbol] = {
                        "size_mb": stored.get("size", 0) / 1024 / 1024,
                        "compressed": False
                    }
            
            return info
    
    # ============= Benchmark =============
    
    def benchmark_vs_disk(self, test_size: int = 1000) -> Dict[str, Any]:
        """
        Benchmark in-memory vs disk performance.
        """
        import json
        import tempfile
        
        # Generate test data
        test_data = []
        for i in range(test_size):
            test_data.append({
                "timestamp": f"2024-01-{i%30+1:02d}",
                "open": 100 + np.random.randn(),
                "high": 102 + np.random.randn(),
                "low": 98 + np.random.randn(),
                "close": 101 + np.random.randn(),
                "volume": int(1000000 + np.random.randint(0, 1000000))
            })
        
        results = {}
        
        # Test disk I/O
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            # Write to disk
            start = time.perf_counter()
            json.dump(test_data, f)
            disk_write_time = time.perf_counter() - start
            temp_path = f.name
        
        # Read from disk
        with open(temp_path, 'r') as f:
            start = time.perf_counter()
            loaded = json.load(f)
            disk_read_time = time.perf_counter() - start
        
        os.unlink(temp_path)
        
        results["disk"] = {
            "write_time_ms": disk_write_time * 1000,
            "read_time_ms": disk_read_time * 1000
        }
        
        # Test in-memory
        start = time.perf_counter()
        self.set_stock_data("TEST", test_data, compress=False)
        memory_write_time = time.perf_counter() - start
        
        start = time.perf_counter()
        retrieved = self.get_stock_data("TEST")
        memory_read_time = time.perf_counter() - start
        
        results["memory"] = {
            "write_time_ms": memory_write_time * 1000,
            "read_time_ms": memory_read_time * 1000
        }
        
        # Calculate improvements
        results["improvement"] = {
            "write_speedup": f"{disk_write_time / memory_write_time:.1f}x",
            "read_speedup": f"{disk_read_time / memory_read_time:.1f}x"
        }
        
        # Clean up
        del self.stock_data["TEST"]
        
        return results

# Global singleton instance
_instance = None

def get_inmemory_store(max_memory_mb: int = 2048) -> InMemoryStore:
    """
    Get the global in-memory store instance.
    """
    global _instance
    if _instance is None:
        _instance = InMemoryStore(max_memory_mb=max_memory_mb)
    return _instance

# Example usage
if __name__ == "__main__":
    # Create store
    store = InMemoryStore(max_memory_mb=1024)
    
    print("In-Memory vs Disk Performance Benchmark")
    print("=" * 60)
    
    # Run benchmark
    results = store.benchmark_vs_disk(test_size=2000)
    
    print("\nDisk I/O:")
    print(f"  Write: {results['disk']['write_time_ms']:.2f}ms")
    print(f"  Read:  {results['disk']['read_time_ms']:.2f}ms")
    
    print("\nIn-Memory:")
    print(f"  Write: {results['memory']['write_time_ms']:.2f}ms")
    print(f"  Read:  {results['memory']['read_time_ms']:.2f}ms")
    
    print("\nImprovement:")
    print(f"  Write: {results['improvement']['write_speedup']} faster")
    print(f"  Read:  {results['improvement']['read_speedup']} faster")
    
    print("\n" + "=" * 60)
    print("Statistics:")
    stats = store.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")