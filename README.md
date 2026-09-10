# PhoneBridge

PhoneBridge is a wireless bridge between an Android phone and a Windows PC. The goal is simple: open PhoneBridge on both devices, pair them on the same Wi-Fi network, and use the PC as a convenient companion for phone files, screen viewing, apps, and approved input.

## Current implementation

- Java Android companion app
- Python/Tkinter Windows desktop client
- Automatic local-network discovery with UDP
- Six-digit pairing handshake
- Android Storage Access Framework for user-selected storage
- Browse, upload, download, rename, delete, and create folders
- Device information and storage statistics
- Installed-app listing and launch requests
- Restricted phone terminal commands
- Optional screen streaming through Android MediaProjection
- Optional touch/navigation control through an explicitly enabled Accessibility Service
- GitHub Actions builds for Android APK and Windows executable

## Security status

This is a development build. The current TCP transport is **not encrypted**. Pairing with a six-digit code prevents casual unauthenticated connections, but it is not a replacement for production-grade authenticated encryption.

Before public/production use, the protocol should add encrypted transport and stronger trusted-device authentication. PhoneBridge does not attempt to bypass Android permissions, root protections, application sandboxes, or the system screen-capture consent dialog.

## Repository layout

```text
PhoneBridge/
├── android/       Android companion app
├── desktop/       Windows desktop client
├── protocol/      Wire protocol documentation
├── docs/          Architecture and security notes
└── .github/       Android and Windows build automation
```

## Building without Android Studio

The Android project is built automatically by GitHub Actions. You do not need Android Studio on your computer to obtain the debug APK.

The Windows client is also packaged automatically as `PhoneBridge.exe`, so normal use does not require VS Code or a Python development environment.

## Local development

### Android

The project can be opened in Android Studio for development, or built in CI with Gradle.

### Windows

For source development, Python 3.12+ and Pillow are used:

```powershell
cd desktop
python -m pip install -r requirements.txt
python phonebridge.py
```

For normal Windows use, prefer the packaged executable produced by GitHub Actions.

## Permissions and limitations

Screen viewing uses Android's MediaProjection permission and therefore requires the Android system consent dialog. Remote touch/navigation requires the user to explicitly enable PhoneBridge's Accessibility Service. File access is limited to the storage tree selected by the user through Android's system picker.

The terminal feature is intentionally restricted to a small set of read-only device commands; it is not an unrestricted remote shell.

## License

MIT
