import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def cleanup_database():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    print("=== CLEANING UP DATABASE ===")
    
    # Get ALL tables
    tables = await conn.fetch("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    
    print("\nDropping ALL tables:")
    for table in tables:
        table_name = table['table_name']
        try:
            await conn.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
            print(f"  DROPPED: {table_name}")
        except Exception as e:
            print(f"  ERROR dropping {table_name}: {e}")
    
    print("\nDatabase cleaned - all tables dropped")
    
    # Verify
    remaining = await conn.fetch("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    
    if remaining:
        print("\nWARNING: Some tables still exist:")
        for table in remaining:
            print(f"  - {table['table_name']}")
    else:
        print("VERIFIED: Database is completely clean")
    
    await conn.close()

asyncio.run(cleanup_database())
