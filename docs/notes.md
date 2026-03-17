These are notes and references to help me develop this code.

# Video

Video is streamed through the av port on the rpi to a fpv tansmitter.

## Setup

In boot/config.txt (edit sd card, not over ssh), add to the bottom of the file (and disable any duplicates):

- camera_auto_detect=0
- dtoverlay=imx477
- dtoverlay=vc4-kms-v3d,composite
- enable_tvout=1

In boot/cmdline.txt

- add to the end of line: vc4.tv_norm=NTSC

## Useful Commands

rpicam-hello --list-cameras -> lists cameras detected
