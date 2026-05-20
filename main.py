"""
AI Virtual Mouse — Professional Edition
----------------------------------------
Controls:
  ✦ Move cursor     →  index finger (1 finger up)
  ✦ Left click      →  thumb + index pinch
  ✦ Right click     →  index + middle up, ring + pinky down  (no pinch)
  ✦ Double click    →  all 5 fingers open
  ✦ Scroll          →  index + middle up → move hand vertically
  ✦ Volume          →  thumb + middle pinch (index down) → spread/close
  ✦ Screenshot      →  fist (all fingers closed)
  ✦ Quit            →  press  Q
"""

import cv2
import math
import time
import numpy as np
import pyautogui
from src.hand_tracker import HandTracker

# ── Optional Windows volume control ─────────────────────────────────────────
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    _dev       = AudioUtilities.GetSpeakers()
    _iface     = _dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    _vol_ctrl  = _iface.QueryInterface(IAudioEndpointVolume)
    VOLUME_OK  = True
    print("[OK] Volume control ready")
except Exception:
    _vol_ctrl  = None
    VOLUME_OK  = False
    print("[--] Volume control unavailable (pycaw / comtypes not installed)")

# ── PyAutoGUI safety ─────────────────────────────────────────────────────────
pyautogui.FAILSAFE   = True
pyautogui.PAUSE      = 0.0

