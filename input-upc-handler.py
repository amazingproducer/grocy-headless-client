#!/usr/bin/env python3.8

import evdev
import requests
import json
import os

INPUT_LISTENER = False
GROCY_DOMAIN = "https://grocy.i.shamacon.us/api"
GROCY_API_KEY = os.environ["GROCY_API_KEY"]
BARCODE_CREATE = "10100"
BARCODE_INCREMENT = "10101"
BARCODE_DECREMENT = "10102"
BARCODE_API_URL = "http://10.8.0.55:5555"

barcode_api_sources = ["off","usda","uhtt"]

opcodes = {
    "create":BARCODE_CREATE,
    "add":BARCODE_INCREMENT,
    "consume":BARCODE_DECREMENT
    }

endpoint_prefixes = {
    "create":f"{GROCY_DOMAIN}/objects/products",
    "add":f"{GROCY_DOMAIN}/stock/products/by-barcode/",
    "consume":f"{GROCY_DOMAIN}/stock/products/by-barcode/"
}

endpoint_suffixes = {
    "create":None,
    "add":"/add",
    "consume":"/consume"
}

class InputHandler():
    active_opcode  = "add"
    scanned_code = ""

    def process_scan(scanned_code):
        if scanned_code in list(opcodes.values()):
            for k in opcodes.items():
                if k[1] == scanned_code:
                    InputHandler.active_opcode = k[0]
                    print(f"OPCODE DETECTED: {InputHandler.active_opcode}")
        else:
            print(f"BARCODE SCANNED: {scanned_code}")
            InputHandler.build_api_url(scanned_code)

    def build_api_url(scanned_code):
        active_opcode = InputHandler.active_opcode
        if active_opcode != "create":
            print(f"API URL: {endpoint_prefixes[active_opcode]}{scanned_code}{endpoint_suffixes[active_opcode]}")
            InputHandler.build_inventory_request(f"{endpoint_prefixes[active_opcode]}{scanned_code}{endpoint_suffixes[active_opcode]}")
        else:
            print(f"API URL: {endpoint_prefixes[active_opcode]}")
            request_url = f"{endpoint_prefixes[active_opcode]}"
        print("JSON request data required.")
        InputHandler.build_create_request(endpoint_prefixes[active_opcode])

    def build_inventory_request(url):
        head = {}
        head["content-type"] = "application/json"
        head["GROCY-API-KEY"] = GROCY_API_KEY
        req = {}
        req["amount"] = 1
        req["transaction_type"] = InputHandler.active_opcode
        d = json.dumps(req)
        r = requests.post(url, data=d, headers=head)
        print(f"API request: {r.request}")
        print(f"API response: {r.text}")

    def build_create_request(url):
        print(f"We'd be inputting to {url} if we had product data to add...")
        for i in barcode_api_sources:
            r_url = f"{BARCODE_API_URL}/{i}/{InputHandler.scanned_code}"
            print(f"Sending request to {r_url}...")
            r = requests.get(r_url)
            print(f"{i} response: {r.text}")
        # print("building request to create item...")
        # head = {}
        # head["content-type"] = "application/json"
        # head["GROCY-API-KEY"] = GROCY_API_KEY
        # req = {}
        # req["name"] = "untitled"
        # req["barcode"] = InputHandler.scanned_code
        # req["location_id"] = 0
        # req["qu_id_purchase"] = 0
        # req["qu_id_stock"] = 0
        # req["qu_factor_purchase_to_stock"] = "1.0"
        # d = json.dumps(req)
        # r = requests.post(url, data=d, headers=head)
        # print(f"API request: {r.request}")
        # print(f"API response: {r.text}")



    def await_scan():
        usb_scanner = evdev.InputDevice(INPUT_LISTENER)
        usb_scanner.grab()
        scan_buffer = []
        scanned_code = InputHandler.scanned_code
        for event in usb_scanner.read_loop():
            if event.type == evdev.ecodes.EV_KEY:
                i = evdev.categorize(event)
                if i.keystate == i.key_down:
                    k = i.keycode.split('_')[1]
                    if k != "ENTER":
                        scan_buffer.append(k)
                    else:
                        scanned_code = "".join(scan_buffer)
                        InputHandler.scanned_code = scanned_code
                        scan_buffer = []
                        InputHandler.process_scan(scanned_code)

    def select_scanner(): # this is ugly and bad and i should feel bad for writing it
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        for device in devices:
            faith = 0
            for i in ["bar", "code", "scanner"]:
                if i in device.name.lower():
                    faith += 1
            if faith > 1:
                INPUT_LISTENER = device.path
                break

InputHandler.select_scanner()
InputHandler.await_scan()