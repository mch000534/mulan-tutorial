#!/usr/bin/env python3
"""Build the static production-dossier site for the Mulan project.

Run:
  python3 scripts/build_site.py
  python3 -m http.server 8000
  open http://localhost:8000/site/
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path

from PIL import Image

from doc_prompts import BRIEF_EXAMPLE, BRIEF_TEMPLATE, PROMPTS
from shotlist import H3_MODEL, build_all, summary

try:
    import mistune
except ImportError:  # fallback keeps the site buildable without extra packages
    mistune = None

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
GEN = ROOT / "assets" / "generated"
THUMBS = SITE / "thumbs"
ASSETS = ROOT / "assets"

THUMB_BOXES = {
    "refs": (560, 560),
    "characters": (720, 560),
    "props": (560, 560),
    "scenes-916": (400, 640),
    "scenes-169": (640, 400),
    "shots-916": (400, 640),
    "shots-169": (640, 400),
}

GROUP_LABELS = {
    "refs": "角色參考",
    "characters": "角色設定",
    "props": "Hero Props",
    "scenes-916": "場景 9:16",
    "scenes-169": "場景 16:9",
    "shots-916": "鏡頭 9:16",
    "shots-169": "鏡頭 16:9",
}


def official_refs():
    return [
        GEN / "characters" / "mulan_A_ref.jpg",
        ASSETS / "ref" / "mulan_B_ref.jpg",
        GEN / "characters" / "mulan_C_ref.jpg",
        GEN / "characters" / "father_ref.jpg",
        GEN / "characters" / "mother_ref.jpg",
        GEN / "characters" / "sister_ref.jpg",
        GEN / "characters" / "boy_ref.jpg",
    ]


def gallery_groups():
    return {
        "refs": official_refs(),
        "characters": sorted((GEN / "characters").glob("char_*_sheet.jpg")),
        "props": sorted((GEN / "props").glob("prop_*.jpg")),
        "scenes-916": sorted((GEN / "scenes").glob("scene_*.jpg")),
        "scenes-169": sorted((GEN / "scenes_16x9").glob("scene_*_16x9.jpg")),
        "shots-916": sorted((GEN / "shots").glob("shot_*.jpg")),
        "shots-169": sorted((GEN / "shots_16x9").glob("shot_*_16x9.jpg")),
    }


def ensure_thumb(src: Path, group: str) -> Path:
    dst = THUMBS / group / f"{src.stem}.jpg"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst

    with Image.open(src) as image:
        image = image.convert("RGB")
        image.thumbnail(THUMB_BOXES[group], Image.Resampling.LANCZOS)
        image.save(dst, "JPEG", quality=82, optimize=True, progressive=True)
    return dst


def image_size(src: Path) -> tuple[int, int]:
    with Image.open(src) as image:
        return image.size


def build_gallery():
    groups = gallery_groups()
    cards = []
    counts = {}

    for group, files in groups.items():
        counts[group] = len(files)
        for src in files:
            thumb = ensure_thumb(src, group)
            width, height = image_size(src)
            label = src.stem
            meta = f"{width} × {height} · {GROUP_LABELS[group]}"
            thumb_rel = thumb.relative_to(SITE).as_posix()
            full_rel = Path("..", src.relative_to(ROOT)).as_posix()
            cards.append(
                f'<button class="gcard" type="button" data-group="{group}" '
                f'data-full="{escape(full_rel)}" data-title="{escape(label)}" '
                f'data-meta="{escape(meta)}" aria-label="放大 {escape(label)}">'
                f'<img src="{escape(thumb_rel)}" alt="{escape(label)}，{escape(GROUP_LABELS[group])}" '
                f'loading="lazy" decoding="async" width="{width}" height="{height}">'
                f'<span class="gcard__cap"><b>{escape(label)}</b><i>{width} × {height}</i></span>'
                "</button>"
            )

    counts["all"] = sum(counts.values())
    return "\n".join(cards), counts



PLACEHOLDER_RE = re.compile(r"(\{\{[^{}]+\}\})")


def highlight(text: str) -> str:
    escaped = escape(text)
    return PLACEHOLDER_RE.sub(lambda match: f'<span class="ph">{match.group(1)}</span>', escaped)


def render_prompt_html(text: str) -> str:
    """Render a prompt as a paper sheet instead of a terminal code block."""
    out: list[str] = []
    section: str | None = None
    items: list[str] = []

    def flush() -> None:
        nonlocal section, items
        if section is None:
            return
        rows = []
        for item in items:
            numbered = re.match(r"^(\d+)\.\s*(.*)$", item)
            if numbered:
                rows.append(f'<li class="is-num">{highlight(numbered.group(2))}</li>')
            elif item.startswith("- "):
                rows.append(f'<li class="is-bul">{highlight(item[2:])}</li>')
            else:
                rows.append(f'<li class="is-p">{highlight(item)}</li>')
        out.append(
            '<section class="prompt-sec">'
            f'<h5>{escape(section)}</h5>'
            f'<ul class="prompt-list">{"".join(rows)}</ul>'
            "</section>"
        )
        section = None
        items = []

    lead = True
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("【") and line.endswith("】"):
            flush()
            section = line[1:-1]
            continue
        if section is None:
            css = "prompt-lead" if lead else "prompt-para"
            out.append(f'<p class="{css}">{highlight(line)}</p>')
            lead = False
            continue
        items.append(line)

    flush()
    return "".join(out)


def render_brief_rows(text: str, blank: bool = False) -> str:
    rows = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("【"):
            continue
        label, _, value = line.partition("：")
        if blank:
            cell = '<span class="brief-blank"></span>'
        else:
            cell = f'<span class="brief-value">{highlight(value)}</span>'
        rows.append(
            '<div class="brief-row">'
            f'<span class="brief-label">{escape(label)}</span>'
            f'<span class="brief-cell">{cell}</span>'
            "</div>"
        )
    return "".join(rows)


TABLE_RE = re.compile(r"(<table>.*?</table>)", re.S)


def render_markdown(text: str) -> str:
    if mistune is None:
        return f'<pre class="doc-pre">{escape(text)}</pre>'
    md = mistune.create_markdown(escape=False, plugins=["table", "strikethrough"])
    return md(text)


def render_design_doc(path: Path) -> str:
    """Render a design document as HTML for the in-page preview."""
    if not path.exists():
        return ""
    html = render_markdown(path.read_text(encoding="utf-8"))
    html = TABLE_RE.sub(lambda match: f'<div class="doc-table-wrap">{match.group(1)}</div>', html)
    html = html.replace('href="./', 'href="../design/')
    html = html.replace('src="./', 'src="../design/')
    return html


def build_prompt_library() -> str:
    chips = "".join(
        f'<a href="#prompt-{escape(item["id"])}">{escape(item["id"])} {escape(item["title"])}</a>'
        for item in PROMPTS
    )

    cards = []
    for index, item in enumerate(PROMPTS):
        card_id = f'prompt-{item["id"]}'
        text_id = f'{card_id}-text'
        char_count = len(item["prompt"])
        open_attr = " open" if index == 0 else ""
        doc_path = ROOT / item["file"]
        doc_html = render_design_doc(doc_path)
        doc_block = ""
        if doc_html:
            doc_block = (
                '<details class="doc-details">'
                f'<summary>《雌雄》的實際產出 <small>{escape(item["file"])}</small></summary>'
                f'<div class="doc-sheet">{doc_html}</div>'
                f'<p class="doc-actions"><a href="../{escape(item["file"])}">開啟原始 Markdown ↗</a></p>'
                '</details>'
            )

        cards.append(
            f'<article class="prompt-doc" id="{card_id}">'
            '<div class="prompt-doc__head">'
            '<div>'
            f'<p class="prompt-file">{escape(item["file"])}</p>'
            f'<h4>{escape(item["title"])}</h4>'
            f'<p class="prompt-summary">{escape(item["summary"])}</p>'
            '</div>'
            f'<button class="copy-btn" type="button" data-copy-target="{text_id}">複製提示詞</button>'
            '</div>'
            '<div class="prompt-output">'
            '<b>這份提示詞會產出</b>'
            f'<span>{escape(item["output"])}</span>'
            '</div>'
            f'<details class="prompt-details"{open_attr}>'
            f'<summary>展開提示詞 <small>{char_count:,} 字</small></summary>'
            f'<div class="prompt-sheet">{render_prompt_html(item["prompt"])}</div>'
            f'<pre class="prompt-raw" id="{text_id}" hidden>{escape(item["prompt"])}</pre>'
            '</details>'
            + doc_block
            + '</article>'
        )

    return f"""
    <div class="prompt-library" id="doc-prompts">
      <div class="prompt-library__head reveal">
        <p class="kicker">03B / Prompt library</p>
        <h3>8 份設計文件<br class="br-d">各自的生成提示詞</h3>
        <p class="lead">這些不是影像提示詞，而是「把一個故事變成一份可執行設計文件」的提示詞。先填共用 Brief，再按 00 → 07 生成；每份文件都有自己的交付檢查。複製後直接貼進 LLM，存成對應檔名即可。</p>
        <p style="margin-top:18px"><a class="btn btn--ghost" href="prompts.md" download>下載全部提示詞 .md</a></p>
      </div>

      <div class="prompt-howto reveal">
        <div><b>01 / BRIEF</b><span>先填共用 Brief：故事、片長、平台、限制、語言版本。</span></div>
        <div><b>02 / ORDER</b><span>按 00 → 07 的順序生成；後面的文件要貼前序文件。</span></div>
        <div><b>03 / SAVE</b><span>把輸出存成 design/00-視覺聖經.md 這類固定檔名。</span></div>
        <div><b>04 / GATE</b><span>先過文件末尾的「交付檢查」，再進下一個階段。</span></div>
      </div>

      <div class="prompt-notice reveal"><b>注意</b>每個提示詞都假設你已貼上共用 Brief。若 AI 反問你，先回答它的問題，再讓它輸出完整文件；不要讓它自行發明時代、文化或角色設定。</div>

      <p class="prompt-verify reveal"><b>已實測</b>把提示詞貼進 LLM，會產出符合章節要求的完整 Markdown：00 視覺聖經與 06 聲音設計（音色＋試鏡）已用本地模型（gemma4:31b）跑過，HEX、時間碼、表格與交付檢查都到位。</p>

      <div class="prompt-jump reveal" aria-label="提示詞快速索引">{chips}</div>

      <article class="brief-card reveal">
        <div class="prompt-doc__head">
          <div>
            <p class="prompt-file">START HERE · 共用 Brief</p>
            <h4>先填這張，再貼進每一份提示詞</h4>
            <p class="prompt-summary">不用每次重寫。把這 12 個欄位填好，複製到每個提示詞的「【專案 brief】」位置。故事不同，方法不變。</p>
          </div>
          <button class="copy-btn" type="button" data-copy-target="brief-template">複製 Brief</button>
        </div>
        <div class="brief-form">{render_brief_rows(BRIEF_TEMPLATE, blank=True)}</div>
        <pre class="prompt-raw" id="brief-template" hidden>{escape(BRIEF_TEMPLATE)}</pre>
        <details class="prompt-details prompt-details--example">
          <summary>示範：一份填好的 Brief（《雌雄》） <small>看長什麼樣子</small></summary>
          <div class="brief-form brief-form--filled">{render_brief_rows(BRIEF_EXAMPLE)}</div>
        </details>
      </article>

      <div class="prompt-grid">{''.join(cards)}</div>
    </div>
    """


def build_prompts_markdown() -> str:
    lines = [
        "# 文件生成提示詞庫",
        "",
        "> 先填共用 Brief，再按 00 → 07 的順序生成。每個提示詞都是獨立的，可以直接貼進 LLM。",
        "",
        "## 共用 Brief",
        "",
        "```text",
        BRIEF_TEMPLATE,
        "```",
        "",
        "### 示範：填好的 Brief（《雌雄》）",
        "",
        "```text",
        BRIEF_EXAMPLE,
        "```",
        "",
    ]
    for item in PROMPTS:
        lines.extend(
            [
                f'## {item["id"]} · {item["title"]}',
                "",
                f'**輸出檔案**：`{item["file"]}`',
                "",
                f'**用途**：{item["summary"]}',
                "",
                f'**會產出**：{item["output"]}',
                "",
                "```text",
                item["prompt"],
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"

def md_bold(text: str) -> str:
    """Render the **bold** markers used across the design documents."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(text))


def prompt_html(prompt: str) -> str:
    """One i2v prompt: visual description + native audio clause, audio highlighted."""
    head, sep, tail = prompt.partition(". Audio: ")
    if not sep:
        return escape(prompt)
    return f'{escape(head)}<span class="code-audio">{escape(sep + tail)}</span>'


def shot_tags(shot: dict) -> str:
    motion = shot["motion"]
    tags = [shot["size"], shot["lens"], shot["move"], f"動態 L{motion.get('level', '—')}"]
    tags.append(shot["speed"])
    if (shot["lipsync"] or {}).get("lipsync") == "要":
        tags.append("需對嘴")
    if motion.get("star"):
        tags.append("★ 重點")
    return "".join(f"<li>{escape(tag)}</li>" for tag in tags)


def render_voice(shot: dict) -> str:
    if not shot["voices"]:
        return '<p class="shot-quiet">此鏡無台詞，只有環境音與 Foley。</p>'

    blocks = []
    for line in shot["voices"]:
        cantonese = ""
        if line["cantonese"] and line["cantonese"] != line["text"]:
            cantonese = (
                f'<p class="shot-voice__alt"><b>粵語版</b> {md_bold(line["cantonese"])}</p>'
            )
        blocks.append(
            f'<div class="shot-voice">'
            f'<p class="shot-voice__meta"><b>{escape(line["id"])}</b>'
            f'<span>{escape(line["role"])}</span>'
            f'<span>{escape(line["timecode"])}</span>'
            f'<span>{escape(line["seconds"])} 秒</span></p>'
            f'<p class="shot-voice__text">{md_bold(line["text"])}</p>'
            f"{cantonese}"
            f'<p class="shot-voice__dir">{md_bold(line["direction"])}</p>'
            f"</div>"
        )
    return "".join(blocks)


