import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import os
import urllib.request
import numpy as np
import time

MODEL_PATH = "hand_landmarker.task"
if not os.path.exists(MODEL_PATH):
    print("Downloading hand landmarker model...")
    url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    urllib.request.urlretrieve(url, MODEL_PATH)
    print("Download complete.")

# ─── MediaPipe hand skeleton connections ───────────────────────────────────────
HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),          # thumb
    (0,5),(5,6),(6,7),(7,8),          # index
    (0,9),(9,10),(10,11),(11,12),     # middle
    (0,13),(13,14),(14,15),(15,16),   # ring
    (0,17),(17,18),(18,19),(19,20),   # pinky
    (5,9),(9,13),(13,17),             # palm
]

FINGERTIP_IDS  = [4, 8, 12, 16, 20]
FINGER_COLORS  = [
    (0,  255, 255),   # thumb  – yellow
    (255,  0, 255),   # index  – magenta
    (0,  255,   0),   # middle – green
    (255,128,   0),   # ring   – orange
    (0,  128, 255),   # pinky  – sky blue
]

class HandTracker:
    """
    Production-grade hand tracker with smooth landmark rendering,
    per-finger colouring, gesture-trail animation, and confidence display.
    """

    def __init__(self,
                 max_hands: int = 1,
                 detection_conf: float = 0.75,
                 tracking_conf : float = 0.60):

        self.max_hands = max_hands

        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=max_hands,
            min_hand_detection_confidence=detection_conf,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=tracking_conf,
        )
        self.detector  = vision.HandLandmarker.create_from_options(options)
        self.results   = None

        # Trail / ripple animation state
        self._trail: list[tuple[int,int,float]] = []   # (x, y, timestamp)
        self._ripples: list[tuple[int,int,float,str]]  = []  # (x,y,ts,label)
        self.TRAIL_DURATION   = 0.30   # seconds trail stays visible
        self.RIPPLE_DURATION  = 0.45   # seconds ripple expands

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def find_hands(self, img: np.ndarray, draw: bool = True) -> np.ndarray:
        """Detect hands and optionally draw the professional overlay."""
        rgb      = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self.results = self.detector.detect(mp_image)

        if draw and self.results.hand_landmarks:
            h, w, _ = img.shape
            for hand_lms in self.results.hand_landmarks:
                pts = [(int(lm.x * w), int(lm.y * h)) for lm in hand_lms]
                self._draw_skeleton(img, pts)
                self._draw_fingertips(img, pts)
                self._draw_palm_circle(img, pts)

            # Animated overlays
            self._draw_trail(img)
            self._draw_ripples(img)

        return img

    def get_landmarks(self, img: np.ndarray, hand_no: int = 0) -> list[tuple[int,int]]:
        """Return pixel-space (x, y) for all 21 landmarks, or [] if no hand."""
        if not self.results or not self.results.hand_landmarks:
            return []
        if len(self.results.hand_landmarks) <= hand_no:
            return []
        h, w, _ = img.shape
        return [
            (int(lm.x * w), int(lm.y * h))
            for lm in self.results.hand_landmarks[hand_no]
        ]

    def add_trail_point(self, x: int, y: int):
        """Feed the index-finger tip position to build the motion trail."""
        self._trail.append((x, y, time.time()))

    def trigger_ripple(self, x: int, y: int, label: str = ""):
        """Spawn an expanding ripple at (x,y) with an optional label."""
        self._ripples.append((x, y, time.time(), label))

    # ──────────────────────────────────────────────────────────────────────────
    # Private drawing helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_skeleton(self, img: np.ndarray, pts: list):
        """Draw semi-transparent hand bones."""
        overlay = img.copy()
        for (a, b) in HAND_CONNECTIONS:
            cv2.line(overlay, pts[a], pts[b], (200, 200, 200), 2, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)

    def _draw_fingertips(self, img: np.ndarray, pts: list):
        """Draw coloured halos + solid dots for each fingertip."""
        finger_names = ["Thumb","Index","Middle","Ring","Pinky"]
        for i, (tip_id, color) in enumerate(zip(FINGERTIP_IDS, FINGER_COLORS)):
            x, y = pts[tip_id]
            # Outer halo (transparent-ish via addWeighted trick)
            overlay = img.copy()
            cv2.circle(overlay, (x, y), 18, color, -1)
            cv2.addWeighted(overlay, 0.20, img, 0.80, 0, img)
            # Solid inner dot
            cv2.circle(img, (x, y), 9, color, -1, cv2.LINE_AA)
            cv2.circle(img, (x, y), 9, (255,255,255), 1, cv2.LINE_AA)

    def _draw_palm_circle(self, img: np.ndarray, pts: list):
        """Draw a subtle circle at the palm centre (landmark 9)."""
        cx, cy = pts[9]
        overlay = img.copy()
        cv2.circle(overlay, (cx, cy), 22, (80, 80, 255), -1)
        cv2.addWeighted(overlay, 0.18, img, 0.82, 0, img)
        cv2.circle(img, (cx, cy), 22, (120,120,255), 1, cv2.LINE_AA)

    def _draw_trail(self, img: np.ndarray):
        """Draw a fading motion trail behind the index fingertip."""
        now    = time.time()
        cutoff = now - self.TRAIL_DURATION
        self._trail = [(x, y, t) for x, y, t in self._trail if t > cutoff]

        if len(self._trail) < 2:
            return

        for i in range(1, len(self._trail)):
            x1, y1, t1 = self._trail[i-1]
            x2, y2, t2 = self._trail[i]
            age   = now - t2
            alpha = max(0.0, 1.0 - age / self.TRAIL_DURATION)
            thick = max(1, int(alpha * 4))
            blue  = int(alpha * 255)
            color = (blue, int(blue * 0.4), 255)

            overlay = img.copy()
            cv2.line(overlay, (x1,y1), (x2,y2), color, thick, cv2.LINE_AA)
            cv2.addWeighted(overlay, alpha * 0.7, img, 1 - alpha * 0.7, 0, img)

    def _draw_ripples(self, img: np.ndarray):
        """Draw expanding ripple rings for gesture events."""
        now    = time.time()
        cutoff = now - self.RIPPLE_DURATION
        self._ripples = [(x,y,t,lbl) for x,y,t,lbl in self._ripples if t > cutoff]

        h, w, _ = img.shape
        for (rx, ry, rt, label) in self._ripples:
            age      = now - rt
            progress = age / self.RIPPLE_DURATION        # 0→1
            alpha    = 1.0 - progress
            radius   = int(progress * 60) + 10
            thick    = max(1, int(alpha * 3))
            color    = (int(255*alpha), int(200*alpha), 0)

            overlay = img.copy()
            cv2.circle(overlay, (rx, ry), radius, color, thick, cv2.LINE_AA)
            cv2.addWeighted(overlay, alpha * 0.8, img, 1 - alpha*0.8, 0, img)

            if label:
                font_scale = 0.55 + progress * 0.15
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX,
                                              font_scale, 2)
                tx = max(5, min(rx - tw//2, w - tw - 5))
                ty = max(th + 5, ry - radius - 10)
                cv2.putText(img, label,
                            (tx + 1, ty + 1),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            font_scale, (0,0,0), 2, cv2.LINE_AA)
                cv2.putText(img, label,
                            (tx, ty),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            font_scale, color, 2, cv2.LINE_AA)