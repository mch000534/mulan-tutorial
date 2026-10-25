#!/usr/bin/env python3
"""把 design/ 的 13 份內容文件合併成 8 份。

⚠️ 一次性工具：原始檔已於 2026-10-21 合併，來源檔已不存在。
   重跑前必須先從 `assets/design_backup/13docs_before_merge/` 還原。
   合併後請人工檢查重疊段落，再跑 scripts/rewrite_refs.py 更新全域交叉引用。

用法：python3 scripts/merge_design_docs.py
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "design"
BAK = DESIGN.parent / "assets" / "audio" / ".design_backup"

CN = "一二三四五六七八九十"


def cn(n: int) -> str:
    if n <= 10:
        return CN[n - 1]
    if n < 20:
        return "十" + CN[n - 11]
    return CN[n // 10 - 1] + "十" + (CN[n % 10 - 1] if n % 10 else "")


def parse(path: Path) -> tuple[str, list[str], list[tuple[str, list[str]]]]:
    """回傳 (標題, 前言區塊行, [(章節標題, 內文行)])"""
    lines = path.read_text(encoding="utf-8").splitlines()
    title = lines[0].lstrip("# ").strip()
    front: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    cur: list[str] | None = None
    body: list[str] = []
    seen_first_h2 = False
    for line in lines[1:]:
        if line.startswith("## "):
            if cur is not None:
                sections.append((cur, body))
            cur = line[3:].strip()
            body = []
            seen_first_h2 = True
        elif line.startswith("### "):
            body.append(line)
        elif seen_first_h2 and cur is not None:
            body.append(line)
        else:
            front.append(line)
    if cur is not None:
        sections.append((cur, body))
    return title, front, sections


def strip_trailing_sections(sections, drop_prefixes=("與其他文件的關係",)):
    keep = []
    for title, body in sections:
        if any(title.startswith(p) for p in drop_prefixes):
            continue
        keep.append((title, body))
    return keep


def renumber(title: str, idx: int) -> str:
    """把「一、xxx」改成「N、xxx」"""
    body = re.sub(r"^[一二三四五六七八九十]+、\s*", "", title)
    return f"{cn(idx)}、{body}"


def demote(lines: list[str], levels: int = 1) -> list[str]:
    out = []
    for ln in lines:
        if ln.startswith("###"):
            out.append("#" * (3 + levels) + ln[3:])
        elif ln.startswith("####"):
            out.append("#" * (4 + levels) + ln[4:])
        else:
            out.append(ln)
    return out


def write_doc(dest: Path, title: str, front: list[str], sections: list[tuple[str, list[str]]],
              tail: list[str]) -> None:
    parts = [f"# {title}", ""]
    parts += front
    parts.append("")
    for t, body in sections:
        parts.append(f"## {t}")
        parts.append("")
        parts += body
        parts.append("")
    if tail:
        parts += tail
    text = "\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    dest.write_text(text, encoding="utf-8")
    print(f"  → {dest.name}（{len(text.splitlines())} 行）")


def main() -> None:
    BAK.mkdir(parents=True, exist_ok=True)
    for p in sorted(DESIGN.glob("*.md")):
        if p.name == "README.md":
            continue
        shutil.copy2(p, BAK / p.name)
    print(f"已備份 {len(list(BAK.glob('*.md')))} 份到 {BAK}")

    # ---------- 00 視覺聖經：內容不動，只換檔名與內部引用 ----------
    # 00 視覺聖經：內容不動

    # ---------- 01 視覺設定：人物 + 場景 + 道具 ----------
    _, _, s01 = parse(DESIGN / "01-視覺設定-人物場景道具.md")
    _, _, s02 = parse(DESIGN / "01-視覺設定-人物場景道具.md")
    _, _, s03 = parse(DESIGN / "01-視覺設定-人物場景道具.md")
    s01 = strip_trailing_sections(s01)
    s02 = strip_trailing_sections(s02)
    s03 = strip_trailing_sections(s03)

    def nest(sections):
        out = []
        for t, b in sections:
            body = []
            for ln in b:
                if ln.startswith("###"):
                    body.append("####" + ln[3:])
                elif ln.startswith("####"):
                    body.append("#####" + ln[4:])
                else:
                    body.append(ln)
            out.append((re.sub(r"^[一二三四五六七八九十]+、\s*", "", t), body))
        return out

    sections = []
    idx = 1
    for group, name in [(s01, "人物設定"), (s02, "場景設定"), (s03, "道具設定")]:
        sections.append((f"{cn(idx)}、{name}", []))
        idx += 1
        for t, b in nest(group):
            sections.append((t, b))
    # 把巢狀的子章節併進父章節
    flat = []
    for t, b in sections:
        if not b:
            flat.append((t, b))
        else:
            flat.append((f"{t}｜{''}", b))  # placeholder replaced below
    merged = []
    i = 0
    while i < len(sections):
        t, b = sections[i]
        if b:
            merged.append((t, b))
            i += 1
            continue
        body = []
        j = i + 1
        while j < len(sections) and sections[j][1]:
            body.append("### " + sections[j][0])
            body.append("")
            body += sections[j][1]
            body.append("")
            j += 1
        merged.append((t, body))
        i = j

    write_doc(
        DESIGN / "01-視覺設定-人物場景道具.md",
        "《雌雄》視覺設定：人物・場景・道具",
        [
            "版本：V1.0（與 `00-視覺聖經.md`、`02-分鏡表-靜態與動態.md` 同步）",
            "用途：美術搭建、堪景、分鏡、生成、場記與連續性管理",
            "",
            "> 本文件合併了原本分散的三份設定：**人物**、**場景**、**道具**。",
            "> 視覺的總則（色彩、光影、符號、一致性清單）見 `00-視覺聖經.md`。",
            "",
        ],
        merged,
        ["## 四、與其他文件的關係", "",
         "| 文件 | 負責範圍 |", "|---|---|",
         "| `00-視覺聖經.md` | 視覺命題、色彩腳本、光影、符號回收、一致性清單 |",
         "| `02-分鏡表-靜態與動態.md` | 鏡頭、時間碼、動作、剪輯點、動態規格 |",
         "| `04-AI生成提示詞包.md` | 角色三視圖、場景圖、道具圖、45 張首幀的生成詞 |",
         "| `05-音樂與音效設計.md` | 場景空間感對應的環境音與 Foley |", ""],
    )

    # ---------- 02 分鏡表：靜態 + 動態 ----------
    _, _, s04 = parse(DESIGN / "02-分鏡表-靜態與動態.md")
    _, _, s12 = parse(DESIGN / "02-分鏡表-靜態與動態.md")
    s04 = strip_trailing_sections(s04)
    s12 = strip_trailing_sections(s12)
    # 04 的聲音設計章節往後移（因為動態章節插在中間），此處維持原順序即可
    merged = []
    idx = 1
    for t, b in s04:
        merged.append((renumber(t, idx), b))
        idx += 1
    for t, b in s12:
        merged.append((renumber(t, idx), b))
        idx += 1

    write_doc(
        DESIGN / "02-分鏡表-靜態與動態.md",
        "《雌雄》分鏡表：靜態時間碼與動態設計",
        [
            "版本：V2.1（靜態時間碼沿用 V1.1 放寬版；動態設計為新增第二層；新增「已生成的 16:9 片段」紀錄）",
            "片長：60.0 秒（片尾黑場 0.5 秒，總長 60.5 秒）／45 顆鏡頭",
            "格式：9:16 直式 1080×1920，24fps（慢動作段 120fps／60fps）",
            "",
            "> 本文件有兩層：**第三節**是靜態分鏡（看見什麼、時間碼、剪輯點），",
            "> **第四節起**是動態設計（它怎麼動）——動態必須在買 i2v 之前完成。",
            "",
        ],
        merged,
        ["## 二十二、與其他文件的關係", "",
         "| 文件 | 負責範圍 |", "|---|---|",
         "| `00-視覺聖經.md` | 視覺命題、色彩、光影、鏡頭語言、一致性清單 |",
         "| `01-視覺設定-人物場景道具.md` | 人物、場景、道具的設定與生成詞 |",
         "| `03-臺詞與雙語版本.md` | 台詞文字、斷句、語速、字幕、粵語版本 |",
         "| `05-音樂與音效設計.md` | 音樂、Foley、環境音、混音 |",
         "| `06-聲音設計-音色選角與試鏡.md` | 角色音色、選角、試鏡、對白後期鏈 |",
         "| `07-配音執行包-真人錄音與AI備援.md` | 錄音 cue 卡、交件規格、回收驗收 |", ""],
    )

    # ---------- 03 臺詞與雙語版本 ----------
    _, _, s05 = parse(DESIGN / "03-臺詞與雙語版本.md")
    _, _, s10 = parse(DESIGN / "03-臺詞與雙語版本.md")
    s05 = strip_trailing_sections(s05)
    s10 = strip_trailing_sections(s10)
    merged = []
    idx = 1
    for t, b in s05:
        merged.append((renumber(t, idx), b))
        idx += 1
    for t, b in s10:
        merged.append((renumber(t, idx), b))
        idx += 1

    write_doc(
        DESIGN / "03-臺詞與雙語版本.md",
        "《雌雄》臺詞與雙語版本",
        [
            "版本：V2.0（普通話 9:16 ＋ 粵語 16:9；時間碼與 `02-分鏡表-靜態與動態.md` V1.1 同步）",
            "用途：配音、字幕、混音對點、版本管理",
            "",
            "> 前七節是**普通話 9:16 版**的台詞定稿；第八節起是**粵語 16:9 版**的版本設計。",
            "> 錄音執行（cue 卡、交件規格、回收驗收）見 `07-配音執行包-真人錄音與AI備援.md`。",
            "",
        ],
        merged,
        ["## 十八、與其他文件的關係", "",
         "| 文件 | 負責範圍 |", "|---|---|",
         "| `02-分鏡表-靜態與動態.md` | 鏡頭、時間碼、剪輯點、動態規格 |",
         "| `05-音樂與音效設計.md` | 音樂、Foley、環境音、混音與交付 |",
         "| `06-聲音設計-音色選角與試鏡.md` | 聲線、選角、錄音規格、對白處理鏈 |",
         "| `07-配音執行包-真人錄音與AI備援.md` | 錄音 cue 卡、交件規格、回收與驗收 |", ""],
    )

    # ---------- 04 AI 生成提示詞包：內容不動 ----------
    shutil.copy2(DESIGN / "04-AI生成提示詞包.md", DESIGN / "04-AI生成提示詞包.md")

    # ---------- 05 音樂與音效設計：內容不動 ----------
    shutil.copy2(DESIGN / "05-音樂與音效設計.md", DESIGN / "05-音樂與音效設計.md")

    # ---------- 06 聲音設計：音色 + 選角 + 試鏡 ----------
    _, _, s08 = parse(DESIGN / "06-聲音設計-音色選角與試鏡.md")
    _, _, s09 = parse(DESIGN / "06-聲音設計-音色選角與試鏡.md")
    s08 = strip_trailing_sections(s08)
    s09 = strip_trailing_sections(s09)
    merged = []
    idx = 1
    for t, b in s08:
        merged.append((renumber(t, idx), b))
        idx += 1
    for t, b in s09:
        merged.append((renumber(t, idx), b))
        idx += 1

    write_doc(
        DESIGN / "06-聲音設計-音色選角與試鏡.md",
        "《雌雄》聲音設計：音色・選角・試鏡",
        [
            "版本：V2.0（與 `03-臺詞與雙語版本.md`、`07-配音執行包-真人錄音與AI備援.md` 同步）",
            "用途：選角、試鏡、配音、對白後期處理鏈",
            "",
            "> 前九節是**角色音色設計**（聲線、語氣、錄音距離、後期鏈）；",
            "> 第十節起是**試鏡流程**（每角色三句、評分表、淘汰線）。",
            "",
        ],
        merged,
        ["## 十七、與其他文件的關係", "",
         "| 文件 | 負責範圍 |", "|---|---|",
         "| `03-臺詞與雙語版本.md` | 台詞文字、斷句、重音、語速、字幕、粵語版本 |",
         "| `05-音樂與音效設計.md` | 音樂、Foley、環境音、混音與交付 |",
         "| `07-配音執行包-真人錄音與AI備援.md` | 錄音 cue 卡、交件規格、回收與驗收 |", ""],
    )

    # ---------- 07 配音執行包：真人 + AI ----------
    _, _, s11 = parse(DESIGN / "07-配音執行包-真人錄音與AI備援.md")
    _, _, s12ai = parse(DESIGN / "07-配音執行包-真人錄音與AI備援.md")
    s11 = strip_trailing_sections(s11)
    s12ai = strip_trailing_sections(s12ai)

    merged = []
    idx = 1
    for t, b in s11:
        merged.append((renumber(t, idx), b))
        idx += 1
    # AI 備援方案整組作為第十一節的子章節
    merged.append((f"{cn(idx)}、AI 備援方案：MiniMax Voice Design", []))
    ai_children = []
    for t, b in s12ai:
        title = re.sub(r"^[一二三四五六七八九十]+、\s*", "", t)
        body = []
        for ln in b:
            if ln.startswith("###"):
                body.append("####" + ln[3:])
            elif ln.startswith("####"):
                body.append("#####" + ln[4:])
            else:
                body.append(ln)
        ai_children.append((title, body))
    idx += 1

    flat = []
    for t, b in merged:
        if b or not b:
            flat.append((t, b, "top"))
    # 把 AI 子章節掛到「AI 備援方案」底下
    out_sections = []
    i = 0
    while i < len(flat):
        t, b, _ = flat[i]
        if "AI 備援方案" in t:
            body = []
            for at, ab in ai_children:
                body.append(f"### {at}")
                body.append("")
                body += ab
                body.append("")
            out_sections.append((t, body))
            i += 1
            continue
        out_sections.append((t, b))
        i += 1

    write_doc(
        DESIGN / "07-配音執行包-真人錄音與AI備援.md",
        "《雌雄》配音執行包：真人錄音與 AI 備援",
        [
            "版本：V2.0（真人錄音為正式方案；AI 備援方案為 MiniMax Voice Design）",
            "用途：委託配音員、錄音現場執行、回收後的後期與驗收",
            "",
            "> 前十節是**真人錄音**（可直接轉寄配音員）；第十一節是**AI 備援方案**。",
            "> 角色音色與試鏡規格見 `06-聲音設計-音色選角與試鏡.md`。",
            "",
        ],
        out_sections,
        ["## 十二、與其他文件的關係", "",
         "| 文件 | 負責範圍 |", "|---|---|",
         "| `03-臺詞與雙語版本.md` | 台詞文字、斷句、重音、語速、字幕、粵語版本 |",
         "| `05-音樂與音效設計.md` | 音樂、Foley、環境音、混音與交付 |",
         "| `06-聲音設計-音色選角與試鏡.md` | 聲線、選角、錄音規格、對白處理鏈 |", ""],
    )

    # ---------- 刪除舊檔 ----------
    for old in ["01-視覺設定-人物場景道具.md", "01-視覺設定-人物場景道具.md", "01-視覺設定-人物場景道具.md", "02-分鏡表-靜態與動態.md",
                "03-臺詞與雙語版本.md", "04-AI生成提示詞包.md", "05-音樂與音效設計.md",
                "06-聲音設計-音色選角與試鏡.md", "06-聲音設計-音色選角與試鏡.md", "03-臺詞與雙語版本.md",
                "07-配音執行包-真人錄音與AI備援.md", "02-分鏡表-靜態與動態.md", "07-配音執行包-真人錄音與AI備援.md"]:
        p = DESIGN / old
        if p.exists():
            p.unlink()
    print("舊檔已刪除")
    for p in sorted(DESIGN.glob("*.md")):
        print("  ", p.name)


if __name__ == "__main__":
    main()
