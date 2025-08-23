#!/usr/bin/env python3
"""
Database Migration Runner
Migrates the existing nse_highspeed database to the new composite key structure.

Usage: 
    python migrate_database.py
"""

import asyncio
import sys
from pathlib import Path

# Add python-api to path
sys.path.append(str(Path(__file__).parent / "python-api"))

from services.database_migration import DatabaseMigrator
import logging

async def main():
    print("🚀 Ultra-Fast Pipeline Database Migration")
    print("=" * 50)
    print("This will migrate your database from:")
    print("  OLD: Primary key (symbol, timestamp)")
    print("  NEW: Primary key candle_key_id (20MICRONS_1, 20MICRONS_2)")
    print("")
    
    response = input("Do you want to proceed with migration? (y/N): ")
    if response.lower() != 'y':
        print("Migration cancelled.")
        return
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    migrator = DatabaseMigrator()
    
    try:
        print("\n🔧 Starting migration process...")
        await migrator.run_full_migration()
        await migrator.finalize_migration()
        
        print("\n" + "="*80)
        print("🎉 MIGRATION COMPLETED SUCCESSFULLY!")
        print("="*80)
        print("✅ Database structure updated:")
        print("   - Primary Key: candle_key_id (20MICRONS_1, 20MICRONS_2, etc.)")
        print("   - Symbol column: symbol (for reference)")
        print("   - Sequence column: candle_sequence_number (0, 1, 2, 3...)")
        print("   - Indicators: All stored in optimized JSONB column")
        print("   - Metadata table: symbol_latest_keys (tracks latest keys per symbol)")
        print("")
        print("✅ Benefits achieved:")
        print("   - O(1) direct lookups by composite key")
        print("   - Fast 'N days ago' queries")
        print("   - Optimized JSONB indexes for indicator queries")
        print("   - Single database write per chunk")
        print("   - Support for streaming chunk processing")
        print("")
        print("🚀 Your system is now ready for ultra-fast processing!")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        
        # Ask if user wants to rollback
        response = input("\nDo you want to rollback the migration? (y/N): ")
        if response.lower() == 'y':
            try:
                await migrator.rollback_migration()
                print("✅ Migration rolled back successfully")
            except Exception as rollback_error:
                print(f"❌ Rollback failed: {rollback_error}")

if __name__ == "__main__":
    asyncio.run(main())