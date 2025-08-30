import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def test_create_indicator_tables():
    """Test creating the indicator management tables manually"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    print("Creating indicator management tables...")
    
    try:
        # Create indicator_registry table (used by dynamic_indicator_manager)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS indicator_registry (
                id SERIAL PRIMARY KEY,
                config_key VARCHAR(50) UNIQUE NOT NULL,
                config_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Created indicator_registry table")
        
        # Create calculated_indicators table (used by indicator_metadata_service)  
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
                description TEXT
            )
        """)
        print("✅ Created calculated_indicators table")
        
        # Create performance indexes
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_calculated_indicators_key 
            ON calculated_indicators(indicator_key)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_calculated_indicators_name_timeframe 
            ON calculated_indicators(indicator_name, timeframe)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_calculated_indicators_status 
            ON calculated_indicators(status)
        """)
        print("✅ Created performance indexes for indicator tables")
        
    except Exception as e:
        print(f"Error creating tables: {e}")
        return
    
    # Check all tables now
    print("\n=== ALL TABLES AFTER CREATION ===")
    tables = await conn.fetch("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    
    for table in tables:
        count = await conn.fetchval(f"SELECT COUNT(*) FROM {table['table_name']}")
        print(f"  {table['table_name']}: {count} rows")
    
    await conn.close()
    print("\n🚀 Indicator management tables created successfully!")

asyncio.run(test_create_indicator_tables())
