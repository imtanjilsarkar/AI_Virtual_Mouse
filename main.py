"""
AI Virtual Mouse — Professional Edition v2
-------------------------------------------
Controls:
  ✦ Move cursor     →  index finger up, others curled (move wrist)
  ✦ Scroll          →  index + middle + ring up → move hand up/down
  ✦ Left click      →  thumb + index pinch  (< 32px)
  ✦ Right click     →  peace sign (index+middle) held STILL for 0.4s  ← fixed
  ✦ Double click    →  all 5 fingers open
  ✦ Volume          →  thumb + middle only up → spread/close
  ✦ Screenshot      →  fist (all fingers closed)
  ✦ Quit            →  press  Q

Scroll vs Cursor logic:
  - index only up  +  vertical delta > SCROLL_LOCK_PX  →  SCROLL mode
  - index only up  +  hand mostly still                →  CURSOR mode
  Scroll and cursor are now 100% separate gestures — no overlap possible.
"""

import cv2
import math
import time
import os
import numpy as np
import pyautogui
from pathlib import Path
from src.hand_tracker import HandTracker

# ── Screenshot save folder ────────────────────────────────────────────────────
SCREENSHOT_DIR = Path(r"D:\My Pictures\Screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)   # create if it doesn't exist

# ── Optional Windows volume control ──────────────────────────────────────────
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    _dev      = AudioUtilities.GetSpeakers()
    _iface    = _dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    _vol_ctrl = _iface.QueryInterface(IAudioEndpointVolume)
    VOLUME_OK = True
    print("[OK] Volume control ready")
except Exception:
    _vol_ctrl = None
    VOLUME_OK = False
    print("[--] Volume control unavailable (pycaw / comtypes not installed)")

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.0
SCREEN_W, SCREEN_H = pyautogui.size()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                            HUD Renderer                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝
class HUD:
    PANEL_W = 310
    PANEL_H = 250
    MARGIN  = 14

    GESTURE_ICONS = {
        "CURSOR"     : "index  Cursor Move",
        "LEFT CLICK" : "pinch  Left Click",
        "RIGHT CLICK": "hold   Right Click",
        "DBL CLICK"  : "open   Double Click",
        "SCROLL UP"  : "index  Scroll UP",
        "SCROLL DOWN": "index  Scroll DOWN",
        "VOLUME"     : "thumb  Volume",
        "SCREENSHOT" : "fist   Screenshot",
        "IDLE"       : "--     Idle",
    }

    def __init__(self):
        self.active_gesture   = "IDLE"
        self.gesture_alpha    = 0.0
        self.fps_history      = []
        self.screenshot_count = 0
        self.volume_pct       = None
        # right-click hold progress 0.0 → 1.0
        self.rc_progress      = 0.0

    def set_gesture(self, name: str):
        if name != self.active_gesture:
            self.active_gesture = name
            self.gesture_alpha  = 0.0

    def draw(self, img: np.ndarray, fps: float,
             vol_pct=None, rc_progress: float = 0.0):
        h, w, _ = img.shape
        self.fps_history.append(fps)
        if len(self.fps_history) > 30:
            self.fps_history.pop(0)
        avg_fps = sum(self.fps_history) / len(self.fps_history)
        if vol_pct is not None:
            self.volume_pct = vol_pct
        if self.gesture_alpha < 1.0:
            self.gesture_alpha = min(1.0, self.gesture_alpha + 0.10)

        # ── Glass panel ──────────────────────────────────────────────────────
        px = w - self.PANEL_W - self.MARGIN
        py = self.MARGIN
        panel = img[py:py+self.PANEL_H, px:px+self.PANEL_W]
        glass = np.zeros_like(panel); glass[:] = (20, 20, 30)
        cv2.addWeighted(glass, 0.72, panel, 0.28, 0, panel)
        img[py:py+self.PANEL_H, px:px+self.PANEL_W] = panel

        cv2.rectangle(img, (px,py), (px+self.PANEL_W, py+self.PANEL_H),
                      (60,60,80), 1, cv2.LINE_AA)
        cv2.line(img, (px, py+1), (px+self.PANEL_W, py+1),
                 (100,180,255), 2, cv2.LINE_AA)

        # Title
        cv2.putText(img, "AI VIRTUAL MOUSE",
                    (px+12, py+24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.52, (100,200,255), 1, cv2.LINE_AA)

        # FPS bar
        bx, by = px+12, py+36
        bw = self.PANEL_W - 24
        cv2.rectangle(img,(bx,by),(bx+bw,by+6),(40,40,60),-1)
        col = (0,220,120) if avg_fps >= 25 else (0,140,255)
        cv2.rectangle(img,(bx,by),(bx+int(bw*min(avg_fps/60,1)),by+6),
                      col,-1,cv2.LINE_AA)
        cv2.putText(img, f"FPS  {avg_fps:4.1f}",
                    (bx, by-3), cv2.FONT_HERSHEY_SIMPLEX,
                    0.40, (160,160,180), 1, cv2.LINE_AA)

        # Active gesture
        ga    = self.gesture_alpha
        gest  = self.GESTURE_ICONS.get(self.active_gesture, self.active_gesture)
        gcol  = tuple(int(c*ga) for c in (60,220,255))
        cv2.putText(img, gest, (px+12, py+74),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, gcol, 2, cv2.LINE_AA)

        # Right-click hold arc
        if rc_progress > 0.01:
            cx2, cy2 = px + self.PANEL_W - 30, py + 74
            angle = int(rc_progress * 360)
            cv2.ellipse(img,(cx2,cy2),(14,14),
                        -90, 0, angle, (0,200,255), 3, cv2.LINE_AA)

        cv2.line(img,(px+10,py+88),(px+self.PANEL_W-10,py+88),(50,50,70),1)

        # Legend
        legend = [
            ("3 fingers up   ", "Scroll Up/Down"),
            ("Pinch           ", "Left Click"),
            ("Peace+hold 0.4s ", "Right Click"),
            ("All open        ", "Dbl Click"),
            ("Fist            ", "Screenshot"),
        ]
        if VOLUME_OK:
            legend.append(("Thumb+Middle  ", "Volume"))

        for i, (key, val) in enumerate(legend):
            yy = py + 104 + i * 20
            cv2.putText(img, key, (px+14, yy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.34,
                        (120,120,150), 1, cv2.LINE_AA)
            cv2.putText(img, val, (px+160, yy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.34,
                        (200,200,220), 1, cv2.LINE_AA)

        # Volume bar
        if self.volume_pct is not None and VOLUME_OK:
            vby = py + self.PANEL_H - 20
            vbx = px + 12
            vbw = self.PANEL_W - 24
            cv2.rectangle(img,(vbx,vby),(vbx+vbw,vby+8),(40,40,60),-1)
            cv2.rectangle(img,(vbx,vby),
                          (vbx+int(vbw*self.volume_pct/100),vby+8),
                          (80,180,255),-1,cv2.LINE_AA)
            cv2.putText(img,f"VOL {self.volume_pct}%",(vbx,vby-4),
                        cv2.FONT_HERSHEY_SIMPLEX,0.38,(130,180,255),1,cv2.LINE_AA)

        # Screenshot badge
        if self.screenshot_count:
            cv2.putText(img, f"SHOT {self.screenshot_count}", (14,34),
                        cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,220,120),2,cv2.LINE_AA)

        # Quit hint
        cv2.putText(img,"Q  quit",(14,h-14),
                    cv2.FONT_HERSHEY_SIMPLEX,0.38,(90,90,110),1,cv2.LINE_AA)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                          Gesture Helpers                                ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def get_finger_states(lm):
    """[thumb, index, middle, ring, pinky]  1=up  0=down"""
    tips = [4, 8, 12, 16, 20]
    pips = [3, 6, 10, 14, 18]
    out  = []
    # Thumb: X-axis (mirrored camera)
    out.append(1 if lm[tips[0]][0] > lm[pips[0]][0] else 0)
    # Fingers: Y-axis (tip above pip = extended)
    for i in range(1, 5):
        out.append(1 if lm[tips[i]][1] < lm[pips[i]][1] else 0)
    return out

def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                             Main Loop                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def main():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,  720)
    cap.set(cv2.CAP_PROP_FPS,           60)

    tracker = HandTracker(max_hands=1, detection_conf=0.78, tracking_conf=0.65)
    hud     = HUD()

    # ── Cursor smoothing ─────────────────────────────────────────────────────
    smooth_x, smooth_y = 0.0, 0.0
    SMOOTH_CURSOR = 0.72   # high = smoother cursor
    SMOOTH_SCROLL = 0.50   # lower = more responsive scroll

    CAM_MARGIN_X = 0.10
    CAM_MARGIN_Y = 0.10

    # ── Pinch hysteresis (enter at 30, exit at 42 → no flicker) ─────────────
    PINCH_ENTER = 30
    PINCH_EXIT  = 42
    in_pinch    = False

    # ── Right-click hold timer ───────────────────────────────────────────────
    RC_HOLD_SEC   = 0.40   # must hold peace sign THIS long to fire
    rc_hold_start = None   # timestamp when peace sign first seen
    rc_fired      = False  # did we already fire this hold?

    # ── Scroll mode latch ────────────────────────────────────────────────────
    # Prevents cursor/scroll flip-flop on small tremors
    SCROLL_LOCK_PX   = 8     # min vertical delta (px) to enter scroll mode
    SCROLL_LATCH_SEC = 0.25  # stay in scroll mode for at least this long
    scroll_mode      = False
    scroll_latch_ts  = 0.0
    prev_scroll_y    = None
    SCROLL_SENS      = 0.55

    # ── Cooldowns ────────────────────────────────────────────────────────────
    cd = {k: 0.0 for k in ["click","double","screenshot"]}
    CD = {"click": 0.30, "double": 0.55, "screenshot": 0.80}

    # ── Volume ───────────────────────────────────────────────────────────────
    prev_vol_dist = None

    shot_count = 0
    prev_time  = time.time()
    rc_progress = 0.0

    print("\n[AI Virtual Mouse v2]  Q = quit\n")
    print(f"[Screenshots] Saving to → {SCREENSHOT_DIR}\n")

    # ── Create preview window and pin to bottom-right corner ─────────────────
    PREVIEW_W, PREVIEW_H = 480, 270
    WIN_NAME = "AI Virtual Mouse v2"
    cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_NAME, PREVIEW_W, PREVIEW_H)
    # Position: bottom-right, 10px from edges
    win_x = SCREEN_W - PREVIEW_W - 10
    win_y = SCREEN_H - PREVIEW_H - 50   # 50px offset clears taskbar
    cv2.moveWindow(WIN_NAME, win_x, win_y)

    while True:
        ok, img = cap.read()
        if not ok:
            break

        img = cv2.flip(img, 1)
        now = time.time()
        dt  = max(now - prev_time, 1e-6)
        fps = 1.0 / dt
        prev_time = now

        # Tick cooldowns
        for k in cd:
            cd[k] = max(0.0, cd[k] - dt)

        img = tracker.find_hands(img, draw=True)
        lm  = tracker.get_landmarks(img)

        current_gesture = "IDLE"
        rc_progress     = 0.0

        if lm and len(lm) >= 21:
            idx_tip    = lm[8]
            thumb_tip  = lm[4]
            middle_tip = lm[12]
            wrist      = lm[0]
            cam_h, cam_w, _ = img.shape

            fingers  = get_finger_states(lm)
            pinch_d  = dist(idx_tip, thumb_tip)
            mid_d    = dist(middle_tip, thumb_tip)

            # ── Pinch hysteresis ─────────────────────────────────────────────
            if in_pinch:
                if pinch_d > PINCH_EXIT:
                    in_pinch = False
            else:
                if pinch_d < PINCH_ENTER:
                    in_pinch = True

            tracker.add_trail_point(*idx_tip)

            # ══════════════════════════════════════════════════════════════════
            # PRIORITY 1 — LEFT CLICK  (pinch, any finger config)
            # ══════════════════════════════════════════════════════════════════
            if in_pinch and cd["click"] == 0:
                pyautogui.click()
                cd["click"] = CD["click"]
                in_pinch    = False   # reset so next frame isn't instant re-click
                tracker.trigger_ripple(*idx_tip, "LEFT CLICK")
                current_gesture = "LEFT CLICK"
                print(f"  ◆ Left Click")

            # ══════════════════════════════════════════════════════════════════
            # PRIORITY 2 — DOUBLE CLICK  (all 5 open)
            # ══════════════════════════════════════════════════════════════════
            elif all(f==1 for f in fingers) and cd["double"] == 0:
                pyautogui.doubleClick()
                cd["double"] = CD["double"]
                tracker.trigger_ripple(*idx_tip, "DBL CLICK")
                current_gesture = "DBL CLICK"
                print("  ◆ Double Click")

            # ══════════════════════════════════════════════════════════════════
            # PRIORITY 3 — SCREENSHOT  (fist)
            # ══════════════════════════════════════════════════════════════════
            elif all(f==0 for f in fingers) and cd["screenshot"] == 0:
                shot_count += 1
                hud.screenshot_count = shot_count
                fname = str(SCREENSHOT_DIR / f"screenshot_{shot_count:03d}.png")
                pyautogui.screenshot(fname)
                cd["screenshot"] = CD["screenshot"]
                tracker.trigger_ripple(*wrist, "SCREENSHOT")
                current_gesture = "SCREENSHOT"
                print(f"  ◆ Screenshot → {fname}")

            # ══════════════════════════════════════════════════════════════════
            # PRIORITY 4 — VOLUME  (thumb + middle only, index down)
            # ══════════════════════════════════════════════════════════════════
            elif (fingers[0]==1 and fingers[2]==1 and
                  fingers[1]==0 and fingers[3]==0 and VOLUME_OK):
                current_gesture = "VOLUME"
                if prev_vol_dist is not None:
                    delta = mid_d - prev_vol_dist
                    if abs(delta) > 4:
                        cur = _vol_ctrl.GetMasterVolumeLevelScalar()
                        nv  = float(np.clip(cur + delta*0.006, 0.0, 1.0))
                        _vol_ctrl.SetMasterVolumeLevelScalar(nv, None)
                        hud.volume_pct = int(nv*100)
                        print(f"  ◆ Volume {hud.volume_pct}%")
                prev_vol_dist = mid_d

            # ══════════════════════════════════════════════════════════════════
            # PRIORITY 5 — RIGHT CLICK  (peace sign held still for RC_HOLD_SEC)
            # Index + Middle up, Ring + Pinky down, no pinch
            # ══════════════════════════════════════════════════════════════════
            elif (fingers[1]==1 and fingers[2]==1 and
                  fingers[3]==0 and fingers[4]==0 and not in_pinch):

                if rc_hold_start is None:
                    rc_hold_start = now
                    rc_fired      = False

                held = now - rc_hold_start
                rc_progress = min(held / RC_HOLD_SEC, 1.0)
                current_gesture = "RIGHT CLICK"

                if held >= RC_HOLD_SEC and not rc_fired:
                    pyautogui.rightClick()
                    rc_fired = True
                    tracker.trigger_ripple(*idx_tip, "RIGHT CLICK")
                    print("  ◆ Right Click")

            else:
                # Reset right-click hold whenever peace sign breaks
                rc_hold_start = None
                rc_fired      = False
                prev_vol_dist = None

            # ══════════════════════════════════════════════════════════════════
            # PRIORITY 6 — SCROLL  (index + middle + ring up, pinky down)
            # Completely separate from cursor — zero conflict
            # Move hand UP = scroll up,  move hand DOWN = scroll down
            # ══════════════════════════════════════════════════════════════════
            if (current_gesture in ("IDLE",) and
                    fingers[1]==1 and fingers[2]==1 and
                    fingers[3]==1 and fingers[4]==0 and not in_pinch):

                if prev_scroll_y is not None:
                    dy = idx_tip[1] - prev_scroll_y
                    if abs(dy) >= SCROLL_LOCK_PX:
                        scroll_amount = -int(dy * SCROLL_SENS)
                        if scroll_amount != 0:
                            pyautogui.scroll(scroll_amount)
                    current_gesture = "SCROLL UP" if dy <= 0 else "SCROLL DOWN"
                else:
                    current_gesture = "SCROLL UP"   # show label immediately on entry

                prev_scroll_y = idx_tip[1]

            else:
                prev_scroll_y = None
                scroll_mode   = False

            # ══════════════════════════════════════════════════════════════════
            # PRIORITY 7 — CURSOR  (index only up, 100% dedicated)
            # Middle=0, Ring=0, Pinky=0 — completely distinct from scroll
            # ══════════════════════════════════════════════════════════════════
            if (current_gesture in ("IDLE", "CURSOR") and
                    fingers[1]==1 and fingers[2]==0 and
                    fingers[3]==0 and fingers[4]==0 and not in_pinch):

                # Still move cursor for all other gestures (so cursor doesn't freeze)
                if current_gesture not in ("LEFT CLICK","RIGHT CLICK",
                                           "DBL CLICK","SCREENSHOT","VOLUME"):
                    nx = (idx_tip[0]/cam_w - CAM_MARGIN_X) / (1.0 - 2*CAM_MARGIN_X)
                    ny = (idx_tip[1]/cam_h - CAM_MARGIN_Y) / (1.0 - 2*CAM_MARGIN_Y)
                    nx = max(0.0, min(1.0, nx))
                    ny = max(0.0, min(1.0, ny))
                    smooth_x = smooth_x * SMOOTH_CURSOR + nx*SCREEN_W * (1.0-SMOOTH_CURSOR)
                    smooth_y = smooth_y * SMOOTH_CURSOR + ny*SCREEN_H * (1.0-SMOOTH_CURSOR)
                    pyautogui.moveTo(smooth_x, smooth_y)

        else:
            prev_scroll_y = None
            prev_vol_dist = None
            rc_hold_start = None
            scroll_mode   = False

        hud.set_gesture(current_gesture)
        hud.draw(img, fps,
                 vol_pct=hud.volume_pct if VOLUME_OK else None,
                 rc_progress=rc_progress)

        # ── Resize frame to compact preview window ───────────────────────────
        display = cv2.resize(img, (PREVIEW_W, PREVIEW_H), interpolation=cv2.INTER_LINEAR)
        cv2.imshow(WIN_NAME, display)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("\n[AI Virtual Mouse] Exited cleanly.")


if __name__ == "__main__":
    main()