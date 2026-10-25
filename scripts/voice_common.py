#!/usr/bin/env python3
"""《雌雄》配音共用模組

集中管理：
  · 時間碼與台詞（`design/02` V1.1、`design/03` V1.1）
  · 角色、版本定義
  · DSP 工具與 `design/06 §七` 的後期處理鏈

被 `tts_voices.py`（AI 備用方案）與 `post_voices.py`（真人錄音正式方案）共用。
"""

from __future__ import annotations

import json
import math
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "audio"
SR = 48000
PEAK_DBFS = -6.0  # design/06：對白峰值 -6 dBFS

VOICE_ROLE = {"vo": "female", "mulan": "female", "lei": "male"}
VOICE_LABEL = {"vo": "VO", "mulan": "MULAN", "lei": "LEI"}
ROLE_LABEL = {"vo": "旁白 VO（木蘭內心）", "mulan": "木蘭台詞", "lei": "老雷"}

# 每句建議採用版本（design/03 §六）
ADOPTED = {**{f"V{i}": "A" for i in [1, 2, 3, 4, 5, 8]}, "V6": "C", "V7": "C"}

VERSION_LABEL = {
    "A": "冷靜版",
    "B": "壓抑版",
    "C": "外放版",
    "EAR": "貼耳版",
}

FOLDER = {"mand": "9x16_mandarin", "yue": "16x9_cantonese"}


# ---------------------------------------------------------------------------
# 時間碼與台詞
# ---------------------------------------------------------------------------


@dataclass
class Line:
    vid: str
    role: str
    start: float
    end: float
    text_mand: str
    text_yue: str
    parts_mand: list[tuple[str, float]] = field(default_factory=list)
    parts_yue: list[tuple[str, float]] = field(default_factory=list)
    breath_before: float = 0.0  # 開口的吸氣（秒）
    tail: float = 0.0  # 台詞結束後殘響可延伸的秒數（僅 S7 大殿）
    end_yue: float | None = None  # 粵語版時間碼（design/03 §三）
    tail_yue: float | None = None
    note: str = ""
    chars: int = 0


