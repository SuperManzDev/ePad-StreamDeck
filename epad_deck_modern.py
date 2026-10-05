import time
import os
import ctypes
import winsound
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk
import hid 

# --- CONFIGURATION ---
BRIDGE_FILE = os.path.abspath("bridge_feed.bmp")
WIDTH, HEIGHT = 320, 240
VENDOR_ID = 0x04df 
PRODUCT_ID = 0x0030
MAX_X_RAW = 28000.0  
HISTORY_SIZE = 15
WIN_THRESHOLD = 10 

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002

def press_key(vk_code):
    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)

class ModernDeck(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Modern Deck (64-bit)")
        self.geometry("350x550")
        
        self.active_button = None
        self.last_press_time = 0
        self.vote_history = []
        
        tk.Label(self, text="MODERN DECK (64-BIT)", font=("Segoe UI", 12, "bold"), fg="#007ACC").pack(pady=10)
        self.lbl_status = tk.Label(self, text="Waiting for USB...", font=("Consolas", 10))
        self.lbl_status.pack()
        
        self.canvas = tk.Canvas(self, width=WIDTH, height=HEIGHT, bg="#222")
        self.canvas.pack(pady=10)
        self.bg_id = self.canvas.create_image(0, 0, anchor="nw")
        
        self.init_hid()
        self.update_display()
        self.hid_loop()

    def init_hid(self):
        try:
            self.hid_device = hid.device()
            self.hid_device.open(VENDOR_ID, PRODUCT_ID)
            self.hid_device.set_nonblocking(1)
            self.lbl_status.config(text="USB Connected (HID Mode)", fg="green")
        except Exception as e:
            self.lbl_status.config(text=f"USB Error: {e}", fg="red")
            self.hid_device = None

    def hid_loop(self):
        if self.hid_device:
            try:
                report = self.hid_device.read(64)
                if report:
                    raw_x = report[1] | (report[2] << 8)
                    pressure = report[5]
                    x = raw_x & 0x7FFF
                    self.process_vote(x, pressure)
                else:
                    self.process_vote(None, 0)
            except: pass
        self.after(2, self.hid_loop)

    def process_vote(self, x, pressure):
        if pressure < 50:
            self.vote_history.clear()
            if self.active_button:
                self.active_button = None
                self.update_display()
                self.lbl_status.config(text="Lifted")
            return

        screen_x = int((x / MAX_X_RAW) * WIDTH)
        vote = "UNKNOWN"
        if screen_x < 106: vote = "PREV"
        elif screen_x < 213: vote = "PLAY"
        else: vote = "NEXT"

        self.vote_history.append(vote)
        if len(self.vote_history) > HISTORY_SIZE:
            self.vote_history.pop(0)

        if len(self.vote_history) == HISTORY_SIZE:
            counts = {b: self.vote_history.count(b) for b in ["PREV", "PLAY", "NEXT"]}
            winner = max(counts, key=counts.get)
            if counts[winner] >= WIN_THRESHOLD:
                self.trigger_logic(winner)

    def trigger_logic(self, btn):
        now = time.time()
        if btn != self.active_button and (now - self.last_press_time > 0.4):
            self.active_button = btn
            self.last_press_time = now
            self.lbl_status.config(text=f"ACTION: {btn}", fg="blue")
            self.trigger_action(btn)
            self.update_display()

    def trigger_action(self, btn):
        try: winsound.Beep(1000, 50)
        except: pass
        if btn == "PREV": press_key(VK_MEDIA_PREV_TRACK)
        elif btn == "PLAY": press_key(VK_MEDIA_PLAY_PAUSE)
        elif btn == "NEXT": press_key(VK_MEDIA_NEXT_TRACK)

    def draw_interface(self):
        img = Image.new("RGB", (WIDTH, HEIGHT), (20, 20, 20))
        d = ImageDraw.Draw(img)
        zw = WIDTH // 3
        btns = ["PREV", "PLAY", "NEXT"]
        colors = {"PREV": "#3498db", "PLAY": "#2ecc71", "NEXT": "#e74c3c"}
        
        for i, b in enumerate(btns):
            x1 = i * zw
            x2 = x1 + zw if i < 2 else WIDTH
            is_active = (self.active_button == b)
            fill_col = colors[b] if is_active else (40, 40, 40)
            text_col = (255, 255, 255) if is_active else (150, 150, 150)
            d.rectangle([x1, 0, x2, HEIGHT], fill=fill_col, outline=(0,0,0))
            
            bbox = d.textbbox((0, 0), b)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            cx, cy = x1 + zw//2, HEIGHT//2
            d.text((cx - text_w/2, cy - text_h/2), b, fill=text_col)
        return img

    def update_display(self):
        rgb_img = self.draw_interface()
        self.tk_img = ImageTk.PhotoImage(rgb_img)
        self.canvas.itemconfig(self.bg_id, image=self.tk_img)
        
        temp_file = BRIDGE_FILE + ".tmp"
        bw_img = rgb_img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        final_img = bw_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        
        # --- THE FIX: Explicitly specify format="BMP" ---
        final_img.save(temp_file, format="BMP")
        
        if os.path.exists(BRIDGE_FILE):
            try: os.remove(BRIDGE_FILE)
            except: pass
        os.rename(temp_file, BRIDGE_FILE)

if __name__ == "__main__":
    app = ModernDeck()
    app.mainloop()