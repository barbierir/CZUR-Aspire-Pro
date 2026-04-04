import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BookCaptureApp(QWidget):
    """Applicazione per anteprima V4L2, scatto singolo e acquisizione continua."""

    CONTINUOUS_STOPPED = "stopped"
    CONTINUOUS_RUNNING = "running"
    CONTINUOUS_PAUSED = "paused"

    def __init__(self, device_path: str = "/dev/video2") -> None:
        super().__init__()
        self.device_path = device_path
        self.capture_dir = Path("captures")
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir = self.capture_dir / "processed"
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.cap: cv2.VideoCapture | None = None
        self.last_frame = None

        self.continuous_state = self.CONTINUOUS_STOPPED
        self.continuous_interval_ms = 3000
        self.next_capture_deadline: float | None = None
        self.paused_remaining_ms: int | None = None
        self.session_capture_count = 0

        self._build_ui()
        self._init_camera()

        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.update_frame)
        self.preview_timer.start(30)

        self.continuous_timer = QTimer(self)
        self.continuous_timer.timeout.connect(self._do_automatic_capture)
        self.continuous_timer.setSingleShot(False)

        self._update_session_status_label()
        self._update_session_count_label()
        self._refresh_session_info_labels()
        self._update_continuous_buttons()

    def _build_ui(self) -> None:
        self.setWindowTitle("Book Capture")
        self.resize(980, 680)

        self.preview_label = QLabel("Anteprima non disponibile")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(800, 450)
        self.preview_label.setStyleSheet("background-color: #111; color: #ddd; border: 1px solid #444;")

        self.session_status_label = QLabel("Sessione: ferma")
        self.session_count_label = QLabel("Scatti sessione: 0")
        self.status_label = QLabel("Stato: inizializzazione...")

        self.capture_button = QPushButton("Scatta foto")
        self.capture_button.clicked.connect(self.capture_photo)

        self.start_continuous_button = QPushButton("Avvia acquisizione continua")
        self.start_continuous_button.clicked.connect(self.start_continuous_capture)

        self.pause_button = QPushButton("Pausa")
        self.pause_button.clicked.connect(self.pause_continuous_capture)

        self.resume_button = QPushButton("Riprendi")
        self.resume_button.clicked.connect(self.resume_continuous_capture)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_continuous_capture)

        self.interval_label = QLabel("Intervallo:")
        self.interval_selector = QComboBox()
        self.interval_selector.addItem("3 secondi", userData=3000)
        self.interval_selector.addItem("5 secondi", userData=5000)

        self.post_process_group = QGroupBox("Post-processing")
        self.save_processed_checkbox = QCheckBox("Salva anche versione elaborata")
        self.grayscale_checkbox = QCheckBox("Scala di grigi")
        self.scanner_checkbox = QCheckBox("Effetto scanner")
        self.doc_crop_checkbox = QCheckBox("Auto-crop documento")
        self.perspective_checkbox = QCheckBox("Correzione prospettiva")

        self.save_processed_checkbox.toggled.connect(self._on_save_processed_toggled)

        pp_layout = QVBoxLayout()
        pp_layout.addWidget(self.save_processed_checkbox)
        pp_layout.addWidget(self.grayscale_checkbox)
        pp_layout.addWidget(self.scanner_checkbox)
        pp_layout.addWidget(self.doc_crop_checkbox)
        pp_layout.addWidget(self.perspective_checkbox)
        self.post_process_group.setLayout(pp_layout)

        self.exit_button = QPushButton("Esci")
        self.exit_button.clicked.connect(self.close)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.capture_button)
        button_layout.addWidget(self.start_continuous_button)
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.resume_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addStretch()
        button_layout.addWidget(self.interval_label)
        button_layout.addWidget(self.interval_selector)
        button_layout.addWidget(self.exit_button)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.preview_label)
        main_layout.addWidget(self.session_status_label)
        main_layout.addWidget(self.session_count_label)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.post_process_group)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

        self._on_save_processed_toggled(False)

    def _on_save_processed_toggled(self, enabled: bool) -> None:
        self.grayscale_checkbox.setEnabled(enabled)
        self.scanner_checkbox.setEnabled(enabled)
        self.doc_crop_checkbox.setEnabled(enabled)
        self.perspective_checkbox.setEnabled(enabled)

    def _init_camera(self) -> None:
        self.cap = cv2.VideoCapture(self.device_path, cv2.CAP_V4L2)

        if not self.cap or not self.cap.isOpened():
            self.status_label.setText(f"Errore: impossibile aprire {self.device_path}")
            self.capture_button.setEnabled(False)
            self.start_continuous_button.setEnabled(False)
            return

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        self.status_label.setText(f"Camera aperta: {self.device_path}")
        self.capture_button.setEnabled(True)
        self.start_continuous_button.setEnabled(True)

    def _selected_interval_ms(self) -> int:
        value = self.interval_selector.currentData()
        return int(value) if value is not None else 3000

    def _update_continuous_buttons(self) -> None:
        if self.continuous_state == self.CONTINUOUS_RUNNING:
            self.start_continuous_button.setEnabled(False)
            self.pause_button.setEnabled(True)
            self.resume_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.interval_selector.setEnabled(False)
        elif self.continuous_state == self.CONTINUOUS_PAUSED:
            self.start_continuous_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.interval_selector.setEnabled(False)
        else:
            camera_available = bool(self.cap and self.cap.isOpened())
            self.start_continuous_button.setEnabled(camera_available)
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.interval_selector.setEnabled(True)

    def _update_session_status_label(self) -> None:
        mapping = {
            self.CONTINUOUS_STOPPED: "Sessione: ferma",
            self.CONTINUOUS_RUNNING: "Sessione: attiva",
            self.CONTINUOUS_PAUSED: "Sessione: in pausa",
        }
        self.session_status_label.setText(mapping.get(self.continuous_state, "Sessione: sconosciuta"))

    def _update_session_count_label(self) -> None:
        self.session_count_label.setText(f"Scatti sessione: {self.session_capture_count}")

    def _refresh_session_info_labels(self) -> None:
        self._update_session_status_label()

        if self.continuous_state == self.CONTINUOUS_RUNNING:
            remaining_s = self._countdown_remaining_seconds()
            self.session_status_label.setText(f"Sessione: attiva (prossimo scatto tra {remaining_s:.1f}s)")
        elif self.continuous_state == self.CONTINUOUS_PAUSED:
            remaining_s = self._countdown_remaining_seconds()
            self.session_status_label.setText(f"Sessione: in pausa (countdown bloccato a {remaining_s:.1f}s)")

    def _reset_continuous_session(self) -> None:
        self.session_capture_count = 0
        self.paused_remaining_ms = None
        self.next_capture_deadline = None
        self._update_session_count_label()

    def _schedule_next_deadline_from_now(self) -> None:
        self.next_capture_deadline = time.monotonic() + (self.continuous_interval_ms / 1000.0)

    def _countdown_remaining_seconds(self) -> float:
        if self.continuous_state == self.CONTINUOUS_RUNNING and self.next_capture_deadline is not None:
            return max(0.0, self.next_capture_deadline - time.monotonic())

        if self.continuous_state == self.CONTINUOUS_PAUSED and self.paused_remaining_ms is not None:
            return max(0.0, self.paused_remaining_ms / 1000.0)

        return 0.0

    def _register_automatic_capture_success(self) -> None:
        self.session_capture_count += 1
        self._update_session_count_label()

    def _build_overlay_lines(self) -> list[str]:
        overlay_state = {
            self.CONTINUOUS_STOPPED: "FERMA",
            self.CONTINUOUS_RUNNING: "ATTIVA",
            self.CONTINUOUS_PAUSED: "PAUSA",
        }.get(self.continuous_state, "SCONOSCIUTA")

        lines = [
            f"Device: {self.device_path}",
            f"Sessione: {overlay_state}",
            f"Scatti sessione: {self.session_capture_count}",
        ]

        if self.continuous_state == self.CONTINUOUS_RUNNING:
            lines.append(f"Prossimo scatto: {self._countdown_remaining_seconds():.1f}s")
        elif self.continuous_state == self.CONTINUOUS_PAUSED:
            lines.append(f"Countdown in pausa: {self._countdown_remaining_seconds():.1f}s")

        return lines

    def _build_preview_with_overlay(self, frame):
        overlay_frame = frame.copy()
        overlay_lines = self._build_overlay_lines()

        margin_x = 12
        margin_y = 12
        line_height = 24
        width = 470
        height = margin_y * 2 + line_height * len(overlay_lines)

        dark_box = overlay_frame.copy()
        cv2.rectangle(dark_box, (8, 8), (8 + width, 8 + height), (20, 20, 20), thickness=-1)
        cv2.addWeighted(dark_box, 0.55, overlay_frame, 0.45, 0, overlay_frame)

        y = 8 + margin_y + 12
        for line in overlay_lines:
            cv2.putText(
                overlay_frame,
                line,
                (8 + margin_x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (240, 240, 240),
                1,
                cv2.LINE_AA,
            )
            y += line_height

        return overlay_frame

    def update_frame(self) -> None:
        self._refresh_session_info_labels()

        if not self.cap or not self.cap.isOpened():
            return

        ok, frame = self.cap.read()
        if not ok or frame is None:
            self.status_label.setText("Errore: lettura frame non riuscita")
            return

        self.last_frame = frame
        preview_frame = self._build_preview_with_overlay(frame)

        frame_rgb = cv2.cvtColor(preview_frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w

        image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image)

        scaled = pixmap.scaled(
            self.preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    def _next_capture_path(self) -> Path:
        existing = sorted(self.capture_dir.glob("page_*.jpg"))
        if not existing:
            next_index = 1
        else:
            last_name = existing[-1].stem
            try:
                next_index = int(last_name.split("_")[-1]) + 1
            except ValueError:
                next_index = len(existing) + 1

        return self.capture_dir / f"page_{next_index:04d}.jpg"

    def _save_original_frame(self, frame, source: str, save_path: Path) -> bool:
        success = cv2.imwrite(str(save_path), frame)
        if success:
            self.status_label.setText(f"Foto salvata ({source}): {save_path}")
            return True
        self.status_label.setText(f"Errore: salvataggio foto {source} non riuscito")
        return False

    @staticmethod
    def _ordered_quad_points(points: np.ndarray) -> np.ndarray:
        pts = points.reshape(4, 2).astype("float32")
        sums = pts.sum(axis=1)
        diffs = pts[:, 0] - pts[:, 1]

        top_left = pts[sums.argmin()]
        bottom_right = pts[sums.argmax()]
        top_right = pts[diffs.argmin()]
        bottom_left = pts[diffs.argmax()]

        return np.array([top_left, top_right, bottom_right, bottom_left], dtype="float32")

    def _detect_document_corners(self, frame) -> tuple[np.ndarray | None, bool]:
        h, w = frame.shape[:2]
        if h < 50 or w < 50:
            return None, False

        target_height = 700
        scale = min(1.0, target_height / float(h))
        resized = cv2.resize(frame, (int(w * scale), int(h * scale)))

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 180)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, False

        img_area = resized.shape[0] * resized.shape[1]
        for contour in sorted(contours, key=cv2.contourArea, reverse=True):
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            area = cv2.contourArea(approx)

            if len(approx) != 4 or area < img_area * 0.15 or not cv2.isContourConvex(approx):
                continue

            corners = self._ordered_quad_points(approx)
            widths = [
                np.linalg.norm(corners[1] - corners[0]),
                np.linalg.norm(corners[2] - corners[3]),
            ]
            heights = [
                np.linalg.norm(corners[3] - corners[0]),
                np.linalg.norm(corners[2] - corners[1]),
            ]

            if min(widths + heights) < 60:
                continue

            corners_full = corners / scale
            return corners_full, True

        return None, False

    def _apply_document_crop(self, image, corners):
        h, w = image.shape[:2]
        xs = np.clip(corners[:, 0], 0, w - 1)
        ys = np.clip(corners[:, 1], 0, h - 1)

        x1, x2 = int(np.min(xs)), int(np.max(xs))
        y1, y2 = int(np.min(ys)), int(np.max(ys))

        if x2 <= x1 or y2 <= y1:
            return image

        return image[y1:y2, x1:x2].copy()

    def _apply_perspective_transform(self, image, corners):
        pts = self._ordered_quad_points(corners)

        width_top = np.linalg.norm(pts[1] - pts[0])
        width_bottom = np.linalg.norm(pts[2] - pts[3])
        max_width = max(2, int(max(width_top, width_bottom)))

        height_left = np.linalg.norm(pts[3] - pts[0])
        height_right = np.linalg.norm(pts[2] - pts[1])
        max_height = max(2, int(max(height_left, height_right)))

        destination = np.array(
            [
                [0, 0],
                [max_width - 1, 0],
                [max_width - 1, max_height - 1],
                [0, max_height - 1],
            ],
            dtype="float32",
        )

        matrix = cv2.getPerspectiveTransform(pts, destination)
        return cv2.warpPerspective(image, matrix, (max_width, max_height))

    def _apply_scanner_effect(self, image):
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        normalized = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
        return cv2.adaptiveThreshold(
            normalized,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            10,
        )

    def _build_processed_image(self, original_frame):
        processed = original_frame.copy()
        corners, reliable = self._detect_document_corners(processed)
        reliability_message = None

        if reliable and corners is not None:
            if self.perspective_checkbox.isChecked():
                processed = self._apply_perspective_transform(processed, corners)
            elif self.doc_crop_checkbox.isChecked():
                processed = self._apply_document_crop(processed, corners)
        elif self.doc_crop_checkbox.isChecked() or self.perspective_checkbox.isChecked():
            reliability_message = (
                "Documento non rilevato con affidabilità sufficiente: "
                "salvata elaborazione senza crop/prospettiva"
            )

        if self.grayscale_checkbox.isChecked():
            processed = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)

        if self.scanner_checkbox.isChecked():
            processed = self._apply_scanner_effect(processed)

        return processed, reliability_message

    def _save_processed_frame(self, original_path: Path, original_frame) -> tuple[bool, str | None]:
        if not self.save_processed_checkbox.isChecked():
            return True, None

        processed_path = self.processed_dir / f"{original_path.stem}_processed.jpg"
        processed_image, message = self._build_processed_image(original_frame)
        success = cv2.imwrite(str(processed_path), processed_image)
        if not success:
            return False, "Errore: versione elaborata non salvata"
        if message:
            return True, message
        return True, f"Versione elaborata salvata: {processed_path}"

    def _save_last_frame(self, source: str) -> bool:
        if self.last_frame is None:
            self.status_label.setText(f"Errore: nessun frame valido per scatto {source}")
            return False

        save_path = self._next_capture_path()
        original_frame = self.last_frame.copy()

        if not self._save_original_frame(original_frame, source, save_path):
            return False

        if not self.save_processed_checkbox.isChecked():
            return True

        try:
            processed_ok, message = self._save_processed_frame(save_path, original_frame)
        except Exception:
            self.status_label.setText(
                f"Foto salvata ({source}): {save_path} | Elaborazione non riuscita (errore inatteso)"
            )
            return True

        if processed_ok:
            self.status_label.setText(f"Foto salvata ({source}): {save_path}" + (f" | {message}" if message else ""))
        else:
            self.status_label.setText(f"Foto salvata ({source}): {save_path} | {message}")

        return True

    def capture_photo(self) -> None:
        self._save_last_frame(source="manuale")

    def start_continuous_capture(self) -> None:
        if self.continuous_state != self.CONTINUOUS_STOPPED:
            return

        if not self.cap or not self.cap.isOpened():
            self.status_label.setText("Errore: camera non disponibile per acquisizione continua")
            return

        self._reset_continuous_session()
        self.continuous_interval_ms = self._selected_interval_ms()
        self._schedule_next_deadline_from_now()
        self.continuous_timer.start(self.continuous_interval_ms)
        self.continuous_state = self.CONTINUOUS_RUNNING
        self.status_label.setText(
            f"Acquisizione continua attiva: uno scatto ogni {self.continuous_interval_ms // 1000} secondi"
        )
        self._refresh_session_info_labels()
        self._update_continuous_buttons()

    def pause_continuous_capture(self) -> None:
        if self.continuous_state != self.CONTINUOUS_RUNNING:
            return

        if self.next_capture_deadline is not None:
            self.paused_remaining_ms = int(max(0.0, self.next_capture_deadline - time.monotonic()) * 1000)

        self.continuous_timer.stop()
        self.continuous_state = self.CONTINUOUS_PAUSED
        self.status_label.setText("Acquisizione continua in pausa")
        self._refresh_session_info_labels()
        self._update_continuous_buttons()

    def resume_continuous_capture(self) -> None:
        if self.continuous_state != self.CONTINUOUS_PAUSED:
            return

        self.continuous_interval_ms = self._selected_interval_ms()
        self.paused_remaining_ms = None
        self._schedule_next_deadline_from_now()
        self.continuous_timer.start(self.continuous_interval_ms)
        self.continuous_state = self.CONTINUOUS_RUNNING
        self.status_label.setText(
            f"Acquisizione continua ripresa: uno scatto ogni {self.continuous_interval_ms // 1000} secondi"
        )
        self._refresh_session_info_labels()
        self._update_continuous_buttons()

    def stop_continuous_capture(self) -> None:
        if self.continuous_timer.isActive():
            self.continuous_timer.stop()

        self.continuous_state = self.CONTINUOUS_STOPPED
        self.next_capture_deadline = None
        self.paused_remaining_ms = None
        self.status_label.setText("Acquisizione continua fermata")
        self._refresh_session_info_labels()
        self._update_continuous_buttons()

    def _do_automatic_capture(self) -> None:
        if self.continuous_state != self.CONTINUOUS_RUNNING:
            return

        if self._save_last_frame(source="automatico"):
            self._register_automatic_capture_success()

        self._schedule_next_deadline_from_now()

    def closeEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "preview_timer") and self.preview_timer.isActive():
            self.preview_timer.stop()

        if hasattr(self, "continuous_timer") and self.continuous_timer.isActive():
            self.continuous_timer.stop()

        if self.cap is not None and self.cap.isOpened():
            self.cap.release()

        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    window = BookCaptureApp(device_path="/dev/video2")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