LINES: list[Line] = [
    Line(
        "V1", "vo", 1.0, 4.35,
        "誰說，踩著萬具枯骨走回來的……不能是個女人？",
        "誰說，踩著萬具枯骨走回來的……不能是個女人？",
        parts_mand=[("誰說，踩著萬具枯骨走回來的……不能是個女人？", 0.0)],
        parts_yue=[("誰說，踩著萬具枯骨走回來的……不能是個女人？", 0.0)],
        chars=18,
        note="跨剪輯點，句尾落在織布機鏡頭（00:03.0–00:04.4）；「不能」要輕，句尾微微上揚",
    ),
    Line(
        "V2", "vo", 4.6, 8.6,
        "軍帖十二卷，卷卷有爺名。阿爺無長子，木蘭無長兄。",
        "軍帖十二卷，卷卷有爺名。阿爺無長子，木蘭無長兄。",
        parts_mand=[("軍帖十二卷，卷卷有爺名。阿爺無長子，木蘭無長兄。", 0.0)],
        parts_yue=[("軍帖十二卷，卷卷有爺名。阿爺無長子，木蘭無長兄。", 0.0)],
        chars=20,
        note="像在數東西；「十二」要清楚；第二句更輕",
    ),
    Line(
        "V3", "vo", 16.2, 18.8,
        "萬里赴戎機，關山度若飛。",
        "萬里赴戎機，關山度若飛。",
        parts_mand=[("萬里赴戎機，關山度若飛。", 0.0)],
        parts_yue=[("萬里赴戎機，關山度若飛。", 0.0)],
        chars=10,
        note="氣息長，一句到底；「飛」往前送",
    ),
    Line(
        "V4", "vo", 22.6, 25.2,
        "不聞爺娘喚女聲。唯聞胡騎鳴啾啾。",
        "不聞爺娘喚女聲。唯聞胡騎鳴啾啾。",
        parts_mand=[("不聞爺娘喚女聲。唯聞胡騎鳴啾啾。", 0.0)],
        parts_yue=[("不聞爺娘喚女聲。唯聞胡騎鳴啾啾。", 0.0)],
        chars=14,
        note="前半空；後半降一半音量；「啾啾」要冷不可愛",
    ),
    Line(
        "V5", "vo", 30.9, 34.7,
        "將軍百戰死。壯士十年歸。",
        "將軍百戰死。壯士十年歸。",
        parts_mand=[("將軍百戰死。壯士十年歸。", 0.0)],
        parts_yue=[("將軍百戰死。壯士十年歸。", 0.0)],
        chars=10,
        note="全片最慢；「死」要乾；疲憊而非悲傷",
    ),
    Line(
        "V6", "mulan", 39.4, 42.4,
        "木蘭不用尚書郎！願借明駝千里足，送兒還故鄉！",
        "木蘭唔做尚書郎！願借明駝千里足，送兒還故鄉！",
        parts_mand=[("木蘭不用尚書郎！願借明駝千里足，送兒還故鄉！", 0.0)],
        # 粵語語音庫語速偏慢，首句用逗號取代驚嘆號
        parts_yue=[("木蘭唔做尚書郎，願借明駝千里足，送兒還故鄉！", 0.0)],
        breath_before=0.22,
        tail=0.6,
        end_yue=42.6,
        tail_yue=0.4,
        chars=19,
        note="胸腔、平等、不顫；開頭吸氣要收進麥裡；大殿殘響 1.8s",
    ),
    Line(
        "V7", "lei", 54.3, 57.3,
        "同……同行十二年，你、你竟是個女郎？！",
        "同……同行十二年，你、你竟然係個女仔？！",
        parts_mand=[("同……", 0.25), ("同行十二年。", 0.12), ("你、你竟是個女郎？！", 0.0)],
        parts_yue=[("同……", 0.25), ("同行十二年。", 0.12), ("你、你竟然係個女仔？！", 0.0)],
        chars=14,
        note="真結巴、破音、氣息收不住；最後三個字往上飄",
    ),
    Line(
        "V8", "vo", 57.4, 59.9,
        "雙兔傍地走。安能辨我是雄雌？",
        "雙兔傍地走。安能辨我是雄雌？",
        parts_mand=[("雙兔傍地走。安能辨我是雄雌？", 0.0)],
        parts_yue=[("雙兔傍地走。安能辨我是雄雌？", 0.0)],
        chars=12,
        note="帶一點笑、釋然；句尾不要收",
    ),
]


def line_window(line: Line, lang: str) -> tuple[float, float, float]:
    """回傳 (起, 訖, 殘響尾巴秒數)，粵語版依 design/03 調整 V6。"""
    end = line.end
    tail = line.tail
    if lang == "yue":
        if line.end_yue is not None:
            end = line.end_yue
        if line.tail_yue is not None:
            tail = line.tail_yue
    return line.start, end, tail


def line_text(line: Line, lang: str) -> str:
    return line.text_mand if lang == "mand" else line.text_yue


def find_line(vid: str) -> Line:
    return next(l for l in LINES if l.vid == vid)


