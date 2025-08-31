"""
Database-based Dynamic Indicator Manager
Replaces JSON file-based approach with database queries
"""

import asyncio
import asyncpg
import json
from datetime import datetime
from typing import Dict, List, Optional
import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseDynamicIndicatorManager:
    """Database-based indicator manager"""
    
    def __init__(self):
        self.pool = None
        self._active_indicators = []
        self._indicator_definitions = {}
        
    async def initialize(self):
        """Initialize database connection"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=int(os.getenv('POSTGRES_PORT', '5432')),
                database='nse_highspeed',
                user=os.getenv('POSTGRES_USER', 'postgres'),
                password=os.getenv('POSTGRES_PASSWORD', '123'),
                min_size=1,
                max_size=5
            )
        await self.load_indicator_config()
        
    async def close(self):
        """Close database connection"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            
    async def load_indicator_config(self):
        """Load indicator configuration from database"""
        if not self.pool:
            await self.initialize()
            
        async with self.pool.acquire() as conn:
            # Load active indicators list
            active_result = await conn.fetchrow("""
                SELECT config_data FROM indicator_registry 
                WHERE config_key = 'active_indicators_list'
            """)
            
            if active_result and active_result['config_data']:
                data = json.loads(active_result['config_data'])
                self._active_indicators = data.get('active_indicators', [])
            else:
                self._active_indicators = []
                
            # Load all indicator definitions
            definitions = await conn.fetch("""
                SELECT config_key, config_data FROM indicator_registry 
                WHERE config_key != 'active_indicators_list'
            """)
            
            self._indicator_definitions = {}
            for row in definitions:
                if row['config_data']:
                    config = json.loads(row['config_data'])
                    self._indicator_definitions[row['config_key']] = config
    
    @property
    def active_indicators(self) -> List[str]:
        """Get active indicators list"""
        return self._active_indicators
        
    @property 
    def indicator_definitions(self) -> Dict:
        """Get indicator definitions"""
        return self._indicator_definitions
        
    async def get_active_indicators_list(self) -> List[str]:
        """Get active indicators from database"""
        await self.load_indicator_config()
        return self._active_indicators
        
    def generate_indicator_key(self, indicator_def: Dict) -> str:
        """Generate indicator key from definition"""
        name = indicator_def.get('name', '').lower()
        timeframe = indicator_def.get('timeframe', 'daily')
        params = indicator_def.get('params', {})
        
        if name == 'supertrend':
            period = params.get('period', 10)
            multiplier = params.get('multiplier', 2.0)
            multiplier_str = str(multiplier).replace('.', 'dot')
            return f"supertrend_{period}_{multiplier_str}"
        elif name == 'percentagechange':
            if timeframe == 'daily':
                lookback = params.get('lookback')
                return f"daily_pctchg_{lookback}" if lookback else "daily_pctchg"
            else:
                return f"{timeframe}_pctchg"
        elif name.lower() in ['rsi', 'sma', 'ema']:
            period = params.get('period', 14)
            return f"{name.lower()}_{period}"
        else:
            return f"{name.lower()}_{timeframe}"
            
    async def add_custom_indicator(self, name: str, params: Dict, timeframe: str = 'daily') -> bool:
        """Add custom indicator to database"""
        if not self.pool:
            await self.initialize()
            
        config = {
            'name': name,
            'timeframe': timeframe,
            'params': params
        }
        
        key = self.generate_indicator_key(config)
        
        async with self.pool.acquire() as conn:
            try:
                # Add to indicator registry
                await conn.execute("""
                    INSERT INTO indicator_registry (config_key, config_data, created_at, updated_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (config_key) DO UPDATE SET
                        config_data = EXCLUDED.config_data,
                        updated_at = EXCLUDED.updated_at
                """,
                key,
                json.dumps(config),
                datetime.now(),
                datetime.now()
                )
                
                # Add to active indicators if not already there
                if key not in self._active_indicators:
                    self._active_indicators.append(key)
                    
                    # Update active indicators list in database
                    await conn.execute("""
                        INSERT INTO indicator_registry (config_key, config_data, created_at, updated_at)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (config_key) DO UPDATE SET
                            config_data = EXCLUDED.config_data,
                            updated_at = EXCLUDED.updated_at
                    """,
                    'active_indicators_list',
                    json.dumps({"active_indicators": self._active_indicators}),
                    datetime.now(),
                    datetime.now()
                    )
                    
                return True
            except Exception as e:
                print(f"Error adding custom indicator {key}: {e}")
                return False
                
    async def auto_calculate_missing_indicator(self, error_detail: str) -> bool:
        """Auto-calculate missing indicator based on error"""
        # Parse error detail to extract indicator info
        # This is a simplified version - you may need to adjust based on your error format
        try:
            if 'supertrend' in error_detail.lower():
                # Extract supertrend parameters
                parts = error_detail.split()
                if len(parts) >= 3:
                    period = int(parts[1])
                    multiplier = float(parts[2])
                    return await self.calculate_and_store_indicator(
                        'SuperTrend', {'period': period, 'multiplier': multiplier}, 'daily'
                    )
            return False
        except:
            return False
            
    async def calculate_and_store_indicator(self, indicator_def: Dict = None, store_in_highspeed: bool = True, name: str = None, params: Dict = None, timeframe: str = None) -> bool:
        """Calculate and store indicator - compatible with both old and new call styles"""
        # Handle both call styles for compatibility
        if indicator_def:
            # New style call with indicator_def dict
            name = indicator_def.get('name', name)
            params = indicator_def.get('params', params or {})
            timeframe = indicator_def.get('timeframe', timeframe or 'daily')
        
        # store_in_highspeed is ignored - we always use the database
        
        if not self.pool:
            await self.initialize()
            
        async with self.pool.acquire() as conn:
            try:
                if name and name.lower() == 'supertrend':
                    # Ensure parameters are integers/floats
                    period = params.get('period', 10)
                    multiplier = params.get('multiplier', 2.0)
                    
                    # Convert to proper types if needed
                    if isinstance(period, float) and period.is_integer():
                        period = int(period)
                    else:
                        period = int(period)
                    
                    # Call supertrend stored procedure for all symbols
                    result = await conn.fetchrow("""
                        SELECT * FROM calculate_supertrend_for_all_symbols($1, $2, FALSE)
                    """, period, multiplier)
                    
                    if result:
                        print(f"SuperTrend calculation result: {dict(result)}")
                        # Check if status is SUCCESS or if we have successful symbols
                        success = (result.get('status') == 'SUCCESS' or 
                                 result.get('successful_symbols', 0) > 0)
                        
                        if success:
                            # Add to active indicators if not already there
                            indicator_key = self.generate_indicator_key({
                                'name': 'SuperTrend',
                                'timeframe': timeframe,
                                'params': {'period': period, 'multiplier': multiplier}
                            })
                            
                            if indicator_key not in self._active_indicators:
                                self._active_indicators.append(indicator_key)
                                # Also add the indicator configuration
                                await self.add_custom_indicator('SuperTrend', 
                                                               {'period': period, 'multiplier': multiplier}, 
                                                               timeframe)
                        
                        return success
                    
                # Add other indicator calculations here
                return False
                
            except Exception as e:
                print(f"Error calculating {name}: {e}")
                return False
                
    async def handle_query_validation_error(self, error_detail: str) -> tuple[bool, str]:
        """Handle query validation error by auto-calculating missing indicators"""
        success = await self.auto_calculate_missing_indicator(error_detail)
        
        if success:
            return True, f"Successfully calculated missing indicator from: {error_detail}"
        else:
            return False, f"Failed to calculate missing indicator from: {error_detail}"

# Create global instance
dynamic_indicator_manager = DatabaseDynamicIndicatorManager()
