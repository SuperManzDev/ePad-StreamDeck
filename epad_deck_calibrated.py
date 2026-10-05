import time
import os
import json
import ctypes
import winsound
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
import comtypes.client
import hid
import statistics

# --- LOAD USER CONFIG ---
CONFIG_FILE = "epad_user_config.json"
CAL = {"min_x": 0, "min_y": 0, "max_x": 28000, "max_y": 28000}

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r") as f:
            CAL = json.load(f)
        print(f"Loaded Calibration: {CAL}")
    except: pass
else:
    print("Using Defaults (Run Calibrator first!)")

# --- CONFIG ---
PROG_ID = "EPadInkCtrl.Pad.1"
BUFFER_FILE = os.path.abspath("deck_buffer.bmp")
WIDTH, HEIGHT = 320, 240
VENDOR_ID = 0x04df 
PRODUCT_ID = 0x0030

# --- FILTER SETTINGS ---
FILTER_WINDOW = 5  # Median Filter Size (Higher = Smoother, Slower)

# --- MEDIA KEYS ---
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002

def press_key(vk_code):
    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)

class EPadDeckCalibrated(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Deck (Calibrated)")
        self.geometry("350x500")
        
        self.driver_active = False
        self.epad = None
        self.hid = None
        self.active_btn = None
        self.last_press = 0
        
        # Buffer for Median Filter
        self.x_buf = []

        # UI
        tk.Label(self, text="CALIBRATED DECK", font=("Arial", 12, "bold")).pack(pady=10)
        self.lbl_status = tk.Label(self, text="Waiting...", font=("Consolas", 10))
        self.lbl_status.pack()
        
        self.canvas = tk.Canvas(self, width=WIDTH, height=HEIGHT, bg="#333")
        self.canvas.pack(pady=10)
        self.bg_id = self.canvas.create_image(0, 0, anchor="nw")
        
        self.init_hw()
        self.update_display()
        self.hid_loop()
        self.screen_loop()

    def init_hw(self):
        try:
            self.epad = comtypes.client.CreateObject(PROG_ID)
            self.epad.OpenConnection()
            self.epad.Light = 1
            self.driver_active = True
        except: pass
        
        try:
            self.hid = hid.device()
            self.hid.open(VENDOR_ID, PRODUCT_ID)
            self.hid.set_nonblocking(1)
            self.lbl_status.config(text="USB & Screen Ready", fg="green")
        except Exception as e:
            self.lbl_status.config(text=f"USB Error: {e}", fg="red")

    def hid_loop(self):
        if self.hid:
            try:
                report = self.hid.read(64)
                if report:
                    raw_x = report[1] | (report[2] << 8)
                    p = report[5]
                    x = raw_x & 0x7FFF
                    
                    self.process_input(x, p)
                else:
                    self.process_input(None, 0)
            except: pass
        self.after(5, self.hid_loop)

    def process_input(self, x, p):
        # 1. Lift Detection
        if p < 50:
            self.x_buf.clear()
            if self.active_btn:
                self.active_btn = None
                self.update_display()
            return

        # 2. Add to Filter Buffer
        self.x_buf.append(x)
        if len(self.x_buf) > FILTER_WINDOW:
            self.x_buf.pop(0)
            
        # 3. Apply Median (Removes Teleport Glitches)
        if len(self.x_buf) == FILTER_WINDOW:
            stable_x = statistics.median(self.x_buf)
            self.map_click(stable_x)

    def map_click(self, raw_x):
        # 4. Apply Calibration
        # Formula: (x - min) / (max - min)
        min_x = CAL["min_x"]
        max_x = CAL["max_x"]
        
        # Avoid division by zero
        denom = max_x - min_x
        if denom == 0: denom = 1
        
        norm_x = (raw_x - min_x) / denom
        norm_x = max(0.0, min(1.0, norm_x)) # Clamp to screen
        
        px = int(norm_x * WIDTH)
        
        # 5. Zones
        btn = "UNKNOWN"
        if px < 106: btn = "PREV"
        elif px < 213: btn = "PLAY"
        else: btn = "NEXT"
        
        # 6. Trigger
        now = time.time()
        if btn != self.active_btn and (now - self.last_press > 0.4):
            self.active_btn = btn
            self.last_press = now
            print(f"Action: {btn}")
            self.trigger(btn)
            self.update_display()

    def trigger(self, btn):
        try: winsound.Beep(800, 100)
        except: pass
        if btn == "PREV": press_key(VK_MEDIA_PREV_TRACK)
        elif btn == "PLAY": press_key(VK_MEDIA_PLAY_PAUSE)
        elif btn == "NEXT": press_key(VK_MEDIA_NEXT_TRACK)

    def update_display(self):
        img = Image.new("1", (WIDTH, HEIGHT), 1)
        d = ImageDraw.Draw(img)
        zw = WIDTH // 3
        
        btns = ["PREV", "PLAY", "NEXT"]
        for i, b in enumerate(btns):
            x1 = i * zw
            x2 = x1 + zw if i < 2 else WIDTH
            fill = 0 if self.active_btn == b else 1
            fg = 1 if self.active_btn == b else 0
            
            d.rectangle([x1, 0, x2, HEIGHT], fill=fill)
            d.line([x2, 0, x2, HEIGHT], fill=0)
            cx, cy = x1 + zw//2, HEIGHT//2
            d.text((cx-15, cy-5), b, fill=fg)

        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.itemconfig(self.bg_id, image=self.tk_img)
        
        if self.driver_active:
            try:
                b = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                b.save(BUFFER_FILE)
                self.epad.SetBitmap(BUFFER_FILE, 1, 0)
                self.epad.Light = 1
            except: pass

    def screen_loop(self):
        if self.driver_active:
            try: comtypes.client.PumpEvents(0.01)
            except: pass
        self.after(100, self.screen_loop)

if __name__ == "__main__":
    app = EPadDeckCalibrated()
    app.mainloop()