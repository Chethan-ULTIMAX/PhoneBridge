# PhoneBridge protocol

PhoneBridge uses two local-network phases.

## 1. Discovery

Android sends a small UDP announcement to port `38741` while the companion app is open.

Announcement format:

```text
PHONEBRIDGE/1 DISCOVER <device-id> <device-name> <tcp-port>
```

The announcement contains no pairing code, file data, or credentials.

## 2. Session

The desktop connects to the announced TCP port and performs a pairing handshake. A six-digit code displayed on the phone must be supplied by the desktop client.

**Current security status:** the current transport is local-network TCP with pairing-code authorization, but it is not encrypted. This is a development build and should not be treated as production-secure. Transport encryption and stronger device authentication are planned before production use.

Application messages are UTF-8 JSON frames preceded by a four-byte big-endian length. Large binary transfers use the same framing layer with a JSON header followed by streamed bytes. Screen frames are JSON messages containing a compressed image payload.

## Operations

Current logical operations include:

- `device.info`
- `storage.list`
- `storage.stats`
- `file.download`
- `file.upload`
- `storage.delete`
- `storage.mkdir`
- `storage.rename`
- `apps.list`
- `app.launch`
- `terminal.exec` (restricted read-only command set)
- `screen.start`
- `screen.stop`
- `input.tap`
- `input.swipe`
- `input.back`
- `input.home`
- `input.recents`
- `input.text`

Screen capture uses Android's MediaProjection permission. Input control uses Android Accessibility and requires explicit user enablement in system settings. PhoneBridge does not bypass those Android security boundaries.

All storage paths are interpreted relative to the Android storage tree selected by the user. The Android side rejects traversal outside that allowed root.

## Compatibility

The protocol is versioned so future desktop clients can negotiate capabilities instead of assuming that every phone supports every operation.

### Active local discovery

The desktop client listens on UDP `38741` and periodically sends `PHONEBRIDGE/1 PROBE` to the local IPv4 `/24` addresses. Android PhoneBridge responds directly with the normal `PHONEBRIDGE/1 DISCOVER` message containing its device ID, model, and TCP server port. This supplements broadcast discovery and supports networks where broadcast announcements do not reach the desktop, including common phone-hotspot layouts.
