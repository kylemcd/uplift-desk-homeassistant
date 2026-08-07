import { describe, expect, it } from "vitest"
import { BluetoothctlNotificationDecoder } from "../src/bluez-transport.js"

describe("bluetoothctl notification decoding", () => {
  it("extracts the bytes printed after a characteristic Value change", () => {
    const decoder = new BluetoothctlNotificationDecoder()
    decoder.lines("\u001b[0;93m[CHG\u001b[0m] Attribute /org/bluez/hci0/dev_F2/service000b/char000e Value:\r\n")
    decoder.lines("  f2 f2 25 02 01 09 31 7e                          ..%...1~\r\n")

    expect(decoder.values()).toEqual([Uint8Array.from([0xf2, 0xf2, 0x25, 0x02, 0x01, 0x09, 0x31, 0x7e])])
  })

  it("handles fragmented output and ignores unrelated hex text", () => {
    const decoder = new BluetoothctlNotificationDecoder()
    decoder.lines("[CHG] Attribute /org/bluez/hci0/dev_F2/service000b/char000e Val")
    decoder.lines("ue:\r\n  f2 f2 01 03 01")
    expect(decoder.values()).toEqual([])
    decoder.lines(" 0e 0f 22 7e                       .......\"~\r\nHandle 0x000e\r\n")

    expect(decoder.values()).toEqual([Uint8Array.from([0xf2, 0xf2, 0x01, 0x03, 0x01, 0x0e, 0x0f, 0x22, 0x7e])])
  })
})
