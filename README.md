# 🖥️ ePad Deck — Repurposed Electronic Signature Tablet Macro Pad

Turn an old, surplus ePad electronic signature capture tablet into a physical, interactive **macro pad and Stream Deck** with dynamic on-screen button drawing and stylus touch coordinate mapping.

---

## ⚡ How It Works

1. **Low-Level COM Hooking**: Interacts with the ePad 32-bit Windows ActiveX / COM libraries (`ePadInkCtrl.ocx` and `ePadInkNative.dll`) using Python's `comtypes` to gain raw access to the LCD screen buffer and digitizer input.
2. **Dynamic UI Rendering**: Draws custom button grids, system statistics, icons, and status text directly to a local bitmap buffer (`deck_buffer.bmp`) and uploads the frame to the signature pad's display in real time.
3. **Stylus Touch Coordinates**: Maps digitizer (X, Y) touch pressure and stylus taps to virtual hotkeys, application launchers, media controls, and desktop automation scripts.
4. **Calibration Engine (`epad_calibrator.py`)**: Includes interactive coordinate calibration routines to align physical screen taps with digital button hitboxes.

---

## 🚀 Getting Started

### Prerequisites
* **Hardware**: IntegriSign / ePad LCD electronic signature capture device (USB).
* **OS**: Windows 10 / 11 (uses 32-bit driver subsystem via `SysWOW64`).
* **Python**: Python 3.8+ (32-bit or 64-bit with registered OCX).
* **Libraries**: `comtypes`, `pillow`, `pynput`.

```bash
pip install comtypes pillow pynput
```

### Setup & Driver Registration
1. Register the ePad ActiveX control:
   ```cmd
   regsvr32 ePadInkCtrl.ocx
   ```
2. Verify hardware connectivity:
   ```bash
   python epad_calibrator.py
   ```
3. Run the Deck:
   ```bash
   python epad_deck.py
   # or the enhanced layout:
   python epad_betterdeckpad.py
   ```

---

## 📂 File Overview

* **`epad_deck.py`**: Core macro pad runtime with button event dispatcher and LCD buffer rendering.
* **`epad_betterdeckpad.py`**: Enhanced layout with multi-page support, visual feedback, and quick action macros.
* **`epad_calibrator.py`**: Stylus touch coordinate calibration utility.
* **`epad_bridge_server.py`**: WebSocket / network bridge for remote control integration.
* **`ePadInkCtrl.ocx`**: 32-bit ActiveX COM control.

---

## 📜 License
MIT License.