# 字幕（design/03 §四、design/03 §七）
SUBTITLES: dict[str, list[tuple[float, float, list[str]]]] = {
    "mand": [
        (1.2, 4.30, ["誰說，踩著萬具枯骨", "走回來的不能是個女人？"]),
        (4.8, 8.55, ["軍帖十二卷，卷卷有爺名", "阿爺無長子，木蘭無長兄"]),
        (16.4, 18.75, ["萬里赴戎機", "關山度若飛"]),
        (22.8, 25.15, ["不聞爺娘喚女聲", "唯聞胡騎鳴啾啾"]),
        (31.1, 34.65, ["將軍百戰死", "壯士十年歸"]),
        (39.7, 42.35, ["木蘭不用尚書郎", "願借明駝千里足，送兒還故鄉"]),
        (54.5, 57.25, ["同行十二年", "你竟是個女郎？！"]),
        (57.6, 59.85, ["雙兔傍地走", "安能辨我是雄雌"]),
    ],
    "yue": [
        (1.2, 4.30, ["誰說，踩著萬具枯骨", "走回來的不能是個女人？"]),
        (4.8, 8.55, ["軍帖十二卷，卷卷有爺名", "阿爺無長子，木蘭無長兄"]),
        (16.4, 18.75, ["萬里赴戎機", "關山度若飛"]),
        (22.8, 25.15, ["不聞爺娘喚女聲", "唯聞胡騎鳴啾啾"]),
        (31.1, 34.65, ["將軍百戰死", "壯士十年歸"]),
        (39.7, 42.55, ["木蘭唔做尚書郎", "願借明駝千里足，送兒還故鄉"]),
        (54.5, 57.25, ["同行十二年", "你竟然係個女仔？！"]),
        (57.6, 59.85, ["雙兔傍地走", "安能辨我是雄雌"]),
    ],
}


# ---------------------------------------------------------------------------
# DSP 工具
# ---------------------------------------------------------------------------


