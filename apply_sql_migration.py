"""
Apply the SQL stored procedures to the database
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def apply_sql_migration():
    """Apply the comprehensive calculations SQL"""
    try:
        # Read the SQL file
        sql_file_path = "python-api/sql/stored_procedures/comprehensive_calculations.sql"
        
        print(f"Reading SQL file: {sql_file_path}")
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        print(f"SQL file loaded, {len(sql_content)} characters")
        
        # Connect to database
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("Connected to database")
        
        # Execute the SQL
        print("Executing SQL migration...")
        await conn.execute(sql_content)
        
        print("SQL migration applied successfully!")
        
        # Verify the procedures were created
        procedures = await conn.fetch("""
            SELECT routine_name FROM information_schema.routines 
            WHERE routine_schema = 'public' 
            AND routine_type = 'FUNCTION'
            AND routine_name LIKE '%weekly%'
            ORDER BY routine_name
        """)
        
        print("Weekly procedures now available:")
        for proc in procedures:
            print(f"  {proc['routine_name']}")
        
        await conn.close()
        
    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(apply_sql_migration())