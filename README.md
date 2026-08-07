# UPLIFT Desk for Home Assistant

A HACS custom integration for controlling an UPLIFT/Jiecang standing desk
through a network Bluetooth Broker.

The integration creates native Home Assistant entities while the broker remains
the sole owner of the physical BLE session. This is intended for installations
where the Bluetooth radio is attached to another Linux host or VM and is shared
with Bluetooth audio.

> [!WARNING]
> Standing-desk commands can move or reconfigure motorized furniture. Clear the
> desk, keep the physical handset within reach, and qualify commands against
> your exact hardware revision. Calibration, reset, preset writes, and limit
> changes remain in the broker's confirmation UI and are not exposed directly
> to Home Assistant.

## Install with HACS

1. Open HACS in Home Assistant.
2. Add `https://github.com/kylemcd/uplift-desk-homeassistant` as a custom
   repository with category **Integration**.
3. Install **UPLIFT Desk** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → UPLIFT Desk**.
5. Enter the Tailnet URL of the broker. The default is
   `https://bluetooth.kpm.house`.

The config flow validates the broker and uses the desk's stable Bluetooth MAC
address as the config-entry identity.

## Home Assistant entities

Enabled by default:

- Desk cover: stand, sit, stop, and validated position movement
- Current height
- Connection and reset-required status
- Movement and error state
- Target height, which stages a value without moving the desk
- Move to target, sit, stand, and stop buttons

Disabled by default:

- Fixed 500 ms jog up/down buttons
- Ten-minute release-for-phone button

Cover and target controls become unavailable when the broker does not know the
desk's effective limits or mapped preset heights. The integration never guesses
movement bounds.

## Architecture

```text
UPLIFT desk ← BLE → BlueZ/Bluetooth Broker ← HTTPS/Tailnet → Home Assistant
                         ↕
                 PipeWire / Bluetooth audio
```

The custom integration contains no Bluetooth stack and cannot claim a USB
radio. The private broker validates GATT profiles, serializes writes, prioritizes
stop, enforces limits, and implements confirmation workflows.

## Protocol library

The repository also retains the strict TypeScript protocol package used by the
broker. Release `v0.1.0` contains the immutable
`@kylemcd/uplift-desk-ble` tarball. See [the protocol notes](docs/protocol.md)
for the observed packet format and FF00 hardware fingerprint.

The Linux transport uses the installed `busctl`, `bluetoothctl`, and
`dbus-monitor` tools. It has no `dbus-next`, Noble, or raw-HCI dependency.

## Development

```bash
npm ci
npm run check
```

Pull requests also run Home Assistant hassfest and HACS validation.

## License

MIT
