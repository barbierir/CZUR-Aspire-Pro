# 📚 Book Capture (Linux V4L2 Scanner App)

A lightweight **Python + PySide6 + OpenCV** desktop application designed to turn **unsupported book scanners or generic USB cameras** into a usable document scanning workflow on Linux.

---

## 🚀 What is this?

This project provides a **complete capture → process → organize → export pipeline** for scanning books and documents using:

* 📷 USB cameras (V4L2 devices like `/dev/video*`)
* 📖 DIY book scanners
* ⚙️ unsupported hardware (e.g. CZUR-like scanners without Linux drivers)

If your scanner works as a camera but has **no official Linux software**, this tool is for you.

---

## 🎯 Key Features

### 📸 Capture

* Live camera preview (V4L2)
* Manual photo capture
* Automatic continuous capture (3s / 5s interval)
* Pause / resume / stop
* Live overlay with session info and countdown

### 📂 Session-based workflow

* Create named sessions (e.g. `history_book_ch1`)
* Automatic folder structure:

  ```
  captures/<session_name>/
    ├── originals/
    └── processed/
  ```
* Page numbering: `page_0001.jpg`, `page_0002.jpg`, ...

### 🧠 Post-processing pipeline

Optional processing per page:

* Grayscale
* Scanner effect (adaptive threshold)
* Auto document crop
* Perspective correction
* Experimental page flattening

### 🗂 Session page manager

* Browse captured pages
* Switch between:

  * Originals
  * Processed
* Static preview of selected page
* Delete last page
* Reorder pages (move up/down with safe renaming)

### 🔄 Editing tools

* Rotate pages (±90°)
* Regenerate processed images
* Regenerate last page quickly

### 🧾 PDF Export

* Export session to PDF
* Choose source:

  * Originals
  * Processed
* Automatic ordering by filename
* Robust handling (RGB conversion, errors)

### 🎛 Preset system

* Save post-processing configurations
* Load presets instantly
* Delete presets
* Persistent across sessions (`captures/presets.json`)

---

## 🧰 Use cases

This tool is especially useful for:

* 📖 DIY book scanning rigs
* 📷 Using webcams or DSLR (via capture card) as scanners
* 🧪 Reverse-engineering workflows for unsupported scanners
* 🐧 Linux users with **no official vendor software**
* 📚 Digitizing books, notes, archives

---

## 🔑 Keywords (for discoverability)

book scanner linux, document scanner linux, DIY book scanner, V4L2 scanner, USB camera scanner, CZUR alternative linux, open source book scanner, camera based scanning, document digitization linux, page capture tool, scanning workflow python

---

## ⚙️ Requirements

* Python 3.10+
* Linux (tested with V4L2 devices)
* A working camera device (e.g. `/dev/video2`)

### Python dependencies

```
PySide6>=6.7
opencv-python>=4.9
Pillow>=10.0
```

---

## ▶️ Run

```bash
pip install -r requirements.txt
python main.py
```

---

## 🧪 Quick workflow

1. Create a session (e.g. `my_book`)
2. Start capturing pages (manual or automatic)
3. Enable post-processing if needed
4. Reorder / fix pages if necessary
5. Export to PDF

---

## 🧠 Design philosophy

* Keep everything **simple and local**
* Use **filesystem as source of truth**
* Avoid hidden state or caching
* Make every operation reversible or safe
* Prefer robustness over complexity

---

## ⚠️ Notes

* This is **not OCR software** (yet)
* Works best with:

  * good lighting
  * stable camera
  * flat pages
* Experimental flattening may not work on all documents

---

## 🔮 Possible future improvements

* OCR integration (e.g. Tesseract)
* Deskew / auto-rotation
* Manual crop UI
* Multi-page batch operations
* Export to searchable PDF

---

## 🤝 Contributing

This project is intentionally simple and hackable.

Feel free to:

* open issues
* suggest improvements
* adapt it to your hardware

---

## 📄 License

MIT

---

## ❤️ Why this exists

Many affordable book scanners (like CZUR-style devices) **do not support Linux**.

This project exists to give Linux users a **practical, open, and hackable alternative** using standard camera interfaces.

If it helps you digitize your books, it has done its job 🙂
