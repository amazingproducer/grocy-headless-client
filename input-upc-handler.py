#!/usr/bin/env python3.8

import evdev
import requests
import json
import os
from pathlib import Path
import subprocess
import datetime
import simpleaudio as sa

INPUT_LISTENER = False
GROCY_DOMAIN = "https://grocy.i.shamacon.us/api"
GROCY_API_KEY = os.environ["GROCY_API_KEY"]

# TODO move most of these messy declarations to configuration files or something


#GROCY_DEFAULT_LOCATION_ID = 10110
GROCY_DEFAULT_QUANTITY_UNIT = "2"

#LOCATION_RANGE = (10110, 10120) # Grocy UserData Field attaching barcode to stock location

BARCODE_API_URL = "http://10.8.0.55:5555"
#barcode_api_sources = ["off","usda","uhtt"]

dt = datetime.datetime
td = datetime.timedelta

do_speak = False # Enables tone based feedback. Set to True to enable text-to-speech based feedback.
remote_speaker = True # Set to false for onboard playback

speaker = {
    "destination":"seiryuu",
    "speaker_app":"aplay"
}

speech = {
    "destination":"seiryuu",
    "speech_app":"espeak-ng"
}

feedback_tones = {
    "add":"./wav/add.wav",
    "consume":"./wav/consume.wav",
    "spoiled":"./wav/spoiled.wav",
    "create":"./wav/create.wav",
    "transfer":"./wav/transfer.wav",
    "error_no_item_remaining":"./wav/error_no.item.remaining.wav",
    "error_item_exists":"./wav/error_item.exists.wav",
    "timer_location_reset":"./wav/timer_location.reset.wav",
    "timer_opcode_reset":"./wav/timer_opcode.reset.wav",
    "timer_transfer_reset":"./wav/timer_transfer.reset.wav"
}

