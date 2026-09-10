# PhoneBridge

PhoneBridge is a privacy-first wireless bridge between an Android phone and a Windows PC. The project is designed around a simple experience: install the Android app, run the desktop client, approve pairing, and manage the phone over the local network without a USB cable.

## Current foundation

- Android companion application in Kotlin
- Windows desktop client in Python using only the standard library
- Local-network device discovery with UDP
- Authenticated pairing using a short numeric code
- Encrypted application traffic using TLS after pairing
- Phone storage browsing and file transfer
- Device information and connection status
- Clean protocol shared by the two clients
- GitHub Actions checks/build entry points

## Security model

PhoneBridge is intended for trusted local networks. The Android app does not expose an unauthenticated control endpoint. A desktop client must first pair using a code shown by the phone. A per-device key is then used to authenticate subsequent sessions. File operations are restricted to Android's user-accessible storage APIs.

The project intentionally does **not** attempt to bypass Android security boundaries, root protections, or application sandboxing.

## Repository layout

```text
PhoneBridge/
├── android/       Android companion app
├── desktop/       Windows desktop client
├── protocol/      Wire protocol documentation
├── docs/          Architecture and security notes
└── .github/       Automation
```

## Development

### Android

Open `android/` in Android Studio and let Gradle sync. The project targets modern Android SDKs and uses Kotlin.

### Windows

Python 3.11+ is recommended:

```powershell
cd desktop
python phonebridge.py
```

The desktop client uses Tkinter, so there is no third-party Python dependency for the initial client.

## Important limitation

Android does not permit a normal application to silently obtain unrestricted control over another application or protected system directories. Screen capture and interactive control require explicit Android user permissions and are therefore designed as opt-in capabilities rather than hidden access.

## License

MIT
