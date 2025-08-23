"""
Optimized population service for high-speed database
"""

import asyncio
import asyncpg
import logging
from typing import Dict, List
from datetime import datetime
import json
from services.static_indicator_calculator import static_indicator_calculator

logger = logging.getLogger(__name__)

class OptimizedPopulationService:
    """Optimized service for populating high-speed database"""
    
    def __init__(self, high_speed_db):
        self.high_speed_db = high_speed_db
        self.batch_size = 10  # Process 10 stocks at a time
        
    async def populate_from_nse_database(self, limit_stocks: int = None) -> Dict[str, int]:
        """
        Populate high-speed database with optimized batch processing
        
        Args:
            limit_stocks: Limit number of stocks to process (for testing)
        """
        try:
            logger.info("Starting optimized population of high-speed database")
            
            # Get connection to NSE database
            nse_pool = await asyncpg.create_pool(
                host=self.high_speed_db.db_config['host'],
                port=self.high_speed_db.db_config['port'],
                user=self.high_speed_db.db_config['user'],
                password=self.high_speed_db.db_config['password'],
                database='nse',
                min_size=2,
                max_size=10
            )
            
            stats = {
                'total_stocks': 0,
                'successful': 0,
                'failed': 0,
                'total_candles': 0,
                'skipped_empty': 0
            }
            
            try:
                async with nse_pool.acquire() as nse_conn:
                    # Get all stock tables
                    query = """
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name LIKE 'stock_%'
                        AND table_name != 'stock_metadata'
                        ORDER BY table_name
                    """
                    
                    if limit_stocks:
                        query += f" LIMIT {limit_stocks}"
                    
                    tables = await nse_conn.fetch(query)
                    
                    stats['total_stocks'] = len(tables)
                    logger.info(f"Found {len(tables)} stock tables to process")
                    
                    # Process in batches
                    for batch_start in range(0, len(tables), self.batch_size):
                        batch_end = min(batch_start + self.batch_size, len(tables))
                        batch_tables = tables[batch_start:batch_end]
                        
                        print(f"[INFO] Processing batch {batch_start//self.batch_size + 1}/{(len(tables) + self.batch_size - 1)//self.batch_size} ({batch_start+1}-{batch_end}/{len(tables)} stocks)")
                        
                        # Process batch sequentially (connection can't be shared)
                        batch_results = []
                        for table_row in batch_tables:
                            try:
                                result = await self._process_single_stock(nse_conn, table_row['table_name'])
                                batch_results.append(result)
                            except Exception as e:
                                batch_results.append(e)
                        
                        # Update stats
                        for result in batch_results:
                            if isinstance(result, Exception):
                                stats['failed'] += 1
                                logger.error(f"Failed to process stock: {result}")
                            elif result:
                                stats['successful'] += 1
                                stats['total_candles'] += result.get('candles', 0)
                                if result.get('empty'):
                                    stats['skipped_empty'] += 1
                        
                        print(f"  Processed: {stats['successful']}, Failed: {stats['failed']}, Candles: {stats['total_candles']}")
                        
            finally:
                await nse_pool.close()
            
            logger.info(f"Population completed: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to populate database: {e}")
            raise
    
    async def _process_single_stock(self, nse_conn, table_name: str) -> Dict:
        """Process a single stock table"""
        try:
            symbol = table_name.replace('stock_', '').upper()
            
            # Get all candles for this stock
            candles = await nse_conn.fetch(f"""
                SELECT timestamp, open, high, low, close, volume
                FROM {table_name}
                ORDER BY timestamp
            """)
            
            if not candles:
                return {'symbol': symbol, 'empty': True}
            
            # Convert to list of dicts
            candle_dicts = []
            for candle in candles:
                candle_dict = dict(candle)
                candle_dict['symbol'] = symbol
                candle_dicts.append(candle_dict)
            
            # Calculate static indicators
            calculated_candles = static_indicator_calculator.calculate_static_indicators(candle_dicts, 'daily_candles')
            
            # Insert into high-speed database
            success = await self.high_speed_db.insert_daily_candles_with_indicators(symbol, calculated_candles)
            
            if success:
                return {'symbol': symbol, 'candles': len(calculated_candles), 'success': True}
            else:
                return {'symbol': symbol, 'error': 'Insert failed'}
                
        except Exception as e:
            logger.error(f"Error processing {table_name}: {e}")
            raise

# Global instance
optimized_population_service = None

def initialize_optimized_service(high_speed_db):
    """Initialize the optimized population service"""
    global optimized_population_service
    optimized_population_service = OptimizedPopulationService(high_speed_db)
    return optimized_population_service