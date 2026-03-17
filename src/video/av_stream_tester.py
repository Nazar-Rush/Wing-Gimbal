# If picamera2 is missing, install it with:
# sudo apt update
# sudo apt install -y python3-picamera2


import time
from picamera2 import Picamera2, Preview

picam2 = Picamera2()

# Full-screen-ish DRM preview on the active display
picam2.start_preview(Preview.DRM, x=0, y=0, width=720, height=480)

preview_config = picam2.create_preview_configuration({"size": (640, 480)})
picam2.configure(preview_config)

picam2.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    picam2.stop()
