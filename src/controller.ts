import { EventEmitter } from "node:events"
import { commandToOpcode } from "./commands.js"
import { encodeCommand, NotificationStreamDecoder } from "./packet.js"
import type {
  CommandResult,
  DeskEvent,
  DeskState,
  KnownDeskCommand,
  NotificationPacket,
  UpliftTransport,
} from "./types.js"

const ERROR_CODES = ["E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09", "E10", "E11", "E12", "E13", "H01", "H02", "LOCK"] as const

export interface UpliftDeskControllerOptions {
  minimumWriteIntervalMs?: number
  wakeCount?: number
  commandTimeoutMs?: number
}

export class UpliftDeskController {
  readonly #events = new EventEmitter()
  readonly #transport: UpliftTransport
  readonly #minimumWriteIntervalMs: number
  readonly #wakeCount: number
  readonly #commandTimeoutMs: number
  #state: DeskState = { connected: false, resetRequired: false, presets: {}, moving: "stopped" }
  #queue: Promise<unknown> = Promise.resolve()
  #stopGeneration = 0
  #lastWriteAt = 0
  #removeNotification: (() => void) | undefined
  #removeDisconnect: (() => void) | undefined
  readonly #notificationDecoder = new NotificationStreamDecoder()

  constructor(transport: UpliftTransport, options: UpliftDeskControllerOptions = {}) {
    this.#transport = transport
    this.#minimumWriteIntervalMs = options.minimumWriteIntervalMs ?? 100
    this.#wakeCount = options.wakeCount ?? 3
    this.#commandTimeoutMs = options.commandTimeoutMs ?? 5_000
  }

  get state(): Readonly<DeskState> {
    return structuredClone(this.#state)
  }

  onEvent(listener: (event: DeskEvent) => void): () => void {
    this.#events.on("event", listener)
    return () => this.#events.off("event", listener)
  }

  async connect(): Promise<void> {
    if (this.#transport.connected) return
    this.#removeNotification = this.#transport.onNotification((data) => this.#processNotifications(data))
    this.#removeDisconnect = this.#transport.onDisconnect((error) => {
      this.#state = { ...this.#state, connected: false, moving: "stopped" }
      this.#emit({ type: "connection", connected: false })
      this.#emitState()
      if (error) this.#emit({ type: "transport_error", error })
    })
    const profile = await this.#transport.connect()
    this.#state = { ...this.#state, connected: true, profile }
    this.#emit({ type: "connection", connected: true })
    this.#emitState()
  }

  async disconnect(): Promise<void> {
    this.#removeNotification?.()
    this.#removeDisconnect?.()
    this.#removeNotification = undefined
    this.#removeDisconnect = undefined
    this.#notificationDecoder.reset()
    await this.#transport.disconnect()
    this.#state = { ...this.#state, connected: false, moving: "stopped" }
    this.#emit({ type: "connection", connected: false })
    this.#emitState()
  }