## TODO: add headless setup dialog for mapping opcode values to custom barcodes
# opcodes = {
#     "create":"10100",
#     "add":"10101",
#     "consume":"10102"
#     }
# Let's remove support for explicitly using the create opcode
opcodes = {
    "add":"10101",
    "consume":"10102"
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

## TODO: add headless setup dialog for mapping stock locations to custom barcodes

def speak_result(result):
    """Use TTS for audible feedback."""
    subprocess.call(["/home/ywr/speak_result", f'\"{result}\"']) #Abstract this call out or something

def audible_playback(status):
    """Use wav files for audible feedback."""
    if remote_speaker:
        subprocess.call(["/home/ywr/remote_speaker", f'\"{status}\"']) #Abstract this call out or something
    else:
        audible_object = sa.WaveObject.from_wave_file(feedback_tones[status])
        playback_object = audible_object.play()
        playback_object.wait_done()


class InputHandler:
    def __init__(self):
        active_opcode  = "consume"
        scanned_code = ""
        scanned_name = ""
        storage_locations = []
        storage_location_codes = []
        DEFAULT_LOCATION = {}
        SELECTED_LOCATION = {}
        self.prepare_storage_locations()

    def get_product_info(barcode):
        """Get info from grocy API about a scanned barcode."""
        print(f"Getting product info for {barcode}")
        head = {}
        head["GROCY-API-KEY"] = GROCY_API_KEY
        r = requests.get(f'{GROCY_DOMAIN}/stock/products/by-barcode/{barcode}', headers=head)
        r_data = json.loads(r.text)
        if r.status_code == "404":
            return None
        elif r.status_code == "200":
            return r_data["product"]["name"]

    def get_barcode_info(barcode):
        """Get info from barcode API abot a scanned barcode."""
        r_url = f"{BARCODE_API_URL}/grocy/{barcode}"
        r = requests.get(r_url)
        r_data = json.loads(r.text)
        if r.status_code == "404":
            return None
        elif r.status_code == "200":
            return r_data["product_name"]

    def prepare_storage_locations(self):
        """Attempt to map location barcodes to locations known by grocy."""
        InputHandler.storage_locations = [] # Do I need to store the whole dictionary? Will I ever need to use more than the codes?
        InputHandler.storage_location_codes = []
        head = {}
        head["GROCY-API-KEY"] = GROCY_API_KEY
        r = requests.get(f'{GROCY_DOMAIN}/objects/locations', headers=head)
        r_data = json.loads(r.text)
        for i in r_data:
            # Ignore location if barcode userfield is not present
            if not i["userfields"]["barcode"]:
                print(f"No barcode set for storage location: {i["name"]}")
            elif i["description"]:
                # Use a default location if one is declared within grocy
                if "default" in i["description"].lower():
                    # Jump to conclusions and prepend this entry to storage locations and set the default location
                    InputHandler.storage_locations = [{"id":i["id"], "barcode":i["userfields"]["barcode"]}] + InputHandler.storage_locations
                    InputHandler.DEFAULT_LOCATION = InputHandler.storage_location[0]
                else:
                    InputHandler.storage_locations.append({"id":i["id"], "barcode":i["userfields"]["barcode"]})
        for i in InputHandler.storage_locations: # This doesn't save us much time to prebuild
            InputHandler.storage_location_codes.append(i["barcode"])

    def process_scan(scanned_code):
        """Determine if the scanned code type and determine its corresponding name."""
        if scanned_code in list(opcodes.values()):
            for k in opcodes.items():
                if k[1] == scanned_code:
                    InputHandler.active_opcode = k[0]
                    print(f"OPCODE DETECTED: {InputHandler.active_opcode}.")
                    if do_speak:
                        speak_result(f"OPCODE DETECTED: {InputHandler.active_opcode}.")
                    else:
                        audible_playback(InputHandler.active_opcode)
        elif scanned_code in InputHandler.storage_location_codes:
            for i in InputHandler.storage_locations:
                if i["barcode"] == scanned_code:
                    InputHandler.SELECTED_LOCATION = i
                    print(f"LOCATION CODE DETECTED. This code will be used with subsequent scans.")
                    if do_speak:
                        speak_result(f"LOCATION CODE DETECTED.")
                    else:
                        audible_playback("transfer") #TODO add a location code sound?
        elif len(scanned_code) >= 12:
            print(f"PRODUCT CODE SCANNED: {scanned_code}.")
            # Search for the code vide grocy api
            InputHandler.scanned_name = get_product_info(scanned_code)
            if not InputHandler.scanned_name:
                # Search for the code via barcode api
                InputHandler.scanned_name = get_barcode_info(scanned_code)
            if not InputHandler.scanned_name:
                InputHandler.scanned_name = "Unknown Product"
                # Create new stock item via grocy api
                create_inventory_item()
            # Call the grocy api to execute the proper command with this new information
            modify_inventory_stock()
#            InputHandler.build_api_url(scanned_code)

# TODO get rid of the create opcode and get rid of this
    def build_api_url(scanned_code): # This function only exists to support a near-useless feature -- scanning a new item into inventory with no intention of adding any stock.
        active_opcode = InputHandler.active_opcode
        if active_opcode != "create":
            print(f"API URL: {endpoint_prefixes[active_opcode]}{scanned_code}{endpoint_suffixes[active_opcode]}")
            InputHandler.build_inventory_request(f"{endpoint_prefixes[active_opcode]}{scanned_code}{endpoint_suffixes[active_opcode]}")
        else:
            print(f"API URL: {endpoint_prefixes[active_opcode]}")
            request_url = f"{endpoint_prefixes[active_opcode]}"
            print("JSON request data required.")
            InputHandler.build_create_request(endpoint_prefixes[active_opcode])

    def modify_inventory_stock():
        head = {}
        head["content-type"] = "application/json"
        head["GROCY-API-KEY"] = GROCY_API_KEY
        req = {}
        req["amount"] = 1
        req["best_before_date"] = (dt.now() + td(36500)).strftime("%Y-%m-%d") # Add impossibly-distant expiration date for future work
        req["transaction_type"] = InputHandler.active_opcode
        r = requests.post(url, data=json.dumps(req), headers=head)
        if r.status_code == "200":
            if do_speak:
                speak_result(f"Request to {InputHandler.active_opcode} {InputHandler.scanned_name} succeeded.")
            else:
                audible_playback(InputHandler.active_opcode)
        elif "amount" in json.loads(r.text)["error_message"].lower():
            if do_speak:
                speak_result(f"All stock of {InputHandler.scanned_name} has been consumed.")
            else:
                audible_playback("error_no_item_remaining")

    def create_inventory_item():
        url = endpoint_prefixes["create"]
        head = {}
        head["content-type"] = "application/json"
        head["GROCY-API-KEY"] = GROCY_API_KEY
        req = []
        req["name"] = InputHandler.scanned_name
        req["barcode"] = InputHandler.scanned_code
        if InputHandler.SELECTED_LOCATION:
            req["location_id"] = InputHandler.SELECTED_LOCATION["id"]
        else:
            req["location_id"] = InputHandler.DEFAULT_LOCATION["id"]
        req["qu_id_purchase"] = GROCY_DEFAULT_QUANTITY_UNIT
        req["qu_id_stock"] = GROCY_DEFAULT_QUANTITY_UNIT
        req["qu_factor_purchase_to_stock"] = "1.0"
        r = requests.post(url, data=json.dumps(req), headers=head)
        if r.status_code == "200":
            audible_playback("create")
        else:
            audible_playback("error_item_exists") # Maybe this result is not necessary

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
                        scan_buffer = []
                        if scanned_code.isnumeric():
                            InputHandler.scanned_code = scanned_code
                            InputHandler.process_scan(scanned_code)
                        else:
                            print("Non-numeric barcode scanned. This is not a UPC.")

#debug laziness
#ih.scanned_code = "070470290614" # comment this debug laziness
#ih.build_create_request(endpoint_prefixes["create"]) # comment this debug laziness

#uncomment for normalcy
ih = InputHandler()
ih.select_scanner()
