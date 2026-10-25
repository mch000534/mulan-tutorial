#!/usr/bin/env python3
"""Build the ComfyUI job list from the design documents."""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "design", "04-AI生成提示詞包.md")
OUT = os.path.join(ROOT, "scripts", "jobs.json")
OUT_16X9 = os.path.join(ROOT, "scripts", "jobs_16x9.json")
OVERRIDES = os.path.join(ROOT, "scripts", "overrides.json")

STYLE_PROP = (
    "cinematic product still life, dark neutral background, macro detail, "
    "35mm film grain, natural side light, no text"
)
STYLE_SHEET = (
    "character reference sheet, neutral grey seamless background, even soft studio light, "
    "full body, photorealistic, no text"
)
STYLE_PORTRAIT = (
    "head and shoulders portrait, neutral grey background, even soft light, "
    "photorealistic, visible skin pores, no beauty retouch, 5th century northern China"
)

NEG_GLOBAL = (
    "modern clothing, zipper, buttons, printed pattern, plastic, neon, glossy skin, "
    "airbrushed, beauty filter, makeup, eyeliner, false eyelashes, fantasy armor, "
    "glowing runes, particle effects, lens flare, HDR, oversaturated, text, watermark, "
    "logo, extra fingers, deformed hands, anime, illustration, 3D render, video game, "
    "cosplay, smiling with teeth"
)

REF_A = "assets/generated/characters/mulan_A_ref.jpg"
REF_B = "assets/ref/mulan_B_ref.jpg"
REF_C = "assets/generated/characters/mulan_C_ref.jpg"
REF_FATHER = "assets/generated/characters/father_ref.jpg"
REF_MOTHER = "assets/generated/characters/mother_ref.jpg"
REF_SISTER = "assets/generated/characters/sister_ref.jpg"
REF_BOY = "assets/generated/characters/boy_ref.jpg"


def fence_blocks(text):
    return re.findall(r"```\n(.*?)\n```", text, re.S)


def clean(s):
    return re.sub(r"\s+", " ", s).strip()


def parse_chars(text):
    out = []
    for m in re.finditer(r"^### (4\.\d+[^\n]*)\n(.*?)(?=^### |^---|\Z)", text, re.S | re.M):
        title, body = m.group(1), m.group(2)
        fences = fence_blocks(body)
        if fences:
            out.append((title, clean(fences[0])))
    return out


def parse_props(text):
    out = []
    for m in re.finditer(r"^### (5\.\d+[^\n]*)\n(.*?)(?=^### |^---|\Z)", text, re.S | re.M):
        title, body = m.group(1), m.group(2)
        fences = fence_blocks(body)
        if fences:
            out.append((title, clean(fences[0])))
    return out


def parse_scenes(text):
    out = []
    part = text.split("## 六、場景概念圖提示詞", 1)[-1].split("## 七、", 1)[0]
    for m in re.finditer(r"^### (S\d+[^\n]*)\n(.*?)(?=^### |^---|\Z)", part, re.S | re.M):
        title, body = m.group(1), m.group(2)
        fences = fence_blocks(body)
        if fences:
            out.append((title, clean(fences[0])))
    return out


def parse_shots(text):
    """Return (shot number, prompt, scene number, style override) for all 45 shots."""
    part = text.split("## 七、45 顆鏡頭首幀提示詞", 1)[-1]
    out = []
    chunks = re.split(r"^### (S\d+)[^\n]*$", part, flags=re.M)
    for i in range(1, len(chunks), 2):
        scene = int(chunks[i][1:])
        body = chunks[i + 1]
        for m in re.finditer(r"\*\*#(\d+)\*\*\n(.*?)(?=\n\*\*#|\Z)", body, re.S):
            n = int(m.group(1))
            fences = fence_blocks(m.group(2))
            if not fences:
                continue
            note = re.search(r"備註：\s*STYLE-([ABC])", m.group(2))
            out.append((n, clean(fences[0]), scene, note.group(1) if note else None))
    return out


def parse_styles(text):
    """STYLE-A / STYLE-B / STYLE-C straight from the design document."""
    out = {}
    part = text.split("## 二、全域風格塊", 1)[-1].split("## 三、", 1)[0]
    for m in re.finditer(r"^### (STYLE-[ABC])[^\n]*\n(.*?)(?=^### |^---|\Z)", part, re.S | re.M):
        fences = fence_blocks(m.group(2))
        if fences:
            out[m.group(1)] = clean(fences[0])
    return out


# 樣式塊已經描述過的東西，描述欄就不必再寫一次
STYLE_WORDS = {
    "9:16", "16:9", "5th century", "5th century china", "35mm", "film grain",
}
STOPWORDS = {
    "a", "an", "the", "of", "on", "in", "and", "with", "only", "no",
    "front", "view", "back", "side", "is", "are", "as",
}


def _tokens(fragment):
    return {
        word
        for word in re.findall(r"[a-z0-9]+", fragment.lower())
        if word not in STOPWORDS
    }


