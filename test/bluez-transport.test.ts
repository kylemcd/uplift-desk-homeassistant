import { describe, expect, it } from "vitest"
import { decodeDbusMonitorMessage } from "../src/bluez-transport.js"

describe("dbus-monitor notification decoding", () => {
  it("extracts a BlueZ characteristic Value byte array", () => {
    const message = `signal sender=org.bluez -> destination=:1.1 serial=42 path=/org/bluez/hci0/dev_F2/service0010/char0012; interface=org.freedesktop.DBus.Properties; member=PropertiesChanged
   string "org.bluez.GattCharacteristic1"
   array [
      dict entry(
         string "Value"
         variant             array of bytes [
               f2  f2  01  02  03  06  7e
            ]
      )
   ]`

    expect(decodeDbusMonitorMessage(message)).toEqual(Uint8Array.from([0xf2, 0xf2, 0x01, 0x02, 0x03, 0x06, 0x7e]))
  })

  it("ignores unrelated property signals", () => {
    expect(decodeDbusMonitorMessage('string "org.bluez.Device1"\nstring "Connected"\nboolean true')).toBeUndefined()
  })
})
