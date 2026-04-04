import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BookCaptureApp(QWidget):
    """Applicazione per anteprima V4L2, scatto singolo e acquisizione continua."""

    CONTINUOUS_STOPPED = "stopped"
    CONTINUOUS_RUNNING = "running"
    CONTINUOUS_PAUSED = "paused"

    @dataclass
    class FlatteningResult:
        image: np.ndarray
        applied: bool
        message: str | None = None

    def __init__(self, device_path: str = "/dev/video2") -> None:
        super().__init__()
        self.device_path = device_path
        self.capture_dir = Path("captures")
        self.capture_dir.mkdir(parents=True, exist_ok=True)

        self.current_session_name: str | None = None
        self.current_session_dir: Path | None = None
        self.session_list_files: list[Path] = []

        self.cap: cv2.VideoCapture | None = None
        self.last_frame = None

        self.continuous_state = self.CONTINUOUS_STOPPED
        self.continuous_interval_ms = 3000
        self.next_capture_deadline: float | None = None
        self.paused_remaining_ms: int | None = None
        self.session_capture_count = 0

        self._build_ui()
        self._init_camera()
        self._ensure_default_session()

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
        self._update_session_labels()
        self._refresh_session_file_list()

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

        self.work_session_group = QGroupBox("Sessione di lavoro")
        self.session_name_input = QLineEdit()
        self.session_name_input.setPlaceholderText("es. libro_storia_cap1")
        self.new_session_button = QPushButton("Nuova sessione")
        self.new_session_button.clicked.connect(self._on_new_session_clicked)
        self.active_session_dir_label = QLabel("Cartella sessione attiva: -")
        self.pages_in_session_label = QLabel("Pagine nella sessione: 0")

        session_input_layout = QHBoxLayout()
        session_input_layout.addWidget(QLabel("Nome sessione:"))
        session_input_layout.addWidget(self.session_name_input)
        session_input_layout.addWidget(self.new_session_button)

        session_layout = QVBoxLayout()
        session_layout.addLayout(session_input_layout)
        session_layout.addWidget(self.active_session_dir_label)
        session_layout.addWidget(self.pages_in_session_label)
        self.work_session_group.setLayout(session_layout)

        self.post_process_group = QGroupBox("Post-processing")
        self.save_processed_checkbox = QCheckBox("Salva anche versione elaborata")
        self.grayscale_checkbox = QCheckBox("Scala di grigi")
        self.scanner_checkbox = QCheckBox("Effetto scanner")
        self.doc_crop_checkbox = QCheckBox("Auto-crop documento")
        self.perspective_checkbox = QCheckBox("Correzione prospettiva")
        self.flattening_checkbox = QCheckBox("Flattening sperimentale")

        self.save_processed_checkbox.toggled.connect(self._on_save_processed_toggled)

        pp_layout = QVBoxLayout()
        pp_layout.addWidget(self.save_processed_checkbox)
        pp_layout.addWidget(self.grayscale_checkbox)
        pp_layout.addWidget(self.scanner_checkbox)
        pp_layout.addWidget(self.doc_crop_checkbox)
        pp_layout.addWidget(self.perspective_checkbox)
        pp_layout.addWidget(self.flattening_checkbox)
        self.post_process_group.setLayout(pp_layout)

        self.export_group = QGroupBox("Export PDF")
        self.pdf_source_selector = QComboBox()
        self.pdf_source_selector.addItem("Originali", userData="originals")
        self.pdf_source_selector.addItem("Elaborate", userData="processed")
        self.export_pdf_button = QPushButton("Esporta PDF sessione")
        self.export_pdf_button.clicked.connect(self._export_session_pdf)

        export_layout = QHBoxLayout()
        export_layout.addWidget(QLabel("Sorgente PDF:"))
        export_layout.addWidget(self.pdf_source_selector)
        export_layout.addWidget(self.export_pdf_button)
        export_layout.addStretch()
        self.export_group.setLayout(export_layout)

        self.session_pages_group = QGroupBox("Pagine sessione")
        self.browser_source_selector = QComboBox()
        self.browser_source_selector.addItem("Originali", userData="originals")
        self.browser_source_selector.addItem("Elaborate", userData="processed")
        self.browser_source_selector.currentIndexChanged.connect(self._on_browser_source_changed)

        self.refresh_list_button = QPushButton("Aggiorna elenco")
        self.refresh_list_button.clicked.connect(self._refresh_session_file_list)

        self.delete_last_page_button = QPushButton("Elimina ultima pagina")
        self.delete_last_page_button.clicked.connect(self._delete_last_page)

        self.move_up_button = QPushButton("Sposta su")
        self.move_up_button.clicked.connect(self._move_selected_page_up)

        self.move_down_button = QPushButton("Sposta giù")
        self.move_down_button.clicked.connect(self._move_selected_page_down)

        self.session_file_list_widget = QListWidget()
        self.session_file_list_widget.currentRowChanged.connect(self._load_selected_session_image_preview)
        self.session_file_list_widget.setMinimumWidth(280)

        self.session_image_preview_label = QLabel("Nessuna immagine selezionata")
        self.session_image_preview_label.setAlignment(Qt.AlignCenter)
        self.session_image_preview_label.setMinimumSize(300, 220)
        self.session_image_preview_label.setStyleSheet("background-color: #151515; color: #ddd; border: 1px solid #444;")

        browser_controls_layout = QHBoxLayout()
        browser_controls_layout.addWidget(QLabel("Sorgente elenco:"))
        browser_controls_layout.addWidget(self.browser_source_selector)
        browser_controls_layout.addWidget(self.refresh_list_button)
        browser_controls_layout.addWidget(self.delete_last_page_button)
        browser_controls_layout.addWidget(self.move_up_button)
        browser_controls_layout.addWidget(self.move_down_button)
        browser_controls_layout.addStretch()

        browser_content_layout = QHBoxLayout()
        browser_content_layout.addWidget(self.session_file_list_widget, 1)
        browser_content_layout.addWidget(self.session_image_preview_label, 2)

        browser_layout = QVBoxLayout()
        browser_layout.addLayout(browser_controls_layout)
        browser_layout.addLayout(browser_content_layout)
        self.session_pages_group.setLayout(browser_layout)

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
        main_layout.addWidget(self.work_session_group)
        main_layout.addWidget(self.post_process_group)
        main_layout.addWidget(self.export_group)
        main_layout.addWidget(self.session_pages_group)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

        self._on_save_processed_toggled(False)

    def _on_save_processed_toggled(self, enabled: bool) -> None:
        self.grayscale_checkbox.setEnabled(enabled)
        self.scanner_checkbox.setEnabled(enabled)
        self.doc_crop_checkbox.setEnabled(enabled)
        self.perspective_checkbox.setEnabled(enabled)
        self.flattening_checkbox.setEnabled(enabled)

    def _sanitize_session_name(self, raw_name: str) -> str:
        candidate = (raw_name or "").strip().replace(" ", "_")
        candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate)
        candidate = candidate.strip("._-")
        if not candidate:
            return self._generate_default_session_name()
        return candidate[:80]

    @staticmethod
    def _generate_default_session_name() -> str:
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def _session_originals_dir(self) -> Path:
        if self.current_session_dir is None:
            raise ValueError("Sessione non inizializzata")
        return self.current_session_dir / "originals"

    def _session_processed_dir(self) -> Path:
        if self.current_session_dir is None:
            raise ValueError("Sessione non inizializzata")
        return self.current_session_dir / "processed"

    def _count_pages_in_current_session(self) -> int:
        try:
            originals_dir = self._session_originals_dir()
        except ValueError:
            return 0
        if not originals_dir.exists():
            return 0
        return len(sorted(originals_dir.glob("page_*.jpg")))

    def _update_session_labels(self) -> None:
        if self.current_session_name is None or self.current_session_dir is None:
            self.active_session_dir_label.setText("Cartella sessione attiva: -")
            self.pages_in_session_label.setText("Pagine nella sessione: 0")
            return

        self.active_session_dir_label.setText(f"Cartella sessione attiva: {self.current_session_dir}")
        self.pages_in_session_label.setText(f"Pagine nella sessione: {self._count_pages_in_current_session()}")

    def _current_browser_source_dir(self) -> Path | None:
        if self.current_session_dir is None:
            return None
        source = self.browser_source_selector.currentData()
        if source == "processed":
            return self._session_processed_dir()
        return self._session_originals_dir()

    def _clear_session_image_preview(self, placeholder: str = "Nessuna immagine selezionata") -> None:
        self.session_image_preview_label.clear()
        self.session_image_preview_label.setText(placeholder)

    def _refresh_session_file_list(self, selected_path: Path | None = None) -> None:
        source_dir = self._current_browser_source_dir()
        self.session_file_list_widget.blockSignals(True)
        self.session_file_list_widget.clear()
        self.session_list_files = []

        if source_dir is None or not source_dir.exists():
            self.session_file_list_widget.blockSignals(False)
            self._clear_session_image_preview()
            return

        source = self.browser_source_selector.currentData()
        pattern = "page_*_processed.jpg" if source == "processed" else "page_*.jpg"
        files = sorted(source_dir.glob(pattern), key=lambda p: p.name)
        self.session_list_files = files

        selected_row = -1
        for index, path in enumerate(files):
            item = QListWidgetItem(path.name)
            self.session_file_list_widget.addItem(item)
            if selected_path is not None and path == selected_path:
                selected_row = index

        if files:
            if selected_row < 0:
                selected_row = len(files) - 1
            self.session_file_list_widget.setCurrentRow(selected_row)
        self.session_file_list_widget.blockSignals(False)
        self._load_selected_session_image_preview()

    def _load_selected_session_image_preview(self, *_args) -> None:
        row = self.session_file_list_widget.currentRow()
        if row < 0 or row >= len(self.session_list_files):
            self._clear_session_image_preview()
            return

        path = self.session_list_files[row]
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._clear_session_image_preview("Anteprima non disponibile")
            self.status_label.setText(f"Immagine non leggibile: {path.name}")
            return

        scaled = pixmap.scaled(
            self.session_image_preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.session_image_preview_label.setPixmap(scaled)

    def _find_last_original_page(self) -> Path | None:
        if self.current_session_dir is None:
            return None
        originals = sorted(self._session_originals_dir().glob("page_*.jpg"), key=lambda p: p.name)
        if not originals:
            return None
        return originals[-1]

    @staticmethod
    def _original_name_from_browser_item(item_name: str) -> str | None:
        if item_name.endswith("_processed.jpg"):
            candidate = item_name.removesuffix("_processed.jpg") + ".jpg"
        else:
            candidate = item_name
        if re.fullmatch(r"page_\d{4}\.jpg", candidate):
            return candidate
        return None

    def _selected_original_page_name(self) -> str | None:
        row = self.session_file_list_widget.currentRow()
        if row < 0 or row >= len(self.session_list_files):
            return None
        return self._original_name_from_browser_item(self.session_list_files[row].name)

    def _move_selected_page_up(self) -> None:
        self._move_selected_page(direction=-1)

    def _move_selected_page_down(self) -> None:
        self._move_selected_page(direction=1)

    def _move_selected_page(self, direction: int) -> None:
        if self.current_session_dir is None:
            self.status_label.setText("Riordino non eseguito: nessuna sessione attiva")
            return

        selected_original = self._selected_original_page_name()
        if selected_original is None:
            self.status_label.setText("Riordino non eseguito: seleziona una pagina nell'elenco")
            return

        originals_dir = self._session_originals_dir()
        ordered_originals = sorted(originals_dir.glob("page_*.jpg"), key=lambda p: p.name)
        if not ordered_originals:
            self.status_label.setText("Riordino non eseguito: nessuna pagina presente nella sessione")
            return

        auto_stop_note = ""
        if self.continuous_state in (self.CONTINUOUS_RUNNING, self.CONTINUOUS_PAUSED):
            self.stop_continuous_capture(update_status=False)
            auto_stop_note = "Acquisizione continua fermata automaticamente prima del riordino. "

        reorder_ok, new_selected_name, error = self._reorder_original_pages(
            selected_original_name=selected_original,
            direction=direction,
            ordered_originals=ordered_originals,
        )
        if not reorder_ok:
            prefix = f"{auto_stop_note}" if auto_stop_note else ""
            self.status_label.setText(f"{prefix}Riordino non riuscito: {error}")
            self._refresh_session_file_list()
            self._update_session_labels()
            return

        self._update_session_labels()
        selected_original_path = originals_dir / new_selected_name
        source = self.browser_source_selector.currentData()
        if source == "processed":
            processed_selected = self._processed_path_for_original(selected_original_path)
            selected_path = processed_selected if processed_selected.exists() else None
        else:
            selected_path = selected_original_path
        self._refresh_session_file_list(selected_path=selected_path)
        self.status_label.setText(f"{auto_stop_note}Pagina riordinata con successo: {new_selected_name}")

    def _reorder_original_pages(
        self,
        selected_original_name: str,
        direction: int,
        ordered_originals: list[Path],
    ) -> tuple[bool, str, str | None]:
        names = [p.name for p in ordered_originals]
        if selected_original_name not in names:
            return False, "", "pagina selezionata non trovata tra gli originali"

        selected_index = names.index(selected_original_name)
        target_index = selected_index + direction
        if target_index < 0:
            return False, "", "la pagina è già la prima"
        if target_index >= len(ordered_originals):
            return False, "", "la pagina è già l'ultima"

        ordered_originals[selected_index], ordered_originals[target_index] = (
            ordered_originals[target_index],
            ordered_originals[selected_index],
        )
        return self._renumber_session_files(ordered_originals, moved_original_name=selected_original_name)

    def _renumber_session_files(
        self,
        ordered_originals: list[Path],
        moved_original_name: str,
    ) -> tuple[bool, str, str | None]:
        rename_plan: list[tuple[Path, Path]] = []
        selected_new_name = ""

        for index, original_path in enumerate(ordered_originals, start=1):
            new_original_name = f"page_{index:04d}.jpg"
            new_original_path = self._session_originals_dir() / new_original_name
            if original_path.name != new_original_name:
                rename_plan.append((original_path, new_original_path))

            current_processed_path = self._processed_path_for_original(original_path)
            new_processed_path = self._session_processed_dir() / f"page_{index:04d}_processed.jpg"
            if current_processed_path.exists() and current_processed_path != new_processed_path:
                rename_plan.append((current_processed_path, new_processed_path))

            if original_path.name == moved_original_name:
                selected_new_name = new_original_name

        if not selected_new_name and ordered_originals:
            selected_new_name = "page_0001.jpg"

        ok, error = self._safe_bulk_rename(rename_plan)
        return ok, selected_new_name, error

    @staticmethod
    def _safe_bulk_rename(rename_pairs: list[tuple[Path, Path]]) -> tuple[bool, str | None]:
        if not rename_pairs:
            return True, None

        unique_pairs: list[tuple[Path, Path]] = []
        seen = set()
        for src, dst in rename_pairs:
            key = (src, dst)
            if src == dst or key in seen:
                continue
            seen.add(key)
            unique_pairs.append((src, dst))

        temp_to_original: dict[Path, Path] = {}
        temp_to_destination: dict[Path, Path] = {}
        second_phase_done: list[tuple[Path, Path]] = []

        try:
            for src, dst in unique_pairs:
                if not src.exists():
                    raise FileNotFoundError(f"File non trovato durante la rinomina: {src.name}")
                temp_name = f".tmp_reorder_{uuid4().hex}_{src.name}"
                temp_path = src.with_name(temp_name)
                src.rename(temp_path)
                temp_to_original[temp_path] = src
                temp_to_destination[temp_path] = dst

            for temp_path, dst in temp_to_destination.items():
                if dst.exists():
                    raise FileExistsError(f"Destinazione già esistente durante la rinomina: {dst.name}")
                temp_path.rename(dst)
                second_phase_done.append((dst, temp_path))

            return True, None
        except Exception as exc:
            for dst, temp_path in reversed(second_phase_done):
                if dst.exists():
                    dst.rename(temp_path)
            for temp_path, original_path in reversed(list(temp_to_original.items())):
                if temp_path.exists():
                    temp_path.rename(original_path)
            return False, str(exc)

    def _processed_path_for_original(self, original_path: Path) -> Path:
        return self._session_processed_dir() / f"{original_path.stem}_processed.jpg"

    def _on_browser_source_changed(self, *_args) -> None:
        self._refresh_session_file_list()

    def _delete_last_page(self) -> None:
        if self.current_session_dir is None:
            self.status_label.setText("Eliminazione non eseguita: nessuna sessione attiva")
            return

        if self.continuous_state in (self.CONTINUOUS_RUNNING, self.CONTINUOUS_PAUSED):
            self.stop_continuous_capture(update_status=False)
            self.status_label.setText("Acquisizione continua fermata automaticamente prima dell'eliminazione")

        last_original = self._find_last_original_page()
        if last_original is None:
            self.status_label.setText("Eliminazione non eseguita: nessuna pagina presente nella sessione")
            self._refresh_session_file_list()
            self._update_session_labels()
            return

        processed_path = self._processed_path_for_original(last_original)
        try:
            last_original.unlink(missing_ok=True)
            if processed_path.exists():
                processed_path.unlink(missing_ok=True)
        except Exception as exc:
            self.status_label.setText(f"Errore eliminazione ultima pagina: {exc}")
            self._refresh_session_file_list()
            self._update_session_labels()
            return

        self._update_session_labels()
        self.status_label.setText(f"Ultima pagina eliminata: {last_original.name}")
        self._refresh_session_file_list()

    def _create_new_session(self, requested_name: str | None = None) -> bool:
        session_name = self._sanitize_session_name(requested_name or "")
        session_dir = self.capture_dir / session_name

        try:
            (session_dir / "originals").mkdir(parents=True, exist_ok=True)
            (session_dir / "processed").mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.status_label.setText(f"Errore: creazione sessione non riuscita ({exc})")
            return False

        self.current_session_name = session_name
        self.current_session_dir = session_dir
        self.session_capture_count = 0
        self._update_session_count_label()
        self._update_session_labels()
        self._refresh_session_file_list()
        self._clear_session_image_preview()
        return True

    def _ensure_default_session(self) -> None:
        if self.current_session_dir is not None:
            return
        if self._create_new_session(self._generate_default_session_name()):
            self.status_label.setText(f"Sessione iniziale pronta: {self.current_session_name}")

    def _on_new_session_clicked(self) -> None:
        if self.continuous_state in (self.CONTINUOUS_RUNNING, self.CONTINUOUS_PAUSED):
            self.stop_continuous_capture(update_status=False)
            self.status_label.setText("Acquisizione continua fermata automaticamente prima della nuova sessione")

        requested = self.session_name_input.text()
        if self._create_new_session(requested):
            self.status_label.setText(f"Nuova sessione attiva: {self.current_session_name}")
            self.session_name_input.clear()

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

        if self.current_session_name:
            lines.append(f"Progetto: {self.current_session_name}")

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
        width = 560
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
        originals_dir = self._session_originals_dir()
        existing = sorted(originals_dir.glob("page_*.jpg"))

        if not existing:
            next_index = 1
        else:
            last_name = existing[-1].stem
            try:
                next_index = int(last_name.split("_")[-1]) + 1
            except ValueError:
                next_index = len(existing) + 1

        return originals_dir / f"page_{next_index:04d}.jpg"

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

    def _is_flattening_applicable(self, image) -> tuple[bool, str | None, np.ndarray | None]:
        h, w = image.shape[:2]
        if h < 280 or w < 280:
            return False, "Flattening sperimentale non applicato: condizioni non adatte", None

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
        text_mask = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            41,
            11,
        )
        text_mask = cv2.medianBlur(text_mask, 3)

        profile_values = np.full(w, np.nan, dtype=np.float32)
        for x in range(w):
            ys = np.flatnonzero(text_mask[:, x] > 0)
            if ys.size < max(8, h // 45):
                continue
            low = np.percentile(ys, 10)
            high = np.percentile(ys, 90)
            profile_values[x] = float((low + high) / 2.0)

        valid = ~np.isnan(profile_values)
        valid_ratio = float(np.count_nonzero(valid)) / float(w)
        if valid_ratio < 0.35:
            return False, "Flattening sperimentale non applicato: condizioni non adatte", None

        x_valid = np.flatnonzero(valid).astype(np.float32)
        y_valid = profile_values[valid]
        interpolated = np.interp(np.arange(w, dtype=np.float32), x_valid, y_valid)
        smooth_profile = cv2.GaussianBlur(interpolated.reshape(1, -1), (0, 0), sigmaX=18).reshape(-1)

        dev = smooth_profile - float(np.median(smooth_profile))
        amplitude = float(np.max(np.abs(dev)))
        if amplitude < 2.0 or amplitude > (h * 0.08):
            return False, "Flattening sperimentale non applicato: condizioni non adatte", None

        return True, None, dev

    def _apply_experimental_flattening(self, image) -> FlatteningResult:
        applicable, message, deformation = self._is_flattening_applicable(image)
        if not applicable or deformation is None:
            return self.FlatteningResult(image=image, applied=False, message=message)

        try:
            h, w = image.shape[:2]
            max_shift = float(h * 0.05)
            shifts = np.clip(deformation, -max_shift, max_shift).astype(np.float32)

            map_x = np.tile(np.arange(w, dtype=np.float32), (h, 1))
            map_y = np.tile(np.arange(h, dtype=np.float32).reshape(-1, 1), (1, w)) + shifts.reshape(1, -1)
            map_y = np.clip(map_y, 0, h - 1)

            flattened = cv2.remap(
                image,
                map_x,
                map_y,
                interpolation=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            )
            return self.FlatteningResult(
                image=flattened,
                applied=True,
                message="Flattening sperimentale applicato",
            )
        except Exception:
            return self.FlatteningResult(
                image=image,
                applied=False,
                message="Elaborazione standard salvata: flattening non riuscito",
            )

    def _build_processed_image(self, original_frame):
        processed = original_frame.copy()
        corners, reliable = self._detect_document_corners(processed)
        pipeline_messages: list[str] = []

        if reliable and corners is not None:
            if self.perspective_checkbox.isChecked():
                processed = self._apply_perspective_transform(processed, corners)
            elif self.doc_crop_checkbox.isChecked():
                processed = self._apply_document_crop(processed, corners)
        elif self.doc_crop_checkbox.isChecked() or self.perspective_checkbox.isChecked():
            pipeline_messages.append(
                "Documento non rilevato con affidabilità sufficiente: "
                "salvata elaborazione senza crop/prospettiva"
            )

        if self.flattening_checkbox.isChecked():
            flattening_result = self._apply_experimental_flattening(processed)
            processed = flattening_result.image
            if flattening_result.message:
                pipeline_messages.append(flattening_result.message)

        if self.grayscale_checkbox.isChecked():
            processed = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)

        if self.scanner_checkbox.isChecked():
            processed = self._apply_scanner_effect(processed)

        message = " | ".join(pipeline_messages) if pipeline_messages else None
        return processed, message

    def _save_processed_frame(self, original_path: Path, original_frame) -> tuple[bool, str | None]:
        if not self.save_processed_checkbox.isChecked():
            return True, None

        processed_path = self._session_processed_dir() / f"{original_path.stem}_processed.jpg"
        processed_image, message = self._build_processed_image(original_frame)
        success = cv2.imwrite(str(processed_path), processed_image)
        if not success:
            return False, "Errore: versione elaborata non salvata"
        base_message = f"Versione elaborata salvata: {processed_path}"
        if message:
            return True, f"{base_message} | {message}"
        return True, base_message

    def _save_last_frame(self, source: str) -> bool:
        if self.last_frame is None:
            self.status_label.setText(f"Errore: nessun frame valido per scatto {source}")
            return False

        if self.current_session_dir is None:
            self.status_label.setText("Errore: nessuna sessione attiva")
            return False

        save_path = self._next_capture_path()
        original_frame = self.last_frame.copy()

        if not self._save_original_frame(original_frame, source, save_path):
            return False

        if not self.save_processed_checkbox.isChecked():
            self._update_session_labels()
            self._refresh_session_file_list(selected_path=save_path)
            return True

        try:
            processed_ok, message = self._save_processed_frame(save_path, original_frame)
        except Exception:
            self.status_label.setText(
                f"Foto salvata ({source}): {save_path} | Elaborazione non riuscita (errore inatteso)"
            )
            self._update_session_labels()
            return True

        if processed_ok:
            self.status_label.setText(f"Foto salvata ({source}): {save_path}" + (f" | {message}" if message else ""))
        else:
            self.status_label.setText(f"Foto salvata ({source}): {save_path} | {message}")

        self._update_session_labels()
        source = self.browser_source_selector.currentData()
        if source == "processed":
            selected = self._processed_path_for_original(save_path)
            self._refresh_session_file_list(selected_path=selected if selected.exists() else None)
        else:
            self._refresh_session_file_list(selected_path=save_path)
        return True

    def _export_session_pdf(self) -> None:
        if self.current_session_dir is None or self.current_session_name is None:
            self.status_label.setText("Errore: nessuna sessione attiva per export PDF")
            return

        source = self.pdf_source_selector.currentData()
        if source == "processed":
            image_dir = self._session_processed_dir()
            pattern = "page_*_processed.jpg"
            pdf_name = f"{self.current_session_name}_processed.pdf"
        else:
            image_dir = self._session_originals_dir()
            pattern = "page_*.jpg"
            pdf_name = f"{self.current_session_name}_originals.pdf"

        image_paths = sorted(image_dir.glob(pattern))
        if not image_paths:
            label = "elaborate" if source == "processed" else "originali"
            self.status_label.setText(f"Export PDF non eseguito: nessuna immagine {label} nella sessione corrente")
            return

        pdf_path = self.current_session_dir / pdf_name
        pil_images: list[Image.Image] = []
        try:
            for path in image_paths:
                with Image.open(path) as opened:
                    pil_images.append(opened.convert("RGB"))

            first, *rest = pil_images
            first.save(pdf_path, save_all=True, append_images=rest)
            self.status_label.setText(f"PDF esportato con successo: {pdf_path}")
        except Exception as exc:
            self.status_label.setText(f"Errore durante export PDF: {exc}")
        finally:
            for img in pil_images:
                img.close()

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

    def stop_continuous_capture(self, update_status: bool = True) -> None:
        if self.continuous_timer.isActive():
            self.continuous_timer.stop()

        self.continuous_state = self.CONTINUOUS_STOPPED
        self.next_capture_deadline = None
        self.paused_remaining_ms = None
        if update_status:
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
