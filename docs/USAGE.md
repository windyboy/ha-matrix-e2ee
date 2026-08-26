# Usage guide

[English](USAGE.md) | [中文](USAGE.zh.md)

Overview of services, events, example automations, and diagnostic entities provided by `matrix_e2ee`.

## Services, events, and automations

### Services

| Service | Fields | Notes |
|---|---|---|
| `matrix_e2ee.send_message` | `message`, `room_id` | Room must be in `allowed_rooms`. Fails closed on unverified devices in encrypted rooms. |
| `matrix_e2ee.reauthenticate` | `password` | Soft logout only. Replaces access token; keeps `device_id` and crypto store. **Admin only.** |
| `matrix_e2ee.start_verification` | `user_id`, `device_id` | Device must already be in the crypto store. Does not trust until confirm. **Admin only.** |
| `matrix_e2ee.confirm_verification` | `transaction_id` | Only step that marks a device verified. **Admin only.** |
| `matrix_e2ee.cancel_verification` | `transaction_id` | Cancels in-progress SAS. **Admin only.** |
| `matrix_e2ee.get_fingerprint` | (none) | Emits `matrix_e2ee_fingerprint` with the bot's public keys. |
| `matrix_e2ee.verify_device_by_fingerprint` | `user_id`, `device_id`, `ed25519` | One-sided local trust on exact match. **Admin only.** |

Admin-only services are enforced by Home Assistant's admin-service helper.

### Events

| Event | Payload (no secrets) |
|---|---|
| `matrix_e2ee_command` | `room_id`, `sender`, `command`, `args` only — never the raw body |
| `matrix_e2ee_error` | `code` plus non-secret context fields (see [Error codes](TROUBLESHOOTING.md#error-codes)) |
| `matrix_e2ee_verification` | `stage`, `transaction_id`, `user_id`, `device_id`; optional `emojis`, `expires_at` |
| `matrix_e2ee_message_received` | `sender`, `room_id`; optional `event_id` |
| `matrix_e2ee_verification_done` | `peer_user_id`, `peer_device_id`, `timestamp` |
| `matrix_e2ee_fingerprint` | `user_id`, `device_id`, `ed25519`, `curve25519` — public keys only |

SAS emoji comparison is available in the Options Flow wizard or, for advanced use, through the `matrix_e2ee_verification` event (`stage: sas`) in Developer Tools. Confirming is the only step that marks a device verified. Accepting an inbound SAS start is protocol continuation, not trust.

Commands fire `matrix_e2ee_command` with `room_id`, `sender`, `command`, and `args` (plus `event_id` / `thread_parent` when Matrix provides them). Accepted inbound text also fires `matrix_e2ee_message_received`; message bodies are never exposed. This integration never calls `domain.service` itself. Map commands in automations.

`notify.matrix_e2ee` is deferred. There is no `matrix_e2ee_message` event.

### Example automations

Send a message when a binary sensor trips:

```yaml
automation:
  - alias: "Notify Matrix on front door"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: "on"
    action:
      - service: matrix_e2ee.send_message
        data:
          room_id: "!yourRoomId:example.org"
          message: "Front door opened"
```

React to an inbound Matrix command (map `!ping` to a reply):

```yaml
automation:
  - alias: "Matrix !ping"
    trigger:
      - platform: event
        event_type: matrix_e2ee_command
        event_data:
          command: ping
    action:
      - service: matrix_e2ee.send_message
        data:
          room_id: "{{ trigger.event.data.room_id }}"
          message: "pong"
```

Reauthenticate after soft logout (admin only; prefer the UI reauth prompt when available):

```yaml
automation:
  - alias: "Matrix soft-logout reauth"
    trigger:
      - platform: event
        event_type: matrix_e2ee_error
        event_data:
          code: soft_logout
    action:
      - service: matrix_e2ee.reauthenticate
        data:
          password: !secret matrix_bot_password
```

## Entities and diagnostics

### Connection binary sensor

The integration exposes a diagnostic connectivity entity:

- **Entity**: `binary_sensor.*_connection` (name: **Connection**)
- **Device class**: connectivity
- **Category**: diagnostic
- **On**: bot is connected and not soft-logged-out
- **Attributes** (no secrets): `soft_logged_out`, `device_id`, `known_device_count`, `verified_peer_count`, `verified_peers` (up to 10 `{user_id, device_id}` pairs; peer devices only, never the bot itself)

### Verified peers binary sensor

The integration also exposes a diagnostic trust indicator:

- **Entity**: `binary_sensor.*_verified_peers` (name: **Verified peers**)
- **Category**: diagnostic
- **On**: the bot trusts at least one peer Matrix device (`verified_peer_count > 0`)
- **Attributes** (no secrets): `verified_peer_count`, `verified_peers` (same capped peer list as above)

The Connection entity behavior is unchanged: it still reports connectivity on/off and keeps the verified-peer attributes from W1N-194.

### Bot activity event

`event.*_bot_activity` records the latest accepted activity with event types
`message`, `command`, and `verification_done`. It shares the bot device with
the Connection entity and is push-driven; it exposes no message body or key
material.

### Config Entry diagnostics

**Settings → Devices & Services → Matrix E2EE → ⋮ → Download diagnostics** returns a redacted snapshot:

| Field | Meaning |
|---|---|
| `integration_version` | Version from `manifest.json` |
| `nio_version` | Installed `matrix-nio` version (if importable) |
| `client.user_id` | Bot Matrix user ID |
| `client.device_id` | Bot device ID |
| `client.session_present` | Session file restored |
| `client.store_present` | Crypto store directory present |
| `client.soft_logged_out` | Soft-logout latch |
| `client.encryption_enabled` | Always `true` for this integration |
| `client.store_sync_tokens` | Always `true` for this integration |
| `client.known_device_count` | Devices in the bot's device store |
| `client.verified_peer_count` | Devices this bot marked verified |

Never includes access tokens, pickle keys, passwords, message bodies, or crypto material.

## Related documentation

- [Device verification](DEVICE_VERIFICATION.md): step-by-step SAS and fingerprint verification.
- [Troubleshooting](TROUBLESHOOTING.md): error codes, recovery runbooks, and disaster recovery.
- [Security model](../SECURITY.md): trust boundaries, storage protection, and key-compromise response.
