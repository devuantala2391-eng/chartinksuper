import asyncio
import aiohttp
import json
import time

async def test_hard_refresh_table_creation():
    """Test that hard refresh creates all required tables"""
    
    # First, check current tables
    print("=== BEFORE HARD REFRESH ===")
    await check_database_tables()
    
    print("\n=== STARTING HARD REFRESH ===")
    
    # Start hard refresh
    url = "http://localhost:8001/api/hard-refresh"
    headers = {'Content-Type': 'application/json'}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers) as response:
                result = await response.json()
                print(f"Hard refresh response: {response.status}")
                print(f"Result: {json.dumps(result, indent=2)}")
                
                if response.status == 200:
                    print("✅ Hard refresh started successfully")
                    
                    # Wait a bit for tables to be created
                    print("⏳ Waiting 10 seconds for table creation...")
                    await asyncio.sleep(10)
                    
                else:
                    print(f"❌ Hard refresh failed with status {response.status}")
                    return
                    
        except Exception as e:
            print(f"Error starting hard refresh: {e}")
            return
    
    print("\n=== AFTER HARD REFRESH (TABLE CREATION) ===")
    await check_database_tables()

async def check_database_tables():
    """Check what tables exist in database"""
    import asyncpg
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        # Get all tables
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        print("TABLES FOUND:")
        for table in tables:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table['table_name']}")
            print(f"  {table['table_name']}: {count} rows")
        
        await conn.close()
        
    except Exception as e:
        print(f"Error checking tables: {e}")

if __name__ == "__main__":
    asyncio.run(test_hard_refresh_table_creation())
