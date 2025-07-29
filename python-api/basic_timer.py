import time
import os
from datetime import datetime

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    print("STARTING LIVE TIMER...")
    time.sleep(2)
    
    cycle = 0
    try:
        while True:
            clear()
            
            now = datetime.now()
            seconds_in_cycle = cycle % 120  # 2 minutes = 120 seconds
            time_left = 120 - seconds_in_cycle
            mins = time_left // 60
            secs = time_left % 60
            
            progress = int((seconds_in_cycle / 120) * 40)
            bar = '#' * progress + '-' * (40 - progress)
            percent = int((seconds_in_cycle / 120) * 100)
            
            print('=' * 60)
            print('LATEST CANDLE UPDATE - LIVE TIMER')
            print('=' * 60)
            print(f'Current Time: {now.strftime("%H:%M:%S")}')
            print(f'Next Update:  {mins:02d}:{secs:02d}')
            print(f'Progress:     [{bar}] {percent}%')
            print(f'Cycle:        {cycle // 120 + 1}')
            print()
            print('Updates every 2 minutes during market hours')
            print('Press Ctrl+C to stop')
            print('=' * 60)
            
            time.sleep(1)
            cycle += 1
            
    except KeyboardInterrupt:
        clear()
        print("Timer stopped by user!")

if __name__ == "__main__":
    main()