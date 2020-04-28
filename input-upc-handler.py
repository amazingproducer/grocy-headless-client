#!/usr/bin/env python3.8

import evdev

INPUT_LISTENER = '/dev/input/event11'
BARCODE_CREATE = 10100
BARCODE_INCREMENT = 10101
BARCODE_DECREMENT = 10102

opcodes = {
    "BARCODE_CREATE":10100,
    "BARCODE_INCREMENT":10101,
    "BARCODE_DECREMENT":10102
    }
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
                scanned_code = int("".join(scan_buffer))
                if scanned_code in list(opcodes.values()):
                    for k in opcodes.items():
                        if k[1] == scanned_code:
                            print(f"OPCODE DETECTED: {k[0]}")
                else:
                    print(f"BARCODE SCANNED: {scanned_code}")
                scan_buffer = []

