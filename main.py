import cv2
import pyautogui
from src.hand_tracker import HandTracker
import math
import numpy as np

# Volume control (Windows only)
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = interface.QueryInterface(IAudioEndpointVolume)
    VOLUME_AVAILABLE = True
    print("Volume control ready")
except:
    VOLUME_AVAILABLE = False
    print("Volume control not available (install pycaw & comtypes)")

screenshot_counter = 0
screen_w, screen_h = pyautogui.size()

smooth_x, smooth_y = 0, 0
smoothing = 0.7

# Cooldown counters (frames)
click_cd = 0
right_cd = 0
double_cd = 0
screenshot_cd = 0

# Scroll variables
prev_scroll_y = None
scroll_sensitivity = 0.5

# Volume variables
prev_vol_dist = None

cap = cv2.VideoCapture(0)
tracker = HandTracker()

def get_finger_states(landmarks):
    """Returns list of 5 booleans: thumb, index, middle, ring, pinky (1=up, 0=down)"""
    # Landmark indices: thumb tip=4, index tip=8, middle tip=12, ring tip=16, pinky tip=20
    # Base joints: thumb ip=3, index mcp=6, middle mcp=10, ring mcp=14, pinky mcp=18
    tips = [4, 8, 12, 16, 20]
    dips = [3, 6, 10, 14, 18]
    states = []
    # Thumb: compare x (for right hand, flipped horizontally, so thumb tip x > thumb ip x)
    if landmarks[tips[0]][0] > landmarks[dips[0]][0]:
        states.append(1)
    else:
        states.append(0)
    # Other fingers: compare y (tip above dip)
    for i in range(1, 5):
        if landmarks[tips[i]][1] < landmarks[dips[i]][1]:
            states.append(1)
        else:
            states.append(0)
    return states

while True:
    success, img = cap.read()
    if not success:
        break

    img = cv2.flip(img, 1)
    img = tracker.find_hands(img)
    landmarks = tracker.get_landmarks(img)

    if landmarks and len(landmarks) > 20:
        # Landmark positions
        idx_tip = landmarks[8]
        thumb_tip = landmarks[4]
        middle_tip = landmarks[12]
        ring_tip = landmarks[16]
        pinky_tip = landmarks[20]

        fingers = get_finger_states(landmarks)

        # Draw fingertip circles
        cv2.circle(img, idx_tip, 10, (255, 0, 255), cv2.FILLED)  # index magenta
        cv2.circle(img, thumb_tip, 10, (0, 255, 255), cv2.FILLED) # thumb yellow
        cv2.circle(img, middle_tip, 10, (255, 255, 0), cv2.FILLED) # middle cyan

        # ----- LEFT CLICK (thumb + index pinch) -----
        pinch_dist = math.hypot(idx_tip[0] - thumb_tip[0], idx_tip[1] - thumb_tip[1])
        if pinch_dist < 30 and click_cd == 0 and right_cd == 0:
            pyautogui.click()
            click_cd = 15
            print("Left Click")

        # ----- RIGHT CLICK (index+middle up, ring+pinky down) -----
        if fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 0 and fingers[4] == 0 and right_cd == 0:
            if pinch_dist >= 30:
                pyautogui.rightClick()
                right_cd = 20
                print("Right Click")

        # ----- DOUBLE CLICK (all fingers up) -----
        if all(f == 1 for f in fingers) and double_cd == 0:
            pyautogui.doubleClick()
            double_cd = 30
            print("Double Click")

        # ----- SCREENSHOT (fist: all fingers down) -----
        if all(f == 0 for f in fingers) and screenshot_cd == 0:
            screenshot_counter += 1
            pyautogui.screenshot(f'screenshot_{screenshot_counter}.png')
            screenshot_cd = 40
            print(f"Screenshot saved: screenshot_{screenshot_counter}.png")

        # ----- VOLUME CONTROL (thumb + middle pinch, index down) -----
        if fingers[0] == 1 and fingers[2] == 1 and fingers[1] == 0 and VOLUME_AVAILABLE:
            vol_dist = math.hypot(middle_tip[0] - thumb_tip[0], middle_tip[1] - thumb_tip[1])
            if prev_vol_dist is not None:
                delta = vol_dist - prev_vol_dist
                if abs(delta) > 5:
                    current = volume.GetMasterVolumeLevelScalar()
                    new_vol = np.clip(current + delta * 0.005, 0, 1)
                    volume.SetMasterVolumeLevelScalar(new_vol, None)
                    print(f"Volume: {int(new_vol*100)}%")
            prev_vol_dist = vol_dist
        else:
            prev_vol_dist = None

        # ----- CURSOR MOVEMENT (index finger) -----
        cam_h, cam_w, _ = img.shape
        screen_x = (idx_tip[0] / cam_w) * screen_w
        screen_y = (idx_tip[1] / cam_h) * screen_h
        smooth_x = smooth_x * smoothing + screen_x * (1 - smoothing)
        smooth_y = smooth_y * smoothing + screen_y * (1 - smoothing)
        pyautogui.moveTo(smooth_x, smooth_y)

        # ----- SCROLLING (middle finger vertical movement, index extended) -----
        if fingers[1] == 1 and pinch_dist >= 30:  # index up and not pinching
            if prev_scroll_y is not None:
                delta_y = middle_tip[1] - prev_scroll_y
                if abs(delta_y) > 5:
                    pyautogui.scroll(-int(delta_y * scroll_sensitivity))
            prev_scroll_y = middle_tip[1]
        else:
            prev_scroll_y = None

        # Decrease cooldowns
        click_cd = max(0, click_cd - 1)
        right_cd = max(0, right_cd - 1)
        double_cd = max(0, double_cd - 1)
        screenshot_cd = max(0, screenshot_cd - 1)

    cv2.imshow("AI Virtual Mouse - Full Control", img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()