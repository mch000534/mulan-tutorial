#!/usr/bin/env python3
"""合併後的全域交叉引用置換（舊檔名 → 新檔名）。

用法：python3 scripts/rewrite_refs.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MAP = {
    "07-配音執行包-真人錄音與AI備援.md": "07-配音執行包-真人錄音與AI備援.md",
    "02-分鏡表-靜態與動態.md": "02-分鏡表-靜態與動態.md",
    "01-視覺設定-人物場景道具.md": "01-視覺設定-人物場景道具.md",
    "01-視覺設定-人物場景道具.md": "01-視覺設定-人物場景道具.md",
    "01-視覺設定-人物場景道具.md": "01-視覺設定-人物場景道具.md",
    "02-分鏡表-靜態與動態.md": "02-分鏡表-靜態與動態.md",
    "03-臺詞與雙語版本.md": "03-臺詞與雙語版本.md",
    "04-AI生成提示詞包.md": "04-AI生成提示詞包.md",
    "05-音樂與音效設計.md": "05-音樂與音效設計.md",
    "06-聲音設計-音色選角與試鏡.md": "06-聲音設計-音色選角與試鏡.md",
    "06-聲音設計-音色選角與試鏡.md": "06-聲音設計-音色選角與試鏡.md",
    "03-臺詞與雙語版本.md": "03-臺詞與雙語版本.md",
    "07-配音執行包-真人錄音與AI備援.md": "07-配音執行包-真人錄音與AI備援.md",
}

TARGETS = [
    *ROOT.glob("design/*.md"),
    ROOT / "README.md",
    ROOT / "assets" / "audio" / "README.md",
    *ROOT.glob("scripts/*.py"),
    ROOT / "scripts" / "build_site.py",
]

# 章節引用：舊「章節號 → 新章節號」（合併後重新編號）
SECTION_FIXES = [
    # design/08 §二 角色聲線總表 → 06 §二（不變）；§2.2–2.3 → §二
    ("design/06 §二", "design/06 §二"),
    ("design/06 §五", "design/06 §五"),
    ("design/06 §七", "design/06 §七"),
    ("design/06 §六", "design/06 §六"),
    ("design/06 §九", "design/06 §九"),
    ("design/06 §二之一", "design/06 §二之一"),
    ("design/03 §二", "design/03 §二"),
    ("design/03 §三", "design/03 §三"),
    ("design/03 §四", "design/03 §四"),
    ("design/03 §六", "design/03 §六"),
    ("design/02 V1.1", "design/02 V1.1"),
    ("design/02 §", "design/02 §"),
    ("design/05 §", "design/05 §"),
    ("design/03 §", "design/03 §"),
    ("design/07 §", "design/05 §"),
    ("design/07 §", "design/05 §"),
    ("§六（`design/03`", "§六（`design/03`"),
    ("`03-臺詞與雙語版本.md`", "`03-臺詞與雙語版本.md`"),
]


def main() -> None:
    changed = []
    for path in TARGETS:
        if not path.exists() or path.suffix not in (".md", ".py"):
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        for old, new in MAP.items():
            text = text.replace(old, new)
        for old, new in SECTION_FIXES:
            text = text.replace(old, new)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            changed.append(str(path.relative_to(ROOT)))
    print("已更新：")
    for c in changed:
        print("  ", c)

    # 檢查是否還有舊檔名
    left = []
    for path in TARGETS:
        if not path.exists() or path.suffix not in (".md", ".py"):
            continue
        text = path.read_text(encoding="utf-8")
        for old in MAP:
            if old in text:
                left.append((str(path.relative_to(ROOT)), old))
    print("\n殘留舊檔名：", left or "無")


if __name__ == "__main__":
    main()
