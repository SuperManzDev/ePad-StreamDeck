import socket
import os
import comtypes.client
import time

# --- CONFIGURATION ---
PROG_ID = "EPadInkCtrl.Pad.1"
BUFFER_FILE = os.path.abspath("ram_buffer.bmp") 
UDP_IP = "127.0.0.1"
UDP_PORT = 5005

def main():
    print("--- ePad BENCHMARK Server (UDP) ---")
    
    try:
        epad = comtypes.client.CreateObject(PROG_ID)
        epad.OpenConnection()
        epad.Light = 1
        print("Driver Active. UNLOCKED mode.")
    except Exception as e:
        print("Driver Error: " + str(e))
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    # Set socket buffer to max to prevent dropped packets
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)

    frame_count = 0
    last_time = time.time()

    while True:
        try:
            # Receive Data (Max buffer size)
            data, addr = sock.recvfrom(65536)
            
            # Write to disk (Fastest mode)
            f = open(BUFFER_FILE, "wb")
            f.write(data)
            f.close()
                
            # Send to Device (The Moment of Truth)
            epad.SetBitmap(BUFFER_FILE, 1, 0)
            
            # FPS Calculation
            frame_count += 1
            if time.time() - last_time > 1.0:
                print("DEVICE FPS: " + str(frame_count))
                frame_count = 0
                last_time = time.time()
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print("Error: " + str(e))

if __name__ == "__main__":
    main()