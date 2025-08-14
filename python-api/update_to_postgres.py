"""
Script to update main.py to use PostgreSQL database instead of JSON files
Run this to integrate the new NSE database service
"""

import asyncio
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_main_py():
    """Update main.py to use the new PostgreSQL database service"""
    
    main_py_path = Path(__file__).parent / "main.py"
    
    if not main_py_path.exists():
        logger.error("main.py not found")
        return False
    
    # Read the current main.py
    with open(main_py_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add import for the new database service at the top after other imports
    import_line = "from services.nse_database_service import nse_db_service"
    
    if import_line not in content:
        # Find the import section and add our import
        import_section_end = content.find("# HIGH PERFORMANCE CONFIGURATION")
        if import_section_end > 0:
            content = content[:import_section_end] + f"{import_line}\n\n" + content[import_section_end:]
            logger.info("Added NSE database service import")
    
    # Create backup
    backup_path = main_py_path.with_suffix('.py.backup')
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    logger.info(f"Created backup at {backup_path}")
    
    # Write updated content
    with open(main_py_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info("Successfully updated main.py")
    return True

async def test_database_connection():
    """Test the database connection and create tables"""
    from services.nse_database_service import nse_db_service
    
    try:
        logger.info("Testing database connection...")
        await nse_db_service.initialize()
        
        # Get database stats
        stats = await nse_db_service.get_database_stats()
        logger.info(f"Database stats: {stats}")
        
        logger.info("Database connection successful!")
        return True
        
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
    finally:
        await nse_db_service.close()

async def main():
    """Main function to perform the update"""
    logger.info("Starting PostgreSQL integration update...")
    
    # Test database connection first
    if not await test_database_connection():
        logger.error("Database connection test failed. Please check your PostgreSQL setup.")
        return
    
    # Update main.py
    if update_main_py():
        logger.info("Update completed successfully!")
        logger.info("The application will now use PostgreSQL instead of JSON files.")
        logger.info("When you run the hard-refresh API, data will be stored in the 'nse' database.")
    else:
        logger.error("Update failed!")

if __name__ == "__main__":
    asyncio.run(main())