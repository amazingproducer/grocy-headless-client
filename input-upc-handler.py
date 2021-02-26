#!/usr/bin/env python3.8

import evdev
import requests
import json
import os
from pathlib import Path
import subprocess
import datetime
import simpleaudio as sa

dt = datetime.datetime
td = datetime.timedelta

# TODO move most of these messy declarations to configuration files or something

INPUT_LISTENER = False
GROCY_DOMAIN = "https://grocy.i.shamacon.us/api"
GROCY_API_KEY = os.environ["GROCY_API_KEY"]
GROCY_DEFAULT_QUANTITY_UNIT = "1"
GROCY_DEFAULT_QUANTITY_FACTOR = "1.0"
GROCY_DEFAULT_INVENTORY_ACTION = "consume" # Used to set the default opcode
CODE_SELECTION_LIFETIME = td(minutes=10)
BARCODE_API_URL = "http://10.8.0.55:5555"
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
#    def __init__():
    active_opcode = GROCY_DEFAULT_INVENTORY_ACTION
    scanned_code = ""
    scanned_name = ""
    storage_locations = []
    storage_location_codes = []
    DEFAULT_LOCATION = {}
    SELECTED_LOCATION = {}
    last_scan_time = dt.now()

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

    def prepare_storage_locations():
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
                print(f"No barcode set for storage location: {i['name']}")
            elif i["description"]:
                # Use a default location if one is declared within grocy
                if "default" in i["description"].lower():
                    # Jump to conclusions and prepend this entry to storage locations and set the default location
                    InputHandler.storage_locations = [{"id":i["id"], "barcode":i["userfields"]["barcode"]}] + InputHandler.storage_locations
                    InputHandler.DEFAULT_LOCATION = InputHandler.storage_locations[0]
                else:
                    InputHandler.storage_locations.append({"id":i["id"], "barcode":i["userfields"]["barcode"]})
        for i in InputHandler.storage_locations: # This doesn't save us much time to prebuild
            InputHandler.storage_location_codes.append(i["barcode"])

    def process_scan():
        """Determine if the scanned code type and determine its corresponding name."""
        # Check timestamp of previous scan and reset opcodes and locations if required
        scanned_code = InputHandler.scanned_code
        if dt.now() - InputHandler.last_scan_time > CODE_SELECTION_LIFETIME:
            InputHandler.DEFAULT_LOCATION = InputHandler.storage_location_codes[0]
            InputHandler.active_opcode = GROCY_DEFAULT_INVENTORY_ACTION
        InputHandler.last_scan_time = dt.now()
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
            InputHandler.scanned_name = InputHandler.get_product_info(scanned_code)
            if not InputHandler.scanned_name:
                InputHandler.scanned_name = InputHandler.get_barcode_info(scanned_code)
            if not InputHandler.scanned_name:
                InputHandler.scanned_name = "Unknown Product"
                InputHandler.create_inventory_item()
            InputHandler.modify_inventory_stock()
        else:
            if do_speak:
                speak_result("Invalid code scanned.")
            else:
                audible_playback("error_item_exists") # TODO find more soundbytes for error types

    def modify_inventory_stock():
        """Add or Consume grocy stock for the scanned product.""" 
        url = endpoint_prefixes[InputHandler.active_opcode]
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
        """Create a new grocy inventory item for the scanned product."""
        url = endpoint_prefixes["create"]
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
        req["qu_id_purchase"] = GROCY_DEFAULT_QUANTITY_UNIT
        req["qu_id_stock"] = GROCY_DEFAULT_QUANTITY_UNIT
        req["qu_factor_purchase_to_stock"] = GROCY_DEFAULT_QUANTITY_FACTOR
        r = requests.post(url, data=json.dumps(req), headers=head)
        if r.status_code == "200":
            if do_speak:
                speak_result("Creating new entry.")
            else:
                audible_playback("create")
        else:
            audible_playback("error_item_exists") # Maybe this result is not necessary

    def select_scanner():
        InputHandler.prepare_storage_locations()
        devices = []
        for i in range(20):
            if Path(f"/dev/input/event{str(i)}").exists():
                devices.append(f"/dev/input/event{str(i)}")
        for device in devices:
            faith = 0
            for i in ["bar", "code", "scanner"]:
                if i in evdev.InputDevice(device).name.lower():
                    faith += 1
            if faith > 1:
                print(f"Found scanner: {evdev.InputDevice(device).name}")
                InputHandler.await_scan(device)
                INPUT_LISTENER = device
                break

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
                            InputHandler.process_scan()
                        else:
                            print("Non-numeric barcode scanned. This is not a UPC.")
                            if do_speak:
                                speak_result("Invalid code scanned.")
                            else:
                                audible_playback("error_no_item_remaining") # TODO srsly get some more audio clips for error types

InputHandler.select_scanner()
