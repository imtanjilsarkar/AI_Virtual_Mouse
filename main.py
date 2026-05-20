import cv2
import pyautogui
from src.hand_tracker import HandTracker
import math

screen_w, screen_h = pyautogui.size()

smooth_x, smooth_y = 0, 0
smoothing = 0.7

clicked = False
click_cooldown = 0

# Scroll variables
prev_scroll_y = None
scroll_sensitivity = 0.5

cap = cv2.VideoCapture(0)
tracker = HandTracker()

while True:
    success, img = cap.read()
    if not success:
        break
    
    img = cv2.flip(img, 1)
    img = tracker.find_hands(img)
    landmarks = tracker.get_landmarks(img)
    
    if landmarks and len(landmarks) > 12:
        idx_tip = landmarks[8]
        thumb_tip = landmarks[4]
        middle_tip = landmarks[12]
        
        # Draw
        cv2.circle(img, idx_tip, 10, (255, 0, 255), cv2.FILLED)
        cv2.circle(img, thumb_tip, 10, (0, 255, 255), cv2.FILLED)
        cv2.circle(img, middle_tip, 10, (255, 255, 0), cv2.FILLED)
        
        # Distance for click (thumb + index)
        pinch_dist = math.hypot(idx_tip[0] - thumb_tip[0], idx_tip[1] - thumb_tip[1])
        if pinch_dist < 30 and not clicked and click_cooldown == 0:
            pyautogui.click()
            clicked = True
            click_cooldown = 10
            print("Click!")
        elif pinch_dist >= 30:
            clicked = False
        
        if click_cooldown > 0:
            click_cooldown -= 1
        
        # Scroll: index + middle fingers up (both above a threshold)
        # Get y-coordinates: index tip (8) and middle tip (12)
        # We check if both fingers are extended (using relative position to wrist or base)
        # Simplified: use vertical distance between index and middle fingers relative to hand center
        # Actually, scroll when index and middle are both raised (landmark 5 and 9? Too complex)
        # Better: When distance between index and middle finger tips is small (together) and they move up/down
        # Let's do: if both index and middle are extended (y < y of knuckles) then vertical movement = scroll
        # Simpler: use middle finger tip y change while pinch is NOT active.
        
        # Scroll when thumb and index are NOT pinched, and we have two fingers up.
        # We'll track middle finger y movement.
        if pinch_dist >= 30:  # not clicking
            if prev_scroll_y is not None:
                delta_y = middle_tip[1] - prev_scroll_y
                if abs(delta_y) > 5:  # dead zone
                    scroll_amount = int(delta_y * scroll_sensitivity)
                    pyautogui.scroll(-scroll_amount)  # negative for natural direction
            prev_scroll_y = middle_tip[1]
        else:
            prev_scroll_y = None
        
        # Cursor movement (index finger)
        cam_h, cam_w, _ = img.shape
        screen_x = (idx_tip[0] / cam_w) * screen_w
        screen_y = (idx_tip[1] / cam_h) * screen_h
        
        smooth_x = smooth_x * smoothing + screen_x * (1 - smoothing)
        smooth_y = smooth_y * smoothing + screen_y * (1 - smoothing)
        
        pyautogui.moveTo(smooth_x, smooth_y)
    
    cv2.imshow("AI Virtual Mouse", img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()