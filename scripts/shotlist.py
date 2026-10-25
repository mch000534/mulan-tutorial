#!/usr/bin/env python3
"""Turn the design documents into a per-shot production record.

`design/` is the source of truth. This module only reads it; every field that
ends up in the web shot list traces back to a line in a design document:

    design/02  逐鏡分鏡表（時間碼／畫面／聲音）＋45 鏡動態規格＋i2v 提示詞
    design/03  旁白與台詞定稿（對白／VO）
    design/04  45 顆鏡頭首幀提示詞（首幀生成提示詞）
    design/05  動態與速度地圖／Cue Sheet／關鍵音效（音樂與音效）

Run this file directly to print a summary and to check that every shot still
resolves to a complete record:

    python3 scripts/shotlist.py
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "design"

DOC_BOARD = DESIGN / "02-分鏡表-靜態與動態.md"
DOC_PROMPTS = DESIGN / "04-AI生成提示詞包.md"
DOC_LINES = DESIGN / "03-臺詞與雙語版本.md"
DOC_SOUND = DESIGN / "05-音樂與音效設計.md"

TIME_RE = re.compile(r"(\d{1,2}):(\d{2}(?:\.\d+)?)")
SCENE_HEAD_RE = re.compile(r"^###\s*(S\d+)\s*｜\s*(.*?)（(.*?)）\s*$")
CUE_HEAD_RE = re.compile(r"^###\s*CUE\s*(\d+)\s*｜\s*([0-9:.]+)[–\-]([0-9:.]+)\s*「(.+?)」")
SHOT_NO_RE = re.compile(r"^(\d+)\s*(★)?$")
I2V_RE = re.compile(r"^-\s*`(shot_\d+)`\s*—\s*(.+)$")
AUDIO_RE = re.compile(r"^(.*?)\.\s*Audio:\s*(.+)$", re.S)
FRAME_HEAD_RE = re.compile(r"^\*\*#(\d+)\*\*$")
LINE_ID_RE = re.compile(r"^V\d$")

# MiniMax H3：原生 24fps、單段 5–15 秒整秒、原生立體聲音軌
H3_MODEL = "MiniMax-H3"
H3_FPS = 24
H3_MIN_CLIP = 5
H3_MAX_CLIP = 15


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"缺少設計文件：{path}")
    return path.read_text(encoding="utf-8").splitlines()


def time_span(text: str) -> tuple[float, float] | None:
    """Read '00:12.8–00:13.6' (or any two timestamps) as a second range."""
    found = TIME_RE.findall(text)
    if len(found) < 2:
        return None
    return (
        int(found[0][0]) * 60 + float(found[0][1]),
        int(found[1][0]) * 60 + float(found[1][1]),
    )


def single_time(text: str) -> float | None:
    found = TIME_RE.fullmatch(text.strip())
    if not found:
        return None
    return int(found.group(1)) * 60 + float(found.group(2))


def table_cells(line: str) -> list[str] | None:
    """Return the cells of a markdown table row, or None for anything else."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if not cells or all(set(cell) <= set("-: ") for cell in cells):
        return None
    return cells


def overlaps(shot_start: float, shot_end: float, start: float, end: float) -> bool:
    return shot_start < end and start < shot_end


# --------------------------------------------------------------------------
# design/02：逐鏡分鏡表、45 鏡動態規格、i2v 提示詞、慢動作、對嘴
# --------------------------------------------------------------------------


