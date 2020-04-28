#!/usr/bin/env python3.8

import evdev

INPUT_LISTENER = '/dev/input/event11'

usb_scanner = evdev.InputDevice(INPUT_LISTENER)
usb_scanner.grab()

scan_buffer = []

for event in usb_scanner.read_loop():
    if event.type == evdev.ecodes.EV_KEY:
        i = evdev.categorize(event)
        if i.keystate == i.key_down:
            k = i.keycode.split('_')[1]
            if k != "ENTER":
                scan_buffer.append(k)
            else:
                scanned_code = "".join(scan_buffer)
                print(scanned_code)
                scan_buffer = []

