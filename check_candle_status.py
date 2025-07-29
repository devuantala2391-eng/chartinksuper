import json
from pathlib import Path
from datetime import datetime

def check_candle_updates():
    """Check the status of candle data to see what might be updated."""
    print("🔍 Checking Candle Data Status")
    print("="*60)
    
    db_dir = Path("db")
    if not db_dir.exists():
        print("❌ DB directory not found!")
        return
    
    # Check a few sample stocks
    sample_stocks = ["RELIANCE", "TCS", "INFY", "HDFC", "ICICIBANK"]
    today = datetime.now().date()
    
    print(f"\n📅 Today's date: {today}")
    print("\nChecking sample stocks for latest candle dates:")
    print("-" * 50)
    
    needs_update = []
    
    for stock in sample_stocks:
        file_path = db_dir / f"{stock}.json"
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                if data and isinstance(data, list):
                    latest = data[-1]
                    timestamp = latest.get('timestamp', 'N/A')
                    close = latest.get('close', 'N/A')
                    
                    # Check if timestamp is today
                    if timestamp != 'N/A':
                        try:
                            candle_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date()
                            days_old = (today - candle_date).days
                            
                            if days_old > 0:
                                needs_update.append(stock)
                                status = f"❌ {days_old} days old"
                            else:
                                status = "✅ Up to date"
                        except:
                            candle_date = timestamp
                            days_old = "?"
                            status = "❓ Unknown date format"
                    else:
                        status = "❓ No timestamp"
                    
                    print(f"{stock:12} | Last: {timestamp[:10] if len(timestamp) > 10 else timestamp} | Close: {close:8} | {status}")
                else:
                    print(f"{stock:12} | ❌ Empty or invalid data")
            except Exception as e:
                print(f"{stock:12} | ❌ Error reading file: {e}")
        else:
            print(f"{stock:12} | ❌ File not found")
    
    print("-" * 50)
    print(f"\n📊 Summary:")
    print(f"   Stocks checked: {len(sample_stocks)}")
    print(f"   Need update: {len(needs_update)}")
    if needs_update:
        print(f"   Outdated stocks: {', '.join(needs_update)}")
    
    # Check precalculatedStorage
    print(f"\n📁 Checking precalculatedStorage:")
    precalc_dir = Path("precalculatedStorage")
    if precalc_dir.exists():
        piped_files = list(precalc_dir.glob("*_piped.json"))
        print(f"   Found {len(piped_files)} precalculated files")
        
        # Check a sample
        if piped_files:
            sample_file = piped_files[0]
            with open(sample_file, 'r') as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                print(f"   Sample ({sample_file.stem}): {len(data)} records")
    else:
        print("   ❌ Directory not found")

if __name__ == "__main__":
    check_candle_updates()