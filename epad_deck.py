import sys
import os
import subprocess
import winreg
import comtypes.client
import ctypes
import time
from datetime import datetime

# --- CONFIGURATION ---
# We now look for BOTH controls found in your C# code
OCX_FILES = [
    {"name": "ePadInkCtrl.ocx", "desc": "LCD Controller (Pad)", "required": True}, 
    {"name": "esW25COM.ocx",    "desc": "Signature Capture (eSign3)", "required": False}
]

# Standard path for 32-bit drivers on 64-bit Windows
DRIVER_PATH = r"C:\Python32" 
SYSWOW64 = os.path.join(os.environ['SystemRoot'], 'SysWOW64')

# --- LOGGER ---
class Logger:
    RESET = "\033[0m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    
    @staticmethod
    def log(msg, color=RESET, type="INFO"):
        t = datetime.now().strftime("%H:%M:%S")
        print(f"{color}[{t}] [{type}] {msg}{Logger.RESET}")

# --- STEP 1: DLL & FILE AUDIT ---
def audit_system():
    Logger.log("--- PHASE 1: FILE SYSTEM AUDIT ---", Logger.CYAN)
    
    # 1. Check for the OCX files in C:\Python32
    for ocx in OCX_FILES:
        path = os.path.join(DRIVER_PATH, ocx["name"])
        if os.path.exists(path):
            Logger.log(f"Found {ocx['desc']}: {path}", Logger.GREEN)
        else:
            if ocx.get("required", True):
                Logger.log(f"MISSING {ocx['desc']} at {path}", Logger.RED, "FAIL")
                Logger.log("Please copy the .OCX files to C:\\Python32", Logger.YELLOW)
                return False
            else:
                Logger.log(f"MISSING (Optional) {ocx['desc']} at {path}", Logger.YELLOW, "WARN")

    # 2. Check for the C++ Runtimes (CRITICAL for ePad)
    # The driver WILL NOT LOAD if msvcr80.dll is missing from SysWOW64
    runtimes = ["msvcr80.dll", "msvcr90.dll"]
    missing_runtimes = False
    for dll in runtimes:
        dll_path = os.path.join(SYSWOW64, dll)
        if os.path.exists(dll_path):
            Logger.log(f"Found Runtime: {dll}", Logger.GREEN)
        else:
            Logger.log(f"MISSING Runtime: {dll} in SysWOW64", Logger.RED, "FAIL")
            missing_runtimes = True
            
    if missing_runtimes:
        Logger.log("CRITICAL: 32-bit C++ Runtimes are missing.", Logger.RED)
        Logger.log("The driver will crash silently. Please run the 'choco' fix again.", Logger.YELLOW)
        # We continue anyway to try and get more error info
    
    return True

# --- STEP 2: REGISTRY DEEP DIVE ---
def find_progid_by_path(ocx_name):
    """
    Scans the Windows Registry to find the ProgID (Class Name) 
    associated with a specific OCX file path.
    """
    target_path = os.path.join(DRIVER_PATH, ocx_name).lower()
    Logger.log(f"Scanning Registry for: {ocx_name}...", Logger.CYAN)
    
    found_clsid = None
    found_progid = None

    try:
        # 1. Scan CLSID to find the file path
        root = winreg.ConnectRegistry(None, winreg.HKEY_CLASSES_ROOT)
        clsid_key = winreg.OpenKey(root, "CLSID")
        
        # We have to iterate because we don't know the ID
        i = 0
        while True:
            try:
                clsid_str = winreg.EnumKey(clsid_key, i)
                try:
                    # Look inside CLSID\{GUID}\InprocServer32
                    with winreg.OpenKey(clsid_key, f"{clsid_str}\\InprocServer32") as server_key:
                        val, _ = winreg.QueryValueEx(server_key, "")
                        if val and val.lower() == target_path:
                            found_clsid = clsid_str
                            Logger.log(f"  -> Match found! CLSID: {found_clsid}", Logger.GREEN)
                            
                            # 2. Now look for the ProgID subkey
                            with winreg.OpenKey(clsid_key, f"{clsid_str}\\ProgID") as prog_key:
                                found_progid, _ = winreg.QueryValueEx(prog_key, "")
                                Logger.log(f"  -> RESOLVED PROGID: {found_progid}", Logger.GREEN, "SUCCESS")
                                break
                except FileNotFoundError:
                    pass
                except Exception:
                    pass
                i += 1
            except OSError:
                break # End of keys
                
    except Exception as e:
        Logger.log(f"Registry Scan Error: {e}", Logger.RED)

    return found_progid

# --- STEP 3: REGISTRATION & CONNECT ---
def main():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        Logger.log("Please run as Administrator", Logger.RED)
        return

    if not audit_system():
        return

    Logger.log("--- PHASE 2: REGISTRATION & CONNECTION ---", Logger.CYAN)

    regsvr = os.path.join(SYSWOW64, "regsvr32.exe")
    
    # 1. Register both OCXs
    for ocx in OCX_FILES:
        full_path = os.path.join(DRIVER_PATH, ocx["name"])
        if not os.path.exists(full_path):
            continue
        Logger.log(f"Registering {ocx['name']}...", Logger.CYAN)
        ret = subprocess.run([regsvr, "/s", full_path], capture_output=True)
        if ret.returncode == 0:
            Logger.log("  -> Registration Successful", Logger.GREEN)
        else:
            Logger.log(f"  -> Failed: {ret.stderr}", Logger.RED)

    # 2. Find the ProgID
    # We specifically want the Controller (ePadInkCtrl), not the capture engine, to wake the screen.
    prog_id = find_progid_by_path("ePadInkCtrl.ocx")
    
    if not prog_id:
        Logger.log("Could not find ProgID in registry. Trying defaults...", Logger.YELLOW)
        # Based on C# namespace "EPADINKCTRLLib", these are the likely candidates
        candidates = ["ePadInkCtrl.ePadInk", "ePadInk.ePadInk", "ePadInkCtrl.Pad"]
    else:
        candidates = [prog_id]

    # 3. Attempt Connection
    device = None
    for pid in candidates:
        try:
            Logger.log(f"Attempting to load COM Object: '{pid}'", Logger.CYAN)
            device = comtypes.client.CreateObject(pid)
            Logger.log(f"SUCCESS! Connected to {pid}", Logger.GREEN, "SUCCESS")
            break
        except Exception as e:
            Logger.log(f"  -> Failed: {e}", Logger.YELLOW)

    if not device:
        Logger.log("FATAL: Could not create ActiveX Object.", Logger.RED)
        Logger.log("POSSIBLE CAUSES:", Logger.RED)
        Logger.log("1. msvcr80.dll is missing from C:\\Windows\\SysWOW64 (Most Likely)", Logger.RED)
        Logger.log("2. The OCX file is corrupted", Logger.RED)
        return

    # 4. Wake the Screen (Using logic from C# btnStart_Click)
    try:
        Logger.log("--- PHASE 3: WAKE PROTOCOL ---", Logger.CYAN)
        
        # C# Code: pad1.OpenConnection()
        Logger.log("Sending OpenConnection()...")
        res = device.OpenConnection()
        Logger.log(f"  -> Result: {res}", Logger.GREEN)
        
        # C# Code: pad1.Light = State.S_ON (S_ON is usually 1)
        Logger.log("Setting Light ON...")
        try: device.Light = 1 
        except: pass

        Logger.log("Device should be active now.", Logger.GREEN)
        
        # Keep alive for 5 seconds to verify
        time.sleep(5)
        
    except Exception as e:
        Logger.log(f"Runtime Error: {e}", Logger.RED)

if __name__ == "__main__":
    main()