SCREEN_W, SCREEN_H   = pyautogui.size()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                          HUD Renderer                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝
class HUD:
    """Draws a dark glass panel + gesture/status indicators onto the frame."""

    PANEL_W  = 310
    PANEL_H  = 240
    MARGIN   = 14

    GESTURE_ICONS = {
        "CURSOR"     : "☝  Cursor Move",
        "LEFT CLICK" : "👌 Left Click",
        "RIGHT CLICK": "✌  Right Click",
        "DBL CLICK"  : "🖐  Double Click",
        "SCROLL"     : "✌  Scroll",
        "VOLUME"     : "🤙 Volume",
        "SCREENSHOT" : "✊  Screenshot",
        "IDLE"       : "—  Idle",
    }

    def __init__(self):
        self.active_gesture    = "IDLE"
        self.gesture_alpha     = 0.0      # fade-in progress
        self.prev_gesture      = "IDLE"
        self.fps_history       = []
        self.screenshot_count  = 0
        self.volume_pct        = None

    def set_gesture(self, name: str):
        if name != self.active_gesture:
            self.prev_gesture  = self.active_gesture
            self.active_gesture = name
            self.gesture_alpha  = 0.0    # trigger fade-in

    def draw(self, img: np.ndarray, fps: float, vol_pct=None):
        h, w, _ = img.shape
        self.fps_history.append(fps)
        if len(self.fps_history) > 30:
            self.fps_history.pop(0)
        avg_fps = sum(self.fps_history) / len(self.fps_history)

        if vol_pct is not None:
            self.volume_pct = vol_pct

        # Animate gesture alpha
        if self.gesture_alpha < 1.0:
            self.gesture_alpha = min(1.0, self.gesture_alpha + 0.12)

        # ── Glass panel ──────────────────────────────────────────────────────
        px = w - self.PANEL_W - self.MARGIN
        py = self.MARGIN
        panel = img[py:py+self.PANEL_H, px:px+self.PANEL_W]

        glass = np.zeros_like(panel)
        glass[:] = (20, 20, 30)
        cv2.addWeighted(glass, 0.72, panel, 0.28, 0, panel)
        img[py:py+self.PANEL_H, px:px+self.PANEL_W] = panel

        # Panel border with accent line
        cv2.rectangle(img, (px,py), (px+self.PANEL_W, py+self.PANEL_H),
                      (60, 60, 80), 1, cv2.LINE_AA)
        cv2.line(img, (px, py+1), (px+self.PANEL_W, py+1),
                 (100, 180, 255), 2, cv2.LINE_AA)

        # Title
        cv2.putText(img, "AI VIRTUAL MOUSE",
                    (px+12, py+24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                    (100, 200, 255), 1, cv2.LINE_AA)

        # FPS bar
        bar_x  = px + 12
        bar_y  = py + 36
        bar_w  = self.PANEL_W - 24
        bar_h  = 6
        ratio  = min(avg_fps / 60.0, 1.0)
        cv2.rectangle(img, (bar_x, bar_y),
                      (bar_x + bar_w, bar_y + bar_h), (40,40,60), -1)
        bar_color = (0, 220, 120) if avg_fps >= 25 else (0, 140, 255)
        cv2.rectangle(img, (bar_x, bar_y),
                      (bar_x + int(bar_w * ratio), bar_y + bar_h),
                      bar_color, -1, cv2.LINE_AA)
        cv2.putText(img, f"FPS  {avg_fps:4.1f}",
                    (bar_x, bar_y - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40,
                    (160,160,180), 1, cv2.LINE_AA)

        # Active gesture (fades in)
        ga   = self.gesture_alpha
        gest = self.GESTURE_ICONS.get(self.active_gesture,
                                      self.active_gesture)
        g_color = tuple(int(c * ga) for c in (60, 220, 255))
        cv2.putText(img, gest,
                    (px + 12, py + 74),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                    g_color, 2, cv2.LINE_AA)

        # Separator
        cv2.line(img, (px+10, py+84), (px+self.PANEL_W-10, py+84),
                 (50, 50, 70), 1)

        # Shortcut legend
        legend = [
            ("Pinch",         "Left Click"),
            ("✌ + no pinch", "Right Click"),
            ("All open",      "Dbl Click"),
            ("✌ + move",     "Scroll"),
            ("Fist",          "Screenshot"),
        ]
        if VOLUME_OK:
            legend.append(("Thumb+Middle", "Volume"))

        for i, (key, val) in enumerate(legend):
            yy = py + 100 + i * 20
            cv2.putText(img, key,
                        (px + 14, yy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                        (120, 120, 150), 1, cv2.LINE_AA)
            cv2.putText(img, val,
                        (px + 150, yy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                        (200, 200, 220), 1, cv2.LINE_AA)

        # Volume bar (bottom of panel)
        if self.volume_pct is not None and VOLUME_OK:
            vby   = py + self.PANEL_H - 20
            vbx   = px + 12
            vbw   = self.PANEL_W - 24
            ratio = self.volume_pct / 100.0
            cv2.rectangle(img, (vbx, vby), (vbx+vbw, vby+8),
                          (40, 40, 60), -1)
            cv2.rectangle(img, (vbx, vby),
                          (vbx + int(vbw * ratio), vby + 8),
                          (80, 180, 255), -1, cv2.LINE_AA)
            cv2.putText(img, f"VOL {self.volume_pct}%",
                        (vbx, vby - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                        (130, 180, 255), 1, cv2.LINE_AA)

        # Screenshot count badge (top-left corner)
        if self.screenshot_count:
            badge = f"📷 {self.screenshot_count}"
            cv2.putText(img, badge,
                        (14, 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (0, 220, 120), 2, cv2.LINE_AA)

        # Quit hint (bottom-left)
        cv2.putText(img, "Q  quit",
                    (14, h - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                    (90, 90, 110), 1, cv2.LINE_AA)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                           Gesture Engine                                ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def get_finger_states(landmarks: list[tuple[int,int]]) -> list[int]:
    """
    Returns [thumb, index, middle, ring, pinky] — 1 = extended, 0 = folded.
    Uses proper DIP comparisons; thumb uses X-axis for flipped camera.
    """
    tips = [4, 8, 12, 16, 20]
    pips = [3, 6, 10, 14, 18]   # proximal joints
    states = []

    # Thumb (horizontal check, mirrored camera)
    states.append(1 if landmarks[tips[0]][0] > landmarks[pips[0]][0] else 0)

    # Fingers (vertical check: tip y < pip y means extended)
    for i in range(1, 5):
        states.append(1 if landmarks[tips[i]][1] < landmarks[pips[i]][1] else 0)

    return states


def dist(a: tuple, b: tuple) -> float:
    return math.hypot(a[0]-b[0], a[1]-b[1])


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                              Main Loop                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def main():
    cap     = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,  720)
    cap.set(cv2.CAP_PROP_FPS,           60)

    tracker = HandTracker(max_hands=1, detection_conf=0.78, tracking_conf=0.65)
    hud     = HUD()

    # ── Smoothing state ──────────────────────────────────────────────────────
    smooth_x, smooth_y   = 0.0, 0.0
    SMOOTHING            = 0.72        # higher = smoother (but slightly laggier)

    # Map only inner 80% of frame to avoid edge jitter
    CAM_MARGIN_X  = 0.10
    CAM_MARGIN_Y  = 0.10

    # ── Cooldown counters (in seconds) ───────────────────────────────────────
    cd: dict[str, float] = {k: 0.0 for k in
        ["click","right","double","screenshot"]}
    CD = {"click":0.35, "right":0.40, "double":0.55, "screenshot":0.80}

    # ── Scroll state ─────────────────────────────────────────────────────────
    prev_scroll_y     = None
    SCROLL_SENS       = 0.6

    # ── Volume state ─────────────────────────────────────────────────────────
    prev_vol_dist     = None

    # ── Screenshot counter ────────────────────────────────────────────────────
    shot_count        = 0

    prev_time         = time.time()

    print("\n[AI Virtual Mouse] Running — press  Q  to quit\n")

    while True:
        ok, img = cap.read()
        if not ok:
            break

        img = cv2.flip(img, 1)

        now = time.time()
        fps = 1.0 / max(now - prev_time, 1e-6)
        prev_time = now

        # Cool down all timers
        for k in cd:
            cd[k] = max(0.0, cd[k] - (1.0/fps if fps > 0 else 0))

        img = tracker.find_hands(img, draw=True)
        lm  = tracker.get_landmarks(img)

        current_gesture = "IDLE"

        if lm and len(lm) >= 21:
            idx_tip    = lm[8]
            thumb_tip  = lm[4]
            middle_tip = lm[12]
            ring_tip   = lm[16]
            pinky_tip  = lm[20]
            wrist      = lm[0]

            fingers    = get_finger_states(lm)
            pinch_d    = dist(idx_tip, thumb_tip)
            mid_d      = dist(middle_tip, thumb_tip)

            # ── Feed trail ───────────────────────────────────────────────────
            tracker.add_trail_point(*idx_tip)

            # ── Cursor movement ──────────────────────────────────────────────
            cam_h, cam_w, _ = img.shape
            # Map within the inner (1-2*margin) zone → full screen
            nx = (idx_tip[0]/cam_w - CAM_MARGIN_X) / (1.0 - 2*CAM_MARGIN_X)
            ny = (idx_tip[1]/cam_h - CAM_MARGIN_Y) / (1.0 - 2*CAM_MARGIN_Y)
            nx = max(0.0, min(1.0, nx))
            ny = max(0.0, min(1.0, ny))

            screen_x  = nx * SCREEN_W
            screen_y  = ny * SCREEN_H
            smooth_x  = smooth_x * SMOOTHING + screen_x * (1.0 - SMOOTHING)
            smooth_y  = smooth_y * SMOOTHING + screen_y * (1.0 - SMOOTHING)
            pyautogui.moveTo(smooth_x, smooth_y)
            current_gesture = "CURSOR"

            # ── Left click (thumb+index pinch) ───────────────────────────────
            if pinch_d < 32 and cd["click"] == 0 and cd["right"] == 0:
                pyautogui.click()
                cd["click"] = CD["click"]
                tracker.trigger_ripple(*idx_tip, "LEFT CLICK")
                current_gesture = "LEFT CLICK"
                print(f"  ◆ Left Click @ screen ({smooth_x:.0f}, {smooth_y:.0f})")

            # ── Right click (index+middle up, ring+pinky down, no pinch) ─────
            elif (fingers[1]==1 and fingers[2]==1 and
                  fingers[3]==0 and fingers[4]==0 and
                  pinch_d >= 32 and cd["right"] == 0):
                pyautogui.rightClick()
                cd["right"] = CD["right"]
                tracker.trigger_ripple(*idx_tip, "RIGHT CLICK")
                current_gesture = "RIGHT CLICK"
                print("  ◆ Right Click")

            # ── Double click (all fingers open) ──────────────────────────────
            elif all(f==1 for f in fingers) and cd["double"] == 0:
                pyautogui.doubleClick()
                cd["double"] = CD["double"]
                tracker.trigger_ripple(*idx_tip, "DBL CLICK")
                current_gesture = "DBL CLICK"
                print("  ◆ Double Click")

            # ── Screenshot (fist) ────────────────────────────────────────────
            elif all(f==0 for f in fingers) and cd["screenshot"] == 0:
                shot_count += 1
                hud.screenshot_count = shot_count
                fname = f"screenshot_{shot_count:03d}.png"
                pyautogui.screenshot(fname)
                cd["screenshot"] = CD["screenshot"]
                tracker.trigger_ripple(*wrist, "SCREENSHOT")
                current_gesture = "SCREENSHOT"
                print(f"  ◆ Screenshot saved → {fname}")

            # ── Volume control (thumb+middle pinch, index down) ───────────────
            elif (fingers[0]==1 and fingers[2]==1 and
                  fingers[1]==0 and VOLUME_OK):
                current_gesture = "VOLUME"
                if prev_vol_dist is not None:
                    delta = mid_d - prev_vol_dist
                    if abs(delta) > 4:
                        cur   = _vol_ctrl.GetMasterVolumeLevelScalar()
                        nv    = float(np.clip(cur + delta * 0.006, 0.0, 1.0))
                        _vol_ctrl.SetMasterVolumeLevelScalar(nv, None)
                        hud.volume_pct = int(nv * 100)
                        print(f"  ◆ Volume {hud.volume_pct}%")
                prev_vol_dist = mid_d
            else:
                prev_vol_dist = None

            # ── Scroll (index+middle up, vertical motion) ─────────────────────
            if (fingers[1]==1 and fingers[2]==1 and pinch_d >= 32
                    and current_gesture not in ("RIGHT CLICK","VOLUME")):
                current_gesture = "SCROLL"
                if prev_scroll_y is not None:
                    dy = middle_tip[1] - prev_scroll_y
                    if abs(dy) > 5:
                        pyautogui.scroll(-int(dy * SCROLL_SENS))
                prev_scroll_y = middle_tip[1]
            else:
                if current_gesture != "SCROLL":
                    prev_scroll_y = None

        else:
            # No hand detected — fade everything
            prev_scroll_y = None
            prev_vol_dist = None

        # ── Update HUD ───────────────────────────────────────────────────────
        hud.set_gesture(current_gesture)
        vol_display = hud.volume_pct if VOLUME_OK else None
        hud.draw(img, fps, vol_pct=vol_display)

        cv2.imshow("AI Virtual Mouse — Pro", img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("\n[AI Virtual Mouse] Exited cleanly.")


if __name__ == "__main__":
    main()