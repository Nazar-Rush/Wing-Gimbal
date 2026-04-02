#!/usr/bin/env python3
"""
contrast_autofocus_test.py

HQ Pi Camera + external focus servo + Picamera2 + pigpio test script.

What it does:
- Starts the camera with Picamera2
- Warms up auto exposure / auto white balance
- Optionally locks exposure and white balance
- Runs a contrast-based autofocus sweep using a Laplacian sharpness metric
- Saves the best-focused frame
- If a desktop display is available, opens a live preview window with controls

Keys in preview window:
    a  -> run autofocus sweep
    j  -> move focus servo a small step toward SERVO_MIN_US
    k  -> move focus servo a small step toward SERVO_MAX_US
    s  -> save current frame
    q  -> quit
"""

import os
import sys
import time
import math
import argparse
from statistics import fmean

import cv2  # pip install opencv-python
import numpy as np
import pigpio
from picamera2 import Picamera2


# -------------------------
# User-tunable defaults
# -------------------------
SERVO_GPIO = 18  # Change to your servo GPIO
SERVO_MIN_US = 500  # Tune carefully for your lens mechanism
SERVO_MAX_US = 1000  # Tune carefully for your lens mechanism
SERVO_START_US = 750  # Safe-ish starting point
SERVO_SETTLE_S = 0.18  # Time for the servo/focus ring to settle after a move

FRAME_WIDTH = 2560
FRAME_HEIGHT = 1600
ROI_FRACTION = 0.35  # Central ROI size as fraction of frame size

COARSE_STEP_US = 40
FINE_STEP_US = 8
SETTLE_FRAMES = 2  # Throw away a few frames after motion
SAMPLE_FRAMES = 3  # Average focus score across a few frames
SAVE_PATH = "../tests/images/autofocus_best.jpg"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def build_center_roi(width, height, fraction):
    rw = max(32, int(width * fraction))
    rh = max(32, int(height * fraction))
    x = (width - rw) // 2
    y = (height - rh) // 2
    return (x, y, rw, rh)


def sharpness_score(rgb_frame, roi):
    """
    Contrast-based focus metric: variance of the Laplacian in the ROI.
    Higher is sharper.
    """
    x, y, w, h = roi
    gray = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2GRAY)
    patch = gray[y : y + h, x : x + w]

    # Small blur helps suppress sensor noise before the Laplacian.
    patch = cv2.GaussianBlur(patch, (3, 3), 0)

    return float(cv2.Laplacian(patch, cv2.CV_64F).var())


class FocusServo:
    def __init__(self, pi, gpio, min_us, max_us, start_us, settle_s):
        self.pi = pi
        self.gpio = gpio
        self.min_us = int(min_us)
        self.max_us = int(max_us)
        self.current_us = int(clamp(start_us, min_us, max_us))
        self.settle_s = float(settle_s)

        self.pi.set_mode(self.gpio, pigpio.OUTPUT)
        self.set_us(self.current_us)

    def set_us(self, pulse_us):
        pulse_us = int(clamp(pulse_us, self.min_us, self.max_us))
        self.pi.set_servo_pulsewidth(self.gpio, pulse_us)
        self.current_us = pulse_us
        time.sleep(self.settle_s)
        return self.current_us

    def nudge(self, delta_us):
        return self.set_us(self.current_us + delta_us)

    def off(self):
        self.pi.set_servo_pulsewidth(self.gpio, 0)


def grab_fresh_frame(picam2, stream="main", settle_frames=2):
    frame = None
    for _ in range(settle_frames):
        frame = picam2.capture_array(stream)
    return frame


def sample_focus_at_position(
    picam2, servo, pulse_us, roi, settle_frames=2, sample_frames=3
):
    """
    Move servo, let things settle, discard a few frames, then average a few
    sharpness measurements.
    """
    servo.set_us(pulse_us)

    # Throw away a couple of frames after motion so we score a fresh image.
    frame = grab_fresh_frame(picam2, settle_frames=settle_frames)

    scores = []
    for _ in range(sample_frames):
        frame = picam2.capture_array("main")
        scores.append(sharpness_score(frame, roi))

    return float(fmean(scores)), frame


