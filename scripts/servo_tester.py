#
# This script is a simple servo tester for Raspberry Pi using the gpiozero library.
# It allows you to set the angle of a servo connected to a specified GPIO pin.
# https://www.raspberrypi.com/documentation/computers/raspberry-pi.html
# https://www.raspberrypi.com/documentation/computers/images/GPIO-Pinout-Diagram-2.png?hash=df7d7847c57a1ca6d5b2617695de6d46
# pin is gpio number not physical pin number, so for example GPIO18 is pin 12 on the header.

# sudo apt update
# sudo apt install python3-gpiozero
import sys
from gpiozero import AngularServo
import time

# MIN_PW = 500
# MAX_PW = 2500
MIN_ANGLE = 0
MAX_ANGLE = 180


# def angle_to_pulsewidth(angle):
#     angle = max(0, min(180, angle))
#     return int(MIN_PW + (angle / 180.0) * (MAX_PW - MIN_PW))


# check command line argument count
if len(sys.argv) != 3:
    print("Usage: python servo_set.py <gpio pin (18)> <angle>")
    sys.exit(1)

# parse gpio pin from command line argument
try:
    pin = int(sys.argv[1])
except ValueError:
    print("Pin must be a integer.")
    sys.exit(1)

# parse angle from command line argument
try:
    angle = float(sys.argv[2])
except ValueError:
    print("Angle must be a number.")
    sys.exit(1)

# validate angle range
if not (MIN_ANGLE <= angle <= MAX_ANGLE):
    print(f"Angle must be between {MIN_ANGLE} and {MAX_ANGLE}.")
    sys.exit(1)

# set angle
servo = AngularServo(pin, min_angle=MIN_ANGLE, max_angle=MAX_ANGLE)
try:
    servo.angle = angle
    print(f"Set servo to {angle} deg")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    servo.detach()


# pi = pigpio.pi()
# if not pi.connected:
#     print("Could not connect to pigpio daemon.")
#     sys.exit(1)

# try:
#     pw = angle_to_pulsewidth(angle)
#     pi.set_servo_pulsewidth(pin, pw)
#     print(f"Set servo to {angle} deg ({pw} us)")
#     while True:
#         time.sleep(1)
# except KeyboardInterrupt:
#     pass
# finally:
#     pi.set_servo_pulsewidth(pin, 0)
#     pi.stop()