def parse_board(path: Path) -> tuple[dict[int, dict], dict[int, dict], list[dict]]:
    """Read the static storyboard, the motion spec table and the scene list."""
    static: dict[int, dict] = {}
    motion: dict[int, dict] = {}
    scenes: list[dict] = []

    section = ""
    scene: dict | None = None

    for line in read_lines(path):
        if line.startswith("## "):
            section = line[3:].strip()
            scene = None
            continue

        heading = SCENE_HEAD_RE.match(line.strip())
        if heading:
            scene = {
                "id": heading.group(1),
                "title": heading.group(2).strip(),
                "range": heading.group(3).strip(),
                "shots": [],
            }
            if section.startswith("三、"):
                scenes.append(scene)
            continue

        cells = table_cells(line)
        if not cells or scene is None:
            continue

        if section.startswith("三、") and len(cells) == 9 and cells[0].isdigit():
            no = int(cells[0])
            scene["shots"].append(no)
            static[no] = {
                "no": no,
                "scene": scene["id"],
                "scene_title": scene["title"],
                "scene_range": scene["range"],
                "timecode": cells[1],
                "seconds": cells[2],
                "size": cells[3],
                "camera": cells[4],
                "lens": cells[5],
                "move": cells[6],
                "picture": cells[7],
                "sound": cells[8],
            }
            continue

        if section.startswith("十四、") and len(cells) == 7:
            matched = SHOT_NO_RE.match(cells[0])
            if not matched:
                continue
            no = int(matched.group(1))
            motion[no] = {
                "level": cells[1],
                "action": cells[2],
                "move_cam": cells[3],
                "env": cells[4],
                "cut": cells[5],
                "risk": cells[6],
                "star": bool(matched.group(2)),
            }

    return static, motion, scenes


def split_audio(prompt: str) -> tuple[str, str]:
    """Split a MiniMax H3 prompt into its visual part and its native audio clause."""
    matched = AUDIO_RE.match(prompt.strip())
    if not matched:
        return prompt.strip(), ""
    return matched.group(1).strip(), matched.group(2).strip()


def parse_i2v_prompts(path: Path) -> dict[str, str]:
    """Read the 45 image-to-video prompts from design/02 附錄."""
    prompts: dict[str, str] = {}
    section = ""

    for line in read_lines(path):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not section.startswith("二十一、"):
            continue
        matched = I2V_RE.match(line.strip())
        if matched:
            prompts[matched.group(1)] = matched.group(2).strip()

    return prompts


def parse_slow_motion(path: Path) -> dict[int, dict]:
    """Read the three slow-motion shots from design/02 慢動作規則."""
    table: dict[int, dict] = {}
    section = ""

    for line in read_lines(path):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not section.startswith("十二、"):
            continue
        cells = table_cells(line)
        if not cells or len(cells) not in (4, 5):
            continue
        matched = re.match(r"^(\d+)", cells[0])
        if not matched:
            continue
        table[int(matched.group(1))] = {
            "label": cells[0],
            "rate": cells[1],
            "fps": cells[2],
            "prompt": cells[3] if len(cells) == 5 else "",
            "length": cells[-1],
        }

    return table


def parse_lipsync(path: Path) -> dict[int, dict]:
    """Read the lip-sync table from design/02 對嘴與動態規範."""
    table: dict[int, dict] = {}
    section = ""

    for line in read_lines(path):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not section.startswith("十八、"):
            continue
        cells = table_cells(line)
        if not cells or len(cells) != 4 or not cells[0].isdigit():
            continue
        table[int(cells[0])] = {
            "line": cells[1],
            "lipsync": cells[2].replace("*", "").strip(),
            "note": cells[3],
        }

    return table


# --------------------------------------------------------------------------
# design/04：45 顆鏡頭首幀提示詞
# --------------------------------------------------------------------------


def parse_first_frames(path: Path) -> dict[int, dict]:
    frames: dict[int, dict] = {}
    section = ""
    current: int | None = None
    buffer: list[str] = []
    in_code = False

    for line in read_lines(path):
        if line.startswith("## "):
            section = line[3:].strip()
            current = None
            continue

        if not section.startswith("七、"):
            continue

        heading = FRAME_HEAD_RE.match(line.strip())
        if heading:
            current = int(heading.group(1))
            frames[current] = {"prompt": "", "i2v": "", "note": ""}
            continue

        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                if current is not None and not frames[current]["prompt"]:
                    frames[current]["prompt"] = "\n".join(buffer).strip()
                buffer = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            buffer.append(line)
            continue

        if current is None:
            continue

        if stripped.startswith("- i2v："):
            frames[current]["i2v"] = stripped.split("：", 1)[1].strip().strip("`")
        elif stripped.startswith("- 備註："):
            frames[current]["note"] = stripped.split("：", 1)[1].strip()

    return frames


# --------------------------------------------------------------------------
# design/03：旁白與台詞
# --------------------------------------------------------------------------


