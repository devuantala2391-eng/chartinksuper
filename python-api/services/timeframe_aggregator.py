"""
Simple TimeframeAggregator - uses stored procedures for monthly candle generation
Replacement for the deleted timeframe_aggregator.py file
"""

import logging
from typing import Optional
import asyncpg

logger = logging.getLogger(__name__)

class TimeframeAggregator:
    """
    Simple timeframe aggregator that uses database stored procedures
    for generating monthly candles
    """
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        
    async def generate_monthly_candles(self, symbol: str) -> int:
        """
        Generate monthly candles for a symbol using stored procedure
        
        Args:
            symbol: Stock symbol to process
            
        Returns:
            Number of monthly candles generated
        """
        try:
            async with self.pool.acquire() as conn:
                # Call the stored procedure
                result = await conn.fetchrow(
                    "SELECT * FROM generate_monthly_candles_for_symbol($1)",
                    symbol
                )
                
                if result and result['status'] == 'SUCCESS':
                    candles_generated = result['generated_months']
                    logger.info(f"✅ Generated {candles_generated} monthly candles for {symbol}")
                    return candles_generated
                else:
                    error_msg = result['status'] if result else 'No result returned'
                    logger.warning(f"⚠️ Monthly candle generation failed for {symbol}: {error_msg}")
                    return 0
                    
        except Exception as e:
            logger.error(f"❌ Error generating monthly candles for {symbol}: {e}")
            return 0