"""
Indicator Metadata Service
Manages a dedicated table for storing all calculated indicators with their parameters
"""

import asyncio
import asyncpg
import logging
import json
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from services.ultra_fast_database_service import ultra_fast_db

logger = logging.getLogger(__name__)

class IndicatorMetadataService:
    """Service to manage indicator metadata in a dedicated table"""
    
    def __init__(self):
        self.table_created = False
        
    async def ensure_indicators_table(self):
        """Ensure the indicators metadata table exists"""
        if self.table_created:
            return
            
        try:
            async with ultra_fast_db.pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS calculated_indicators (
                        id SERIAL PRIMARY KEY,
                        indicator_key VARCHAR(100) UNIQUE NOT NULL,
                        indicator_name VARCHAR(50) NOT NULL,
                        timeframe VARCHAR(20) NOT NULL DEFAULT 'daily',
                        parameters JSONB NOT NULL,
                        calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        stocks_calculated INTEGER DEFAULT 0,
                        total_candles_calculated INTEGER DEFAULT 0,
                        status VARCHAR(20) DEFAULT 'active',
                        description TEXT,
                        created_by VARCHAR(50) DEFAULT 'dynamic_system'
                    )
                """)
                
                # Create indexes for performance
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_calculated_indicators_key 
                    ON calculated_indicators(indicator_key)
                """)
                
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_calculated_indicators_name_timeframe 
                    ON calculated_indicators(indicator_name, timeframe)
                """)
                
                self.table_created = True
                logger.info("✅ Indicators metadata table ready")
                
        except Exception as e:
            logger.error(f"Error creating indicators table: {e}")
            raise
    
    async def register_indicator(self, indicator_key: str, indicator_def: Dict, 
                               stocks_calculated: int = 0, candles_calculated: int = 0) -> bool:
        """Register a new calculated indicator in the metadata table"""
        try:
            await self.ensure_indicators_table()
            
            async with ultra_fast_db.pool.acquire() as conn:
                # Check if already exists
                existing = await conn.fetchrow(
                    "SELECT id FROM calculated_indicators WHERE indicator_key = $1",
                    indicator_key
                )
                
                if existing:
                    # Update existing entry
                    await conn.execute("""
                        UPDATE calculated_indicators 
                        SET last_updated = CURRENT_TIMESTAMP,
                            stocks_calculated = $2,
                            total_candles_calculated = $3,
                            status = 'active'
                        WHERE indicator_key = $1
                    """, indicator_key, stocks_calculated, candles_calculated)
                    logger.info(f"Updated indicator metadata: {indicator_key}")
                else:
                    # Insert new entry
                    await conn.execute("""
                        INSERT INTO calculated_indicators 
                        (indicator_key, indicator_name, timeframe, parameters, 
                         stocks_calculated, total_candles_calculated, description)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """, 
                    indicator_key, 
                    indicator_def.get('name', 'Unknown'),
                    indicator_def.get('timeframe', 'daily'),
                    json.dumps(indicator_def.get('params', {})),
                    stocks_calculated,
                    candles_calculated,
                    f"{indicator_def.get('name', 'Unknown')} indicator with params {indicator_def.get('params', {})}"
                    )
                    logger.info(f"Registered new indicator: {indicator_key}")
                
                return True
                
        except Exception as e:
            logger.error(f"Error registering indicator {indicator_key}: {e}")
            return False
    
    async def get_all_calculated_indicators(self) -> List[Dict]:
        """Get list of all calculated indicators"""
        try:
            await self.ensure_indicators_table()
            
            async with ultra_fast_db.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT indicator_key, indicator_name, timeframe, parameters,
                           calculation_date, last_updated, stocks_calculated,
                           total_candles_calculated, status, description
                    FROM calculated_indicators
                    WHERE status = 'active'
                    ORDER BY calculation_date DESC
                """)
                
                indicators = []
                for row in rows:
                    indicators.append({
                        'indicator_key': row['indicator_key'],
                        'indicator_name': row['indicator_name'],
                        'timeframe': row['timeframe'],
                        'parameters': json.loads(row['parameters']) if row['parameters'] else {},
                        'calculation_date': row['calculation_date'].isoformat() if row['calculation_date'] else None,
                        'last_updated': row['last_updated'].isoformat() if row['last_updated'] else None,
                        'stocks_calculated': row['stocks_calculated'],
                        'total_candles_calculated': row['total_candles_calculated'],
                        'status': row['status'],
                        'description': row['description']
                    })
                
                return indicators
                
        except Exception as e:
            logger.error(f"Error getting calculated indicators: {e}")
            return []
    
    async def check_indicator_exists(self, indicator_key: str) -> bool:
        """Check if an indicator is already calculated"""
        try:
            await self.ensure_indicators_table()
            
            async with ultra_fast_db.pool.acquire() as conn:
                result = await conn.fetchval("""
                    SELECT 1 FROM calculated_indicators 
                    WHERE indicator_key = $1 AND status = 'active'
                """, indicator_key)
                
                return bool(result)
                
        except Exception as e:
            logger.error(f"Error checking indicator existence: {e}")
            return False
    
    async def get_indicator_stats(self) -> Dict:
        """Get statistics about calculated indicators"""
        try:
            await self.ensure_indicators_table()
            
            async with ultra_fast_db.pool.acquire() as conn:
                stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_indicators,
                        SUM(stocks_calculated) as total_stocks_processed,
                        SUM(total_candles_calculated) as total_candles_processed,
                        COUNT(DISTINCT indicator_name) as unique_indicator_types,
                        COUNT(DISTINCT timeframe) as timeframes_used
                    FROM calculated_indicators
                    WHERE status = 'active'
                """)
                
                return {
                    'total_indicators': stats['total_indicators'] or 0,
                    'total_stocks_processed': stats['total_stocks_processed'] or 0,
                    'total_candles_processed': stats['total_candles_processed'] or 0,
                    'unique_indicator_types': stats['unique_indicator_types'] or 0,
                    'timeframes_used': stats['timeframes_used'] or 0
                }
                
        except Exception as e:
            logger.error(f"Error getting indicator stats: {e}")
            return {}
    
    async def mark_indicator_inactive(self, indicator_key: str) -> bool:
        """Mark an indicator as inactive (soft delete)"""
        try:
            await self.ensure_indicators_table()
            
            async with ultra_fast_db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE calculated_indicators 
                    SET status = 'inactive', last_updated = CURRENT_TIMESTAMP
                    WHERE indicator_key = $1
                """, indicator_key)
                
                logger.info(f"Marked indicator as inactive: {indicator_key}")
                return True
                
        except Exception as e:
            logger.error(f"Error marking indicator inactive: {e}")
            return False

# Global instance
indicator_metadata_service = IndicatorMetadataService()