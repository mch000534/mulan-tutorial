#!/usr/bin/env python3
"""把 45 鏡 i2v 片段依 design/02 時間碼組接成 60 秒粵語粗剪。

流程（16:9，目前只有 16:9 有動態素材）：

    讀 shotlist → 每鏡裁到時間碼窗格（24fps 整幀）→ 裁成 1280×720
                → 逐鏡編出片段（含 H3 原生環境聲）
                → 串接 45 段 → 混 60 秒 DX 對白軌
                → 輸出 MP4（內嵌軟字幕）

用法：

    python3 scripts/assemble_cut.py                      # v1 粵語粗剪
    python3 scripts/assemble_cut.py --round v2
    python3 scripts/assemble_cut.py --no-ambience        # 只留對白
    python3 scripts/assemble_cut.py --ambience-gain 0.5
    python3 scripts/assemble_cut.py --no-subs
    python3 scripts/assemble_cut.py --overrides cuts/seed_overrides.json
    python3 scripts/assemble_cut.py --keep-work          # 保留逐鏡中間檔

`--overrides` 是 JSON：{"15": "v2", "31": "v1"}，逐鏡指定 v1／v2。
"""

from __future__ import annotations

import argparse
import array
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import shotlist  # noqa: E402

FPS = 24
OUT_W, OUT_H, OUT_CROP_Y = 1280, 720, 8  # 片段 1280×736 → 居中裁回 16:9
CLIP_DIR = ROOT / "assets" / "video" / "shots_169"
DX_TRACK = ROOT / "assets" / "audio" / "tracks" / "MULAN_60s_16x9_CANTONESE_DX.wav"
SRT = ROOT / "assets" / "audio" / "srt" / "MULAN_60s_16x9_yue-Hant.srt"
CUTS_DIR = ROOT / "assets" / "video" / "cuts"
SEG_CRF = "16"


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr[-4000:] + "\n")
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:8])}…")


def probe_duration(path: Path) -> float:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(p.stdout.strip())


def clip_path(no: int, pick: str) -> Path:
    suffix = "" if pick == "v1" else "_v2"
    return CLIP_DIR / f"shot_{no:02d}_16x9{suffix}.mp4"


def load_overrides(path: Path | None) -> dict[int, str]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[int, str] = {}
    for k, v in data.items():
        pick = str(v).lower()
        if pick not in ("v1", "v2"):
            raise ValueError(f"override {k}: 只能是 v1 或 v2，收到 {v!r}")
        out[int(k)] = pick
    return out


def encode_segment(src: Path, dst: Path, n_frames: int, ambience: bool) -> None:
    """把一片段裁成 n_frames、1280×720；環境聲關掉時輸出靜音。"""
    dur = n_frames / FPS
    src_dur = probe_duration(src)
    # 素材比需要的短才放慢（setpts 拉伸），否則取前 n_frames
    slow = src_dur + 1e-3 < dur
    if slow:
        rate = dur / src_dur
        v = (
            f"[0:v]setpts=PTS*{rate:.6f},fps={FPS},"
            f"crop={OUT_W}:{OUT_H}:0:{OUT_CROP_Y},format=yuv420p,trim=end_frame={n_frames},"
            f"setpts=PTS-STARTPTS[v]"
        )
    else:
        v = (
            f"[0:v]trim=end_frame={n_frames},setpts=PTS-STARTPTS,"
            f"crop={OUT_W}:{OUT_H}:0:{OUT_CROP_Y},fps={FPS},format=yuv420p[v]"
        )
    fade_out = max(dur - 0.005, 0.0)
    if ambience:
        a = (
            f"[0:a]atrim=duration={dur:.6f},asetpts=PTS-STARTPTS,"
            f"aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo,"
            f"afade=t=in:d=0.005,afade=t=out:st={fade_out:.6f}:d=0.005[a]"
        )
    else:
        a = f"anullsrc=r=48000:cl=stereo:d={dur:.6f},aformat=sample_fmts=s16[a]"
    run([
        "ffmpeg", "-y", "-i", str(src),
        "-filter_complex", f"{v};{a}",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", SEG_CRF,
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-fps_mode", "cfr",
        "-video_track_timescale", "24000",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
        str(dst),
    ])


def concat_segments(listfile: Path, dst: Path) -> None:
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-c", "copy", str(dst),
    ])


def final_mix(video_in: Path, dx: Path, srt: Path | None, out: Path,
              ambience_gain: float, with_subs: bool, total: float = 60.0) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(video_in), "-i", str(dx),
    ]
    srt_idx = None
    if with_subs and srt is not None and srt.exists():
        cmd += ["-i", str(srt)]
        srt_idx = 2
    gain = f"{ambience_gain:.4f}"
    fc = (
        f"[1:a]pan=stereo|FL=c0|FR=c0,aresample=48000[dx];"
        f"[0:a]volume={gain}[amb];"
        f"[dx][amb]amix=inputs=2:duration=longest:normalize=0,"
        f"alimiter=limit=0.97:level=false,apad=whole_dur={total:.6f},"
        f"atrim=end={total:.6f}[a]"
    )
    cmd += [
        "-filter_complex", fc,
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-video_track_timescale", "24000",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
    ]
    if srt_idx is not None:
        cmd += [
            "-map", f"{srt_idx}:s", "-c:s", "mov_text",
            "-metadata:s:s:0", "language=chi",
        ]
    cmd += [
        "-movflags", "+faststart",
        "-metadata", "title=雌雄 · 粗剪 16:9",
        str(out),
    ]
    run(cmd)


