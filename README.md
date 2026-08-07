# UPLIFT Desk BLE

An unofficial, safety-focused TypeScript library for controlling compatible
UPLIFT/Jiecang standing desks over Bluetooth Low Energy on Linux.

The library speaks to BlueZ through the host's `busctl`, `bluetoothctl`, and
`dbus-monitor` utilities. The bounded `bluetoothctl` process owns only its own
discovery lease. It does not access a raw HCI socket or ship a third-party
D-Bus runtime, so the Bluetooth controller remains available to normal Linux
consumers such as PipeWire and WirePlumber.

> [!WARNING]
> This project implements undocumented vendor commands that can move or
> reconfigure motorized furniture. Clear the desk, keep the physical handset
> within reach, and validate every command against your exact hardware revision.

## Installation

Releases contain an npm-compatible tarball. Pin the tarball URL and checksum in
your consuming application; this package is intentionally not published to npm.

## Example

```ts
import { BluezUpliftTransport, UpliftDeskController } from "@kylemcd/uplift-desk-ble"

const transport = new BluezUpliftTransport({ address: "F2:94:81:26:3D:5D" })
const desk = new UpliftDeskController(transport)

desk.onEvent((event) => console.log(event))
await desk.connect()
await desk.requestUnits()
await desk.requestHeightLimits()
```

See [the protocol notes](docs/protocol.md) for the observed wire format,
supported BLE profiles, and command confidence.

## Project boundaries

This repository contains only the reusable UPLIFT BLE protocol and BlueZ
transport. Home Assistant, MQTT, device assignment, and web UI concerns belong
in consuming applications.

## Acknowledgements

The packet format and command catalogue were cross-checked against the
MIT-licensed [`librick/uplift-ble`](https://github.com/librick/uplift-ble)
project and independently verified against an UPLIFT adapter exposing the FF00
service layout.

## License

MIT
