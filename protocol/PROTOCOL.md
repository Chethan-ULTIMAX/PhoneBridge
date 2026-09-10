# PhoneBridge protocol

PhoneBridge uses two local-network phases.

## 1. Discovery

Android sends a small UDP announcement to port `38741` at a short interval while the companion app is open.

Announcement format:

```text
PHONEBRIDGE/1 DISCOVER <device-id> <device-name> <tcp-port> <pairing-required>
```

The announcement contains no secret, token, file data, or personal information.

## 2. Session

The desktop connects to the announced TCP port and performs a pairing handshake. A new client receives a six-digit code displayed on the phone. After approval, both sides derive an authenticated session key from the pairing material.

Application messages are UTF-8 JSON frames preceded by a four-byte big-endian length. Binary files use the same framing layer with a message header followed by streamed bytes.

## File API

The first desktop client supports these logical operations:

- `device.info`
- `storage.list`
- `file.download`
- `file.upload`
- `file.delete`
- `file.mkdir`
- `file.rename`

All paths are interpreted relative to Android's exposed shared-storage root. The Android side rejects traversal outside its allowed root.

## Compatibility

The protocol is versioned so future desktop clients can negotiate capabilities instead of assuming that every phone supports every feature.