def dx_end_seconds(path: Path, thresh_db: float = -45.0) -> float:
    """掃 DX 軸最後一個有聲取樣，回傳結束時間（秒）。"""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1",
         "-ar", "48000", "-"],
        capture_output=True, check=True,
    )
    a = array.array("h")
    a.frombytes(p.stdout[: len(p.stdout) // 2 * 2])
    thresh = 32768 * (10 ** (thresh_db / 20))
    for i in range(len(a) - 1, -1, -1):
        if abs(a[i]) > thresh:
            return i / 48000
    return 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description="60 秒粵語粗剪組接")
    ap.add_argument("--round", choices=("v1", "v2"), default="v1",
                    help="預設整批用哪個 seed 輪（可被 overrides 覆蓋）")
    ap.add_argument("--overrides", type=Path, default=None,
                    help='逐鏡指定：{"15": "v2"}')
    ap.add_argument("--ambience-gain", type=float, default=0.85,
                    help="H3 原生環境聲相對 DX 的音量（預設 0.85，環境聲本身已偏小）")
    ap.add_argument("--no-ambience", action="store_true", help="關掉環境聲，只留對白")
    ap.add_argument("--no-subs", action="store_true", help="不內嵌軟字幕")
    ap.add_argument("--tail", choices=("auto", "off"), default="auto",
                    help="auto：DX 尾音超過 60 秒時，延長最後一鏡讓它講完（L cut 到片尾）")
    ap.add_argument("--keep-work", action="store_true", help="保留逐鏡中間檔")
    ap.add_argument("--out", type=Path, default=None, help="輸出路徑")
    args = ap.parse_args()

    shots, _ = shotlist.build_all()
    overrides = load_overrides(args.overrides)

    # L cut 到片尾：DX 最後一句若超過 60 秒，延長最後一鏡
    tail_frames = 0
    if args.tail == "auto" and DX_TRACK.exists():
        over = dx_end_seconds(DX_TRACK) - 60.0
        if over > 0.02:
            tail_frames = min(int(-(-over * FPS // 1)), 110)  # ceil，素材上限 124 幀
            print(f"DX 尾音超出 {over:.2f}s → 最後一鏡延長 {tail_frames} 幀")

    work = CUTS_DIR / "_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    CUTS_DIR.mkdir(parents=True, exist_ok=True)

    out = args.out or (
        CUTS_DIR / f"雌雄_粗剪_16x9_粵語_{args.round}.mp4"
    )

    picks: dict[int, str] = {}
    seg_files: list[Path] = []
    rows: list[dict] = []

    for si, s in enumerate(shots):
        no = int(s["no"])
        pick = overrides.get(no, args.round)
        src = clip_path(no, pick)
        if not src.exists():
            raise FileNotFoundError(f"缺少片段：{src}")
        start_f = round(s["start"] * FPS)
        end_f = round(s["end"] * FPS)
        n = end_f - start_f
        if si == len(shots) - 1:
            n += tail_frames  # 片尾延長，讓最後一句講完
        seg = work / f"seg_{no:02d}.mov"
        encode_segment(src, seg, n, ambience=not args.no_ambience)
        seg_files.append(seg)
        picks[no] = pick
        rows.append({
            "no": no, "start_f": start_f, "end_f": end_f, "frames": n,
            "pick": pick, "src": src.name,
        })
        print(f"  鏡 {no:02d}  {s['start']:5.2f}–{s['end']:5.2f}s  "
              f"{n:3d} 幀  ← {src.name}")

    listfile = work / "concat.txt"
    listfile.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in seg_files), encoding="utf-8"
    )
    joined = work / "joined.mov"
    print("串接 45 段…")
    concat_segments(listfile, joined)

    print("混對白＋環境聲…")
    total = sum(r["frames"] for r in rows) / FPS
    final_mix(
        joined, DX_TRACK, SRT, out,
        ambience_gain=0.0 if args.no_ambience else args.ambience_gain,
        with_subs=not args.no_subs,
        total=total,
    )

    manifest = {
        "round": args.round,
        "overrides": {str(k): v for k, v in overrides.items()},
        "ambience_gain": 0.0 if args.no_ambience else args.ambience_gain,
        "subs": not args.no_subs,
        "fps": FPS,
        "size": f"{OUT_W}x{OUT_H}",
        "frames": sum(r["frames"] for r in rows),
        "tail_frames": tail_frames,
        "shots": rows,
        "dx": str(DX_TRACK.relative_to(ROOT)),
        "out": str(out.relative_to(ROOT)),
    }
    man_path = out.with_suffix(".json")
    man_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if not args.keep_work:
        shutil.rmtree(work)

    dur = probe_duration(out)
    print(f"\n完成：{out}")
    print(f"  時長 {dur:.3f}s（{manifest['frames']} 幀 @{FPS}fps）")
    print(f"  字幕 {'有（軟字幕）' if not args.no_subs else '無'}；"
          f"環境聲 {manifest['ambience_gain']}")
    print(f"  紀錄 {man_path}")


if __name__ == "__main__":
    main()
