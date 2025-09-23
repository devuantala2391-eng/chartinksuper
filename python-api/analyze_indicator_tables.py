"""
Analyze calculated_indicators and indicators_registery tables
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def analyze_tables():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    print('=== TABLE ANALYSIS REPORT ===')
    print()

    # Check if both tables exist
    tables_check = await conn.fetch('''
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name IN ('calculated_indicators', 'indicators_registery')
        ORDER BY table_name
    ''')

    print('1. TABLE EXISTENCE:')
    for table in tables_check:
        print(f'   {table["table_name"]} - EXISTS')
    print()

    # Analyze calculated_indicators table
    print('2. CALCULATED_INDICATORS TABLE:')
    print('   STRUCTURE:')
    calc_structure = await conn.fetch('''
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'calculated_indicators'
        ORDER BY ordinal_position
    ''')

    for col in calc_structure:
        print(f'     {col["column_name"]}: {col["data_type"]} | Nullable: {col["is_nullable"]}')

    # Sample data from calculated_indicators
    calc_data = await conn.fetch('SELECT * FROM calculated_indicators ORDER BY created_at DESC LIMIT 3')
    print(f'   SAMPLE DATA ({len(calc_data)} rows):')
    for row in calc_data:
        print(f'     ID: {row["id"]} | Key: {row["indicator_key"]} | Name: {row["indicator_name"]}')
        print(f'     Timeframe: {row["timeframe"]} | Status: {row["status"]} | Params: {row["parameters"]}')

    # Count records by status
    calc_stats = await conn.fetch('''
        SELECT status, COUNT(*) as count
        FROM calculated_indicators
        GROUP BY status
    ''')
    print('   RECORD COUNTS BY STATUS:')
    for stat in calc_stats:
        print(f'     {stat["status"]}: {stat["count"]} records')
    print()

    # Analyze indicators_registery table
    print('3. INDICATORS_REGISTERY TABLE:')
    try:
        reg_structure = await conn.fetch('''
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'indicators_registery'
            ORDER BY ordinal_position
        ''')

        print('   STRUCTURE:')
        for col in reg_structure:
            print(f'     {col["column_name"]}: {col["data_type"]} | Nullable: {col["is_nullable"]}')

        # Sample data from indicators_registery
        reg_data = await conn.fetch('SELECT * FROM indicators_registery LIMIT 3')
        print(f'   SAMPLE DATA ({len(reg_data)} rows):')
        for row in reg_data:
            print(f'     {dict(row)}')

        # Count total records
        reg_count = await conn.fetchrow('SELECT COUNT(*) as count FROM indicators_registery')
        print(f'   TOTAL RECORDS: {reg_count["count"]}')

    except Exception as e:
        print(f'   ERROR: Could not analyze indicators_registery - {e}')

    print()

    # Check usage in stored procedures
    print('4. USAGE IN STORED PROCEDURES:')
    procedures = await conn.fetch('''
        SELECT proname, prosrc
        FROM pg_proc
        WHERE prosrc LIKE '%calculated_indicators%'
           OR prosrc LIKE '%indicators_registery%'
        ORDER BY proname
    ''')

    calc_refs = []
    reg_refs = []

    for proc in procedures:
        if 'calculated_indicators' in proc['prosrc']:
            calc_refs.append(proc['proname'])
        if 'indicators_registery' in proc['prosrc']:
            reg_refs.append(proc['proname'])

    print(f'   Functions using calculated_indicators: {len(calc_refs)}')
    for func in calc_refs[:10]:  # Show first 10
        print(f'     - {func}')
    if len(calc_refs) > 10:
        print(f'     ... and {len(calc_refs) - 10} more')

    print(f'   Functions using indicators_registery: {len(reg_refs)}')
    for func in reg_refs[:10]:  # Show first 10
        print(f'     - {func}')
    if len(reg_refs) > 10:
        print(f'     ... and {len(reg_refs) - 10} more')

    print()

    # Check data overlap
    print('5. DATA COMPARISON:')

    # Get distinct indicators from calculated_indicators
    calc_indicators = await conn.fetch('''
        SELECT DISTINCT indicator_name, timeframe, parameters
        FROM calculated_indicators
        WHERE status = 'active'
        ORDER BY indicator_name, timeframe
    ''')

    print(f'   calculated_indicators has {len(calc_indicators)} active indicator configurations')

    # Group by indicator type
    indicator_summary = {}
    for ind in calc_indicators:
        name = ind['indicator_name']
        if name not in indicator_summary:
            indicator_summary[name] = []
        indicator_summary[name].append(f"{ind['timeframe']} ({ind['parameters']})")

    for name, configs in indicator_summary.items():
        print(f'     {name}: {len(configs)} configurations')
        for config in configs[:3]:  # Show first 3
            print(f'       - {config}')
        if len(configs) > 3:
            print(f'       ... and {len(configs) - 3} more')

    await conn.close()

    # Generate recommendations
    print()
    print('=== ANALYSIS CONCLUSIONS ===')
    print()

    if len(reg_refs) == 0:
        print('RECOMMENDATION: indicators_registery appears to be UNUSED')
        print('- No stored procedures reference this table')
        print('- All cron functions use calculated_indicators as source of truth')
    else:
        print('WARNING: indicators_registery is still being used')
        print('- Multiple systems may be reading from different tables')
        print('- This could cause data inconsistency')

    print()
    print('SINGLE SOURCE OF TRUTH ANALYSIS:')
    print('- calculated_indicators: Used by cron system for active indicator calculation')
    print('- Should store ALL indicator configurations with parameters')
    print('- Status field controls which indicators are actively calculated')

if __name__ == "__main__":
    asyncio.run(analyze_tables())