def render_sound(shot: dict) -> str:
    rows = []

    ambience = shot.get("ambience") or {}
    if ambience:
        rows.append(
            '<div class="shot-sound"><h5>環境聲（H3 原生）</h5>'
            f'<p class="shot-ambience"><b>{escape(ambience["zh"])}</b>'
            f'<span>{escape(ambience["en"])}</span></p></div>'
        )

    if shot["sfx"]:
        items = "".join(
            f'<li><b>{escape(item["timecode"])}</b> {md_bold(item["name"])}'
            f'<span>{md_bold(item["recipe"])}</span>'
            f'<i>{md_bold(item["note"])}</i></li>'
            for item in shot["sfx"]
        )
        rows.append(
            '<div class="shot-sound"><h5>音效（H3 原生）</h5>'
            '<p class="shot-quiet">時間碼為全片規劃值（允許 ±0.3 秒聲畫錯位），歸屬以本鏡為準。</p>'
            f'<ul class="shot-sfx">{items}</ul></div>'
        )

    for music in shot["music"]:
        rows.append(
            f'<div class="shot-sound"><h5>背景音樂</h5>'
            f'<p class="shot-music"><b>{escape(music["timecode"])}</b>'
            f'{md_bold(music["state"])}'
            f'<span>{escape(music["segment"])} · {escape(music["bpm"])} · {escape(music["dynamics"])}</span>'
            f"</p></div>"
        )

    for cue in shot["cues"]:
        rows.append(
            f'<div class="shot-sound"><h5>{escape(cue["id"])}「{escape(cue["name"])}」</h5>'
            f'<p class="shot-music"><b>{escape(cue["timecode"])}</b>'
            f'{md_bold(cue["instruments"])}'
            f'<span>{md_bold(cue["function"])} · {md_bold(cue["note"])}</span>'
            f"</p></div>"
        )

    rows.append(
        '<div class="shot-sound"><h5>分工</h5>'
        '<p class="shot-quiet">環境聲與音效由 H3 原生生成；'
        "音樂與人聲一律後期加（提示詞寫 no music, no dialogue, no singing）。</p></div>"
    )

    if not rows:
        rows.append('<p class="shot-quiet">此鏡只有環境音，無獨立音效與配樂。</p>')

    return "".join(rows)


def render_clip_players(shot: dict, label: str = "clip-duo") -> str:
    """Two 16:9 players for one shot: the same prompt, two different seeds."""
    tag = f"{shot['no']:02d}"
    figures = []
    for clip in shot.get("clips", []):
        slot = "A" if clip["variant"] == "v1" else "B"
        figures.append(
            f'<figure class="clip">'
            f'<video controls preload="none" playsinline'
            f' poster="thumbs/shots-169/shot_{tag}_16x9.jpg"'
            f' src="../{clip["file"]}"'
            f' aria-label="鏡 {tag} 片段 {slot}，seed {clip["seed"]}"></video>'
            f'<figcaption><b>片段 {slot} · seed {clip["seed"]}</b>'
            f'<span>{clip["duration_s"]}s · {clip["width"]}×{clip["height"]} · 原生立體聲</span>'
            f"</figcaption></figure>"
        )
    if not figures:
        return ""
    return (
        f'<div class="{label} reveal">'
        f'<p class="clip-duo__label">同一提示詞 · 兩個 seed</p>'
        f'<div class="clip-duo__row">{"".join(figures)}</div>'
        "</div>"
    )


def render_video_slot(shot: dict) -> str:
    no = shot["no"]
    motion = shot["motion"]
    lipsync = (shot["lipsync"] or {}).get("lipsync", "—")
    clips = shot.get("clips", [])

    clip_rows = "".join(
        f'<dt>16:9 片段 {"B" if clip["variant"] == "v2" else "A"}</dt>'
        f'<dd>{escape(Path(clip["file"]).name)}<br>seed {clip["seed"]} · '
        f'{clip["duration_s"]}s · {clip["width"]}×{clip["height"]}</dd>'
        for clip in clips
    )

    rows = [
        ("9:16 影片", "未生成"),
        ("素材長度", f"{shot['clip_seconds']} 秒（鏡長 {shot['seconds']}s）"),
        ("幀率", f"{shot['fps']}fps（{H3_MODEL} 原生）"),
        ("速度", shot["speed"]),
        ("音軌", "原生立體聲：環境聲 + 音效（音樂、人聲後期）"),
        ("對嘴", lipsync),
        ("剪點", motion.get("cut", "—")),
    ]
    meta = "".join(
        f"<dt>{escape(label)}</dt><dd>{md_bold(value)}</dd>" for label, value in rows
    )

    if clips:
        badge = (
            f'<p class="video-slot__badge video-slot__badge--ready">'
            f"16:9 已生成 ×{len(clips)}</p>"
        )
        note = (
            '<p class="video-slot__note">同一條提示詞換 seed 重跑一次，'
            "取表現較好的一版；原生音軌已含在片段裡，9:16 版本尚未生成。</p>"
        )
        return (
            '<div class="video-slot video-slot--ready">'
            f"{badge}"
            f'<dl class="meta-list">{meta}</dl>'
            f'<dl class="meta-list meta-list--clips">{clip_rows}</dl>'
            f"{note}</div>"
        )

    return (
        '<div class="video-slot">'
        '<p class="video-slot__badge">影片未生成</p>'
        f'<dl class="meta-list">{meta}</dl>'
        '<p class="video-slot__note">此處是佔位：設計階段已定規格，動態素材尚未生成。</p>'
        "</div>"
    )


def render_shot_card(shot: dict) -> str:
    no = shot["no"]
    tag = f"{no:02d}"
    motion = shot["motion"]
    frame_note = shot["first_frame_note"]
    alt = f"鏡 {tag} {shot['scene_title']} 首幀"

    motion_rows = "".join(
        f"<dt>{escape(label)}</dt><dd>{md_bold(value)}</dd>"
        for label, value in [
            ("動作", motion.get("action", "—")),
            ("攝影機", motion.get("move_cam", "—")),
            ("環境動態", motion.get("env", "—")),
            ("剪點", motion.get("cut", "—")),
            ("風險", motion.get("risk", "—")),
        ]
    )

    backup = ""
    if shot["first_frame_i2v"] and shot["first_frame_i2v"] != shot["i2v"]:
        backup = (
            '<p class="shot-block__note"><b>提示詞包 i2v 備案</b> '
            f"{md_bold(shot['first_frame_i2v'])}</p>"
        )

    note = f'<p class="shot-block__note"><b>備註</b> {md_bold(frame_note)}</p>' if frame_note else ""

    return f"""
    <article class="shot-item reveal" id="shot-{tag}" data-scene="{escape(shot['scene'])}">
      <header class="shot-item__head">
        <span class="shot-item__no">{tag}</span>
        <div class="shot-item__title">
          <p class="kicker">{escape(shot['scene'])} {escape(shot['scene_title'])}</p>
          <h3>{escape(shot['timecode'])}<i>{escape(shot['seconds'])}s</i></h3>
        </div>
        <ul class="shot-item__tags">{shot_tags(shot)}</ul>
      </header>

      <div class="shot-item__body">
        <div class="shot-item__media">
          <figure class="shot-frame" data-shot-frame>
            <img data-shot-img-916 src="thumbs/shots-916/shot_{tag}.jpg" alt="{escape(alt)} 9:16" width="400" height="640" loading="lazy">
            <img data-shot-img-169 src="thumbs/shots-169/shot_{tag}_16x9.jpg" alt="{escape(alt)} 16:9" width="640" height="400" loading="lazy" hidden>
            <figcaption data-shot-cap>首幀 · 9:16</figcaption>
          </figure>
          {render_video_slot(shot)}
        </div>

        <div class="shot-item__detail">
          <section class="shot-block">
            <h4>劇本</h4>
            <p class="shot-picture">{md_bold(shot['picture'])}</p>
            <p class="shot-block__note"><b>分鏡表聲音</b> {md_bold(shot['sound'])}</p>
          </section>

          <section class="shot-block">
            <h4>台詞／旁白</h4>
            {render_voice(shot)}
          </section>

          <section class="shot-block">
            <h4>聲音</h4>
            {render_sound(shot)}
          </section>

          <section class="shot-block">
            <h4>首幀提示詞</h4>
            <pre class="code-block" data-label="First frame"><code id="first-frame-{tag}">{escape(shot['first_frame'])}</code></pre>
            <button class="copy-btn" type="button" data-copy-target="first-frame-{tag}">複製首幀提示詞</button>
            {note}
            {backup}
          </section>

          <section class="shot-block">
            <h4>動態（{H3_MODEL}）</h4>
            <dl class="meta-list">{motion_rows}</dl>
            <pre class="code-block" data-label="H3 i2v 提示詞"><code id="i2v-{tag}">{prompt_html(shot["i2v"])}</code></pre>
            <button class="copy-btn" type="button" data-copy-target="i2v-{tag}">複製 i2v 提示詞</button>
            <p class="shot-block__note"><b>提示詞</b> 視覺與原生音軌合為一段，直接貼進 H3 的 image-to-video 欄位（與 <code>design/02</code> 第二十一節逐字一致）。</p>
          </section>

          <section class="shot-block">
            <h4>動態片段（雙 seed）</h4>
            {render_clip_players(shot)}
            <p class="shot-block__note"><b>選片段</b> 同一提示詞換 seed 抽兩次：動作成立、音軌乾淨的那一版進剪輯。檔名、seed 與 prompt_id 記在 <code>assets/video/manifest_i2v.jsonl</code>。</p>
          </section>
        </div>
      </div>
    </article>"""


def render_shot_index(shots: list[dict]) -> str:
    rows = []
    for shot in shots:
        tag = f"{shot['no']:02d}"
        voices = "、".join(line["id"] for line in shot["voices"]) or "—"
        sfx = "、".join(item["name"] for item in shot["sfx"]) or "—"
        clip_links = "".join(
            f'<a class="clip-link" href="../{clip["file"]}">'
            f'{"B" if clip["variant"] == "v2" else "A"} · seed {clip["seed"]}</a>'
            for clip in shot.get("clips", [])
        ) or '<span class="tag tag--pending">未生成</span>'
        rows.append(
            f'<tr data-scene="{escape(shot["scene"])}">'
            f'<td><a href="#shot-{tag}">{tag}</a></td>'
            f"<td>{escape(shot['timecode'])}</td>"
            f"<td>{escape(shot['scene'])}</td>"
            f"<td>{escape(shot['size'])}</td>"
            f"<td>{escape(shot['move'])}</td>"
            f"<td>{escape(voices)}</td>"
            f"<td>{escape(sfx)}</td>"
            f"<td>{clip_links}</td>"
            "</tr>"
        )
    return "".join(rows)


