#!/usr/bin/env python3

import evdev
import requests
import json
import os
from pathlib import Path
import subprocess
import datetime
import simpleaudio as sa
from configparser import ConfigParser, ExtendedInterpolation

dt = datetime.datetime
td = datetime.timedelta
INPUT_LISTENER = None

user_config = ConfigParser(interpolation=ExtendedInterpolation())
user_config.read("config.ini")

GROCY_DOMAIN = user_config["grocy_settings"].get("domain", "https://grocy.info")
GROCY_API_KEY = user_config["grocy_settings"].get("api_key", os.environ["GROCY_API_KEY"])
GROCY_DEFAULT_QUANTITY_UNIT = int(user_config["grocy_settings"]["default_quantity_unit"])
GROCY_DEFAULT_QUANTITY_FACTOR = float(user_config["grocy_settings"]["default_quantity_factor"])
GROCY_DEFAULT_INVENTORY_ACTION = user_config["grocy_settings"]["default_inventory_action"]
BARCODE_API_URL = user_config["grocy_settings"]["barcode_api_url"]
user_timeout = int(user_config["local_settings"].get("code_selection_lifetime", 10))
CODE_SELECTION_LIFETIME = td(minutes=user_timeout)
do_speak = user_config["local_settings"]["do_speak"]
remote_speaker = user_config["local_settings"]["remote_speaker"]
speaker = user_config["tone_output_settings"]
speech = user_config["speech_output_settings"]
feedback_tones = user_config["feedback_tones"]
## TODO: add headless setup dialog for mapping opcode values to custom barcodes
## TODO: add headless setup dialog for mapping stock locations to custom barcodes
opcodes = user_config["opcodes"]
endpoint_prefixes = user_config["endpoint_prefixes"]
endpoint_suffixes = user_config["endpoint_suffixes"]

## TODO: make these external calls asynchronous
## TODO: bring the text to speech and remote speaker apps into the project
def speak_result(result):
    """Use TTS for audible feedback."""
    if remote_speaker:
        subprocess.call(["/home/ywr/speak_result", f'\"{result}\"'])
    else:
        subprocess.call(["/home/ywr/speak_result_local", f'\"{result}\"'])

def audible_playback(status):
    """Use wav files for audible feedback."""
    if remote_speaker:
        subprocess.call(["/home/ywr/remote_speaker", f'\"{status}\"'])
    else:
        audible_object = sa.WaveObject.from_wave_file(feedback_tones[status])
        playback_object = audible_object.play()
        playback_object.wait_done()

class ScannedCode: 
    """gather information to turn a scanned barcode into a complete object for GrocyClient"""
    active_opcode = GROCY_DEFAULT_INVENTORY_ACTION
    fallback_opcode = None # Used to retain active_opcode when using a transfer instruction
    active_transfer = False
    active_storage_source = None # INT, Used in determining the source of an item marked for transfer
    storage_locations = []
    storage_location_codes = []
    default_location_id = None
    DEFAULT_LOCATION = {}
    FALLBACK_LOCATION = {} # Used to retain SELECTED_LOCATION when using a transfer instruction
    SELECTED_LOCATION = {}
    last_scan_time = dt.now()

    def __init__(self, code):
        ScannedCode.scanned_code = code
        ScannedCode.scanned_name = None
        self.refresh_check()

# TODO: replace this with an asynchronous, timed reaction
    def refresh_check(self):
        if dt.now() - ScannedCode.last_scan_time > CODE_SELECTION_LIFETIME or ScannedCode.DEFAULT_LOCATION == {}:
#            print(dt.now() - ScannedCode.last_scan_time, CODE_SELECTION_LIFETIME)
#            print(ScannedCode.DEFAULT_LOCATION)
            print("Resetting opcode and location settings.")
            ScannedCode.active_opcode = GROCY_DEFAULT_INVENTORY_ACTION
            self.get_user_defaults()
            self.prepare_storage_locations()
        else:
            ScannedCode.last_scan_time = dt.now()

    def get_product_info(self):
        """Get info from grocy API about a scanned barcode."""
        head = {}
        head["GROCY-API-KEY"] = GROCY_API_KEY
        r = requests.get(f'{GROCY_DOMAIN}/api/stock/products/by-barcode/{self.scanned_code}', headers=head)
        r_data = json.loads(r.text)
        if r.status_code == 400:
            ScannedCode.active_storage_source = None
            return None
        elif r.status_code == 200:
            ScannedCode.active_storage_source = r_data["product"]["id"]
            return r_data["product"]["name"]
        else:
            ScannedCode.active_storage_source = None
            print(r.status_code, type(r.status_code))
            return None

    def get_barcode_info(self):
        """Get info from barcode API abot a scanned barcode."""
        r_url = f"{BARCODE_API_URL}{self.scanned_code}"
        r = requests.get(r_url)
        if r.status_code == 404:
            return None
        elif r.status_code == 200:
            r_data = json.loads(r.text)
            return r_data["product_name"]
        else:
            print(r.status_code, type(r.status_code))

    def get_user_defaults(self):
        """Determine default values as determined by user settings"""
        head = {}
        head["GROCY-API-KEY"] = GROCY_API_KEY
        r = requests.get(f'{GROCY_DOMAIN}/api/user/settings', headers=head)
        r_data = json.loads(r.text)
        ScannedCode.GROCY_DEFAULT_QUANTITY_UNIT = r_data['product_presets_qu_id']
        ScannedCode.default_location_id = r_data['product_presets_location_id']
