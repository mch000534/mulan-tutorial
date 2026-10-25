#!/usr/bin/env python3
"""《雌雄》AI 配音（備用方案）

正式版已改為真人錄音，見 `design/07-配音執行包-真人錄音與AI備援.md`。
本腳本保留作為「真人未到齊時的佔位音」與「純合成旁白示範版」。

流程：
  1. 以參考語速生成，量測自然長度
  2. 依時間碼推算所需語速（edge-tts rate），重新生成
  3. 以 ffmpeg atempo 微調到剛好落在時間碼內
  4. 套用 design/06 §七 的後期鏈，峰值對齊 −6 dBFS

輸出預設：`assets/audio/tts_draft/`（不與真人版混放）

用法：
  python3 scripts/tts_voices.py                 # 全量
  python3 scripts/tts_voices.py --lang yue      # 只做粵語
  python3 scripts/tts_voices.py --lines V6,V7   # 只做指定句
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_common import (  # noqa: E402
    ADOPTED,
    LINES,
    OUT,
    PEAK_DBFS,
    SR,
    VERSION_LABEL,
    VOICE_LABEL,
    VOICE_ROLE,
    Line,
    atempo,
    build_dx_track,
    decode_f32,
    encode_wav,
    line_window,
    make_breath,
    normalize_peak,
    peak_dbfs,
    post_process,
    silence,
    trim_silence,
    write_manifest,
    write_srt,
)

VOICES = {
    "mand": {"female": "zh-CN-XiaoxiaoNeural", "male": "zh-CN-YunjianNeural"},
    "yue": {"female": "zh-HK-HiuMaanNeural", "male": "zh-HK-WanLungNeural"},
}

# 音高修正（半音，負數為降低），把語音庫原生音高移進 design/06 §二之一 的音域
PITCH_SHIFT = {
    ("mand", "female"): -7.0,
    ("mand", "male"): 0.0,
    ("yue", "female"): -5.5,
    ("yue", "male"): +3.0,
}

VERSIONS = {
    "A": {"pitch": {"vo": "-10Hz", "mulan": "-8Hz", "lei": "-6Hz"},
          "volume": {"vo": "-2%", "mulan": "-2%", "lei": "-2%"}},
    "B": {"pitch": {"vo": "-14Hz", "mulan": "-12Hz", "lei": "-8Hz"},
          "volume": {"vo": "-5%", "mulan": "-5%", "lei": "-5%"}},
    "C": {"pitch": {"vo": "-7Hz", "mulan": "-5Hz", "lei": "-3Hz"},
          "volume": {"vo": "+3%", "mulan": "+8%", "lei": "+10%"}},
    "EAR": {"pitch": {"vo": "-12Hz", "mulan": "-10Hz", "lei": "-8Hz"},
            "volume": {"vo": "-9%", "mulan": "-10%", "lei": "-8%"}},
}

PROBE_RATE = 0.25
MAX_RATE = 1.0
MIN_RATE = -0.45


def _patch_mkssml():
    """把 xml:lang 改成與 voice 一致（edge-tts 預設 en-US）。"""
    import edge_tts.communicate as ec

    def mkssml(tc, escaped_text):
        if isinstance(escaped_text, bytes):
            escaped_text = escaped_text.decode("utf-8")
        lang = "zh-CN"
        if tc.voice.startswith("zh-HK"):
            lang = "zh-HK"
        elif tc.voice.startswith("zh-TW"):
            lang = "zh-TW"
        return (
            "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='"
            + lang + "'><voice name='" + tc.voice + "'><prosody pitch='" + tc.pitch
            + "' rate='" + tc.rate + "' volume='" + tc.volume + "'>"
            + escaped_text + "</prosody></voice></speak>"
        )

    ec.mkssml = mkssml


async def tts_segment(text: str, voice: str, rate: str, pitch: str, volume: str, dest: Path) -> None:
    from edge_tts import Communicate

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return
    comm = Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
    data = bytearray()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            data.extend(chunk["data"])
    if not data:
        raise RuntimeError(f"no audio for {text!r}")
    dest.write_bytes(bytes(data))


def rate_str(rate: float) -> str:
    return f"{rate * 100:+.0f}%"


async def synth_parts(line: Line, lang: str, version: str, rate: float, pitch: str,
                      volume: str, tag: str, raw_dir: Path):
    role = line.role
    voice = VOICES[lang][VOICE_ROLE[role]]
    parts = line.parts_mand if lang == "mand" else line.parts_yue
    stem = f"{VOICE_LABEL[role]}_{line.vid}_{version}"
    chunks, raw_files = [], []
    for i, (text, gap) in enumerate(parts):
        tag_r = tag if tag == "probe" else f"{tag}_{rate_str(rate).replace('+', 'p').replace('-', 'm')}"
        p = raw_dir / f"{stem}_{tag_r}_seg{i}.mp3"
        await tts_segment(text, voice, rate_str(rate), pitch, volume, p)
        raw_files.append(p)
        seg = trim_silence(decode_f32(p.read_bytes()), thresh_db=-55.0)
        chunks.append(seg if seg.size else np.zeros(1))
        if gap > 0:
            chunks.append(silence(gap))
    return chunks, raw_files


@dataclass
class Result:
    lang: str
    vid: str
    version: str
    role: str
    path: str
    duration: float
    peak_dbfs: float
    rate: str
    pitch: str
    volume: str
    voice: str
    window: list[float]
    atempo: float
    chars: int
    cps: float
    fits: bool
    note: str = ""


async def build_line(line: Line, lang: str, version: str, raw_dir: Path) -> tuple[Result, np.ndarray]:
    role = line.role
    pitch = VERSIONS[version]["pitch"][role]
    volume = VERSIONS[version]["volume"][role]
    start, end, tail = line_window(line, lang)
    window = end - start
    target = window - line.breath_before

    chunks, _ = await synth_parts(line, lang, version, PROBE_RATE, pitch, volume, "probe", raw_dir)
    d0 = np.concatenate(chunks).size / SR
    if d0 <= 0:
        raise RuntimeError(f"empty audio {line.vid}")

    need = max(MIN_RATE, min(MAX_RATE, d0 * (1 + PROBE_RATE) / target - 1))
    chunks2, raw_files2 = await synth_parts(line, lang, version, need, pitch, volume, "fit", raw_dir)
    d1 = np.concatenate(chunks2).size / SR
    if abs(d1 / target - 1) > 0.04:
        need2 = max(MIN_RATE, min(MAX_RATE, (1 + need) * d1 / target - 1))
        chunks2, raw_files2 = await synth_parts(line, lang, version, need2, pitch, volume, "fit2", raw_dir)
        need = need2
        d1 = np.concatenate(chunks2).size / SR

    factor = max(0.85, min(1.15, d1 / target))
    speech = atempo(np.concatenate(chunks2), factor)

    chunks = []
    if line.breath_before > 0:
        chunks.append(make_breath(line.breath_before))
    chunks.extend(chunks2)
    full = np.concatenate(chunks)

    allowed = window + tail
    processed, _ = post_process(full, role, version, int(allowed * SR))
    dur = processed.size / SR
    if dur > allowed + 0.005:
        processed = atempo(processed, dur / allowed)
        dur = processed.size / SR
    processed = normalize_peak(processed, PEAK_DBFS)

    res = Result(
        lang=lang, vid=line.vid, version=version, role=role, path="",
        duration=round(dur, 3), peak_dbfs=round(peak_dbfs(processed), 2),
        rate=rate_str(need), pitch=pitch, volume=volume,
        voice=VOICES[lang][VOICE_ROLE[role]], window=[start, end],
        atempo=round(factor, 4), chars=line.chars,
        cps=round(line.chars / dur, 2) if dur else 0.0,
        fits=dur <= allowed + 0.02, note=line.note,
    )
    return res, processed


async def main_async(args) -> int:
    _patch_mkssml()
    langs = ["mand", "yue"] if args.lang == "all" else [args.lang]
    lines = [l for l in LINES if not args.lines or l.vid in args.lines.split(",")]
    versions = args.versions.split(",") if args.versions else list(VERSIONS.keys())
    base = (Path(args.out) if args.out else (OUT / "tts_draft")).resolve()
    raw_dir = base / "raw"

    sem = asyncio.Semaphore(args.concurrency)

    async def guarded(line, lang, version):
        async with sem:
            return await build_line(line, lang, version, raw_dir)

    tasks = [guarded(l, lang, v) for lang in langs for l in lines for v in versions]
    results: list[Result] = []
    audio: dict[tuple[str, str, str], np.ndarray] = {}
    for i, coro in enumerate(asyncio.as_completed(tasks), 1):
        r, wav = await coro
        results.append(r)
        audio[(r.lang, r.vid, r.version)] = wav
        print(f"[{i}/{len(tasks)}] {r.lang} {r.vid} {r.version} "
              f"{r.duration:.2f}s / {r.window[1] - r.window[0]:.2f}s "
              f"rate {r.rate} peak {r.peak_dbfs:.1f}dBFS {r.cps}字/s "
              f"{'OK' if r.fits else 'OVER'}", flush=True)

    results.sort(key=lambda r: (r.lang, r.vid, r.version))
    for r in results:
        folder = "9x16_mandarin" if r.lang == "mand" else "16x9_cantonese"
        dest = base / folder / f"{VOICE_LABEL[r.role]}_{r.vid}_{r.version}.wav"
        encode_wav(audio[(r.lang, r.vid, r.version)], dest)
        r.path = str(dest.relative_to(OUT.parent.parent))

    for lang in langs:
        items = [{"vid": r.vid, "version": r.version, "path": r.path}
                 for r in results if r.lang == lang]
        track = build_dx_track(items, lang)
        name = ("MULAN_60s_9x16_MANDARIN_DX.wav" if lang == "mand"
                else "MULAN_60s_16x9_CANTONESE_DX.wav")
        encode_wav(track, base / "tracks" / name)
    write_srt("mand", "MULAN_60s_9x16_zh-Hant.srt", base / "srt")
    write_srt("yue", "MULAN_60s_16x9_zh-Hant.srt", base / "srt")
    write_srt("yue", "MULAN_60s_16x9_yue-Hant.srt", base / "srt")

    write_manifest(base / "manifest.json", [r.__dict__ for r in results],
                   extra={"pipeline": "scripts/tts_voices.py（AI 備用方案）",
                          "note": "AI 備用方案，非定稿；正式版見 assets/audio/9x16_mandarin 等目錄"})
    print(f"\n完成：{len(results)} 個檔案 → {base}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="all", choices=["all", "mand", "yue"])
    ap.add_argument("--lines", default="")
    ap.add_argument("--versions", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
