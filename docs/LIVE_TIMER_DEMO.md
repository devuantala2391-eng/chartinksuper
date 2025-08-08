# 🕒 Live Timer Demo

## Usage

### Option 1: Full Demo (with API server)
```bash
# Terminal 1 - Start the API server
cd python-api
python main.py

# Terminal 2 - Run live timer
cd python-api  
python live_timer_demo.py
```

### Option 2: Simple Timer (standalone)
```bash
cd python-api
python -c "
import asyncio
import os
from datetime import datetime, timedelta

async def simple_timer():
    update_interval = 2  # minutes
    start_time = datetime.now()
    
    print('🕒 LATEST CANDLE UPDATE TIMER')
    print('='*50)
    print('Updates every 2 minutes during market hours')
    print('Press Ctrl+C to stop')
    print()
    
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        
        now = datetime.now()
        elapsed = (now - start_time).total_seconds()
        cycle_time = update_interval * 60  # 2 minutes in seconds
        
        # Calculate next update
        next_update_in = cycle_time - (elapsed % cycle_time)
        minutes = int(next_update_in // 60)
        seconds = int(next_update_in % 60)
        
        # Market hours check
        current_time = now.time()
        is_market_hours = (
            now.weekday() < 5 and  # Monday-Friday
            datetime.strptime('09:15', '%H:%M').time() <= current_time <= datetime.strptime('15:30', '%H:%M').time()
        )
        
        print('🕒 LATEST CANDLE UPDATE TIMER')
        print('='*50)
        print(f'⏰ Current Time: {now.strftime(\"%H:%M:%S\")}')
        print(f'📈 Market: {\"🟢 OPEN\" if is_market_hours else \"🔴 CLOSED\"}')
        print(f'⏳ Next Update: {minutes:02d}:{seconds:02d}')
        
        # Progress bar
        progress = 1 - (next_update_in / cycle_time)
        bar_length = 30
        filled = int(bar_length * progress)
        bar = '█' * filled + '░' * (bar_length - filled)
        print(f'📊 Progress: [{bar}] {int(progress * 100)}%')
        
        if is_market_hours:
            print('✅ Status: Ready to update')
        else:
            print('⏸️  Status: Waiting for market hours')
        
        print('\\nPress Ctrl+C to stop')
        
        await asyncio.sleep(1)

try:
    asyncio.run(simple_timer())
except KeyboardInterrupt:
    print('\\n\\nTimer stopped!')
"
```

## What You'll See

```
🕒 LATEST CANDLE UPDATE TIMER
==================================================
⏰ Current Time: 14:25:30
📈 Market: 🟢 OPEN  
⏳ Next Update: 01:23
📊 Progress: [████████████░░░░░░░░░░░░░░░░░░] 42%
✅ Status: Ready to update

Press Ctrl+C to stop
```

## Features

✅ **Live Countdown** - Shows exact time until next update  
✅ **Progress Bar** - Visual progress indicator  
✅ **Market Status** - Shows if market is open/closed  
✅ **Auto-refresh** - Updates every second  
✅ **Color-coded** - Green for market open, red for closed  

## Quick Commands

Start timer with API integration:
```bash
cd python-api && python live_timer_demo.py
```

Start simple standalone timer:
```bash
cd python-api && python -c "exec(open('live_timer_demo.py').read().split('async def main')[0] + 'asyncio.run(simple_timer())')"
```