#        print(f"Default quantity id: {r_data['product_presets_qu_id']}")
#        print(f"Default location id: {r_data['product_presets_location_id']}")
        
    def prepare_storage_locations(self):
        """Attempt to map location barcodes to locations known by grocy."""
        ScannedCode.storage_locations = []
        ScannedCode.storage_location_codes = []
        head = {}
        head["GROCY-API-KEY"] = GROCY_API_KEY
        r = requests.get(f'{GROCY_DOMAIN}/api/objects/locations', headers=head)
        r_data = json.loads(r.text)
        for i in r_data:
            if not i["userfields"]["barcode"]:
                print(f"No barcode set for storage location: {i['name']}")
            elif i["id"] == ScannedCode.default_location_id:
                    ScannedCode.storage_locations = [{"id":i["id"], "name":i["name"], "barcode":i["userfields"]["barcode"]}] + ScannedCode.storage_locations
                    ScannedCode.DEFAULT_LOCATION = i
                    print(ScannedCode.DEFAULT_LOCATION)
            else:
                ScannedCode.storage_locations.append({"id":i["id"], "name":i["name"], "barcode":i["userfields"]["barcode"]})
        for i in ScannedCode.storage_locations:
            ScannedCode.storage_location_codes.append(i["barcode"])


class GrocyClient(ScannedCode): 
    """directly manipulate grocy stock objects"""
    def __init__(self, code):
        super().__init__(code)
        self.process_scan()

    def process_scan(self):
        """Determine if the scanned code type and determine its corresponding name."""
        scanned_code = self.scanned_code
        if scanned_code in list(opcodes.values()):
            for k in opcodes.items():
                if k[1] == scanned_code:
                    if k[0] == "transfer" or ScannedCode.active_transfer:
                        if k[0] != "transfer": # Any other opcode during active transfer triggers fallback
                            ScannedCode.active_opcode = k[0]
                        else:
                            print("OPCODE DETECTED: Transfer.")
                            if do_speak:
                                speak_result("OPCODE DETECTED: Transfer.")
                            else:
                                audible_playback("transfer")
                        self.insert_transfer_opcode() # do the transfer needful
                    else:
                        ScannedCode.active_opcode = k[0]
                        print(f"OPCODE DETECTED: {ScannedCode.active_opcode}.")
                        if do_speak:
                            speak_result(f"OPCODE DETECTED: {ScannedCode.active_opcode}.")
                        else:
                            audible_playback(ScannedCode.active_opcode)
        elif scanned_code in ScannedCode.storage_location_codes:
            for i in ScannedCode.storage_locations:
                if i["barcode"] == scanned_code:
                    ScannedCode.SELECTED_LOCATION = i
                    print(f"LOCATION CODE DETECTED. This code will be used with subsequent scans.")
                    if do_speak:
                        speak_result(f"LOCATION CODE DETECTED.")
                    else:
                        audible_playback("transfer") #TODO add a location code sound?
        elif len(scanned_code) >= 12:
            print(f"PRODUCT CODE SCANNED: {scanned_code}.")
            self.scanned_name = self.get_product_info()
            if ScannedCode.active_transfer and self.scanned_name:
                self.insert_transfer_product()
            elif not self.scanned_name:
                self.scanned_name = self.get_barcode_info()
                if not self.scanned_name:
                    self.scanned_name = scanned_code
                    self.create_inventory_item()
                else:
                    self.create_inventory_item()
            self.modify_inventory_stock()
        else:
            if do_speak:
                speak_result("Invalid code scanned.")
            else:
                audible_playback("error_item_exists") # TODO find more soundbytes for error types
    
    def insert_transfer_opcode(self):
        """Divert normal flow to manage fallback locations and active transfers."""
        if not ScannedCode.active_transfer:
            if not ScannedCode.SELECTED_LOCATION: #ugly
                ScannedCode.SELECTED_LOCATION = ScannedCode.DEFAULT_LOCATION
            if ScannedCode.SELECTED_LOCATION and not ScannedCode.FALLBACK_LOCATION:
                ScannedCode.FALLBACK_LOCATION = ScannedCode.SELECTED_LOCATION
            ScannedCode.active_transfer = True
        elif ScannedCode.FALLBACK_LOCATION:
            ScannedCode.SELECTED_LOCATION = ScannedCode.FALLBACK_LOCATION
            ScannedCode.FALLBACK_LOCATION = {}
            ScannedCode.active_transfer = False

    def insert_transfer_product(self):
        """Complete product transfer and reset relevant values."""
        url = endpoint_prefixes["transfer"] + self.scanned_code + endpoint_suffixes["transfer"]
        head = {}
        head["content-type"] = "application/json"
        head["GROCY-API-KEY"] = GROCY_API_KEY
        req = {}
        req["amount"] = 1
        req["location_id_from"] = ScannedCode.active_storage_source
        req["location_id_to"] = ScannedCode.SELECTED_LOCATION
        r = requests.post(url, data=json.dumps(req), headers=head)
        ScannedCode.SELECTED_LOCATION = ScannedCode.FALLBACK_LOCATION
        ScannedCode.FALLBACK_LOCATION = {}
        ScannedCode.active_transfer = False
        if r.status_code == 200:
            if do_speak:
                speak_result(f"Request to {ScannedCode.active_opcode} {self.scanned_name} succeeded.")
            else:
                audible_playback(ScannedCode.active_opcode)
        else:
            if do_speak:
                speak_result(json.loads(r.text)["error_message"])
            else:
                audible_playback("error_no_item_remaining")

    def modify_inventory_stock(self):
        """Add or Consume grocy stock for the scanned product.""" 
        url = endpoint_prefixes[ScannedCode.active_opcode] + self.scanned_code + endpoint_suffixes[ScannedCode.active_opcode]
        head = {}
        head["content-type"] = "application/json"
        head["GROCY-API-KEY"] = GROCY_API_KEY
        req = {}
        req["amount"] = 1
        req["best_before_date"] = (dt.now() + td(36500)).strftime("%Y-%m-%d") # Add impossibly-distant expiration date for future work
        req["transaction_type"] = ScannedCode.active_opcode
        r = requests.post(url, data=json.dumps(req), headers=head)
        if r.status_code == 200:
            if do_speak:
                speak_result(f"Request to {ScannedCode.active_opcode} {self.scanned_name} succeeded.")
            else:
                audible_playback(ScannedCode.active_opcode)
        else: 
            if "amount" in json.loads(r.text)["error_message"]:
                if do_speak:
                    speak_result(f"All stock of {self.scanned_name} has been consumed.")
                else:
                    audible_playback("error_no_item_remaining")

    def create_inventory_item(self):
        """Create a new grocy inventory item for the scanned product."""
        url = endpoint_prefixes["create"]
        head = {}
        head["content-type"] = "application/json"
        head["GROCY-API-KEY"] = GROCY_API_KEY
        req = {}
        req["name"] = self.scanned_name
        req["barcode"] = self.scanned_code
        if ScannedCode.SELECTED_LOCATION:
            print(f"using preselected location: {ScannedCode.SELECTED_LOCATION['name']}")
            req["location_id"] = ScannedCode.SELECTED_LOCATION["id"]
        else:
            req["location_id"] = ScannedCode.DEFAULT_LOCATION["id"]
        req["qu_id_purchase"] = GROCY_DEFAULT_QUANTITY_UNIT
        req["qu_id_stock"] = GROCY_DEFAULT_QUANTITY_UNIT
        req["qu_factor_purchase_to_stock"] = GROCY_DEFAULT_QUANTITY_FACTOR
        r = requests.post(url, data=json.dumps(req), headers=head)
        if r.status_code == 200:
            if do_speak:
                speak_result("Creating new entry.")
            else:
                audible_playback("create")
        else:
            print(r.status_code, r.text)
            audible_playback("error_item_exists") # Maybe this result is not necessary


class InputHandler: 
    """set up a USB HID barcode scanner and send its scans to ScannedCode"""
    def select_scanner():
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
        scanned_code = None
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
                            GrocyClient(scanned_code)
                            print("Complete code scanned:", scanned_code)
                        else:
                            print("Non-numeric barcode scanned. This is not a UPC.")
                            if do_speak:
                                speak_result("Invalid code scanned.")
                            else:
                                audible_playback("error_no_item_remaining") # TODO srsly get some more audio clips for error types

InputHandler.select_scanner()