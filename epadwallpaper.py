import time
import subprocess
import threading
import random
import shutil
import comtypes.client
import tkinter as tk
from datetime import datetime
from ctypes import Structure, c_int, c_long, c_uint64, sizeof, byref, windll, create_unicode_buffer

# --- CONFIGURATION ---
PROG_ID = "EPadInkCtrl.Pad.1"
NORMAL_REFRESH = 800    # 0.8s Update speed (Text Mode)
VISUAL_REFRESH = 100    # 0.1s Update speed (Visualizer Mode)

# --- SHARED STATE (Thread Safe) ---
state = {
    "media_title": "Waiting for Music...",
    "cpu": 0,
    "ram_str": "Calculating...", # Now stores "X / Y GB" string
    "disk": "0GB",
    "active_app": "Desktop",
    "top_process": "Analyzing...",
    "battery": "N/A"
}

# --- NATIVE WINDOWS API ---
class MEMORYSTATUSEX(Structure):
    _fields_ = [("dwLength", c_int), ("dwMemoryLoad", c_int), ("ullTotalPhys", c_uint64),
                ("ullAvailPhys", c_uint64), ("ullTotalPageFile", c_uint64), ("ullAvailPageFile", c_uint64),
                ("ullTotalVirtual", c_uint64), ("ullAvailVirtual", c_uint64), ("ullAvailExtendedVirtual", c_uint64)]

class SYSTEM_POWER_STATUS(Structure):
    _fields_ = [("ACLineStatus", c_int, 8), ("BatteryFlag", c_int, 8), ("BatteryLifePercent", c_int, 8),
                ("Reserved1", c_int, 8), ("BatteryLifeTime", c_long), ("BatteryFullLifeTime", c_long)]

