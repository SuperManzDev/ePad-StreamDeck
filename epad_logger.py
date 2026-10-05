import time
import os
import csv
import hid  # pip install hidapi
import tkinter as tk
from datetime import datetime

# --- CONFIGURATION ---
VENDOR_ID = 0x04df 
PRODUCT_ID = 0x0030
LOG_FILE = "epad_master_log.csv"

# Calibration Defaults (Standard ePad)
MAX_RAW_X = 28000.0
MAX_RAW_Y = 28000.0

# Visualization Scale (2x size for better visibility on PC)
WINDOW_W = 640
WINDOW_H = 480
SCALE_X = WINDOW_W / MAX_RAW_X
SCALE_Y = WINDOW_H / MAX_RAW_Y

class EPadVisualizer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Input Visualizer & Logger")
        self.geometry("660x650")
        
        # --- LOGGING SETUP ---
        self.log_file = open(LOG_FILE, "w", newline='')
        self.writer = csv.writer(self.log_file)
        self.writer.writerow(["TIMESTAMP", "RAW_X", "RAW_Y", "PRESSURE", "BUTTON_GUESS"])
        print(f"Logging to {LOG_FILE}...")

        # --- GUI LAYOUT ---
        # 1. Header
        tk.Label(self, text="LIVE INPUT VISUALIZER", font=("Arial", 14, "bold"), fg="red").pack(pady=5)
        tk.Label(self, text="Red Dots = Where ePad thinks your finger is", font=("Arial", 10)).pack()
        
        # 2. Canvas (The Virtual Screen)
        self.canvas = tk.Canvas(self, width=WINDOW_W, height=WINDOW_H, bg="black")
        self.canvas.pack(pady=10, padx=10)
        
        # Draw Button Zones (Visual Guide)
        w3 = WINDOW_W // 3
        # Prev Zone (Blue outline)
        self.canvas.create_rectangle(2, 2, w3, WINDOW_H, outline="#3333FF", width=2, dash=(4, 4))
        self.canvas.create_text(w3//2, 30, text="PREV ZONE", fill="#3333FF", font=("Arial", 12, "bold"))
        # Play Zone (Green outline)
        self.canvas.create_rectangle(w3, 2, w3*2, WINDOW_H, outline="#33FF33", width=2, dash=(4, 4))
        self.canvas.create_text(w3 + w3//2, 30, text="PLAY ZONE", fill="#33FF33", font=("Arial", 12, "bold"))
        # Next Zone (Red outline)
        self.canvas.create_rectangle(w3*2, 2, WINDOW_W, WINDOW_H, outline="#FF3333", width=2, dash=(4, 4))
        self.canvas.create_text(w3*2 + w3//2, 30, text="NEXT ZONE", fill="#FF3333", font=("Arial", 12, "bold"))

        # 3. Footer Stats
        self.lbl_raw = tk.Label(self, text="Waiting for USB...", font=("Consolas", 12), fg="blue")
        self.lbl_raw.pack(pady=5)

        # State
        self.device = None
        self.dot_ids = [] # Store dots to remove them later (trail effect)
        
        # --- INIT HARDWARE ---
        self.connect_hid()
        self.update_loop()

    def connect_hid(self):
        try:
            self.device = hid.device()
            self.device.open(VENDOR_ID, PRODUCT_ID)
            self.device.set_nonblocking(1)
            self.lbl_raw.config(text="USB CONNECTED - TOUCH THE SCREEN")
        except Exception as e:
            self.lbl_raw.config(text=f"USB ERROR: {e}", fg="red")

    def draw_dot(self, x, y, p):
        # 1. Convert Raw -> Screen Pixels
        # Standard ePad coords are usually inverted on Y, let's see.
        screen_x = int(x * SCALE_X)
        screen_y = int(y * SCALE_Y)
        
        # 2. Color based on pressure (Light=Yellow, Hard=Red)
        color = "#FFFF00"
        if p > 100: color = "#FF0000"
        
        # 3. Draw Dot
        r = 4 # Radius
        dot_id = self.canvas.create_oval(screen_x-r, screen_y-r, screen_x+r, screen_y+r, fill=color, outline="")
        
        # 4. Manage Trail (Keep last 50 dots)
        self.dot_ids.append(dot_id)
        if len(self.dot_ids) > 50:
            oldest = self.dot_ids.pop(0)
            self.canvas.delete(oldest)

        # 5. Determine Zone for Log
        zone = "UNKNOWN"
        w3 = WINDOW_W // 3
        if screen_x < w3: zone = "PREV"
        elif screen_x < w3*2: zone = "PLAY"
        else: zone = "NEXT"
        
        return zone, screen_x, screen_y

    def update_loop(self):
        if self.device:
            try:
                # Read 64 bytes
                report = self.device.read(64)
                if report:
                    # Parse
                    raw_x = report[1] | (report[2] << 8)
                    raw_y = report[3] | (report[4] << 8)
                    pressure = report[5]
                    
                    # Clean
                    x = raw_x & 0x7FFF
                    y = raw_y & 0x7FFF

                    # VISUALIZE
                    if pressure > 0:
                        zone, sx, sy = self.draw_dot(x, y, pressure)
                        
                        # Update Text
                        self.lbl_raw.config(text=f"RAW: {x},{y} (P:{pressure})  -->  SCREEN: {sx},{sy} [{zone}]")
                        
                        # LOG
                        t_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        self.writer.writerow([t_str, x, y, pressure, zone])
                        
            except Exception as e:
                print(e)
        
        # Run FAST (2ms) to catch every single glitch
        self.after(2, self.update_loop)

    def on_close(self):
        if self.log_file:
            self.log_file.close()
        self.destroy()

if __name__ == "__main__":
    app = EPadVisualizer()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()