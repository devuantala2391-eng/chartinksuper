"""Analyze current database schema to replace JSON files"""

import asyncio
import asyncpg
import os
import sys
import io
from dotenv import load_dotenv

# Fix Unicode output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

async def analyze_schema():
    """Analyze current database schema"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("=" * 60)
        print("ANALYZING DATABASE SCHEMA FOR JSON FILE REPLACEMENT")
        print("=" * 60)
        
        # 1. List all tables
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """)
        
        print(f"\nFound {len(tables)} tables:")
        for table in tables:
            print(f"  • {table['table_name']}")
        
        # 2. Check indicator_registry table structure
        print("\n" + "=" * 40)
        print("INDICATOR_REGISTRY TABLE STRUCTURE")
        print("=" * 40)
        
        try:
            registry_schema = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'indicator_registry'
                ORDER BY ordinal_position
            """)
            
            if registry_schema:
                print("Columns:")
                for col in registry_schema:
                    print(f"  • {col['column_name']} ({col['data_type']}) {'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'}")
                
                # Sample data
                sample_data = await conn.fetch("SELECT * FROM indicator_registry LIMIT 5")
                if sample_data:
                    print(f"\nSample data ({len(sample_data)} rows):")
                    for row in sample_data:
                        print(f"  • {dict(row)}")
            else:
                print("❌ No columns found - table might not exist")
                
        except Exception as e:
            print(f"❌ indicator_registry table not accessible: {e}")
        
        # 3. Check calculated_indicators table
        print("\n" + "=" * 40)
        print("CALCULATED_INDICATORS TABLE STRUCTURE") 
        print("=" * 40)
        
        try:
            calc_schema = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'calculated_indicators'
                ORDER BY ordinal_position
            """)
            
            if calc_schema:
                print("Columns:")
                for col in calc_schema:
                    print(f"  • {col['column_name']} ({col['data_type']}) {'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'}")
                    
                sample_data = await conn.fetch("SELECT * FROM calculated_indicators LIMIT 5")
                if sample_data:
                    print(f"\nSample data ({len(sample_data)} rows):")
                    for row in sample_data:
                        print(f"  • {dict(row)}")
            else:
                print("❌ No columns found - table might not exist")
                
        except Exception as e:
            print(f"❌ calculated_indicators table not accessible: {e}")
            
        # 4. Check what indicators currently exist in daily_candles
        print("\n" + "=" * 40)
        print("CURRENT INDICATORS IN DAILY_CANDLES")
        print("=" * 40)
        
        sample_indicators = await conn.fetchrow("""
            SELECT indicators
            FROM daily_candles
            WHERE indicators IS NOT NULL
            AND jsonb_typeof(indicators) = 'object'
            LIMIT 1
        """)
        
        if sample_indicators and sample_indicators['indicators']:
            indicators = sample_indicators['indicators']
            if isinstance(indicators, dict):
                print(f"Found {len(indicators)} indicator types:")
                for key, value in sorted(indicators.items()):
                    print(f"  • {key}: {value}")
            else:
                print(f"Indicators data: {indicators}")
        else:
            print("❌ No indicators found in daily_candles")
            
        # 5. Check symbols with indicators
        indicator_stats = await conn.fetchrow("""
            SELECT 
                COUNT(DISTINCT symbol) as symbols_with_indicators,
                COUNT(*) as total_records_with_indicators
            FROM daily_candles
            WHERE indicators IS NOT NULL
            AND jsonb_typeof(indicators) = 'object'
        """)
        
        if indicator_stats:
            print(f"\nIndicator statistics:")
            print(f"  • Symbols with indicators: {indicator_stats['symbols_with_indicators']}")
            print(f"  • Total records with indicators: {indicator_stats['total_records_with_indicators']}")
            
        print("\n" + "=" * 60)
        print("CONCLUSION")
        print("=" * 60)
        
        print("\n✅ Database can replace JSON files:")
        print("  1. indicator_registry → Replace dynamic_indicators.json")
        print("  2. calculated_indicators → Replace precalculatedIndicators.json")  
        print("  3. daily_candles.indicators → Check what exists dynamically")
        print("  4. schema_indicators.json → Likely obsolete with JSONB approach")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        print(traceback.format_exc())
    
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(analyze_schema())