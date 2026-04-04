# 📚 Book Capture (Linux V4L2 Scanner App)

A practical **Linux book scanning app** for unsupported scanners and USB cameras: capture pages, process images, organize sessions, and export PDFs.

## Who is this for?

This project is for Linux users who want reliable **document digitization on Linux** when vendor software is missing, unavailable, or Windows-only.

Typical users include:
- People with a **CZUR alternative Linux** need (or any CZUR-like device without official Linux software).
- Users with a **camera document scanner** setup (USB document camera, webcam, DSLR via capture card).
- Makers building a **DIY book scanner Linux** rig.
- Archivists/students/researchers doing **book scanning software Linux** workflows at home or in labs.

## Why this project exists

Many affordable scanners and book scanners are tied to vendor apps that do not support Linux. This repository exists to provide a simple, open, and hackable workflow for **unsupported scanner Linux** scenarios, as long as the device is exposed as a standard camera (V4L2/UVC).

In short: if your hardware works as `/dev/video*`, this app helps you turn it into a practical scanner workflow.

## Supported use cases

- **Linux book scanner** workflow with overhead capture.
- **USB camera scanning** for documents and books.
- **V4L2 document scanner** setup using generic UVC devices.
- Session-based capture for multi-page books.
- Optional post-processing (grayscale, threshold/scanner effect, crop/perspective tools).
- Page ordering, quick fixes, and PDF export.

## Limitations

- No OCR/searchable PDF in the current version.
- Quality depends on lighting, camera alignment, and page stability.
- Some advanced “page flattening” situations may require manual experimentation.
- This is not a hardware driver package; it depends on Linux camera support (V4L2/UVC).

## Installation

### Option A — Run from source

```bash
pip install -r requirements.txt
python main.py
```

### Option B — Install as a user desktop app

```bash
chmod +x install.sh
./install.sh
```

What `install.sh` does:
- Installs app files in `~/.local/share/book-capture/`
- Creates launcher `~/.local/bin/book-capture`
- Installs desktop entry in `~/.local/share/applications/`
- Uses `assets/icon.png` if available

## Launching

After install, launch with either:

- Application menu entry: **Book Capture**
- Terminal command:

```bash
book-capture
```

If you run from source, use:

```bash
python main.py
```

## Uninstall

```bash
chmod +x uninstall.sh
./uninstall.sh
```

This removes user-level app files, launcher, desktop entry, and icon cache entry created by install.

## Typical workflow

1. Connect your camera/scanner and confirm Linux sees it as a V4L2 device (`/dev/video*`).
2. Start Book Capture and create a session.
3. Capture pages manually or with timed auto-capture.
4. Apply processing options when useful.
5. Reorder/fix pages in the session browser.
6. Export the session to PDF.

## Keywords / discoverability

This project is intentionally described with terms users search for, including:

- linux book scanner
- camera document scanner
- V4L2 document scanner
- CZUR alternative Linux
- unsupported scanner Linux
- USB camera scanning
- DIY book scanner Linux
- document digitization Linux
- book scanning software Linux

## Related hardware / equivalent devices

This app may be useful if you own or use:

- CZUR-like scanners
- USB document cameras
- Overhead book scanners
- Unsupported vendor-specific scanners that still expose a V4L2/UVC camera

If the device appears as a standard Linux video capture source, this project can often provide a workable scanning pipeline.

## Screenshots

> Placeholder images — add screenshots as files become available.

![Live capture view](docs/screenshot-live.png)
![Session browser](docs/screenshot-browser.png)
![Post-processing and export](docs/screenshot-processing.png)

## Repository structure

```text
.
├── main.py
├── install.sh
├── uninstall.sh
├── desktop/
│   └── book-capture.desktop
├── assets/
│   ├── icon.png                  # app icon used by installer (recommended)
│   └── icon-placeholder.txt
└── docs/
    └── README.md                 # screenshots and documentation assets
```

## Suggested GitHub topics

- linux
- scanner
- book-scanner
- document-scanner
- v4l2
- opencv
- pyside6
- digitization
- pdf
- czur

## License

MIT
