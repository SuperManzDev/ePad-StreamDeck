import socket
import time
import threading
import io
import mss
import tkinter as tk
from PIL import Image, ImageTk, ImageEnhance

# --- CONFIGURATION ---
UDP_IP = "127.0.0.1"
UDP_PORT = 5005
WIDTH, HEIGHT = 320, 240

# --- THE SPEED LIMIT ---
# We cap this at 20 FPS. 
# Why? Because the device can only do 15. 
# Sending more just causes the "4 FPS Traffic Jam".
TARGET_FPS = 20
FRAME_TIME = 1.0 / TARGET_FPS

class SmartCaster(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Smart Caster (Traffic Control)")
        self.geometry("350x300")
        self.configure(bg="black")
        
        tk.Label(self, text="SMART CASTER", font=("Arial", 14, "bold"), fg="#00ccff", bg="black").pack(pady=10)
        tk.Label(self, text="Optimized for USB 1.1 Limit", font=("Arial", 10), fg="gray", bg="black").pack()
        
        self.canvas = tk.Canvas(self, width=WIDTH, height=HEIGHT, bg="#222", highlightthickness=0)
        self.canvas.pack(pady=5)
        self.bg_id = self.canvas.create_image(0, 0, anchor="nw")
        
        self.lbl_fps = tk.Label(self, text="Sending: 0 FPS", fg="white", bg="black", font=("Consolas", 12))
        self.lbl_fps.pack(pady=5)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = True
        self.frames = 0
        self.start_time = time.time()
        
        # Start Capture Thread
        self.thread = threading.Thread(target=self.capture_loop)
        self.thread.daemon = True
        self.thread.start()
        
        self.update_gui()

    def capture_loop(self):
        with mss.mss() as sct:
            # Grab Primary Monitor
            monitor = sct.monitors[1] 
            bbox = {'top': monitor['top'], 'left': monitor['left'], 'width': monitor['width'], 'height': monitor['height']}

            while self.running:
                loop_start = time.time()
                
                try:
                    # 1. Capture
                    sct_img = sct.grab(bbox)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    img = img.resize((WIDTH, HEIGHT), Image.Resampling.NEAREST)
                    
                    # 2. Process
                    bw_img = img.convert("1", dither=Image.Dither.NONE)
                    
                    # 3. Send
                    output = io.BytesIO()
                    final_img = bw_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    final_img.save(output, format="BMP")
                    packet = output.getvalue()
                    
                    self.sock.sendto(packet, (UDP_IP, UDP_PORT))
                    
                    # Preview
                    self.current_preview = bw_img
                    self.frames += 1

                except Exception as e:
                    print(f"Error: {e}")

                # --- THE SMART THROTTLE ---
                # Sleep just enough to hit exactly 20 FPS
                # This prevents the server from choking/lagging
                elapsed = time.time() - loop_start
                sleep_time = FRAME_TIME - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

    def update_gui(self):
        try:
            if hasattr(self, 'current_preview'):
                self.tk_img = ImageTk.PhotoImage(self.current_preview)
                self.canvas.itemconfig(self.bg_id, image=self.tk_img)
        except: pass

        now = time.time()
        if now - self.start_time > 1.0:
            fps = self.frames / (now - self.start_time)
            self.lbl_fps.config(text=f"Sending: {int(fps)} FPS")
            self.frames = 0
            self.start_time = now
            
        self.after(100, self.update_gui)

if __name__ == "__main__":
    app = SmartCaster()
    app.mainloop()