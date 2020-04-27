# grocy-input-upc-handler

Grocy API handler for USB HID based barcode scanners.

USB BARCODE SCANNER INTEGRATION, GROCY

Issues:
Barcode scanner is a keyboard
  Scanned data is pushed into current x session
    remove with xinput
      xinput list
      xinput set-prop 10 "Device Enabled" 0
      xinput float 10
    python evdev's "grab" can gain exclusive access to keyboard

  Input device capture requires elevated permissions
    grant permission to regular users:
      lsusb (to get vendor/product IDs)
      add udev rule as /lib/udev/rules.d/90-usb-barcode-scanner.rules
        SUBSYSTEM=="input", ATTRS{idVendor}=="05e0", ATTRS{idProduct}=="1200" MODE="0644"

Barcodes provide context for multiple Grocy actions
  Hardware button on scanner provides no sniffable input

  Perhaps a barcode could be scanned to set the grocy context

    scan to input product into system
  
    scan to increment inventory quantity of product

    scan to decrement inventory quantity of product


