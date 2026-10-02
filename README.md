# matrix_e2ee

Home Assistant **custom** integration that runs a dedicated Matrix bot with a persistent end-to-end encryption (E2EE) device identity.

- Unique domain: `matrix_e2ee`
- Does **not** override Home Assistant’s built-in `matrix` integration
- Python, `matrix-nio[e2e]==0.26.0` with its E2EE extras (`vodozemac`, `peewee`, `cachetools`, `atomicwrites`) declared explicitly in `manifest.json`
- Config Flow (UI) setup; not in HACS

## Table of contents

- [Documentation](#documentation)
- [Installation](#installation)
- [Security warning](#security-warning)
- [Configuration (UI)](#configuration-ui)
- [Device verification](#device-verification)
- [Roadmap](#roadmap)
- [License](#license)

## Documentation

| Document | Description |
|---|---|
| [Usage guide](docs/USAGE.md) ([中文](docs/USAGE.zh.md)) | Services, events, automations, and diagnostic entities |
| [Device verification](docs/DEVICE_VERIFICATION.md) ([中文](docs/DEVICE_VERIFICATION.zh.md)) | Step-by-step SAS and fingerprint verification walkthrough |
| [Troubleshooting](docs/TROUBLESHOOTING.md) ([中文](docs/TROUBLESHOOTING.zh.md)) | Error codes, recovery runbooks, and storage migration |
| [Security model](SECURITY.md) ([中文](SECURITY.zh.md)) | Trust boundaries, storage protection, and compromise response |
| [SAS architecture](docs/SAS_ARCHITECTURE.md) ([中文](docs/SAS_ARCHITECTURE.zh.md)) | SAS protocol flow, trust rules, and component boundaries |
| [matrix-nio compatibility](docs/NIO_COMPAT.md) ([中文](docs/NIO_COMPAT.zh.md)) | Runtime compatibility fixes and upgrade checklist |
| [Development notes](docs/DEVELOPMENT.md) ([中文](docs/DEVELOPMENT.zh.md)) | Environment setup, testing, CI, and local install |
| [Changelog](CHANGELOG.md) | Release history |
Current release: **v0.3.15** (see `custom_components/matrix_e2ee/manifest.json`).

## Installation

This is a **manual** custom integration (not in HACS). It is configured through Home Assistant's Config Flow (UI), not YAML.

Use a dedicated **non-admin** Matrix bot account. Do not run Home Assistant’s built-in `matrix` integration and `matrix_e2ee` on the same bot account. Read the [security warning](#security-warning) before enabling it.

`<config>` is the Home Assistant configuration directory (`/config` on Home Assistant OS / Container).

### 1. Copy the integration

Copy only the `matrix_e2ee` package into `custom_components`. The GitHub repository root is not that folder — do not install the whole repo tree (docs/, tests/, etc.) under `custom_components`.

**From a release archive** (recommended):

1. Download the source zip of the latest release: https://github.com/windyboy/ha-matrix-e2ee/releases
2. Extract it, then copy `custom_components/matrix_e2ee` to the HA config directory:

```bash
mkdir -p /config/custom_components
cp -a custom_components/matrix_e2ee /config/custom_components/matrix_e2ee
```

**From git** (replace `v0.3.15` with the [release tag](https://github.com/windyboy/ha-matrix-e2ee/releases) you want):

```bash
git clone --depth 1 --branch v0.3.11 https://github.com/windyboy/ha-matrix-e2ee.git /tmp/ha-matrix-e2ee
mkdir -p /config/custom_components
cp -a /tmp/ha-matrix-e2ee/custom_components/matrix_e2ee /config/custom_components/matrix_e2ee
```

The integration folder should be located at `<config>/custom_components/matrix_e2ee/`.

### 2. Add the integration in the UI

1. Restart Home Assistant once after copying the files (so the integration is discovered).
2. **Settings → Devices & Services → Add Integration → Matrix E2EE**.
3. Enter the **homeserver URL**, the bot **username**, and the **password**. The password is used only to log in and test the connection; it is never stored.
4. On first load Home Assistant installs `matrix-nio[e2e]` and its E2EE dependencies from `manifest.json`. That can take a minute; if setup fails on the first attempt after a fresh copy, wait for the dependency install to finish and retry or restart once more.
5. On first login the integration creates the bot device and writes its crypto store. Later restarts restore the same device without any password.

The password is required only on the very first login, when no session file exists yet. It is not saved to the config entry.

**One bot per Home Assistant.** This integration supports a single config entry (`"single_config_entry": true`). The session file and crypto store are global to the integration, so a second entry would silently rebind them to a different account. Adding the integration a second time — even with a different username — is rejected with "Already configured".

### 3. Migrating from YAML (legacy)

If a legacy `matrix_e2ee:` block is present in `configuration.yaml`, Home Assistant imports it into a config entry on startup and the YAML block can then be removed.
### 4. Dependencies

On first load, Home Assistant installs `matrix-nio[e2e]==0.26.0` and its explicit E2EE dependencies (`vodozemac`, `peewee`, `cachetools`, `atomicwrites`) from `manifest.json`. The E2EE deps are listed explicitly because Home Assistant's requirement manager drops the `[e2e]` extra and would otherwise skip them. If any requirement fails to install, setup fails closed. Do not work around it with OS-level `pip` on Home Assistant OS.

After a successful first setup, HA writes:

- `<config>/.storage/matrix_e2ee_session.json`
- `<config>/.storage/matrix_e2ee_store/`

Those files must stay on the same persistent volume as Home Assistant. They are gitignored and must never be committed.

If setup fails, check `matrix_e2ee_error` events and the Home Assistant log (tokens, pickle keys, and passwords must not appear there). Soft logout recovery is in [Troubleshooting](docs/TROUBLESHOOTING.md) ([中文](docs/TROUBLESHOOTING.zh.md)).

## Security warning

**Home Assistant is an E2EE endpoint.** If this integration is enabled, this host decrypts Matrix text and holds device keys. Compromise of the Home Assistant host, backups, logs, or the crypto store is compromise of the bot device.

Protect, back up, and revoke together:

- `.storage/matrix_e2ee_session.json` (`user_id`, `device_id`, `access_token`, `pickle_key`)
- `.storage/matrix_e2ee_store/` (Olm/Megolm, device trust, sync token)

Core security principles:

- Dedicated **non-admin** Matrix bot account only
- Never use Synapse admin login tokens for E2EE
- Never set `ignore_unverified_devices=True` by default
- Never auto-trust unknown devices
- Never fall back to plaintext when an encrypted send fails (unverified/unknown devices block the send; it is never downgraded to plaintext). Unencrypted rooms on the allowlist are still sent unencrypted.
- Never process commands from unverified devices
- Never log access tokens, pickle keys, message bodies, or crypto-store secrets
- Crypto store loss is a **new device**. Old history is not recoverable
- Do not run built-in `matrix` and `matrix_e2ee` on the same bot account

Device verification has been manually confirmed on a real deployment (Element SAS with the `m.key.verification.done` handshake). An automated end-to-end SAS test against a real homeserver is still backlog (W1N-171).

## Configuration (UI)

All configuration is done through the Config Flow:

- **homeserver** and **username** are entered when the integration is added. The username is read-only afterwards; the homeserver can be changed via **Reconfigure**. Changing to a **different server origin** (scheme, host, or port) quarantines the old session file and crypto store and logs in as a fresh device — the old token is never sent to the new origin, and you must re-enter the bot password and re-run device verification. Changing only the trailing slash or path keeps the same device.
- **allowed_rooms**, **allowed_users**, **verification_peer_users**, and **command_prefix** are edited via **Configure** (Options). Changing them reloads the integration and reuses the existing crypto store.

### Homeserver URL rules

The integration normalizes and validates the homeserver URL before login:

- Bare hosts default to `https://`.
- **HTTPS is required** except for localhost / loopback (`localhost`, `127.0.0.1`, `::1`).
- Usernames or passwords embedded in the URL are rejected.
- Trailing slashes, paths, and default ports are stripped; only the origin (`scheme://host[:port]`) is kept.

Invalid input surfaces as Config Flow errors such as `homeserver_invalid`, `homeserver_http_not_allowed`, or `homeserver_credentials`.

### Access-control semantics

| Option | Empty value means |
|---|---|
| `allowed_rooms` | No send and no inbound commands |
| `allowed_users` | No inbound commands; send to allowed rooms is still permitted |
| `verification_peer_users` | No inbound SAS from other accounts (only the bot's own account may initiate) |

The old YAML block is no longer required. If a `matrix_e2ee:` block remains in `configuration.yaml`, it is imported into a config entry on startup (see [Migrating from YAML](#3-migrating-from-yaml-legacy)).

## Device verification

Use **Settings → Devices & Services → Matrix E2EE → Configure → Verify device** and initiate verification for `Home Assistant matrix_e2ee` from Element. Compare every emoji and confirm only when both sides match. Devices are never trusted automatically, even when they belong to the same account.

See [Device verification](docs/DEVICE_VERIFICATION.md) ([中文](docs/DEVICE_VERIFICATION.zh.md)) for the complete walkthrough, [Security](SECURITY.md) for the trust model, and [SAS architecture](docs/SAS_ARCHITECTURE.md) for implementation details.

## Roadmap

| Milestone | Intent | Status |
|---|---|---|
| **M1** | Independent YAML integration, unencrypted-room send/commands, allowlist, startup/shutdown, mock tests | Released ([#2](https://github.com/windyboy/ha-matrix-e2ee/pull/2)) |
| **M2** | E2EE lifecycle: first login writes a full crypto device, restart restores the same device, encrypted text path, fail-closed unverified send/commands | Released ([#4](https://github.com/windyboy/ha-matrix-e2ee/pull/4)) |
| **M3** | SAS services/events (`start_verification`, `confirm_verification`, `cancel_verification`) so encrypted send/commands can succeed with verified devices | Released ([#5](https://github.com/windyboy/ha-matrix-e2ee/pull/5)) |
| **M4** | Soft logout / `reauthenticate`, store-loss runbook, diagnostics | Released ([#6](https://github.com/windyboy/ha-matrix-e2ee/pull/6)) |
| **M5** | Config Flow migration: UI setup, options / reconfigure / reauth flows, YAML import, tests | Released (v0.2.0) |
| **v0.3** | Options Flow device-verification wizard for Element-initiated SAS with live emoji comparison, `m.key.verification.done` handshake | Released (v0.3.8) |
| **v0.3.x** | UI polish + maintenance: single-config-entry enforcement, homeserver URL normalization (HTTPS-only, credential rejection), origin-change reconfigure isolation, verified-peer diagnostics, Connection binary sensor, numbered SAS emoji compare, brand assets, `nio_compat.py` extraction with version guard, CI quality gates (ruff + coverage + audit), docs alignment | Released (v0.3.10) |

M1 acceptance uses unencrypted test rooms. The first successful login still creates a full E2EE-capable Matrix device so M2 does not “upgrade” a non-crypto device.

M3 adds SAS so an already-known device can become `verified=True`. Tests mock nio; they do not use a live Element session. SAS has been manually confirmed on a real deployment; automated end-to-end SAS testing is still backlog (W1N-171).

## License

Apache License 2.0. Copyright 2026 windyboy.
