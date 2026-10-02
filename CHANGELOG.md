# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.15] - 2026-10-02

### Fixed

- After a restart with a stored sync token, sends failed with `LocalProtocolError: No such room` for joined rooms that had no new events, because the incremental sync never loaded them into `nio.rooms`. Restore now runs one full-state sync from the stored token (callbacks already registered, so commands sent during downtime are still dispatched) before continuing incrementally.

### Changed

- Commands may carry one leading addressing prefix (`hass: !ping`), as chat clients add when replying to or mentioning the bot. The command word must still start with the configured prefix.

## [0.3.14] - 2026-08-26

### Added (W1N-220)

- **Verified peers** diagnostic binary sensor (`binary_sensor.*_verified_peers`): on/off state when the bot trusts at least one peer device, with `verified_peer_count` and capped `verified_peers` attributes (no secrets).
- Options Flow Configure menu and verification wizard now show current bot-side trust (count, peer list, and trust note) on init, verify wait, and successful completion.
- Fingerprint trust (`verify_device_by_fingerprint`) now notifies state listeners so diagnostic entities refresh without restart.

### Documentation

- Document the Verified peers entity in `USAGE` and point verification success to the entity and Configure trust summary in `DEVICE_VERIFICATION` (EN + zh-Hans).

## [0.3.13] - 2026-08-22

### Fixed

- Avoid blocking I/O on the event loop during config-entry restore (W1N-208): preload matrix-nio version and SAS patch imports at `nio_compat` module load, and run `restore_login` via `asyncio.to_thread`.

## [0.3.11] - 2026-08-19

### Fixed

- Restore `ruff format --check` compliance in `client.py` (drop redundant parentheses around comma-separated `except` clauses).

### Documentation

- Expand README with v0.3.10 alignment: TOC, error-code table, Connection diagnostics, URL normalization rules, automation examples.
- Add DEVICE_VERIFICATION troubleshooting for `session_corrupt` / `restore_failed`.
- Add `SECURITY.zh.md` and sync EN/ZH security and migration notes.
- Complete DEVELOPMENT test inventory and NIO upgrade checklist.
- Polish migration wording and changelog dates.

## [0.3.10] - 2026-08-19

### Documentation

- Ship bilingual EN/ZH operator and maintainer docs under `docs/`.
- Align README with released v0.3.x behavior: error-code table, Connection diagnostic entity, diagnostics fields, URL normalization rules, automation examples, recovery/migration notes.

## [0.3.9] - 2026-08-19

### Added / Changed (W1N-190)

- Single config-entry enforcement.
- Homeserver URL normalization (HTTPS-only except localhost; reject embedded credentials).
- Origin-change reconfigure isolation (quarantine old session/store).
- Verified-peer diagnostics and Connection health binary sensor.
- Numbered SAS emoji comparison in the Options Flow wizard.
- Brand assets under `custom_components/matrix_e2ee/brand/`.
- `nio_compat.py` extraction with version guard.
- CI quality gates: ruff, coverage threshold, pip-audit on runtime requirements.

## [0.3.8] - 2026-08-18

### Added

- Options Flow device-verification wizard for Element-initiated SAS with live emoji comparison.
- `m.key.verification.done` handshake completion for request-based SAS.

## [0.3.0] – [0.3.7]

Incremental SAS wizard, peer-initiated verification, and related fixes. See git history and Linear W1N-180…W1N-189.

## [0.2.0] - M5

### Added

- Config Flow UI setup, options / reconfigure / reauth flows, YAML import, and related tests.

## [0.1.x] - M1–M4

### Added

- M1: independent YAML integration, unencrypted send/commands, allowlists, mock tests.
- M2: E2EE lifecycle, encrypted text path, fail-closed unverified send/commands.
- M3: SAS services and events.
- M4: soft logout / `reauthenticate`, store-loss runbook, diagnostics foundation.

[0.3.14]: https://github.com/windyboy/ha-matrix-e2ee/releases/tag/v0.3.14
[0.3.13]: https://github.com/windyboy/ha-matrix-e2ee/releases/tag/v0.3.13
[0.3.11]: https://github.com/windyboy/ha-matrix-e2ee/releases/tag/v0.3.11
[0.3.10]: https://github.com/windyboy/ha-matrix-e2ee/releases/tag/v0.3.10
[0.3.9]: https://github.com/windyboy/ha-matrix-e2ee/releases/tag/v0.3.9
[0.3.8]: https://github.com/windyboy/ha-matrix-e2ee/releases/tag/v0.3.8
