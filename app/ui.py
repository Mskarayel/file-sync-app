"""CustomTkinter arayüzü ve thread/queue entegrasyonu.

Bu katman yalnızca sunum ve kullanıcı etkileşimini yönetir. İş mantığı
sync_engine, validators, report_manager ve settings_manager modüllerinden
gelir; motor kodu burada tekrarlanmaz.

Uzun işlemler daemon thread içinde çalışır. Worker thread widget'lara
dokunmaz; ilerlemeyi queue.Queue'ya ProgressMessage olarak yazar. Ana
thread queue'yu after() ile yoklayarak arayüzü günceller.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from . import constants, report_manager, settings_manager, sync_engine
from .models import STATUS_LABELS, FileStatus, ProgressMessage, SyncSummary
from .validators import validate_folders

logger = logging.getLogger(__name__)

# Durum -> "İşlem" sütunundaki metin.
ACTION_LABELS: dict[FileStatus, str] = {
    FileStatus.NEW: "Kopyala",
    FileStatus.MODIFIED: "Güncelle",
    FileStatus.SAME: "Atla",
    FileStatus.ERROR: "Hata",
}

DEFAULT_SUMMARY = "Toplam 0  |  Yeni 0  |  Değişmiş 0  |  Aynı 0  |  Hata 0"


def setup_logging() -> None:
    """Teknik dosya günlüğünü yapılandırır (yalnızca bir kez).

    Kullanıcıya gösterilen işlem günlüğünden bağımsızdır; RotatingFileHandler
    ile logs/app.log dosyasına UTF-8 olarak yazar. Aynı logger'a tekrar handler
    eklenmesi engellenir.
    """
    app_logger = logging.getLogger("app")
    if app_logger.handlers:
        return
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    constants.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        constants.LOG_FILE,
        maxBytes=constants.LOG_MAX_BYTES,
        backupCount=constants.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    app_logger.addHandler(handler)


def display_path(path: str) -> str:
    """Yolu işletim sistemine uygun ayraçla gösterir (Windows'ta ters eğik çizgi)."""
    return str(Path(path)) if path else ""


def format_size(num_bytes: int) -> str:
    """Byte değerini okunabilir B/KB/MB/GB biçimine çevirir."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class FileSyncApp(ctk.CTk):
    """Ana uygulama penceresi."""

    def __init__(self) -> None:
        super().__init__()

        setup_logging()
        logger.info("Uygulama açıldı")

        self._settings = settings_manager.load_settings()
        self._queue: queue.Queue[ProgressMessage] = queue.Queue()
        self._busy = False
        self._operation: str | None = None
        self._analysis: SyncSummary | None = None
        self._report_paths: dict[str, Path] = {}
        self._report_formats = list(
            self._settings.get("report_formats", list(constants.REPORT_FORMAT_OPTIONS))
        )

        self._source_var = tk.StringVar(value=display_path(self._settings.get("last_source", "")))
        self._target_var = tk.StringVar(value=display_path(self._settings.get("last_target", "")))
        self._theme_var = tk.StringVar(value=self._settings.get("theme", "System"))

        ctk.set_appearance_mode(self._theme_var.get())

        self.title(f"{constants.APP_NAME}")
        self.geometry("1100x700")
        self.minsize(900, 600)

        self._build_layout()
        self._apply_treeview_style()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_id: str | None = self.after(100, self._poll_queue)

    # ---- Yerleşim kurulumu -------------------------------------------------

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        # Tablo satırı ana genişleyen alandır.
        self.grid_rowconfigure(5, weight=1)

        self._build_header()
        self._build_folder_section()
        self._build_toolbar()
        self._build_summary_line()
        self._build_table()
        self._build_status_bar()
        self._build_log_section()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 3))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header, text="FileSync", font=ctk.CTkFont(size=14, weight="bold")
        )
        title.grid(row=0, column=0, sticky="w")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(right, text="◐", font=ctk.CTkFont(size=13)).pack(
            side="left", padx=(0, 1)
        )
        theme_menu = ctk.CTkOptionMenu(
            right,
            width=84,
            height=24,
            values=list(constants.THEME_OPTIONS),
            variable=self._theme_var,
            command=self._on_theme_change,
            font=ctk.CTkFont(size=11),
        )
        theme_menu.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            right,
            text="⚙",
            width=28,
            height=24,
            command=self._open_settings_dialog,
            font=ctk.CTkFont(size=15),
        ).pack(side="left")

        # İnce alt ayırıcı çizgi.
        ttk.Separator(self, orient="horizontal").grid(
            row=1, column=0, sticky="ew", padx=12, pady=(0, 4)
        )

    def _build_folder_section(self) -> None:
        self._browse_buttons: list[ctk.CTkButton] = []
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=2, column=0, sticky="ew", padx=12, pady=2)
        frame.grid_columnconfigure(1, weight=1)

        self._make_folder_row(frame, 0, "Kaynak klasör:", self._source_var, "source")
        self._make_folder_row(frame, 1, "Hedef klasör:", self._target_var, "target")

    def _make_folder_row(
        self, parent: ctk.CTkFrame, row: int, label: str, var: tk.StringVar, kind: str
    ) -> None:
        ctk.CTkLabel(parent, text=label, width=88, anchor="w",
                     font=ctk.CTkFont(size=11)).grid(
            row=row, column=0, sticky="w", padx=(0, 6), pady=2
        )
        entry = ctk.CTkEntry(parent, textvariable=var, height=24,
                             font=ctk.CTkFont(size=11))
        entry.grid(row=row, column=1, sticky="ew", pady=2)
        entry.configure(state="disabled")  # Salt okunur yol alanı.
        button = ctk.CTkButton(
            parent, text="Gözat", width=66, height=24, font=ctk.CTkFont(size=11),
            command=lambda: self._browse_folder(kind),
        )
        button.grid(row=row, column=2, sticky="e", padx=(6, 0), pady=2)
        self._browse_buttons.append(button)

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 2))

        self.btn_analyze = ctk.CTkButton(
            bar, text="Analiz Et", width=104, height=22, command=self._start_analyze,
            font=ctk.CTkFont(size=11),
        )
        self.btn_analyze.pack(side="left", padx=(0, 6))

        self.btn_sync = ctk.CTkButton(
            bar, text="Senkronize Et", width=120, height=22, command=self._start_sync,
            state="disabled", font=ctk.CTkFont(size=11),
        )
        self.btn_sync.pack(side="left", padx=6)

        self.btn_report = ctk.CTkButton(
            bar, text="Raporu Aç", width=104, height=22, command=self._open_report,
            state="disabled", fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=11),
        )
        self.btn_report.pack(side="left", padx=6)

    def _build_summary_line(self) -> None:
        self._summary_var = tk.StringVar(value=DEFAULT_SUMMARY)
        ctk.CTkLabel(
            self, textvariable=self._summary_var, anchor="w",
            font=ctk.CTkFont(size=11),
        ).grid(row=4, column=0, sticky="w", padx=12, pady=(1, 0))

    def _build_table(self) -> None:
        container = ctk.CTkFrame(self, corner_radius=4)
        container.grid(row=5, column=0, sticky="nsew", padx=12, pady=(4, 4))
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        columns = ("path", "status", "size", "action")
        self.tree = ttk.Treeview(container, columns=columns, show="headings", height=10)
        self.tree.heading("path", text="Dosya yolu", anchor="w")
        self.tree.heading("status", text="Durum", anchor="center")
        self.tree.heading("size", text="Boyut", anchor="e")
        self.tree.heading("action", text="İşlem", anchor="center")
        self.tree.column("path", width=560, minwidth=280, anchor="w", stretch=True)
        self.tree.column("status", width=100, minwidth=80, anchor="center", stretch=False)
        self.tree.column("size", width=110, minwidth=90, anchor="e", stretch=False)
        self.tree.column("action", width=130, minwidth=100, anchor="center", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ctk.CTkScrollbar(container, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Yalnızca hata satırı belirgin; diğerleri sade kalır.
        self.tree.tag_configure("error", foreground="#d9534f")

    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 3))
        bar.grid_columnconfigure(0, weight=1)

        self._status_var = tk.StringVar(value="Hazır")
        ctk.CTkLabel(bar, textvariable=self._status_var, anchor="w",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w")

        self._percent_var = tk.StringVar(value="%0")
        ctk.CTkLabel(bar, textvariable=self._percent_var, width=42, anchor="e",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=1, sticky="e")

        self.progress = ctk.CTkProgressBar(bar, height=10)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 0))

    def _build_log_section(self) -> None:
        self._log_open = True
        self._log_toggle = ctk.CTkButton(
            self, text="▼  İşlem günlüğü", anchor="w", height=24,
            fg_color="transparent", command=self._toggle_log,
            font=ctk.CTkFont(size=11),
        )
        self._log_toggle.grid(row=7, column=0, sticky="ew", padx=12)

        self.log_text = ctk.CTkTextbox(self, height=72, font=ctk.CTkFont(size=11))
        self.log_text.grid(row=8, column=0, sticky="ew", padx=12, pady=(2, 8))
        self.log_text.configure(state="disabled")

    # ---- Tema ve stil ------------------------------------------------------

    def _apply_treeview_style(self) -> None:
        """ttk.Treeview'ı geçerli ctk temasına göre renklendirir."""
        dark = ctk.get_appearance_mode() == "Dark"
        bg = "#2b2b2b" if dark else "#ffffff"
        fg = "#dce4ee" if dark else "#1a1a1a"
        heading_bg = "#3a3a3a" if dark else "#e5e5e5"
        selected = "#1f6aa5"

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Treeview", background=bg, foreground=fg, fieldbackground=bg,
            rowheight=22, borderwidth=0, font=("Segoe UI", 9),
        )
        style.map("Treeview", background=[("selected", selected)],
                  foreground=[("selected", "#ffffff")])
        style.configure(
            "Treeview.Heading", background=heading_bg, foreground=fg,
            relief="flat", font=("Segoe UI", 9, "bold"),
        )
        style.map("Treeview.Heading", background=[("active", heading_bg)])

    def _on_theme_change(self, theme: str) -> None:
        ctk.set_appearance_mode(theme)
        self._settings["theme"] = theme
        self._apply_treeview_style()

    # ---- Klasör seçimi -----------------------------------------------------

    def _browse_folder(self, kind: str) -> None:
        var = self._source_var if kind == "source" else self._target_var
        initial = var.get() or str(Path.home())
        chosen = filedialog.askdirectory(initialdir=initial)
        if not chosen:
            return
        chosen = display_path(chosen)
        if chosen == var.get():
            return  # Aynı klasör yeniden seçildi; analizi geçersiz kılma.
        var.set(chosen)
        recent_key = "recent_sources" if kind == "source" else "recent_targets"
        settings_key = "last_source" if kind == "source" else "last_target"
        self._settings[settings_key] = chosen
        settings_manager.add_recent_folder(self._settings, recent_key, chosen)
        # Klasör değişti: önceki analiz sonucu artık geçersiz.
        self._invalidate_analysis()

    def _invalidate_analysis(self) -> None:
        """Önceki analiz sonucunu ve ona bağlı arayüz durumunu temizler."""
        self._analysis = None
        self._report_paths = {}
        self._clear_table()
        self._summary_var.set(DEFAULT_SUMMARY)
        self.progress.set(0)
        self._percent_var.set("%0")
        self.btn_sync.configure(state="disabled")
        self.btn_report.configure(state="disabled")
        self._set_status("Hazır")

    # ---- İşlem başlatma ----------------------------------------------------

    def _start_analyze(self) -> None:
        if self._busy:
            return
        source = Path(self._source_var.get())
        target = Path(self._target_var.get())
        if not self._source_var.get() or not self._target_var.get():
            messagebox.showwarning("Eksik bilgi", "Kaynak ve hedef klasör seçilmeli.")
            return

        result = validate_folders(source, target)
        if not result.ok:
            messagebox.showerror("Geçersiz klasör", result.message)
            self._append_log(f"HATA: {result.message}")
            return

        self._analysis = None
        self._report_paths = {}
        self.btn_sync.configure(state="disabled")
        self.btn_report.configure(state="disabled")
        self._clear_table()
        self._operation = "analyze"
        self._set_status("Analiz ediliyor")
        self._begin_busy()
        self._spawn(self._worker_analyze, source, target)

    def _start_sync(self) -> None:
        if self._busy or self._analysis is None:
            return
        if not self._analysis.pending:
            messagebox.showinfo("Bilgi", "Kopyalanacak veya güncellenecek dosya yok.")
            return

        summary = self._analysis
        total = len(summary.pending)
        confirm = messagebox.askyesno(
            "Senkronizasyonu onayla",
            f"Yeni dosya: {summary.new_count}\n"
            f"Değişmiş dosya: {summary.modified_count}\n"
            f"İşlenecek toplam: {total}\n"
            f"Hedef klasör: {display_path(str(summary.target))}\n\n"
            "Devam edilsin mi?",
        )
        if not confirm:
            self._append_log("Senkronizasyon kullanıcı tarafından iptal edildi.")
            return

        self._report_paths = {}
        self.btn_report.configure(state="disabled")
        self._operation = "sync"
        self._set_status("Senkronize ediliyor")
        self._begin_busy()
        self._spawn(self._worker_sync, summary, list(self._report_formats))

    def _spawn(self, target: Callable[..., None], *args: object) -> None:
        thread = threading.Thread(target=target, args=args, daemon=True)
        thread.start()

    def _begin_busy(self) -> None:
        self._busy = True
        self.progress.set(0)
        self._percent_var.set("%0")
        self.btn_analyze.configure(state="disabled")
        self.btn_sync.configure(state="disabled")
        for button in self._browse_buttons:
            button.configure(state="disabled")

    def _finish_busy(self) -> None:
        self._busy = False
        self._operation = None
        self.btn_analyze.configure(state="normal")
        self.btn_sync.configure(
            state="normal" if self._analysis and self._analysis.pending else "disabled"
        )
        for button in self._browse_buttons:
            button.configure(state="normal")

    # ---- Worker fonksiyonları (ayrı thread) --------------------------------

    def _emit(self, message: ProgressMessage) -> None:
        """Worker thread'den ana thread'e mesaj aktarır (thread-güvenli)."""
        self._queue.put(message)

    def _worker_analyze(self, source: Path, target: Path) -> None:
        logger.info("Analiz başladı: %s -> %s", source, target)
        try:
            summary = sync_engine.analyze(source, target, progress=self._emit)
            logger.info(
                "Analiz bitti: toplam=%d yeni=%d değişmiş=%d aynı=%d hata=%d",
                summary.total_count, summary.new_count, summary.modified_count,
                summary.same_count, summary.error_count,
            )
        except Exception as exc:  # noqa: BLE001 - kullanıcıya iletilecek
            logger.exception("Analiz sırasında beklenmeyen hata")
            self._emit(ProgressMessage("error", text=f"Analiz hatası: {exc}"))

    def _worker_sync(self, plan: SyncSummary, formats: list[str]) -> None:
        logger.info("Senkronizasyon başladı: %d dosya işlenecek", len(plan.pending))
        try:
            result = sync_engine.synchronize(plan, progress=self._emit)
            paths = report_manager.save_reports(result, formats=formats)
            logger.info(
                "Senkronizasyon bitti: yeni=%d değişmiş=%d hata=%d",
                result.new_count, result.modified_count, result.error_count,
            )
            self._emit(ProgressMessage("reports", payload=paths))
        except report_manager.ReportError as exc:
            logger.exception("Rapor yazılamadı")
            self._emit(ProgressMessage("error", text=str(exc)))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Senkronizasyon sırasında beklenmeyen hata")
            self._emit(ProgressMessage("error", text=f"Senkronizasyon hatası: {exc}"))

    # ---- Queue yoklama (ana thread) ----------------------------------------

    def _poll_queue(self) -> None:
        try:
            while True:
                message = self._queue.get_nowait()
                self._handle_message(message)
        except queue.Empty:
            pass
        self._poll_id = self.after(100, self._poll_queue)

    def _handle_message(self, message: ProgressMessage) -> None:
        if message.kind == "log":
            self._append_log(message.text)
        elif message.kind == "progress":
            self._on_progress(message)
        elif message.kind == "done":
            self._on_done(message.payload)
        elif message.kind == "reports":
            self._on_reports(message.payload)
        elif message.kind == "error":
            self._append_log(message.text)
            messagebox.showerror("Hata", message.text)
            self._set_status("Hazır")
            self._finish_busy()

    def _on_progress(self, message: ProgressMessage) -> None:
        frac = (message.current / message.total) if message.total else 0.0
        self.progress.set(frac)
        self._percent_var.set(f"%{int(frac * 100)}")

    def _on_done(self, summary: object) -> None:
        if not isinstance(summary, SyncSummary):
            return
        operation = self._operation
        if operation == "analyze":
            self._analysis = summary
        self._populate_table(summary)
        self._update_summary_line(summary)
        self.progress.set(1.0)
        self._percent_var.set("%100")
        self._set_status("Tamamlandı")
        self._finish_busy()
        if operation == "sync":
            messagebox.showinfo(
                "Senkronizasyon tamamlandı",
                f"Yeni: {summary.new_count}\n"
                f"Değişmiş: {summary.modified_count}\n"
                f"Hata: {summary.error_count}\n"
                f"Toplam: {summary.total_count}",
            )

    def _on_reports(self, paths: object) -> None:
        if not isinstance(paths, dict) or not paths:
            return
        self._report_paths = paths
        self.btn_report.configure(state="normal")
        for path in paths.values():
            self._append_log(f"Rapor oluşturuldu: {path.name}")

    # ---- Tablo ve özet -----------------------------------------------------

    def _clear_table(self) -> None:
        self.tree.delete(*self.tree.get_children())

    def _populate_table(self, summary: SyncSummary) -> None:
        self._clear_table()
        for comparison in summary.comparisons:
            tag = ("error",) if comparison.status is FileStatus.ERROR else ()
            self.tree.insert(
                "", "end",
                values=(
                    str(comparison.relative_path),
                    STATUS_LABELS[comparison.status],
                    format_size(comparison.size),
                    ACTION_LABELS[comparison.status],
                ),
                tags=tag,
            )

    def _update_summary_line(self, summary: SyncSummary) -> None:
        self._summary_var.set(
            f"Toplam {summary.total_count}  |  "
            f"Yeni {summary.new_count}  |  "
            f"Değişmiş {summary.modified_count}  |  "
            f"Aynı {summary.same_count}  |  "
            f"Hata {summary.error_count}"
        )

    # ---- Log ve durum ------------------------------------------------------

    def _append_log(self, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{timestamp}  {text}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)

    def _toggle_log(self) -> None:
        self._log_open = not self._log_open
        if self._log_open:
            self.log_text.grid()
            self._log_toggle.configure(text="▼  İşlem günlüğü")
        else:
            self.log_text.grid_remove()
            self._log_toggle.configure(text="▶  İşlem günlüğü")

    # ---- Rapor açma --------------------------------------------------------

    def _open_report(self) -> None:
        path = self._report_paths.get("txt") or self._report_paths.get("json")
        if not path:
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except OSError as exc:
            messagebox.showerror("Rapor açılamadı", str(exc))

    # ---- Ayarlar penceresi -------------------------------------------------

    def _open_settings_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Ayarlar")
        dialog.geometry("300x180")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="Rapor formatları", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=16, pady=(16, 8))

        txt_var = tk.BooleanVar(value="txt" in self._report_formats)
        json_var = tk.BooleanVar(value="json" in self._report_formats)
        ctk.CTkCheckBox(dialog, text="TXT raporu", variable=txt_var,
                        font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=4)
        ctk.CTkCheckBox(dialog, text="JSON raporu", variable=json_var,
                        font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=4)

        def apply_and_close() -> None:
            formats = [f for f, v in (("txt", txt_var), ("json", json_var)) if v.get()]
            if not formats:
                messagebox.showwarning("Uyarı", "En az bir rapor formatı seçilmeli.",
                                       parent=dialog)
                return
            self._report_formats = formats
            self._settings["report_formats"] = formats
            dialog.destroy()

        ctk.CTkButton(dialog, text="Kaydet", width=90, command=apply_and_close,
                      font=ctk.CTkFont(size=12)).pack(pady=16)

    # ---- Kapanış -----------------------------------------------------------

    def _on_close(self) -> None:
        if self._busy and not messagebox.askyesno(
            "Çıkış", "Bir işlem sürüyor. Yine de çıkılsın mı?"
        ):
            return
        self._persist_settings()
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        logger.info("Uygulama kapandı")
        self.destroy()

    def _persist_settings(self) -> None:
        self._settings["last_source"] = self._source_var.get()
        self._settings["last_target"] = self._target_var.get()
        self._settings["theme"] = self._theme_var.get()
        self._settings["report_formats"] = list(self._report_formats)
        try:
            settings_manager.save_settings(self._settings)
        except OSError:
            pass  # Ayar kaydı başarısız olsa da uygulama kapanabilmeli.
