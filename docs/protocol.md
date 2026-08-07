# UPLIFT/Jiecang BLE protocol notes

This is an unofficial description of an undocumented protocol. Commands may
behave differently across controller firmware and desk brands that reuse
Jiecang hardware.

The Linux transport invokes systemd's `busctl` for BlueZ method calls,
`bluetoothctl` for a bounded discovery lease, and `dbus-monitor` for
characteristic property-change signals. All three communicate through the
system D-Bus; none claims a raw Bluetooth HCI socket. No JavaScript D-Bus
binding is included as a runtime dependency.

## Observed hardware

One observed adapter advertises UUID `00FF` but, after connection, exposes
service `FF00`, input characteristic `FF01`, and notification characteristic `FF02`.
Profile detection therefore validates the resolved GATT database instead of
trusting advertisements alone.

## Frames

Commands use `F1 F1 OPCODE LENGTH PAYLOAD CHECKSUM 7E`. Notifications use the
same structure with header `F2 F2`. The checksum is the low byte of the opcode,
payload length, and every payload byte added together.

## Known profiles

| Variant | Service | Input | Output | Name |
| --- | --- | --- | --- | --- |
| 00FF | 00FF | 01FF | 02FF | 36EF |
| FE60 | FE60 | FE61 | FE62 | FE63 |
| FF00 | FF00 | FF01 | FF02 | FE63 |
| FF12 | FF12 | FF01 | FF02 | FF06 |

All values are expanded to Bluetooth's standard 128-bit base UUID in code.

## Commands

| Opcode | Operation | Confidence on FF00 |
| --- | --- | --- |
| `00` | Wake | Observed |
| `01` / `02` | Move up / down | Reference-only |
| `03` / `04` | Save presets 1 / 2 | Reference-only |
| `05` / `06` | Recall presets 1 / 2 | Reference-only |
| `07` | Request height limits | Reference-only |
| `0E` | Request or set units | Reference-only |
| `10` | Set calibration offset | Reference-only; hazardous |
| `11` | Set maximum height | Reference-only; hazardous |
| `19` | Set touch mode | Reference-only |
| `1B` | Move to height | Reference-only; moves immediately |
| `21` / `22` | Set current height as maximum / minimum | Reference-only; hazardous |
| `23` | Clear maximum or minimum | Reference-only; hazardous |
| `2B` | Stop | Reference-only |
| `FE` | Reset | Reference-only; hazardous |

The package exposes these as typed methods. It intentionally provides no raw
opcode API.

## Notifications

Known notifications report current height (`01`), error (`02`), reset-required
(`04`), configured limits (`07`), units (`0E`), touch mode (`19`), lock state
(`1F`), active limits (`21`/`22`), and presets 1–4 (`25`–`28`). Height is a
big-endian integer in tenths of the configured display unit; limits are
big-endian millimeters. Preset units are firmware-dependent and remain raw.
