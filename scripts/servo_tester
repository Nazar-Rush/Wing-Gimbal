#
# This script is a simple servo tester for Raspberry Pi using the pigpio library.
# It allows you to set the angle of a servo connected to a specified GPIO pin.
# https://www.raspberrypi.com/documentation/computers/raspberry-pi.html
# https://www.raspberrypi.com/documentation/computers/images/GPIO-Pinout-Diagram-2.png?hash=df7d7847c57a1ca6d5b2617695de6d46
# pin is gpio number not physical pin number, so for example GPIO18 is pin 12 on the header.

# sudo apt update
# sudo apt install pigpio python3-pigpio
# sudo systemctl enable --now pigpiod
import pigpio
import sys
import time

MIN_PW = 500
MAX_PW = 2500


def angle_to_pulsewidth(angle):
    angle = max(0, min(180, angle))
    return int(MIN_PW + (angle / 180.0) * (MAX_PW - MIN_PW))


if len(sys.argv) != 3:
    print("Usage: python servo_set.py <gpio pin (18)> <angle>")
    sys.exit(1)

try:
    pin = int(sys.argv[1])
except ValueError:
    print("Pin must be a integer.")
    sys.exit(1)

try:
    angle = float(sys.argv[2])
except ValueError:
    print("Angle must be a number.")
    sys.exit(1)

if not (0 <= angle <= 180):
    print("Angle must be between 0 and 180.")
    sys.exit(1)

pi = pigpio.pi()
if not pi.connected:
    print("Could not connect to pigpio daemon.")
    sys.exit(1)

try:
    pw = angle_to_pulsewidth(angle)
    pi.set_servo_pulsewidth(pin, pw)
    print(f"Set servo to {angle} deg ({pw} us)")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    pi.set_servo_pulsewidth(pin, 0)
    pi.stop()