# --- BACKGROUND POLLER (Prevents Lag) ---
class SystemPoller(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True 
        self.running = True

    def get_spotify_title(self):
        try:
            cmd = 'tasklist /v /fi "imagename eq Spotify.exe" /fo list'
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            output = subprocess.check_output(cmd, startupinfo=si, text=True)
            for line in output.split('\n'):
                if line.startswith("Window Title:"):
                    title = line.replace("Window Title:", "").strip()
                    if title and title != "N/A" and title != "Spotify":
                        return title
                    elif title == "Spotify":
                        return "Spotify (Paused)"
        except: pass
        return None

    def get_generic_media(self):
        cmd = "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object -ExpandProperty MainWindowTitle"
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            out = subprocess.check_output(["powershell", "-c", cmd], startupinfo=si, text=True)
            for line in out.split('\n'):
                line = line.strip()
                if not line: continue
                if "- YouTube" in line: return line.split("- YouTube")[0].strip()
                if "VLC" in line: return line.replace("- VLC media player", "").strip()
        except: pass
        return None

    def get_top_process(self):
        ps = "Get-Process | Sort-Object CPU -Descending | Select-Object -First 1 -Property ProcessName"
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            out = subprocess.check_output(["powershell", "-c", ps], startupinfo=si, text=True)
            lines = out.strip().split('\n')
            if len(lines) >= 3: return lines[-1].strip()
        except: pass
        return "System"

    def get_cpu_load(self):
        try:
            cmd = 'typeperf "\\Processor(_Total)\\% Processor Time" -sc 1'
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            out = subprocess.check_output(cmd, startupinfo=si, text=True)
            import re
            matches = re.findall(r'"(\d+\.\d+)"', out)
            return float(matches[-1]) if matches else 0
        except: return 0

    def run(self):
        while self.running:
            # 1. RAM (GB Calculation)
            mem = MEMORYSTATUSEX()
            mem.dwLength = sizeof(MEMORYSTATUSEX)
            windll.kernel32.GlobalMemoryStatusEx(byref(mem))
            
            # Convert Bytes to GB
            total_gb = mem.ullTotalPhys / (1024**3)
            avail_gb = mem.ullAvailPhys / (1024**3)
            used_gb = total_gb - avail_gb
            
            state["ram_str"] = f"{used_gb:.1f} / {total_gb:.0f} GB"

            # 2. Disk
            total, used, free = shutil.disk_usage("C:\\")
            state["disk"] = f"{free // (1024**3)}GB"

            # 3. Active Window
            hwnd = windll.user32.GetForegroundWindow()
            length = windll.user32.GetWindowTextLengthW(hwnd)
            buf = create_unicode_buffer(length + 1)
            windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            state["active_app"] = buf.value if buf.value else "Desktop"

            # 4. Battery
            pwr = SYSTEM_POWER_STATUS()
            if windll.kernel32.GetSystemPowerStatus(byref(pwr)):
                state["battery"] = f"{pwr.BatteryLifePercent}%"
            
            # 5. Media
            media = self.get_spotify_title()
            if not media: media = self.get_generic_media()
            state["media_title"] = media if media else "No Media Detected"

            # 6. Top Process
            state["top_process"] = self.get_top_process()
            
            # 7. CPU (Acts as loop delay)
            state["cpu"] = self.get_cpu_load()

# --- MAIN APP ---
class EpadDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ePad Controller")
        self.geometry("400x420")
        self.configure(bg="#1a1a1a")
        
        self.worker = SystemPoller()
        self.worker.start()

        try:
            self.epad = comtypes.client.CreateObject(PROG_ID)
            self.epad.OpenConnection()
            self.epad.Light = 1
            self.epad.FontName = 1
            self.epad.FontSize = 1
            self.driver_active = True
        except:
            self.driver_active = False

        self.canvas = tk.Canvas(self, width=320, height=240, bg="#9EA78F", highlightthickness=0)
        self.canvas.pack(pady=15)
        
        self.screen_text = self.canvas.create_text(
            10, 10, anchor="nw", text="Starting...", 
            font=("Courier New", 12, "bold"), fill="black"
        )
        
        self.viz_mode = False
        self.btn = tk.Button(self, text="ENABLE VISUALIZER 🎵", command=self.toggle_viz,
                             bg="#444444", fg="white", font=("Segoe UI", 11, "bold"), height=2)
        self.btn.pack(fill="x", padx=20, pady=10)

        self.bars = [1, 2, 3, 4, 3, 2, 1]
        self.page_idx = 0
        self.last_cycle = time.time()
        
        self.update_loop()

    def toggle_viz(self):
        self.viz_mode = not self.viz_mode
        if self.viz_mode:
            self.btn.config(text="STOP VISUALIZER ⏹", bg="#d63031")
        else:
            self.btn.config(text="ENABLE VISUALIZER 🎵", bg="#444444")
            # We do NOT force reset fonts here to avoid flickering logic you didn't like

    def make_bar(self, percent, width=10):
        filled = int((percent / 100) * width)
        bar = "|" * filled + " " * (width - filled)
        return f"[{bar}]"

    def draw_visualizer(self):
        # Fake EQ Animation
        new_bars = []
        for h in self.bars:
            delta = random.choice([-1, -1, 0, 1, 2])
            new_bars.append(max(1, min(6, h + delta)))
        self.bars = new_bars
        
        track = state["media_title"]
        if len(track) > 18: track = track[:16] + ".."
        
        rows = [
            f"NOW PLAYING  {state['battery']}",
            "-" * 20,
            f"{track}",
            ""
        ]
        
        for r in range(4, 0, -1):
            line = ""
            for h in self.bars:
                line += "||| " if h >= r else "... "
            rows.append(line)
        return "\r\n".join(rows)

    def draw_dashboard(self):
        # Cycle Pages every 5 seconds
        if time.time() - self.last_cycle > 5.0:
            self.page_idx = (self.page_idx + 1) % 2
            self.last_cycle = time.time()
            
        now = datetime.now().strftime("%I:%M%p")
        
        if self.page_idx == 0:
            # PAGE 1: TASK MGR
            cpu = state["cpu"]
            return "\r\n".join([
                f"TASK MGR       {now}",
                "-" * 20,
                f"CPU: {self.make_bar(cpu)} {int(cpu)}%",
                f"RAM: {state['ram_str']}",
                f"DSK: {state['disk']} Free",
                "",
                "Top App:",
                f"> {state['top_process'][:18]}"
            ])
        else:
            # PAGE 2: MEDIA
            track = state["media_title"]
            lines = [f"MEDIA INFO     {state['battery']}", "-" * 20]
            if len(track) > 20:
                lines.append(track[:20])
                lines.append(track[20:40])
            else:
                lines.append(track)
            
            lines.append("")
            lines.append(f"Focus: {state['active_app'][:15]}")
            return "\r\n".join(lines)

    def update_loop(self):
        delay = VISUAL_REFRESH if self.viz_mode else NORMAL_REFRESH
        
        if self.viz_mode:
            text = self.draw_visualizer()
        else:
            text = self.draw_dashboard()
            
        self.canvas.itemconfig(self.screen_text, text=text)
        
        if self.driver_active:
            try:
                self.epad.CreateScreen(0, 10, text, 1, 100)
                comtypes.client.PumpEvents()
            except: pass
            
        self.after(delay, self.update_loop)

    def on_close(self):
        self.worker.running = False
        if self.driver_active:
            try:
                self.epad.Light = 0
                self.epad.CloseConnection()
            except: pass
        self.destroy()

if __name__ == "__main__":
    app = EpadDashboard()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()