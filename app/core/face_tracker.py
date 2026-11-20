import cv2
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import numpy as np

logger = logging.getLogger("clipstream.face_tracker")

class FaceTracker:
    def __init__(self):
        # OpenCV built-in Haar Cascade for frontal face
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

    def detect_face_in_frame(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """
        Detect the primary/largest face in frame.
        Returns (x, y, w, h) or None.
        """
        if frame is None or frame.size == 0:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.12,
            minNeighbors=5,
            minSize=(50, 50)
        )
        if len(faces) == 0:
            return None

        # Return largest face by area (w * h)
        largest = max(faces, key=lambda f: f[2] * f[3])
        return tuple(int(v) for v in largest)

    def find_facecam_region(
        self,
        video_path: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        preferred_position: str = "auto",
        sample_frames: int = 20
    ) -> Dict[str, Any]:
        """
        Detect or position the streamer facecam region for Gaming Split / PiP layouts.
        Samples frames strictly within [start_time, end_time] of the clip.
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {"detected": False, "x": 0, "y": 0, "w": 400, "h": 400}

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

        if total_frames <= 0 or orig_w <= 0 or orig_h <= 0:
            cap.release()
            return {"detected": False, "x": 0, "y": 0, "w": 400, "h": 400}

        # Preset coordinates for specific user-selected positions
        quadrants = {
            "top-right": {
                "x": int(orig_w * 0.62),
                "y": int(orig_h * 0.03),
                "w": int(orig_w * 0.35),
                "h": int(orig_h * 0.45)
            },
            "top-left": {
                "x": int(orig_w * 0.03),
                "y": int(orig_h * 0.03),
                "w": int(orig_w * 0.35),
                "h": int(orig_h * 0.45)
            },
            "bottom-right": {
                "x": int(orig_w * 0.62),
                "y": int(orig_h * 0.52),
                "w": int(orig_w * 0.35),
                "h": int(orig_h * 0.45)
            },
            "bottom-left": {
                "x": int(orig_w * 0.03),
                "y": int(orig_h * 0.52),
                "w": int(orig_w * 0.35),
                "h": int(orig_h * 0.45)
            },
            "center": {
                "x": int(orig_w * 0.30),
                "y": int(orig_h * 0.15),
                "w": int(orig_w * 0.40),
                "h": int(orig_h * 0.55)
            }
        }

        # If user explicitly selected a position, use it immediately
        if preferred_position in quadrants:
            cap.release()
            preset = quadrants[preferred_position]
            return {
                "detected": True,
                "position": preferred_position,
                "x": preset["x"],
                "y": preset["y"],
                "w": preset["w"],
                "h": preset["h"],
                "orig_w": orig_w,
                "orig_h": orig_h
            }

        # Auto-detect: Sample frames STRICTLY within [start_time, end_time]
        start_frame = int(start_time * fps) if (start_time is not None and start_time > 0) else 0
        end_frame = int(end_time * fps) if (end_time is not None and end_time > 0) else total_frames
        start_frame = max(0, min(start_frame, total_frames - 1))
        end_frame = max(start_frame + 1, min(end_frame, total_frames))

        frame_step = max(1, (end_frame - start_frame) // sample_frames)
        detected_faces = []

        for f_idx in range(start_frame, end_frame, frame_step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            face = self.detect_face_in_frame(frame)
            if face:
                detected_faces.append(face)

        cap.release()

        # If no face detected, default to Top-Right (standard gaming stream facecam position)
        if not detected_faces:
            logger.info("No face detected in clip; defaulting to standard Top-Right facecam position.")
            preset = quadrants["top-right"]
            return {
                "detected": False,
                "position": "top-right",
                "x": preset["x"],
                "y": preset["y"],
                "w": preset["w"],
                "h": preset["h"],
                "orig_w": orig_w,
                "orig_h": orig_h
            }

        # Cluster face detections by quadrant to find where the streamer actually sits
        # (This prevents averaging two faces on opposite sides of the screen)
        quad_counts = {"top-left": [], "top-right": [], "bottom-left": [], "bottom-right": []}
        mid_x = orig_w / 2.0
        mid_y = orig_h / 2.0

        for f in detected_faces:
            cx = f[0] + f[2] / 2.0
            cy = f[1] + f[3] / 2.0
            if cy < mid_y:
                quad = "top-left" if cx < mid_x else "top-right"
            else:
                quad = "bottom-left" if cx < mid_x else "bottom-right"
            quad_counts[quad].append(f)

        # Choose the quadrant with the most consistent face detections
        best_quad = max(quad_counts, key=lambda k: len(quad_counts[k]))
        dominant_faces = quad_counts[best_quad] if quad_counts[best_quad] else detected_faces

        avg_x = int(np.mean([f[0] for f in dominant_faces]))
        avg_y = int(np.mean([f[1] for f in dominant_faces]))
        avg_w = int(np.mean([f[2] for f in dominant_faces]))
        avg_h = int(np.mean([f[3] for f in dominant_faces]))

        # Generous padding around the face so head and shoulders fit comfortably in the frame
        pad_w = int(max(avg_w * 2.2, orig_w * 0.30))
        pad_h = int(max(avg_h * 2.4, orig_h * 0.40))
        center_x = avg_x + avg_w // 2
        center_y = avg_y + avg_h // 2

        crop_x = max(0, min(orig_w - pad_w, center_x - pad_w // 2))
        crop_y = max(0, min(orig_h - pad_h, center_y - pad_h // 2))
        crop_w = min(orig_w - crop_x, pad_w)
        crop_h = min(orig_h - crop_y, pad_h)

        # Ensure even dimensions for libx264
        crop_w = crop_w - (crop_w % 2)
        crop_h = crop_h - (crop_h % 2)

        return {
            "detected": True,
            "position": best_quad,
            "x": crop_x,
            "y": crop_y,
            "w": crop_w,
            "h": crop_h,
            "orig_w": orig_w,
            "orig_h": orig_h
        }

    def compute_smart_tracking_crop(
        self,
        video_path: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        preferred_focus: str = "auto",
        sample_frames: int = 25
    ) -> Dict[str, Any]:
        """
        Compute primary speaker center X ratio (0.0 to 1.0) for 9:16 vertical crop.
        Samples frames strictly within [start_time, end_time].
        """
        # Manual speaker position overrides
        if preferred_focus == "left":
            return {"center_x_ratio": 0.28, "detected": True, "mode": "left"}
        elif preferred_focus == "center":
            return {"center_x_ratio": 0.50, "detected": True, "mode": "center"}
        elif preferred_focus == "right":
            return {"center_x_ratio": 0.72, "detected": True, "mode": "right"}
        else:
            # Check if numeric string passed (e.g. "0.35")
            try:
                val = float(preferred_focus)
                if 0.05 <= val <= 0.95:
                    return {"center_x_ratio": round(val, 3), "detected": True, "mode": "custom"}
            except (ValueError, TypeError):
                pass

        # Auto-detect within clip time range
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {"center_x_ratio": 0.50, "detected": False, "mode": "fallback"}

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

        if total_frames <= 0 or orig_w <= 0:
            cap.release()
            return {"center_x_ratio": 0.50, "detected": False, "mode": "fallback"}

        start_frame = int(start_time * fps) if (start_time is not None and start_time > 0) else 0
        end_frame = int(end_time * fps) if (end_time is not None and end_time > 0) else total_frames
        start_frame = max(0, min(start_frame, total_frames - 1))
        end_frame = max(start_frame + 1, min(end_frame, total_frames))

        frame_step = max(1, (end_frame - start_frame) // sample_frames)
        centers_x = []

        for f_idx in range(start_frame, end_frame, frame_step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            face = self.detect_face_in_frame(frame)
            if face:
                cx = face[0] + face[2] / 2.0
                centers_x.append(cx / float(orig_w))

        cap.release()

        if not centers_x:
            logger.info("No face detected for smart tracking; defaulting to center (0.50).")
            return {"center_x_ratio": 0.50, "detected": False, "mode": "center_default"}

        median_center = float(np.median(centers_x))
        # Clamp to avoid extreme edge crops where 9:16 box would extend past video boundary
        # In 16:9 video, 9:16 width is (9/16)/(16/9) = 31.6% of video width.
        # Half of that is ~16%. So center should stay between 0.16 and 0.84!
        clamped_center = max(0.18, min(0.82, median_center))

        logger.info(f"Smart tracking detected speaker center X ratio: {clamped_center:.3f}")
        return {
            "center_x_ratio": round(clamped_center, 3),
            "detected": True,
            "mode": "auto"
        }
