#!/usr/bin/env python3.8

import evdev
import requests
import json
import os
from pathlib import Path

INPUT_LISTENER = False
GROCY_DOMAIN = "https://grocy.i.shamacon.us/api"
GROCY_API_KEY = os.environ["GROCY_API_KEY"]
GROCY_DEFAULT_LOCATION_ID = "6"
GROCY_DEFAULT_QUANTITY_UNIT = "5"

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
    scanned_name = ""

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
        r_url = f"{BARCODE_API_URL}/lookup/{InputHandler.scanned_code}"
        print(f"Sending request to {r_url}...")
        r = requests.get(r_url)
 #       print(f"response: {r.text}")
        r_dict = json.loads(r.text)
#        print(r_dict)
        found = False
        for i in r_dict["results"]:
            if ("error" not in i["result"]) and (not found):
                found = True
                InputHandler.scanned_name = i["result"]["product_name"]
                print(f'JSON Parsed Name: {i["result"]["product_name"]}')
        if not found:
            print(f"No info found on scanned code: {InputHandler.scanned_code}")
        else:
            print("building request to create item...")
            head = {}
            head["content-type"] = "application/json"
            head["GROCY-API-KEY"] = GROCY_API_KEY
            req = {}
            req["name"] = InputHandler.scanned_name
            req["barcode"] = InputHandler.scanned_code
            req["location_id"] = GROCY_DEFAULT_LOCATION_ID
            req["qu_id_purchase"] = GROCY_DEFAULT_QUANTITY_UNIT
            req["qu_id_stock"] = GROCY_DEFAULT_QUANTITY_UNIT
            req["qu_factor_purchase_to_stock"] = "1.0"
            d = json.dumps(req)
            r = requests.post(url, data=d, headers=head)
            print(f"API request: {r.request}")
            print(f"API response: {r.text}")

    def select_scanner(): # this is ugly and bad and i should feel bad for writing it
        devices = []
        for i in range(20):
            if Path(f"/dev/input/event{str(i)}").exists():
                devices.append(f"/dev/input/event{str(i)}")
#        print(devices)
        for device in devices:
#            print(evdev.InputDevice(device).name)
            faith = 0
            for i in ["bar", "code", "scanner"]:
                if i in evdev.InputDevice(device).name.lower():
                    faith += 1
            if faith > 1:
                print(f"Found scanner: {evdev.InputDevice(device).name}")
                InputHandler.await_scan(device)
                INPUT_LISTENER = device
                break
        print("No scanners found; exiting.")


    def await_scan(dev):
        usb_scanner = evdev.InputDevice(dev)
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

#debug laziness
#InputHandler.scanned_code = "070470290614" # comment this debug laziness
#InputHandler.build_create_request(endpoint_prefixes["create"]) # comment this debug laziness

#uncomment for normalcy
InputHandler.select_scanner()
