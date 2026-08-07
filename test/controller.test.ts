import { describe, expect, it } from "vitest"
import { bluetoothBaseUuid, UpliftDeskController, type DeskProfile, type UpliftTransport } from "../src/index.js"

const profile: DeskProfile = {
  variant: "jiecang_ff00",
  serviceUuid: bluetoothBaseUuid(0xff00),
  inputCharacteristicUuid: bluetoothBaseUuid(0xff01),
  outputCharacteristicUuid: bluetoothBaseUuid(0xff02),
  nameCharacteristicUuid: bluetoothBaseUuid(0xfe63),
  requiresWake: false,
}

class FakeTransport implements UpliftTransport {
  connected = false
  profile = profile
  writes: Uint8Array[] = []
  notifications = new Set<(data: Uint8Array) => void>()
  disconnects = new Set<(error?: Error) => void>()
  connect(): Promise<DeskProfile> { this.connected = true; return Promise.resolve(profile) }
  disconnect(): Promise<void> { this.connected = false; return Promise.resolve() }
  write(packet: Uint8Array): Promise<void> { this.writes.push(packet); return Promise.resolve() }
  onNotification(listener: (data: Uint8Array) => void): () => void { this.notifications.add(listener); return () => this.notifications.delete(listener) }
  onDisconnect(listener: (error?: Error) => void): () => void { this.disconnects.add(listener); return () => this.disconnects.delete(listener) }
  notify(data: number[]): void { for (const listener of this.notifications) listener(Uint8Array.from(data)) }
}

describe("UpliftDeskController", () => {
  it("connects, writes commands, and reduces notifications into state", async () => {
    const transport = new FakeTransport()
    const desk = new UpliftDeskController(transport, { minimumWriteIntervalMs: 0 })
    await desk.connect()
    await desk.moveUp()
    transport.notify([0xf2, 0xf2, 0x0e, 0x01, 0x01, 0x10, 0x7e])
    transport.notify([0xf2, 0xf2, 0x01, 0x03, 0x01, 0x23, 0x00, 0x28, 0x7e])
    expect(desk.state.connected).toBe(true)
    expect(desk.state.unit).toBe("inches")
    expect(desk.state.heightMm).toBeCloseTo(291 * 2.54)
    expect(transport.writes).toHaveLength(1)
  })

  it("prioritizes stop without waiting for queued work", async () => {
    const transport = new FakeTransport()
    const desk = new UpliftDeskController(transport, { minimumWriteIntervalMs: 0 })
    await desk.connect()
    await Promise.all([desk.moveUp(), desk.stop()])
    expect(transport.writes.at(-1)?.[2]).toBe(0x2b)
  })

  it("classifies a stalled transport write as timed-out", async () => {
    const transport = new FakeTransport()
    transport.write = () => new Promise<void>(() => undefined)
    const desk = new UpliftDeskController(transport, { minimumWriteIntervalMs: 0, commandTimeoutMs: 5 })
    await desk.connect()
    await expect(desk.moveUp()).resolves.toMatchObject({ status: "timed-out" })
  })
})
