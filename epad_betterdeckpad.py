import time
import os
import ctypes
import winsound
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
import comtypes.client
import hid  # pip install hidapi
import math

# --- CONFIGURATION ---
PROG_ID = "EPadInkCtrl.Pad.1"
BUFFER_FILE = os.path.abspath("deck_buffer.bmp")
WIDTH, HEIGHT = 320, 240

# --- USB SETTINGS ---
VENDOR_ID = 0x04df 
PRODUCT_ID = 0x0030
# Your log showed values up to 32257, so we adjusted the Max
MAX_X_RAW = 32768.0 
MAX_Y_RAW = 32768.0

# --- THE TELEPORT FILTER ---
# Maximum distance (in raw units) a finger can move per frame.
# If it jumps more than this, we treat it as a glitch.
JUMP_LIMIT = 5000 
# How many frames a "glitch" must persist to be accepted as a real movement
GLITCH_TOLERANCE = 5 

# --- MEDIA KEYS ---
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002

def press_key(vk_code):
    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)

class EPadDeckTeleportFix(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Deck (Teleport Fix)")
        self.geometry("350x550")
        
        # --- STATE ---
        self.driver_active = False
        self.epad = None
        self.hid_device = None
        self.active_button = None
        self.last_press_time = 0
        
        # Filter State
        self.last_valid_x = None
        self.last_valid_y = None
        self.glitch_counter = 0
        self.held_candidate_x = 0

        # --- GUI ---
        tk.Label(self, text="FILTER DIAGNOSTICS", font=("Arial", 10, "bold")).pack(pady=5)
        self.lbl_status = tk.Label(self, text="Waiting...", font=("Consolas", 9), fg="blue")
        self.lbl_status.pack()
        
        self.lbl_action = tk.Label(self, text="---", font=("Arial", 14, "bold"), fg="green")
        self.lbl_action.pack(pady=5)

        # Preview
        self.canvas_preview = tk.Canvas(self, width=WIDTH, height=HEIGHT, bg="#333")
        self.canvas_preview.pack(pady=10)
        self.tk_img = None
        self.bg_id = self.canvas_preview.create_image(0, 0, anchor="nw")
        
        # Touch Indicator Dot
        self.dot_id = self.canvas_preview.create_oval(-10, -10, -5, -5, fill="red", outline="white")

        # --- INIT ---
        self.init_screen()
        self.init_hid()
        self.update_display()
        self.hid_loop() 
        self.screen_loop()

    def init_screen(self):
        try:
            self.epad = comtypes.client.CreateObject(PROG_ID)
            self.epad.OpenConnection()
            self.epad.Light = 1
            self.driver_active = True
        except: pass

    def init_hid(self):
        try:
            self.hid_device = hid.device()
            self.hid_device.open(VENDOR_ID, PRODUCT_ID)
            self.hid_device.set_nonblocking(1)
            self.lbl_status.config(text="USB CONNECTED")
        except Exception as e:
            self.lbl_status.config(text=f"USB ERROR: {e}", fg="red")

    def hid_loop(self):
        if self.hid_device:
            try:
                report = self.hid_device.read(64)
                if report:
                    # Parse
                    raw_x = report[1] | (report[2] << 8)
                    raw_y = report[3] | (report[4] << 8)
                    pressure = report[5]
                    
                    x = raw_x & 0x7FFF
                    y = raw_y & 0x7FFF
                    
                    # Log raw data for UI
                    # self.lbl_status.config(text=f"Raw: {x} P:{pressure}")
                    
                    self.process_filter(x, y, pressure)
                else:
                    self.process_filter(None, None, 0)
            except: pass
        self.after(5, self.hid_loop)

    def process_filter(self, x, y, pressure):
        # 1. LIFT Logic
        if pressure < 50 or x is None:
            self.last_valid_x = None
            self.last_valid_y = None
            self.glitch_counter = 0
            if self.active_button:
                self.active_button = None
                self.update_display()
            return

        # 2. TELEPORT FILTER
        # If this is the first touch, accept it
        if self.last_valid_x is None:
            self.last_valid_x = x
            self.last_valid_y = y
            self.handle_valid_touch(x, y)
            return

        # Calculate Distance from last known valid point
        dist = math.sqrt((x - self.last_valid_x)**2 + (y - self.last_valid_y)**2)

        if dist < JUMP_LIMIT:
            # Valid movement -> Update trackers
            self.last_valid_x = x
            self.last_valid_y = y
            self.glitch_counter = 0
            self.handle_valid_touch(x, y)
        else:
            # INVALID JUMP DETECTED
            self.lbl_status.config(text=f"Glitch Blocked! (Jump: {int(dist)})", fg="orange")
            
            # Check if it persists (maybe user actually moved fast?)
            self.glitch_counter += 1
            if self.glitch_counter > GLITCH_TOLERANCE:
                # Okay, it's real, snap to it
                self.last_valid_x = x
                self.last_valid_y = y
                self.glitch_counter = 0

    def handle_valid_touch(self, raw_x, raw_y):
        # Map to Screen
        sx = int((raw_x / MAX_X_RAW) * WIDTH)
        sy = int((raw_y / MAX_Y_RAW) * HEIGHT)
        
        # Update Visual Dot
        self.canvas_preview.coords(self.dot_id, sx-5, sy-5, sx+5, sy+5)

        # Map to Buttons
        btn = "UNKNOWN"
        if sx < 106: btn = "PREV"
        elif sx < 213: btn = "PLAY"
        else: btn = "NEXT"

        # Trigger
        now = time.time()
        if btn != self.active_button and (now - self.last_press_time > 0.4):
            self.active_button = btn
            self.last_press_time = now
            
            self.lbl_action.config(text=f"ACTION: {btn}")
            self.trigger_action(btn)
            self.update_display()

    def trigger_action(self, btn):
        try: winsound.Beep(800, 100)
        except: pass
        if btn == "PREV": press_key(VK_MEDIA_PREV_TRACK)
        elif btn == "PLAY": press_key(VK_MEDIA_PLAY_PAUSE)
        elif btn == "NEXT": press_key(VK_MEDIA_NEXT_TRACK)

    def draw_interface(self):
        img = Image.new("1", (WIDTH, HEIGHT), 1)
        d = ImageDraw.Draw(img)
        zw = WIDTH // 3

        btns = ["PREV", "PLAY", "NEXT"]
        for i, b_name in enumerate(btns):
            x1 = i * zw
            x2 = x1 + zw
            if i == 2: x2 = WIDTH
            
            is_pressed = (self.active_button == b_name)
            bg = 0 if is_pressed else 1
            fg = 1 if is_pressed else 0
            
            d.rectangle([x1, 0, x2, HEIGHT], fill=bg)
            d.line([x2, 0, x2, HEIGHT], fill=0)
            
            cx, cy = x1 + (zw//2), HEIGHT // 2
            d.text((cx-15, cy-5), b_name, fill=fg)

        return img

    def update_display(self):
        img = self.draw_interface()
        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas_preview.itemconfig(self.bg_id, image=self.tk_img)
        
        if self.driver_active:
            try:
                send_img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                send_img.save(BUFFER_FILE)
                self.epad.SetBitmap(BUFFER_FILE, 1, 0)
                self.epad.Light = 1
            except: pass

    def screen_loop(self):
        if self.driver_active:
            try: comtypes.client.PumpEvents(0.01)
            except: pass
        self.after(100, self.screen_loop)

if __name__ == "__main__":
    app = EPadDeckTeleportFix()
    app.mainloop()