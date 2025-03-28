import sys
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os

class ChangeHandler(FileSystemEventHandler):
    def __init__(self, restart_bot):
        self.restart_bot = restart_bot
        self.last_modified = {}
        self.cooldown = 2  # Cooldown period in seconds
        
    def on_modified(self, event):
        if event.src_path.endswith(('.py', '.txt', '.json')):
            current_time = time.time()
            file_path = os.path.abspath(event.src_path)
            
            # Check if file was modified recently
            if file_path in self.last_modified:
                if current_time - self.last_modified[file_path] < self.cooldown:
                    return  # Skip if modified too recently
                
            self.last_modified[file_path] = current_time
            print(f"\nChange detected in {os.path.basename(event.src_path)}")
            self.restart_bot()

def run_bot():
    process = None
    observer = None
    
    try:
        while True:
            if process is None:
                print("\nStarting bot...")
                process = subprocess.Popen([sys.executable, "bot.py"])
                
                # Setup file watcher
                if observer is None:
                    event_handler = ChangeHandler(lambda: restart_bot(process))
                    observer = Observer()
                    observer.schedule(event_handler, path=".", recursive=False)
                    observer.start()
            
            # Check if process is still running
            if process.poll() is not None:
                process = None  # Reset process if it died
                continue
                
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        if process and process.poll() is None:
            process.terminate()
            process.wait()
        if observer:
            observer.stop()
            observer.join()

def restart_bot(process):
    if process and process.poll() is None:
        process.terminate()
        process.wait()
    global should_restart
    should_restart = True

if __name__ == "__main__":
    run_bot() 