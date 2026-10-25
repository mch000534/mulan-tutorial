# 教學網站 · 雌雄

## 線上展示

網站使用 GitHub Pages 發布，推送到 `main` 後由
`.github/workflows/pages.yml` 自動部署。根目錄入口會轉到 `site/`。
首次設定時，在倉庫 **Settings → Pages → Source** 選擇 **GitHub Actions**。

發布內容包括 `site/`、`design/`、`assets/generated/`、`assets/ref/` 與
`assets/video/`，保留既有圖片、影片及下載連結的相對路徑。
網站發布前如有修改來源文件，先執行下方的重建指令，再提交更新。

《雌雄》從〈木蘭辭〉到 60 秒短片的製作 SOP，含 133 張生成圖、90 支 16:9 動態片段（每鏡兩個 seed 並排比較）、60 秒粵語粗剪播放器、流程圖、8 份設計文件的生成提示詞（附《雌雄》實際產出）與雙語版本說明。

## 開啟

```bash
cd /Users/barry/Downloads/木蘭辭
python3 scripts/build_site.py
python3 -m http.server 8000
open http://localhost:8000/site/
```

也可以直接雙擊 `site/index.html`；圖庫與下載連結使用相對路徑，直接開啟仍可瀏覽。

## 檔案

| 檔案 | 用途 |
|---|---|
| `index.html` | 由 `scripts/build_site.py` 產生，不要手動編輯 |
| `styles.css` | 版型、色彩、響應式與列印樣式 |
| `app.js` | 圖庫篩選、燈箱、章節導覽、提示詞複製與進場動畫 |
| `prompts.md` | 由 `scripts/build_site.py` 產生的 8 份文件生成提示詞，可下載 |
| `thumbs/` | 133 張圖庫縮圖（長邊 640px，JPEG） |
| 片段引用 | 影片以相對路徑 `../assets/video/shots_169/` 與 `../assets/video/cuts/` 引用，不複製進 `site/` |

## 重建

修改設計文件、提示詞或新增圖片後：

```bash
python3 scripts/build_site.py
```

建置脚本會：

1. 從 `assets/generated/` 收集正式資產。
2. 產生 `site/thumbs/` 縮圖。
3. 讀 `assets/video/manifest_i2v.jsonl`，把 45 鏡 × 2 個 seed 的片段（檔名、seed、時長、尺寸）接到鏡次清單與動態章節。
4. 讀 `assets/video/cuts/*.json`，若有粗剪就在「06B 粗剪」章節嵌入播放器與重跑說明。
5. 重寫 `site/index.html` 的 133 張圖庫卡片與提示詞區。
6. 產生 `site/prompts.md` 提示詞庫。
7. 把 `design/00–07` 的實際文件轉成 HTML，嵌在每張提示詞卡下方。

> 設計文件轉 HTML 需要 `mistune`（`pip install mistune`）；未安裝時會退回純文字預覽，不影響其餘建置。

## 來源

- 設計文件：`../design/`
- 生成資產：`../assets/generated/`
- 動態素材：`../assets/video/`（`shots_169/` 90 支 16:9 片段、`cuts/` 60 秒粵語粗剪、`manifest_i2v.jsonl` 生成紀錄）
- 生成脚本：`../scripts/build_site.py`、`../scripts/assemble_cut.py`
