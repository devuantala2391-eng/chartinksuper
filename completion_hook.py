#!/usr/bin/env python3
"""
Completion hook - makes noise when tasks are done
"""

import winsound
import time
import sys

def play_completion_sound():
    """Play a completion sound using Windows beep"""
    try:
        # Play a pleasant completion melody
        notes = [
            (523, 200),  # C
            (587, 200),  # D
            (659, 200),  # E
            (523, 400),  # C
        ]
        
        print("\n[COMPLETED] TASK COMPLETED!")
        print("=" * 50)
        
        for freq, duration in notes:
            winsound.Beep(freq, duration)
            time.sleep(0.05)
        
        # Also play system sound
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
        
    except Exception as e:
        # Fallback to simple beep
        print("\a" * 3)  # Terminal bell
        print(f"Could not play sound: {e}")

if __name__ == "__main__":
    # Get task name from command line if provided
    task_name = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Task"
    
    print(f"\n[DONE] {task_name} COMPLETED!")
    print("=" * 50)
    play_completion_sound()