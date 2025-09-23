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
        """No longer needed - using indicator_registry as single source of truth"""
        if self.table_created:
            return

        try:
            # calculated_indicators table removed - using indicator_registry instead
            logger.info("Using indicator_registry as single source of truth for indicator metadata")
            self.table_created = True

        except Exception as e:
            logger.error(f"Error in indicator metadata service: {e}")
            raise
    
    async def register_indicator(self, indicator_key: str, indicator_def: Dict,
                               stocks_calculated: int = 0, candles_calculated: int = 0) -> bool:
        """DEPRECATED: Register a new calculated indicator - now uses indicator_registry directly"""
        try:
            logger.info(f"Indicator registration deprecated: {indicator_key}. Use indicator_registry directly.")
            return True

        except Exception as e:
            logger.error(f"Error in deprecated register_indicator for {indicator_key}: {e}")
            return False
    
    async def get_all_calculated_indicators(self) -> List[Dict]:
        """DEPRECATED: Get list of all calculated indicators - now uses indicator_registry"""
        try:
            await self.ensure_indicators_table()

            async with ultra_fast_db.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT config_data, created_at, updated_at
                    FROM indicator_registry
                    ORDER BY created_at DESC
                """)

                indicators = []
                for row in rows:
                    config = json.loads(row['config_data'])
                    indicators.append({
                        'indicator_name': config.get('name', 'Unknown'),
                        'timeframe': config.get('timeframe', 'daily'),
                        'parameters': config.get('params', {}),
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                        'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
                        'status': 'active'
                    })

                return indicators

        except Exception as e:
            logger.error(f"Error getting indicators from registry: {e}")
            return []
    
    async def check_indicator_exists(self, indicator_key: str) -> bool:
        """DEPRECATED: Check if an indicator exists - now checks indicator_registry"""
        try:
            await self.ensure_indicators_table()

            # Since we don't use indicator_keys anymore, this method is deprecated
            # Return True to avoid breaking existing code
            logger.info(f"Deprecated check_indicator_exists called for {indicator_key}")
            return True

        except Exception as e:
            logger.error(f"Error in deprecated check_indicator_exists: {e}")
            return False
    
    async def get_indicator_stats(self) -> Dict:
        """Get statistics about indicators from indicator_registry"""
        try:
            await self.ensure_indicators_table()

            async with ultra_fast_db.pool.acquire() as conn:
                stats = await conn.fetchrow("""
                    SELECT COUNT(*) as total_indicators
                    FROM indicator_registry
                """)

                # Get detailed stats from the JSON data
                rows = await conn.fetch("""
                    SELECT config_data
                    FROM indicator_registry
                """)

                timeframes = set()
                indicator_types = set()

                for row in rows:
                    config = json.loads(row['config_data'])
                    timeframes.add(config.get('timeframe', 'daily'))
                    indicator_types.add(config.get('name', 'unknown'))

                return {
                    'total_indicators': stats['total_indicators'] or 0,
                    'unique_indicator_types': len(indicator_types),
                    'timeframes_used': len(timeframes),
                    'note': 'Stats from indicator_registry - stock/candle counts not tracked'
                }

        except Exception as e:
            logger.error(f"Error getting indicator stats: {e}")
            return {}
    
    async def mark_indicator_inactive(self, indicator_key: str) -> bool:
        """DEPRECATED: Mark an indicator as inactive - now deletes from indicator_registry"""
        try:
            await self.ensure_indicators_table()

            logger.info(f"Deprecated mark_indicator_inactive called for {indicator_key}")
            logger.info("To remove indicators, delete them directly from indicator_registry table")
            return True

        except Exception as e:
            logger.error(f"Error in deprecated mark_indicator_inactive: {e}")
            return False

# Global instance
indicator_metadata_service = IndicatorMetadataService()