def build_visual_assets() -> tuple[str, str, str]:
    """Build character/scene/prop cards with prompts and images."""
    import json
    from pathlib import Path

    # Load manifest
    manifest = {}
    for mpath in [ROOT / "assets/generated/manifest.jsonl"]:
        if mpath.exists():
            for line in mpath.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    manifest[row["id"]] = row
                except Exception:
                    pass


    # Load prompts from design files and jobs
    prompts_map = {}
    # Try design/04
    d4 = ROOT / "design/04-AI生成提示詞包.md"
    if d4.exists():
        txt = d4.read_text(encoding="utf-8")
        # crude extraction not needed, store for info
        pass
    # Try jobs
    jobs_map = {}
    for jp in [ROOT / "scripts/jobs.json", ROOT / "scripts/jobs_16x9.json"]:
        if jp.exists():
            try:
                import json
                jobs = json.loads(jp.read_text(encoding="utf-8"))
                for j in jobs:
                    if isinstance(j, dict) and j.get("id"):
                        jobs_map[j["id"]] = j
            except Exception:
                pass

    def prompt_block(job: dict | None, label: str = "生成提示詞（節錄）") -> str:
        """Prompt + negative prompt for one generated asset."""
        if not job or not job.get("prompt"):
            return ""
        out = []
        ptxt = job["prompt"]
        if len(ptxt) > 700:
            ptxt = ptxt[:700] + " ..."
        out.append('<p><b>%s</b></p><pre class="code-block"><code>%s</code></pre>' % (escape(label), escape(ptxt)))
        if job.get("negative"):
            neg = job["negative"]
            if len(neg) > 300:
                neg = neg[:300] + " ..."
            out.append('<p><b>負面提示詞</b></p><pre class="code-block"><code>%s</code></pre>' % escape(neg))
        return "".join(out)

    def refs_block(job: dict | None, extra: list[str]) -> str:
        """Reference images used for this asset."""
        items = []
        for r in (job or {}).get("refs") or []:
            if r:
                items.append("<li><code>%s</code></li>" % escape(r))
        for r in extra:
            if r:
                items.append("<li><code>%s</code>（參考圖）</li>" % escape(r))
        return '<p><b>參考圖</b></p><ul>%s</ul>' % ("".join(items) if items else "<li>（無）</li>")

    chars = [
        ("mulan", "木蘭（A·閨中）", "mulan_A_ref", "assets/generated/characters/mulan_A_ref.jpg", "assets/generated/characters/char_A_sheet.jpg", "閨中木蘭，素麻襦裙，長髮鬆挽", "char_A_sheet"),
        ("mulan", "木蘭（B·沙場）", "mulan_B_ref", "assets/generated/characters/mulan_B_ref.jpg", "assets/generated/characters/char_B_sheet.jpg", "沙場木蘭，玄黑札甲，短髮束帶，左眉疤", "char_B_sheet"),
        ("mulan", "木蘭（C·還鄉）", "mulan_C_ref", "assets/generated/characters/mulan_C_ref.jpg", "assets/generated/characters/char_C_sheet.jpg", "還鄉木蘭，鵝黃襦裙，高髻插銀簪", "char_C_sheet"),
        ("family", "父親", "ref_father", "assets/generated/characters/father_ref.jpg", "assets/generated/characters/char_father_sheet.jpg", "約60歲，佝僂持拐，補丁粗布，白鬚短亂", "char_father_sheet"),
        ("family", "阿娘", "ref_mother", "assets/generated/characters/mother_ref.jpg", "assets/generated/characters/char_mother_sheet.jpg", "約55歲，瘦小背駝，深藍襖圍裙，灰白髮髻", "char_mother_sheet"),
        ("family", "阿姊", "ref_sister", "assets/generated/characters/sister_ref.jpg", "assets/generated/characters/char_sister_sheet.jpg", "約22歲，桃紅舊衫，雙鬟插絹花，對鏡撲粉", "char_sister_sheet"),
        ("family", "幼弟", "ref_boy", "assets/generated/characters/boy_ref.jpg", "assets/generated/characters/char_boy_sheet.jpg", "約10歲，過大短褂，赤腳，磨刀集中", "char_boy_sheet"),
        ("others", "戰友（三人組）", None, None, "assets/generated/characters/char_comrades_sheet.jpg", "老雷、瘦子、小石，雜牌甲，刀劍", "char_comrades_sheet"),
        ("others", "天子", None, None, "assets/generated/characters/char_emperor_sheet.jpg", "不露正臉：龍袍下擺、執玉圭、冠冕陰影", "char_emperor_sheet"),
        ("others", "敵軍（黑鐵面具兵）", None, None, "assets/generated/characters/char_enemy_sheet.jpg", "虛構黑鐵面具兵，無民族特徵，統一黑甲", "char_enemy_sheet"),
    ]

    char_html = []
    for group, name, ref_id, ref_file, sheet_file, desc, sheet_id in chars:
        sheet_info = manifest.get(sheet_id, {})
        ref_info = manifest.get(ref_id) if ref_id else {}

        imgs = []
        if ref_file and (ROOT / ref_file).exists():
            imgs.append('<img src="thumbs/characters/%s.jpg" alt="%s 參考" width="200" height="200" loading="lazy">' % (Path(ref_file).stem, escape(name)))
        if (ROOT / sheet_file).exists():
            imgs.append('<img src="thumbs/characters/%s.jpg" alt="%s 設定圖" width="320" height="200" loading="lazy">' % (Path(sheet_file).stem, escape(name)))

        meta_items = []
        if sheet_info.get("seed"):
            meta_items.append("<span>seed %s</span>" % sheet_info["seed"])
        if sheet_info.get("prompt_id"):
            meta_items.append("<span>prompt_id %s...</span>" % sheet_info["prompt_id"][:8])

        meta = " · ".join(meta_items)
        group_label = "主角" if group == "mulan" else ("家人" if group == "family" else "其他")

        file_list = []
        if ref_file:
            file_list.append(ref_file)
        file_list.append(sheet_file)
        file_items = "".join("<li><code>%s</code></li>" % escape(p) for p in file_list)

        job = jobs_map.get(sheet_id)
        prompt_html_block = prompt_block(job)
        refs_html = refs_block(job, [ref_file] if ref_file else [])
        
        char_html.append(
            '      <article class="asset-card" data-visual-group="%s">\n'
            '        <div class="asset-card__head">\n'
            '          <div>\n'
            '            <p class="kicker">%s</p>\n'
            '            <h4>%s</h4>\n'
            '            <p class="asset-desc">%s</p>\n'
            '          </div>\n'
            '          <div class="asset-meta">%s</div>\n'
            '        </div>\n'
            '        <div class="asset-card__images">%s</div>\n'
            '        <details class="asset-prompt">\n'
            '          <summary>查看生成資訊與提示詞</summary>\n'
            '          <div class="asset-prompt__body">\n'
            '            <p><b>檔案</b></p>\n'
            '            <ul>%s</ul>\n'
            '%s\n'
            '%s\n'
            '            <p><b>說明</b>（節錄自 <code>design/01-視覺設定-人物場景道具.md</code>）</p>\n'
            '            <p class="asset-note">%s</p>\n'
            '          </div>\n'
            '        </details>\n'
            '      </article>' % (group, group_label, escape(name), escape(desc), meta, "".join(imgs), file_items, refs_html, prompt_html_block, escape(desc))
        )

    scenes = []
    for i in range(1, 11):
        sid = "S%02d" % i
        s916 = "scene_S%02d" % i
        s169 = "scene_S%02d_16x9" % i
        info916 = manifest.get(s916, {})
        info169 = manifest.get(s169, {})
        job916 = jobs_map.get(s916)
        job169 = jobs_map.get(s169)
        prompt_html_block = prompt_block(job916, "9:16 生成提示詞（節錄）") + prompt_block(
            job169, "16:9 生成提示詞（節錄）"
        )
        refs_html = refs_block(job916, [])
        file_items = "".join(
            "<li><code>%s</code></li>" % escape(fp)
            for fp in (
                "assets/generated/scenes/scene_S%02d.jpg" % i,
                "assets/generated/scenes_16x9/scene_S%02d_16x9.jpg" % i,
            )
        )
        scenes.append(
            '      <article class="asset-card asset-card--wide">\n'
            '        <div class="asset-card__head">\n'
            '          <div>\n'
            '            <p class="kicker">場景 %s</p>\n'
            '            <h4>場景設定（9:16／16:9）</h4>\n'
            '          </div>\n'
            '          <div class="asset-meta">\n'
            '            <span>9:16 seed %s</span>\n'
            '            <span>16:9 seed %s</span>\n'
            '          </div>\n'
            '        </div>\n'
            '        <div class="asset-card__images asset-card__images--scenes">\n'
            '          <figure><img src="thumbs/scenes-916/scene_S%02d.jpg" alt="%s 9:16" width="200" height="320" loading="lazy"><figcaption>9:16 · 720×1280</figcaption></figure>\n'
            '          <figure><img src="thumbs/scenes-169/scene_S%02d_16x9.jpg" alt="%s 16:9" width="320" height="180" loading="lazy"><figcaption>16:9 · 1280×720</figcaption></figure>\n'
            '        </div>\n'
            '        <details class="asset-prompt">\n'
            '          <summary>查看生成資訊與提示詞</summary>\n'
            '          <div class="asset-prompt__body">\n'
            '            <p><b>檔案</b></p>\n'
            '            <ul>%s</ul>\n'
            '%s\n'
            '%s\n'
            '          </div>\n'
            '        </details>\n'
            '      </article>' % (sid, info916.get("seed", "—"), info169.get("seed", "—"), i, sid, i, sid, file_items, refs_html, prompt_html_block)
        )

    props = [
        ("prop_armor", "染血胸甲", "玄黑札甲、皮帶、左肩甲缺口"),
        ("prop_mirror_rouge", "銅鏡與胭脂", "氧化銅鏡、小瓷盒、竹筆"),
        ("prop_short_sword", "短刀", "環首、刃口崩、皮鞘"),
        ("prop_spear_banner", "長槍與旌旗", "雜牌武器、破損旗幟"),
        ("prop_scrolls", "軍帖與簡牘", "木簡、竹簡、軍令"),
        ("prop_yellow_dress", "還鄉襦裙", "鵝黃舊衣、補針、素銀簪"),
    ]
    prop_html = []
    for pid, name, desc in props:
        info = manifest.get(pid, {})
        job = jobs_map.get(pid)
        prop_html.append(
            '      <article class="asset-card">\n'
            '        <div class="asset-card__head">\n'
            '          <div>\n'
            '            <p class="kicker">道具</p>\n'
            '            <h4>%s</h4>\n'
            '            <p class="asset-desc">%s</p>\n'
            '          </div>\n'
            '          <div class="asset-meta"><span>seed %s</span></div>\n'
            '        </div>\n'
            '        <div class="asset-card__images asset-card__images--prop">\n'
            '          <img src="thumbs/props/%s.jpg" alt="%s" width="240" height="240" loading="lazy">\n'
            '        </div>\n'
            '        <details class="asset-prompt">\n'
            '          <summary>查看生成資訊與提示詞</summary>\n'
            '          <div class="asset-prompt__body">\n'
            '            <p><b>檔案</b></p>\n'
            '            <ul><li><code>assets/generated/props/%s.jpg</code></li></ul>\n'
            '%s\n'
            '%s\n'
            '            <p><b>說明</b>（節錄自 <code>design/01-視覺設定-人物場景道具.md</code>）</p>\n'
            '            <p class="asset-note">%s</p>\n'
            '          </div>\n'
            '        </details>\n'
            '      </article>' % (escape(name), escape(desc), info.get("seed", "—"), pid, escape(name), pid, refs_block(job, []), prompt_block(job), escape(desc))
        )

    return "\n".join(char_html), "\n".join(scenes), "\n".join(prop_html)


def build_clip_table(shots: list[dict], scenes: list[dict]) -> str:
    """45 shots x 2 seeds: file, seed and duration of every 16:9 clip."""
    rows = []
    for shot in shots:
        tag = f"{shot['no']:02d}"
        cells = []
        for clip in shot.get("clips", []):
            slot = "B" if clip["variant"] == "v2" else "A"
            cells.append(
                f'<td><a class="clip-link" href="../{clip["file"]}">'
                f'<b>{slot}</b> seed {clip["seed"]}</a>'
                f'<span class="clip-cell__meta">{clip["duration_s"]}s · '
                f'{clip["width"]}×{clip["height"]} · 原生立體聲</span></td>'
            )
        rows.append(
            f'<tr data-scene="{escape(shot["scene"])}">'
            f'<td><a href="#shot-{tag}">{tag}</a></td>'
            f'<td>{escape(shot["scene"])} {escape(shot["scene_title"])}</td>'
            + "".join(cells)
            + f'<td><a class="clip-link" href="#shot-{tag}">看提示詞</a></td>'
            "</tr>"
        )

    filters = ['<button class="filter is-active" type="button" data-clip-filter="all">全部 45</button>']
    for scene in scenes:
        filters.append(
            f'<button class="filter" type="button" data-clip-filter="{escape(scene["id"])}">'
            f'{escape(scene["id"])} {escape(scene["title"])}</button>'
        )

    return (
        '<div class="clip-table-wrap reveal">'
        f'<div class="filters filters--clip">{"".join(filters)}</div>'
        '<table class="clip-table" data-clip-rows>'
        "<thead><tr><th>鏡</th><th>場景</th><th>片段 A</th><th>片段 B</th><th></th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody>'
        "</table></div>"
    )


CUTS_DIR = ASSETS / "video" / "cuts"
ROUGH_CUT_MP4 = CUTS_DIR / "雌雄_粗剪_16x9_粵語_v1.mp4"
ROUGH_CUT_JSON = CUTS_DIR / "雌雄_粗剪_16x9_粵語_v1.json"
MANUAL_CUTS = [
    ("雌雄_手剪_16x9_粵語_v1.mp4", "粵語"),
    ("雌雄_手剪_16x9_普通話_v1.mp4", "普通話"),
]


