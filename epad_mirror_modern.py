import time
import os
import tkinter as tk
from PIL import Image, ImageGrab, ImageTk

# --- CONFIGURATION ---
BRIDGE_FILE = os.path.abspath("bridge_feed.bmp")
WIDTH, HEIGHT = 320, 240

class ScreenMirror(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Screen Cast (64-bit)")
        self.geometry("350x300")
        
        # UI
        tk.Label(self, text="SCREEN CAST ACTIVE", font=("Arial", 14, "bold"), fg="red").pack(pady=10)
        tk.Label(self, text="Minimizing this window improves FPS", font=("Arial", 10)).pack()
        
        self.lbl_fps = tk.Label(self, text="FPS: 0", font=("Consolas", 10))
        self.lbl_fps.pack(pady=5)
        
        # Preview
        self.canvas = tk.Canvas(self, width=WIDTH, height=HEIGHT, bg="#000")
        self.canvas.pack(pady=10)
        self.bg_id = self.canvas.create_image(0, 0, anchor="nw")
        
        self.last_time = time.time()
        self.frames = 0
        
        # Start Loop
        self.update_loop()

    def update_loop(self):
        start_time = time.time()
        
        # 1. Capture Full Screen
        try:
            # Grab screen (bbox=None means full screen)
            screenshot = ImageGrab.grab()
            
            # 2. Resize to ePad Resolution (High Quality Downscaling)
            # using LANCZOS for readable text, or NEAREST for speed
            screenshot = screenshot.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            
            # 3. Update PC Preview
            self.tk_img = ImageTk.PhotoImage(screenshot)
            self.canvas.itemconfig(self.bg_id, image=self.tk_img)
            
            # 4. Save for ePad Bridge
            temp_file = BRIDGE_FILE + ".tmp"
            
            # Convert to 1-bit B/W with Dithering (Best for ePad)
            bw_img = screenshot.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
            
            # Flip logic (Drivers usually need flip, remove if upside down)
            final_img = bw_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            
            # Explicit BMP format fix
            final_img.save(temp_file, format="BMP")
            
            # Atomic Send
            if os.path.exists(BRIDGE_FILE):
                try: os.remove(BRIDGE_FILE)
                except: pass
            os.rename(temp_file, BRIDGE_FILE)
            
        except Exception as e:
            print(e)
            
        # FPS Counter
        self.frames += 1
        if time.time() - self.last_time > 1.0:
            fps = self.frames / (time.time() - self.last_time)
            self.lbl_fps.config(text=f"FPS: {fps:.1f}")
            self.frames = 0
            self.last_time = time.time()

        # Run as fast as possible
        self.after(10, self.update_loop)

if __name__ == "__main__":
    app = ScreenMirror()
    app.mainloop()