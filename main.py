import sys
from pathlib import Path

import cv2
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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

        self.cap: cv2.VideoCapture | None = None
        self.last_frame = None
        self.continuous_state = self.CONTINUOUS_STOPPED

        self._build_ui()
        self._init_camera()

        # Timer preview live.
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.update_frame)
        self.preview_timer.start(30)

        # Timer separato per scatto continuo.
        self.continuous_timer = QTimer(self)
        self.continuous_timer.timeout.connect(self._do_automatic_capture)
        self.continuous_timer.setSingleShot(False)

        self._update_continuous_buttons()

    def _build_ui(self) -> None:
        """Costruisce la GUI principale."""
        self.setWindowTitle("Book Capture")
        self.resize(980, 640)

        self.preview_label = QLabel("Anteprima non disponibile")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(800, 450)
        self.preview_label.setStyleSheet("background-color: #111; color: #ddd; border: 1px solid #444;")

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
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

    def _init_camera(self) -> None:
        """Inizializza la camera V4L2 e imposta una risoluzione di base."""
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
        """Restituisce l'intervallo selezionato in millisecondi."""
        value = self.interval_selector.currentData()
        return int(value) if value is not None else 3000

    def _update_continuous_buttons(self) -> None:
        """Allinea lo stato dei pulsanti della sessione continua."""
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

    def update_frame(self) -> None:
        """Legge un frame dalla camera e aggiorna la preview."""
        if not self.cap or not self.cap.isOpened():
            return

        ok, frame = self.cap.read()
        if not ok or frame is None:
            self.status_label.setText("Errore: lettura frame non riuscita")
            return

        self.last_frame = frame

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
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
        """Restituisce il prossimo nome file page_XXXX.jpg disponibile."""
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

    def _save_last_frame(self, source: str) -> bool:
        """Salva l'ultimo frame valido e aggiorna la status label."""
        if self.last_frame is None:
            self.status_label.setText(f"Errore: nessun frame valido per scatto {source}")
            return False

        save_path = self._next_capture_path()
        success = cv2.imwrite(str(save_path), self.last_frame)

        if success:
            self.status_label.setText(f"Foto salvata ({source}): {save_path}")
            return True

        self.status_label.setText(f"Errore: salvataggio foto {source} non riuscito")
        return False

    def capture_photo(self) -> None:
        """Scatto singolo manuale."""
        self._save_last_frame(source="manuale")

    def start_continuous_capture(self) -> None:
        """Avvia una sessione di acquisizione continua temporizzata."""
        if self.continuous_state != self.CONTINUOUS_STOPPED:
            return

        if not self.cap or not self.cap.isOpened():
            self.status_label.setText("Errore: camera non disponibile per acquisizione continua")
            return

        interval_ms = self._selected_interval_ms()
        self.continuous_timer.start(interval_ms)
        self.continuous_state = self.CONTINUOUS_RUNNING
        self.status_label.setText(
            f"Acquisizione continua attiva: uno scatto ogni {interval_ms // 1000} secondi"
        )
        self._update_continuous_buttons()

    def pause_continuous_capture(self) -> None:
        """Mette in pausa la sessione continua."""
        if self.continuous_state != self.CONTINUOUS_RUNNING:
            return

        self.continuous_timer.stop()
        self.continuous_state = self.CONTINUOUS_PAUSED
        self.status_label.setText("Acquisizione continua in pausa")
        self._update_continuous_buttons()

    def resume_continuous_capture(self) -> None:
        """Riprende la sessione continua ripartendo da zero col timer."""
        if self.continuous_state != self.CONTINUOUS_PAUSED:
            return

        interval_ms = self._selected_interval_ms()
        self.continuous_timer.start(interval_ms)
        self.continuous_state = self.CONTINUOUS_RUNNING
        self.status_label.setText(
            f"Acquisizione continua ripresa: uno scatto ogni {interval_ms // 1000} secondi"
        )
        self._update_continuous_buttons()

    def stop_continuous_capture(self) -> None:
        """Ferma completamente la sessione continua."""
        if self.continuous_timer.isActive():
            self.continuous_timer.stop()

        self.continuous_state = self.CONTINUOUS_STOPPED
        self.status_label.setText("Acquisizione continua fermata")
        self._update_continuous_buttons()

    def _do_automatic_capture(self) -> None:
        """Esegue uno scatto automatico durante la sessione continua."""
        if self.continuous_state != self.CONTINUOUS_RUNNING:
            return

        self._save_last_frame(source="automatico")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        """Rilascia timer e risorse OpenCV alla chiusura della finestra."""
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
