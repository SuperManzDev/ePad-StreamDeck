import time
import os
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageGrab, ImageEnhance, ImageTk
import comtypes.client

# --- CONFIGURATION ---
PROG_ID = "EPadInkCtrl.Pad.1"
BUFFER_FILE = os.path.abspath("stream_buffer.bmp")
WIDTH, HEIGHT = 320, 240 # Native ePad resolution

class HollowCaptureWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Capture Zone")
        self.geometry("400x300+100+100")
        self.attributes("-topmost", True)
        
        # KEY TRICK: Transparent Color
        self.configure(bg='fuchsia')
        self.attributes("-transparentcolor", "fuchsia")
        
        # Create the visual "Border" (Green this time for visibility)
        self.canvas = tk.Canvas(self, bg="fuchsia", highlightthickness=5, highlightbackground="#00FF00")
        self.canvas.pack(fill="both", expand=True)
        
        # Resolution Label
        self.lbl_info = tk.Label(self, text="400x300", bg="#00FF00", fg="black", font=("Arial", 10, "bold"))
        self.lbl_info.place(x=10, y=260) 
        
        self.bind("<Configure>", self.update_dims)

    def update_dims(self, event):
        w, h = self.winfo_width(), self.winfo_height()
        self.lbl_info.config(text=f"{w}x{h}")
        self.lbl_info.place(y=h-25)