def merge_style(prompt, style):
    """Append a style block, dropping the parts the prompt already states."""
    style_frags = [frag.strip() for frag in style.split(",") if frag.strip()]
    style_tokens = [_tokens(frag) for frag in style_frags]
    style_lower = {frag.lower() for frag in style_frags}

    kept = []
    for frag in [f.strip() for f in prompt.split(",")]:
        if not frag:
            continue
        low = frag.lower()
        if low in style_lower or low in STYLE_WORDS:
            continue
        toks = _tokens(frag)
        if len(toks) >= 2 and any(
            len(toks & style_tok) / len(toks) >= 0.6 and len(toks & style_tok) >= 2
            for style_tok in style_tokens
        ):
            continue
        if low.startswith("cinematic"):
            frag = re.sub(r"^cinematic\s+", "", frag, flags=re.I).strip()
            if not frag or frag.lower() == "cinematic":
                continue
            toks = _tokens(frag)
            if len(toks) >= 2 and any(
                len(toks & style_tok) / len(toks) >= 0.6 and len(toks & style_tok) >= 2
                for style_tok in style_tokens
            ):
                continue
        kept.append(frag)

    return ", ".join(kept + style_frags)


def add(jobs, **kw):
    jobs.append(kw)


def main():
    text = open(DOC, encoding="utf-8").read()
    styles = parse_styles(text)
    chars = parse_chars(text)
    props = parse_props(text)
    scenes = parse_scenes(text)
    shots = parse_shots(text)

    assert set(styles) == {"STYLE-A", "STYLE-B", "STYLE-C"}, f"styles={sorted(styles)}"
    # design/04 第六節：S2 用 STYLE-B，S8／S9 用 STYLE-C，其餘 STYLE-A
    scene_style = {2: "B", 8: "C", 9: "C"}

    assert len(chars) == 10, f"chars={len(chars)}"
    assert len(props) == 6, f"props={len(props)}"
    assert len(scenes) == 10, f"scenes={len(scenes)}"
    assert len(shots) == 45, f"shots={len(shots)}"

    jobs = []

    # ---------- portrait references ----------
    ref_prompts = {
        "ref_mulan_A": (
            "A 17-year-old Chinese woman, strong athletic build, plain undyed hemp cross-collar tunic, "
            "long black hair loosely tied with a wooden pin, loose strands at the temples, no makeup, "
            "thick untrimmed eyebrows, faint freckles, pale lips, calm stubborn gaze, " + STYLE_PORTRAIT
        ),
        "ref_mulan_B": (
            "The exact same young woman as the reference, same face, now a soldier. Short black hair "
            "cropped below the ears tied with a dark cloth strip, sun-tanned weathered skin, dirt on the "
            "cheeks, chapped lips, no makeup, a small pale scar at the tail of her left eyebrow on the "
            "right side of the image, battered black lamellar armor with deep sword gashes, torn left "
            "shoulder plate, dried dark brown blood, " + STYLE_PORTRAIT
        ),
        "ref_mulan_C": (
            "The same Chinese woman, long black hair in a high bun with a plain silver hairpin, a small "
            "gold leaf flower ornament on her forehead, dark red matte lips, no other makeup, faded pale "
            "yellow old ruqun with visible mended stitches, calm expression with a faint smile, " + STYLE_PORTRAIT
        ),
        "ref_father": (
            "A 60-year-old Chinese farmer, hunched back, strong arms, patched coarse hemp short jacket, "
            "hemp rope belt, short messy white beard, eyebrows still black, cloudy eyes, sun-cracked face, "
            "ashamed expression, avoiding eye contact, " + STYLE_PORTRAIT
        ),
        "ref_mother": (
            "A 55-year-old Chinese mother, small and thin, slightly stooped, dark blue coarse cotton "
            "jacket, flour-stained apron, grey hair in a loose bun with a broken wooden hairpin, tearful "
            "but restrained expression, " + STYLE_PORTRAIT
        ),
        "ref_sister": (
            "A 22-year-old Chinese woman, peach-pink old blouse, double buns with fabric flowers, "
            "slightly flushed cheeks, hurried comic energy, " + STYLE_PORTRAIT
        ),
        "ref_boy": (
            "A 10-year-old Chinese boy, oversized hemp shirt, soot on the nose, thick eyebrows, missing "
            "one front tooth, focused expression, " + STYLE_PORTRAIT
        ),
    }
    ref_files = {
        "ref_mulan_A": REF_A,
        "ref_mulan_B": REF_B,
        "ref_mulan_C": REF_C,
        "ref_father": REF_FATHER,
        "ref_mother": REF_MOTHER,
        "ref_sister": REF_SISTER,
        "ref_boy": REF_BOY,
    }
    ref_sources = {
        "ref_mulan_A": None,
        "ref_mulan_B": REF_A,
        "ref_mulan_C": REF_A,
        "ref_father": None,
        "ref_mother": None,
        "ref_sister": None,
        "ref_boy": None,
    }
    for i, (jid, prompt) in enumerate(ref_prompts.items()):
        add(jobs, id=jid, kind="ref", file=ref_files[jid], prompt=prompt,
            negative=NEG_GLOBAL, width=1024, height=1024, seed=1100 + i * 97,
            refs=[ref_sources[jid]] if ref_sources[jid] else [],
            steps=25, cfg=2.0)

    # ---------- character sheets ----------
    sheet_keys = ["A", "B", "C", "father", "mother", "sister", "boy", "comrades", "emperor", "enemy"]
    sheet_refs = [REF_A, REF_B, REF_C, REF_FATHER, REF_MOTHER, REF_SISTER, REF_BOY, None, None, None]
    sheet_neg_extra = {
        "comrades": "single person, identical faces, uniform armor",
        "emperor": "visible face, facial features",
        "enemy": "cultural markings, patterns, insignia, real ethnic clothing, fantasy spikes",
    }
    for i, (title, prompt) in enumerate(chars):
        key = sheet_keys[i]
        neg = NEG_GLOBAL
        if key in sheet_neg_extra:
            neg += ", " + sheet_neg_extra[key]
        add(jobs, id=f"char_{key}_sheet", kind="sheet",
            file=f"assets/generated/characters/char_{key}_sheet.jpg",
            prompt=merge_style(prompt, STYLE_SHEET), negative=neg,
            width=1536, height=1024, seed=2100 + i * 211,
            refs=[sheet_refs[i]] if sheet_refs[i] else [], steps=25, cfg=2.0)

    # ---------- props ----------
    prop_keys = ["armor", "mirror_rouge", "scrolls", "short_sword", "yellow_dress", "spear_banner"]
    for i, (title, prompt) in enumerate(props):
        add(jobs, id=f"prop_{prop_keys[i]}", kind="prop",
            file=f"assets/generated/props/prop_{prop_keys[i]}.jpg",
            prompt=merge_style(prompt, STYLE_PROP), negative=NEG_GLOBAL + ", person, hand, multiple objects",
            width=1024, height=1024, seed=3100 + i * 307, refs=[], steps=25, cfg=2.0)

    # ---------- scenes ----------
    for i, (title, prompt) in enumerate(scenes):
        n = int(re.match(r"S(\d+)", title).group(1))
        style = styles["STYLE-" + scene_style.get(n, "A")]
        add(jobs, id=f"scene_S{n:02d}", kind="scene",
            file=f"assets/generated/scenes/scene_S{n:02d}.jpg",
            prompt=merge_style(prompt, style), negative=NEG_GLOBAL + ", people, person, crowd",
            width=720, height=1280, seed=4100 + i * 401, refs=[], steps=25, cfg=2.0)

    # ---------- shots ----------
    def shot_refs(n):
        b = [REF_B]
        table = {
            3: b, 6: [REF_FATHER], 7: [REF_A],
            14: [REF_A], 15: [REF_A], 16: b,
            20: b, 21: b, 23: b, 26: b, 27: b, 28: b,
            29: b, 30: b, 31: b, 32: b, 34: b,
            35: [REF_FATHER], 36: [REF_MOTHER], 37: [REF_SISTER], 38: [REF_BOY],
            39: b, 40: b, 42: [REF_C], 45: [REF_C],
        }
        return table.get(n, [])

    for n, prompt, scene, style_note in shots:
        extra = ""
        if n in (2, 3):
            extra = ", extreme close-up, shallow depth of field"
        if style_note:
            style_key = style_note
        elif scene in (8, 9):
            style_key = "C"
        else:
            style_key = "A"
        add(jobs, id=f"shot_{n:02d}", kind="shot",
            file=f"assets/generated/shots/shot_{n:02d}.jpg",
            prompt=merge_style(prompt + extra, styles["STYLE-" + style_key]),
            negative=NEG_GLOBAL,
            width=720, height=1280, seed=5100 + n * 137,
            refs=shot_refs(n), steps=25, cfg=2.0)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OVERRIDES):
        with open(OVERRIDES, encoding="utf-8") as f:
            overrides = json.load(f)
        for job in jobs:
            if job["id"] in overrides:
                job.update(overrides[job["id"]])
        print(f"applied {len(overrides)} overrides")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    wide = []
    for job in jobs:
        if job["kind"] not in ("shot", "scene"):
            continue
        w = dict(job)
        stem, ext = os.path.splitext(os.path.basename(job["file"]))
        folder = os.path.dirname(job["file"]) + "_16x9"
        w["id"] = job["id"] + "_16x9"
        w["file"] = os.path.join(folder, stem + "_16x9" + ext)
        w["width"] = 1280
        w["height"] = 720
        w["prompt"] = (job["prompt"]
                       .replace("vertical 9:16 composition", "horizontal 16:9 composition")
                       .replace("9:16", "16:9"))
        w["negative"] = job.get("negative", "").replace("9:16", "16:9")
        wide.append(w)
    with open(OUT_16X9, "w", encoding="utf-8") as f:
        json.dump(wide, f, ensure_ascii=False, indent=2)

    print(f"wrote {len(jobs)} jobs -> {OUT}")
    print(f"wrote {len(wide)} 16:9 jobs -> {OUT_16X9}")
    from collections import Counter
    print(Counter(j["kind"] for j in jobs))
    print("shots with refs:", sum(1 for j in jobs if j["kind"] == "shot" and j["refs"]))


if __name__ == "__main__":
    main()
