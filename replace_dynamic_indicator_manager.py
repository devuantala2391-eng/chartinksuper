"""
Replace all DynamicIndicatorManager usage with database-based solution
"""

import asyncio
import asyncpg
import os
import sys
import io
from pathlib import Path
from dotenv import load_dotenv

# Fix Unicode output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

async def replace_dynamic_indicator_manager():
    """Replace DynamicIndicatorManager with database-based solution"""
    
    print("=" * 60)
    print("REPLACING DYNAMIC INDICATOR MANAGER")
    print("=" * 60)
    
    # 1. Create new database-based dynamic_indicator_manager.py
    print("📝 Creating new database-based dynamic_indicator_manager.py...")
    
    new_manager_code = '''"""
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
            
    async def calculate_and_store_indicator(self, name: str, params: Dict, timeframe: str) -> bool:
        """Calculate and store indicator"""
        # This would call the appropriate stored procedure based on indicator type
        if not self.pool:
            await self.initialize()
            
        async with self.pool.acquire() as conn:
            try:
                if name.lower() == 'supertrend':
                    period = params.get('period', 10)
                    multiplier = params.get('multiplier', 2.0)
                    
                    # Call supertrend stored procedure for all symbols
                    result = await conn.fetchrow("""
                        SELECT * FROM calculate_supertrend_for_all_symbols($1, $2, FALSE)
                    """, period, multiplier)
                    
                    return result and result.get('status') == 'SUCCESS'
                    
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
'''
    
    # Write the new manager
    manager_file = Path("python-api/services/dynamic_indicator_manager.py")
    
    # Backup the old file first
    if manager_file.exists():
        backup_file = Path("python-api/services/dynamic_indicator_manager_old.py")
        with open(manager_file, 'r', encoding='utf-8') as f:
            old_content = f.read()
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(old_content)
        print(f"  📁 Backed up old file to: {backup_file}")
    
    with open(manager_file, 'w', encoding='utf-8') as f:
        f.write(new_manager_code)
        
    print(f"  ✅ Created new database-based {manager_file}")
    
    # 2. Update main.py to initialize the database manager
    print("\n🔧 Updating main.py initialization...")
    
    main_file = Path("python-api/main.py")
    if main_file.exists():
        with open(main_file, 'r', encoding='utf-8') as f:
            main_content = f.read()
            
        # Add initialization after app creation
        startup_code = '''
# Initialize database-based indicator manager
@app.on_event("startup")
async def startup_event():
    from services.dynamic_indicator_manager import dynamic_indicator_manager
    await dynamic_indicator_manager.initialize()
    
@app.on_event("shutdown") 
async def shutdown_event():
    from services.dynamic_indicator_manager import dynamic_indicator_manager
    await dynamic_indicator_manager.close()
'''
        
        # Find a good place to insert (after app = FastAPI())
        app_creation_pattern = "app = FastAPI("
        if app_creation_pattern in main_content:
            # Find the end of app creation
            app_start = main_content.find(app_creation_pattern)
            app_end = main_content.find('\n\n', app_start)
            if app_end == -1:
                app_end = main_content.find('\n', app_start) + 1
                
            # Insert startup code
            updated_content = main_content[:app_end] + startup_code + main_content[app_end:]
            
            with open(main_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            print(f"  ✅ Added database manager initialization to {main_file}")
        else:
            print(f"  ⚠️ Could not find app creation pattern in {main_file}")
    
    print("\n✅ Dynamic Indicator Manager replacement completed!")
    print("\n📋 What was changed:")
    print("  • Created new database-based dynamic_indicator_manager.py")
    print("  • Added startup/shutdown events to main.py")
    print("  • Old manager backed up as dynamic_indicator_manager_old.py")
    print("\n🔄 Next steps:")
    print("  • Remove JSON file dependencies")
    print("  • Delete JSON files")
    print("  • Test the system")

if __name__ == "__main__":
    asyncio.run(replace_dynamic_indicator_manager())