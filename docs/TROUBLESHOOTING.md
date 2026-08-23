# Troubleshooting

[English](TROUBLESHOOTING.md) | [中文](TROUBLESHOOTING.zh.md)

Error code reference and recovery runbooks for common operational issues in `matrix_e2ee`.

## Error codes

`matrix_e2ee_error` events carry a `code` field (never secrets). Common codes:

| Code | Meaning | Typical action |
|---|---|---|
| `soft_logout` | Access token invalid; same device may sign in again | Call `reauthenticate` or use the UI reauth prompt |
| `hard_logout` | Token invalid and not soft logout | Delete session + store, remove integration, add again, re-verify |
| `store_missing` | Crypto store directory missing | Treat as new device; do not reuse leftover session alone |
| `session_missing` | Session file missing on restore path | First login / re-setup with password |
| `session_corrupt` | Session file unreadable or invalid | Delete session (+ store if inconsistent), re-setup |
| `restore_failed` | Could not restore client from session/store | Check logs; often ends in re-setup |
| `password_required` | Password needed but not provided | Supply password to login / reauth |
| `login_failed` | Homeserver rejected login | Check credentials and homeserver URL |
| `device_mismatch` | Reauth would change `device_id` | Token not written; not a new-device upgrade path |
| `room_not_allowed` | `room_id` not in `allowed_rooms` | Add room or send elsewhere |
| `send_failed` | Send failed for a non-trust reason | Check connectivity and room membership |
| `unverified_device` | Encrypted send blocked: unverified/unknown devices | Complete SAS (or fingerprint) for those devices |
| `encryption_unavailable` | E2EE path not available | Check nio/store; should not happen on a healthy install |
| `device_missing` | Target device not in crypto store | Wait for device keys / start verification only for known devices |
| `fingerprint_mismatch` | Manual fingerprint did not match store | Recheck key; do not force trust |
| `invalid_transaction` | Unknown or expired SAS `transaction_id` | Start a new verification |
| `invalid_state` | Service called in an unexpected client state | Check soft-logout / connection; retry after recovery |
| `verification_timeout` | Integration 240s verification window expired | Restart SAS from Element |
| `verification_peer_denied` | Initiator not bot account and not in `verification_peer_users` | Adjust allowlist or initiate from an allowed user |
| `refresh_token_unsupported` | Server offered refresh/short-lived token | Use long-lived password login without token refresh |

## Recovery runbook

Session JSON and the crypto store stay on the Home Assistant host. They are gitignored. This is a public repository: never commit tokens, pickle keys, passwords, or store files.

Safe diagnostics (no token, pickle key, password, or message body) are available via **Download diagnostics** and the **Connection** binary sensor — see [Entities and diagnostics](USAGE.md#entities-and-diagnostics).

**Session file and crypto store must always be backed up and restored together.** The session JSON alone cannot recover Megolm history; the store alone is useless without the matching `pickle_key` in the session file. Treat a mismatched pair as a new device.

### Soft logout (`matrix_e2ee_error` code `soft_logout`)

The access token is invalid, but the homeserver still allows the same device to sign in again. The integration **keeps** `.storage/matrix_e2ee_store/` and the existing `device_id`. Send, inbound commands, SAS, and sync stay blocked until reauthentication succeeds.

At setup time a soft logout shows a **Re-authenticate** prompt on the integration (the native reauth flow). At runtime, reauthenticate via the service:

1. Call `matrix_e2ee.reauthenticate` with the bot account password (Developer Tools → Services, or an automation). Provide the password only to this service.
2. On success the session file is rewritten with a **new access token only**. `device_id` and `pickle_key` are unchanged. The crypto store is reused.
3. If the homeserver would return a different `device_id`, the new token is **not** written (`device_mismatch`). The old session remains. This is not a new-device upgrade path.

The password never appears in events, log lines, or service return values.

### Hard logout (`hard_logout`)

The token is invalid and this is **not** a soft logout. Setup **fails**. Do **not** reuse the old crypto store.

1. Revoke the old device on the homeserver if you still can.
2. Delete `<config>/.storage/matrix_e2ee_session.json` **and** `<config>/.storage/matrix_e2ee_store/`.
3. Delete the integration in **Settings → Devices & Services**, then add it again through the UI so first login creates a **new** device.
4. Run SAS again (`start_verification` / `confirm_verification`). Old history cannot be decrypted.

### Crypto store missing (`store_missing`)

Treat this as a new device. The session JSON is not enough to recover Megolm history. Delete the leftover session file, then follow the hard-logout steps (new login + SAS). Do not copy an old store onto a new device.

### Leaked keys or stolen host

1. Revoke the old Matrix device on the homeserver.
2. Destroy the local session file and crypto store (same paths as above).
3. First login creates a new device.
4. SAS-verify devices that should be trusted. Previous ciphertext is not recoverable.

### Migrating to a new Home Assistant host (legitimate move)

1. Stop Home Assistant on the old host (or disable the integration) so the bot is not connected from two places.
2. Copy **both** `<config>/.storage/matrix_e2ee_session.json` and `<config>/.storage/matrix_e2ee_store/` to the same paths on the new host. They must stay a matched pair.
3. Install the same `matrix_e2ee` version under `custom_components` on the new host and restart.
4. Re-add the integration through **Settings → Devices & Services** (the flow still asks for a password; with the session file present, the client restores the same `device_id` instead of creating a new one). If the store or session is missing or mismatched, treat it as a new device and re-verify.

### Short-lived / refresh tokens (`refresh_token_unsupported`)

This integration does not rotate refresh tokens. If login or `reauthenticate` would receive a refresh token or a short-lived access token (`expires_in_ms`), the integration refuses to persist the session. Use a long-lived access token (standard password login without token refresh).

## Related documentation

- [Usage guide](USAGE.md): services, events, automations, and diagnostic entities.
- [Device verification](DEVICE_VERIFICATION.md): step-by-step SAS and fingerprint verification.
- [Security model](../SECURITY.md): trust boundaries, storage protection, and key-compromise response.
