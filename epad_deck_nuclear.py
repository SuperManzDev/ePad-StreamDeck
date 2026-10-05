import time
import os
import ctypes
import winsound
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
import comtypes.client
import hid  # pip install hidapi

# --- CONFIGURATION ---
PROG_ID = "EPadInkCtrl.Pad.1"
BUFFER_FILE = os.path.abspath("deck_buffer.bmp")
WIDTH, HEIGHT = 320, 240

# --- USB SETTINGS ---
VENDOR_ID = 0x04df 
PRODUCT_ID = 0x0030
MAX_X_RAW = 28000.0

# --- THE NUCLEAR FILTER ---
# This is a "voting system". We look at the last 20 frames of data.
# The button is only pressed if it wins >70% of the votes.
HISTORY_SIZE = 20
WIN_THRESHOLD = 14  # 14 out of 20 votes required

# --- MEDIA KEYS ---
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002

def press_key(vk_code):
    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)

class EPadDeckNuclear(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Deck (Nuclear Filter)")
        self.geometry("350x500")
        
        self.driver_active = False
        self.epad = None
        self.hid_device = None
        self.active_button = None
        self.last_press_time = 0
        
        # The Voting Box
        self.vote_history = []

        # UI
        tk.Label(self, text="NUCLEAR FILTER ENABLED", font=("Arial", 12, "bold"), fg="red").pack(pady=10)
        self.lbl_status = tk.Label(self, text="Waiting...", font=("Consolas", 10))
        self.lbl_status.pack()
        
        self.canvas = tk.Canvas(self, width=WIDTH, height=HEIGHT, bg="#333")
        self.canvas.pack(pady=10)
        self.bg_id = self.canvas.create_image(0, 0, anchor="nw")
        
        self.init_hw()
        self.update_display()
        self.hid_loop() 
        self.screen_loop()

    def init_hw(self):
        try:
            self.epad = comtypes.client.CreateObject(PROG_ID)
            self.epad.OpenConnection()
            self.epad.Light = 1
            self.driver_active = True
        except: pass
        
        try:
            self.hid_device = hid.device()
            self.hid_device.open(VENDOR_ID, PRODUCT_ID)
            self.hid_device.set_nonblocking(1)
            self.lbl_status.config(text="USB Connected", fg="green")
        except Exception as e:
            self.lbl_status.config(text=f"USB Error: {e}", fg="red")

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
        self.after(5, self.hid_loop)

    def process_vote(self, x, pressure):
        # 1. Lift Detection
        if pressure < 50:
            self.vote_history.clear()
            if self.active_button:
                self.active_button = None
                self.update_display()
                self.lbl_status.config(text="Lifted")
            return

        # 2. Cast Vote
        screen_x = int((x / MAX_X_RAW) * WIDTH)
        vote = "UNKNOWN"
        if screen_x < 106: vote = "PREV"
        elif screen_x < 213: vote = "PLAY"
        else: vote = "NEXT"

        # Add to history
        self.vote_history.append(vote)
        if len(self.vote_history) > HISTORY_SIZE:
            self.vote_history.pop(0)

        # 3. Count Votes
        if len(self.vote_history) == HISTORY_SIZE:
            # Count how many times each button appears in history
            prev_count = self.vote_history.count("PREV")
            play_count = self.vote_history.count("PLAY")
            next_count = self.vote_history.count("NEXT")

            winner = None
            if prev_count >= WIN_THRESHOLD: winner = "PREV"
            elif play_count >= WIN_THRESHOLD: winner = "PLAY"
            elif next_count >= WIN_THRESHOLD: winner = "NEXT"

            if winner:
                self.lbl_status.config(text=f"Locked: {winner} ({max(prev_count, play_count, next_count)}/{HISTORY_SIZE})", fg="blue")
                self.trigger_logic(winner)
            else:
                self.lbl_status.config(text="Stabilizing...", fg="orange")

    def trigger_logic(self, btn):
        now = time.time()
        if btn != self.active_button and (now - self.last_press_time > 0.5):
            self.active_button = btn
            self.last_press_time = now
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
        for i, b in enumerate(btns):
            x1 = i * zw
            x2 = x1 + zw if i < 2 else WIDTH
            fill = 0 if self.active_button == b else 1
            fg = 1 if self.active_button == b else 0
            d.rectangle([x1, 0, x2, HEIGHT], fill=fill)
            d.line([x2, 0, x2, HEIGHT], fill=0)
            cx, cy = x1 + zw//2, HEIGHT//2
            d.text((cx-15, cy-5), b, fill=fg)
        return img

    def update_display(self):
        img = self.draw_interface()
        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.itemconfig(self.bg_id, image=self.tk_img)
        if self.driver_active:
            try:
                b = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                b.save(BUFFER_FILE)
                self.epad.SetBitmap(BUFFER_FILE, 1, 0)
                self.epad.Light = 1
            except: pass

    def screen_loop(self):
        if self.driver_active:
            try: comtypes.client.PumpEvents(0.01)
            except: pass
        self.after(100, self.screen_loop)

if __name__ == "__main__":
    app = EPadDeckNuclear()
    app.mainloop()