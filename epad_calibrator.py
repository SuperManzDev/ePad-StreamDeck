import time
import json
import os
import tkinter as tk
from tkinter import ttk
import hid  # pip install hidapi

# --- CONFIGURATION ---
VENDOR_ID = 0x04df
PRODUCT_ID = 0x0030
CONFIG_FILE = "epad_user_config.json"

class EPadCalibrator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Touch Calibrator")
        self.geometry("400x350")
        
        # Calibration State
        self.step = 0
        self.cal_data = {
            "min_x": 0, "min_y": 0,
            "max_x": 28000, "max_y": 28000
        }
        self.raw_min_x = 99999
        self.raw_min_y = 99999
        self.raw_max_x = -99999
        self.raw_max_y = -99999
        
        self.samples = []

        # GUI
        tk.Label(self, text="CALIBRATION WIZARD", font=("Arial", 14, "bold")).pack(pady=10)
        
        self.lbl_instruction = tk.Label(self, text="Initializing...", font=("Arial", 12), fg="blue", wraplength=350)
        self.lbl_instruction.pack(pady=20)
        
        self.lbl_raw = tk.Label(self, text="Raw Input: Waiting...", font=("Consolas", 10))
        self.lbl_raw.pack(pady=5)
        
        self.btn_next = tk.Button(self, text="Next Step", state="disabled", command=self.next_step)
        self.btn_next.pack(pady=20)
        
        self.progress = ttk.Progressbar(self, orient="horizontal", length=300, mode="determinate")
        self.progress.pack(pady=10)

        # HID Init
        try:
            self.device = hid.device()
            self.device.open(VENDOR_ID, PRODUCT_ID)
            self.device.set_nonblocking(1)
            self.lbl_instruction.config(text="Step 1: Touch and HOLD the Top-Left corner of the ePad.")
            self.start_step(1)
        except Exception as e:
            self.lbl_instruction.config(text=f"Error: Could not open USB device.\n{e}", fg="red")
            self.device = None

        self.update_loop()

    def start_step(self, step_num):
        self.step = step_num
        self.samples = []
        self.btn_next.config(state="disabled")
        self.progress['value'] = 0
        
        if step_num == 1:
            self.lbl_instruction.config(text="STEP 1: Touch & HOLD the Top-Left corner.\n(Keep holding until bar fills)")
        elif step_num == 2:
            self.lbl_instruction.config(text="STEP 2: Touch & HOLD the Bottom-Right corner.\n(Keep holding until bar fills)")
        elif step_num == 3:
            self.save_config()
            self.lbl_instruction.config(text="CALIBRATION COMPLETE!\nConfig saved to 'epad_user_config.json'.\nYou can now run the Deck App.")
            self.btn_next.config(text="Close", state="normal", command=self.destroy)

    def next_step(self):
        if self.step == 1:
            # Save Min Values
            xs = [p[0] for p in self.samples]
            ys = [p[1] for p in self.samples]
            self.cal_data["min_x"] = int(sum(xs) / len(xs))
            self.cal_data["min_y"] = int(sum(ys) / len(ys))
            print(f"Captured Min: {self.cal_data['min_x']}, {self.cal_data['min_y']}")
            self.start_step(2)
        elif self.step == 2:
            # Save Max Values
            xs = [p[0] for p in self.samples]
            ys = [p[1] for p in self.samples]
            self.cal_data["max_x"] = int(sum(xs) / len(xs))
            self.cal_data["max_y"] = int(sum(ys) / len(ys))
            print(f"Captured Max: {self.cal_data['max_x']}, {self.cal_data['max_y']}")
            self.start_step(3)

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.cal_data, f)
        print("Configuration Saved.")

    def update_loop(self):
        if self.device:
            try:
                report = self.device.read(64)
                if report:
                    raw_x = report[1] | (report[2] << 8)
                    raw_y = report[3] | (report[4] << 8)
                    pressure = report[5]
                    
                    # Basic cleaning
                    x = raw_x & 0x7FFF
                    y = raw_y & 0x7FFF
                    
                    self.lbl_raw.config(text=f"Raw: X={x}, Y={y}, P={pressure}")

                    # If user is holding down (pressure > 20) and we are calibrating
                    if pressure > 20 and self.step in [1, 2]:
                        self.samples.append((x, y))
                        
                        # Update Progress
                        count = len(self.samples)
                        self.progress['value'] = count
                        
                        # Require 50 samples (~1 second of holding)
                        if count >= 50:
                            self.lbl_instruction.config(text="OK! Release finger and click Next.")
                            self.btn_next.config(state="normal")
            except: pass
            
        self.after(10, self.update_loop)

if __name__ == "__main__":
    app = EPadCalibrator()
    app.mainloop()