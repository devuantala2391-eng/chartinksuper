"""
Clean up long decimal keys from database
"""
import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def cleanup_long_keys():
    """Remove long decimal keys from indicators JSONB"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("="*70)
        print("CLEANING UP LONG DECIMAL KEYS FROM DATABASE")
        print("="*70)
        
        # First, find all long keys
        print("\nSearching for long indicator keys...")
        
        rows = await conn.fetch("""
            SELECT DISTINCT jsonb_object_keys(indicators) as key
            FROM daily_candles
            WHERE indicators IS NOT NULL
        """)
        
        long_keys = []
        for row in rows:
            key = row['key']
            # Check if key is suspiciously long (normal keys should be < 50 chars)
            if len(key) > 50:
                long_keys.append(key)
                print(f"Found long key: {key[:50]}...")
        
        if not long_keys:
            print("No long keys found. Database is clean!")
            return
        
        print(f"\nFound {len(long_keys)} long keys to remove")
        
        # Remove each long key
        for key in long_keys:
            print(f"\nRemoving key: {key[:50]}...")
            
            # Use the - operator to remove the key from JSONB
            result = await conn.execute("""
                UPDATE daily_candles
                SET indicators = indicators - $1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE indicators ? $1
            """, key)
            
            # Get the number of rows updated
            rows_updated = int(result.split()[-1])
            print(f"  Removed from {rows_updated} rows")
        
        # Verify cleanup
        print("\n" + "="*70)
        print("VERIFICATION")
        print("="*70)
        
        # Check if any long keys remain
        rows = await conn.fetch("""
            SELECT DISTINCT jsonb_object_keys(indicators) as key
            FROM daily_candles
            WHERE indicators IS NOT NULL
        """)
        
        remaining_long_keys = []
        for row in rows:
            key = row['key']
            if len(key) > 50:
                remaining_long_keys.append(key)
        
        if remaining_long_keys:
            print(f"[WARNING] {len(remaining_long_keys)} long keys still remain")
            for key in remaining_long_keys:
                print(f"  - {key[:50]}...")
        else:
            print("[OK] All long keys have been removed")
        
        # Show sample of clean data
        print("\nSample of cleaned data:")
        sample = await conn.fetchrow("""
            SELECT 
                candle_key_id,
                indicators
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND indicators IS NOT NULL
            ORDER BY candle_sequence_number DESC
            LIMIT 1
        """)
        
        if sample and sample['indicators']:
            indicators = json.loads(sample['indicators']) if isinstance(sample['indicators'], str) else sample['indicators']
            print(f"Candle: {sample['candle_key_id']}")
            print("Indicators:")
            for key in sorted(indicators.keys()):
                if len(key) <= 50:  # Only show properly formatted keys
                    print(f"  - {key}: {indicators[key]}")
        
        print("\n" + "="*70)
        print("CLEANUP COMPLETE")
        print("="*70)
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(cleanup_long_keys())