#!/usr/bin/env python3.8

import evdev
import requests
import json
import os
from pathlib import Path
import subprocess
import datetime

INPUT_LISTENER = False
GROCY_DOMAIN = "https://grocy.i.shamacon.us/api"
GROCY_API_KEY = os.environ["GROCY_API_KEY"]

#GROCY_DEFAULT_LOCATION_ID = 10110
GROCY_DEFAULT_QUANTITY_UNIT = "2"

#LOCATION_RANGE = (10110, 10120) # Grocy UserData Field attaching barcode to stock location

BARCODE_API_URL = "http://10.8.0.55:5555"
#barcode_api_sources = ["off","usda","uhtt"]

dt = datetime.datetime
td = datetime.timedelta

speech = {
    "destination":"seiryuu",
    "speech_app":"espeak-ng"
}

opcodes = {
    "create":10100,
    "add":10101,
    "consume":10102
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
    active_opcode  = "consume"
    scanned_code = ""
    scanned_name = ""
    scanned_product = {}
    locations = []
    DEFAULT_LOCATION = {}
    SELECTED_LOCATION = None

    def speak_result(result):
        subprocess.call(["/home/ywr/speak_result", f'\"{result}\"'])

    def get_product_info(barcode):
        print(f"Getting product info for {barcode}")
        head = {}
        head["GROCY-API-KEY"] = GROCY_API_KEY
        r = requests.get(f'{GROCY_DOMAIN}/stock/products/by-barcode/{barcode}', headers=head)
        r_data = json.loads(r.text)
        InputHandler.scanned_product = r_data["product"]
        print(r_data)

    def prepare_locations():
        head = {}
        head["GROCY-API-KEY"] = GROCY_API_KEY
        r = requests.get(f'{GROCY_DOMAIN}/objects/locations', headers=head)
        r_data = json.loads(r.text)
        InputHandler.locations = []
        for i in r_data:
            if "default" in i["description"].lower() and not InputHandler.SELECTED_LOCATION:
                InputHandler.DEFAULT_LOCATION = {"id":i["id"], "barcode":i["userfields"]["barcode"]}
                print(f"Default location found: {InputHandler.DEFAULT_LOCATION}")
            if i["userfields"]:
                InputHandler.locations.append({"id":i["id"], "barcode":i["userfields"]["barcode"]})
#         print(f'Locations list built: {InputHandler.locations}')

    def process_scan(scanned_code):
        InputHandler.prepare_locations()
        location_codes = []
#        print(list(opcodes.values()))
        for i in InputHandler.locations:
            location_codes.append(i["barcode"])     
        print(location_codes)
        if int(scanned_code) in list(opcodes.values()):
            for k in opcodes.items():
                if k[1] == int(scanned_code):
                    InputHandler.active_opcode = k[0]
                    print(f"OPCODE DETECTED: {InputHandler.active_opcode}.")
                    InputHandler.speak_result(f"OPCODE DETECTED: {InputHandler.active_opcode}.")
        elif scanned_code in location_codes:
            for i in InputHandler.locations:
                if i["barcode"] == scanned_code:
                    InputHandler.SELECTED_LOCATION = i
                    print(f"LOCATION CODE DETECTED. This code will be used with subsequent scans.")
                    InputHandler.speak_result(f"LOCATION CODE DETECTED.")
        else:
            print(f"BARCODE SCANNED: {scanned_code}.")
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
        prev_opcode = ""
        head = {}
        head["content-type"] = "application/json"
        head["GROCY-API-KEY"] = GROCY_API_KEY
        req = {}
        req["amount"] = 1
        req["best_before_date"] = dt.strftime(dt.now() + td(36500))
        print("Adding impossibly distant best-before date...")
        req["transaction_type"] = InputHandler.active_opcode
        d = json.dumps(req)
        r = requests.post(url, data=d, headers=head)
        r_dict = json.loads(r.text)
        print(f"API request: {r.request}")
        print(f"API response: {r.text}")
        if "id" in r_dict.keys():
            InputHandler.get_product_info(InputHandler.scanned_code)
            print(f"Request to {InputHandler.active_opcode} {InputHandler.scanned_product['name']} succeeded.")
            InputHandler.speak_result(f"Request to {InputHandler.active_opcode} {InputHandler.scanned_product['name']} succeeded.")
        elif "error_message" in r_dict.keys():
            if r_dict["error_message"] == f"No product with barcode {InputHandler.scanned_code} found":
                print("Barcode not found in inventory; attempting to lookup product info via barcode.")
                prev_opcode = InputHandler.active_opcode
                InputHandler.active_opcode = "create"
                InputHandler.build_api_url(InputHandler.scanned_code)
                if InputHandler.scanned_name:
                    print("New product created from found info. Reattempting inventory request.")
                    InputHandler.active_opcode = prev_opcode
                    InputHandler.build_inventory_request(url)
                else:
                    InputHandler.active_opcode = prev_opcode
                    print("Barcode not found in any dataset; ignoring.")
            else:
                print(r_dict["error_message"])


    def build_create_request(url):
        r_url = f"{BARCODE_API_URL}/lookup/{InputHandler.scanned_code}"
        print(f"Sending upc request to {r_url}...")
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
            InputHandler.scanned_name = ""
            print(f"No info found on scanned code: {InputHandler.scanned_code}")
        else:
            print("building request to create item...")
            head = {}
            head["content-type"] = "application/json"
            head["GROCY-API-KEY"] = GROCY_API_KEY
            req = {}
            req["name"] = InputHandler.scanned_name
            req["barcode"] = InputHandler.scanned_code
            if InputHandler.SELECTED_LOCATION:
                req["location_id"] = InputHandler.SELECTED_LOCATION["id"]
            else:
                req["location_id"] = InputHandler.DEFAULT_LOCATION["id"]
            print(f'Location ID used: {req["location_id"]}')
            req["qu_id_purchase"] = GROCY_DEFAULT_QUANTITY_UNIT
            req["qu_id_stock"] = GROCY_DEFAULT_QUANTITY_UNIT
            req["qu_factor_purchase_to_stock"] = "1.0"
            d = json.dumps(req)
            print(f"Sending grocy request to {url}")
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
