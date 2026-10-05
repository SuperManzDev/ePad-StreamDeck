import time
import os
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageGrab, ImageTk, ImageEnhance, ImageOps

# --- CONFIGURATION ---
BRIDGE_FILE = os.path.abspath("bridge_feed.bmp")
WIDTH, HEIGHT = 320, 240

class UltimateCaster(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Ultimate Caster (Collision Proof)")
        self.geometry("500x650")
        self.configure(bg="#1e1e1e")
        
        # --- UI STYLING ---
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", background="#1e1e1e", foreground="white")
        style.configure("TScale", background="#1e1e1e")
        style.configure("TCheckbutton", background="#1e1e1e", foreground="white")
        
        # --- HEADER ---
        tk.Label(self, text="ULTIMATE CASTER", font=("Segoe UI", 16, "bold"), bg="#1e1e1e", fg="#00ff00").pack(pady=10)
        
        # --- PREVIEW AREA ---
        self.canvas = tk.Canvas(self, width=WIDTH, height=HEIGHT, bg="black", highlightthickness=0)
        self.canvas.pack(pady=5)
        self.bg_id = self.canvas.create_image(0, 0, anchor="nw")

        # --- CONTROLS FRAME ---
        ctrl_frame = tk.Frame(self, bg="#2d2d2d", padx=10, pady=10)
        ctrl_frame.pack(fill="x", padx=10, pady=10)

        # 1. Rotation
        tk.Label(ctrl_frame, text="Rotation:", bg="#2d2d2d", fg="white").grid(row=0, column=0, sticky="w")
        self.var_rot = tk.IntVar(value=0)
        self.slider_rot = ttk.Scale(ctrl_frame, from_=0, to=270, orient="horizontal", variable=self.var_rot, command=self.snap_rotation)
        self.slider_rot.grid(row=0, column=1, sticky="ew", padx=5)
        self.lbl_rot = tk.Label(ctrl_frame, text="0°", bg="#2d2d2d", fg="cyan", width=4)
        self.lbl_rot.grid(row=0, column=2)

        # 2. Contrast
        tk.Label(ctrl_frame, text="Contrast:", bg="#2d2d2d", fg="white").grid(row=1, column=0, sticky="w")
        self.var_cont = tk.DoubleVar(value=1.5) 
        ttk.Scale(ctrl_frame, from_=0.5, to=3.0, orient="horizontal", variable=self.var_cont).grid(row=1, column=1, sticky="ew", padx=5)
        
        # 3. Brightness
        tk.Label(ctrl_frame, text="Brightness:", bg="#2d2d2d", fg="white").grid(row=2, column=0, sticky="w")
        self.var_brit = tk.DoubleVar(value=1.0)
        ttk.Scale(ctrl_frame, from_=0.1, to=3.0, orient="horizontal", variable=self.var_brit).grid(row=2, column=1, sticky="ew", padx=5)

        # 4. Invert
        self.var_inv = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl_frame, text="Invert Colors", variable=self.var_inv).grid(row=3, column=0, columnspan=3, pady=5)

        # 5. Speed (Delay)
        tk.Label(ctrl_frame, text="Speed Limit (ms):", bg="#2d2d2d", fg="white").grid(row=4, column=0, sticky="w")
        self.var_delay = tk.IntVar(value=0) 
        ttk.Scale(ctrl_frame, from_=0, to=200, orient="horizontal", variable=self.var_delay).grid(row=4, column=1, sticky="ew", padx=5)

        # --- STATS ---
        self.lbl_stats = tk.Label(self, text="FPS: 0", font=("Consolas", 10), bg="#1e1e1e", fg="gray")
        self.lbl_stats.pack(pady=5)

        self.last_time = time.time()
        self.frames = 0
        ctrl_frame.columnconfigure(1, weight=1)
        
        self.process_loop()

    def snap_rotation(self, val):
        v = float(val)
        snapped = round(v / 90) * 90
        self.var_rot.set(snapped)
        self.lbl_rot.config(text=f"{snapped}°")

    def process_loop(self):
        try:
            # 1. Capture & Resize
            img = ImageGrab.grab()
            img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            
            # 2. Filters
            rot = self.var_rot.get()
            if rot > 0: img = img.rotate(rot, expand=False)
            if self.var_inv.get(): img = ImageOps.invert(img)
            
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(self.var_cont.get())
            
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(self.var_brit.get())

            # 3. Convert
            bw_img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
            
            # 4. Preview
            self.tk_img = ImageTk.PhotoImage(bw_img)
            self.canvas.itemconfig(self.bg_id, image=self.tk_img)

            # 5. Safe Save (Collision Proof)
            final_img = bw_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            temp_file = BRIDGE_FILE + ".tmp"
            
            # Save to temp first
            final_img.save(temp_file, format="BMP") 
            
            # Try to swap files. If locked, just ignore and try next frame.
            try:
                os.replace(temp_file, BRIDGE_FILE)
            except OSError:
                # File is busy! Clean up temp and skip this frame.
                try: os.remove(temp_file)
                except: pass

        except Exception as e:
            print(f"Frame dropped: {e}")

        # --- FPS Calc ---
        self.frames += 1
        delta = time.time() - self.last_time
        if delta > 1.0:
            fps = self.frames / delta
            self.lbl_stats.config(text=f"FPS: {fps:.1f}")
            self.frames = 0
            self.last_time = time.time()

        delay = self.var_delay.get()
        if delay < 1: delay = 1 
        self.after(delay, self.process_loop)

if __name__ == "__main__":
    app = UltimateCaster()
    app.mainloop()