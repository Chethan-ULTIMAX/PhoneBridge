# PhoneBridge architecture

## Connection flow

1. Android opens a local TCP server on an ephemeral port.
2. Android broadcasts a small UDP discovery packet on port 38741 while the app is open.
3. Windows listens for the packet and shows the phone automatically.
4. The user enters the six-digit pairing code displayed by Android.
5. The Android server accepts the session only after the code matches.
6. File requests are exchanged using length-prefixed JSON messages and streamed file bytes.

## Storage model

The Android app uses Android's Storage Access Framework. The user explicitly chooses the storage tree once. This avoids requesting broad legacy storage access and respects modern Android scoped-storage rules.

Paths are logical paths such as:

```text
DCIM/Camera/photo.jpg
Download/example.zip
Documents/notes.txt
```

The server resolves every path segment from the granted tree and rejects `..`, empty traversal segments, and objects outside the selected tree.

## Why screen control is separate

Android treats screen capture and remote input as privileged user-visible capabilities. A robust implementation needs MediaProjection for capture and an explicit accessibility-based input service for interaction. These permissions should be requested visibly and never bypassed. The desktop protocol is intentionally extensible so screen/control capabilities can be added without changing the file API.

## Testing checklist

- Both devices on the same Wi-Fi
- Android PhoneBridge open
- Storage tree selected
- Windows firewall allows the desktop app on the private network
- Phone appears in the desktop discovery list
- Correct pairing code connects
- Root storage lists correctly
- Double-click opens folders
- Download preserves file bytes
- Upload creates/replaces a file in the current folder
- Invalid paths are rejected
- Disconnect/reconnect works
