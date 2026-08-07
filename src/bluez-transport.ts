import { spawn } from "node:child_process"
import type { ChildProcessByStdio } from "node:child_process"
import { EventEmitter } from "node:events"
import type { Readable } from "node:stream"
import { DESK_PROFILES } from "./profiles.js"
import type { DeskProfile, UpliftTransport } from "./types.js"

export interface BluezUpliftTransportOptions {
  address: string
  adapter?: string
  discoveryTimeoutMs?: number
  runner?: BluezCommandRunner
}

export interface BluezCommandRunner {
  call(args: readonly string[]): Promise<string>
  scan(durationMs: number): { done: Promise<void>; close(): void }
  notify(path: string, onValue: (value: Uint8Array) => void): { ready: Promise<void>; closed: Promise<Error | undefined>; close(): void }
}

export class BluezUpliftTransport implements UpliftTransport {
  readonly #options: BluezUpliftTransportOptions
  readonly #runner: BluezCommandRunner
  readonly #events = new EventEmitter()
  #devicePath?: string
  #inputPath?: string
  #outputPath?: string
  #inputFlags: string[] = []
  #notificationSession: { ready: Promise<void>; closed: Promise<Error | undefined>; close(): void } | undefined
  #connectionPoll: NodeJS.Timeout | undefined
  #profile?: DeskProfile
  #connected = false

  constructor(options: BluezUpliftTransportOptions) {
    this.#options = options
    this.#runner = options.runner ?? new BusctlCommandRunner()
  }