def ffmpeg_bytes(*args: str, stdin: bytes | None = None) -> bytes:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *args]
    p = subprocess.run(cmd, input=stdin, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{p.stderr.decode()}")
    return p.stdout


def decode_f32(data: bytes) -> np.ndarray:
    out = ffmpeg_bytes(
        "-i", "pipe:0", "-f", "f32le", "-ar", str(SR), "-ac", "1", "pipe:1", stdin=data
    )
    return np.frombuffer(out, dtype="<f4").astype(np.float64)


def filter_audio(x: np.ndarray, chain: list[str]) -> np.ndarray:
    if not chain:
        return x
    args = []
    for c in chain:
        args += ["-filter:a", c]
    out = ffmpeg_bytes(
        "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "pipe:0",
        *args, "-f", "f32le", "pipe:1",
        stdin=x.astype("<f4").tobytes(),
    )
    return np.frombuffer(out, dtype="<f4").astype(np.float64)


def encode_wav(samples: np.ndarray, dest: Path) -> None:
    """寫 48k / 24bit / mono WAV。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    ints = np.clip(np.round(clipped * 8388607.0), -8388608, 8388607).astype(np.int64)
    u = (ints & 0xFFFFFF).astype(np.uint32)
    b = np.empty((u.size, 3), dtype=np.uint8)
    b[:, 0] = (u & 0xFF).astype(np.uint8)
    b[:, 1] = ((u >> 8) & 0xFF).astype(np.uint8)
    b[:, 2] = ((u >> 16) & 0xFF).astype(np.uint8)
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(SR)
        w.writeframes(b.tobytes())


def db(x: float) -> float:
    return 20.0 * math.log10(max(x, 1e-12))


def peak_dbfs(x: np.ndarray) -> float:
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    return db(peak)


def rms_dbfs(x: np.ndarray) -> float:
    if x.size == 0:
        return -120.0
    return db(float(np.sqrt(np.mean(x ** 2))))


def trim_silence(x: np.ndarray, thresh_db: float = -55.0, keep: float = 0.0) -> np.ndarray:
    """裁掉頭尾靜默；keep 為保留的秒數。"""
    if x.size == 0:
        return x
    peak = float(np.max(np.abs(x)))
    if peak <= 0:
        return x
    mask = np.abs(x) > peak * (10 ** (thresh_db / 20.0))
    if not mask.any():
        return x
    idx = np.where(mask)[0]
    a = max(0, idx[0] - int(keep * SR))
    b = min(len(x), idx[-1] + 1 + int(keep * SR))
    return x[a:b]


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(round(seconds * SR)), dtype=np.float64)


def atempo(x: np.ndarray, factor: float) -> np.ndarray:
    """用 ffmpeg atempo 微調速度，保持音色。"""
    if abs(factor - 1.0) < 0.005:
        return x
    chain = []
    f = factor
    while f > 2.0:
        chain.append(2.0)
        f /= 2.0
    while f < 0.5:
        chain.append(0.5)
        f /= 0.5
    chain.append(f)
    filt = ",".join(f"atempo={c:.6f}" for c in chain)
    return filter_audio(x, [filt])


def saturate(x: np.ndarray, amount: float = 0.16) -> np.ndarray:
    """輕度諧波失真（tanh），給老雷粗礫感。"""
    drive = 1 + amount * 3
    return np.tanh(x * drive) / math.tanh(drive)


def make_hall_ir(seconds: float = 1.8, decay: float = 2.6, seed: int = 7) -> np.ndarray:
    """大殿殘響 IR：早期反射 + 指數衰減噪聲尾巴。"""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    ir = rng.normal(0, 1, n) * np.exp(-decay * np.linspace(0, 1, n))
    for delay_ms, amp in [(17, 0.5), (29, 0.42), (43, 0.34), (67, 0.28), (91, 0.22)]:
        d = int(delay_ms / 1000 * SR)
        if d < n:
            ir[d] += amp
    ir /= np.max(np.abs(ir)) * 1.4
    return ir


def convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """回傳完整卷積（含殘響尾巴）。"""
    n = len(x) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    X = np.fft.rfft(x, size)
    H = np.fft.rfft(ir, size)
    return np.fft.irfft(X * H, size)[:n]


def make_breath(seconds: float, seed: int = 3) -> np.ndarray:
    """吸氣：帶通白噪聲 + 漸強漸弱包徵（收進麥裡）。"""
    dur = f"{seconds:.3f}"
    chain = (
        f"anoisesrc=color=brown:duration={dur}:amplitude=1:sample_rate={SR}:seed={seed},"
        f"highpass=f=500,bandpass=f=1500:width_type=h:w=900,"
        f"afade=t=in:st=0:d={seconds * 0.45:.3f},"
        f"afade=t=out:st={seconds * 0.55:.3f}:d={seconds * 0.45:.3f},"
        f"volume=0.32"
    )
    out = ffmpeg_bytes("-f", "lavfi", "-i", chain, "-f", "f32le", "-ac", "1", "-ar", str(SR), "pipe:1")
    return np.frombuffer(out, dtype="<f4").astype(np.float64)


# ---------------------------------------------------------------------------
# 後期鏈（design/06 §七）
# ---------------------------------------------------------------------------

PROFILES = {
    # VO／乾聲：HPF 70 → De-ess → EQ 200 -2dB, 3k +1dB → Compressor 2.5:1 → 無殘響
    "dry": [
        "highpass=f=70:poles=2",
        "deesser=i=0.35:m=0.5:f=0.5:s=0",
        "equalizer=f=200:t=q:w=1:g=-2",
        "equalizer=f=3000:t=q:w=1:g=1",
        "acompressor=threshold=0.125:ratio=2.5:attack=10:release=80:makeup=1.4:detection=rms",
    ],
    # 木蘭台詞：HPF 80 → De-ess → EQ 200 -2dB, 3k +1.5dB → Compressor 3:1 → 大殿 1.8s（乾濕 7:3）
    "hall": [
        "highpass=f=80:poles=2",
        "deesser=i=0.35:m=0.5:f=0.5:s=0",
        "equalizer=f=200:t=q:w=1:g=-2",
        "equalizer=f=3000:t=q:w=1:g=1.5",
        "acompressor=threshold=0.1:ratio=3:attack=10:release=80:makeup=1.8:detection=rms",
    ],
    # 貼耳版：更近、更小聲、氣息更明顯；高頻收、無殘響
    "ear": [
        "highpass=f=90:poles=2",
        "deesser=i=0.2:m=0.5:f=0.5:s=0",
        "equalizer=f=200:t=q:w=1:g=1",
        "equalizer=f=3000:t=q:w=1:g=-1",
        "equalizer=f=8000:t=q:w=1:g=-3",
        "equalizer=f=9000:t=h:w=1:g=-6",
        "acompressor=threshold=0.16:ratio=2:attack=10:release=80:makeup=1.2:detection=rms",
    ],
    # 老雷：HPF 90 → 少量飽和（numpy 端）→ EQ 300 +1dB → Compressor 3:1
    "lei": [
        "highpass=f=90:poles=2",
        "equalizer=f=300:t=q:w=1:g=1",
        "acompressor=threshold=0.1:ratio=3:attack=10:release=80:makeup=1.8:detection=rms",
    ],
}


def post_process(x: np.ndarray, role: str, version: str, allowed_samples: int | None = None
                 ) -> tuple[np.ndarray, list[str]]:
    """依角色與版本套用後期鏈。殘響只出現在 S7 大殿（木蘭台詞）。"""
    if role == "lei":
        chain = PROFILES["lei"]
        y = saturate(x, 0.16)
    elif role == "mulan":
        chain = PROFILES["hall"]
        y = x
    elif version == "EAR":
        chain = PROFILES["ear"]
        y = x
    else:
        chain = PROFILES["dry"]
        y = x
    y = filter_audio(y, chain)
    if role == "mulan":
        ir = make_hall_ir()
        wet = convolve(y, ir)
        dry = np.zeros_like(wet)
        dry[: len(y)] = y
        y = 0.7 * dry + 0.3 * wet
        y = y * (np.max(np.abs(x)) / max(np.max(np.abs(y)), 1e-9)) * 0.95
        if allowed_samples and len(y) > allowed_samples:
            y = y[:allowed_samples]
    return y, chain


def normalize_peak(x: np.ndarray, target_dbfs: float = PEAK_DBFS) -> np.ndarray:
    peak = peak_dbfs(x)
    if peak > -60:
        return x * (10 ** ((target_dbfs - peak) / 20.0))
    return x


# ---------------------------------------------------------------------------
# AI 語音整形：停頓符合化 + 時間碼對齊
# ---------------------------------------------------------------------------

# 各句「設計停頓總量」（design/05 斷句：`／` 0.2s、`∥` 0.5s、`…` 0.4s）
DESIGN_PAUSE_BUDGET = {
    "V1": 0.80, "V2": 0.90, "V3": 0.20, "V4": 0.50,
    "V5": 0.50, "V6": 0.95, "V7": 1.05, "V8": 0.50,
}


def detect_segments(x: np.ndarray, thr_db: float = -42.0, rel: float = 0.02,
                    min_gap: float = 0.15) -> list[tuple[float, float]]:
    """回傳有聲片段（秒）。低於 min_gap 的間隙視為同一個短語內的自然斷裂。"""
    if x.size == 0:
        return []
    w = max(1, int(0.01 * SR))
    n = x.size // w
    if n == 0:
        return []
    env = np.sqrt(np.mean(x[: n * w].reshape(-1, w) ** 2, axis=1))
    thr = max(env.max() * rel, 10 ** (thr_db / 20.0))
    on = env > thr
    raw: list[list[float]] = []
    i = 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            raw.append([i * 0.01, j * 0.01])
            i = j
        else:
            i += 1
    if not raw:
        return []
    merged = [raw[0]]
    for s, e in raw[1:]:
        if s - merged[-1][1] <= min_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def conform_pauses(x: np.ndarray, pause_budget: float, min_gap: float = 0.15,
                   floor: float = 0.08) -> tuple[np.ndarray, dict]:
    """把過長的停頓按比例壓到設計預算，同時保留原有的相對結構。

    回傳 (處理後音訊, 統計)。
    """
    segs = detect_segments(x, min_gap=min_gap)
    stats = {"segments": len(segs), "pause_before": 0.0, "pause_after": 0.0,
             "major_gaps": [], "total": x.size / SR}
    if not segs:
        return x, stats

    gaps: list[float] = []
    for i in range(len(segs) - 1):
        gaps.append(segs[i + 1][0] - segs[i][1])
    stats["pause_before"] = segs[0][0]
    stats["pause_after"] = x.size / SR - segs[-1][1]

    major_idx = [i for i, g in enumerate(gaps) if g >= min_gap]
    major_total = sum(gaps[i] for i in major_idx)
    scale = 1.0
    if major_total > 0 and pause_budget > 0:
        scale = min(1.0, pause_budget / major_total)

    chunks = []
    if segs[0][0] > 0:
        chunks.append(x[: int(segs[0][0] * SR)])
    for i, (s, e) in enumerate(segs):
        chunks.append(x[int(s * SR): int(e * SR)])
        if i < len(gaps):
            g = gaps[i]
            if i in major_idx:
                new_g = max(floor, g * scale)
                stats["major_gaps"].append(round(g, 3))
            else:
                new_g = g
            chunks.append(silence(new_g))
    stats["scale"] = round(scale, 3)
    stats["new_total"] = sum(c.size for c in chunks) / SR
    return np.concatenate(chunks), stats


def fit_window(x: np.ndarray, target_seconds: float, max_tempo: float = 1.30,
               truncate: bool = False) -> tuple[np.ndarray, float]:
    """把音軌對到目標長度：先微調速度（不變調），再補靜音。

    超過 max_tempo 時**不裁尾**（裁尾會切掉句尾的字），而是保留溢出，
    由呼叫端回報——語音超窗要嘛重錄、要嘛改剪輯，不該默默被切掉。
    """
    cur = x.size / SR
    if cur <= 0:
        return x, 1.0
    factor = cur / target_seconds
    if factor > max_tempo:
        factor = max_tempo
    y = atempo(x, factor)
    if y.size / SR > target_seconds + 0.01:
        if truncate:
            y = y[: int(target_seconds * SR)]
    elif y.size / SR < target_seconds - 0.01:
        y = np.concatenate([y, silence(target_seconds - y.size / SR)])
    return y, round(factor, 4)


# ---------------------------------------------------------------------------
# 字幕
# ---------------------------------------------------------------------------


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(lang: str, name: str, dest_dir: Path) -> Path:
    dest = dest_dir / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    rows_out = []
    for i, (a, b, rows) in enumerate(SUBTITLES[lang], 1):
        rows_out.append(str(i))
        rows_out.append(f"{srt_time(a)} --> {srt_time(b)}")
        rows_out.extend(rows)
        rows_out.append("")
    dest.write_text("\n".join(rows_out), encoding="utf-8")
    return dest


def build_dx_track(items: list[dict], lang: str, total: float = 60.0) -> np.ndarray:
    """把採用版依時間碼放回時間軸。items 需含 vid 與 path。

    L cut 規則：不改變語速；某句若比它的窗格長，就讓它跨越剪輯點延到下一畫面；
    下一句的起點若會撞上前一句的尾音，則順延到前一句結束（對白不疊對白）。
    軸長自動延長到最後一句講完（最短 60 秒）。
    """
    placed: list[tuple[int, np.ndarray]] = []
    cursor = 0
    for it in items:
        if it.get("version") != ADOPTED.get(it["vid"]) or not it.get("path"):
            continue
        audio = decode_f32(Path(it["path"]).read_bytes())
        line = find_line(it["vid"])
        start = max(int(line.start * SR), cursor)
        placed.append((start, audio))
        cursor = start + len(audio)
    track = np.zeros(max(int(total * SR), cursor), dtype=np.float64)
    for start, audio in placed:
        track[start: start + len(audio)] += audio
    return track


def write_manifest(dest: Path, items: list[dict], extra: dict | None = None) -> Path:
    manifest = {
        "project": "雌雄 / 木蘭辭",
        "sample_rate": SR,
        "bit_depth": 24,
        "channels": 1,
        "peak_target_dbfs": PEAK_DBFS,
        "adopted_versions": ADOPTED,
        "timeline_version": "design/02 V1.1（時間碼放寬版）",
        "sources": [
            "design/02-分鏡表-靜態與動態.md",
            "design/03-臺詞與雙語版本.md",
            "design/06-聲音設計-音色選角與試鏡.md",
            "design/03-臺詞與雙語版本.md",
            "design/07-配音執行包-真人錄音與AI備援.md",
        ],
        "items": items,
    }
    if extra:
        manifest.update(extra)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest
