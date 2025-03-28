import subprocess
import sys

def run_bots():
    try:
        # Start main bot
        main_bot = subprocess.Popen([sys.executable, "bot.py"])
        
        # Start music bot
        music_bot = subprocess.Popen([sys.executable, "music_bot.py"])
        
        # Wait for both to finish
        main_bot.wait()
        music_bot.wait()
        
    except Exception as e:
        print(f"Error starting bots: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_bots() 