  get connected(): boolean { return this.#connected }
  get profile(): DeskProfile | undefined { return this.#profile }

  async connect(): Promise<DeskProfile> {
    if (this.#connected && this.#profile) return this.#profile
    const adapterPath = this.#options.adapter ? `/org/bluez/${this.#options.adapter}` : "/org/bluez/hci0"
    this.#devicePath = `${adapterPath}/dev_${this.#options.address.replaceAll(":", "_").toUpperCase()}`
    let objects = await this.#managedObjects()
    if (!objects[this.#devicePath]?.["org.bluez.Device1"]) {
      await this.#discover()
      objects = await this.#managedObjects()
    }
    if (!objects[this.#devicePath]?.["org.bluez.Device1"]) throw new Error(`device ${this.#options.address} was not discovered`)
    try {
      await this.#runner.call(["call", "org.bluez", this.#devicePath, "org.bluez.Device1", "Connect"])
      objects = await this.#waitForServices()
      const detected = detectProfileFromManagedObjects(objects, this.#devicePath)
      this.#profile = detected.profile
      this.#inputPath = detected.inputPath
      this.#outputPath = detected.outputPath
      this.#inputFlags = detected.inputFlags
      this.#notificationSession = this.#runner.notify(this.#outputPath, (value) => this.#events.emit("notification", value))
      await this.#notificationSession.ready
      const notificationSession = this.#notificationSession
      void notificationSession.closed.then(async (error) => {
        if (this.#notificationSession !== notificationSession || !this.#connected) return
        this.#notificationSession = undefined
        if (this.#connectionPoll) clearInterval(this.#connectionPoll)
        this.#connectionPoll = undefined
        this.#connected = false
        await this.#disconnectDevice()
        this.#events.emit("disconnect", error ?? new Error("Bluetooth notification session ended"))
      })
      this.#connected = true
      this.#connectionPoll = setInterval(() => void this.#pollConnection(), 5_000)
      return this.#profile
    } catch (error) {
      const notificationSession = this.#notificationSession
      this.#notificationSession = undefined
      notificationSession?.close()
      this.#connected = false
      await this.#disconnectDevice()
      throw error
    }
  }

  async disconnect(): Promise<void> {
    this.#connected = false
    if (this.#connectionPoll) clearInterval(this.#connectionPoll)
    this.#connectionPoll = undefined
    const notificationSession = this.#notificationSession
    this.#notificationSession = undefined
    notificationSession?.close()
    await this.#disconnectDevice()
  }

  async write(packet: Uint8Array): Promise<void> {
    if (!this.#inputPath || !this.#connected) throw new Error("transport is not connected")
    const mode = this.#inputFlags.includes("write-without-response") ? "command" : "request"
    if (!this.#inputFlags.includes("write-without-response") && !this.#inputFlags.includes("write")) throw new Error("input characteristic does not permit writes")
    await this.#runner.call([
      "call", "org.bluez", this.#inputPath, "org.bluez.GattCharacteristic1", "WriteValue", "aya{sv}",
      String(packet.length), ...[...packet].map(String), "1", "type", "s", mode,
    ])
  }

  onNotification(listener: (data: Uint8Array) => void): () => void {
    this.#events.on("notification", listener)
    return () => this.#events.off("notification", listener)
  }

  onDisconnect(listener: (error?: Error) => void): () => void {
    this.#events.on("disconnect", listener)
    return () => this.#events.off("disconnect", listener)
  }

  async #discover(): Promise<void> {
    const durationMs = this.#options.discoveryTimeoutMs ?? 15_000
    const scan = this.#runner.scan(durationMs)
    const deadline = Date.now() + durationMs
    try {
      while (Date.now() < deadline) {
        const objects = await this.#managedObjects()
        if (this.#devicePath && objects[this.#devicePath]?.["org.bluez.Device1"]) return
        await new Promise((resolve) => setTimeout(resolve, 250))
      }
    } finally {
      scan.close()
      await scan.done.catch(() => undefined)
    }
  }

  async #managedObjects(): Promise<ManagedObjects> {
    const output = await this.#runner.call(["--json=short", "call", "org.bluez", "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"])
    const parsed = JSON.parse(output) as { data?: [ManagedObjects] }
    return parsed.data?.[0] ?? {}
  }

  async #waitForServices(): Promise<ManagedObjects> {
    const deadline = Date.now() + 10_000
    while (Date.now() < deadline) {
      const objects = await this.#managedObjects()
      if (this.#devicePath && Object.keys(objects).some((path) => path.startsWith(`${this.#devicePath}/service`))) return objects
      await new Promise((resolve) => setTimeout(resolve, 250))
    }
    throw new Error("timed out waiting for resolved GATT services")
  }

  async #pollConnection(): Promise<void> {
    try {
      const objects = await this.#managedObjects()
      const connected = this.#devicePath ? variantValue(objects[this.#devicePath]?.["org.bluez.Device1"]?.Connected) === true : false
      if (!connected && this.#connected) {
        if (this.#connectionPoll) clearInterval(this.#connectionPoll)
        this.#connectionPoll = undefined
        const notificationSession = this.#notificationSession
        this.#notificationSession = undefined
        notificationSession?.close()
        this.#connected = false
        this.#events.emit("disconnect")
      }
    } catch (error) {
      this.#events.emit("disconnect", error instanceof Error ? error : new Error(String(error)))
    }
  }

  async #disconnectDevice(): Promise<void> {
    if (this.#devicePath) await this.#runner.call(["call", "org.bluez", this.#devicePath, "org.bluez.Device1", "Disconnect"]).catch(() => undefined)
  }
}

interface BusctlVariant { type: string; data: unknown }
type ManagedObjects = Record<string, Record<string, Record<string, BusctlVariant>>>

function detectProfileFromManagedObjects(objects: ManagedObjects, devicePath: string): { profile: DeskProfile; inputPath: string; outputPath: string; inputFlags: string[] } {
  const services = new Map<string, string>()
  const characteristics = new Map<string, { path: string; flags: string[] }>()
  for (const [path, interfaces] of Object.entries(objects)) {
    if (!path.startsWith(devicePath)) continue
    const service = interfaces["org.bluez.GattService1"]
    const characteristic = interfaces["org.bluez.GattCharacteristic1"]
    const serviceUuid = variantValue(service?.UUID)
    const characteristicUuid = variantValue(characteristic?.UUID)
    if (typeof serviceUuid === "string") services.set(serviceUuid.toLowerCase(), path)
    if (typeof characteristicUuid === "string") {
      const flags = variantValue(characteristic?.Flags)
      characteristics.set(characteristicUuid.toLowerCase(), { path, flags: Array.isArray(flags) ? flags.filter((item): item is string => typeof item === "string") : [] })
    }
  }
  for (const profile of DESK_PROFILES) {
    if (!services.has(profile.serviceUuid)) continue
    const input = characteristics.get(profile.inputCharacteristicUuid)
    const output = characteristics.get(profile.outputCharacteristicUuid)
    if (input && output) return { profile, inputPath: input.path, outputPath: output.path, inputFlags: input.flags }
  }
  throw new Error(`unsupported UPLIFT GATT profile; services: ${[...services.keys()].join(", ")}`)
}

function variantValue(value: BusctlVariant | undefined): unknown { return value?.data }

export class BusctlCommandRunner implements BluezCommandRunner {
  readonly #busctl: string
  readonly #bluetoothctl: string

  constructor(options: { busctl?: string; bluetoothctl?: string } = {}) {
    this.#busctl = options.busctl ?? "busctl"
    this.#bluetoothctl = options.bluetoothctl ?? "bluetoothctl"
  }

  call(args: readonly string[]): Promise<string> {
    return run(this.#busctl, args)
  }

  scan(durationMs: number): { done: Promise<void>; close(): void } {
    const seconds = Math.max(1, Math.ceil(durationMs / 1_000))
    const child = spawn(this.#bluetoothctl, ["--timeout", String(seconds), "scan", "le"], { stdio: ["ignore", "pipe", "pipe"] })
    const done = collectChild(this.#bluetoothctl, child).then(() => undefined)
    return { done, close: () => child.kill("SIGTERM") }
  }

  notify(path: string, onValue: (value: Uint8Array) => void): { ready: Promise<void>; closed: Promise<Error | undefined>; close(): void } {
    // Interactive bluetoothctl stays alive until explicitly terminated. On
    // current BlueZ, `--timeout 0` still exits after the default idle timeout.
    const child = spawn(this.#bluetoothctl, [], { stdio: ["pipe", "pipe", "pipe"] })
    const decoder = new BluetoothctlNotificationDecoder()
    let settled = false
    let resolveReady: (() => void) | undefined
    let rejectReady: ((error: Error) => void) | undefined
    let resolveClosed: ((error: Error | undefined) => void) | undefined
    let closedSettled = false
    const ready = new Promise<void>((resolve, reject) => {
      resolveReady = resolve
      rejectReady = reject
    })
    const closed = new Promise<Error | undefined>((resolve) => {
      resolveClosed = resolve
    })
    const timeout = setTimeout(() => {
      if (!settled) {
        settled = true
        rejectReady?.(new Error(`timed out enabling notifications for ${path}`))
      }
      child.kill("SIGTERM")
    }, 10_000)

    child.stdout.setEncoding("utf8")
    child.stdout.on("data", (chunk: string) => {
      for (const line of decoder.lines(chunk)) {
        if (line.includes("Notify started") || line.includes("Notifying: yes")) {
          if (!settled) {
            settled = true
            clearTimeout(timeout)
            resolveReady?.()
          }
        }
        if (/Failed to start notify|not available|Invalid command/i.test(line)) {
          if (!settled) {
            settled = true
            clearTimeout(timeout)
            rejectReady?.(new Error(`bluetoothctl could not enable notifications for ${path}: ${line.trim()}`))
            child.kill("SIGTERM")
          }
        }
      }
      for (const value of decoder.values()) onValue(value)
    })
    child.once("error", (error) => {
      if (!closedSettled) {
        closedSettled = true
        resolveClosed?.(error)
      }
      if (!settled) {
        settled = true
        clearTimeout(timeout)
        rejectReady?.(error)
      }
    })
    child.once("close", (code) => {
      if (!closedSettled) {
        closedSettled = true
        resolveClosed?.(code === 0 || code === null ? undefined : new Error(`bluetoothctl notification process exited with code ${String(code)}`))
      }
      if (!settled) {
        settled = true
        clearTimeout(timeout)
        rejectReady?.(new Error(`bluetoothctl exited before notifications were ready (code ${String(code)})`))
      }
    })
    child.stdin.write(`agent off\nmenu gatt\nselect-attribute ${path}\nnotify on\n`)
    return { ready, closed, close: () => child.kill("SIGTERM") }
  }
}

function stripAnsi(value: string): string {
  let result = ""
  for (let index = 0; index < value.length; index += 1) {
    if (value.charCodeAt(index) === 0x1b && value[index + 1] === "[") {
      index += 2
      while (index < value.length) {
        const code = value.charCodeAt(index)
        if (code >= 0x40 && code <= 0x7e) break
        index += 1
      }
      continue
    }
    result += value[index]
  }
  return result
}

export class BluetoothctlNotificationDecoder {
  #buffer = ""
  #expectingValue = false
  #values: Uint8Array[] = []

  lines(chunk: string): string[] {
    this.#buffer += chunk.replaceAll("\r", "\n")
    const rawLines = this.#buffer.split("\n")
    this.#buffer = rawLines.pop() ?? ""
    const lines = rawLines.map(stripAnsi)
    for (const line of lines) {
      if (line.includes("Value:")) {
        this.#expectingValue = true
        continue
      }
      if (!this.#expectingValue) continue
      const match = line.match(/(?:^|>\s*)\s*((?:[0-9a-f]{2}\s+){5,}[0-9a-f]{2})\b/i)
      if (!match?.[1]) continue
      this.#values.push(Uint8Array.from(match[1].trim().split(/\s+/).map((byte) => Number.parseInt(byte, 16))))
      this.#expectingValue = false
    }
    return lines
  }

  values(): Uint8Array[] {
    return this.#values.splice(0)
  }
}

function run(command: string, args: readonly string[]): Promise<string> {
  const child = spawn(command, [...args], { stdio: ["ignore", "pipe", "pipe"] })
  return collectChild(command, child)
}

function collectChild(command: string, child: ChildProcessByStdio<null, Readable, Readable>): Promise<string> {
  return new Promise((resolve, reject) => {
    let stdout = ""
    let stderr = ""
    child.stdout.setEncoding("utf8").on("data", (chunk: string) => { stdout += chunk })
    child.stderr.setEncoding("utf8").on("data", (chunk: string) => { stderr += chunk })
    child.on("error", reject)
    child.on("close", (code) => code === 0 ? resolve(stdout.trim()) : reject(new Error(`${command} exited ${code}: ${stderr.trim()}`)))
  })
}
