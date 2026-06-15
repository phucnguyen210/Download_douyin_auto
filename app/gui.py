from __future__ import annotations

import threading
import asyncio
import sys
import os
import json
from pathlib import Path
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

from app.logger import setup_logger
from app.config import load_settings
from app.main import amain
from tkinter import ttk
from app.services.audio_extract_service import AudioExtractService
from app.services.asr_service import ASRService
from app.services.tts_service import TTSService, TTS_VOICE_OPTIONS, DEFAULT_TTS_VOICE_LABEL
from app.services.audio_merge_service import AudioMergeService
from app.services.video_merge_service import VideoMergeService
from app.services.subtitle_service import SubtitleService
from app.config import Settings
from app.database.db import Database
from app.database.repositories import VideoRepository
from app.translator import Translator, TRANSLATION_STYLE_LABELS

LOGGER = setup_logger("gui")

class AppGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Douyin Downloader — Pipeline GUI")
        self.settings = load_settings()
        self.cwd = Path(os.getcwd())

        frm = tk.Frame(root)
        frm.pack(padx=8, pady=8)

        form_frame = tk.Frame(frm)
        form_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(form_frame, text="URL Profile:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        self.profile_var = tk.StringVar()
        tk.Entry(form_frame, textvariable=self.profile_var, width=60).grid(row=0, column=1, padx=4, pady=2)

        tk.Label(form_frame, text="Tháng mục tiêu (YYYY-MM):").grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        self.month_var = tk.StringVar()
        tk.Entry(form_frame, textvariable=self.month_var, width=20).grid(row=1, column=1, sticky=tk.W, padx=4, pady=2)

        tk.Label(form_frame, text="Giới hạn:").grid(row=2, column=0, sticky=tk.W, padx=4, pady=2)
        self.limit_var = tk.StringVar(value="0")
        tk.Entry(form_frame, textvariable=self.limit_var, width=10).grid(row=2, column=1, sticky=tk.W, padx=4, pady=2)

        tk.Label(form_frame, text="Kieu dich:").grid(row=3, column=0, sticky=tk.W, padx=4, pady=2)
        self.translation_style_options = {label: key for key, label in TRANSLATION_STYLE_LABELS.items()}
        self.translation_style_var = tk.StringVar(value=TRANSLATION_STYLE_LABELS["general"])
        style_combo = ttk.Combobox(
            form_frame,
            textvariable=self.translation_style_var,
            values=list(self.translation_style_options.keys()),
            state="readonly",
            width=24,
        )
        style_combo.grid(row=3, column=1, sticky=tk.W, padx=4, pady=2)


        tk.Label(form_frame, text="Giong doc:").grid(row=4, column=0, sticky=tk.W, padx=4, pady=2)
        self.tts_voice_var = tk.StringVar(value=os.getenv("TTS_VOICE_LABEL", DEFAULT_TTS_VOICE_LABEL))
        if self.tts_voice_var.get() not in TTS_VOICE_OPTIONS:
            self.tts_voice_var.set(DEFAULT_TTS_VOICE_LABEL)
        voice_combo = ttk.Combobox(
            form_frame,
            textvariable=self.tts_voice_var,
            values=list(TTS_VOICE_OPTIONS.keys()),
            state="readonly",
            width=32,
        )
        voice_combo.grid(row=4, column=1, sticky=tk.W, padx=4, pady=2)

        btn_frame = tk.Frame(frm)
        btn_frame.pack(side=tk.TOP, fill=tk.X)

        download_btn = tk.Button(btn_frame, text="Tải video", width=12, command=self._run_download)
        download_btn.grid(row=0, column=0, padx=4)

        open_out = tk.Button(btn_frame, text="Mở thư mục", width=12, command=self._open_output)
        open_out.grid(row=0, column=1, padx=4)

        refresh_btn = tk.Button(btn_frame, text="Làm mới", width=12, command=self.refresh_file_list)
        refresh_btn.grid(row=0, column=2, padx=4)

        # Video list
        list_frame = tk.Frame(frm)
        list_frame.pack(fill=tk.BOTH, expand=True)

        file_frame = tk.LabelFrame(list_frame, text="Video tải về")
        file_frame.pack(fill=tk.BOTH, expand=True)

        file_cols = ("sel", "name", "path")
        self.file_tree = ttk.Treeview(file_frame, columns=file_cols, show="headings", height=8)
        self.file_tree.heading("sel", text="Chọn")
        self.file_tree.heading("name", text="Tiêu đề")
        self.file_tree.heading("path", text="Đường dẫn")
        self.file_tree.column("sel", width=40, anchor=tk.CENTER)
        self.file_tree.column("name", width=300)
        self.file_tree.column("path", width=500)
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        file_scroll = tk.Scrollbar(file_frame, orient="vertical", command=self.file_tree.yview)
        file_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_tree.configure(yscrollcommand=file_scroll.set)
        self.file_tree.bind("<Double-1>", self._on_file_tree_toggle)

        db_frame = tk.LabelFrame(list_frame, text="Cơ sở dữ liệu video")
        db_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        db_cols = ("status", "title", "path")
        self.db_tree = ttk.Treeview(db_frame, columns=db_cols, show="headings", height=8)
        self.db_tree.heading("status", text="Trạng thái")
        self.db_tree.heading("title", text="Tiêu đề")
        self.db_tree.heading("path", text="Đường dẫn / Video")
        self.db_tree.column("status", width=120, anchor=tk.CENTER)
        self.db_tree.column("title", width=300)
        self.db_tree.column("path", width=500)
        self.db_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        db_scroll = tk.Scrollbar(db_frame, orient="vertical", command=self.db_tree.yview)
        db_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.db_tree.configure(yscrollcommand=db_scroll.set)

        # Action buttons for selected
        action_frame = tk.Frame(frm)
        action_frame.pack(fill=tk.X, pady=(6, 8))

        tk.Button(action_frame, text="ASR", command=self._asr_selected).pack(side=tk.LEFT, padx=4)
        tk.Button(action_frame, text="Chạy pipeline", command=self._process_selected).pack(side=tk.LEFT, padx=4)
        tk.Button(action_frame, text="Lên lịch DB", command=self._schedule_selected).pack(side=tk.LEFT, padx=4)
        tk.Button(action_frame, text="Làm mới DB", command=self.refresh_db_list).pack(side=tk.LEFT, padx=4)

        self.log = ScrolledText(frm, height=10, width=100)
        self.log.pack(pady=(8, 0))

        # internal state
        self._selected_files = set()
        self.settings: Settings = load_settings()

        self.refresh_file_list()
        self.refresh_db_list()

    def _append(self, text: str) -> None:
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def _get_translation_style(self) -> str:
        label = self.translation_style_var.get().strip()
        return self.translation_style_options.get(label, "general")

    def _get_translation_style_label(self) -> str:
        return self.translation_style_var.get().strip() or TRANSLATION_STYLE_LABELS["general"]


    def _get_tts_voice_label(self) -> str:
        label = self.tts_voice_var.get().strip()
        return label if label in TTS_VOICE_OPTIONS else DEFAULT_TTS_VOICE_LABEL
    def _run_action(self, action, label: str) -> None:
        self._append(f"Bắt đầu: {label}")

        def target() -> None:
            try:
                result = action()
                if asyncio.iscoroutine(result):
                    asyncio.run(result)
                self._append(f"{label} hoàn tất")
            except Exception as exc:
                self._append(f"Lỗi {label}: {exc}")

        t = threading.Thread(target=target, daemon=True)
        t.start()

    def _run_download(self) -> None:
        profile_url = self.profile_var.get().strip()
        if not profile_url:
            self._append("Cần nhập URL Profile.")
            return
        month = self.month_var.get().strip() or None
        limit = self.limit_var.get().strip() or "0"
        args = [profile_url]
        if month:
            args.append(month)
        if limit.isdigit() and int(limit) > 0:
            args.extend(["--limit", limit])

        self._append(f"Bắt đầu tải: {profile_url}")

        def target() -> None:
            try:
                asyncio.run(amain(args))
                self._append("Tải video hoàn tất.")
                self.refresh_file_list()
            except Exception as exc:
                self._append(f"Lỗi tải video: {exc}")

        t = threading.Thread(target=target, daemon=True)
        t.start()

    def _open_output(self) -> None:
        out = Path(self.settings.output_dir)
        os.startfile(str(out))

    def _build_pipeline_paths(self, video_path: Path) -> dict[str, Path]:
        video_path = Path(video_path)
        output_root = Path(self.settings.output_dir)
        work_dir = output_root / "work" / video_path.stem
        audio_dir = work_dir / "audio"
        final_dir = output_root / "final"
        for folder in (work_dir, audio_dir, final_dir):
            folder.mkdir(parents=True, exist_ok=True)
        base = work_dir / video_path.stem
        return {
            "work_dir": work_dir,
            "audio_dir": audio_dir,
            "base": base,
            "tts_audio": work_dir / f"{video_path.stem}.tts.wav",
            "merged_audio": work_dir / f"{video_path.stem}.merged_audio.m4a",
            "final_video": final_dir / f"{video_path.stem}.final.mp4",
            "final_srt": final_dir / f"{video_path.stem}.final.srt",
        }
    def refresh_file_list(self) -> None:
        # scan downloads dir for mp4 files (recent)
        base = Path(self.settings.downloads_dir)
        self.file_tree.delete(*self.file_tree.get_children())
        self._selected_files.clear()
        if not base.exists():
            return
        files = list(base.rglob("*.mp4"))
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[:200]:
            name = f.name
            iid = str(f)
            sel = "☐"
            self.file_tree.insert("", tk.END, iid=iid, values=(sel, name, str(f)))

    def refresh_db_list(self) -> None:
        db = Database(Path(self.settings.database_path))
        repo = VideoRepository(db)
        videos = repo.list_videos(limit=200)
        self.db_tree.delete(*self.db_tree.get_children())
        for row in videos:
            iid = str(row.get("id"))
            status = row.get("download_status", "")
            title = row.get("title") or row.get("source_video_url")
            path = row.get("local_video_path") or row.get("source_video_url")
            self.db_tree.insert("", tk.END, iid=iid, values=(status, title, str(path)))
        db.close()

    def _get_selected_paths(self) -> list[Path]:
        paths: list[Path] = []
        for item in self._selected_files:
            try:
                paths.append(Path(item))
            except Exception:
                continue
        return paths

    def _on_file_tree_toggle(self, event: tk.Event) -> None:
        item_id = self.file_tree.identify_row(event.y)
        if not item_id:
            return
        if item_id in self._selected_files:
            self._selected_files.remove(item_id)
            self.file_tree.set(item_id, "sel", "☐")
        else:
            self._selected_files.add(item_id)
            self.file_tree.set(item_id, "sel", "☑")

    def _extract_audio_selected(self) -> None:
        paths = self._get_selected_paths()
        if not paths:
            self._append("Chưa chọn video để tách audio")
            return
        def target():
            svc = AudioExtractService(self.settings)
            for p in paths:
                try:
                    pipeline_paths = self._build_pipeline_paths(p)
                    outdir = pipeline_paths["audio_dir"]
                    self._append(f"Đang tách audio cho {p.name} -> {outdir}")
                    res = svc.extract_audio(p, outdir)
                    self._append(f"Audio đã lưu: {res}")
                except Exception as e:
                    self._append(f"Tách audio thất bại cho {p.name}: {e}")
        threading.Thread(target=target, daemon=True).start()

    def _asr_selected(self) -> None:
        paths = self._get_selected_paths()
        if not paths:
            self._append("Chưa chọn audio/video để chạy ASR")
            return
        def target():
            svc = ASRService(self.settings)
            for p in paths:
                # prefer extracted audio file if exists
                pipeline_paths = self._build_pipeline_paths(p)
                audio_dir = pipeline_paths["audio_dir"]
                audio = audio_dir / "original_audio.wav"
                if not audio.exists():
                    possible = list(p.parent.glob(p.stem + '*audio*/*.wav'))
                    audio = possible[0] if possible else p
                self._append(f"Đang ASR {p.name} bằng {audio}")
                try:
                    import asyncio
                    result = asyncio.run(svc.transcribe(audio))
                    base = pipeline_paths["base"]
                    out_json, out_srt = svc.write_transcript_files(base, result)
                    self._append(f"ASR hoàn tất: {out_json}")
                except Exception as e:
                    self._append(f"ASR thất bại cho {p.name}: {e}")
        threading.Thread(target=target, daemon=True).start()

    def _process_selected(self) -> None:
        paths = self._get_selected_paths()
        if not paths:
            self._append("Chưa chọn video để xử lý")
            return

        def target():
            ae = AudioExtractService(self.settings)
            ar = ASRService(self.settings)
            tts_voice_label = self._get_tts_voice_label()
            tt = TTSService(self.settings, voice_label=tts_voice_label)
            am = AudioMergeService(self.settings)
            vm = VideoMergeService(self.settings)
            ss = SubtitleService()
            translation_style = self._get_translation_style()
            translation_style_label = self._get_translation_style_label()
            self._append(f"[PIPELINE] TTS voice: {tts_voice_label}")

            import asyncio

            for p in paths:
                try:
                    self._append(f"[PIPELINE] Processing {p.name}")

                    pipeline_paths = self._build_pipeline_paths(p)
                    self._append(f"[PIPELINE] Work dir: {pipeline_paths['work_dir']}")
                    self._append(f"[PIPELINE] Final dir: {pipeline_paths['final_video'].parent}")

                    # 1) Extract audio
                    outdir = pipeline_paths["audio_dir"]
                    self._append(f"[PIPELINE] Extracting audio")
                    orig_audio = ae.extract_audio(p, outdir)

                    # 2) ASR
                    self._append(f"[PIPELINE] Running ASR")
                    result = asyncio.run(ar.transcribe(orig_audio))
                    base = pipeline_paths["base"]
                    json_path, srt_path = ar.write_transcript_files(base, result)

                    # Remove stale outputs from previous failed/old pipeline runs
                    for old_output in (pipeline_paths["tts_audio"], pipeline_paths["merged_audio"], pipeline_paths["final_video"], pipeline_paths["final_srt"]):
                        try:
                            old_output.unlink(missing_ok=True)
                        except Exception:
                            pass

                    # 3) Translate transcript to Vietnamese, preserving ASR timestamps
                    self._append(f"[PIPELINE] Translating transcript to Vietnamese ({translation_style_label})")
                    translated_json_path = None
                    translated_srt_path = None
                    try:
                        with json_path.open("r", encoding="utf-8") as f:
                            source_data = json.load(f)
                        segments = source_data.get("segments") or []
                        if not segments:
                            raise RuntimeError("ASR returned no timestamp segments; cannot create Vietnamese synced TTS safely.")
                        translator = Translator(self.settings)
                        translated_segments = asyncio.run(translator.translate_transcript_segments(segments, style=translation_style))
                        translated_json_path, translated_srt_path = ss.write_translated_transcript(base, source_data, translated_segments)
                        self._append(f"[PIPELINE] Vietnamese subtitle saved: {translated_srt_path}")
                    except Exception as e:
                        self._append(f"[PIPELINE] Translation failed; stop before TTS to avoid Chinese voiceover: {e}")
                        raise

                    # 4) TTS
                    self._append(f"[PIPELINE] Running Vietnamese TTS ({tts_voice_label})")
                    tts_out = pipeline_paths["tts_audio"]
                    try:
                        tts_result = tt.synthesize_from_transcript_file(translated_json_path, tts_out)
                        tts_size = Path(tts_result).stat().st_size if Path(tts_result).exists() else 0
                        self._append(f"[PIPELINE] Vietnamese TTS saved: {tts_result} ({tts_size} bytes)")
                    except Exception as e:
                        self._append(f"[PIPELINE] TTS failed, stopping before merge: {e}")
                        raise

                    # 5) Audio merge
                    self._append(f"[PIPELINE] Merging audio (original 5%, Vietnamese TTS 100%)")
                    merged_audio = pipeline_paths["merged_audio"]
                    am.merge(orig_audio, tts_out, merged_audio, original_volume=0.05, voice_volume=1.0)
                    self._append(f"[PIPELINE] Mixed audio saved: {merged_audio}")

                    # 6) Video mux
                    self._append(f"[PIPELINE] Muxing video + audio")
                    final_vid = pipeline_paths["final_video"]
                    vm.mux_audio_into_video(p, merged_audio, final_vid)

                    # 7) Subtitles
                    self._append(f"[PIPELINE] Generating subtitles")
                    ss.create_srt_for_transcript(translated_json_path, merged_audio, pipeline_paths["final_srt"])

                    try:
                        db = Database(Path(self.settings.database_path))
                        repo = VideoRepository(db)
                        video_id = repo.upsert_video({
                            "source_platform": "douyin",
                            "source_video_id": p.stem,
                            "source_video_url": str(p),
                            "title": p.stem,
                            "local_video_path": str(p),
                            "download_status": "completed",
                            "audio_extract_status": "completed",
                            "asr_status": "completed",
                            "translation_status": "completed",
                            "tts_status": "completed",
                            "audio_merge_status": "completed",
                            "video_merge_status": "completed",
                            "original_audio_path": str(orig_audio),
                            "transcript_json_path": str(json_path),
                            "transcript_srt_path": str(srt_path),
                            "translated_json_path": str(translated_json_path),
                            "translated_srt_path": str(translated_srt_path),
                            "merged_voice_path": str(tts_out),
                            "final_audio_path": str(merged_audio),
                            "final_video_path": str(final_vid),
                            "error_message": "",
                        })
                        db.close()
                        self._append(f"[PIPELINE] DB updated: video_id={video_id}")
                    except Exception as db_exc:
                        self._append(f"[PIPELINE] DB update failed: {db_exc}")
                    self._append(f"[PIPELINE] Hoàn tất {p.name} -> {final_vid}")

                except Exception as e:
                    self._append(f"[PIPELINE] Thất bại {p.name}: {e}")

        threading.Thread(target=target, daemon=True).start()

    def _schedule_selected(self) -> None:
        paths = self._get_selected_paths()
        if not paths:
            self._append("Chưa chọn video để lên lịch")
            return

        db = Database(Path(self.settings.database_path))
        repo = VideoRepository(db)

        for p in paths:
            try:
                sid = p.stem
                data = {
                    "source_platform": "douyin",
                    "source_video_id": sid,
                    "source_video_url": str(p),
                    "title": p.name,
                    "local_video_path": str(p),
                    "download_status": "completed",
                    "audio_extract_status": "pending",
                    "asr_status": "pending",
                    "tts_status": "pending",
                    "audio_merge_status": "pending",
                    "video_merge_status": "pending",
                }
                vid = repo.upsert_video(data)
                self._append(f"Đã lên lịch {p.name} với id={vid}")
            except Exception as e:
                self._append(f"Lên lịch thất bại cho {p.name}: {e}")

        db.close()
        self.refresh_db_list()

    def _tts_selected(self) -> None:
        paths = self._get_selected_paths()
        if not paths:
            self._append("Chưa chọn transcript để TTS")
            return
        def target():
            tts_voice_label = self._get_tts_voice_label()
            tts = TTSService(self.settings, voice_label=tts_voice_label)
            self._append(f"TTS voice: {tts_voice_label}")
            for p in paths:
                pipeline_paths = self._build_pipeline_paths(p)
                trans = pipeline_paths["base"].with_suffix('.vi.transcript.json')
                if not trans.exists():
                    trans = pipeline_paths["base"].with_suffix('.transcript.json')
                if not trans.exists():
                    self._append(f"Transcript not found for {p.name}: expected {trans}")
                    continue
                out = pipeline_paths["tts_audio"]
                try:
                    res = tts.synthesize_from_transcript_file(trans, out)
                    self._append(f"TTS saved: {res}")
                except Exception as e:
                    self._append(f"TTS thất bại cho {p.name}: {e}")
        threading.Thread(target=target, daemon=True).start()

    def _sub_selected(self) -> None:
        paths = self._get_selected_paths()
        if not paths:
            self._append("Chưa chọn video để tạo phụ đề")
            return
        self._append("Hãy chạy ASR trước để tạo transcript, sau đó dùng nút Chạy pipeline để tiếp tục.")


def main() -> None:
    root = tk.Tk()
    app = AppGUI(root)
    root.mainloop()

