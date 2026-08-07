import { describe, expect, it, vi } from "vitest"
import { BluetoothctlNotificationDecoder, BluezUpliftTransport, type BluezCommandRunner } from "../src/bluez-transport.js"

const devicePath = "/org/bluez/hci0/dev_02_00_00_00_00_01"

function managedObjects(connected: boolean): string {
  const variant = (type: string, data: unknown) => ({ type, data })
  return JSON.stringify({ data: [{
    [devicePath]: { "org.bluez.Device1": { Connected: variant("b", connected) } },
    [`${devicePath}/service000b`]: { "org.bluez.GattService1": { UUID: variant("s", "0000ff00-0000-1000-8000-00805f9b34fb") } },
    [`${devicePath}/service000b/char000c`]: { "org.bluez.GattCharacteristic1": {
      UUID: variant("s", "0000ff01-0000-1000-8000-00805f9b34fb"),
      Flags: variant("as", ["write-without-response"]),
    } },
    [`${devicePath}/service000b/char000e`]: { "org.bluez.GattCharacteristic1": {
      UUID: variant("s", "0000ff02-0000-1000-8000-00805f9b34fb"),
      Flags: variant("as", ["notify"]),
    } },
  }] })
}

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

  it("releases the notification owner when the desk disconnects", async () => {
    vi.useFakeTimers()
    let connected = true
    let notificationClosed = false
    let closeNotification: ((error: Error | undefined) => void) | undefined
    const runner: BluezCommandRunner = {
      call: (args) => Promise.resolve(args[0] === "--json=short" ? managedObjects(connected) : ""),
      scan: () => ({ done: Promise.resolve(), close: () => undefined }),
      notify: () => ({
        ready: Promise.resolve(),
        closed: new Promise((resolve) => { closeNotification = resolve }),
        close: () => {
          notificationClosed = true
          closeNotification?.(undefined)
        },
      }),
    }
    const transport = new BluezUpliftTransport({ address: "02:00:00:00:00:01", runner })
    const disconnected = vi.fn()
    transport.onDisconnect(disconnected)
    await transport.connect()

    connected = false
    await vi.advanceTimersByTimeAsync(5_000)

    expect(notificationClosed).toBe(true)
    expect(disconnected).toHaveBeenCalledOnce()
    expect(transport.connected).toBe(false)
    vi.useRealTimers()
  })
})
