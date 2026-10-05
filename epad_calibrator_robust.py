import time
import json
import os
import tkinter as tk
from tkinter import ttk
import hid  # pip install hidapi
import statistics

# --- CONFIGURATION ---
VENDOR_ID = 0x04df
PRODUCT_ID = 0x0030
CONFIG_FILE = "epad_user_config.json"

class EPadRobustCalibrator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Robust Calibrator")
        self.geometry("450x400")
        
        self.step = 0
        self.samples_x = []
        self.samples_y = []
        self.cal_data = {"min_x": 0, "min_y": 0, "max_x": 28000, "max_y": 28000}
        
        # GUI
        tk.Label(self, text="ROBUST CALIBRATOR", font=("Arial", 14, "bold"), fg="blue").pack(pady=10)
        self.lbl_instr = tk.Label(self, text="Initializing...", font=("Arial", 11), wraplength=400)
        self.lbl_instr.pack(pady=15)
        
        self.lbl_debug = tk.Label(self, text="Raw: ---", font=("Consolas", 10))
        self.lbl_debug.pack(pady=5)
        
        self.progress = ttk.Progressbar(self, orient="horizontal", length=300, mode="determinate")
        self.progress.pack(pady=20)
        
        self.btn_next = tk.Button(self, text="Next Step", state="disabled", command=self.next_step)
        self.btn_next.pack(pady=10)

        # Init HID
        try:
            self.device = hid.device()
            self.device.open(VENDOR_ID, PRODUCT_ID)
            self.device.set_nonblocking(1)
            self.start_step(1)
        except Exception as e:
            self.lbl_instr.config(text=f"USB Error: {e}", fg="red")
            self.device = None

        self.update_loop()

    def start_step(self, step):
        self.step = step
        self.samples_x = []
        self.samples_y = []
        self.progress['value'] = 0
        self.btn_next.config(state="disabled")
        
        if step == 1:
            self.lbl_instr.config(text="STEP 1: Hold finger on TOP-LEFT corner.\n(Wait for bar to fill with STABLE data)")
        elif step == 2:
            self.lbl_instr.config(text="STEP 2: Hold finger on BOTTOM-RIGHT corner.\n(Wait for bar to fill with STABLE data)")
        elif step == 3:
            self.save_config()
            self.lbl_instr.config(text="DONE! Calibration saved.\nYou can now run the Deck App.")
            self.btn_next.config(text="Close", state="normal", command=self.destroy)

    def next_step(self):
        # Use MEDIAN to find the true coordinate, ignoring outliers/glitches
        if self.step == 1:
            self.cal_data["min_x"] = int(statistics.median(self.samples_x))
            self.cal_data["min_y"] = int(statistics.median(self.samples_y))
            print(f"Top-Left Set: {self.cal_data['min_x']}, {self.cal_data['min_y']}")
            self.start_step(2)
        elif self.step == 2:
            self.cal_data["max_x"] = int(statistics.median(self.samples_x))
            self.cal_data["max_y"] = int(statistics.median(self.samples_y))
            print(f"Btm-Right Set: {self.cal_data['max_x']}, {self.cal_data['max_y']}")
            self.start_step(3)

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.cal_data, f)
        print(f"Saved to {CONFIG_FILE}")

    def update_loop(self):
        if self.device:
            try:
                report = self.device.read(64)
                if report:
                    raw_x = report[1] | (report[2] << 8)
                    raw_y = report[3] | (report[4] << 8)
                    p = report[5]
                    x = raw_x & 0x7FFF
                    y = raw_y & 0x7FFF
                    
                    self.lbl_debug.config(text=f"Raw: {x},{y} (P:{p})")

                    # FILTER LOGIC:
                    # 1. Ignore Lift (P<20)
                    # 2. Ignore Zeroes (Common glitch)
                    if p > 20 and x > 0 and y > 0 and self.step < 3:
                        self.samples_x.append(x)
                        self.samples_y.append(y)
                        
                        # Limit buffer size for responsiveness
                        if len(self.samples_x) > 200:
                            self.samples_x.pop(0)
                            self.samples_y.pop(0)

                        # Update Progress Bar
                        # We need 100 samples to be confident
                        count = len(self.samples_x)
                        self.progress['value'] = min(100, count)
                        
                        if count >= 100:
                            self.btn_next.config(state="normal")
                            
            except: pass
        self.after(5, self.update_loop)

if __name__ == "__main__":
    app = EPadRobustCalibrator()
    app.mainloop()