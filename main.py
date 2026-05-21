"""
AI Virtual Mouse — Professional Edition v3
-------------------------------------------
Controls:
  ✦ Move cursor     →  index finger only up
  ✦ Scroll          →  index + middle + ring up → move hand up/down
  ✦ Left click      →  thumb + index pinch
  ✦ Right click     →  peace sign (index+middle) held 0.4s
  ✦ Double click    →  all 5 fingers open
  ✦ Volume          →  thumb + middle only → spread/close
  ✦ Screenshot      →  fist (all fingers closed)
  ✦ Quit            →  press  Q
"""

import cv2
import math
import time
import numpy as np
import pyautogui
from pathlib import Path
from src.hand_tracker import HandTracker

# ── Screenshot folder ────────────────────────────────────────────────────────
SCREENSHOT_DIR = Path(r"D:\My Pictures\Screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ── Volume (Windows only) ────────────────────────────────────────────────────
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
    print("[--] Volume control unavailable")

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.0
SCREEN_W, SCREEN_H = pyautogui.size()

# ── Display constants ────────────────────────────────────────────────────────
# Camera feed crops to a clean 4:3 region, then we compose a wider canvas
# with a side panel — total output is 16:9-ish, good for screen recording.
CAM_DISPLAY_W  = 640   # webcam preview width  (sharp, big enough for audience)
CAM_DISPLAY_H  = 480   # webcam preview height
PANEL_W        = 260   # right side info panel
CANVAS_W       = CAM_DISPLAY_W + PANEL_W   # 900
CANVAS_H       = CAM_DISPLAY_H             # 480
WIN_NAME       = "AI Virtual Mouse  |  Tanjil Sarkar"

# Brand accent colours (BGR)
C_ACCENT   = (255, 190,  60)   # cyan-gold
C_BLUE     = (255, 180,  80)   # sky blue
C_GREEN    = (100, 220,  80)   # lime green
C_ORANGE   = ( 60, 150, 255)   # orange
C_WHITE    = (235, 235, 240)
C_DIM      = (100, 100, 115)
C_PANEL_BG = ( 18,  20,  28)
C_BORDER   = ( 55,  58,  75)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                         Side-Panel HUD                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝
class SidePanel:
    """Draws a full-height info panel to the right of the camera feed."""

    GESTURE_META = {
        # name           : (label,           colour,    symbol)
        "IDLE"       : ("Idle",           C_DIM,     "  "),
        "CURSOR"     : ("Cursor Move",    C_BLUE,    "01"),
        "LEFT CLICK" : ("Left Click",     C_GREEN,   "LC"),
        "RIGHT CLICK": ("Right Click",    C_ORANGE,  "RC"),
        "DBL CLICK"  : ("Double Click",   C_ACCENT,  "DC"),
        "SCROLL UP"  : ("Scroll  UP",     C_BLUE,    "SU"),
        "SCROLL DOWN": ("Scroll DOWN",    C_BLUE,    "SD"),
        "VOLUME"     : ("Volume",         C_ACCENT,  "VO"),
        "SCREENSHOT" : ("Screenshot",     C_GREEN,   "SS"),
    }

    SHORTCUT_ROWS = [
        ("☝  Index only",   "→ Cursor"),
        ("☝✌🤘 3 fingers",  "→ Scroll"),
        ("👌 Pinch",         "→ Left Click"),
        ("✌  Hold 0.4s",    "→ Right Click"),
        ("🖐  All open",     "→ Dbl Click"),
        ("✊  Fist",         "→ Screenshot"),
        ("🤙 Thumb+Mid",     "→ Volume"),
    ]

    def __init__(self):
        self.active     = "IDLE"
        self.alpha      = 0.0
        self.fps_hist   = []
        self.shot_count = 0
        self.vol_pct    = None
        self.rc_prog    = 0.0
        # gesture flash animation
        self._flash_ts  = 0.0
        self._flash_col = C_BLUE

    def set_gesture(self, name: str):
        if name != self.active:
            self.active    = name
            self.alpha     = 0.0
            self._flash_ts = time.time()
            _, col, _      = self.GESTURE_META.get(name, ("", C_DIM, ""))
            self._flash_col = col

    def draw(self, canvas: np.ndarray, fps: float,
             rc_progress: float = 0.0, vol_pct=None):

        if vol_pct is not None:
            self.vol_pct = vol_pct
        self.alpha    = min(1.0, self.alpha + 0.10)
        self.rc_prog  = rc_progress

        self.fps_hist.append(fps)
        if len(self.fps_hist) > 45:
            self.fps_hist.pop(0)
        avg_fps = sum(self.fps_hist) / len(self.fps_hist)

        # ── Panel background ─────────────────────────────────────────────────
        px = CAM_DISPLAY_W
        panel = canvas[:, px:]
        panel[:] = C_PANEL_BG

        W = PANEL_W
        x0 = px + 16

        # ── Top accent bar ───────────────────────────────────────────────────
        cv2.rectangle(canvas, (px, 0), (px + W, 3), C_ACCENT, -1)

        # ── Title ────────────────────────────────────────────────────────────
        cv2.putText(canvas, "AI VIRTUAL MOUSE",
                    (x0, 26), cv2.FONT_HERSHEY_SIMPLEX,
                    0.58, C_ACCENT, 2, cv2.LINE_AA)
        cv2.putText(canvas, "by Tanjil Sarkar",
                    (x0, 44), cv2.FONT_HERSHEY_SIMPLEX,
                    0.36, C_DIM, 1, cv2.LINE_AA)

        # ── Divider ──────────────────────────────────────────────────────────
        def divider(y, col=C_BORDER):
            cv2.line(canvas, (px+8, y), (px+W-8, y), col, 1)

        divider(54)

        # ── FPS ──────────────────────────────────────────────────────────────
        fps_col = C_GREEN if avg_fps >= 25 else C_ORANGE
        cv2.putText(canvas, f"FPS", (x0, 72),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_DIM, 1, cv2.LINE_AA)
        cv2.putText(canvas, f"{avg_fps:5.1f}",
                    (x0 + 36, 72), cv2.FONT_HERSHEY_SIMPLEX,
                    0.48, fps_col, 2, cv2.LINE_AA)

        # FPS bar
        bx, by, bw, bh = x0, 78, W - 32, 5
        cv2.rectangle(canvas, (bx, by), (bx+bw, by+bh), (35,38,50), -1)
        fill = int(bw * min(avg_fps / 60.0, 1.0))
        cv2.rectangle(canvas, (bx, by), (bx+fill, by+bh), fps_col, -1)

        divider(93)

        # ── Active gesture block ──────────────────────────────────────────────
        label, gcol, sym = self.GESTURE_META.get(
            self.active, ("Unknown", C_DIM, "??"))

        # Flash border when gesture changes
        flash_age = time.time() - self._flash_ts
        if flash_age < 0.35:
            flash_alpha = 1.0 - flash_age / 0.35
            brd_col = tuple(int(c * flash_alpha) for c in self._flash_col)
            cv2.rectangle(canvas, (px+8, 98), (px+W-8, 148), brd_col, 2)

        # Gesture symbol badge
        cv2.rectangle(canvas, (x0, 101), (x0+38, 143), (30,33,45), -1)
        cv2.rectangle(canvas, (x0, 101), (x0+38, 143), gcol, 1)
        cv2.putText(canvas, sym, (x0+4, 132),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.72,
                    tuple(int(c * self.alpha) for c in gcol),
                    2, cv2.LINE_AA)

        # Gesture label
        cv2.putText(canvas, "GESTURE", (x0+46, 113),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, C_DIM, 1, cv2.LINE_AA)
        gcol_a = tuple(int(c * self.alpha) for c in gcol)
        cv2.putText(canvas, label, (x0+46, 134),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, gcol_a, 2, cv2.LINE_AA)

        # Right-click charge arc
        if rc_progress > 0.01:
            arc_cx = px + W - 28
            cv2.ellipse(canvas, (arc_cx, 122), (16, 16),
                        -90, 0, int(rc_progress * 360),
                        (0, 200, 255), 3, cv2.LINE_AA)
            cv2.putText(canvas, "HOLD",
                        (arc_cx - 12, 126),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.28,
                        (0, 200, 255), 1, cv2.LINE_AA)

        divider(153)

        # ── Shortcut legend ───────────────────────────────────────────────────
        cv2.putText(canvas, "SHORTCUTS", (x0, 167),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, C_DIM, 1, cv2.LINE_AA)

        rows = self.SHORTCUT_ROWS
        if not VOLUME_OK:
            rows = [r for r in rows if "Volume" not in r[1]]

        for i, (gesture, action) in enumerate(rows):
            y = 184 + i * 36
            # Highlight the currently active row
            active_label = self.GESTURE_META.get(self.active, ("","",""))[0]
            is_active = action.replace("→ ", "") in active_label or \
                        (self.active in ("SCROLL UP","SCROLL DOWN") and "Scroll" in action)
            row_col = C_WHITE if is_active else C_DIM
            row_thick = 2 if is_active else 1
            if is_active:
                cv2.rectangle(canvas,
                              (px+8, y-14), (px+W-8, y+18),
                              (35, 40, 55), -1)
            cv2.putText(canvas, gesture, (x0, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.34,
                        row_col, row_thick, cv2.LINE_AA)
            cv2.putText(canvas, action, (x0, y+14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.34,
                        tuple(int(c*0.7) for c in row_col), 1, cv2.LINE_AA)

        divider(CANVAS_H - 60)

        # ── Volume bar ────────────────────────────────────────────────────────
        if self.vol_pct is not None and VOLUME_OK:
            vy = CANVAS_H - 44
            cv2.putText(canvas, f"VOL", (x0, vy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.34, C_DIM, 1, cv2.LINE_AA)
            cv2.putText(canvas, f"{self.vol_pct}%", (x0+34, vy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, C_BLUE, 2, cv2.LINE_AA)
            vbx, vby = x0, vy + 6
            vbw = W - 32
            cv2.rectangle(canvas, (vbx, vby), (vbx+vbw, vby+6), (35,38,50), -1)
            fill = int(vbw * self.vol_pct / 100)
            cv2.rectangle(canvas, (vbx, vby), (vbx+fill, vby+6),
                          C_BLUE, -1, cv2.LINE_AA)

        # ── Screenshot counter ────────────────────────────────────────────────
        if self.shot_count:
            sy = CANVAS_H - 18
            cv2.putText(canvas, f"SHOTS  {self.shot_count:03d}",
                        (x0, sy), cv2.FONT_HERSHEY_SIMPLEX,
                        0.38, C_GREEN, 1, cv2.LINE_AA)

        # ── Quit hint ─────────────────────────────────────────────────────────
        cv2.putText(canvas, "Q  quit",
                    (px + W - 60, CANVAS_H - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, C_DIM, 1, cv2.LINE_AA)

        # ── Left divider line ─────────────────────────────────────────────────
        cv2.line(canvas, (px, 0), (px, CANVAS_H), C_BORDER, 1)


# ── Corner overlay drawn ON the camera feed ──────────────────────────────────
def draw_cam_overlay(img: np.ndarray, gesture: str, fps: float):
    """Minimal overlay on the camera feed — corner brackets + gesture pill."""
    h, w = img.shape[:2]
    L = 28   # bracket arm length
    T = 3    # bracket thickness
    col = (255, 190, 60)

    # Corner brackets
    for (cx, cy) in [(0,0),(w,0),(0,h),(w,h)]:
        sx = 1 if cx == 0 else -1
        sy = 1 if cy == 0 else -1
        ox, oy = cx + sx*6, cy + sy*6
        cv2.line(img,(ox,oy),(ox+sx*L,oy), col, T, cv2.LINE_AA)
        cv2.line(img,(ox,oy),(ox,oy+sy*L), col, T, cv2.LINE_AA)

    # Gesture pill bottom-left
    if gesture not in ("IDLE",""):
        label = gesture
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
        rx, ry = 10, h - 14
        cv2.rectangle(img, (rx-6, ry-th-6), (rx+tw+6, ry+4),
                      (20, 22, 32), -1)
        cv2.rectangle(img, (rx-6, ry-th-6), (rx+tw+6, ry+4),
                      col, 1, cv2.LINE_AA)
        cv2.putText(img, label, (rx, ry),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, col, 2, cv2.LINE_AA)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                          Gesture Helpers                                ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def get_finger_states(lm):
    tips = [4,  8, 12, 16, 20]
    pips = [3,  6, 10, 14, 18]
    out  = [1 if lm[tips[0]][0] > lm[pips[0]][0] else 0]
    for i in range(1, 5):
        out.append(1 if lm[tips[i]][1] < lm[pips[i]][1] else 0)
    return out

def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                            Main Loop                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def main():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,  720)
    cap.set(cv2.CAP_PROP_FPS,           60)
    # Sharper image: disable auto-exposure if supported
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)

    tracker = HandTracker(max_hands=1, detection_conf=0.78, tracking_conf=0.65)
    panel   = SidePanel()

    # Smoothing
    smooth_x, smooth_y = 0.0, 0.0
    SMOOTH = 0.72
    CAM_MARGIN_X = 0.10
    CAM_MARGIN_Y = 0.10

    # Pinch hysteresis
    PINCH_ENTER, PINCH_EXIT = 30, 42
    in_pinch = False

    # Right-click hold
    RC_HOLD_SEC   = 0.40
    rc_hold_start = None
    rc_fired      = False

    # Scroll
    SCROLL_LOCK_PX = 8
    SCROLL_SENS    = 0.55
    prev_scroll_y  = None

    # Cooldowns
    cd = {k: 0.0 for k in ["click","double","screenshot"]}
    CD = {"click":0.30, "double":0.55, "screenshot":0.80}

    # Volume
    prev_vol_dist = None

    shot_count = 0
    prev_time  = time.time()

    # ── Window setup ─────────────────────────────────────────────────────────
    cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_NAME, CANVAS_W, CANVAS_H)
    # Pin bottom-right, above taskbar
    win_x = SCREEN_W - CANVAS_W - 12
    win_y = SCREEN_H - CANVAS_H - 50
    cv2.moveWindow(WIN_NAME, win_x, win_y)

    print(f"\n[AI Virtual Mouse v3]  Q = quit")
    print(f"[Screenshots] → {SCREENSHOT_DIR}\n")

    while True:
        ok, raw = cap.read()
        if not ok:
            break

        raw = cv2.flip(raw, 1)

        now = time.time()
        dt  = max(now - prev_time, 1e-6)
        fps = 1.0 / dt
        prev_time = now

        for k in cd:
            cd[k] = max(0.0, cd[k] - dt)

        # ── Sharpen the camera frame ──────────────────────────────────────────
        # Unsharp mask: adds crisp edges, makes hand more visible on recording
        blur    = cv2.GaussianBlur(raw, (0, 0), 3)
        sharp   = cv2.addWeighted(raw, 1.6, blur, -0.6, 0)

        # Run detection on sharp frame
        proc = tracker.find_hands(sharp.copy(), draw=True)
        lm   = tracker.get_landmarks(proc)

        current_gesture = "IDLE"
        rc_progress     = 0.0

        if lm and len(lm) >= 21:
            idx_tip    = lm[8]
            thumb_tip  = lm[4]
            middle_tip = lm[12]
            wrist      = lm[0]
            cam_h, cam_w, _ = proc.shape

            fingers = get_finger_states(lm)
            pinch_d = dist(idx_tip, thumb_tip)
            mid_d   = dist(middle_tip, thumb_tip)

            # Pinch hysteresis
            if in_pinch:
                if pinch_d > PINCH_EXIT:  in_pinch = False
            else:
                if pinch_d < PINCH_ENTER: in_pinch = True

            tracker.add_trail_point(*idx_tip)

            # ── Priority 1: LEFT CLICK ────────────────────────────────────────
            if in_pinch and cd["click"] == 0:
                pyautogui.click()
                cd["click"] = CD["click"]
                in_pinch    = False
                tracker.trigger_ripple(*idx_tip, "LEFT CLICK")
                current_gesture = "LEFT CLICK"
                print("  ◆ Left Click")

            # ── Priority 2: DOUBLE CLICK ──────────────────────────────────────
            elif all(f==1 for f in fingers) and cd["double"] == 0:
                pyautogui.doubleClick()
                cd["double"] = CD["double"]
                tracker.trigger_ripple(*idx_tip, "DBL CLICK")
                current_gesture = "DBL CLICK"
                print("  ◆ Double Click")

            # ── Priority 3: SCREENSHOT ────────────────────────────────────────
            elif all(f==0 for f in fingers) and cd["screenshot"] == 0:
                shot_count += 1
                panel.shot_count = shot_count
                fname = str(SCREENSHOT_DIR / f"screenshot_{shot_count:03d}.png")
                pyautogui.screenshot(fname)
                cd["screenshot"] = CD["screenshot"]
                tracker.trigger_ripple(*wrist, "SCREENSHOT")
                current_gesture = "SCREENSHOT"
                print(f"  ◆ Screenshot → {fname}")

            # ── Priority 4: VOLUME ────────────────────────────────────────────
            elif (fingers[0]==1 and fingers[2]==1 and
                  fingers[1]==0 and fingers[3]==0 and VOLUME_OK):
                current_gesture = "VOLUME"
                if prev_vol_dist is not None:
                    delta = mid_d - prev_vol_dist
                    if abs(delta) > 4:
                        cur = _vol_ctrl.GetMasterVolumeLevelScalar()
                        nv  = float(np.clip(cur + delta*0.006, 0.0, 1.0))
                        _vol_ctrl.SetMasterVolumeLevelScalar(nv, None)
                        panel.vol_pct = int(nv * 100)
                        print(f"  ◆ Volume {panel.vol_pct}%")
                prev_vol_dist = mid_d

            # ── Priority 5: RIGHT CLICK ───────────────────────────────────────
            elif (fingers[1]==1 and fingers[2]==1 and
                  fingers[3]==0 and fingers[4]==0 and not in_pinch):
                if rc_hold_start is None:
                    rc_hold_start = now
                    rc_fired      = False
                held = now - rc_hold_start
                rc_progress     = min(held / RC_HOLD_SEC, 1.0)
                current_gesture = "RIGHT CLICK"
                if held >= RC_HOLD_SEC and not rc_fired:
                    pyautogui.rightClick()
                    rc_fired = True
                    tracker.trigger_ripple(*idx_tip, "RIGHT CLICK")
                    print("  ◆ Right Click")
            else:
                rc_hold_start = None
                rc_fired      = False
                prev_vol_dist = None

            # ── Priority 6: SCROLL (index+middle+ring up) ─────────────────────
            if (current_gesture == "IDLE" and
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
                    current_gesture = "SCROLL UP"
                prev_scroll_y = idx_tip[1]
            else:
                prev_scroll_y = None

            # ── Priority 7: CURSOR (index only) ──────────────────────────────
            if (current_gesture in ("IDLE","CURSOR") and
                    fingers[1]==1 and fingers[2]==0 and
                    fingers[3]==0 and fingers[4]==0 and not in_pinch):
                nx = (idx_tip[0]/cam_w - CAM_MARGIN_X) / (1.0 - 2*CAM_MARGIN_X)
                ny = (idx_tip[1]/cam_h - CAM_MARGIN_Y) / (1.0 - 2*CAM_MARGIN_Y)
                nx = max(0.0, min(1.0, nx))
                ny = max(0.0, min(1.0, ny))
                smooth_x = smooth_x * SMOOTH + nx*SCREEN_W * (1.0-SMOOTH)
                smooth_y = smooth_y * SMOOTH + ny*SCREEN_H * (1.0-SMOOTH)
                pyautogui.moveTo(smooth_x, smooth_y)
                current_gesture = "CURSOR"

        else:
            prev_scroll_y = None
            prev_vol_dist = None
            rc_hold_start = None

        # ── Compose final canvas ──────────────────────────────────────────────
        # Resize processed frame (with skeleton drawn) to display size
        cam_display = cv2.resize(proc, (CAM_DISPLAY_W, CAM_DISPLAY_H),
                                 interpolation=cv2.INTER_LANCZOS4)

        # Draw minimal overlay on cam feed
        draw_cam_overlay(cam_display, current_gesture, fps)

        # Build canvas: cam feed left, panel right
        canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
        canvas[:, :CAM_DISPLAY_W] = cam_display

        # Draw side panel
        panel.set_gesture(current_gesture)
        panel.draw(canvas, fps,
                   rc_progress=rc_progress,
                   vol_pct=panel.vol_pct if VOLUME_OK else None)

        cv2.imshow(WIN_NAME, canvas)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("\n[AI Virtual Mouse] Exited cleanly.")


if __name__ == "__main__":
    main()