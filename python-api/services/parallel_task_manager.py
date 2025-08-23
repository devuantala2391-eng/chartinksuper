"""
Parallel Task Manager with Maximum Resource Utilization
- Removes all artificial limits (20 request limit, batch waiting)
- Implements failure queue with retry logic (max 10 attempts)
- Uses 100% CPU and RAM efficiently
- Continuous task dispatch when workers are available
- No batch waiting - process immediately as resources become available
"""

import asyncio
import logging
import time
import psutil
import threading
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import weakref
import resource
import os

from .streaming_pipeline_processor import streaming_processor, ChunkProcessingResult
from .ultra_fast_database_service import ultra_fast_db
from .chartink_service import ChartinkService
from utils.constants import STOCK_SYMBOLS

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

@dataclass
class TaskItem:
    task_id: str
    symbol: str
    task_type: str  # 'fetch', 'process', 'store'
    data: Any
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 10
    status: TaskStatus = TaskStatus.PENDING
    error: Optional[str] = None
    result: Any = None

@dataclass
class WorkerStats:
    worker_id: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_time: float = 0
    average_time: float = 0
    current_task: Optional[str] = None
    is_busy: bool = False

class ParallelTaskManager:
    """
    Ultra-high performance task manager that maximizes system resource utilization.
    
    Key Features:
    - No artificial limits - uses all available CPU/RAM
    - Failure queue with exponential backoff retry (max 10 attempts)
    - Continuous task dispatch (no batch waiting)
    - Dynamic worker scaling based on system load
    - Real-time resource monitoring and adjustment
    - Dead letter queue for permanently failed tasks
    """
    
    def __init__(self):
        # System resource detection
        self.cpu_cores = psutil.cpu_count()
        self.logical_cores = psutil.cpu_count(logical=True)
        self.total_ram_gb = psutil.virtual_memory().total / (1024**3)
        
        # MAXIMUM scaling configuration - no artificial limits
        self.base_workers = self.logical_cores * 2
        self.max_workers = self.logical_cores * 8  # VERY aggressive scaling
        self.min_workers = max(self.cpu_cores, 20)
        
        # Task queues with high capacity
        self.pending_queue = asyncio.Queue(maxsize=10000)
        self.failure_queue = asyncio.Queue(maxsize=5000)
        self.dead_letter_queue = deque(maxlen=1000)
        
        # Worker management
        self.workers = {}
        self.worker_stats = {}
        self.active_workers = 0
        self.target_workers = self.base_workers
        
        # Resource monitoring
        self.resource_monitor_task = None
        self.auto_scaler_task = None
        
        # Performance tracking
        self.performance_stats = {
            'tasks_submitted': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'tasks_retried': 0,
            'total_processing_time': 0,
            'start_time': 0,
            'current_workers': 0,
            'peak_workers': 0,
            'cpu_utilization_history': deque(maxlen=100),
            'memory_utilization_history': deque(maxlen=100),
            'throughput_history': deque(maxlen=100)
        }
        
        # Services
        self.chartink_service = ChartinkService()
        
        # Control flags
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        
        # Configure system for maximum performance
        self._optimize_system_settings()
        
        logger.info(f"🚀 Parallel Task Manager initialized:")
        logger.info(f"   CPU: {self.cpu_cores} physical / {self.logical_cores} logical cores")
        logger.info(f"   RAM: {self.total_ram_gb:.1f}GB total")
        logger.info(f"   Workers: {self.min_workers}-{self.max_workers} (starting with {self.base_workers})")
        logger.info(f"   Queue Capacity: 10,000 pending + 5,000 failure")

    def _optimize_system_settings(self):
        """Optimize system settings for maximum performance"""
        try:
            # Increase file descriptor limits
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            resource.setrlimit(resource.RLIMIT_NOFILE, (min(hard, 65536), hard))
            
            # Set process priority to high (Unix/Linux only)
            if hasattr(os, 'nice'):
                try:
                    os.nice(-5)  # Higher priority
                except PermissionError:
                    pass  # Need sudo for this
            
            logger.info("✅ System optimized for maximum performance")
            
        except Exception as e:
            logger.warning(f"Could not fully optimize system settings: {e}")

    async def initialize(self):
        """Initialize the task manager and all subsystems"""
        if self.is_running:
            return
        
        self.is_running = True
        self.performance_stats['start_time'] = time.time()
        
        # Initialize database
        await ultra_fast_db.initialize()
        await streaming_processor.initialize()
        
        # Start monitoring tasks
        self.resource_monitor_task = asyncio.create_task(self._monitor_resources())
        self.auto_scaler_task = asyncio.create_task(self._auto_scale_workers())
        
        # Start initial workers
        await self._scale_workers_to_target(self.base_workers)
        
        # Start failure queue processor
        asyncio.create_task(self._process_failure_queue())
        
        logger.info(f"✅ Parallel Task Manager started with {self.active_workers} workers")

    async def submit_task(self, symbol: str, task_type: str, data: Any, 
                         priority: int = 0) -> str:
        """
        Submit a task for processing. Tasks are processed immediately as workers become available.
        No batch waiting - maximum throughput.
        """
        task_id = f"{symbol}_{task_type}_{int(time.time() * 1000)}"
        
        task = TaskItem(
            task_id=task_id,
            symbol=symbol,
            task_type=task_type,
            data=data,
            priority=priority
        )
        
        # Add to queue immediately - no artificial delays
        await self.pending_queue.put(task)
        self.performance_stats['tasks_submitted'] += 1
        
        logger.debug(f"📝 Submitted task {task_id} (queue size: {self.pending_queue.qsize()})")
        return task_id

    async def submit_hard_refresh(self, symbols: List[str] = None) -> str:
        """Submit hard refresh task for multiple symbols"""
        if symbols is None:
            symbols = STOCK_SYMBOLS
        
        logger.info(f"🎯 Submitting hard refresh for {len(symbols)} symbols")
        
        # Submit all symbol processing tasks immediately
        task_ids = []
        for symbol in symbols:
            task_id = await self.submit_task(
                symbol=symbol,
                task_type='hard_refresh_symbol',
                data={'symbol': symbol, 'total_candles': 2000},
                priority=1
            )
            task_ids.append(task_id)
        
        logger.info(f"📝 Submitted {len(task_ids)} hard refresh tasks")
        return f"batch_{int(time.time())}"

    async def _worker(self, worker_id: str):
        """
        Worker coroutine that continuously processes tasks.
        No waiting between tasks - maximum utilization.
        """
        worker_stats = WorkerStats(worker_id=worker_id)
        self.worker_stats[worker_id] = worker_stats
        
        logger.debug(f"🟢 Worker {worker_id} started")
        
        while self.is_running:
            try:
                # Get next task immediately (no timeout - wait for tasks)
                task = await self.pending_queue.get()
                
                # Update worker status
                worker_stats.is_busy = True
                worker_stats.current_task = task.task_id
                task.status = TaskStatus.IN_PROGRESS
                task.started_at = time.time()
                
                # Process the task based on type
                result = await self._process_task(task)
                
                # Update task status
                if result is not None:
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    task.completed_at = time.time()
                    
                    # Update stats
                    worker_stats.tasks_completed += 1
                    self.performance_stats['tasks_completed'] += 1
                    
                    processing_time = task.completed_at - task.started_at
                    worker_stats.total_time += processing_time
                    worker_stats.average_time = worker_stats.total_time / worker_stats.tasks_completed
                    self.performance_stats['total_processing_time'] += processing_time
                    
                    logger.debug(f"✅ Worker {worker_id} completed {task.task_id} in {processing_time:.2f}s")
                else:
                    # Task failed - send to failure queue for retry
                    task.status = TaskStatus.FAILED
                    task.completed_at = time.time()
                    
                    if task.retry_count < task.max_retries:
                        await self.failure_queue.put(task)
                        logger.warning(f"⚠️ Task {task.task_id} failed, queued for retry ({task.retry_count + 1}/{task.max_retries})")
                    else:
                        # Max retries exceeded - send to dead letter queue
                        self.dead_letter_queue.append(task)
                        logger.error(f"💀 Task {task.task_id} permanently failed after {task.max_retries} retries")
                    
                    worker_stats.tasks_failed += 1
                    self.performance_stats['tasks_failed'] += 1
                
                # Reset worker status
                worker_stats.is_busy = False
                worker_stats.current_task = None
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Worker {worker_id} error: {e}")
                worker_stats.is_busy = False
                worker_stats.current_task = None
        
        logger.debug(f"🔴 Worker {worker_id} stopped")

    async def _process_task(self, task: TaskItem) -> Any:
        """Process a single task based on its type"""
        try:
            if task.task_type == 'hard_refresh_symbol':
                # Process entire symbol using streaming processor
                symbol = task.data['symbol']
                total_candles = task.data.get('total_candles', 2000)
                
                results = await streaming_processor.process_symbol_streaming(symbol, total_candles)
                return {'symbol': symbol, 'chunks_processed': len(results), 'results': results}
            
            elif task.task_type == 'fetch_data':
                # Fetch data from Chartink
                symbol = task.data['symbol']
                size = task.data.get('size', 2000)
                
                response_data = await self.chartink_service.fetch_stock_data(symbol, size=size)
                mapped_data = self.chartink_service._map_response_data(response_data)
                return mapped_data
            
            elif task.task_type == 'process_chunk':
                # Process a chunk with indicators
                symbol = task.data['symbol']
                chunk_data = task.data['chunk_data']
                chunk_index = task.data['chunk_index']
                
                result = await streaming_processor.process_chunk(symbol, chunk_index, chunk_data)
                return result
            
            elif task.task_type == 'store_data':
                # Store processed data
                symbol = task.data['symbol']
                processed_data = task.data['processed_data']
                timeframe = task.data.get('timeframe', 'daily')
                
                success = await ultra_fast_db.store_chunk_with_indicators(symbol, processed_data, timeframe)
                return {'success': success, 'candles_stored': len(processed_data)}
            
            else:
                logger.warning(f"Unknown task type: {task.task_type}")
                return None
        
        except Exception as e:
            task.error = str(e)
            logger.error(f"Error processing task {task.task_id}: {e}")
            return None

    async def _process_failure_queue(self):
        """
        Continuously process failed tasks with exponential backoff retry.
        Failed tasks get retried up to max_retries times.
        """
        while self.is_running:
            try:
                # Get failed task
                failed_task = await self.failure_queue.get()
                
                # Increment retry count
                failed_task.retry_count += 1
                failed_task.status = TaskStatus.RETRYING
                
                # Exponential backoff delay
                delay = min(2 ** failed_task.retry_count, 60)  # Max 60 second delay
                await asyncio.sleep(delay)
                
                # Add back to pending queue for retry
                await self.pending_queue.put(failed_task)
                self.performance_stats['tasks_retried'] += 1
                
                logger.info(f"🔄 Retrying task {failed_task.task_id} (attempt {failed_task.retry_count}/{failed_task.max_retries})")
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in failure queue processor: {e}")

    async def _monitor_resources(self):
        """Continuously monitor system resources"""
        while self.is_running:
            try:
                # Get current resource usage
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                
                # Store in history
                self.performance_stats['cpu_utilization_history'].append(cpu_percent)
                self.performance_stats['memory_utilization_history'].append(memory_percent)
                
                # Calculate throughput (tasks per second)
                elapsed = time.time() - self.performance_stats['start_time']
                if elapsed > 0:
                    throughput = self.performance_stats['tasks_completed'] / elapsed
                    self.performance_stats['throughput_history'].append(throughput)
                
                # Log resource usage periodically
                if int(time.time()) % 30 == 0:  # Every 30 seconds
                    logger.info(f"📊 Resources: CPU {cpu_percent:.1f}% | RAM {memory_percent:.1f}% | "
                              f"Workers: {self.active_workers} | Queue: {self.pending_queue.qsize()} | "
                              f"Throughput: {throughput:.1f} tasks/sec")
                
                await asyncio.sleep(5)  # Monitor every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in resource monitor: {e}")

    async def _auto_scale_workers(self):
        """
        Automatically scale workers based on queue size and resource utilization.
        Maximize resource usage without overwhelming the system.
        """
        while self.is_running:
            try:
                current_queue_size = self.pending_queue.qsize()
                cpu_history = list(self.performance_stats['cpu_utilization_history'])
                memory_history = list(self.performance_stats['memory_utilization_history'])
                
                if cpu_history and memory_history:
                    avg_cpu = sum(cpu_history[-10:]) / min(len(cpu_history), 10)
                    avg_memory = sum(memory_history[-10:]) / min(len(memory_history), 10)
                    
                    # Scaling logic
                    should_scale_up = (
                        (current_queue_size > self.active_workers) or     # Any queue backlog
                        (avg_cpu < 85 and avg_memory < 85)  # More aggressive resource usage
                    )
                    
                    should_scale_down = (
                        (current_queue_size == 0 and self.active_workers > self.min_workers) or  # No work
                        (avg_cpu > 95 or avg_memory > 95)  # Only scale down at very high usage
                    )
                    
                    if should_scale_up and self.active_workers < self.max_workers:
                        new_target = min(self.active_workers + self.cpu_cores, self.max_workers)
                        await self._scale_workers_to_target(new_target)
                        logger.info(f"📈 Scaled up to {new_target} workers (queue: {current_queue_size}, CPU: {avg_cpu:.1f}%)")
                    
                    elif should_scale_down and self.active_workers > self.min_workers:
                        new_target = max(self.active_workers - self.cpu_cores, self.min_workers)
                        await self._scale_workers_to_target(new_target)
                        logger.info(f"📉 Scaled down to {new_target} workers (queue: {current_queue_size}, CPU: {avg_cpu:.1f}%)")
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto scaler: {e}")

    async def _scale_workers_to_target(self, target_workers: int):
        """Scale workers to target number"""
        current_workers = self.active_workers
        
        if target_workers > current_workers:
            # Scale up - add workers
            for i in range(target_workers - current_workers):
                worker_id = f"worker_{current_workers + i + 1}"
                worker_task = asyncio.create_task(self._worker(worker_id))
                self.workers[worker_id] = worker_task
                self.active_workers += 1
        
        elif target_workers < current_workers:
            # Scale down - remove workers
            workers_to_remove = current_workers - target_workers
            worker_ids = list(self.workers.keys())[:workers_to_remove]
            
            for worker_id in worker_ids:
                worker_task = self.workers.pop(worker_id)
                worker_task.cancel()
                if worker_id in self.worker_stats:
                    del self.worker_stats[worker_id]
                self.active_workers -= 1
        
        # Update performance tracking
        self.performance_stats['current_workers'] = self.active_workers
        self.performance_stats['peak_workers'] = max(
            self.performance_stats['peak_workers'], 
            self.active_workers
        )

    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report"""
        elapsed = time.time() - self.performance_stats['start_time']
        
        # Calculate averages
        cpu_history = list(self.performance_stats['cpu_utilization_history'])
        memory_history = list(self.performance_stats['memory_utilization_history'])
        throughput_history = list(self.performance_stats['throughput_history'])
        
        avg_cpu = sum(cpu_history) / len(cpu_history) if cpu_history else 0
        avg_memory = sum(memory_history) / len(memory_history) if memory_history else 0
        current_throughput = throughput_history[-1] if throughput_history else 0
        avg_throughput = sum(throughput_history) / len(throughput_history) if throughput_history else 0
        
        # Worker statistics
        busy_workers = sum(1 for stats in self.worker_stats.values() if stats.is_busy)
        total_worker_tasks = sum(stats.tasks_completed for stats in self.worker_stats.values())
        
        return {
            'runtime_seconds': elapsed,
            'tasks': {
                'submitted': self.performance_stats['tasks_submitted'],
                'completed': self.performance_stats['tasks_completed'],
                'failed': self.performance_stats['tasks_failed'],
                'retried': self.performance_stats['tasks_retried'],
                'pending_queue_size': self.pending_queue.qsize(),
                'failure_queue_size': self.failure_queue.qsize(),
                'dead_letter_count': len(self.dead_letter_queue)
            },
            'workers': {
                'active': self.active_workers,
                'busy': busy_workers,
                'idle': self.active_workers - busy_workers,
                'peak': self.performance_stats['peak_workers'],
                'total_tasks_completed': total_worker_tasks
            },
            'throughput': {
                'current_tasks_per_second': current_throughput,
                'average_tasks_per_second': avg_throughput,
                'total_processing_time': self.performance_stats['total_processing_time']
            },
            'resources': {
                'cpu_cores': self.cpu_cores,
                'logical_cores': self.logical_cores,
                'total_ram_gb': self.total_ram_gb,
                'avg_cpu_utilization': avg_cpu,
                'avg_memory_utilization': avg_memory,
                'current_cpu': cpu_history[-1] if cpu_history else 0,
                'current_memory': memory_history[-1] if memory_history else 0
            }
        }

    async def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Wait for all tasks to complete"""
        start_time = time.time()
        
        while self.pending_queue.qsize() > 0 or self.failure_queue.qsize() > 0:
            if timeout and (time.time() - start_time) > timeout:
                return False
            
            await asyncio.sleep(1)
        
        # Wait a bit more for workers to finish current tasks
        await asyncio.sleep(5)
        return True

    async def shutdown(self):
        """Gracefully shutdown the task manager"""
        logger.info("🛑 Shutting down parallel task manager...")
        
        self.is_running = False
        self.shutdown_event.set()
        
        # Cancel all workers
        for worker_id, worker_task in self.workers.items():
            worker_task.cancel()
        
        # Cancel monitoring tasks
        if self.resource_monitor_task:
            self.resource_monitor_task.cancel()
        if self.auto_scaler_task:
            self.auto_scaler_task.cancel()
        
        # Wait for workers to finish
        if self.workers:
            await asyncio.gather(*self.workers.values(), return_exceptions=True)
        
        # Cleanup streaming processor
        await streaming_processor.cleanup()
        
        logger.info("✅ Parallel task manager shutdown complete")

# Global instance
parallel_task_manager = ParallelTaskManager()