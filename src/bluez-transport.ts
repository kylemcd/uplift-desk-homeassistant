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
  monitor(path: string, onValue: (value: Uint8Array) => void): { close(): void }
}

export class BluezUpliftTransport implements UpliftTransport {
  readonly #options: BluezUpliftTransportOptions
  readonly #runner: BluezCommandRunner
  readonly #events = new EventEmitter()
  #devicePath?: string
  #inputPath?: string
  #outputPath?: string
  #inputFlags: string[] = []
  #monitor: { close(): void } | undefined
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
    await this.#runner.call(["call", "org.bluez", this.#devicePath, "org.bluez.Device1", "Connect"])
    objects = await this.#waitForServices()
    const detected = detectProfileFromManagedObjects(objects, this.#devicePath)
    this.#profile = detected.profile
    this.#inputPath = detected.inputPath
    this.#outputPath = detected.outputPath
    this.#inputFlags = detected.inputFlags
    this.#monitor = this.#runner.monitor(this.#outputPath, (value) => this.#events.emit("notification", value))
    await this.#runner.call(["call", "org.bluez", this.#outputPath, "org.bluez.GattCharacteristic1", "StartNotify"])
    this.#connected = true
    this.#connectionPoll = setInterval(() => void this.#pollConnection(), 5_000)
    return this.#profile
  }

  async disconnect(): Promise<void> {
    if (this.#connectionPoll) clearInterval(this.#connectionPoll)
    this.#connectionPoll = undefined
    if (this.#outputPath) await this.#runner.call(["call", "org.bluez", this.#outputPath, "org.bluez.GattCharacteristic1", "StopNotify"]).catch(() => undefined)
    this.#monitor?.close()
    this.#monitor = undefined
    if (this.#devicePath) await this.#runner.call(["call", "org.bluez", this.#devicePath, "org.bluez.Device1", "Disconnect"]).catch(() => undefined)
    this.#connected = false
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
        this.#connected = false
        this.#events.emit("disconnect")
      }
    } catch (error) {
      this.#events.emit("disconnect", error instanceof Error ? error : new Error(String(error)))
    }
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
  readonly #dbusMonitor: string

  constructor(options: { busctl?: string; bluetoothctl?: string; dbusMonitor?: string } = {}) {
    this.#busctl = options.busctl ?? "busctl"
    this.#bluetoothctl = options.bluetoothctl ?? "bluetoothctl"
    this.#dbusMonitor = options.dbusMonitor ?? "dbus-monitor"
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

  monitor(path: string, onValue: (value: Uint8Array) => void): { close(): void } {
    const match = `type='signal',sender='org.bluez',path='${path}',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged'`
    const child = spawn(this.#dbusMonitor, ["--system", match], { stdio: ["ignore", "pipe", "pipe"] })
    let block = ""
    child.stdout.setEncoding("utf8")
    child.stdout.on("data", (chunk: string) => {
      block += chunk
      const blocks = block.split(/\n\s*\n/)
      block = blocks.pop() ?? ""
      for (const message of blocks) emitBytes(message, onValue)
    })
    return { close: () => child.kill("SIGTERM") }
  }
}

function emitBytes(message: string, onValue: (value: Uint8Array) => void): void {
  const value = decodeDbusMonitorMessage(message)
  if (value) onValue(value)
}

export function decodeDbusMonitorMessage(message: string): Uint8Array | undefined {
  if (!message.includes('string "Value"') || !message.includes('string "org.bluez.GattCharacteristic1"')) return
  const valueSection = message.slice(message.indexOf('string "Value"'))
  const compactArray = valueSection.match(/array of bytes\s*\[([\s\S]*?)\]/i)
  const bytes = compactArray
    ? [...compactArray[1]!.matchAll(/\b([0-9a-f]{2})\b/gi)].map((match) => Number.parseInt(match[1]!, 16))
    : [...valueSection.matchAll(/\bbyte\s+(?:0x([0-9a-f]{2})|(\d{1,3}))\b/gi)].map((match) => match[1] ? Number.parseInt(match[1], 16) : Number.parseInt(match[2]!, 10)).filter((byte) => byte <= 0xff)
  return bytes.length > 0 ? Uint8Array.from(bytes) : undefined
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
