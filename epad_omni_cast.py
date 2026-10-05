import time
import os
import cv2
import numpy as np
import mss
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

# --- NEW LIBRARY FOR CAMERA NAMES ---
try:
    from pygrabber.dshow_graph import FilterGraph
except ImportError:
    print("Please run: py -3.12 -m pip install pygrabber")
    exit()

# --- CONFIGURATION ---
BRIDGE_FILE = os.path.abspath("bridge_feed.bmp")
WIDTH, HEIGHT = 320, 240

class TitanCasterV3(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad TITAN v3 (Real Camera Names)")
        self.geometry("450x750")
        self.configure(bg="#050505")
        
        # --- GET CAMERA NAMES ---
        self.camera_map = {} # Maps "Name" -> ID (0, 1, 2)
        self.refresh_camera_list()
        
        # --- GPU CHECK ---
        cv2.setUseOptimized(True)
        gpu_on = cv2.useOptimized()
        
        # --- HEADER ---
        tk.Label(self, text="TITAN CASTER v3", font=("Impact", 18), bg="#050505", fg="#00ff00").pack(pady=10)
        status_text = "GPU: ACTIVE" if gpu_on else "GPU: INACTIVE"
        tk.Label(self, text=status_text, font=("Consolas", 9), bg="#050505", fg="#00ff00" if gpu_on else "orange").pack()

        # --- PREVIEW ---
        self.canvas = tk.Canvas(self, width=WIDTH, height=HEIGHT, bg="#111", highlightthickness=0)
        self.canvas.pack(pady=10)
        self.bg_id = self.canvas.create_image(0, 0, anchor="nw")

        # --- CONTROLS ---
        ctrl = tk.Frame(self, bg="#111", padx=10, pady=10)
        ctrl.pack(fill="x", padx=15)

        # 1. Source Select
        tk.Label(ctrl, text="SOURCE:", bg="#111", fg="white").grid(row=0, column=0, sticky="w")
        self.var_source = tk.StringVar(value="SCREEN")
        ttk.Radiobutton(ctrl, text="Screen", variable=self.var_source, value="SCREEN").grid(row=0, column=1)
        ttk.Radiobutton(ctrl, text="Camera", variable=self.var_source, value="WEBCAM").grid(row=0, column=2)

        # 2. Camera Picker (THE NEW PART)
        tk.Label(ctrl, text="Select Cam:", bg="#111", fg="cyan").grid(row=1, column=0, sticky="w")
        
        self.combo_cams = ttk.Combobox(ctrl, values=list(self.camera_map.keys()), state="readonly", width=25)
        if self.camera_map:
            self.combo_cams.current(0) # Select first camera by default
        self.combo_cams.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        
        # Bind the selection event to switch cameras immediately
        self.combo_cams.bind("<<ComboboxSelected>>", self.switch_camera)

        # 3. Rotation
        tk.Label(ctrl, text="Rotation:", bg="#111", fg="white").grid(row=2, column=0, sticky="w")
        self.var_rot = tk.IntVar(value=0)
        ttk.Scale(ctrl, from_=0, to=360, variable=self.var_rot, command=self.update_rot).grid(row=2, column=1, columnspan=2, sticky="ew")
        self.lbl_rot = tk.Label(ctrl, text="0°", bg="#111", fg="gray", width=4)
        self.lbl_rot.grid(row=2, column=3)

        # 4. Contrast
        tk.Label(ctrl, text="Contrast:", bg="#111", fg="white").grid(row=3, column=0, sticky="w")
        self.var_cont = tk.DoubleVar(value=1.2)
        ttk.Scale(ctrl, from_=0.5, to=3.0, variable=self.var_cont).grid(row=3, column=1, columnspan=2, sticky="ew")

        # 5. Brightness
        tk.Label(ctrl, text="Brightness:", bg="#111", fg="white").grid(row=4, column=0, sticky="w")
        self.var_brit = tk.DoubleVar(value=10)
        ttk.Scale(ctrl, from_=-100, to=100, variable=self.var_brit).grid(row=4, column=1, columnspan=2, sticky="ew")

        # 6. Speed
        tk.Label(ctrl, text="Speed Limit:", bg="#111", fg="white").grid(row=5, column=0, sticky="w")
        self.var_speed = tk.IntVar(value=15)
        ttk.Scale(ctrl, from_=1, to=60, variable=self.var_speed).grid(row=5, column=1, columnspan=2, sticky="ew")
        
        # 7. Toggles
        self.var_inv = tk.BooleanVar(value=False)
        self.var_flip = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Invert", variable=self.var_inv).grid(row=6, column=0, columnspan=2, pady=5)
        ttk.Checkbutton(ctrl, text="Mirror", variable=self.var_flip).grid(row=6, column=2, columnspan=2, pady=5)

        self.lbl_fps = tk.Label(self, text="FPS: 0", bg="#050505", fg="gray")
        self.lbl_fps.pack(pady=10)

        # --- ENGINES ---
        self.sct = mss.mss()
        self.cam = None
        self.running = True
        self.frames = 0
        self.last_time = time.time()
        
        self.after(100, self.render_loop)

    def refresh_camera_list(self):
        # Use pygrabber to ask Windows for device names
        try:
            graph = FilterGraph()
            devices = graph.get_input_devices()
            self.camera_map = {name: i for i, name in enumerate(devices)}
        except:
            self.camera_map = {"Error: No Cameras Found": 0}

    def switch_camera(self, event=None):
        # Force release of current camera
        if self.cam is not None:
            self.cam.release()
            self.cam = None
        
        cam_name = self.combo_cams.get()
        cam_id = self.camera_map.get(cam_name, 0)
        print(f"Switching to: {cam_name} (ID: {cam_id})")
        
        # Open new camera immediately
        self.cam = cv2.VideoCapture(cam_id, cv2.CAP_DSHOW)

    def update_rot(self, val):
        self.lbl_rot.config(text=f"{int(float(val))}°")

    def get_frame(self):
        # MODE A: SCREEN
        if self.var_source.get() == "SCREEN":
            monitor = self.sct.monitors[1]
            sct_img = self.sct.grab(monitor)
            img = np.array(sct_img)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        # MODE B: WEBCAM
        else:
            if self.cam is None or not self.cam.isOpened():
                # Try to open currently selected camera
                cam_name = self.combo_cams.get()
                cam_id = self.camera_map.get(cam_name, 0)
                self.cam = cv2.VideoCapture(cam_id, cv2.CAP_DSHOW)
            
            ret, frame = self.cam.read()
            if ret:
                return frame
            else:
                blk = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
                cv2.putText(blk, "CAMERA LOADING...", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)
                return blk

    def render_loop(self):
        start_t = time.time()
        try:
            raw_img = self.get_frame()
            if raw_img is not None:
                # GPU Pipeline
                u_img = cv2.UMat(raw_img)
                u_img = cv2.resize(u_img, (WIDTH, HEIGHT), interpolation=cv2.INTER_NEAREST)
                
                angle = self.var_rot.get()
                if angle != 0:
                    M = cv2.getRotationMatrix2D((WIDTH//2, HEIGHT//2), angle, 1.0)
                    u_img = cv2.warpAffine(u_img, M, (WIDTH, HEIGHT))

                u_img = cv2.convertScaleAbs(u_img, alpha=self.var_cont.get(), beta=self.var_brit.get())

                if self.var_flip.get():
                    u_img = cv2.flip(u_img, 1)

                gray = cv2.cvtColor(u_img, cv2.COLOR_BGR2GRAY)
                cpu_img = gray.get()

                if self.var_inv.get():
                    cpu_img = cv2.bitwise_not(cpu_img)

                pil_img = Image.fromarray(cpu_img)
                bw_img = pil_img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
                
                self.tk_img = ImageTk.PhotoImage(bw_img)
                self.canvas.itemconfig(self.bg_id, image=self.tk_img)

                final_save = bw_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                temp_file = BRIDGE_FILE + ".tmp"
                final_save.save(temp_file, format="BMP") 
                try: os.replace(temp_file, BRIDGE_FILE)
                except: pass

        except Exception as e:
            print(f"Error: {e}")

        self.frames += 1
        delta = time.time() - self.last_time
        if delta > 1.0:
            self.lbl_fps.config(text=f"FPS: {self.frames / delta:.1f}")
            self.frames = 0
            self.last_time = time.time()

        target = self.var_speed.get()
        elapsed = time.time() - start_t
        delay = max(1, int((1.0/target - elapsed) * 1000))
        self.after(delay, self.render_loop)

if __name__ == "__main__":
    app = TitanCasterV3()
    app.mainloop()