import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import os
import urllib.request

MODEL_PATH = "hand_landmarker.task"
if not os.path.exists(MODEL_PATH):
    print("Downloading hand landmarker model...")
    url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    urllib.request.urlretrieve(url, MODEL_PATH)
    print("Download complete.")

class HandTracker:
    def __init__(self, max_hands=1, detection_conf=0.7, tracking_conf=0.5):
        self.max_hands = max_hands
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=max_hands,
            min_hand_detection_confidence=detection_conf,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=tracking_conf
        )
        self.detector = vision.HandLandmarker.create_from_options(options)

    def find_hands(self, img, draw=True):
        # Convert BGR to RGB and to MediaPipe Image
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self.results = self.detector.detect(mp_image)

        if draw and self.results.hand_landmarks:
            h, w, _ = img.shape
            for hand_landmarks in self.results.hand_landmarks:
                # Draw all landmarks as small green circles
                for lm in hand_landmarks:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cv2.circle(img, (cx, cy), 3, (0, 255, 0), -1)
        return img

    def get_landmarks(self, img, hand_no=0):
        landmarks = []
        if self.results.hand_landmarks and len(self.results.hand_landmarks) > hand_no:
            hand = self.results.hand_landmarks[hand_no]
            h, w, _ = img.shape
            for lm in hand:
                cx, cy = int(lm.x * w), int(lm.y * h)
                landmarks.append((cx, cy))
        return landmarks