def load_roughcut() -> dict | None:
    if not ROUGH_CUT_JSON.exists():
        return None
    try:
        return json.loads(ROUGH_CUT_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_roughcut_section() -> str:
    """06B：60 秒粵語粗剪播放器與重跑說明。素材不在就整章不出。"""
    meta = load_roughcut()
    if meta is None or not ROUGH_CUT_MP4.exists():
        return ""

    href = "../" + ROUGH_CUT_MP4.relative_to(ROOT).as_posix()
    json_href = "../" + ROUGH_CUT_JSON.relative_to(ROOT).as_posix()
    dur = meta["frames"] / meta.get("fps", 24)
    overrides = meta.get("overrides") or {}
    override_note = (
        f"（已逐鏡覆蓋 {len(overrides)} 鏡："
        + "、".join(f"鏡{k}→{v}" for k, v in sorted(overrides.items(), key=lambda kv: int(kv[0])))
        + "）"
        if overrides
        else "（全片同一 seed 輪）"
    )
    subs = "有（內嵌軟字幕）" if meta.get("subs") else "無"
    gain = meta.get("ambience_gain", 0.85)

    manual_block = ""
    for manual_name, manual_lang in MANUAL_CUTS:
        manual_mp4 = CUTS_DIR / manual_name
        if not manual_mp4.exists():
            continue
        manual_href = "../" + manual_mp4.relative_to(ROOT).as_posix()
        manual_block += f"""
    <figure class="clip roughcut-player reveal">
      <video controls preload="metadata" playsinline
        poster="thumbs/shots-169/shot_01_16x9.jpg"
        src="{manual_href}"
        aria-label="雌雄 手剪版，16:9 {manual_lang}"></video>
      <figcaption>
        <b>雌雄 · 手剪版 · 16:9 {manual_lang} · 手動剪輯</b>
        <span>115.417s · 1920×1080 · 24fps · 2770 幀 · H.264 + AAC 48k 立體聲 · 約 26 MB</span>
      </figcaption>
    </figure>
"""
    if manual_block:
        manual_block += """
    <p class="section-note reveal" style="margin-top:40px"><b>腳本粗剪</b> —— 45 鏡依 <code>design/02</code> 時間碼自動組接的 60 秒版本，用來驗對點與重跑：</p>
"""

    return f"""
  <section class="chapter" id="roughcut">
    <div class="chapter-head reveal">
      <p class="kicker">06B / Rough cut</p>
      <h2>45 鏡，<br class="br-d">接成 60 秒</h2>
      <p class="lead">動態素材齊了就剪。這一版把 45 段 i2v 片段依 <code>design/02</code> 時間碼逐鏡裁切（24fps 整幀、合計 {meta["frames"]} 幀），混入粵語 DX 對白與各鏡 H3 原生環境聲，並內嵌軟字幕。對白不變速：某句比窗格長時以 L cut 跨到下一畫面，必要時延長片尾讓最後一句講完。粗剪用來驗節奏與對點，不是定剪。本章收錄：上方手剪版（粵語／普通話雙版本、完整節奏），下方腳本粗剪（可重跑、可對點）。</p>
    </div>
{manual_block}
    <figure class="clip roughcut-player reveal">
      <video controls preload="metadata" playsinline
        poster="thumbs/shots-169/shot_01_16x9.jpg"
        src="{href}"
        aria-label="雌雄 60 秒粵語粗剪，16:9"></video>
      <figcaption>
        <b>雌雄 · 粗剪 · 16:9 粵語 · seed {escape(str(meta.get("round", "v1")))} {override_note}</b>
        <span>{dur:.3f}s · {meta["size"]} · {meta["fps"]}fps · {meta["frames"]} 幀 · 環境聲 {gain}× · 字幕 {subs}</span>
      </figcaption>
    </figure>

    <div class="ratio-stats reveal" style="margin-top:28px">
      <div><strong>{dur:.3f}s</strong><span>總時長（含片尾延長）</span></div>
      <div><strong>{meta["frames"]}</strong><span>總幀數</span></div>
      <div><strong>{meta.get("fps", 24)}</strong><span>fps（CFR）</span></div>
      <div><strong>{escape(str(meta.get("size", "1280x720")))}</strong><span>畫幅（裁自 736）</span></div>
      <div><strong>8</strong><span>句 DX 對白</span></div>
      <div><strong>{gain}×</strong><span>環境聲增益</span></div>
    </div>

    <div class="post-grid" style="margin-top:40px">
      <div class="reveal">
        <h3 style="font-family:var(--font-display);font-weight:500;font-size:28px;margin:0 0 16px">怎麼剪的</h3>
        <ul class="checklist">
          <li><b>時間碼</b><span>design/02 V1.1 · shotlist.py 解析</span></li>
          <li><b>取幀</b><span>每鏡取素材前 n 幀；n = round(end×24)−round(start×24)</span></li>
          <li><b>畫幅</b><span>1280×736 居中裁 1280×720</span></li>
          <li><b>對白</b><span>minimax/cantonese → 不變速（只壓停頓）→ L cut 順延</span></li>
          <li><b>片尾</b><span>尾句超過 60s 時延長最後一鏡（tail_frames）</span></li>
          <li><b>環境聲</b><span>各鏡 H3 原生音軌，接點 5ms 淡入出</span></li>
          <li><b>字幕</b><span>mov_text 軟字幕（yue-Hant SRT）</span></li>
        </ul>
      </div>
      <div class="reveal">
        <h3 style="font-family:var(--font-display);font-weight:500;font-size:28px;margin:0 0 16px">重跑與換 seed</h3>
        <pre class="code-block" data-label="Assemble"><code>python3 scripts/assemble_cut.py
python3 scripts/assemble_cut.py --round v2
python3 scripts/assemble_cut.py --ambience-gain 0.5
python3 scripts/assemble_cut.py --no-subs

# 逐鏡指定（例：{{"24": "v2"}}）
python3 scripts/assemble_cut.py --overrides \\
  assets/video/cuts/seed_overrides.json</code></pre>
        <div class="downloads" style="margin-top:18px">
          <a href="{href}"><span>MP4</span>下載粗剪（約 23 MB）</a>
          <a href="../assets/video/cuts/雌雄_手剪_16x9_粵語_v1.mp4"><span>MP4</span>下載手剪版粵語（約 26 MB）</a>
          <a href="../assets/video/cuts/雌雄_手剪_16x9_普通話_v1.mp4"><span>MP4</span>下載手剪版普通話（約 26 MB）</a>
          <a href="{json_href}"><span>JSON</span>逐鏡組接紀錄</a>
          <a href="../assets/video/cuts/README.md"><span>Notes</span>粗剪說明與待辦</a>
          <a href="#shots"><span>Shot list</span>回到 45 鏡清單</a>
        </div>
      </div>
    </div>

    <div class="callout reveal">
      <p><b>定剪前還沒做的：</b>逐鏡挑 v1／v2（用 <code>--overrides</code>）、鏡 15／25／43 後期變速、鏡 31 粵語對嘴素材、音樂鋪底、真人錄音取代 MiniMax DX、環境聲跨鏡交叉淡化。見 <code>assets/video/cuts/README.md</code>。</p>
      <small>TODO / assemble_cut.py · cuts/README.md</small>
    </div>

    <p class="section-note reveal">相對路徑引用 <code>../assets/video/cuts/</code>，發布網站時要把 <code>cuts/</code> 一起放上去，或改用絕對路徑。重組腳本：<code>scripts/assemble_cut.py</code>。</p>
  </section>
"""


def build_shot_list() -> str:
    shots, scenes = build_all()
    facts = summary()

    filters = ['<button class="filter is-active" type="button" data-scene-filter="all">全部 45</button>']
    for scene in scenes:
        count = len(scene["shots"])
        filters.append(
            f'<button class="filter" type="button" data-scene-filter="{escape(scene["id"])}">'
            f'{escape(scene["id"])} {escape(scene["title"])}<i>{count}</i></button>'
        )

    cards = "\n".join(render_shot_card(shot) for shot in shots)

    return f"""
  <section class="chapter" id="shots">
    <div class="chapter-head reveal">
      <p class="kicker">05 / Shot list</p>
      <h2>45 鏡，<br class="br-d">一鏡一格</h2>
      <p class="lead">這一章把整部片攤平：每顆鏡頭的時間碼、畫面劇本、台詞、聲音、首幀提示詞、動態提示詞都在同一格。資料全部由 <code>design/</code> 的設計文件解析而來，不是另外手寫一份。i2v 提示詞是 <strong>{H3_MODEL}</strong> 格式，<strong>視覺描述與原生音軌（環境聲 + 音效）合為一段</strong>，一鍵複製就能貼進 H3；音樂與人聲留給後期。16:9 動態已生成：每鏡兩個 seed，片段可直接在頁面上播放、比較。</p>
    </div>

    <div class="shotlist-stats reveal">
      <div class="stat"><strong>{facts['shots']}</strong><span>鏡頭</span></div>
      <div class="stat"><strong>{facts['scenes']}</strong><span>場景</span></div>
      <div class="stat"><strong>{facts['seconds']:.0f}</strong><span>秒</span></div>
      <div class="stat"><strong>{facts['voice_segments']}</strong><span>人聲段落</span></div>
      <div class="stat"><strong>{len(facts['slow_shots'])}</strong><span>慢動作鏡頭</span></div>
      <div class="stat"><strong>{len(facts['fast_shots'])}</strong><span>高速感鏡頭</span></div>
      <div class="stat"><strong>{facts['native_audio']}</strong><span>鏡有原生音軌</span></div>
      <div class="stat"><strong>{len(facts['lipsync_shots'])}</strong><span>需對嘴</span></div>
    </div>

    <div class="shotlist-tools reveal">
      <div class="shotlist-tools__row">
        <span class="shotlist-tools__label">場景</span>
        <div class="filters" role="group" aria-label="依場景篩選鏡頭">{"".join(filters)}</div>
      </div>
      <div class="shotlist-tools__row">
        <span class="shotlist-tools__label">畫幅</span>
        <div class="filters" role="group" aria-label="切換首幀畫幅">
          <button class="filter is-active" type="button" data-ratio="916">9:16 直式</button>
          <button class="filter" type="button" data-ratio="169">16:9 橫式</button>
        </div>
        <span class="shotlist-tools__count" data-shot-count>顯示 45 / 45 鏡</span>
      </div>
    </div>

    <div class="shotlist-index reveal">
      <table class="shotlist-table">
        <caption>全 45 鏡索引（點鏡號跳到該鏡）</caption>
        <thead>
          <tr><th>鏡</th><th>時間碼</th><th>場景</th><th>景別</th><th>運鏡</th><th>台詞</th><th>音效</th><th>影片</th></tr>
        </thead>
        <tbody data-shot-rows>{render_shot_index(shots)}</tbody>
      </table>
    </div>

    <div class="shotlist-cards" data-shot-cards>
{cards}
    </div>
  </section>"""


def make_page(cards: str, counts: dict[str, int]) -> str:
    total = counts["all"]
    prompt_library = build_prompt_library()
    shot_list = build_shot_list()

    shots, scenes = build_all()
    by_no = {shot["no"]: shot for shot in shots}
    motion_blocks: dict[str, str] = {}
    for no in (15, 23, 27, 42):
        shot = by_no[no]
        motion_blocks[f"{{{{MOTION_PROMPT_{no}}}}}"] = prompt_html(shot["i2v"])
        motion_blocks[f"{{{{MOTION_CLIPS_{no}}}}}"] = render_clip_players(shot)
    motion_blocks["{{CLIP_TABLE}}"] = build_clip_table(shots, scenes)
    motion_blocks["{{ROUGH_CUT}}"] = build_roughcut_section()
    vchars, vscenes, vprops = build_visual_assets()
    motion_blocks["{{VISUAL_CHARACTERS}}"] = vchars
    motion_blocks["{{VISUAL_SCENES}}"] = vscenes
    motion_blocks["{{VISUAL_PROPS}}"] = vprops

    page = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="《雌雄》從〈木蘭辭〉到 60 秒短片的完整製作 SOP：視覺聖經、45 鏡分鏡、90 支 i2v 片段、60 秒粵語粗剪、9:16 普通話與 16:9 粵語雙版本。">
  <meta property="og:title" content="雌雄 · 從〈木蘭辭〉到 60 秒短片">
  <meta property="og:description" content="一份可以重跑的 AI 短片製作手冊，附 133 張生成圖、90 支 16:9 動態片段與 60 秒粵語粗剪。">
  <meta property="og:type" content="website">
  <title>雌雄 · 從〈木蘭辭〉到 60 秒短片｜製作 SOP</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' fill='%239b2c24'/%3E%3Crect x='6' y='6' width='52' height='52' fill='none' stroke='%23f3eee4' stroke-width='2'/%3E%3C/svg%3E">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
<a class="skip" href="#main">跳至主要內容</a>

<header class="topbar">
  <a class="brand" href="#top" aria-label="回到首頁">
    <strong>雌雄</strong>
    <span>Production Dossier</span>
  </a>
  <nav class="chapters" aria-label="章節">
    <a href="#overview">00 專案</a>
    <a href="#story">01 故事</a>
    <a href="#visual">02 視覺</a>
    <a href="#visual-assets">02B 視覺設定</a>
    <a href="#sop">03 SOP</a>
    <a href="#doc-prompts">03B 提示詞</a>
    <a href="#pipeline">04 管線</a>
    <a href="#shots">05 鏡頭清單</a>
    <a href="#motion">06 動態</a>
    <a href="#roughcut">06B 粗剪</a>
    <a href="#ratio">07 雙畫幅</a>
    <a href="#sound">08 聲音</a>
    <a href="#post">09 後期</a>
    <a href="#gallery">10 圖庫</a>
    <a href="#reproduce">11 重現</a>
  </nav>
  <a class="nav-cta" href="#roughcut">看 60 秒粗剪</a>
</header>

<main id="main">
  <section class="hero" id="top">
    <div class="hero-copy">
      <p class="eyebrow">Production dossier · 60 sec · 2026</p>
      <h1 class="hero-title">雌雄</h1>
      <p class="hero-sub">從〈木蘭辭〉到 60 秒短片</p>
      <p class="lede">一份可以重跑的製作手冊。從命題、視覺聖經、45 鏡分鏡、Qwen Image 2.1 生成，到 9:16 普通話與 16:9 粵語雙版本。不是作品集，是把每一步留下來，讓下一次可以少走一點冤枉路。</p>
      <div class="hero-meta">
        <span>60 秒</span>
        <span>45 鏡</span>
        <span>133 張圖</span>
        <span>90 支片段</span>
        <span>3 支剪輯</span>
        <span>2 語言</span>
      </div>
      <div class="hero-actions">
        <a class="btn" href="#roughcut">看 60 秒粗剪</a>
        <a class="btn btn--ghost" href="#sop">讀完整 SOP</a>
        <a class="btn btn--ghost" href="#shots">查 45 鏡清單</a>
      </div>
      <div class="status-pill"><i></i> Rough cut ready / final pending</div>
    </div>

    <div class="hero-strip" aria-label="代表畫面">
      <figure class="still">
        <img src="thumbs/shots-169/shot_01_16x9.jpg" alt="S01 鐵甲與營帳，16:9 鏡頭首幀" width="640" height="360">
        <figcaption><span>S01 / 鐵甲</span><span>16:9</span></figcaption>
      </figure>
      <figure class="still">
        <img src="thumbs/shots-169/shot_02_16x9.jpg" alt="S02 銅鏡與胭脂，16:9 鏡頭首幀" width="640" height="360">
        <figcaption><span>S02 / 胭脂</span><span>16:9</span></figcaption>
      </figure>
      <figure class="still">
        <img src="thumbs/shots-169/shot_42_16x9.jpg" alt="S42 開門逆光，16:9 鏡頭首幀" width="640" height="360">
        <figcaption><span>S42 / 開門</span><span>16:9</span></figcaption>
      </figure>
      <div class="seal" aria-hidden="true">雌雄</div>
    </div>
  </section>

  <section class="chapter" id="overview">
    <div class="chapter-head reveal">
      <p class="kicker">00 / Project</p>
      <h2>先決定不要什麼</h2>
      <p class="lead">《木蘭辭》很容易被拍成史詩。我們刻意反過來：不做大場面，不做英雄主題，不做真實民族敵人，不做美顏。60 秒只留一個問題——一個人如何把「應該」脫下來。</p>
    </div>

    <div class="overview-grid reveal">
      <article class="note-card">
        <span>Premise</span>
        <h3>粗糙的鐵甲，細膩的胭脂</h3>
        <p>全片的視覺命題，是兩種材質長在同一個人身上。鐵甲越冷，胭脂越私人；戰場越大，銅鏡越小。</p>
      </article>
      <article class="note-card">
        <span>Constraint</span>
        <h3>限制不是省錢，是剪輯</h3>
        <p>紅色只出現六處；血一律暗褐乾涸；敵軍用虛構黑鐵面具；全片只三次逆光。限制讓 60 秒有記憶點。</p>
      </article>
      <article class="note-card">
        <span>Deliverable</span>
        <h3>兩個版本，不是一個加減</h3>
        <p>9:16 普通話版與 16:9 粵語版各自獨立生成、獨立構圖、獨立混音。不是把同一支片裁成兩種比例。</p>
      </article>
    </div>

    <div class="status-board reveal" aria-label="專案狀態">
      <div class="status-row"><span>設計文件</span><b>完成</b><i style="--v:100%"></i></div>
      <div class="status-row"><span>首幀圖</span><b>完成</b><i style="--v:100%"></i></div>
      <div class="status-row"><span>動態 16:9</span><b>完成 ×2 seed</b><i style="--v:100%"></i></div>
      <div class="status-row"><span>粗剪</span><b>粵語可看</b><i style="--v:55%"></i></div>
      <div class="status-row"><span>定剪／混音</span><b>未完成</b><i style="--v:20%"></i></div>
    </div>
  </section>

  <section class="chapter" id="story">
    <div class="chapter-head reveal">
      <p class="kicker">01 / Story</p>
      <h2>60 秒只留三件事</h2>
      <p class="lead">她是誰、她經歷了什麼、她最後為什麼笑。其餘全部剪掉。分鏡先寫聲音，再寫畫面；因為觀眾閉上眼時，故事仍然要成立。</p>
    </div>

    <div class="timeline reveal" aria-label="60 秒故事結構">
      <article class="beat" style="--span:15;--fill:1">
        <span class="beat-time">00–15</span>
        <div><h3>營帳與織房</h3><p>鐵甲、胭脂、四市。建立「她本來可以不這樣」。</p></div>
      </article>
      <article class="beat" style="--span:10;--fill:1">
        <span class="beat-time">15–25</span>
        <div><h3>黃河 · 黑山</h3><p>渡河、宿營。第一次離開家，鏡頭開始變寬。</p></div>
      </article>
      <article class="beat" style="--span:10;--fill:1">
        <span class="beat-time">25–35</span>
        <div><h3>雪原戰場</h3><p>十年征戰壓縮成一個冬天。血是褐的，不是紅的。</p></div>
      </article>
      <article class="beat" style="--span:8;--fill:1">
        <span class="beat-time">35–43</span>
        <div><h3>金鑾殿</h3><p>辭官。全片唯一一次正面頂光，也是唯一一次她說「不」。</p></div>
      </article>
      <article class="beat" style="--span:9;--fill:1">
        <span class="beat-time">43–52</span>
        <div><h3>返鄉</h3><p>換裝。胭脂重新出現，但這次不是為了遮掩。</p></div>
      </article>
      <article class="beat" style="--span:5;--fill:1">
        <span class="beat-time">52–57</span>
        <div><h3>開門</h3><p>老雷認不出她。逆光把兩個人切成一明一暗。</p></div>
      </article>
      <article class="beat" style="--span:3;--fill:1">
        <span class="beat-time">57–60</span>
        <div><h3>雙兔</h3><p>收在笑聲，不收在口號。雌雄不是答案，是問題。</p></div>
      </article>
    </div>

    <div class="story-stats reveal">
      <div class="stat"><strong>45</strong><span>鏡頭</span></div>
      <div class="stat"><strong>8</strong><span>人聲段落</span></div>
      <div class="stat"><strong>117</strong><span>字</span></div>
      <div class="stat"><strong>27s</strong><span>人聲總長</span></div>
    </div>

    <div class="callout reveal">
      <p>全片只三次逆光：斷髮、開門、雙兔。每一次都代表一個身份被光切開。</p>
      <small>Lighting rule / 00-視覺聖經</small>
    </div>
  </section>

  <section class="chapter" id="visual">
    <div class="chapter-head reveal">
      <p class="kicker">02 / Visual language</p>
      <h2>紅色不是配色，<br class="br-d">是敘事</h2>
      <p class="lead">如果紅色到處都是，觀眾就不會記得任何一個紅。我們把紅色當成標點符號：只在句子需要停頓的地方出現。</p>
    </div>

    <div class="palette reveal" aria-label="色票">
      <div class="swatch" style="--c:#141311"><b>INK</b><span>#141311</span></div>
      <div class="swatch" style="--c:#e9e3d6"><b>PAPER</b><span>#E9E3D6</span></div>
      <div class="swatch" style="--c:#9b2c24"><b>CINNABAR</b><span>#9B2C24</span></div>
      <div class="swatch" style="--c:#687365"><b>BRONZE</b><span>#687365</span></div>
      <div class="swatch" style="--c:#22323c"><b>NIGHT BLUE</b><span>#22323C</span></div>
      <div class="swatch" style="--c:#f3eee4"><b>BONE</b><span>#F3EEE4</span></div>
    </div>

    <div class="red-grid reveal" aria-label="紅色出現的六個地方">
      <div class="red-item"><b>01</b><span>唇</span></div>
      <div class="red-item"><b>02</b><span>官印</span></div>
      <div class="red-item"><b>03</b><span>血</span></div>
      <div class="red-item"><b>04</b><span>旗邊</span></div>
      <div class="red-item"><b>05</b><span>花鈿</span></div>
      <div class="red-item"><b>06</b><span>門聯</span></div>
    </div>
    <p class="section-note reveal">花鈿在角色設定裡曾用金箔，在視覺聖經裡被列為紅色。這是目前文件之間唯一未定案的矛盾；正式製作前要在 00 與 01 之間選一個，不要讓生成模型自己決定。</p>

    <div class="material-grid reveal">
      <figure>
        <img src="thumbs/shots-169/shot_01_16x9.jpg" alt="S01 鐵甲與營帳" width="640" height="360" loading="lazy">
        <figcaption><span>鐵甲 / 冷、粗、重</span><span>S01</span></figcaption>
      </figure>
      <figure>
        <img src="thumbs/shots-169/shot_02_16x9.jpg" alt="S02 銅鏡與胭脂" width="640" height="360" loading="lazy">
        <figcaption><span>胭脂 / 小、私、暖</span><span>S02</span></figcaption>
      </figure>
      <figure>
        <img src="thumbs/shots-169/shot_42_16x9.jpg" alt="S42 開門逆光" width="640" height="360" loading="lazy">
        <figcaption><span>門 / 光、家、審判</span><span>S42</span></figcaption>
      </figure>
    </div>

    <div class="do-not reveal">
      <div><b>Do not 01</b>美顏、磨皮、空氣感底妝。皮膚要有毛孔與風霜。</div>
      <div><b>Do not 02</b>鮮紅血漿、發光符文、粒子特效。血是暗褐、乾涸、沾在布上。</div>
      <div><b>Do not 03</b>把敵軍做成可辨識的真實民族。用虛構黑鐵面具，避免歷史錯置。</div>
      <div><b>Do not 04</b>滿屏紅色。紅色只在六處，其他時候讓墨、紙、銅綠說話。</div>
    </div>
  </section>

  <section class="chapter" id="visual-assets">
    <div class="chapter-head reveal">
      <p class="kicker">02B / Visual assets</p>
      <h2>視覺設定</h2>
      <p class="lead">從設計文件提煉的設定，搭配實際生成的參考圖、設定圖與場景圖。每張圖附上用於生成的提示詞、參考圖與相關檔案，方便重跑與校對。</p>
    </div>

    <h3 style="font-family:var(--font-display);font-weight:500;font-size:28px;margin:40px 0 16px" id="visual-characters">人物</h3>
    <div class="filters reveal">
      <button class="filter is-active" type="button" data-visual-filter="all">全部</button>
      <button class="filter" type="button" data-visual-filter="mulan">木蘭</button>
      <button class="filter" type="button" data-visual-filter="family">家人</button>
      <button class="filter" type="button" data-visual-filter="others">其他</button>
    </div>
    <div class="asset-grid reveal">
      {{VISUAL_CHARACTERS}}
    </div>

    <h3 style="font-family:var(--font-display);font-weight:500;font-size:28px;margin:64px 0 16px" id="visual-scenes">場景</h3>
    <p class="section-note reveal">10 個場景各有 9:16 與 16:9 兩種構圖，兩者獨立生成。</p>
    <div class="asset-grid asset-grid--scenes reveal">
      {{VISUAL_SCENES}}
    </div>

    <h3 style="font-family:var(--font-display);font-weight:500;font-size:28px;margin:64px 0 16px" id="visual-props">道具</h3>
    <div class="asset-grid asset-grid--props reveal">
      {{VISUAL_PROPS}}
    </div>

    <p class="section-note reveal">來源：<a href="../design/01-視覺設定-人物場景道具.md">design/01-視覺設定-人物場景道具.md</a>、<a href="../design/00-視覺聖經.md">design/00-視覺聖經.md</a>、<code>assets/generated/manifest.jsonl</code>。</p>
  </section>

  <section class="chapter" id="sop">
    <div class="chapter-head reveal">
      <p class="kicker">03 / SOP</p>
      <h2>從一句話<br class="br-d">到 133 張圖</h2>
      <p class="lead">這條流程的重點不是「用哪個模型」，而是每個階段都有可檢查的產出。上一階段沒有通關，就不要把問題帶進生成。每一步對應的設計文件，都可以在下方 <a href="#doc-prompts">提示詞庫</a> 直接複製生成提示詞。</p>
    </div>

    <div class="sop-list">
      <article class="sop-step reveal">
        <div class="sop-num">00</div>
        <div class="sop-body">
          <h3>命題與限制</h3>
          <p>先寫一句話：「粗糙的鐵甲與細膩的胭脂，長在同一個人身上。」再寫不能做的事：不做史詩、不做英雄主題、不做真實民族敵人、不做美顏。限制越早寫，後面越少返工。</p>
          <div class="sop-meta"><span>輸入 <b>原詩、片長、平台</b></span><span>產出 <b>命題、限制清單、版本矩陣</b></span></div>
          <div class="gate"><b>GATE</b> 能用一句話說完全片，且知道哪些東西不能出現。</div>
          <p class="sop-prompt-link"><a href="#brief-template">↓ 先複製共用 Brief</a></p>
        </div>
      </article>

      <article class="sop-step reveal">
        <div class="sop-num">01</div>
        <div class="sop-body">
          <h3>視覺聖經</h3>
          <p>視覺聖經不是 moodboard，是判準。色彩、光線、鏡頭、材質、符號，每一條都要能回答「這個鏡頭該不該這樣拍」。寫下紅色六處、三次逆光、血的顏色、敵軍的處理方式。</p>
          <div class="sop-meta"><span>輸入 <b>命題、參考片、歷史資料</b></span><span>產出 <b>design/00-視覺聖經.md</b></span></div>
          <div class="gate"><b>GATE</b> 攝影、美術、生成、剪輯都能引用同一條規則。</div>
          <p class="sop-prompt-link"><a href="#prompt-00">↓ 複製「視覺聖經」生成提示詞</a></p>
        </div>
      </article>

      <article class="sop-step reveal">
        <div class="sop-num">02</div>
        <div class="sop-body">
          <h3>人物、場景、道具</h3>
          <p>先做參考圖，再做設定圖，再做道具與場景。角色設定圖用中性灰背景，目的是對照，不是海報。道具要能靠輪廓認出；場景要有可重複的光位。</p>
          <div class="sop-meta"><span>輸入 <b>視覺聖經</b></span><span>產出 <b>design/01-視覺設定-人物場景道具.md</b></span></div>
          <div class="gate"><b>GATE</b> 每個角色有剪影記憶點；每件道具在遠景也能被認出。</div>
          <p class="sop-prompt-link"><a href="#prompt-01">↓ 複製「視覺設定」生成提示詞</a></p>
        </div>
      </article>

      <article class="sop-step reveal">
        <div class="sop-num">03</div>
        <div class="sop-body">
          <h3>45 鏡分鏡</h3>
          <p>每鏡都要有時間碼、景別、機位、運鏡、聲音。分鏡不是畫面清單，是剪輯計畫。先問「這一鏡刪掉會怎樣」，答不出來就刪。</p>
          <div class="sop-meta"><span>輸入 <b>60 秒結構、角色、場景</b></span><span>產出 <b>design/02-分鏡表-靜態與動態.md</b></span></div>
          <div class="gate"><b>GATE</b> 每顆鏡頭都有存在的理由，且能接到下一顆。</div>
          <p class="sop-prompt-link"><a href="#prompt-02">↓ 複製「分鏡表：靜態與動態」生成提示詞</a></p>
        </div>
      </article>

      <article class="sop-step reveal">
        <div class="sop-num">04</div>
        <div class="sop-body">
          <h3>臺詞與旁白</h3>
          <p>8 句人聲、117 字、約 27 秒。先修到關掉畫面也聽得懂，再進錄音。標出斷句、重音、停頓與字幕斷行；不要讓演員在錄音室裡幫你改劇本。</p>
          <div class="sop-meta"><span>輸入 <b>原詩、分鏡</b></span><span>產出 <b>design/03-臺詞與雙語版本.md</b></span></div>
          <div class="gate"><b>GATE</b> 斷句、重音、停頓都能被演員執行。</div>
          <p class="sop-prompt-link"><a href="#prompt-03">↓ 複製「臺詞與雙語版本」生成提示詞</a></p>
        </div>
      </article>

      <article class="sop-step reveal">
        <div class="sop-num">05</div>
        <div class="sop-body">
          <h3>提示詞包</h3>
          <p>提示詞包是全片唯一的視覺語言。Global style、refs、props、scenes、45 shots、negative 分層管理。每個角色只綁定一張主參考圖，避免模型在兩張臉之間平均。</p>
          <div class="sop-meta"><span>輸入 <b>視覺聖經、設定圖</b></span><span>產出 <b>design/04-AI生成提示詞包.md</b></span></div>
          <div class="gate"><b>GATE</b> 同一角色在不同鏡頭可辨識；負面詞能擋掉現代感。</div>
          <p class="sop-prompt-link"><a href="#prompt-04">↓ 複製「AI 生成提示詞包」生成提示詞</a></p>
        </div>
      </article>

      <article class="sop-step reveal">
        <div class="sop-num">06</div>
        <div class="sop-body">
          <h3>生成管線</h3>
          <p>用 <code>build_jobs.py</code> 把設計文件變成 <code>jobs.json</code>；用 <code>comfy_batch.py</code> 送到 ComfyUI；用 manifest 記錄每一次生成。設計文件是原始碼，JSON 是編譯後的任務，manifest 是執行紀錄。</p>
          <div class="sop-meta"><span>輸入 <b>提示詞包</b></span><span>產出 <b>jobs.json、jobs_16x9.json、manifest.jsonl</b></span></div>
          <div class="gate"><b>GATE</b> 任何一張圖都能追溯提示詞、refs、尺寸與生成時間。</div>
        </div>
      </article>

      <article class="sop-step reveal">
        <div class="sop-num">07</div>
        <div class="sop-body">
          <h3>首幀與重生成</h3>
          <p>先跑 batch，再整批看 contact sheet。不要一張一張盯；問題要在總表上看出來。把手、臉、文字、歷史錯置、構圖重複列成檢查表，通過的才放進 overrides 之外。</p>
          <div class="sop-meta"><span>輸入 <b>jobs.json</b></span><span>產出 <b>45 張鏡頭、10 張場景、overrides.json</b></span></div>
          <div class="gate"><b>GATE</b> 手、臉、文字、歷史錯置、構圖重複都檢查過。</div>
        </div>
      </article>

      <article class="sop-step reveal">
        <div class="sop-num">08</div>
        <div class="sop-body">
          <h3>雙畫幅</h3>
          <p>16:9 不是裁切。改提示詞、改構圖、重新採樣，只重生成 scenes 與 shots。角色設定圖與道具維持原比例，因為它們是參考，不是鏡頭。</p>
          <div class="sop-meta"><span>輸入 <b>9:16 分鏡、16:9 版本決策</b></span><span>產出 <b>10 張場景、45 張鏡頭、55 張 16:9</b></span></div>
          <div class="gate"><b>GATE</b> 16:9 的安全框、人物位置、字幕空間都獨立檢查。</div>
        </div>
      </article>

      <article class="sop-step reveal">
        <div class="sop-num">09</div>
        <div class="sop-body">
          <h3>聲音與雙語</h3>
          <p>9:16 普通話、16:9 粵語。同一語言內，木蘭與 VO 由同一人聲扮演；粵語不是普通話配音。V1–V5、V8 用粵讀文言保留原句；V6、V7 用粵語口語，讓角色真的像在香港長大。</p>
          <div class="sop-meta"><span>輸入 <b>臺詞、音色設計</b></span><span>產出 <b>design/05、06、07；音樂音效、聲音設計、配音執行包</b></span></div>
          <div class="gate"><b>GATE</b> V6/V7 的粵語口語與嘴型能在剪輯裡成立。</div>
          <p class="sop-prompt-link"><a href="#prompt-05">↓ 音樂音效</a> · <a href="#prompt-06">聲音設計</a> · <a href="#prompt-07">配音執行包</a></p>
        </div>
      </article>

      <article class="sop-step reveal">
        <div class="sop-num">10</div>
        <div class="sop-body">
          <h3>後期與交付</h3>
          <p>animatic → i2v → 對嘴 → 字幕 → 音樂音效 → 混音 → 調色 → QC → 交付。先剪 animatic，確認 60 秒成立，再花錢生成動態。動態規格已寫在 <a href="#motion">06 動態</a> 與 <code>design/02</code>；兩個版本各自完整，不是一個版本加減。</p>
          <div class="sop-meta"><span>輸入 <b>首幀、聲音、剪輯</b></span><span>產出 <b>master、stems、字幕、stills、交付清單</b></span></div>
          <div class="gate"><b>GATE</b> 兩個版本各自完整，且都通過 -14 LUFS 與安全框檢查。</div>
        </div>
      </article>
    </div>

    {{PROMPT_LIBRARY}}
  </section>

  <section class="chapter" id="pipeline">
    <div class="chapter-head reveal">
      <p class="kicker">04 / Pipeline</p>
      <h2>設計文件<br class="br-d">就是原始碼</h2>
      <p class="lead">不要把提示詞留在聊天框裡。把可重跑的內容放進 Markdown，把任務編譯成 JSON，把每次生成寫進 manifest。這樣你才能回答「這張圖是怎麼來的」。</p>
    </div>

    <div class="flow reveal" aria-label="生成管線">
      <div class="flow-box"><span>01 / Design</span><b>8 份設計文件</b><small>視覺聖經、視覺設定、分鏡（靜態＋動態）、臺詞與雙語、AI 提示詞、音樂音效、聲音設計、配音執行包。</small></div>
      <div class="flow-arrow" aria-hidden="true">→</div>
      <div class="flow-box"><span>02 / Compile</span><b>build_jobs.py</b><small>解析提示詞包，套用 overrides，產出 jobs.json。</small></div>
      <div class="flow-arrow" aria-hidden="true">→</div>
      <div class="flow-box"><span>03 / Generate</span><b>comfy_batch.py</b><small>上傳 refs、送出 workflow、等待、下載、寫 manifest。</small></div>
      <div class="flow-arrow" aria-hidden="true">→</div>
      <div class="flow-box"><span>04 / Archive</span><b>133 張圖 + 90 支片段 + 紀錄</b><small>可追溯的資產，加上 contact sheet 與這份教學。</small></div>
    </div>

    <p class="section-note reveal">存檔格式也是流程的一部分：ComfyUI 給 PNG，但 AI 影像的 PNG 是純浪費——同一張 720×1280 鏡頭，PNG 1.2 MB、JPEG（q90、4:4:4）只要 144 KB，整批 185 MB 降到 21 MB，尺寸與肉眼品質不變。<code>comfy_batch.py</code> 下載後直接寫 JPG，舊資產用 <code>to_jpg.py</code> 一次轉完。</p>

    <table class="model-table reveal">
      <tbody>
        <tr><th>ComfyUI</th><td>0.37.4，遠端節點；實際主機位址放在本機環境變數 <code>COMFY_BASE</code>，不寫進公開頁面。</td></tr>
        <tr><th>Base model</th><td><code>qwen_image_2.1_int8_convrot.safetensors</code></td></tr>
        <tr><th>Text encoder</th><td><code>qwen3vl_8b_int8_convrot.safetensors</code></td></tr>
        <tr><th>VAE</th><td><code>qwen_image_2.1_vae_bf16.safetensors</code></td></tr>
        <tr><th>Sampler</th><td><code>euler</code> / <code>simple</code>；25 steps；cfg 2.0；denoise 1.0。</td></tr>
        <tr><th>Output</th><td>9:16 為 720×1280；16:9 為 1280×720。角色設定與道具維持原始比例。</td></tr>
      </tbody>
    </table>

    <div class="prompt-anatomy reveal" aria-label="提示詞結構">
      <span>主體</span><span>景別與機位</span><span>光線</span><span>材質</span><span>時代與風格</span><span>負面詞</span>
    </div>

    <pre class="code-block reveal" data-label="Build & run"><code>python3 scripts/build_jobs.py

# 9:16 基礎資產
python3 scripts/comfy_batch.py --kind ref
python3 scripts/comfy_batch.py --kind sheet
python3 scripts/comfy_batch.py --kind prop
python3 scripts/comfy_batch.py --kind scene
python3 scripts/comfy_batch.py --kind shot --start 1 --limit 10

# 16:9 獨立重生成
python3 scripts/comfy_batch.py \\
  --jobs scripts/jobs_16x9.json \\
  --start 2 --limit 18 \\
  --manifest assets/generated/manifest_16x9.jsonl

# PNG 轉 JPEG（comfy_batch 已直接輸出 JPG，此步用於舊資產）
python3 scripts/to_jpg.py</code></pre>

    <article class="shot-card reveal">
      <img src="thumbs/shots-169/shot_30_16x9.jpg" alt="S30 金鑾殿抱拳，16:9 鏡頭首幀" width="640" height="360" loading="lazy">
      <div class="shot-card__body">
        <p class="kicker">Shot card / S30</p>
        <h3>把「行禮」寫清楚</h3>
        <p>第一版生成出現現代舉手禮。修正不是加「古裝」，而是把動作寫死：single knee, cupped-hand salute, baoquan, no modern military salute。負面詞要擋的是動作，不只是服裝。</p>
        <dl class="meta-list">
          <dt>檔案</dt><dd>shots_16x9/shot_30_16x9.jpg</dd>
          <dt>尺寸</dt><dd>1280 × 720 / 16:9</dd>
          <dt>參考</dt><dd>Mulan B / 金鑾殿場景</dd>
          <dt>參數</dt><dd>25 steps / cfg 2.0 / euler simple</dd>
        </dl>
      </div>
    </article>

    <div class="lessons reveal">
      <div class="lesson"><b>Fix 01</b><strong>現代舉手禮</strong><span>把抱拳、單膝、視角都寫進提示詞；負面詞加入 modern military salute。</span></div>
      <div class="lesson"><b>Fix 02</b><strong>沙漠而不是雪原</strong><span>遠景只寫「戰場」會默認成沙漠；補上 wind-scoured snow pass、dark rock。</span></div>
      <div class="lesson"><b>Fix 03</b><strong>誤用 B 參考圖</strong><span>shot_03 需要更年輕、更素的脸；改用 A 參考圖，並移除眼線與磨皮。</span></div>
      <div class="lesson"><b>Fix 04</b><strong>男性的手</strong><span>特寫手部要獨立描述：slender female hand, short unpolished nails, small scars。</span></div>
    </div>
  </section>

{{SHOT_LIST}}

  <section class="chapter" id="motion">
    <div class="chapter-head reveal">
      <p class="kicker">06 / Motion</p>
      <h2>動態不是<br class="br-d">讓畫面動</h2>
      <p class="lead">45 張首幀只是起點。動態分鏡決定它們怎麼活：重量、速度、剪點。這份規格必須在買 i2v 之前完成，否則你會在生成完 45 段素材後，才發現動態是亂的。</p>
    </div>

    <p class="section-note reveal">動態分三層：<strong>L-A 主體動作</strong>（角色或物件自己動）、<strong>L-B 攝影機運動</strong>（虛擬攝影機動）、<strong>L-C 環境動態</strong>（風、煙、水、布料等世界元素動）。一鏡只讓一層主動，其餘兩層降到八成以下。</p>

    <div class="overview-grid overview-grid--motion reveal">
      <div class="note-card">
        <span>L-A / 主體動作</span>
        <h3>角色或物件自己動</h3>
        <p>抬手、落甲、握拳、開門、起立。全片只有 18 顆鏡頭由這層主導——因為 AI 生成最不可靠的，就是「人做複雜動作」。</p>
      </div>
      <div class="note-card">
        <span>L-B / 攝影機運動</span>
        <h3>虛擬攝影機動</h3>
        <p>推、拉、橫、升、手持晃、固定。速度全部量化：推 5–15 cm/s、拉 10–25 cm/s、手持呼吸晃 0.5–1.5°。i2v 最穩的一層。</p>
      </div>
      <div class="note-card">
        <span>L-C / 環境動態</span>
        <h3>風、煙、水、布料等世界元素動</h3>
        <p>風、雪、塵、火光、煙、水、布料。雪要橫掃、火光 8–12Hz 擺動、煙塵 0.5 m/s 擴散——物理不對，觀眾不用說就會覺得假。</p>
      </div>
    </div>

    <div class="do-not reveal">
      <div><b>Rule 01</b>一鏡只讓一層主動。其餘兩層降到八成以下，否則畫面會手舞足蹈而沒有重點。</div>
      <div><b>Rule 02</b>動態必須剪得掉。每個動作都要有明確的起 pose 與止 pose，剪點只能落在動作最高點或停頓處。</div>
      <div><b>Rule 03</b>動態服從剪輯，不服從模型。i2v 只會給你一段它自己發明的運動。</div>
      <div><b>Rule 04</b>慢動作全片只有三處：斷髮 0.4x、中箭 0.25x、雙兔 0.6x。其餘一律 24fps。</div>
    </div>

    <h3 style="font-family:var(--font-display);font-weight:500;font-size:28px;margin:48px 0 16px">全片動態強度曲線</h3>
    <div class="timeline reveal" aria-label="全片動態強度曲線">
      <article class="beat" style="--span:1;--fill:0.4"><span class="beat-time">S1</span><div><h3>2</h3><p>營帳 · 材質動態</p></div></article>
      <article class="beat" style="--span:1;--fill:0.4"><span class="beat-time">S2</span><div><h3>2</h3><p>織房 · 機械動態</p></div></article>
      <article class="beat" style="--span:1;--fill:0.8"><span class="beat-time">S3</span><div><h3>4</h3><p>四市 · 全片最快</p></div></article>
      <article class="beat" style="--span:1;--fill:0.6"><span class="beat-time">S4</span><div><h3>3</h3><p>黃河 · 尺度</p></div></article>
      <article class="beat" style="--span:1;--fill:0.4"><span class="beat-time">S5</span><div><h3>2</h3><p>黑山 · 風雪</p></div></article>
      <article class="beat" style="--span:1;--fill:1"><span class="beat-time">S6</span><div><h3>5</h3><p>雪原 · 爆點</p></div></article>
      <article class="beat" style="--span:1;--fill:0.2"><span class="beat-time">S7</span><div><h3>1</h3><p>金鑾殿 · 秩序</p></div></article>
      <article class="beat" style="--span:1;--fill:0.6"><span class="beat-time">S8</span><div><h3>3</h3><p>返鄉 · 生活</p></div></article>
      <article class="beat" style="--span:1;--fill:0.6"><span class="beat-time">S9</span><div><h3>3</h3><p>開門 · 由快到慢</p></div></article>
      <article class="beat" style="--span:1;--fill:0.4"><span class="beat-time">S10</span><div><h3>2</h3><p>雙兔 · 收</p></div></article>
    </div>
    <p class="section-note reveal">曲線：<strong>2 → 2 → 4 → 3 → 2 → 5 → 1 → 3 → 3 → 2</strong>。S7 的 1 是刻意的斷崖——觀眾剛看過戰場混亂，突然進入絕對秩序。紅線長度＝動態強度（0–5）。</p>

    <div class="lessons reveal">
      <div class="lesson"><b>Still 01</b><strong>鏡 19 · 黑山雪暴</strong><span>2 秒裡小黑點幾乎不動，動的只有橫掃的雪。</span></div>
      <div class="lesson"><b>Still 02</b><strong>鏡 31 · 金鑾殿搖頭</strong><span>搖頭前 0.3 秒，環境與身體全部靜止，只有頭在動。</span></div>
      <div class="lesson"><b>Still 03</b><strong>鏡 45 · 定格</strong><span>眼神停住 0.3 秒後切黑，讓最後一記鼓聲在黑暗裡收。</span></div>
      <div class="lesson"><b>Cut on action</b><strong>12 處動作接動作</strong><span>硬切為主：甲砸泥→筆壓唇、槍穿盾→箭入肉、走出光柱→駝蹄踏土。</span></div>
    </div>

    <h3 style="font-family:var(--font-display);font-weight:500;font-size:28px;margin:48px 0 16px">四顆鏡頭的動態怎麼寫</h3>

    <article class="shot-card reveal">
      <img src="thumbs/shots-916/shot_15.jpg" alt="鏡 15 斷髮，9:16 首幀" width="400" height="640" loading="lazy">
      {{MOTION_CLIPS_15}}
      <div class="shot-card__body">
        <p class="kicker">Motion card / 鏡 15</p>
        <h3>刀落 → 斷開 → 散下</h3>
        <p>0.4x 慢動作，全片三處之一。斷口必須整齊、不閃爍、不變色；散開的髮絲要有 0.15 秒慣性落後，不能瞬間攤開。</p>
        <p class="motion-prompt" id="motion-prompt-15">{{MOTION_PROMPT_15}}</p>
        <button class="copy-btn" type="button" data-copy-target="motion-prompt-15">複製 i2v 提示詞</button>
        <dl class="meta-list">
          <dt>動態層</dt><dd>L-A 主體動作 · 強度 4</dd>
          <dt>剪點</dt><dd>斷開瞬間</dd>
          <dt>幀率</dt><dd>24fps（原生）→ 0.4x 後期變速</dd>
          <dt>風險</dt><dd>斷口閃爍、髮絲變色</dd>
        </dl>
      </div>
    </article>

    <article class="shot-card reveal">
      <img src="thumbs/shots-916/shot_23.jpg" alt="鏡 23 格擋，9:16 首幀" width="400" height="640" loading="lazy">
      {{MOTION_CLIPS_23}}
      <div class="shot-card__body">
        <p class="kicker">Motion card / 鏡 23</p>
        <h3>劈下 → 擋下 → 火星爆</h3>
        <p>全片最難的一顆。手持晃 4°，撞擊瞬間是峰值；槍與刀的角度要對上，否則觀眾會讀不出「擋」。三次不成就拆成兩鏡。</p>
        <p class="motion-prompt" id="motion-prompt-23">{{MOTION_PROMPT_23}}</p>
        <button class="copy-btn" type="button" data-copy-target="motion-prompt-23">複製 i2v 提示詞</button>
        <dl class="meta-list">
          <dt>動態層</dt><dd>L-A 主體動作 · 強度 5</dd>
          <dt>剪點</dt><dd>武器接觸點</dd>
          <dt>幀率</dt><dd>24fps（原生）· 手持 4°</dd>
          <dt>風險</dt><dd>槍刀比例、格擋角度</dd>
        </dl>
      </div>
    </article>

    <article class="shot-card reveal">
      <img src="thumbs/shots-916/shot_27.jpg" alt="鏡 27 雪原跪旗，9:16 首幀" width="400" height="640" loading="lazy">
      {{MOTION_CLIPS_27}}
      <div class="shot-card__body">
        <p class="kicker">Motion card / 鏡 27</p>
        <h3>不動，讓鏡頭升</h3>
        <p>2.5 秒全片最安靜。身體只有肩膀起伏，動的是升降臂（20cm/s）與雪。AI 常把人畫成會動，所以提示詞要明寫 body still。</p>
        <p class="motion-prompt" id="motion-prompt-27">{{MOTION_PROMPT_27}}</p>
        <button class="copy-btn" type="button" data-copy-target="motion-prompt-27">複製 i2v 提示詞</button>
        <dl class="meta-list">
          <dt>動態層</dt><dd>L-B 攝影機 · 強度 2</dd>
          <dt>剪點</dt><dd>2.5 秒不剪</dd>
          <dt>幀率</dt><dd>24fps（原生）· 升 20cm/s</dd>
          <dt>風險</dt><dd>人物亂動、雪停不下</dd>
        </dl>
      </div>
    </article>

    <article class="shot-card reveal">
      <img src="thumbs/shots-169/shot_42_16x9.jpg" alt="鏡 42 開門，16:9 首幀" width="640" height="360" loading="lazy">
      {{MOTION_CLIPS_42}}
      <div class="shot-card__body">
        <p class="kicker">Motion card / 鏡 42</p>
        <h3>門縫 → 光溢 → 拉遠</h3>
        <p>全片唯一一個不剪的鏡頭。開門用 ease-out，後段拉遠要慢到幾乎不動（15cm/s）；rack focus 與碗碎同一格。開門光過曝 1 格。</p>
        <p class="motion-prompt" id="motion-prompt-42">{{MOTION_PROMPT_42}}</p>
        <button class="copy-btn" type="button" data-copy-target="motion-prompt-42">複製 i2v 提示詞</button>
        <dl class="meta-list">
          <dt>動態層</dt><dd>L-B 拉遠 + L-C 光 · 3→2</dd>
          <dt>剪點</dt><dd>全程不剪</dd>
          <dt>幀率</dt><dd>24fps（原生）· 拉 15cm/s</dd>
          <dt>風險</dt><dd>拉遠速度、對焦時機</dd>
        </dl>
      </div>
    </article>

    <h3 style="font-family:var(--font-display);font-weight:500;font-size:28px;margin:48px 0 16px">i2v 生成規格（{{H3_MODEL}}）</h3>
    <div class="do-not reveal">
      <div><b>Spec 01</b>素材長度＝鏡長 × 2（向上取整，最低 5 秒）；慢動作鏡頭 × 1.5。{{H3_MODEL}} 單段 5–15 秒整秒，超過就分兩段接。</div>
      <div><b>Spec 02</b>單一動作原則：每段只描述一個主動作 + 一個次動作，其餘不要寫，模型才不會自己加戲。</div>
      <div><b>Spec 03</b>Prompt 結構：主體＋單一動作＋攝影機＋物理＋幀率＋光線＋negative＋<b>原生音軌</b>，全英文，不加形容詞堆砌。</div>
      <div><b>Spec 04</b>音軌分工：{{H3_MODEL}} 同一趟生成「環境聲 + 音效」；音樂與人聲一律後期加，所以每條提示詞都結尾 no music, no dialogue, no singing。</div>
      <div><b>Spec 05</b>先難後易：先做 23、24、25、12、15、42、43、40，再做中風險，最後做固定機位（八成一次就成）。</div>
      <div><b>Spec 06</b>重生順序不可跳：換 seed → 改動詞 → 改負面詞 → 改音軌詞 → 換首幀。一顆最多重生 3 次，之後改用實拍或拆鏡。</div>
      <div><b>Spec 07</b>首尾幀對齊：A 的尾幀當 B 的首幀；切點前後各留 2 幀重疊，6 幀交叉溶解。慢動作＝提示詞 slow motion + 後期變速，{{H3_MODEL}} 原生只有 24fps。</div>
    </div>

    <div class="callout reveal" style="margin-top:34px">
      <h3 style="font-family:var(--font-display);font-weight:500;font-size:24px;margin:0 0 12px">對嘴只有一顆鏡頭</h3>
      <p>鏡 31 是全片唯一需要精準口型的地方（V6「木蘭不用尚書郎」）。普通話 5.0 字／秒 → 每字約 4.8 幀；粵語 5.9 字／秒 → 每字約 4.1 幀，粵語版要另外生成一次。其餘人聲都是旁白或畫外，嘴只要有呼吸與眼神。順序是：先錄音 → 依時間碼對嘴 → 剪輯 → 混音，不要先生成動態再去遷就錄音。</p>
    </div>

    <h3 style="font-family:var(--font-display);font-weight:500;font-size:28px;margin:48px 0 16px" id="clips">16:9 動態片段：同一提示詞、兩個 seed</h3>
    <p class="section-note reveal">45 鏡各跑兩次：<strong>提示詞一字不改，只換 seed</strong>。片段 A 與 B 都是 {{H3_MODEL}} 原生輸出（1280×736、24fps、AAC 立體聲），差異全部來自抽卡結果——這就是為什麼 i2v 一定要預留重生次數。</p>
    {{CLIP_TABLE}}
    <p class="section-note reveal">片段檔案在 <code>assets/video/shots_169/</code>（<code>shot_NN_16x9.mp4</code> 與 <code>shot_NN_16x9_v2.mp4</code>），生成紀錄（seed、prompt_id、時長、尺寸）寫在 <code>assets/video/manifest_i2v.jsonl</code>。</p>

    <p class="section-note reveal">完整規格：<a href="../design/02-分鏡表-靜態與動態.md">design/02-分鏡表-靜態與動態.md</a>（45 鏡動態表、12 處動作接動作、45 組英文 i2v 提示詞、物理與材質規則、QA 清單）。對應的生成提示詞在 <a href="#prompt-02">提示詞庫 #02</a>。</p>
  </section>

{{ROUGH_CUT}}

  <section class="chapter" id="ratio">
    <div class="chapter-head reveal">
      <p class="kicker">07 / Aspect ratio</p>
      <h2>16:9 不是<br class="br-d">把兩邊裁掉</h2>
      <p class="lead">直式與橫式是兩種觀看距離。9:16 讓觀眾貼近臉；16:9 讓觀眾看見人物與空間的關係。構圖要重新寫，不是把同一張圖切一刀。</p>
    </div>

    <div class="ratio-pair reveal">
      <figure class="ratio-figure">
        <img src="../assets/generated/shots/shot_42.jpg" alt="S42 開門，9:16 直式構圖" width="720" height="1280" loading="lazy">
        <figcaption><span>9:16 / 720 × 1280</span><span>直式：臉與門的壓迫</span></figcaption>
      </figure>
      <figure class="ratio-figure">
        <img src="../assets/generated/shots_16x9/shot_42_16x9.jpg" alt="S42 開門，16:9 橫式構圖" width="1280" height="720" loading="lazy">
        <figcaption><span>16:9 / 1280 × 720</span><span>橫式：人物與院落的關係</span></figcaption>
      </figure>
    </div>

    <div class="ratio-stats reveal">
      <div><strong>45</strong><span>16:9 鏡頭</span></div>
      <div><strong>90</strong><span>16:9 動態片段（雙 seed）</span></div>
      <div><strong>10</strong><span>16:9 場景</span></div>
      <div><strong>55</strong><span>16:9 總圖數</span></div>
    </div>

    <p class="section-note reveal">做法：複製 jobs，將 <code>vertical 9:16 composition</code> 改為 <code>horizontal 16:9 composition</code>，寬高改為 1280×720，重新採樣。角色設定圖與道具不重生成，因為它們是參考資產，不是鏡頭。字幕安全框、人物視線與前景遮擋都要獨立檢查。動態也照同一套：16:9 已有 45 鏡 × 2 個 seed = 90 支片段，見 <a href="#clips">06 動態</a>。</p>
    <span class="stamp reveal">Not a crop / independent generation</span>
  </section>

  <section class="chapter" id="sound">
    <div class="chapter-head reveal">
      <p class="kicker">08 / Voice & language</p>
      <h2>粵語不是<br class="br-d">普通話配音</h2>
      <p class="lead">9:16 普通話版與 16:9 粵語版不是同一條聲軌換語言。粵語的節奏、語氣、甚至 V7 的語意都不一樣；對嘴與剪輯必須分開做。</p>
    </div>

    <div class="version-grid reveal">
      <article class="version-card">
        <p class="kicker">Version A / 9:16</p>
        <h3>普通話</h3>
        <p>貼近臉的直式版本。VO 用低聲、近距離、幾乎貼著麥克風的語氣；戰場段落不喊，反而更冷。</p>
        <ul>
          <li><span>畫幅</span><b>720 × 1280</b></li>
          <li><span>人聲</span><b>8 段 / 117 字</b></li>
          <li><span>字幕</span><b>標準書面中文</b></li>
          <li><span>混音</span><b>-14 LUFS</b></li>
        </ul>
      </article>
      <article class="version-card version-card--dark">
        <p class="kicker">Version B / 16:9</p>
        <h3>粵語</h3>
        <p>看見空間的橫式版本。V1–V5、V8 用粵讀文言保留原句；V6、V7 用粵語口語，讓金鑾殿與開門的衝突更像人說話。</p>
        <ul>
          <li><span>畫幅</span><b>1280 × 720</b></li>
          <li><span>人聲</span><b>8 段 / 約 23.4 秒</b></li>
          <li><span>字幕</span><b>標準中文 / 可選 yue-Hant</b></li>
          <li><span>混音</span><b>-14 LUFS</b></li>
        </ul>
      </article>
    </div>

    <table class="line-table reveal">
      <thead>
        <tr><th>Line</th><th>9:16 普通話</th><th>16:9 粵語</th></tr>
      </thead>
      <tbody>
        <tr><td>V1</td><td>唧唧復唧唧，木蘭當戶織。</td><td>唧唧復唧唧，木蘭當戶織。</td></tr>
        <tr><td>V6</td><td>木蘭不用尚書郎，願借明駝千里足，送兒還故鄉。</td><td>木蘭唔做尚書郎！願借明駝千里足，送兒還故鄉！</td></tr>
        <tr><td>V7</td><td>同行十二年，不知木蘭是女郎。</td><td>同……同行十二年，你、你竟然係個女仔？！</td></tr>
        <tr><td>V8</td><td>雄兔腳撲朔，雌兔眼迷離；雙兔傍地走，安能辨我是雄雌？</td><td>雄兔腳撲朔，雌兔眼迷離；雙兔傍地走，安能辨我是雄雌？</td></tr>
      </tbody>
    </table>

    <div class="callout reveal">
      <p>V6 粵語比普通話多約 0.2 秒，用 00:42.4–00:43.0 的 0.6 秒緩衝吸收，不改剪。</p>
      <small>Timing note / 03-臺詞與雙語版本</small>
    </div>

    <div class="two-col reveal" style="margin-top:36px">
      <div>
        <h3 style="font-family:var(--font-display);font-weight:500;font-size:26px;margin:0 0 12px">錄音距離</h3>
        <p class="section-note" style="margin-bottom:0">VO 5–10cm，近距離、低音量；台詞 30cm，保留胸腔；畫外音 3–10m，加空間殘響。同一個語言內，木蘭與 VO 由同一人聲扮演，避免「旁白是另一個人」的斷裂。</p>
      </div>
      <div>
        <h3 style="font-family:var(--font-display);font-weight:500;font-size:26px;margin:0 0 12px">試鏡順序</h3>
        <p class="section-note" style="margin-bottom:0">先試 V6（辭官）與 V7（被認出），因為這兩段同時考驗台詞、情緒與粵語語感。V1 與 V8 最後試，用來確認同一個聲音能否從頭到尾成立。</p>
      </div>
    </div>
  </section>

  <section class="chapter" id="post">
    <div class="chapter-head reveal">
      <p class="kicker">09 / Post-production</p>
      <h2>先剪粗剪，<br class="br-d">再花錢定案</h2>
      <p class="lead">16:9 粵語粗剪已完成（見 <a href="#roughcut">06B</a>）：45 鏡按時間碼組接、對白與環境聲已混。這一版用來驗節奏與對點；定剪前還要挑 seed、變速、對嘴、配樂與真人錄音。</p>
    </div>

    <div class="post-grid">
      <div class="reveal">
        <h3 style="font-family:var(--font-display);font-weight:500;font-size:28px;margin:0 0 16px">後期 SOP</h3>
        <ul class="checklist">
          <li><b>i2v 全 45 鏡</b><span>完成（16:9 ×2 seed）</span></li>
          <li><b>粗剪</b><span>完成（16:9 粵語）</span></li>
          <li><b>逐鏡挑 seed</b><span>待辦（--overrides）</span></li>
          <li><b>慢動作變速</b><span>待辦（鏡 15/25/43）</span></li>
          <li><b>對嘴</b><span>待辦（鏡 31 粵語）</span></li>
          <li><b>真人錄音</b><span>未錄（目前 MiniMax DX）</span></li>
          <li><b>音樂與音效</b><span>未開始</span></li>
          <li><b>調色與交付</b><span>未開始</span></li>
        </ul>
      </div>
      <div class="risk-grid reveal">
        <div class="risk"><b>Risk 01</b><p>i2v 最容易壞的是手、臉與武器邊緣。先測 S1 開場、S9 開門、V6 金鑾殿、V7 老雷。</p></div>
        <div class="risk"><b>Risk 02</b><p>粵語 V6/V7 與普通話嘴型不同，不能共用對嘴資料。兩版要各自做。</p></div>
        <div class="risk"><b>Risk 03</b><p>木蘭 A/B/C 三張臉仍有年齡差。剪輯時用景別、光線與遮擋控制，不要硬切特寫。</p></div>
        <div class="risk"><b>Risk 04</b><p>16:9 的人物位置與字幕安全框要獨立檢查；直接沿用 9:16 的構圖會出現空洞前景。</p></div>
      </div>
    </div>

    <table class="deliverables reveal">
      <thead>
        <tr><th>交付</th><th>規格</th><th>備註</th></tr>
      </thead>
      <tbody>
        <tr><td>Master 9:16</td><td>1080×1920 / 24fps / H.264</td><td>普通話；字幕燒錄版與乾淨版各一。</td></tr>
        <tr><td>Master 16:9</td><td>1920×1080 / 24fps / H.264</td><td>粵語；字幕燒錄版與乾淨版各一。</td></tr>
        <tr><td>Subtitles</td><td>SRT / ASS</td><td>標準中文；16:9 另附 yue-Hant 選用軌。</td></tr>
        <tr><td>Audio stems</td><td>48kHz / 24-bit WAV</td><td>VO、音樂、Foley、環境、混音母帶。</td></tr>
        <tr><td>Stills</td><td>JPG q90</td><td>133 張正式資產、contact sheets、圖庫。</td></tr>
        <tr><td>Clips 16:9</td><td>MP4 / H.264 + AAC</td><td>90 支 i2v 片段（45 鏡 × 2 個 seed），1280×736 / 24fps / 原生立體聲。</td></tr>
        <tr><td>Rough cut 16:9</td><td>MP4 / H.264 + AAC + mov_text</td><td>粵語粗剪 60.000s / 1440 幀 / 1280×720；見 <a href="#roughcut">06B</a>。</td></tr>
        <tr><td>Manual cut 16:9</td><td>MP4 / H.264 + AAC</td><td>手剪版雙語言：粵語＋普通話，各 115.417s / 2770 幀 / 1920×1080；見 <a href="#roughcut">06B</a>。</td></tr>
        <tr><td>Docs</td><td>Markdown</td><td>設計文件、試鏡表、雙語版本、這份教學。</td></tr>
      </tbody>
    </table>
  </section>

  <section class="gallery" id="gallery">
    <div class="gallery-inner">
      <div class="chapter-head reveal">
        <p class="kicker">10 / Archive</p>
        <h2>133 張圖，<br class="br-d">全部可追溯</h2>
        <p class="lead">角色參考、設定圖、道具、場景與鏡頭首幀。點圖放大；<kbd>Esc</kbd> 關閉，方向鍵切換。所有圖片由同一組 jobs 與 manifest 產出。</p>
      </div>

      <div class="filters reveal" role="group" aria-label="圖庫篩選">
        <button class="filter is-active" type="button" data-filter="all" aria-pressed="true">全部 133</button>
        <button class="filter" type="button" data-filter="refs" aria-pressed="false">參考 7</button>
        <button class="filter" type="button" data-filter="characters" aria-pressed="false">角色 10</button>
        <button class="filter" type="button" data-filter="props" aria-pressed="false">道具 6</button>
        <button class="filter" type="button" data-filter="scenes-916" aria-pressed="false">場景 9:16 · 10</button>
        <button class="filter" type="button" data-filter="scenes-169" aria-pressed="false">場景 16:9 · 10</button>
        <button class="filter" type="button" data-filter="shots-916" aria-pressed="false">鏡頭 9:16 · 45</button>
        <button class="filter" type="button" data-filter="shots-169" aria-pressed="false">鏡頭 16:9 · 45</button>
        <span class="gallery-count" data-gallery-count>全部 · 133 / 133</span>
      </div>

      <div class="gallery-grid">
{{GALLERY}}
      </div>
    </div>
  </section>

  <section class="chapter" id="reproduce">
    <div class="chapter-head reveal">
      <p class="kicker">11 / Reproduce</p>
      <h2>把這條流程<br class="br-d">重跑一次</h2>
      <p class="lead">你不需要同樣的 GPU，但需要同樣的順序：先寫文件，再編譯任務，再生成，再檢查。以下指令以本專案根目錄為工作目錄。</p>
    </div>

    <div class="two-col">
      <div class="reveal">
        <pre class="file-tree"><b>design/</b>             00–12 設計文件
<b>scripts/</b>            build_jobs.py
                     comfy_batch.py
                     h3_i2v.py
                     assemble_cut.py
                     to_jpg.py
                     jobs.json / jobs_16x9.json
                     overrides.json
<b>assets/generated/</b>   characters/  props/
                     scenes/  scenes_16x9/
                     shots/  shots_16x9/
                     manifest*.jsonl
<b>assets/video/</b>       shots_169/  (90 clips)
                     cuts/       (rough cut)
<b>site/</b>               index.html
                     styles.css  app.js</pre>
        <pre class="code-block" data-label="Local preview"><code>python3 scripts/build_site.py
python3 -m http.server 8000
open http://localhost:8000/site/</code></pre>
      </div>
      <div class="reveal">
        <h3 style="font-family:var(--font-display);font-weight:500;font-size:28px;margin:0 0 16px">下載與延伸閱讀</h3>
        <div class="downloads">
          <a href="../design/README.md"><span>Design index</span>設計文件索引</a>
          <a href="../design/01-視覺設定-人物場景道具.md"><span>Look</span>視覺設定</a>
          <a href="../design/02-分鏡表-靜態與動態.md"><span>45 shots</span>分鏡表＋動態</a>
          <a href="../design/03-臺詞與雙語版本.md"><span>Script</span>臺詞與雙語版本</a>
          <a href="../design/04-AI生成提示詞包.md"><span>Prompts</span>AI 生成提示詞包</a>
          <a href="../design/05-音樂與音效設計.md"><span>Music</span>音樂與音效</a>
          <a href="../design/06-聲音設計-音色選角與試鏡.md"><span>Voice</span>聲音設計與試鏡</a>
          <a href="../design/07-配音執行包-真人錄音與AI備援.md"><span>Package</span>配音執行包</a>
          <a href="prompts.md"><span>Prompts</span>8 份文件生成提示詞</a>
          <a href="../assets/video/cuts/雌雄_粗剪_16x9_粵語_v1.mp4"><span>Rough cut</span>60 秒粵語粗剪 MP4</a>
          <a href="../assets/video/cuts/雌雄_手剪_16x9_粵語_v1.mp4"><span>Manual cut</span>手剪版 16:9 粵語 MP4</a>
          <a href="../assets/video/cuts/雌雄_手剪_16x9_普通話_v1.mp4"><span>Manual cut</span>手剪版 16:9 普通話 MP4</a>
          <a href="../assets/generated/index.html"><span>All assets</span>完整資產索引</a>
          <a href="../assets/generated/README.md"><span>Report</span>生成報告與已知問題</a>
        </div>
        <button class="btn btn--ghost" type="button" data-print style="margin-top:18px">列印 SOP</button>
      </div>
    </div>

    <div class="do-not reveal" style="margin-top:44px">
      <div><b>Don't 01</b>不要把 9:16 直接裁成 16:9。人物會失去空間，字幕會撞到臉。</div>
      <div><b>Don't 02</b>不要重跑 build_jobs.py 覆蓋掉 overrides 後的成果；先確認 overrides.json 已載入。</div>
      <div><b>Don't 03</b>不要用普通話 TTS 硬配粵語版。聲調與嘴型都不會對。</div>
      <div><b>Don't 04</b>不要在粗剪節奏未成立前逐鏡抽卡定案 seed。先用 60 秒粗剪驗對點，再用 --overrides 換鏡。</div>
    </div>
  </section>
</main>

<footer class="footer">
  <div class="footer-inner">
    <div>
      <h2>動起來了，也剪起來了。下一步是把它剪對。</h2>
      <p>16:9 動態兩輪跑完（45 鏡 × 2 seed = 90 支），並已依 <code>design/02</code> 時間碼組接成 60.000 秒粵語粗剪（見「06B 粗剪」）：對白、環境聲與軟字幕都在。定剪前待辦：逐鏡挑 seed、慢動作變速、鏡 31 對嘴、音樂、真人錄音與 9:16 普通話版。這份文件會跟著製作更新。</p>
      <div class="footer-meta">
        <span>雌雄 / Production dossier</span>
        <span>Updated 2026-10-23</span>
        <span>133 stills + 90 clips + 1 rough cut</span>
      </div>
    </div>
    <div>
      <p>所有圖像以 ComfyUI + Qwen Image 2.1 生成。設計文件、提示詞與生成紀錄保存在專案內，網頁不依賴外部 CDN，可離線瀏覽。</p>
      <p style="margin-top:16px"><a href="#top">回到頂部 ↑</a></p>
    </div>
  </div>
</footer>

<div class="lightbox" id="lightbox" role="dialog" aria-modal="true" aria-labelledby="lightbox-title" aria-hidden="true" hidden>
  <button class="lightbox__close" type="button" data-lightbox-close aria-label="關閉圖庫">關閉 ✕</button>
  <div class="lightbox__stage">
    <img id="lightbox-img" src="" alt="">
  </div>
  <div class="lightbox__bar">
    <div class="lightbox__meta">
      <b id="lightbox-title"></b>
      <span id="lightbox-meta"></span>
      <span data-lightbox-position></span>
    </div>
    <div class="lightbox__controls">
      <a id="lightbox-link" class="btn btn--ghost" href="#" target="_blank" rel="noopener" style="min-height:38px;padding:0 12px">原圖 ↗</a>
      <button type="button" data-lightbox-prev aria-label="上一張">←</button>
      <button type="button" data-lightbox-next aria-label="下一張">→</button>
    </div>
  </div>
</div>

<div class="copy-toast" role="status" aria-live="polite"></div>

<script src="app.js"></script>
</body>
</html>
"""
    html = page
    for key, value in motion_blocks.items():
        html = html.replace(key, value)
    return (
        html.replace("{{H3_MODEL}}", H3_MODEL)
        .replace("{{GALLERY}}", cards)
        .replace("{{PROMPT_LIBRARY}}", prompt_library)
        .replace("{{SHOT_LIST}}", shot_list)
        .replace("{{VISUAL_CHARACTERS}}", motion_blocks.get("{{VISUAL_CHARACTERS}}", ""))
        .replace("{{VISUAL_SCENES}}", motion_blocks.get("{{VISUAL_SCENES}}", ""))
        .replace("{{VISUAL_PROPS}}", motion_blocks.get("{{VISUAL_PROPS}}", ""))
    )


def main():
    SITE.mkdir(exist_ok=True)
    cards, counts = build_gallery()
    html = make_page(cards, counts)
    target = SITE / "index.html"
    target.write_text(html, encoding="utf-8")
    prompts_target = SITE / "prompts.md"
    prompts_target.write_text(build_prompts_markdown(), encoding="utf-8")
    thumb_count = sum(1 for _ in THUMBS.rglob("*.jpg"))
    print(f"wrote {target}")
    print(f"wrote {prompts_target} ({len(PROMPTS)} prompts)")
    print(f"gallery cards: {counts['all']} (thumbs: {thumb_count})")
    for key in ("refs", "characters", "props", "scenes-916", "scenes-169", "shots-916", "shots-169"):
        print(f"  {key}: {counts[key]}")


if __name__ == "__main__":
    main()
