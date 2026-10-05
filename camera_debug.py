import cv2
import time

def test_camera(index):
    print(f"--- TESTING CAMERA INDEX {index} ---")
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        print(f"Cam {index}: FAILED to open.")
        return False
    
    # Try to read 10 frames (sometimes the first few are black)
    print(f"Cam {index}: Reading frames...")
    for i in range(10):
        ret, frame = cap.read()
        if ret:
            # Check if frame is totally black
            if frame.max() == 0:
                print(f"Frame {i}: BLACK SCREEN (Driver active, but no video)")
            else:
                print(f"Frame {i}: SUCCESS! Video Detected.")
                # Show the video
                print("Press 'q' to close this window and try the next camera.")
                while True:
                    ret, frame = cap.read()
                    if not ret: break
                    cv2.imshow(f"Camera {index} (Press q to quit)", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                cap.release()
                cv2.destroyAllWindows()
                return True
        else:
            print(f"Frame {i}: Read Error.")
            time.sleep(0.1)
            
    cap.release()
    print(f"Cam {index}: gave up (All frames empty).")
    return False

print("Scanning cameras (0 to 5)...")
found_any = False
for i in range(6):
    if test_camera(i):
        found_any = True

if not found_any:
    print("\nCONCLUSION: No working cameras found.")
    print("1. If using DroidCam: Open the DroidCam Client on PC and click 'Start'.")
    print("2. Check if another app (Zoom/Discord) is using the camera.")
else:
    print("\nCONCLUSION: We found a working camera! Use that Index number in the main app.")