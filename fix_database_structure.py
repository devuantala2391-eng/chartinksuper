#!/usr/bin/env python3
"""
Fix database structure by dropping and recreating tables with correct composite key structure
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_database_structure():
    """Drop and recreate tables with correct composite key structure"""
    
    db_config = {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', '5432')),
        'database': 'nse_highspeed',
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', '123'),
    }
    
    conn = await asyncpg.connect(**db_config)
    
    try:
        print("Dropping existing tables...")
        await conn.execute("DROP TABLE IF EXISTS daily_candles CASCADE")
        await conn.execute("DROP TABLE IF EXISTS weekly_candles CASCADE") 
        await conn.execute("DROP TABLE IF EXISTS monthly_candles CASCADE")
        print("Tables dropped")
        
        print("\nRecreating tables with composite key structure...")
        
        # Create daily candles with composite key
        await conn.execute("""
            CREATE TABLE daily_candles (
                candle_key_id VARCHAR(50) PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                candle_sequence_number INTEGER NOT NULL,
                timestamp BIGINT NOT NULL,
                datetime TIMESTAMP NOT NULL,
                open DECIMAL(20,6) NOT NULL,
                high DECIMAL(20,6) NOT NULL,
                low DECIMAL(20,6) NOT NULL,
                close DECIMAL(20,6) NOT NULL,
                volume BIGINT NOT NULL,
                indicators JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("Created daily_candles with composite key")
        
        # Create weekly candles 
        await conn.execute("""
            CREATE TABLE weekly_candles (
                candle_key_id VARCHAR(50) PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                candle_sequence_number INTEGER NOT NULL,
                timestamp BIGINT NOT NULL,
                datetime TIMESTAMP NOT NULL,
                open DECIMAL(20,6) NOT NULL,
                high DECIMAL(20,6) NOT NULL,
                low DECIMAL(20,6) NOT NULL,
                close DECIMAL(20,6) NOT NULL,
                volume BIGINT NOT NULL,
                indicators JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("Created weekly_candles with composite key")
        
        # Create monthly candles
        await conn.execute("""
            CREATE TABLE monthly_candles (
                candle_key_id VARCHAR(50) PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                candle_sequence_number INTEGER NOT NULL,
                timestamp BIGINT NOT NULL,
                datetime TIMESTAMP NOT NULL,
                open DECIMAL(20,6) NOT NULL,
                high DECIMAL(20,6) NOT NULL,
                low DECIMAL(20,6) NOT NULL,
                close DECIMAL(20,6) NOT NULL,
                volume BIGINT NOT NULL,
                indicators JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("Created monthly_candles with composite key")
        
        print("\nDatabase structure fixed with composite keys!")
        print("Primary keys: candle_key_id (SYMBOL_123 format)")
        print("Ready for ultra-fast processing")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_database_structure())