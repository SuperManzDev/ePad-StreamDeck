import time
import os
import threading
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageGrab, ImageEnhance, ImageTk
import comtypes.client
import pythoncom

# --- CONFIGURATION ---
PROG_ID = "EPadInkCtrl.Pad.1"
BUFFER_FILE = os.path.abspath("mirror_buffer.bmp")
WIDTH, HEIGHT = 320, 240

class EPadMirrorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ePad Mirror Command Center")
        self.root.geometry("500x450")
        self.root.resizable(False, False)

        # --- STATE ---
        self.running = False
        self.thread = None
        self.driver_active = False
        self.epad = None
        
        # Default Settings
        self.setting_contrast = 1.5
        self.setting_delay = 0.05 # Faster default
        self.force_clear_flag = False

        # --- GUI LAYOUT ---
        self.create_gui()
        
        # --- START DRIVER THREAD ---
        self.start_mirroring()

    def create_gui(self):
        # 1. Preview Area
        frame_preview = ttk.LabelFrame(self.root, text="Live Preview (What ePad sees)")
        frame_preview.pack(pady=10, padx=10, fill="both", expand=True)

        self.lbl_preview = tk.Label(frame_preview, bg="gray")
        self.lbl_preview.pack(pady=10)

        # 2. Controls Area
        frame_controls = ttk.LabelFrame(self.root, text="Command Center")
        frame_controls.pack(pady=5, padx=10, fill="x")

        # Contrast Slider
        lbl_cont = ttk.Label(frame_controls, text="Contrast:")
        lbl_cont.grid(row=0, column=0, padx=5, pady=5, sticky="e")
        
        self.scale_contrast = ttk.Scale(frame_controls, from_=0.5, to=4.0, command=self.update_settings)
        self.scale_contrast.set(self.setting_contrast)
        self.scale_contrast.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Speed Slider
        lbl_speed = ttk.Label(frame_controls, text="Upload Delay:")
        lbl_speed.grid(row=1, column=0, padx=5, pady=5, sticky="e")
        
        self.scale_speed = ttk.Scale(frame_controls, from_=0.0, to=1.0, command=self.update_settings)
        self.scale_speed.set(self.setting_delay)
        self.scale_speed.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # Buttons
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=10, fill="x")

        self.btn_clear = ttk.Button(btn_frame, text="FORCE CLEAR / FLASH", command=self.trigger_force_clear)
        self.btn_clear.pack(side="left", padx=20, expand=True, fill="x")
        
        self.btn_toggle = ttk.Button(btn_frame, text="STOP STREAM", command=self.toggle_stream)
        self.btn_toggle.pack(side="right", padx=20, expand=True, fill="x")

        # Status Bar
        self.status_var = tk.StringVar(value="Initializing...")
        lbl_status = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor="w")
        lbl_status.pack(side="bottom", fill="x")

    def update_settings(self, _=None):
        self.setting_contrast = float(self.scale_contrast.get())
        self.setting_delay = float(self.scale_speed.get())

    def toggle_stream(self):
        self.running = not self.running
        if self.running:
            self.btn_toggle.config(text="STOP STREAM")
            self.start_mirroring()
        else:
            self.btn_toggle.config(text="START STREAM")
            self.status_var.set("Stream Paused")

    def trigger_force_clear(self):
        self.force_clear_flag = True

    def start_mirroring(self):
        if self.thread and self.thread.is_alive():
            return
        self.running = True
        self.thread = threading.Thread(target=self.worker_loop, daemon=True)
        self.thread.start()

    def worker_loop(self):
        # Initialize COM for this thread
        try:
            pythoncom.CoInitialize()
            self.epad = comtypes.client.CreateObject(PROG_ID)
            self.driver_active = True
            # Wake up the pad immediately
            try:
                self.epad.OpenConnection()
                self.epad.Light = 1
            except: pass
            self.root.after(0, lambda: self.status_var.set("Connected to ePad Driver"))
        except Exception as e:
            self.driver_active = False
            self.root.after(0, lambda: self.status_var.set(f"Driver Error: {e}"))

        while self.running:
            loop_start = time.time()

            # CRITICAL: Pump messages so the ActiveX driver doesn't freeze/crash
            if self.driver_active:
                try:
                    comtypes.client.PumpEvents(0.01)
                except:
                    pass

            try:
                # 1. Capture & Process
                screen = ImageGrab.grab()
                frame = screen.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
                
                enhancer = ImageEnhance.Contrast(frame)
                frame = enhancer.enhance(self.setting_contrast)

                # Keep copy for GUI
                frame_preview = frame.copy()

                # 2. Update GUI
                self.update_preview_image(frame_preview)

                # 3. Handle ePad Update
                if self.driver_active:
                    # Prepare image for ePad
                    if self.force_clear_flag:
                        save_img = Image.new("RGB", (WIDTH, HEIGHT), "white")
                        self.force_clear_flag = False
                        self.root.after(0, lambda: self.status_var.set("Screen Cleared"))
                    else:
                        # FLIP_TOP_BOTTOM is required for this specific driver
                        save_img = frame.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                        # Ensure it is RGB (removing alpha channel if present)
                        save_img = save_img.convert("RGB")

                    # Save Buffer
                    save_img.save(BUFFER_FILE)
                    
                    # TINY SLEEP to ensure file lock is released by OS before driver reads it
                    time.sleep(0.02)

                    # Send to Device
                    try:
                        self.epad.SetBitmap(BUFFER_FILE, 1, 0)
                        self.epad.Light = 1  # Trigger refresh
                    except Exception as cx:
                        # If Access Violation happens, it usually means driver is busy or file is locked
                        # We just skip this frame instead of crashing the app
                        print(f"Frame Drop: {cx}")

            except Exception as e:
                print(f"Loop Error: {e}")

            # 4. Speed Control
            delay = self.setting_delay
            process_time = time.time() - loop_start
            actual_sleep = max(0, delay - process_time)
            time.sleep(actual_sleep)

    def update_preview_image(self, pil_image):
        def _update():
            tk_img = ImageTk.PhotoImage(pil_image)
            self.lbl_preview.config(image=tk_img)
            self.lbl_preview.image = tk_img
        self.root.after(0, _update)

if __name__ == "__main__":
    root = tk.Tk()
    app = EPadMirrorApp(root)
    root.mainloop()