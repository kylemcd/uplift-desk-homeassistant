import type { CommandCapability, KnownDeskCommand } from "./types.js"

const allVariants = ["jiecang_00ff", "jiecang_fe60", "jiecang_ff00", "jiecang_ff12"] as const

export const COMMAND_CAPABILITIES: readonly CommandCapability[] = [
  { command: "wake", confidence: "observed", variants: allVariants },
  { command: "move_up", confidence: "observed", variants: allVariants },
  { command: "move_down", confidence: "observed", variants: allVariants },
  { command: "stop", confidence: "observed", variants: allVariants },
  { command: "save_preset", confidence: "reference-only", variants: allVariants, warning: "Writes stored desk configuration." },
  { command: "recall_preset", confidence: "reference-only", variants: allVariants, warning: "Moves the desk immediately." },
  { command: "request_height_limits", confidence: "reference-only", variants: allVariants },
  { command: "request_units", confidence: "observed", variants: allVariants },
  { command: "move_to_height", confidence: "reference-only", variants: allVariants, warning: "Units are firmware-specific raw display units." },
  { command: "set_units", confidence: "reference-only", variants: allVariants, warning: "Changes stored desk configuration." },
  { command: "set_touch_mode", confidence: "reference-only", variants: allVariants, warning: "Changes physical handset behavior." },
  { command: "set_calibration_offset", confidence: "reference-only", variants: allVariants, warning: "May make displayed and physical height diverge." },
  { command: "set_maximum_height", confidence: "reference-only", variants: allVariants, warning: "Changes a physical safety limit." },
  { command: "set_current_height_as_limit", confidence: "reference-only", variants: allVariants, warning: "Changes a physical safety limit." },
  { command: "clear_height_limit", confidence: "reference-only", variants: allVariants, warning: "Removes a physical safety limit." },
  { command: "reset", confidence: "reference-only", variants: allVariants, warning: "May initiate controller reset behavior." },
]

export function commandToOpcode(command: KnownDeskCommand): { opcode: number; payload: Uint8Array } {
  switch (command.type) {
    case "wake": return packet(0x00)
    case "move_up": return packet(0x01)
    case "move_down": return packet(0x02)
    case "stop": return packet(0x2b)
    case "save_preset": return packet(command.preset === 1 ? 0x03 : 0x04)
    case "recall_preset": return packet(command.preset === 1 ? 0x05 : 0x06)
    case "request_height_limits": return packet(0x07)
    case "request_units": return packet(0x0e)
    case "move_to_height": return packet(0x1b, uint16(command.height, "height"))
    case "set_units": return packet(0x0e, Uint8Array.of(command.unit === "centimeters" ? 0 : 1))
    case "set_touch_mode": return packet(0x19, Uint8Array.of(command.mode === "one_touch" ? 0 : 1))
    case "set_calibration_offset": return packet(0x10, uint16(command.offset, "offset"))
    case "set_maximum_height": return packet(0x11, uint16(command.heightMm, "heightMm"))
    case "set_current_height_as_limit": return packet(command.limit === "maximum" ? 0x21 : 0x22)
    case "clear_height_limit": return packet(0x23, Uint8Array.of(command.limit === "maximum" ? 1 : 2))
    case "reset": return packet(0xfe)
  }
}

function uint16(value: number, name: string): Uint8Array {
  if (!Number.isInteger(value) || value < 0 || value > 0xffff) {
    throw new RangeError(`${name} must be an integer in [0, 65535]`)
  }
  return Uint8Array.of(value >> 8, value & 0xff)
}

function packet(opcode: number, payload: Uint8Array<ArrayBufferLike> = new Uint8Array()): { opcode: number; payload: Uint8Array<ArrayBufferLike> } {
  return { opcode, payload }
}
