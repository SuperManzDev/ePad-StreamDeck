import time
import os
import comtypes.client

# --- CONFIGURATION ---
PROG_ID = "EPadInkCtrl.Pad.1"
WATCH_FILE = os.path.abspath("bridge_feed.bmp")

def main():
    print("--- ePad Driver Server (32-bit) ---")
    print(f"Watching: {WATCH_FILE}")
    
    try:
        epad = comtypes.client.CreateObject(PROG_ID)
        epad.OpenConnection()
        epad.Light = 1
        print("SUCCESS: USB Connected.")
    except Exception as e:
        print(f"FATAL: {e}")
        return

    last_mod = 0
    
    while True:
        try:
            if os.path.exists(WATCH_FILE):
                try:
                    mod = os.path.getmtime(WATCH_FILE)
                    if mod > last_mod:
                        # Wait 10ms for file write to complete
                        time.sleep(0.01)
                        epad.SetBitmap(WATCH_FILE, 1, 0)
                        last_mod = mod
                except: 
                    # If file is locked, just skip this frame
                    pass
            
            # Keep driver alive
            comtypes.client.PumpEvents(0.001)
            
        except KeyboardInterrupt: break
        except: time.sleep(0.1)

if __name__ == "__main__":
    main()