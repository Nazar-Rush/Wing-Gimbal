These are notes and references to help me develop this code.

# Video

Video is streamed through the av port on the rpi to a fpv tansmitter.

## Setup

In boot/config.txt (edit sd card, not over ssh)

- enable_tvout=1
- dtoverlay=vc4-kms-v3d,composite

In boot/cmdline.txt

- add to the end of line: vc4.tv_norm=NTSC
