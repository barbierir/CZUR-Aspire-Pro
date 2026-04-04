import sys
from pathlib import Path

import cv2
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BookCaptureApp(QWidget):
    """Applicazione minimale per anteprima V4L2 e salvataggio di foto."""

    def __init__(self, device_path: str = "/dev/video2") -> None:
        super().__init__()
        self.device_path = device_path
        self.capture_dir = Path("captures")
        self.capture_dir.mkdir(parents=True, exist_ok=True)

        self.cap: cv2.VideoCapture | None = None
        self.last_frame = None

        self._build_ui()
        self._init_camera()

        # Aggiorna la preview circa ogni 30 ms.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

    def _build_ui(self) -> None:
        """Costruisce la GUI principale."""
        self.setWindowTitle("Book Capture")
        self.resize(960, 600)

        self.preview_label = QLabel("Anteprima non disponibile")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(800, 450)
        self.preview_label.setStyleSheet("background-color: #111; color: #ddd; border: 1px solid #444;")

        self.status_label = QLabel("Stato: inizializzazione...")

        self.capture_button = QPushButton("Scatta foto")
        self.capture_button.clicked.connect(self.capture_photo)

        self.exit_button = QPushButton("Esci")
        self.exit_button.clicked.connect(self.close)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.capture_button)
        button_layout.addWidget(self.exit_button)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.preview_label)
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def _init_camera(self) -> None:
        """Inizializza la camera V4L2 e imposta una risoluzione di base."""
        # CAP_V4L2 è disponibile su Linux con backend V4L2.
        self.cap = cv2.VideoCapture(self.device_path, cv2.CAP_V4L2)

        if not self.cap or not self.cap.isOpened():
            self.status_label.setText(f"Errore: impossibile aprire {self.device_path}")
            self.capture_button.setEnabled(False)
            return

        # Richiesta risoluzione iniziale (potrebbe non essere accettata dal device).
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        self.status_label.setText(f"Camera aperta: {self.device_path}")
        self.capture_button.setEnabled(True)

    def update_frame(self) -> None:
        """Legge un frame dalla camera e aggiorna la preview."""
        if not self.cap or not self.cap.isOpened():
            return

        ok, frame = self.cap.read()
        if not ok or frame is None:
            self.status_label.setText("Errore: lettura frame non riuscita")
            return

        self.last_frame = frame

        # Conversione BGR (OpenCV) -> RGB (Qt)
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
            last_name = existing[-1].stem  # es: page_0007
            try:
                next_index = int(last_name.split("_")[-1]) + 1
            except ValueError:
                next_index = len(existing) + 1

        return self.capture_dir / f"page_{next_index:04d}.jpg"

    def capture_photo(self) -> None:
        """Salva l'ultimo frame valido ricevuto dalla preview."""
        if self.last_frame is None:
            self.status_label.setText("Errore: nessun frame valido da salvare")
            return

        save_path = self._next_capture_path()
        success = cv2.imwrite(str(save_path), self.last_frame)

        if success:
            self.status_label.setText(f"Foto salvata: {save_path}")
        else:
            self.status_label.setText("Errore: salvataggio foto non riuscito")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        """Rilascia risorse OpenCV alla chiusura della finestra."""
        if hasattr(self, "timer") and self.timer.isActive():
            self.timer.stop()

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
