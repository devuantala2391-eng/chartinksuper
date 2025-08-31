"""Check existing indicator management tables"""

import asyncio
import asyncpg
import os
import sys
import io
import json
from dotenv import load_dotenv

# Fix Unicode output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

async def check_tables():
    """Check existing indicator tables"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("=" * 60)
        print("CHECKING EXISTING INDICATOR TABLES")
        print("=" * 60)
        
        # 1. Check indicator_registry contents
        print("\n📊 INDICATOR_REGISTRY TABLE:")
        registry_data = await conn.fetch("SELECT * FROM indicator_registry ORDER BY id")
        
        if registry_data:
            print(f"Found {len(registry_data)} records:")
            for row in registry_data:
                config_data = dict(row['config_data']) if row['config_data'] else {}
                print(f"  • ID: {row['id']}")
                print(f"    Key: {row['config_key']}")
                print(f"    Data: {config_data}")
                print(f"    Created: {row['created_at']}")
                print()
        else:
            print("  ❌ No records found")
            
        # 2. Check calculated_indicators contents
        print("📈 CALCULATED_INDICATORS TABLE:")
        calc_data = await conn.fetch("SELECT * FROM calculated_indicators ORDER BY id")
        
        if calc_data:
            print(f"Found {len(calc_data)} records:")
            for row in calc_data:
                params = dict(row['parameters']) if row['parameters'] else {}
                print(f"  • ID: {row['id']}")
                print(f"    Key: {row['indicator_key']}")
                print(f"    Name: {row['indicator_name']}")
                print(f"    Timeframe: {row['timeframe']}")
                print(f"    Parameters: {params}")
                print(f"    Status: {row['status']}")
                print(f"    Last Updated: {row['last_updated']}")
                print()
        else:
            print("  ❌ No records found")
            
        # 3. Show what we can replace
        print("=" * 60)
        print("REPLACEMENT PLAN")
        print("=" * 60)
        
        if registry_data or calc_data:
            print("✅ We can use existing tables:")
            print("  • indicator_registry → Store indicator configurations")
            print("  • calculated_indicators → Track calculation status")
            print("\n📋 What each JSON file will become:")
            print("  • dynamic_indicators.json → Query indicator_registry")
            print("  • precalculatedIndicators.json → Query calculated_indicators")
            print("  • schema_indicators.json → Delete (obsolete with JSONB)")
        else:
            print("⚠️ Tables exist but are empty. We can populate them and remove JSON files.")
            
        # 4. Check what indicators actually exist in daily_candles
        print("\n🔍 WHAT'S ACTUALLY CALCULATED:")
        
        # Get unique indicator keys from all records
        indicator_keys = await conn.fetch("""
            SELECT DISTINCT jsonb_object_keys(indicators) as indicator_key
            FROM daily_candles 
            WHERE indicators IS NOT NULL 
            AND jsonb_typeof(indicators) = 'object'
        """)
        
        if indicator_keys:
            print(f"Found {len(indicator_keys)} different indicators currently calculated:")
            for row in indicator_keys:
                print(f"  • {row['indicator_key']}")
        else:
            print("  ❌ No calculated indicators found")
            
        return len(registry_data), len(calc_data), len(indicator_keys) if indicator_keys else 0
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        print(traceback.format_exc())
        return 0, 0, 0
    
    finally:
        await conn.close()

async def main():
    registry_count, calc_count, actual_count = await check_tables()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"• indicator_registry records: {registry_count}")
    print(f"• calculated_indicators records: {calc_count}")  
    print(f"• Actually calculated indicators: {actual_count}")
    
    if registry_count > 0 or calc_count > 0:
        print("\n✅ Ready to eliminate JSON files using existing tables!")
    else:
        print("\n📝 Tables are empty but ready - we can populate and eliminate JSON files!")

if __name__ == "__main__":
    asyncio.run(main())