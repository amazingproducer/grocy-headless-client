# grocy-input-upc-handler

USB HID based barcode scanner-driven grocy API client.

## At all times, the app must know:

- Active Opcode
- Active Location
- Grocy API path
- UPC API path

## TWO TYPES OF REQUEST
- Inventory Request: builds a new inventory item for future stock requests
- Stock Request (ADD/CONSUME/TRANSFER/OPEN Opcodes): adds, modifies, or deletes single stock units for a given inventory item

## FLOW

### REVERT OPCODE AND LOCATION TO DEFAULT
- If decay timer has expired, set Opcode and Location to default and restart

### DETERMINE BARCODE TYPE:
- Acquire barcode string
  - If barcode string is within opcode list, set opcode and restart
  - Else if barcode string is within location list, set location and restart
  - Else if barcode string is shorter than 12, reject string and restart
  - Else barcode string is for a product

### BUILD REQUESTS FROM BARCODE
- If barcode does not exist in Grocy DB, make UPC lookup API request for product name
  - If UPC lookup returns a product name, build inventory request using the product name
  - Else, build inventory request using the barcode as the product name

- Build stock request via barcode

### MAKE BUILT REQUESTS AND HANDLE ERRORS
- Make inventory request, if exists
- If an error is encountered:
  - Make a log entry
  - Send an audible feedback signal
  - Restart to initial state

- Make stock request
- If an error is encountered:
  - Make a log entry
  - Send an audible feedback signal
  - Restart to initial state

### Restarting to initial state includes resetting the Opcode and Location Decay timers