class EPadStreamerPro(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Streamer PRO (Stable CPU)")
        self.geometry("450x650")
        self.resizable(False, False)

        # --- STATE ---
        self.driver_active = False
        self.epad = None
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.is_fullscreen = False
        
        # --- SETTINGS ---
        self.use_turbo = tk.BooleanVar(value=True) # Default to Speed
        self.setting_contrast = 1.5
        self.setting_brightness = 1.0
        
        # --- GUI ---
        self.create_gui()
        
        # --- OVERLAY ---
        self.capture_win = HollowCaptureWindow(self)
        
        # --- DRIVER ---
        self.init_driver()
        
        # --- START ---
        self.update_loop()

    def create_gui(self):
        style = ttk.Style()
        style.configure("Big.TButton", font=("Arial", 10, "bold"))

        # 1. MONITOR PREVIEW
        tk.Label(self, text="ePad Output Preview", font=("Arial", 9, "bold")).pack(pady=(10,0))
        self.lbl_preview = tk.Label(self, bg="#222", width=320, height=240)
        self.lbl_preview.pack(pady=5)

        # 2. SOURCE SELECTION
        frame_src = ttk.LabelFrame(self, text="Source Selection")
        frame_src.pack(fill="x", padx=10, pady=5)
        
        self.btn_fs = ttk.Button(frame_src, text="SWITCH TO FULL SCREEN", style="Big.TButton", command=self.toggle_fullscreen)
        self.btn_fs.pack(fill="x", padx=10, pady=10)
        
        self.lbl_status = tk.Label(frame_src, text="Current Mode: REGION (Green Box)", fg="green", font=("Arial", 10))
        self.lbl_status.pack(pady=(0, 10))

        # 3. IMAGE CONTROLS
        frame_ctrl = ttk.LabelFrame(self, text="Image Adjustments")
        frame_ctrl.pack(fill="x", padx=10, pady=5)

        # Brightness
        tk.Label(frame_ctrl, text="Brightness").grid(row=0, column=0, sticky="e", padx=5)
        self.scale_bright = ttk.Scale(frame_ctrl, from_=0.5, to=2.0, value=1.0, command=self.update_vals)
        self.scale_bright.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        
        # Contrast
        tk.Label(frame_ctrl, text="Contrast").grid(row=1, column=0, sticky="e", padx=5)
        self.scale_cont = ttk.Scale(frame_ctrl, from_=0.5, to=3.0, value=1.5, command=self.update_vals)
        self.scale_cont.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        # 4. PERFORMANCE
        frame_perf = ttk.LabelFrame(self, text="Performance")
        frame_perf.pack(fill="x", padx=10, pady=5)
        
        self.chk_turbo = ttk.Checkbutton(frame_perf, text="TURBO MODE (Low Quality, Max FPS)", variable=self.use_turbo)
        self.chk_turbo.pack(anchor="w", padx=10, pady=5)
        
        # FPS Counter
        self.lbl_fps = tk.Label(frame_perf, text="FPS: 0", font=("Consolas", 14, "bold"), fg="blue")
        self.lbl_fps.pack(anchor="e", padx=10, pady=5)

        # 5. UTILS
        ttk.Button(self, text="FORCE CLEAR SCREEN", command=self.force_clear).pack(fill="x", padx=20, pady=20)

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.capture_win.withdraw() # Hide the box
            self.btn_fs.config(text="SWITCH TO REGION (GREEN BOX)")
            self.lbl_status.config(text="Current Mode: FULL SCREEN", fg="red")
        else:
            self.capture_win.deiconify() # Show the box
            self.btn_fs.config(text="SWITCH TO FULL SCREEN")
            self.lbl_status.config(text="Current Mode: REGION (Green Box)", fg="green")

    def update_vals(self, _=None):
        self.setting_brightness = float(self.scale_bright.get())
        self.setting_contrast = float(self.scale_cont.get())

    def init_driver(self):
        try:
            self.epad = comtypes.client.CreateObject(PROG_ID)
            self.epad.OpenConnection()
            self.epad.Light = 1
            self.driver_active = True
        except:
            self.driver_active = False
            self.lbl_status.config(text="DRIVER NOT FOUND - SIMULATION", fg="orange")

    def force_clear(self):
        if self.driver_active:
            try:
                white = Image.new("1", (WIDTH, HEIGHT), 1)
                white.save(BUFFER_FILE)
                self.epad.SetBitmap(BUFFER_FILE, 1, 0)
                self.epad.Light = 1
            except: pass

    def update_loop(self):
        # 1. Pump Events (Essential for App Response)
        if self.driver_active:
            try: comtypes.client.PumpEvents(0.001)
            except: pass
            
        try:
            # --- A. CAPTURE & SAFETY CHECK ---
            if self.is_fullscreen:
                screen = ImageGrab.grab()
            else:
                # Calculate coordinates
                x = self.capture_win.winfo_rootx() + 5  # +5 for border thickness
                y = self.capture_win.winfo_rooty() + 5
                w = self.capture_win.winfo_width() - 10
                h = self.capture_win.winfo_height() - 10
                
                # CRITICAL CRASH FIX:
                # If window is collapsed or invalid, skip this frame
                if w <= 0 or h <= 0:
                    self.after(10, self.update_loop)
                    return

                screen = ImageGrab.grab(bbox=(x, y, x+w, y+h))

            # --- B. RESIZE ---
            # Turbo Mode = NEAREST (Fastest). Quality = BILINEAR (Better Text)
            algo = Image.Resampling.NEAREST if self.use_turbo.get() else Image.Resampling.BILINEAR
            frame = screen.resize((WIDTH, HEIGHT), algo)

            # --- C. ENHANCE ---
            # Brightness
            if self.setting_brightness != 1.0:
                frame = ImageEnhance.Brightness(frame).enhance(self.setting_brightness)
            # Contrast
            if self.setting_contrast != 1.0:
                frame = ImageEnhance.Contrast(frame).enhance(self.setting_contrast)

            # --- D. DITHER/CONVERT ---
            if self.use_turbo.get():
                # Fast Thresholding (No Dithering calculation)
                final = frame.convert("1", dither=Image.Dither.NONE)
            else:
                # Pretty Dithering (Floyd-Steinberg)
                final = frame.convert("1", dither=Image.Dither.FLOYDSTEINBERG)

            # --- E. UPDATE PREVIEW ---
            self.tk_img = ImageTk.PhotoImage(final)
            self.lbl_preview.config(image=self.tk_img)

            # --- F. UPLOAD ---
            if self.driver_active:
                # Flip vertically for ePad driver
                send_img = final.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                send_img.save(BUFFER_FILE)
                self.epad.SetBitmap(BUFFER_FILE, 1, 0)
                self.epad.Light = 1

        except Exception as e:
            # Catch grab errors without crashing the whole app
            print(f"Loop Error: {e}")

        # --- FPS COUNTER ---
        self.frame_count += 1
        if time.time() - self.last_fps_time >= 1.0:
            self.lbl_fps.config(text=f"FPS: {self.frame_count}")
            self.frame_count = 0
            self.last_fps_time = time.time()

        # --- LOOP CONTROL ---
        self.after(1, self.update_loop)

if __name__ == "__main__":
    app = EPadStreamerPro()
    app.mainloop()