def lock_exposure_and_wb(picam2):
    """
    Let AE/AWB settle, then lock the current values so brightness and color
    do not drift during the focus sweep.
    """
    time.sleep(1.5)
    md = picam2.capture_metadata()

    try:
        with picam2.controls as controls:
            controls.AeEnable = False
            controls.ExposureTime = int(md["ExposureTime"])
            controls.AnalogueGain = float(md["AnalogueGain"])

            # Setting ColourGains also disables AWB.
            if "ColourGains" in md:
                controls.ColourGains = tuple(md["ColourGains"])

            # Best effort if the control exists.
            try:
                controls.AwbEnable = False
            except Exception:
                pass

        print(
            f"Locked camera: ExposureTime={md.get('ExposureTime')} "
            f"AnalogueGain={md.get('AnalogueGain')} "
            f"ColourGains={md.get('ColourGains')}"
        )
    except Exception as exc:
        print(f"Warning: could not lock AE/AWB cleanly: {exc}")

    return md


def autofocus_sweep(
    picam2,
    servo,
    roi,
    coarse_step_us=40,
    fine_step_us=8,
    settle_frames=2,
    sample_frames=3,
):
    """
    Two-stage autofocus:
      1) coarse sweep across the full servo range
      2) fine sweep around the best coarse position
    """
    results = []

    # Stage 1: coarse sweep
    coarse_positions = list(range(servo.min_us, servo.max_us + 1, coarse_step_us))
    if coarse_positions[-1] != servo.max_us:
        coarse_positions.append(servo.max_us)

    print("Starting coarse autofocus sweep...")
    best_pos = servo.current_us
    best_score = -1.0
    best_frame = None

    for pos in coarse_positions:
        score, frame = sample_focus_at_position(
            picam2,
            servo,
            pos,
            roi,
            settle_frames=settle_frames,
            sample_frames=sample_frames,
        )
        results.append((pos, score))
        print(f"  coarse pos={pos:4d} us  score={score:10.2f}")

        if score > best_score:
            best_score = score
            best_pos = pos
            best_frame = frame

    # Stage 2: fine sweep around the best coarse result
    fine_min = clamp(best_pos - coarse_step_us, servo.min_us, servo.max_us)
    fine_max = clamp(best_pos + coarse_step_us, servo.min_us, servo.max_us)

    fine_positions = list(range(fine_min, fine_max + 1, fine_step_us))
    if fine_positions[-1] != fine_max:
        fine_positions.append(fine_max)

    print("Starting fine autofocus sweep...")
    for pos in fine_positions:
        score, frame = sample_focus_at_position(
            picam2,
            servo,
            pos,
            roi,
            settle_frames=settle_frames,
            sample_frames=sample_frames,
        )
        results.append((pos, score))
        print(f"  fine   pos={pos:4d} us  score={score:10.2f}")

        if score > best_score:
            best_score = score
            best_pos = pos
            best_frame = frame

    # Backlash compensation: approach final position from one direction.
    approach_us = clamp(best_pos - fine_step_us * 3, servo.min_us, servo.max_us)
    servo.set_us(approach_us)
    servo.set_us(best_pos)

    print(f"Autofocus complete: best_pos={best_pos} us  best_score={best_score:.2f}")
    return best_pos, best_score, best_frame, results


