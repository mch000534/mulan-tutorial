#!/usr/bin/env python3
"""MiniMax 產出的語音 → 專案回收格式

讀入 `assets/audio/minimax/{mandarin,cantonese}/V*.wav`，
做兩件事：
  1. 停頓符合化：把模型過長的停頓壓到 `design/05` 的設計預算（保留相對結構）
  2. 對點：以 atempo 微調到 `design/04` V1.1 的時間碼（不變調），補／裁靜音

輸出到 `assets/audio/recorded_raw/{9x16_mandarin,16x9_cantonese}/`，
檔名沿用 `design/07 §八`：`{ROLE}_{VID}_{ADOPTED}.wav`，可直接餵給 `post_voices.py`。

用法：
  python3 scripts/minimax_import.py                 # 轉換＋整形＋對點
  python3 scripts/minimax_import.py --dry-run       # 只看數字，不寫檔
  python3 scripts/minimax_import.py --no-conform    # 不動停頓，只對點
  python3 scripts/minimax_import.py --max-tempo 1.0 # 禁止變速（只用裁切／補白）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_common import (  # noqa: E402
    ADOPTED,
    DESIGN_PAUSE_BUDGET,
    FOLDER,
    LINES,
    OUT,
    SR,
    VOICE_LABEL,
    conform_pauses,
    decode_f32,
    encode_wav,
    find_line,
    fit_window,
    line_window,
)

SRC_DIR = OUT / "minimax"
LANG_SRC = {"mand": "mandarin", "yue": "cantonese"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="all", choices=["all", "mand", "yue"])
    ap.add_argument("--src", default=str(SRC_DIR))
    ap.add_argument("--no-conform", action="store_true", help="不做停頓符合化")
    ap.add_argument("--max-tempo", type=float, default=1.30)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src_root = Path(args.src)
    langs = ["mand", "yue"] if args.lang == "all" else [args.lang]
    rows = []

    for lang in langs:
        srcdir = src_root / LANG_SRC[lang]
        if not srcdir.exists():
            print(f"找不到來源目錄：{srcdir}")
            continue
        for line in LINES:
            src = srcdir / f"{line.vid}.wav"
            if not src.exists():
                print(f"缺檔：{src}")
                continue
            st, en, tail = line_window(line, lang)
            window = en - st
            raw = decode_f32(src.read_bytes())
            orig = raw.size / SR

            if args.no_conform:
                work = raw
                pstats = {}
            else:
                work, pstats = conform_pauses(raw, DESIGN_PAUSE_BUDGET[line.vid])

            work, factor = fit_window(work, window, args.max_tempo)
            final = work.size / SR
            over = final - window

            version = ADOPTED[line.vid]
            dest = (OUT / "recorded_raw" / FOLDER[lang]
                    / f"{VOICE_LABEL[line.role]}_{line.vid}_{version}.wav")
            if not args.dry_run:
                encode_wav(work, dest)

            rows.append((lang, line.vid, version, orig, pstats.get("new_total", orig),
                         final, window, factor, pstats.get("scale", 1.0),
                         len(pstats.get("major_gaps", [])), dest))
            print(f"{lang} {line.vid} {version}: 原 {orig:5.2f}s → 停頓整形 {pstats.get('new_total', orig):5.2f}s "
                  f"→ 對點 {final:5.2f}s（視窗 {window:.2f}s）atempo {factor:.3f} "
                  f"停頓縮放 {pstats.get('scale', 1.0)}", flush=True)

    if args.dry_run:
        print("\n--dry-run：未寫檔")
        return 0

    print("\n| 語言 | 句 | 版本 | 原長 | 整形後 | 對點後 | 視窗 | atempo | 停頓縮放 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]:.2f}s | {r[4]:.2f}s | {r[5]:.2f}s | "
              f"{r[6]:.2f}s | {r[7]:.3f} | {r[8]} |")
    print(f"\n輸出 → {OUT / 'recorded_raw'}")
    print(f"接著執行：python3 scripts/post_voices.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
