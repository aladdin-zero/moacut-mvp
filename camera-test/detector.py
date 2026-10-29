"""Motion/absence capture proposals, not product identity recognition."""
import numpy as np
import cv2


def compensated_difference(current, reference):
    """Remove global exposure changes using the majority unchanged background."""
    offset = float(np.median(current - reference))
    gain = 1.0
    for _ in range(3):
        residual = np.abs(current - (reference * gain + offset))
        keep = residual <= np.percentile(residual, 60)
        x, y = reference[keep], current[keep]
        if x.size and float(np.var(x)) > 36:
            gain = float(np.clip(np.mean((x-x.mean())*(y-y.mean())) / np.var(x), .6, 1.6))
            offset = float(np.clip(np.median(y - gain*x), -60, 60))
        else:
            offset = float(np.clip(np.median(y-x), -60, 60))
    return np.abs(current - np.clip(reference * gain + offset, 0, 255))


class Detector:
    def __init__(self, stable_seconds=0.65, empty_seconds=1.2):
        self.stable_seconds = stable_seconds
        self.empty_seconds = empty_seconds
        self.reference = None
        self.reset()

    def reset(self):
        self.previous = None
        self.last_capture = None
        self.stable_since = None
        self.empty_since = None
        self.was_present = False
        self.armed = True
        self.state = "uncalibrated" if self.reference is None else "empty"

    def calibrate(self, gray):
        values = np.asarray(gray, dtype=np.float32)
        self.reference = np.median(values, axis=0) if values.ndim == 3 else values.copy()
        self.reset()
        self.previous = self.reference.copy()

    def update(self, gray, now, allow_capture=True):
        current = gray.astype(np.float32)
        if self.reference is None:
            return {"state": "uncalibrated", "capture": False, "boundary": False}
        residual = compensated_difference(current, self.reference)
        mask = (residual > 24).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        occupancy = float(np.mean(mask))
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        largest = float(stats[1:, cv2.CC_STAT_AREA].max() / mask.size) if count > 1 else 0.0
        motion = 0.0 if self.previous is None else float(np.mean(compensated_difference(current, self.previous)))
        self.previous = current.copy()
        result = dict(capture=False, boundary=False, occupancy=round(occupancy, 3),
                      motion=round(motion, 2), largest=round(largest, 3))
        # shortcut: foreground presence, not garment recognition; validate hands/shadows on site.
        if occupancy < 0.03:
            self.stable_since = None
            if self.empty_since is None:
                self.empty_since = now
            if now - self.empty_since >= self.empty_seconds:
                result["boundary"] = self.was_present
                self.was_present = False
                self.last_capture = None
                self.armed = True
            self.state = "empty"
        elif occupancy > .85 or largest < .07 or occupancy < .08:
            self.stable_since = None
            self.empty_since = None
            self.state = "scene_changed" if occupancy > .85 else "uncertain"
        else:
            self.empty_since = None
            self.was_present = True
            if motion > 2.5:
                self.stable_since = None
                self.armed = True
                self.state = "moving"
            else:
                if self.stable_since is None:
                    self.stable_since = now
                difference = 255.0 if self.last_capture is None else float(
                    np.mean(np.abs(current - self.last_capture)))
                if now - self.stable_since >= self.stable_seconds:
                    if self.armed and difference >= 6.0 and allow_capture:
                        result["capture"] = True
                        self.last_capture = current.copy()
                        self.armed = False
                    self.state = "captured" if allow_capture or not self.armed else "awaiting_product"
                else:
                    self.state = "settling"
        result["state"] = self.state
        return result