def draw_overlay(bgr_frame, roi, pulse_us, score, locked):
    x, y, w, h = roi
    out = bgr_frame.copy()
    cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 2)

    lines = [
        f"servo: {pulse_us} us",
        f"sharpness: {score:.1f}",
        f"AE/AWB locked: {'yes' if locked else 'no'}",
        "keys: a=autofocus  j/k=manual  s=save  q=quit",
    ]

    y0 = 28
    for i, line in enumerate(lines):
        cv2.putText(
            out,
            line,
            (12, y0 + i * 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return out


def save_rgb_as_jpg(frame, path):
    cv2.imwrite(path, frame)


def main():
    parser = argparse.ArgumentParser(description="HQ camera contrast autofocus test")
    parser.add_argument("--gpio", type=int, default=SERVO_GPIO, help="Servo GPIO")
    parser.add_argument(
        "--min-us", type=int, default=SERVO_MIN_US, help="Servo min pulse width"
    )
    parser.add_argument(
        "--max-us", type=int, default=SERVO_MAX_US, help="Servo max pulse width"
    )
    parser.add_argument(
        "--start-us", type=int, default=SERVO_START_US, help="Servo start pulse width"
    )
    parser.add_argument("--width", type=int, default=FRAME_WIDTH, help="Preview width")
    parser.add_argument(
        "--height", type=int, default=FRAME_HEIGHT, help="Preview height"
    )
    parser.add_argument(
        "--roi-frac", type=float, default=ROI_FRACTION, help="Central ROI fraction"
    )
    parser.add_argument(
        "--coarse-step", type=int, default=COARSE_STEP_US, help="Coarse step in us"
    )
    parser.add_argument(
        "--fine-step", type=int, default=FINE_STEP_US, help="Fine step in us"
    )
    parser.add_argument(
        "--settle-s", type=float, default=SERVO_SETTLE_S, help="Servo settle time"
    )
    parser.add_argument(
        "--settle-frames",
        type=int,
        default=SETTLE_FRAMES,
        help="Frames to discard after motion",
    )
    parser.add_argument(
        "--sample-frames",
        type=int,
        default=SAMPLE_FRAMES,
        help="Frames to average per focus point",
    )
    parser.add_argument("--save", type=str, default=SAVE_PATH, help="Output image path")
    parser.add_argument(
        "--no-lock", action="store_true", help="Do not lock AE/AWB after warm-up"
    )
    parser.add_argument(
        "--no-preview", action="store_true", help="Skip OpenCV preview window"
    )
    args = parser.parse_args()

    pi = pigpio.pi()
    if not pi.connected:
        print("Error: could not connect to pigpio daemon. Is pigpiod running?")
        sys.exit(1)

    servo = None
    picam2 = None

    try:
        servo = FocusServo(
            pi=pi,
            gpio=args.gpio,
            min_us=args.min_us,
            max_us=args.max_us,
            start_us=args.start_us,
            settle_s=args.settle_s,
        )

        picam2 = Picamera2()
        config = picam2.create_preview_configuration(
            main={"size": (args.width, args.height), "format": "RGB888"}
        )
        picam2.configure(config)
        picam2.start()

        # Warm up camera a bit.
        time.sleep(2.0)

        locked = not args.no_lock
        if locked:
            lock_exposure_and_wb(picam2)

        roi = build_center_roi(args.width, args.height, args.roi_frac)

        # Initial autofocus pass
        best_pos, best_score, best_frame, _ = autofocus_sweep(
            picam2,
            servo,
            roi,
            coarse_step_us=args.coarse_step,
            fine_step_us=args.fine_step,
            settle_frames=args.settle_frames,
            sample_frames=args.sample_frames,
        )

        save_rgb_as_jpg(best_frame, args.save)
        print(f"Saved best frame to: {args.save}")

        gui_allowed = (not args.no_preview) and bool(os.environ.get("DISPLAY"))

        if not gui_allowed:
            print(
                "No preview window requested or DISPLAY not set. Exiting after autofocus."
            )
            return

        window_name = "HQ Camera Servo Autofocus Test"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        last_score = best_score

        while True:
            rgb = picam2.capture_array("main")
            last_score = sharpness_score(rgb, roi)

            display = draw_overlay(
                rgb,
                roi=roi,
                pulse_us=servo.current_us,
                score=last_score,
                locked=locked,
            )

            cv2.imshow(window_name, display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            elif key == ord("a"):
                best_pos, best_score, best_frame, _ = autofocus_sweep(
                    picam2,
                    servo,
                    roi,
                    coarse_step_us=args.coarse_step,
                    fine_step_us=args.fine_step,
                    settle_frames=args.settle_frames,
                    sample_frames=args.sample_frames,
                )
                save_rgb_as_jpg(best_frame, args.save)
                print(f"Saved best frame to: {args.save}")
            elif key == ord("j"):
                servo.nudge(-args.fine_step)
            elif key == ord("k"):
                servo.nudge(+args.fine_step)
            elif key == ord("s"):
                save_rgb_as_jpg(rgb, args.save)
                print(f"Saved current frame to: {args.save}")

        cv2.destroyAllWindows()

    finally:
        try:
            if picam2 is not None:
                picam2.stop()
        except Exception:
            pass

        try:
            if servo is not None:
                servo.off()
        except Exception:
            pass

        try:
            pi.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
