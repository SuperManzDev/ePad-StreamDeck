import os
import sys
import time
import json
import math
import queue
import threading
import statistics
import ctypes
import winsound
import subprocess
from datetime import datetime

# GUI Libraries
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageGrab

# Device Libraries
import hid
import comtypes
import comtypes.client
import mss
import pyautogui
import psutil

# Configuration
CONFIG_FILE = "epad_user_config.json"
PROG_ID = "EPadInkCtrl.Pad.1"
WIDTH, HEIGHT = 320, 240
VENDOR_ID = 0x04df
PRODUCT_ID = 0x0030

# Media and Volume Virtual Keys
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE      = 0xAD
VK_VOLUME_DOWN      = 0xAE
VK_VOLUME_UP        = 0xAF
KEYEVENTF_KEYUP     = 0x0002

def press_key(vk_code):
    try:
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
    except Exception as e:
        print(f"Keypress error: {e}")


def wrap_text(text, width=48):
    """Wraps text lines to fit the ePad screen width limit cleanly."""
    lines = []
    for line in text.splitlines():
        if not line:
            lines.append("")
            continue
        if len(line) <= width:
            lines.append(line)
        else:
            for i in range(0, len(line), width):
                lines.append(line[i:i+width])
    return lines


class HollowCaptureWindow(tk.Toplevel):
    """
    Transparent bounding box that can be dragged and resized.
    Grabs whatever desktop area is inside it to stream to the ePad.
    """
    def __init__(self, master):
        super().__init__(master)
        self.title("ePad Capture Zone")
        self.geometry("400x300+100+100")
        self.attributes("-topmost", True)
        
        # Transparent Color Background
        self.configure(bg='fuchsia')
        self.attributes("-transparentcolor", "fuchsia")
        
        # Visual green boundary border
        self.canvas = tk.Canvas(self, bg="fuchsia", highlightthickness=4, highlightbackground="#00FF00")
        self.canvas.pack(fill="both", expand=True)
        
        # Resolution Info label
        self.lbl_info = tk.Label(self, text="400x300", bg="#00FF00", fg="black", font=("Arial", 9, "bold"))
        self.lbl_info.place(x=10, y=260) 
        
        self.bind("<Configure>", self.update_dims)
        
        # Intercept close "X" click to hide instead of destroying window
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

    def update_dims(self, event):
        w, h = self.winfo_width(), self.winfo_height()
        self.lbl_info.config(text=f"{w}x{h}")
        self.lbl_info.place(y=h-22)


class EPadCOMWorker(threading.Thread):
    """
    Dedicated worker thread for EPad ActiveX/COM operations.
    Keeps COM calls off the main GUI thread to prevent frame drop/stuttering.
    """
    def __init__(self, log_cb, status_cb):
        super().__init__()
        self.daemon = True
        self.queue = queue.Queue(maxsize=1)  # Only keep the latest frame
        self.running = True
        self.log_cb = log_cb
        self.status_cb = status_cb
        self.epad = None
        self.connected = False

    def run(self):
        comtypes.CoInitialize()
        self.log_cb("COM Worker: Thread started. Attempting connection...")
        
        try:
            self.epad = comtypes.client.CreateObject(PROG_ID)
            res = self.epad.OpenConnection()
            if res in (0, 1):
                self.connected = True
                self.epad.Light = 1
                self.status_cb(True)
                self.log_cb(f"COM Worker: Connected to EPad COM. OpenConnection={res}")
            else:
                self.log_cb(f"COM Worker: OpenConnection returned failure ({res}).", error=True)
                self.status_cb(False)
        except Exception as e:
            self.log_cb(f"COM Worker: Failed to initialize EPad ActiveX: {e}", error=True)
            self.status_cb(False)

        last_update_time = 0

        while self.running:
            try:
                task = self.queue.get(timeout=0.05)
                action = task.get("action")

                if action == "bitmap" and self.connected:
                    img = task.get("image")
                    fps = task.get("fps", 10)
                    frame_time = 1.0 / fps

                    # USB 1.1 Traffic Control / Throttle
                    now = time.time()
                    elapsed = now - last_update_time
                    if elapsed < frame_time:
                        time.sleep(frame_time - elapsed)

                    # Save to local buffer
                    buf_path = os.path.abspath("temp_launcher_buffer.bmp")
                    mono = img.convert("1", dither=Image.Dither.NONE)
                    mono.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(buf_path)

                    try:
                        self.epad.SetBitmap(buf_path, 1, 0)
                        last_update_time = time.time()
                    except Exception as e:
                        self.log_cb(f"COM Worker: SetBitmap Error: {e}", error=True)

                elif action == "light" and self.connected:
                    val = task.get("value")
                    try:
                        self.epad.Light = val
                        self.log_cb(f"COM Worker: Backlight set to {val}")
                    except Exception as e:
                        self.log_cb(f"COM Worker: Light Set Error: {e}", error=True)

                elif action == "clear" and self.connected:
                    try:
                        self.epad.Clear(1, 1)
                        self.log_cb("COM Worker: Screen cleared")
                    except Exception as e:
                        self.log_cb(f"COM Worker: Clear Error: {e}", error=True)

            except queue.Empty:
                if self.connected:
                    try:
                        comtypes.client.PumpEvents(0.001)
                    except:
                        pass

        if self.connected:
            try:
                self.epad.Light = 0
                self.epad.CloseConnection()
                self.log_cb("COM Worker: Connection closed successfully.")
            except Exception as e:
                self.log_cb(f"COM Worker: Disconnection error: {e}", error=True)

        comtypes.CoUninitialize()
        self.status_cb(False)
        self.log_cb("COM Worker: Thread terminated.")

    def push_image(self, img, fps):
        try:
            while not self.queue.empty():
                self.queue.get_nowait()
        except queue.Empty:
            pass

        try:
            self.queue.put_nowait({"action": "bitmap", "image": img, "fps": fps})
        except queue.Full:
            pass

    def set_light(self, value):
        self.queue.put({"action": "light", "value": value})

    def clear_screen(self):
        self.queue.put({"action": "clear"})


