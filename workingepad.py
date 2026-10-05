import hid
import pyautogui
import time
import sys
import os
import comtypes.client
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
# Macro Deck Layout: 2x2 Grid
BUTTONS = [
    {"name": "Vol Down", "key": "volumedown", "rect": (0, 0, 160, 120)},  # Top Left
    {"name": "Vol Up",   "key": "volumeup",   "rect": (160, 0, 320, 120)}, # Top Right
    {"name": "Prev",     "key": "prevtrack",  "rect": (0, 120, 160, 240)}, # Btm Left
    {"name": "Next",     "key": "nexttrack",  "rect": (160, 120, 320, 240)} # Btm Right
]

# Paths
BMP_PATH = os.path.abspath("macro_layout.bmp")
PROG_ID = "EPadInkCtrl.Pad.1"  # Discovered from your logs

# USB IDs
VENDOR_ID = 0x04df 
PRODUCT_ID = 0x0030

# --- HELPER: Generate UI Image ---
def create_interface_bmp():
    # ePad Ink resolution is 320x240 (Standard for these devices)
    # The Developer Guide mentions screen area 319,239
    img = Image.new('RGB', (320, 240), color='white')
    d = ImageDraw.Draw(img)
    
    # Draw Grid
    d.line([(160, 0), (160, 240)], fill='black', width=2)
    d.line([(0, 120), (320, 120)], fill='black', width=2)
    
    # Draw Text
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()
        
    for btn in BUTTONS:
        x1, y1, x2, y2 = btn["rect"]
        # Calculate center
        text_w = d.textlength(btn["name"], font=font)
        tx = x1 + (160 - text_w) / 2
        ty = y1 + (120 - 20) / 2
        d.text((tx, ty), btn["name"], fill='black', font=font)
    
    # ePad expects monochrome BMP usually, but driver might handle RGB.
    # Developer guide implies bitmaps.
    img.save(BMP_PATH)
    print(f"[UI] Generated interface: {BMP_PATH}")

# --- ACTIVE_X: Screen Control ---
def init_screen():
    print(f"[Screen] Connecting to {PROG_ID}...")
    try:
        epad = comtypes.client.CreateObject(PROG_ID)
        
        # 1. Open Connection
        if epad.OpenConnection():
            print("[Screen] Connection established.")
        else:
            print("[Screen] OpenConnection returned False. (Device busy?)")
            return None

        # 2. Turn on Light
        # 0=Off, 1=On, 2=Auto
        epad.Light = 1 
        
        # 3. Load Image
        # SetBitmap(Path, Layer, ScreenID)
        # Layer 1 overwrites previous layer
        print(f"[Screen] Uploading bitmap...")
        epad.SetBitmap(BMP_PATH, 1, 100)
        
        print("[Screen] Display Updated.")
        return epad
        
    except Exception as e:
        print(f"[Screen] Error: {e}")
        return None

# --- HID: Input Handling ---
def get_clean_coord(report):
    # Extracts X, Y, Pressure from raw USB bytes
    if not report or len(report) < 6: return None, None, 0
    raw_x = report[1] | (report[2] << 8)
    raw_y = report[3] | (report[4] << 8)
    pressure = report[5]
    return (raw_x & 0x7FFF), (raw_y & 0x7FFF), pressure

def map_click(x, y):
    # Map raw coords (0-32768) to screen pixels (0-320/0-240)
    # Note: You might need to calibrate these max values based on your specific unit
    MAX_X = 28000 
    MAX_Y = 28000
    
    screen_x = (x / MAX_X) * 320
    screen_y = (y / MAX_Y) * 240
    
    for btn in BUTTONS:
        bx1, by1, bx2, by2 = btn["rect"]
        if bx1 <= screen_x <= bx2 and by1 <= screen_y <= by2:
            return btn
    return None

# --- MAIN ---
def main():
    print("--- ePad Macro Deck ---")
    
    # 1. Generate UI
    create_interface_bmp()
    
    # 2. Wake Screen
    display = init_screen()
    if not display:
        print("Warning: Screen init failed. Input might still work.")

    # 3. Input Loop
    try:
        h = hid.device()
        h.open(VENDOR_ID, PRODUCT_ID)
        h.set_nonblocking(1)
        print(f"[Input] USB HID Connected.")
    except Exception as e:
        print(f"[Input] Failed to open USB device: {e}")
        return

    print("[System] Ready. Press buttons on ePad...")
    
    last_click = 0
    
    while True:
        try:
            report = h.read(64)
            if report:
                x, y, pressure = get_clean_coord(report)
                
                # Debounce: Require pressure > 20 and 0.4s delay
                if pressure > 20 and (time.time() - last_click) > 0.4:
                    btn = map_click(x, y)
                    if btn:
                        print(f"[ACTION] {btn['name']} Triggered! (Raw: {x},{y})")
                        pyautogui.press(btn['key'])
                        last_click = time.time()
            
            time.sleep(0.01)
            
        except KeyboardInterrupt:
            print("\nExiting...")
            if display: 
                # Clean up screen
                try: display.CloseConnection() 
                except: pass
            break

if __name__ == "__main__":
    main()