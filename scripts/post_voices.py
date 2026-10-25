#!/usr/bin/env python3
"""《雌雄》真人錄音的後期、對點與驗收

輸入：配音員回收的乾聲（任意格式，ffmpeg 可解碼即可）
      `assets/audio/recorded_raw/9x16_mandarin/`、`assets/audio/recorded_raw/16x9_cantonese/`
      檔名規則見 `design/07-配音執行包-真人錄音與AI備援.md` §八：`{ROLE}_{VID}_{VERSION}.wav`

輸出：
  `assets/audio/9x16_mandarin/`、`assets/audio/16x9_cantonese/`  處理後單句 WAV
  `assets/audio/tracks/*_DX.wav`                              60 秒對點對白軌
  `assets/audio/srt/*.srt`                                    字幕
  `assets/audio/manifest.json`                                每檔參數與驗收數值
  `assets/audio/驗收報告.md`                                  回收驗收表

用法：
  python3 scripts/post_voices.py                     # 兩種語言都做
  python3 scripts/post_voices.py --lang yue          # 只做粵語
  python3 scripts/post_voices.py --fit stretch       # 超長時自動微調速度對齊
  python3 scripts/post_voices.py --check             # 只檢查長度與峰值，不輸出
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_common import (  # noqa: E402
    ADOPTED,
    FOLDER,
    LINES,
    OUT,
    PEAK_DBFS,
    ROLE_LABEL,
    SR,
    VERSION_LABEL,
    VOICE_LABEL,
    build_dx_track,
    decode_f32,
    encode_wav,
    find_line,
    line_window,
    normalize_peak,
    peak_dbfs,
    post_process,
    rms_dbfs,
    trim_silence,
    atempo,
    write_manifest,
    write_srt,
)

RAW_DIR = OUT / "recorded_raw"
LANG_LABEL = {"mand": "9:16 普通話", "yue": "16:9 粵語"}


@dataclass
class Item:
    lang: str
    vid: str
    version: str
    role: str
    path: str = ""
    source: str = ""
    duration: float = 0.0
    raw_duration: float = 0.0
    peak_dbfs: float = 0.0
    rms_dbfs: float = 0.0
    window: list[float] = field(default_factory=list)
    fits: bool = True
    fit_action: str = ""
    note: str = ""
    missing: bool = False


def process(lang: str, version: str, line, src: Path, out_dir: Path,
            fit: str, check_only: bool) -> Item:
    role = line.role
    stem = f"{VOICE_LABEL[role]}_{line.vid}_{version}"
    src_file = src / f"{stem}.wav"
    # 也接受其他副檔名（mp3/m4a/aiff…）
    if not src_file.exists():
        cands = sorted(src.glob(f"{stem}.*"))
        src_file = cands[0] if cands else src_file

    start, end, tail = line_window(line, lang)
    window = end - start
    allowed = window + tail
    item = Item(lang=lang, vid=line.vid, version=version, role=role,
                window=[start, end], note=line.note)

    if not src_file.exists():
        item.missing = True
        item.fits = False
        item.fit_action = "缺檔"
        return item

    item.source = str(src_file.relative_to(OUT.parent.parent))
    raw = decode_f32(src_file.read_bytes())
    item.raw_duration = round(raw.size / SR, 3)
    speech = trim_silence(raw, thresh_db=-50.0)
    if speech.size == 0:
        item.missing = True
        item.fit_action = "無聲音"
        return item
    item.duration = round(speech.size / SR, 3)

    # 長度處理：說話本體要塞進視窗（殘響尾巴另外算）
    body = speech
    if item.duration > window + 0.02:
        if fit == "stretch":
            k = item.duration / window
            body = atempo(body, min(k, 1.10))
            item.fit_action = f"微調速度 {1/k:.3f}×"
        elif fit == "trim":
            body = body[: int(window * SR)]
            item.fit_action = "裁掉尾端"
        else:
            item.fit_action = f"超出視窗 {item.duration - window:+.2f}s（未處理）"
    elif item.duration < window - 0.02:
        item.fit_action = f"短於視窗 {item.duration - window:+.2f}s（可接受）"
    else:
        item.fit_action = "剛好"

    allowed_samples = int(allowed * SR)
    processed, chain = post_process(body, role, version, allowed_samples)
    processed = normalize_peak(processed, PEAK_DBFS)

    dur = processed.size / SR
    item.duration = round(dur, 3)
    item.peak_dbfs = round(peak_dbfs(processed), 2)
    item.rms_dbfs = round(rms_dbfs(processed), 2)
    item.fits = (start + dur) <= (end + tail + 0.02)

    if not check_only:
        dest = out_dir / f"{stem}.wav"
        encode_wav(processed, dest)
        item.path = str(dest.relative_to(OUT.parent.parent))
    return item


def write_report(items: list[Item], path: Path) -> None:
    lines = [
        "# 《雌雄》配音回收驗收報告",
        "",
        f"產生時間：{__import__('datetime').datetime.now():%Y-%m-%d %H:%M}",
        "",
        "時間碼依 `design/04` V1.1（放寬版）；峰值基準 −6 dBFS。",
        "",
        "## 逐句結果",
        "",
        "| 語言 | 句 | 角色 | 版本 | 視窗 | 實測長度 | 峰值 | 對點 | 處理 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for it in sorted(items, key=lambda i: (i.lang, i.vid, i.version)):
        if it.missing:
            lines.append(f"| {LANG_LABEL[it.lang]} | {it.vid} | {ROLE_LABEL[it.role]} | "
                         f"{it.version} {VERSION_LABEL[it.version]} | "
                         f"{it.window[0]:.2f}–{it.window[1]:.2f} | — | — | ❌ | {it.fit_action} |")
            continue
        mark = "✅" if it.fits else "⚠️"
        lines.append(
            f"| {LANG_LABEL[it.lang]} | {it.vid} | {ROLE_LABEL[it.role]} | "
            f"{it.version} {VERSION_LABEL[it.version]} | "
            f"{it.window[0]:.2f}–{it.window[1]:.2f} | {it.duration:.2f}s | "
            f"{it.peak_dbfs:.1f} dBFS | {mark} | {it.fit_action} |"
        )

    over = [i for i in items if not i.missing and not i.fits]
    missing = [i for i in items if i.missing]

    lines += ["", "## 檢查摘要", ""]
    lines.append(f"- 應收 {len(items)} 檔，實收 {len(items) - len(missing)} 檔")
    lines.append(f"- 超出視窗：{len(over)} 檔")
    lines.append(f"- 缺檔：{len(missing)} 檔")
    if over:
        lines.append("")
        lines.append("### 超出視窗")
        for it in over:
            lines.append(f"- {LANG_LABEL[it.lang]} {it.vid} {it.version}：{it.fit_action}")
    if missing:
        lines.append("")
        lines.append("### 缺檔")
        for it in missing:
            lines.append(f"- {LANG_LABEL[it.lang]} {it.vid} {it.version}（{ROLE_LABEL[it.role]}）")

    lines += [
        "",
        "## 需要用耳朵確認的項目（數值驗證不了）",
        "",
        "- [ ] 木蘭與 VO 是同一人；VO 更近、更低、更冷",
        "- [ ] 所有句尾沒有播音腔式下墜",
        "- [ ] V5 的「乾」、V7 的真結巴與破音、V8 的懸空句尾",
        "- [ ] 粵語版高風險字詞讀音（帖 tip3／騎 kei4／傍 bong6／雌 ci1／還 waan4／長 zoeng2）",
        "- [ ] 沒有噴麥、吞字、爆音；呼吸保留且沒有降噪造成的抽氣聲",
        "- [ ] 大殿殘響只出現在 S7（V6），其餘為乾聲",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="all", choices=["all", "mand", "yue"])
    ap.add_argument("--versions", default="A,B,C,EAR")
    ap.add_argument("--src", default=str(RAW_DIR))
    ap.add_argument("--fit", default="none", choices=["none", "trim", "stretch"],
                    help="超出視窗時的處理：none=只標示、trim=裁尾、stretch=微調速度")
    ap.add_argument("--check", action="store_true", help="只檢查，不輸出檔案")
    args = ap.parse_args()

    langs = ["mand", "yue"] if args.lang == "all" else [args.lang]
    versions = args.versions.split(",")
    src_root = Path(args.src)

    items: list[Item] = []
    for lang in langs:
        src = src_root / FOLDER[lang]
        out_dir = OUT / FOLDER[lang]
        for line in LINES:
            for v in versions:
                it = process(lang, v, line, src, out_dir, args.fit, args.check)
                items.append(it)
                flag = "缺" if it.missing else ("OK" if it.fits else "OVER")
                print(f"{LANG_LABEL[lang]:9s} {it.vid} {it.version:3s} "
                      f"{it.duration:5.2f}s / {it.window[1] - it.window[0]:.2f}s  "
                      f"peak {it.peak_dbfs:6.2f}dBFS  {flag:5s} {it.fit_action}", flush=True)

    if args.check:
        write_report(items, OUT / "驗收報告.md")
        print(f"\n檢查完成 → {OUT / '驗收報告.md'}")
        return 0

    # DX 對白軌與字幕
    for lang in langs:
        lang_items = [i for i in items if i.lang == lang and i.path]
        track = build_dx_track([{"vid": i.vid, "version": i.version, "path": i.path} for i in lang_items], lang)
        name = ("MULAN_60s_9x16_MANDARIN_DX.wav" if lang == "mand"
                else "MULAN_60s_16x9_CANTONESE_DX.wav")
        encode_wav(track, OUT / "tracks" / name)
    write_srt("mand", "MULAN_60s_9x16_zh-Hant.srt", OUT / "srt")
    write_srt("yue", "MULAN_60s_16x9_zh-Hant.srt", OUT / "srt")
    write_srt("yue", "MULAN_60s_16x9_yue-Hant.srt", OUT / "srt")

    manifest_items = []
    for it in items:
        d = it.__dict__.copy()
        d["post_chain"] = None
        manifest_items.append(d)
    write_manifest(
        OUT / "manifest.json",
        manifest_items,
        extra={"pipeline": "scripts/post_voices.py", "source": "真人錄音",
               "fit_mode": args.fit},
    )
    write_report(items, OUT / "驗收報告.md")

    missing = [i for i in items if i.missing]
    over = [i for i in items if not i.missing and not i.fits]
    print(f"\n輸出 → {OUT}")
    print(f"缺檔 {len(missing)}／超出視窗 {len(over)}／合計 {len(items)}")
    print(f"驗收報告 → {OUT / '驗收報告.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
