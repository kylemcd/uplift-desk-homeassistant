export type DeskVariant = "jiecang_00ff" | "jiecang_fe60" | "jiecang_ff00" | "jiecang_ff12"
export type DeskUnit = "centimeters" | "inches"
export type DeskTouchMode = "one_touch" | "constant_touch"
export type DeskLockStatus = "unlocked" | "locked"
export type HeightLimit = "maximum" | "minimum"
export type CommandConfidence = "reference-only" | "observed" | "verified-live"
export type CommandResultStatus = "sent" | "state-confirmed" | "timed-out" | "failed"

export interface DeskProfile {
  readonly variant: DeskVariant
  readonly serviceUuid: string
  readonly inputCharacteristicUuid: string
  readonly outputCharacteristicUuid: string
  readonly nameCharacteristicUuid: string
  readonly requiresWake: boolean
}

export interface DeskState {
  connected: boolean
  profile?: DeskProfile
  heightRaw?: number
  heightMm?: number
  unit?: DeskUnit
  moving?: "up" | "down" | "stopped"
  error?: string
  resetRequired: boolean
  lockStatus?: DeskLockStatus
  touchMode?: DeskTouchMode
  configuredMinimumMm?: number
  configuredMaximumMm?: number
  activeMinimumMm?: number
  activeMaximumMm?: number
  presets: Partial<Record<1 | 2 | 3 | 4, number>>
  lastNotificationAt?: string
}

export type KnownDeskCommand =
  | { type: "wake" }
  | { type: "move_up" }
  | { type: "move_down" }
  | { type: "stop" }
  | { type: "save_preset"; preset: 1 | 2 }
  | { type: "recall_preset"; preset: 1 | 2 }
  | { type: "request_height_limits" }
  | { type: "request_units" }
  | { type: "move_to_height"; height: number }
  | { type: "set_units"; unit: DeskUnit }
  | { type: "set_touch_mode"; mode: DeskTouchMode }
  | { type: "set_calibration_offset"; offset: number }
  | { type: "set_maximum_height"; heightMm: number }
  | { type: "set_current_height_as_limit"; limit: HeightLimit }
  | { type: "clear_height_limit"; limit: HeightLimit }
  | { type: "reset" }

export interface CommandCapability {
  command: KnownDeskCommand["type"]
  confidence: CommandConfidence
  variants: readonly DeskVariant[]
  warning?: string
}

export interface CommandResult {
  command: KnownDeskCommand
  status: CommandResultStatus
  sentAt: string
  packet: Uint8Array
  error?: string
}

export interface NotificationPacket {
  opcode: number
  payload: Uint8Array
  checksum: number
}

export type DeskEvent =
  | { type: "connection"; connected: boolean }
  | { type: "state"; state: Readonly<DeskState> }
  | { type: "notification"; packet: NotificationPacket }
  | { type: "unknown_notification"; packet: NotificationPacket }
  | { type: "transport_error"; error: Error }

export interface UpliftTransport {
  readonly connected: boolean
  readonly profile: DeskProfile | undefined
  connect(): Promise<DeskProfile>
  disconnect(): Promise<void>
  write(packet: Uint8Array): Promise<void>
  onNotification(listener: (data: Uint8Array) => void): () => void
  onDisconnect(listener: (error?: Error) => void): () => void
}