class EPadHIDWorker(threading.Thread):
    """
    Dedicated worker thread for EPad USB HID input handling.
    Polls the hardware at 200Hz to prevent missed points and input lag.
    """
    def __init__(self, log_cb, status_cb, touch_cb):
        super().__init__()
        self.daemon = True
        self.log_cb = log_cb
        self.status_cb = status_cb
        self.touch_cb = touch_cb
        self.running = True
        self.device = None
        self.connected = False

    def run(self):
        self.log_cb("HID Worker: Thread started. Attempting USB hook...")
        try:
            self.device = hid.device()
            self.device.open(VENDOR_ID, PRODUCT_ID)
            self.device.set_nonblocking(1)
            self.connected = True
            self.status_cb(True)
            self.log_cb("HID Worker: Connected to EPad USB HID interface.")
        except Exception as e:
            self.log_cb(f"HID Worker: Failed to open USB Device. {e}", error=True)
            self.status_cb(False)

        while self.running:
            if self.connected:
                try:
                    report = self.device.read(64)
                    if report:
                        raw_x = report[1] | (report[2] << 8)
                        raw_y = report[3] | (report[4] << 8)
                        pressure = report[5]
                        
                        x = raw_x & 0x7FFF
                        y = raw_y & 0x7FFF
                        
                        self.touch_cb(x, y, pressure)
                    else:
                        self.touch_cb(None, None, 0)
                except Exception as e:
                    self.log_cb(f"HID Worker: Read error: {e}", error=True)
                    self.connected = False
                    self.status_cb(False)
            time.sleep(0.005) # 200 Hz polling rate

        if self.device:
            try:
                self.device.close()
                self.log_cb("HID Worker: USB device closed.")
            except:
                pass
        self.status_cb(False)
        self.log_cb("HID Worker: Thread terminated.")


class EpadAppLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Config
        self.title("ePad-ink (VP9805) Launcher & Optimizer")
        self.geometry("950x640")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Start Time for Uptime stats
        self.start_time = time.time()

        # Create Virtual 1GB VMdrive if not exists
        self.create_vmdrive()

        # Persistent Shell Working Directory
        self.term_cwd = "/root"

        # Initial Terminal History Buffer
        self.term_buffer = [
            "Debian GNU/Linux 12 (custom build by MNZ)",
            "epad-mnz login: root (automatic login)",
            "Linux epad-mnz 2.4.19-mnz-superlight #1",
            "ARM7TDMI @ 180MHz, 8MB RAM, 1GB VMdrive",
            "",
            "Type commands in the PC GUI terminal box...",
            "root@epad-mnz:~# neofetch"
        ]
        self.term_buffer.extend(self.execute_linux_command("neofetch"))
        while len(self.term_buffer) > 17:
            self.term_buffer.pop(0)

        # Load Calibration
        self.cal = {"min_x": 0, "min_y": 0, "max_x": 28000, "max_y": 28000}
        self.load_calibration()

        # Calibration state machine
        self.calibration_step = 0
        self.cal_raw_points = []
        self.cal_coords = []

        # Threading/Worker Objects
        self.com_worker = None
        self.hid_worker = None

        # Thread-safe Input Variables
        self.last_raw_x = 0
        self.last_raw_y = 0
        self.last_pressure = 0
        self.last_filtered_x = 0
        self.last_filtered_y = 0
        self.touch_active = False

        # Filter Histories
        self.x_history = []
        self.y_history = []
        self.last_valid_x = None
        self.last_valid_y = None
        self.last_lift_time = 0

        # Click/Zone Decision state
        self.vote_history = []
        self.active_button = None
        self.last_click_time = 0

        # Mode loop state
        self.current_mode = "Off"
        self.inverse_mode = False

        # GUI layout
        self.setup_ui()

        # Hollow Overlay Window
        self.capture_win = HollowCaptureWindow(self)
        self.capture_win.withdraw()

        # Start Workers
        self.start_workers()

        # Start periodic GUI Update Loops
        self.update_canvas_loop()
        self.system_monitor_loop()
        self.screen_mirror_loop()

    def load_calibration(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.cal = json.load(f)
                print(f"Loaded Calibration: {self.cal}")
            except Exception as e:
                print(f"Error loading calibration config: {e}")

    def create_vmdrive(self):
        """Creates a 1GB sparse file representing the VM Drive on PC."""
        vmdrive_path = "vmdrive.img"
        if not os.path.exists(vmdrive_path):
            try:
                with open(vmdrive_path, "wb") as f:
                    f.seek(1024 * 1024 * 1024 - 1)
                    f.write(b'\0')
                print("Created 1GB virtual drive sparse file: vmdrive.img")
            except Exception as e:
                print(f"Failed to create virtual drive: {e}")

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1) # Controls
        self.grid_columnconfigure(1, weight=1) # Visualizer / Canvas
        self.grid_rowconfigure(0, weight=1)

        # ----------------- LEFT PANEL: CONTROLS -----------------
        left_frame = ctk.CTkFrame(self, corner_radius=15, fg_color="#1e1e24")
        left_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        left_frame.grid_columnconfigure(0, weight=1)

        # Title
        title_lbl = ctk.CTkLabel(
            left_frame, text="ePad-ink Launcher & Optimizer", 
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"), 
            text_color="#00ccff"
        )
        title_lbl.grid(row=0, column=0, padx=20, pady=15, sticky="w")

        # Connection Status Card
        status_card = ctk.CTkFrame(left_frame, fg_color="#2a2a35", corner_radius=10)
        status_card.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        status_card.grid_columnconfigure((0, 1), weight=1)

        self.lbl_com_status = ctk.CTkLabel(status_card, text="ActiveX: Offline", text_color="red", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_com_status.grid(row=0, column=0, padx=10, pady=8)

        self.lbl_hid_status = ctk.CTkLabel(status_card, text="USB: Offline", text_color="red", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_hid_status.grid(row=0, column=1, padx=10, pady=8)

        # Mode Selection Header
        mode_hdr = ctk.CTkLabel(left_frame, text="Select Dashboard Mode", font=ctk.CTkFont(size=14, weight="bold"))
        mode_hdr.grid(row=2, column=0, padx=20, pady=(12, 5), sticky="w")

        # Mode Selection Grid
        modes_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        modes_frame.grid(row=3, column=0, padx=20, pady=5, sticky="ew")
        modes_frame.grid_columnconfigure((0, 1), weight=1)

        self.btn_mode_off = ctk.CTkButton(modes_frame, text="🔴 Blank / Off", command=lambda: self.set_mode("Off"), fg_color="#444", hover_color="#555")
        self.btn_mode_off.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.btn_mode_deck3 = ctk.CTkButton(modes_frame, text="🎹 Media Deck (3x1)", command=lambda: self.set_mode("Media Deck"))
        self.btn_mode_deck3.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.btn_mode_deck4 = ctk.CTkButton(modes_frame, text="🎛️ Advanced Grid (2x2)", command=lambda: self.set_mode("Grid Deck"))
        self.btn_mode_deck4.grid(row=1, column=0, padx=5, pady=5, sticky="ew")

        self.btn_mode_sys = ctk.CTkButton(modes_frame, text="📈 Sys Dashboard", command=lambda: self.set_mode("Sys Monitor"))
        self.btn_mode_sys.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        self.btn_mode_mirror = ctk.CTkButton(modes_frame, text="🖥️ Mirror (Mouse)", command=lambda: self.set_mode("Mirror"))
        self.btn_mode_mirror.grid(row=2, column=0, padx=5, pady=5, sticky="ew")

        self.btn_mode_os = ctk.CTkButton(modes_frame, text="🖼️ OS Mode (Box Cast)", command=lambda: self.set_mode("OS Mode"))
        self.btn_mode_os.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        self.btn_mode_term = ctk.CTkButton(modes_frame, text="🐚 Linux Terminal (MNZ Debian)", command=lambda: self.set_mode("Linux Terminal"))
        self.btn_mode_term.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        # Sliders / Optimizations Header
        opts_hdr = ctk.CTkLabel(left_frame, text="Hardware & Anti-Glitch Optimizers", font=ctk.CTkFont(size=14, weight="bold"))
        opts_hdr.grid(row=4, column=0, padx=20, pady=(12, 5), sticky="w")

        sliders_frame = ctk.CTkFrame(left_frame, fg_color="#2a2a35", corner_radius=10)
        sliders_frame.grid(row=5, column=0, padx=20, pady=5, sticky="nsew")
        sliders_frame.grid_columnconfigure(0, weight=1)

        # 1. Target FPS
        self.lbl_fps_slider = ctk.CTkLabel(sliders_frame, text="Target Refresh Rate: 10 FPS (Bus Limit)")
        self.lbl_fps_slider.grid(row=0, column=0, padx=15, pady=(8, 0), sticky="w")
        self.slider_fps = ctk.CTkSlider(sliders_frame, from_=1, to=20, number_of_steps=19, command=self.on_fps_changed)
        self.slider_fps.set(10)
        self.slider_fps.grid(row=1, column=0, padx=15, pady=(0, 8), sticky="ew")

        # 2. Glitch Filter Size
        self.lbl_filter_slider = ctk.CTkLabel(sliders_frame, text="Anti-Glitch Filter Size: 5 frames")
        self.lbl_filter_slider.grid(row=2, column=0, padx=15, pady=(5, 0), sticky="w")
        self.slider_filter = ctk.CTkSlider(sliders_frame, from_=1, to=15, number_of_steps=14, command=self.on_filter_changed)
        self.slider_filter.set(5)
        self.slider_filter.grid(row=3, column=0, padx=15, pady=(0, 8), sticky="ew")

        # 3. Min Pressure
        self.lbl_pressure_slider = ctk.CTkLabel(sliders_frame, text="Min Pressure Cutoff: 50")
        self.lbl_pressure_slider.grid(row=4, column=0, padx=15, pady=(5, 0), sticky="w")
        self.slider_pressure = ctk.CTkSlider(sliders_frame, from_=10, to=150, number_of_steps=28, command=self.on_pressure_changed)
        self.slider_pressure.set(50)
        self.slider_pressure.grid(row=5, column=0, padx=15, pady=(0, 8), sticky="ew")

        # 4. Inverse Color Switch
        self.chk_inverse = ctk.CTkCheckBox(sliders_frame, text="Invert Display Colors", command=self.toggle_inverse)
        self.chk_inverse.grid(row=6, column=0, padx=15, pady=(5, 12), sticky="w")

        # 5. Terminal Input Frame (hidden by default, gridded dynamically)
        self.term_frame = ctk.CTkFrame(left_frame, fg_color="#2a2a35", corner_radius=10)
        self.term_frame.grid_columnconfigure(0, weight=1)
        
        term_lbl = ctk.CTkLabel(self.term_frame, text="Linux Terminal Console Input", font=ctk.CTkFont(size=12, weight="bold"))
        term_lbl.grid(row=0, column=0, padx=15, pady=(8, 0), sticky="w")
        
        self.entry_term = ctk.CTkEntry(self.term_frame, placeholder_text="Type command (e.g. neofetch, ls, cd)...")
        self.entry_term.grid(row=1, column=0, padx=15, pady=(5, 8), sticky="ew")
        self.entry_term.bind("<Return>", self.on_term_submit)

        # 6. Calibration Action Button
        self.btn_calibrate = ctk.CTkButton(left_frame, text="🎯 Calibrate Touchscreen", command=self.start_calibration, fg_color="#e67e22", hover_color="#d35400")
        self.btn_calibrate.grid(row=7, column=0, padx=20, pady=10, sticky="ew")

        # ----------------- RIGHT PANEL: CANVAS & LOGS -----------------
        right_frame = ctk.CTkFrame(self, corner_radius=15, fg_color="#18181c")
        right_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        right_frame.grid_columnconfigure(0, weight=1)
        right_frame.grid_rowconfigure(2, weight=1)

        # Header Live Preview
        preview_hdr = ctk.CTkLabel(right_frame, text="Live ePad LCD Preview", font=ctk.CTkFont(size=14, weight="bold"))
        preview_hdr.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        # Preview Canvas
        canvas_border = ctk.CTkFrame(right_frame, fg_color="#333", border_width=2, corner_radius=5)
        canvas_border.grid(row=1, column=0, padx=20, pady=5)
        
        self.canvas = tk.Canvas(canvas_border, width=WIDTH, height=HEIGHT, bg="#9EA78F", highlightthickness=0)
        self.canvas.pack(padx=2, pady=2)
        self.canvas_bg_image = self.canvas.create_image(0, 0, anchor="nw")
        
        # Real-time pointer overlay
        self.pointer_oval = self.canvas.create_oval(-10, -10, -10, -10, fill="#2ecc71", outline="white", width=2)

        # Log Header
        log_hdr = ctk.CTkLabel(right_frame, text="System Log Console", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray")
        log_hdr.grid(row=2, column=0, padx=20, pady=(15, 0), sticky="ws")

        # Scrollable Log Window
        self.log_txt = ctk.CTkTextbox(right_frame, fg_color="#111", text_color="#ccc", font=ctk.CTkFont(family="Consolas", size=11))
        self.log_txt.grid(row=3, column=0, padx=20, pady=(5, 20), sticky="nsew")
        self.log_txt.insert("0.0", "--- Diagnostic Console Initialized ---\n")
        self.log_txt.configure(state="disabled")

    # Log/Status Updates
    def log(self, message, error=False):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {'[ERROR] ' if error else ''}{message}\n"
        self.after(0, lambda: self.async_append_log(formatted))

    def async_append_log(self, text):
        self.log_txt.configure(state="normal")
        self.log_txt.insert("end", text)
        self.log_txt.see("end")
        self.log_txt.configure(state="disabled")

    def com_status_cb(self, connected):
        self.after(0, lambda: self.update_status_label(self.lbl_com_status, "ActiveX: Ready" if connected else "ActiveX: Offline", connected))

    def hid_status_cb(self, connected):
        self.after(0, lambda: self.update_status_label(self.lbl_hid_status, "USB HID: Ready" if connected else "USB: Offline", connected))

    def update_status_label(self, label, text, ok):
        label.configure(text=text, text_color="#2ecc71" if ok else "red")

    # Slider / Settings handlers
    def on_fps_changed(self, value):
        self.lbl_fps_slider.configure(text=f"Target Refresh Rate: {int(value)} FPS")

    def on_filter_changed(self, value):
        self.lbl_filter_slider.configure(text=f"Anti-Glitch Filter Size: {int(value)} frames")

    def on_pressure_changed(self, value):
        self.lbl_pressure_slider.configure(text=f"Min Pressure Cutoff: {int(value)}")

    def toggle_inverse(self):
        self.inverse_mode = self.chk_inverse.get() == 1
        self.log(f"Inverse Mode toggled: {self.inverse_mode}")
        self.trigger_screen_update()

    # Touch Screen Calibration
    def start_calibration(self):
        self.current_mode = "Calibrate"
        self.calibration_step = 0
        self.cal_raw_points.clear()
        self.cal_coords.clear()
        self.log("Touchscreen calibration started. Follow crosshairs on ePad screen.")
        self.trigger_screen_update()

    # Terminal Input handlers
    def on_term_submit(self, event=None):
        cmd = self.entry_term.get().strip()
        if not cmd: return
        self.entry_term.delete(0, 'end')
        
        self.log(f"Terminal Executing: {cmd}")
        self.term_buffer.append(f"root@epad-mnz:{self.term_cwd}# {cmd}")
        
        # Execute Command
        output_lines = self.execute_linux_command(cmd)
        wrapped_output = []
        for line in output_lines:
            wrapped_output.extend(wrap_text(line, 48))
            
        for line in wrapped_output:
            self.term_buffer.append(line)
            
        while len(self.term_buffer) > 17:
            self.term_buffer.pop(0)
            
        self.trigger_screen_update()

    def execute_linux_command(self, cmd):
        # Handle Directory Traversal
        if cmd.strip().startswith("cd "):
            target = cmd[3:].strip()
            if target == "~" or not target:
                self.term_cwd = "/root"
                return []
            else:
                try:
                    res = subprocess.run(
                        ["wsl", "bash", "-c", f"cd {self.term_cwd} && cd {target} && pwd"],
                        capture_output=True, text=True, timeout=1.5
                    )
                    if res.returncode == 0:
                        self.term_cwd = res.stdout.strip()
                        return []
                    else:
                        return [f"bash: cd: {target}: No such directory"]
                except Exception:
                    # Fallback Windows Directory
                    try:
                        os.chdir(target)
                        self.term_cwd = os.getcwd()
                        return []
                    except Exception as ex:
                        return [f"cd: {ex}"]

        cmd_lower = cmd.lower()
        
        if cmd_lower == "neofetch" or cmd_lower == "screenfetch":
            uptime_sec = int(time.time() - self.start_time)
            mins = uptime_sec // 60
            secs = uptime_sec % 60
            uptime_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            
            return [
                "       _,.---._       root@epad-mnz",
                "     ,'   __   `.     -------------",
                f"    /   ,'  `.   \\    OS: Debian MNZ Light",
                "   |   /      \\   |   Host: ePad-ink VP9805",
                "   |   |      |   |   Kernel: 2.4.19-mnz",
                f"    \\   \\    /   /    Uptime: {uptime_str}",
                "     `.  `--'  ,'     Shell: bash-light",
                "       `'---''        CPU: ARM7TDMI @ 180MHz",
                "                      RAM: 4.2MB / 8.0MB",
                "                      VMdrive: 1GB vmdrive.img"
            ]
            
        elif cmd_lower == "help":
            return [
                "Supported commands:",
                "  neofetch      - System specification summary",
                "  df -h         - Virtual disk usage details",
                "  free -m       - RAM memory statistics",
                "  uname -a      - Kernel and processor architecture",
                "  ls / cd / pwd - Basic directory traversal",
                "  clear         - Clear terminal window screen",
                "  <wsl command> - Executes direct in WSL Debian"
            ]
            
        elif cmd_lower == "df -h":
            return [
                "Filesystem      Size  Used Avail Use% Mounted on",
                "/dev/vmdrive    1.0G  1.2M  1.0G   0% /mnt/vmdrive",
                "tmpfs           4.0M  100K  3.9M   2% /var/run"
            ]
            
        elif cmd_lower == "free -m":
            return [
                "             total        used        free",
                "Mem:             8           4           4",
                "Swap:            0           0           0"
            ]
            
        elif cmd_lower == "uname -a":
            return [
                "Linux epad-mnz 2.4.19-mnz-superlight #1 Tue Jul 14 01:45:00 armv4l GNU/Linux"
            ]
            
        elif cmd_lower == "clear":
            self.term_buffer.clear()
            return []
            
        elif cmd_lower == "ls":
            try:
                res = subprocess.run(
                    ["wsl", "bash", "-c", f"cd {self.term_cwd} && ls"],
                    capture_output=True, text=True, timeout=1.5
                )
                if res.returncode == 0:
                    return [res.stdout.strip()]
            except Exception:
                pass
            return ["vmdrive.img  sys/  bin/  var/  etc/  home/"]
            
        elif cmd_lower == "pwd":
            return [self.term_cwd]
            
        # Fallback: Execute command interactively inside WSL bash relative to term_cwd
        else:
            try:
                res = subprocess.run(
                    ["wsl", "bash", "-c", f"cd {self.term_cwd} && {cmd}"], 
                    capture_output=True, text=True, timeout=1.5
                )
                if res.returncode == 0:
                    lines = res.stdout.strip().split("\n")
                    return [l.strip() for l in lines[:10] if l.strip()]
                else:
                    err = res.stderr.strip()
                    if err:
                        return [f"bash: {err.splitlines()[0]}"]
                    return [f"Command returned exit code {res.returncode}"]
            except subprocess.TimeoutExpired:
                return ["bash: connection timed out"]
            except Exception:
                # Fallback to CMD
                try:
                    res = subprocess.run(
                        ["cmd.exe", "/c", f"cd {self.term_cwd} && {cmd}"],
                        capture_output=True, text=True, timeout=1.5
                    )
                    lines = (res.stdout if res.returncode == 0 else res.stderr).strip().split("\n")
                    return [line.strip() for line in lines[:10] if line.strip()]
                except Exception:
                    return [f"bash: command not found: {cmd}"]

    # Worker Threads
    def start_workers(self):
        self.com_worker = EPadCOMWorker(self.log, self.com_status_cb)
        self.com_worker.start()

        self.hid_worker = EPadHIDWorker(self.log, self.hid_status_cb, self.on_touch_packet)
        self.hid_worker.start()

    # Touch Input Callback from HID thread
    def on_touch_packet(self, x, y, pressure):
        """Processes raw USB reports. Glitch-filtered via voting matrix."""
        # --- Handle Touch Calibration State ---
        if self.current_mode == "Calibrate":
            min_p = int(self.slider_pressure.get())
            if pressure >= min_p and x is not None:
                self.cal_raw_points.append((self.last_raw_x, self.last_raw_y))
            elif (pressure == 0 or x is None) and self.cal_raw_points:
                # Stylus released - process calibrated point
                rx = int(statistics.median([pt[0] for pt in self.cal_raw_points]))
                ry = int(statistics.median([pt[1] for pt in self.cal_raw_points]))
                self.cal_coords.append((rx, ry))
                
                self.log(f"Calibrated point {self.calibration_step + 1}/4: Raw X={rx}, Y={ry}")
                self.cal_raw_points.clear()
                self.calibration_step += 1
                
                try: winsound.Beep(1000, 100)
                except: pass
                
                if self.calibration_step == 4:
                    # TL:0, TR:1, BR:2, BL:3
                    min_x = int((self.cal_coords[0][0] + self.cal_coords[3][0]) / 2)
                    max_x = int((self.cal_coords[1][0] + self.cal_coords[2][0]) / 2)
                    min_y = int((self.cal_coords[0][1] + self.cal_coords[1][1]) / 2)
                    max_y = int((self.cal_coords[2][1] + self.cal_coords[3][1]) / 2)
                    
                    self.cal = {
                        "min_x": min_x,
                        "min_y": min_y,
                        "max_x": max_x,
                        "max_y": max_y
                    }
                    
                    try:
                        with open(CONFIG_FILE, "w") as f:
                            json.dump(self.cal, f)
                        self.log(f"Calibration Complete! Bounds saved: {self.cal}")
                    except Exception as e:
                        self.log(f"Failed to save bounds: {e}", error=True)
                        
                    self.set_mode("Off")
                else:
                    self.trigger_screen_update()
            return

        if pressure == 0 or x is None:
            # Lift detected
            self.touch_active = False
            self.last_pressure = 0
            self.x_history.clear()
            self.y_history.clear()
            self.last_valid_x = None
            self.last_valid_y = None
            self.last_lift_time = time.time()
            
            # Reset voting Matrix when finger lifted
            self.vote_history.clear()
            if self.active_button:
                self.active_button = None
                self.trigger_screen_update()
            return

        self.last_raw_x = x
        self.last_raw_y = y
        self.last_pressure = pressure
        self.touch_active = True

        min_p = int(self.slider_pressure.get())
        if pressure < min_p:
            return  # Below pressure cutoff

        # 1. Median Filtering
        f_size = int(self.slider_filter.get())
        self.x_history.append(x)
        self.y_history.append(y)
        
        if len(self.x_history) > f_size:
            self.x_history.pop(0)
            self.y_history.pop(0)

        if len(self.x_history) < f_size:
            return # Wait for filter window to fill

        med_x = statistics.median(self.x_history)
        med_y = statistics.median(self.y_history)

        self.last_valid_x = med_x
        self.last_valid_y = med_y

        # Map Raw coords to screen bounds (0-320 / 0-240)
        sx, sy = self.map_raw_to_screen(med_x, med_y)
        self.last_filtered_x = sx
        self.last_filtered_y = sy

        # Map to button actions (Grid or Media columns)
        self.process_button_vote(sx, sy)

    def map_raw_to_screen(self, rx, ry):
        min_x = self.cal.get("min_x", 0)
        max_x = self.cal.get("max_x", 28000)
        min_y = self.cal.get("min_y", 0)
        max_y = self.cal.get("max_y", 28000)

        denom_x = max_x - min_x
        denom_y = max_y - min_y
        if denom_x == 0: denom_x = 1
        if denom_y == 0: denom_y = 1

        norm_x = (rx - min_x) / denom_x
        norm_y = (ry - min_y) / denom_y
        
        # Clamp
        norm_x = max(0.0, min(1.0, norm_x))
        norm_y = max(0.0, min(1.0, norm_y))

        # Apply correct inversion bounds if min > max
        if min_y > max_y:
            norm_y = 1.0 - norm_y

        return int(norm_x * WIDTH), int(norm_y * HEIGHT)

    def process_button_vote(self, sx, sy):
        # Resolve button name
        vote = "NONE"
        if self.current_mode == "Media Deck":
            if sx < 106: vote = "PREV"
            elif sx < 213: vote = "PLAY"
            else: vote = "NEXT"
        elif self.current_mode == "Grid Deck":
            if sx < 160 and sy < 120: vote = "VOL_DOWN"
            elif sx >= 160 and sy < 120: vote = "VOL_UP"
            elif sx < 160 and sy >= 120: vote = "PREV"
            else: vote = "NEXT"

        if vote == "NONE":
            return

        # Add to voting list
        self.vote_history.append(vote)
        
        # Keep vote size proportional to filter size
        max_votes = max(10, int(self.slider_filter.get()) * 3)
        if len(self.vote_history) > max_votes:
            self.vote_history.pop(0)

        # Require 70% consensus to register button click
        consensus = int(max_votes * 0.7)
        if self.vote_history.count(vote) >= consensus:
            self.lock_button(vote)

    def lock_button(self, btn):
        now = time.time()
        
        if btn != self.active_button and (now - self.last_click_time > 0.4):
            self.active_button = btn
            self.last_click_time = now
            self.log(f"Macro Pressed: {btn}")
            
            # Sound beep
            try: winsound.Beep(900, 80)
            except: pass

            # Trigger Keypress
            self.trigger_shortcut(btn)
            
            # Update display immediately
            self.trigger_screen_update()

    def trigger_shortcut(self, btn):
        if btn == "PREV": press_key(VK_MEDIA_PREV_TRACK)
        elif btn == "PLAY": press_key(VK_MEDIA_PLAY_PAUSE)
        elif btn == "NEXT": press_key(VK_MEDIA_NEXT_TRACK)
        elif btn == "VOL_DOWN": press_key(VK_VOLUME_DOWN)
        elif btn == "VOL_UP": press_key(VK_VOLUME_UP)

    # ----------------- DISPLAY MODES DRAWING -----------------
    def set_mode(self, mode):
        self.current_mode = mode
        self.log(f"Changing mode to: {mode}")

        # Update button colors
        self.btn_mode_off.configure(fg_color="#0066cc" if mode == "Off" else "#444")
        self.btn_mode_deck3.configure(fg_color="#0066cc" if mode == "Media Deck" else "#1f6aa5")
        self.btn_mode_deck4.configure(fg_color="#0066cc" if mode == "Grid Deck" else "#1f6aa5")
        self.btn_mode_sys.configure(fg_color="#0066cc" if mode == "Sys Monitor" else "#1f6aa5")
        self.btn_mode_mirror.configure(fg_color="#0066cc" if mode == "Mirror" else "#1f6aa5")
        self.btn_mode_os.configure(fg_color="#0066cc" if mode == "OS Mode" else "#1f6aa5")
        self.btn_mode_term.configure(fg_color="#0066cc" if mode == "Linux Terminal" else "#1f6aa5")

        if mode == "OS Mode":
            self.capture_win.deiconify()
        else:
            self.capture_win.withdraw()

        if mode == "Linux Terminal":
            self.term_frame.grid(row=6, column=0, padx=20, pady=5, sticky="ew")
            self.entry_term.focus()
        else:
            self.term_frame.grid_remove()

        if mode == "Off":
            self.com_worker.clear_screen()
            self.com_worker.set_light(0)
        else:
            self.com_worker.set_light(1)
            self.trigger_screen_update()

    def trigger_screen_update(self):
        """Draws current frame and pushes it to COM worker thread."""
        img = self.draw_frame_image()
        if img:
            self.com_worker.push_image(img, int(self.slider_fps.get()))

    def draw_frame_image(self):
        img = None

        if self.current_mode == "Off":
            img = Image.new("1", (WIDTH, HEIGHT), 1)

        elif self.current_mode == "Media Deck":
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
                d.line([x2, 0, x2, HEIGHT], fill=0, width=2)
                
                try: font = ImageFont.truetype("arial.ttf", 22)
                except: font = ImageFont.load_default()
                
                d.text((x1 + zw//2 - 25, HEIGHT//2 - 10), b, fill=fg, font=font)

        elif self.current_mode == "Grid Deck":
            img = Image.new("1", (WIDTH, HEIGHT), 1)
            d = ImageDraw.Draw(img)
            
            # Quad Buttons
            buttons = [
                {"name": "VOL -", "code": "VOL_DOWN", "rect": (0, 0, 160, 120)},
                {"name": "VOL +", "code": "VOL_UP", "rect": (160, 0, 320, 120)},
                {"name": "PREV",  "code": "PREV", "rect": (0, 120, 160, 240)},
                {"name": "NEXT",  "code": "NEXT", "rect": (160, 120, 320, 240)}
            ]

            for btn in buttons:
                x1, y1, x2, y2 = btn["rect"]
                fill = 0 if self.active_button == btn["code"] else 1
                fg = 1 if self.active_button == btn["code"] else 0
                
                d.rectangle([x1, y1, x2, y2], fill=fill)
                
                try: font = ImageFont.truetype("arial.ttf", 20)
                except: font = ImageFont.load_default()
                
                d.text((x1 + 45, y1 + 45), btn["name"], fill=fg, font=font)

            d.line([(160, 0), (160, 240)], fill=0, width=3)
            d.line([(0, 120), (320, 120)], fill=0, width=3)

        elif self.current_mode == "Sys Monitor":
            img = Image.new("1", (WIDTH, HEIGHT), 1)
            d = ImageDraw.Draw(img)
            
            now_time = datetime.now().strftime("%I:%M:%S %p")
            cpu_val = int(psutil.cpu_percent())
            ram = psutil.virtual_memory()
            ram_used = ram.used / (1024**3)
            ram_total = ram.total / (1024**3)
            
            disk = psutil.disk_usage("C:\\")
            disk_free = disk.free / (1024**3)

            # Native UI Drawing (Clean Retro look)
            try: 
                font_title = ImageFont.truetype("arial.ttf", 18)
                font_body = ImageFont.truetype("cour.ttf", 14)
            except: 
                font_title = ImageFont.load_default()
                font_body = ImageFont.load_default()

            d.text((10, 10), "SYSTEM DASHBOARD", fill=0, font=font_title)
            d.line([(10, 32), (310, 32)], fill=0, width=2)

            d.text((15, 50), f"Time:   {now_time}", fill=0, font=font_body)
            
            # CPU
            d.text((15, 80), f"CPU:    {cpu_val}%", fill=0, font=font_body)
            d.rectangle([95, 83, 295, 93], outline=0)
            d.rectangle([97, 85, 97 + int(1.96 * cpu_val), 91], fill=0)

            # RAM
            d.text((15, 115), f"RAM:    {ram_used:.1f}/{ram_total:.0f} GB", fill=0, font=font_body)
            d.rectangle([165, 118, 295, 128], outline=0)
            d.rectangle([167, 120, 167 + int(1.24 * ram.percent), 126], fill=0)

            # Disk Free
            d.text((15, 150), f"DISK C: {disk_free:.0f} GB Free", fill=0, font=font_body)

            # Active Foreground Window Title
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            active_name = buf.value if buf.value else "Desktop"
            if len(active_name) > 24:
                active_name = active_name[:22] + ".."

            d.text((15, 185), f"Active: {active_name}", fill=0, font=font_body)

        elif self.current_mode == "Mirror":
            # Grabs a 320x240 image centered on the mouse cursor
            try:
                mx, my = pyautogui.position()
                bbox = {
                    'top': int(my - 120),
                    'left': int(mx - 160),
                    'width': 320,
                    'height': 240
                }
                with mss.MSS() as sct:
                    sct_img = sct.grab(bbox)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    bw_img = img.convert("1", dither=Image.Dither.NONE)
                    img = bw_img
            except Exception as e:
                img = Image.new("1", (WIDTH, HEIGHT), 1)
                d = ImageDraw.Draw(img)
                d.text((20, 100), f"Mirror error: {e}", fill=0)

        elif self.current_mode == "OS Mode":
            # Grabs resizable hollow frame screen bounds
            try:
                x = self.capture_win.winfo_rootx() + 4  # +4 for border thickness
                y = self.capture_win.winfo_rooty() + 4
                w = self.capture_win.winfo_width() - 8
                h = self.capture_win.winfo_height() - 8
                
                if w <= 0 or h <= 0:
                    img = Image.new("1", (WIDTH, HEIGHT), 1)
                else:
                    screen = ImageGrab.grab(bbox=(x, y, x+w, y+h))
                    frame = screen.resize((WIDTH, HEIGHT), Image.Resampling.NEAREST)
                    img = frame.convert("1", dither=Image.Dither.NONE)
            except Exception as e:
                img = Image.new("1", (WIDTH, HEIGHT), 1)
                d = ImageDraw.Draw(img)
                d.text((20, 100), f"OS Mode error: {e}", fill=0)

        elif self.current_mode == "Linux Terminal":
            img = Image.new("1", (WIDTH, HEIGHT), 1)
            d = ImageDraw.Draw(img)
            
            try: 
                # Size 10 for zoomed out, high-density look
                font = ImageFont.truetype("cour.ttf", 10)
            except: 
                font = ImageFont.load_default()
                
            y_offset = 6
            for line in self.term_buffer:
                d.text((8, y_offset), line, fill=0, font=font)
                # Shorter line spacing for zoomed out view
                y_offset += 13
                
            return img

        elif self.current_mode == "Calibrate":
            # White screen background
            img = Image.new("1", (WIDTH, HEIGHT), 1)
            d = ImageDraw.Draw(img)
            
            targets = [
                (20, 20, "1/4: Touch Top-Left"),
                (300, 20, "2/4: Touch Top-Right"),
                (300, 220, "3/4: Touch Bottom-Right"),
                (20, 220, "4/4: Touch Bottom-Left")
            ]
            
            if self.calibration_step < 4:
                tx, ty, label = targets[self.calibration_step]
                
                # Draw Target Crosshair
                d.ellipse([tx - 8, ty - 8, tx + 8, ty + 8], outline=0)
                d.line([(tx - 15, ty), (tx + 15, ty)], fill=0, width=1)
                d.line([(tx, ty - 15), (tx, ty + 15)], fill=0, width=1)
                
                # Label text
                try: font = ImageFont.truetype("arial.ttf", 16)
                except: font = ImageFont.load_default()
                d.text((WIDTH//2 - 70, HEIGHT//2 - 10), label, fill=0, font=font)
                
            return img

        # Apply Inverse Colors Mode
        if img:
            if self.inverse_mode:
                img = img.point(lambda p: 255 - p)
            return img
        return None

    # ----------------- GUI BACKGROUND LOOPS -----------------
    def update_canvas_loop(self):
        """Redraws the preview canvas at 30 FPS. Fully decoupled from device rates."""
        try:
            img = self.draw_frame_image()
            if img:
                rgb_preview = img.convert("RGB")
                self.tk_lcd_img = ImageTk.PhotoImage(rgb_preview)
                self.canvas.itemconfig(self.canvas_bg_image, image=self.tk_lcd_img)
            
            # Update Overlay Touch Pointer position
            if self.touch_active and self.current_mode != "Calibrate":
                x, y = self.last_filtered_x, self.last_filtered_y
                self.canvas.coords(self.pointer_oval, x-6, y-6, x+6, y+6)
            else:
                self.canvas.coords(self.pointer_oval, -20, -20, -20, -20)
        except:
            pass

        self.after(33, self.update_canvas_loop) # ~30 FPS

    def system_monitor_loop(self):
        """Stats loop running at 1s intervals to update LCD in System Monitor mode."""
        if self.current_mode == "Sys Monitor":
            self.trigger_screen_update()
        self.after(1000, self.system_monitor_loop)

    def screen_mirror_loop(self):
        """Mirror loop running at target FPS to update LCD in screen cast mode."""
        if self.current_mode in ("Mirror", "OS Mode"):
            self.trigger_screen_update()
        
        # Calculate delay based on target FPS slider
        target_fps = int(self.slider_fps.get())
        delay_ms = max(50, int(1000 / target_fps))
        self.after(delay_ms, self.screen_mirror_loop)

    def on_closing(self):
        self.log("Closing threads and exiting launcher...")
        if self.com_worker:
            self.com_worker.running = False
        if self.hid_worker:
            self.hid_worker.running = False
        
        try:
            self.capture_win.destroy()
        except:
            pass

        time.sleep(0.3)
        self.destroy()


if __name__ == "__main__":
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("Launcher requires Administrator privileges. Launching UAC prompt...")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

    app = EpadAppLauncher()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
