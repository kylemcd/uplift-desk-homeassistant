import type { DeskProfile } from "./types.js"

export const bluetoothBaseUuid = (value: number): string =>
  `${value.toString(16).padStart(8, "0")}-0000-1000-8000-00805f9b34fb`

export const DESK_PROFILES: readonly DeskProfile[] = [
  {
    variant: "jiecang_00ff",
    serviceUuid: bluetoothBaseUuid(0x00ff),
    inputCharacteristicUuid: bluetoothBaseUuid(0x01ff),
    outputCharacteristicUuid: bluetoothBaseUuid(0x02ff),
    nameCharacteristicUuid: bluetoothBaseUuid(0x36ef),
    requiresWake: true,
  },
  {
    variant: "jiecang_fe60",
    serviceUuid: bluetoothBaseUuid(0xfe60),
    inputCharacteristicUuid: bluetoothBaseUuid(0xfe61),
    outputCharacteristicUuid: bluetoothBaseUuid(0xfe62),
    nameCharacteristicUuid: bluetoothBaseUuid(0xfe63),
    requiresWake: true,
  },
  {
    variant: "jiecang_ff00",
    serviceUuid: bluetoothBaseUuid(0xff00),
    inputCharacteristicUuid: bluetoothBaseUuid(0xff01),
    outputCharacteristicUuid: bluetoothBaseUuid(0xff02),
    nameCharacteristicUuid: bluetoothBaseUuid(0xfe63),
    requiresWake: true,
  },
  {
    variant: "jiecang_ff12",
    serviceUuid: bluetoothBaseUuid(0xff12),
    inputCharacteristicUuid: bluetoothBaseUuid(0xff01),
    outputCharacteristicUuid: bluetoothBaseUuid(0xff02),
    nameCharacteristicUuid: bluetoothBaseUuid(0xff06),
    requiresWake: true,
  },
]

export function detectDeskProfile(serviceUuids: Iterable<string>): DeskProfile | undefined {
  const normalized = new Set([...serviceUuids].map((uuid) => uuid.toLowerCase()))
  return DESK_PROFILES.find((profile) => normalized.has(profile.serviceUuid))
}
