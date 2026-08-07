# UPLIFT Desk for Home Assistant

An unofficial HACS custom integration for UPLIFT and compatible Jiecang
standing desks with a Bluetooth adapter.

The integration supports two local connection methods:

- **Home Assistant Bluetooth** — the default. Home Assistant connects through
  any configured local adapter or supported Bluetooth proxy.
- **Bluetooth Broker** — optional. Use this when another service owns the BLE
  connection and exposes the broker HTTP API.

No cloud account is required.

> [!WARNING]
> Standing-desk commands can move motorized furniture. Clear the desk, keep the
> physical handset within reach, and test commands against your exact hardware
> revision. This project is unofficial and is not affiliated with UPLIFT Desk.

## Install with HACS

1. Open HACS in Home Assistant.
2. Add this repository as a custom repository with category **Integration**.
3. Install **UPLIFT Desk** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → UPLIFT Desk**.
5. Choose **Home Assistant Bluetooth** for a local adapter or Bluetooth proxy.
   Choose **Bluetooth Broker** only if you operate a compatible broker.

Home Assistant Bluetooth discovery recognizes the known `00FF`, `FE60`,
`FF00`, and `FF12` Jiecang service layouts. The selected device is validated
against its actual GATT services and characteristics before setup completes.

## Home Assistant entities

Enabled by default:

- Desk cover for stand, sit, stop, and validated position movement
- Current height
- Connection and reset-required status
- Movement and error state
- Target height, which stages a value without moving the desk
- Move-to-target, sit, stand, and stop buttons

Disabled by default:

- Fixed 500 ms jog up/down buttons
- Ten-minute release-for-phone button

Movement controls remain unavailable until required height limits and preset
values are known. The integration does not guess movement bounds.

## Connection architecture

Native Bluetooth:

```text
UPLIFT desk ← BLE → Home Assistant Bluetooth
```

Optional broker:

```text
UPLIFT desk ← BLE → Bluetooth Broker ← HTTP(S) → Home Assistant
```

Broker URLs and desk IDs are discovered or entered during setup. The
integration contains no hostnames, addresses, or credentials for a particular
installation.

## Protocol library

The repository also contains the strict TypeScript protocol package used by
compatible broker implementations. See [the protocol notes](docs/protocol.md)
for the observed packet format and supported UUID profiles.

The Linux TypeScript transport uses installed BlueZ command-line tools. It has
no `dbus-next`, Noble, or raw-HCI dependency.

## Development

```bash
npm ci
npm run check
```

Pull requests also run Home Assistant hassfest and HACS validation.

## License

MIT
