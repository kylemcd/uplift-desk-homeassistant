import type { NotificationPacket } from "./types.js"

export function computeChecksum(opcode: number, payload: Uint8Array = new Uint8Array()): number {
  assertByte(opcode, "opcode")
  if (payload.length > 0xff) throw new RangeError("payload length must be <= 255")
  return (opcode + payload.length + payload.reduce((sum, byte) => sum + byte, 0)) & 0xff
}

export function encodeCommand(opcode: number, payload: Uint8Array = new Uint8Array()): Uint8Array {
  const packet = new Uint8Array(payload.length + 6)
  packet.set([0xf1, 0xf1, opcode, payload.length], 0)
  packet.set(payload, 4)
  packet[packet.length - 2] = computeChecksum(opcode, payload)
  packet[packet.length - 1] = 0x7e
  return packet
}

export function decodeNotifications(data: Uint8Array): NotificationPacket[] {
  const packets: NotificationPacket[] = []
  for (let cursor = 0; cursor + 6 <= data.length;) {
    if (data[cursor] !== 0xf2 || data[cursor + 1] !== 0xf2) {
      cursor += 1
      continue
    }
    const payloadLength = data[cursor + 3]
    if (payloadLength === undefined) break
    const packetLength = payloadLength + 6
    if (cursor + packetLength > data.length) break
    const opcode = data[cursor + 2]
    if (opcode === undefined) break
    const payload = data.slice(cursor + 4, cursor + 4 + payloadLength)
    const checksum = data[cursor + packetLength - 2]
    const trailer = data[cursor + packetLength - 1]
    if (checksum === computeChecksum(opcode, payload) && trailer === 0x7e) {
      packets.push({ opcode, payload, checksum })
      cursor += packetLength
    } else {
      cursor += 1
    }
  }
  return packets
}

export class NotificationStreamDecoder {
  #buffer = new Uint8Array()

  push(data: Uint8Array): NotificationPacket[] {
    const joined = new Uint8Array(this.#buffer.length + data.length)
    joined.set(this.#buffer)
    joined.set(data, this.#buffer.length)
    this.#buffer = joined
    const packets: NotificationPacket[] = []
    while (this.#buffer.length >= 2) {
      const header = findHeader(this.#buffer)
      if (header < 0) {
        this.#buffer = this.#buffer.at(-1) === 0xf2 ? this.#buffer.slice(-1) : new Uint8Array()
        break
      }
      if (header > 0) this.#buffer = this.#buffer.slice(header)
      if (this.#buffer.length < 4) break
      const payloadLength = this.#buffer[3]!
      const packetLength = payloadLength + 6
      if (this.#buffer.length < packetLength) break
      const candidate = this.#buffer.slice(0, packetLength)
      const decoded = decodeNotifications(candidate)
      if (decoded.length === 1) {
        packets.push(decoded[0]!)
        this.#buffer = this.#buffer.slice(packetLength)
      } else {
        this.#buffer = this.#buffer.slice(1)
      }
    }
    if (this.#buffer.length > 1_024) this.#buffer = this.#buffer.slice(-1_024)
    return packets
  }

  reset(): void { this.#buffer = new Uint8Array() }
}

function findHeader(data: Uint8Array): number {
  for (let index = 0; index + 1 < data.length; index += 1) {
    if (data[index] === 0xf2 && data[index + 1] === 0xf2) return index
  }
  return -1
}

function assertByte(value: number, name: string): void {
  if (!Number.isInteger(value) || value < 0 || value > 0xff) {
    throw new RangeError(`${name} must be an integer in [0, 255]`)
  }
}
