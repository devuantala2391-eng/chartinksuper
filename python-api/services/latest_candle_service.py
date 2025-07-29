#!/usr/bin/env python3
"""
Standalone Latest Candle Update Service

This service runs independently and updates only the latest candle for each symbol
every 2 minutes during market hours (9:15 AM to 3:30 PM IST).

Usage:
    python services/latest_candle_service.py

Features:
- Fetches only size=1 (latest candle) for maximum efficiency
- Updates only the last candle in existing JSON files
- Skips unnecessary writes if data is unchanged
- Runs only during market hours
- Logs progress and statistics
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the parent directory to sys.path so we can import from services/
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.latest_candle_updater import latest_candle_updater
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [LATEST_CANDLE] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent.parent / 'latest_candle_updates.log')
    ]
)

logger = logging.getLogger(__name__)

async def main():
    """Main service loop."""
    logger.info("="*60)
    logger.info("STARTING LATEST CANDLE UPDATE SERVICE")
    logger.info("="*60)
    logger.info("Service will update latest candles every 2 minutes during market hours")
    logger.info("Market hours: 9:15 AM to 3:30 PM IST (Monday to Friday)")
    logger.info("Press Ctrl+C to stop the service")
    logger.info("="*60)
    
    try:
        # Start the periodic updates with 2-minute interval
        await latest_candle_updater.start_periodic_updates(interval_minutes=2)
        
    except KeyboardInterrupt:
        logger.info("Service stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Service error: {e}")
    finally:
        logger.info("Shutting down service...")
        latest_candle_updater.stop_periodic_updates()
        logger.info("Service shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nService stopped by user")
    except Exception as e:
        print(f"Service failed to start: {e}")
        sys.exit(1)