  execute(command: KnownDeskCommand): Promise<CommandResult> {
    if (command.type === "stop") {
      this.#stopGeneration += 1
      const stop = this.#send(command)
      this.#queue = stop.catch(() => undefined)
      return stop
    }
    const stopGeneration = this.#stopGeneration
    const operation = this.#queue.then(() => {
      if (isMovementCommand(command) && stopGeneration !== this.#stopGeneration) {
        const encoded = commandToOpcode(command)
        return {
          command,
          status: "failed" as const,
          sentAt: new Date().toISOString(),
          packet: encodeCommand(encoded.opcode, encoded.payload),
          error: "superseded by stop",
        }
      }
      return this.#send(command)
    })
    this.#queue = operation.catch(() => undefined)
    return operation
  }

  wake = (): Promise<CommandResult> => this.execute({ type: "wake" })
  moveUp = (): Promise<CommandResult> => this.execute({ type: "move_up" })
  moveDown = (): Promise<CommandResult> => this.execute({ type: "move_down" })
  stop = (): Promise<CommandResult> => this.execute({ type: "stop" })
  savePreset = (preset: 1 | 2): Promise<CommandResult> => this.execute({ type: "save_preset", preset })
  recallPreset = (preset: 1 | 2): Promise<CommandResult> => this.execute({ type: "recall_preset", preset })
  requestHeightLimits = (): Promise<CommandResult> => this.execute({ type: "request_height_limits" })
  requestUnits = (): Promise<CommandResult> => this.execute({ type: "request_units" })
  moveToHeight = (height: number): Promise<CommandResult> => this.execute({ type: "move_to_height", height })
  setUnits = (unit: "centimeters" | "inches"): Promise<CommandResult> => this.execute({ type: "set_units", unit })
  setTouchMode = (mode: "one_touch" | "constant_touch"): Promise<CommandResult> => this.execute({ type: "set_touch_mode", mode })
  setCalibrationOffset = (offset: number): Promise<CommandResult> => this.execute({ type: "set_calibration_offset", offset })
  setMaximumHeight = (heightMm: number): Promise<CommandResult> => this.execute({ type: "set_maximum_height", heightMm })
  setCurrentHeightAsLimit = (limit: "maximum" | "minimum"): Promise<CommandResult> => this.execute({ type: "set_current_height_as_limit", limit })
  clearHeightLimit = (limit: "maximum" | "minimum"): Promise<CommandResult> => this.execute({ type: "clear_height_limit", limit })
  reset = (): Promise<CommandResult> => this.execute({ type: "reset" })

  async #send(command: KnownDeskCommand): Promise<CommandResult> {
    if (!this.#transport.connected) throw new Error("desk transport is not connected")
    try {
      if (this.#transport.profile?.requiresWake && command.type !== "wake") {
        for (let index = 0; index < this.#wakeCount; index += 1) {
          await this.#writePacket(encodeCommand(0x00))
        }
      }
      const encoded = commandToOpcode(command)
      const packet = encodeCommand(encoded.opcode, encoded.payload)
      await this.#writePacket(packet)
      if (command.type === "move_up") this.#state.moving = "up"
      if (command.type === "move_down") this.#state.moving = "down"
      if (command.type === "stop") this.#state.moving = "stopped"
      this.#emitState()
      return { command, status: "sent", sentAt: new Date().toISOString(), packet }
    } catch (error) {
      const packetData = commandToOpcode(command)
      const packet = encodeCommand(packetData.opcode, packetData.payload)
      return {
        command,
        status: error instanceof CommandTimeoutError ? "timed-out" : "failed",
        sentAt: new Date().toISOString(),
        packet,
        error: error instanceof Error ? error.message : String(error),
      }
    }
  }

  async #writePacket(packet: Uint8Array): Promise<void> {
    const waitMs = Math.max(0, this.#minimumWriteIntervalMs - (Date.now() - this.#lastWriteAt))
    if (waitMs > 0) await new Promise((resolve) => setTimeout(resolve, waitMs))
    let timeout: NodeJS.Timeout | undefined
    try {
      await Promise.race([
        this.#transport.write(packet),
        new Promise<never>((_resolve, reject) => {
          timeout = setTimeout(() => reject(new CommandTimeoutError(this.#commandTimeoutMs)), this.#commandTimeoutMs)
        }),
      ])
    } finally {
      if (timeout) clearTimeout(timeout)
    }
    this.#lastWriteAt = Date.now()
  }

  #processNotifications(data: Uint8Array): void {
    for (const packet of this.#notificationDecoder.push(data)) {
      this.#emit({ type: "notification", packet })
      if (!this.#applyNotification(packet)) this.#emit({ type: "unknown_notification", packet })
    }
  }

  #applyNotification(packet: NotificationPacket): boolean {
    const payload = packet.payload
    const now = new Date().toISOString()
    this.#state.lastNotificationAt = now
    switch (packet.opcode) {
      case 0x01: {
        if (payload.length !== 3) return false
        const raw = readUint16(payload)
        this.#state.heightRaw = raw
        if (this.#state.unit) this.#state.heightMm = this.#state.unit === "inches" ? raw * 2.54 : raw
        break
      }
      case 0x02: {
        if (payload.length !== 1) return false
        const code = payload[0]
        if (code === undefined || code < 1 || code > ERROR_CODES.length) return false
        const error = ERROR_CODES[code - 1]
        if (!error) return false
        this.#state.error = error
        break
      }
      case 0x04:
        if (payload.length !== 0) return false
        this.#state.resetRequired = true
        break
      case 0x07:
        if (payload.length !== 4) return false
        this.#state.configuredMaximumMm = readUint16(payload, 0)
        this.#state.configuredMinimumMm = readUint16(payload, 2)
        break
      case 0x0e: {
        if (payload.length !== 1 || (payload[0] !== 0 && payload[0] !== 1)) return false
        this.#state.unit = payload[0] === 0 ? "centimeters" : "inches"
        if (this.#state.heightRaw !== undefined) {
          this.#state.heightMm = this.#state.unit === "inches" ? this.#state.heightRaw * 2.54 : this.#state.heightRaw
        }
        break
      }
      case 0x19:
        if (payload.length !== 1 || (payload[0] !== 0 && payload[0] !== 1)) return false
        this.#state.touchMode = payload[0] === 0 ? "one_touch" : "constant_touch"
        break
      case 0x1f:
        if (payload.length !== 1 || (payload[0] !== 0 && payload[0] !== 1)) return false
        this.#state.lockStatus = payload[0] === 0 ? "unlocked" : "locked"
        break
      case 0x21:
        if (payload.length !== 2) return false
        this.#state.activeMaximumMm = readUint16(payload)
        break
      case 0x22:
        if (payload.length !== 2) return false
        this.#state.activeMinimumMm = readUint16(payload)
        break
      case 0x25:
      case 0x26:
      case 0x27:
      case 0x28: {
        if (payload.length !== 2) return false
        const preset = (packet.opcode - 0x24) as 1 | 2 | 3 | 4
        this.#state.presets[preset] = readUint16(payload)
        break
      }
      default:
        return false
    }
    this.#emitState()
    return true
  }

  #emitState(): void {
    this.#emit({ type: "state", state: this.state })
  }

  #emit(event: DeskEvent): void {
    this.#events.emit("event", event)
  }
}

function isMovementCommand(command: KnownDeskCommand): boolean {
  return command.type === "move_up" || command.type === "move_down" || command.type === "move_to_height" || command.type === "recall_preset"
}

function readUint16(bytes: Uint8Array, offset = 0): number {
  const high = bytes[offset]
  const low = bytes[offset + 1]
  if (high === undefined || low === undefined) throw new RangeError("missing uint16 bytes")
  return (high << 8) | low
}

class CommandTimeoutError extends Error {
  constructor(timeoutMs: number) { super(`desk command timed out after ${timeoutMs} ms`) }
}