def parse_voice_lines(path: Path) -> list[dict]:
    lines: list[dict] = []
    section = ""

    for raw in read_lines(path):
        if raw.startswith("## "):
            section = raw[3:].strip()
            continue
        cells = table_cells(raw)
        if not cells:
            continue
        if section.startswith("二、") and len(cells) == 8 and LINE_ID_RE.match(cells[0]):
            lines.append(
                {
                    "id": cells[0],
                    "timecode": cells[1],
                    "seconds": cells[2],
                    "role": cells[3],
                    "text": cells[4],
                    "chars": cells[5],
                    "speed": cells[6],
                    "direction": cells[7],
                    "cantonese": "",
                }
            )
        elif section.startswith("十、") and len(cells) == 4 and LINE_ID_RE.match(cells[0]):
            for line in lines:
                if line["id"] == cells[0]:
                    line["cantonese"] = cells[2]

    return lines


# --------------------------------------------------------------------------
# design/05：音樂與音效
# --------------------------------------------------------------------------


def parse_sound(path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Read the music map, the cue sheet and the key sound effects."""
    music_map: list[dict] = []
    sfx: list[dict] = []
    cues: list[dict] = []
    section = ""
    current_cue: dict | None = None

    for raw in read_lines(path):
        if raw.startswith("## "):
            section = raw[3:].strip()
            current_cue = None
            continue

        if section.startswith("四、"):
            heading = CUE_HEAD_RE.match(raw.strip())
            if heading:
                current_cue = {
                    "id": f"CUE {heading.group(1)}",
                    "timecode": f"{heading.group(2)}–{heading.group(3)}",
                    "name": heading.group(4),
                    "instruments": "",
                    "level": "",
                    "function": "",
                    "note": "",
                }
                cues.append(current_cue)
                continue
            if current_cue is not None and raw.strip().startswith("- "):
                label, _, value = raw.strip()[2:].partition("：")
                key = {
                    "樂器": "instruments",
                    "動態": "level",
                    "功能": "function",
                    "備註": "note",
                }.get(label.strip())
                if key:
                    current_cue[key] = value.strip()
            continue

        cells = table_cells(raw)
        if not cells:
            continue

        if section.startswith("三、") and len(cells) == 5:
            span = time_span(cells[0])
            if span:
                music_map.append(
                    {
                        "timecode": cells[0],
                        "start": span[0],
                        "end": span[1],
                        "segment": cells[1],
                        "bpm": cells[2],
                        "dynamics": cells[3],
                        "state": cells[4],
                    }
                )
        elif section.startswith("五、") and len(cells) in (4, 5):
            stamp = single_time(cells[0])
            if stamp is not None:
                shot_no = None
                if len(cells) == 5 and cells[4].strip().isdigit():
                    shot_no = int(cells[4].strip())
                sfx.append(
                    {
                        "timecode": cells[0],
                        "at": stamp,
                        "name": cells[1],
                        "recipe": cells[2],
                        "note": cells[3],
                        "shot": shot_no,
                    }
                )

    return music_map, cues, sfx


def parse_ambience(path: Path) -> dict[str, dict]:
    """Read the ten scene ambience beds that H3 renders as native audio."""
    ambience: dict[str, dict] = {}
    section = ""
    in_ambience = False

    for raw in read_lines(path):
        if raw.startswith("## "):
            section = raw[3:].strip()
            in_ambience = False
            continue
        if raw.startswith("### "):
            in_ambience = "環境聲底噪" in raw
            continue
        if not (section.startswith("六、") and in_ambience):
            continue
        cells = table_cells(raw)
        if not cells or len(cells) != 3:
            continue
        scene_id = cells[0].split()[0]
        if not re.match(r"^S\d+$", scene_id):
            continue
        ambience[scene_id] = {
            "scene": scene_id,
            "title": cells[0].split(maxsplit=1)[1] if " " in cells[0] else "",
            "zh": cells[1],
            "en": cells[2],
        }

    return ambience


# --------------------------------------------------------------------------
# 組裝
# --------------------------------------------------------------------------


def i2v_length(seconds: float, slow: dict | None) -> int:
    """H3 素材長度（整秒、5–15 秒）：鏡長 × 2；慢動作鏡頭鏡長 ÷ 倍率 × 1.5。"""
    if slow:
        rate = re.search(r"([0-9.]+)x", slow["rate"])
        factor = float(rate.group(1)) if rate else 1.0
        raw = seconds / factor * 1.5
    else:
        raw = seconds * 2
    return max(H3_MIN_CLIP, min(H3_MAX_CLIP, math.ceil(raw)))


def speed_label(shot: dict) -> str:
    """慢動作／高速感／標準 24fps。"""
    if shot.get("slow"):
        return f"慢動作 {shot['slow']['rate'].split('（')[0]}（後期變速）"
    if "高速感" in " ".join(
        [shot.get("move", ""), shot.get("motion", {}).get("move_cam", "")]
    ):
        return "高速感（不變速）"
    return "標準 24fps"


CLIP_ID_RE = re.compile(r"^shot_(\d+)_16x9(_v2)?$")
CLIP_DIR = "assets/video/shots_169"
DOC_CLIP_MANIFEST = ROOT / "assets/video/manifest_i2v.jsonl"


def parse_clips(path: Path = DOC_CLIP_MANIFEST) -> dict[int, list[dict]]:
    """Read the ComfyUI / MiniMax-H3 clip manifest: 16:9 shots, two seeds each.

    The manifest holds one row per generation run; the same shot can appear
    twice (a low-res trial plus the final 1280x736 run), so the widest row per
    shot_id wins. Rows without a file on disk are ignored.
    """
    clips: dict[int, list[dict]] = {}
    if not path.exists():
        return clips

    best: dict[str, dict] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        row = json.loads(raw)
        shot_id = row.get("shot_id", "")
        if not CLIP_ID_RE.match(shot_id):
            continue
        file = f"{CLIP_DIR}/{shot_id}.mp4"
        if not (ROOT / file).exists():
            continue
        entry = {
            "variant": "v2" if shot_id.endswith("_v2") else "v1",
            "file": file,
            "seed": row.get("seed"),
            "duration_s": row.get("duration_s"),
            "width": row.get("width"),
            "height": row.get("height"),
            "steps": row.get("steps"),
            "model": row.get("model"),
            "tool": row.get("tool"),
            "version": row.get("version"),
            "prompt_id": row.get("prompt_id"),
        }
        prev = best.get(shot_id)
        if prev is None or (row.get("width") or 0) >= (prev["width"] or 0):
            best[shot_id] = entry

    for shot_id, entry in best.items():
        no = int(CLIP_ID_RE.match(shot_id).group(1))
        clips.setdefault(no, []).append(entry)
    for entries in clips.values():
        entries.sort(key=lambda item: item["variant"])
    return clips


def check_prompt_sync(i2v: dict[str, str], frames: dict[int, dict]) -> None:
    """design/02 附錄與 design/04 第七節的 i2v 提示詞必須逐字一致。"""
    drift: list[str] = []
    for no in range(1, 46):
        board = i2v.get(f"shot_{no:02d}", "")
        pack = frames.get(no, {}).get("i2v", "")
        if board != pack:
            drift.append(f"shot_{no:02d}")
    if drift:
        raise ValueError(
            "design/02 §二十一 與 design/04 §七 的 i2v 提示詞不一致："
            + "、".join(drift)
        )


def build() -> list[dict]:
    static, motion, scenes = parse_board(DOC_BOARD)
    i2v = parse_i2v_prompts(DOC_BOARD)
    slow = parse_slow_motion(DOC_BOARD)
    lipsync = parse_lipsync(DOC_BOARD)
    frames = parse_first_frames(DOC_PROMPTS)
    voice_lines = parse_voice_lines(DOC_LINES)
    music_map, cues, sfx = parse_sound(DOC_SOUND)
    ambience = parse_ambience(DOC_SOUND)
    clips = parse_clips()

    if len(static) != 45:
        raise ValueError(f"逐鏡分鏡表解析到 {len(static)} 鏡，預期 45 鏡")

    check_prompt_sync(i2v, frames)

    has_shot_map = any(item["shot"] is not None for item in sfx)

    shots: list[dict] = []
    for no in sorted(static):
        shot = static[no]
        span = time_span(shot["timecode"])
        if not span:
            raise ValueError(f"鏡 {no} 的時間碼無法解析：{shot['timecode']}")
        start, end = span

        seconds = float(shot["seconds"])
        shot["start"] = start
        shot["end"] = end

        motion_row = motion.get(no, {})
        shot["motion"] = motion_row
        shot["slow"] = slow.get(no)
        shot["lipsync"] = lipsync.get(no)

        # 首幀與動態提示詞
        frame = frames.get(no, {})
        shot["first_frame"] = frame.get("prompt", "")
        shot["first_frame_note"] = frame.get("note", "")
        shot["first_frame_i2v"] = frame.get("i2v", "")
        shot["i2v"] = i2v.get(f"shot_{no:02d}", "")
        shot["i2v_visual"], shot["i2v_audio"] = split_audio(shot["i2v"])

        # 聲音：對白／VO 依時間碼落在哪一鏡
        shot["voices"] = [
            line
            for line in voice_lines
            if (line_span := time_span(line["timecode"]))
            and overlaps(start, end, line_span[0], line_span[1])
        ]
        # 音效：優先用 design/05 的「對應鏡次」，整張表都沒有鏡次欄才回退到時間碼推算
        if has_shot_map:
            shot["sfx"] = [item for item in sfx if item["shot"] == no]
        else:
            shot["sfx"] = [item for item in sfx if start <= item["at"] < end]
        shot["music"] = [
            item
            for item in music_map
            if overlaps(start, end, item["start"], item["end"])
        ]
        shot["cues"] = [
            cue
            for cue in cues
            if (cue_span := time_span(cue["timecode"]))
            and overlaps(start, end, cue_span[0], cue_span[1])
        ]
        shot["ambience"] = ambience.get(shot["scene"], {})

        # 影片佔位：H3 素材長度、幀率、速度、對嘴需求
        shot["fps"] = H3_FPS
        shot["clip_seconds"] = i2v_length(seconds, shot["slow"])
        shot["speed"] = speed_label(shot)

        # 已生成的 16:9 動態素材（每鏡兩個 seed）
        shot["clips"] = clips.get(no, [])

        shots.append(shot)

    return shots


def build_all() -> tuple[list[dict], list[dict]]:
    """Return the 45 shot records plus the 10 scene records."""
    static, motion, scenes = parse_board(DOC_BOARD)
    shots = build()
    return shots, scenes


def summary() -> dict:
    shots, scenes = build_all()
    voices = {
        line["id"]
        for shot in shots
        for line in shot["voices"]
    }
    return {
        "shots": len(shots),
        "scenes": len(scenes),
        "seconds": sum(float(shot["seconds"]) for shot in shots),
        "voice_segments": len(voices),
        "slow_shots": [shot["no"] for shot in shots if shot["slow"]],
        "fast_shots": [
            shot["no"] for shot in shots if shot["speed"].startswith("高速感")
        ],
        "lipsync_shots": [
            shot["no"] for shot in shots if (shot["lipsync"] or {}).get("lipsync") == "要"
        ],
        "model": H3_MODEL,
        "fps": H3_FPS,
        "clip_range": [H3_MIN_CLIP, H3_MAX_CLIP],
        "clips": sorted({shot["clip_seconds"] for shot in shots}),
        "native_audio": sum(1 for shot in shots if shot["i2v_audio"]),
    }


def main() -> None:
    shots = build()
    print(f"shots: {len(shots)}")
    for shot in shots:
        voices = "、".join(line["id"] for line in shot["voices"]) or "—"
        print(
            f"{shot['no']:02d} {shot['scene']:<3} {shot['timecode']:<22} "
            f"voices={voices:<8} sfx={len(shot['sfx']):<2} "
            f"frame={'y' if shot['first_frame'] else 'n'} "
            f"i2v={'y' if shot['i2v'] else 'n'} "
            f"audio={'y' if shot['i2v_audio'] else 'n'} "
            f"motion={'y' if shot['motion'] else 'n'} "
            f"fps={shot['fps']} len={shot['clip_seconds']}s"
        )
    print(summary())



if __name__ == "__main__":
    main()
