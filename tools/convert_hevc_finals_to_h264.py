from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = ROOT / "output" / "final"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "final_h264"


def ffprobe_codec(path: Path) -> str:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"ffprobe failed for {path}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    return str((streams[0] if streams else {}).get("codec_name") or "")


def convert_to_h264(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(target),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-2000:])


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert old HEVC final videos to Facebook-friendly H.264/AAC MP4.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--all", action="store_true", help="Convert all mp4 files, not only HEVC/H.265 files.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    files = sorted(args.input_dir.glob("*.mp4"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not files:
        print(f"No mp4 files found in {args.input_dir}")
        return 0

    converted = 0
    skipped = 0
    failed = 0
    for source in files:
        try:
            codec = ffprobe_codec(source)
            needs_convert = args.all or codec in {"hevc", "h265"}
            if not needs_convert:
                skipped += 1
                print(f"SKIP {source.name}: codec={codec}")
                continue
            target = args.output_dir / source.name
            print(f"CONVERT {source.name}: codec={codec} -> {target}")
            if not args.dry_run:
                convert_to_h264(source, target)
                out_codec = ffprobe_codec(target)
                if out_codec != "h264":
                    raise RuntimeError(f"converted output codec is {out_codec}, expected h264")
            converted += 1
        except Exception as exc:
            failed += 1
            print(f"FAILED {source.name}: {exc}")

    print(f"Done. converted={converted}, skipped={skipped}, failed={failed}, output_dir={args.output_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())