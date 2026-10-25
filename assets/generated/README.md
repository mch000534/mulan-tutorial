# 《雌雄》生成資產

以 ComfyUI + Qwen Image 2.1 產出的前期視覺資產。鏡頭與場景提供 **9:16 與 16:9 雙版本**；角色參考圖、角色設定圖與道具圖維持原始比例，供 i2v、剪輯 animatic 與美術對照使用。

## 語言版本

| 畫幅 | 對白／VO | 字幕 |
|---|---|---|
| 9:16 | 普通話 | 標準書面中文 |
| 16:9 | 廣東話（粵語） | 標準書面中文；可選粵語字幕 |

兩版畫面獨立生成，音軌、字幕與對嘴版本分開管理；詳見 [`design/10-雙語版本設計.md`](../../design/10-雙語版本設計.md)。

## 索引

- 教學網站（SOP + 133 張圖庫）：[`../../site/index.html`](../../site/index.html)
- 資產總覽網頁：`index.html`（可直接用瀏覽器開啟）
- 45 鏡總表（9:16）：`contact_sheet_shots.jpg`
- 45 鏡總表（16:9）：`contact_sheet_shots_16x9.jpg`
- 場景總表（16:9）：`contact_sheet_scenes_16x9.jpg`
- 角色總表：`contact_sheet_characters.jpg`
- 道具與場景總表：`contact_sheet_props_scenes.jpg`

## 生成環境

| 項目 | 值 |
|---|---|
| ComfyUI | 0.37.4 |
| 伺服器 | `http://172.16.30.35:8188` |
| GPU | NVIDIA GB10（130GB VRAM） |
| Diffusion model | `qwen_image_2.1_int8_convrot.safetensors` |
| Text encoder | `qwen3vl_8b_int8_convrot.safetensors`（type `qwen_image`） |
| VAE | `qwen_image_2.1_vae_bf16.safetensors` |
| Sampler | `euler` / `simple`，25 steps，cfg 2.0 |

## 產出數量

| 類型 | 9:16 | 16:9 | 尺寸 |
|---|---:|---:|---|
| 角色參考圖 | 7 | — | 1024×1024（B 為 1024×576 舊圖） |
| 角色設定圖 | 10 | — | 1536×1024 |
| Hero Props | 6 | — | 1024×1024 |
| 場景概念圖 | 10 | 10 | 720×1280／1280×720 |
| 鏡頭首幀 | 45 | 45 | 720×1280／1280×720 |
| **合計** | **78** | **55** | 共 133 張 |

`manifest.jsonl` 保留 9:16 每次生成紀錄；`manifest_16x9.jsonl` 保留 16:9 紀錄。兩者皆含重生成，最新一次即為目前檔案。

## 檔案格式

ComfyUI 輸出 PNG，但 PNG 對這種「全畫面都是漸層與顆粒」的 AI 影像特別不划算：同一張圖 PNG 約 1.2 MB、JPEG 只要 144 KB。因此本專案統一以 **JPEG（quality 90、4:4:4 無色度抽樣、progressive）** 儲存，尺寸完全不變。

| 項目 | 轉換前 | 轉換後 |
|---|---|---|
| 133 張正式資產 | 185.3 MB（PNG） | 20.8 MB（JPG） |
| 單張 720×1280 鏡頭 | 1.2 MB | 144 KB |

轉換由 `scripts/to_jpg.py` 進行（可重跑，會跳過已存在檔案）；`scripts/comfy_batch.py` 下載後直接寫 JPG，不會再產生 PNG。

## 16:9 版本說明

- 16:9 是**獨立重生成**，不是把 9:16 裁切或補邊。
- 提示詞中的 `vertical 9:16 composition` 已改為 `horizontal 16:9 composition`；其餘內容與參考圖不變。
- 因模型對不同畫幅的構圖反應不同，16:9 的人物大小、留白與物件位置會與 9:16 略有差異；剪輯與 i2v 需分別對點。
- 角色設定圖與道具圖不重新生成 16:9，因為它們是參考資產，不是成片畫幅。

## 重生成紀錄

以下 9:16 鏡頭因構圖或造型問題重生成，最終提示詞存於 `scripts/overrides.json`；16:9 版本繼承同一組提示詞並改為橫式：

| 鏡頭 | 原因 | 處理 |
|---|---|---|
| `shot_02` | 毛筆遮住嘴唇 | 改為筆尖抵下唇、唇形可見 |
| `shot_03` | 誤用 B 參考圖、妝感過重 | 改用 A 參考圖，去除眼線與磨皮 |
| `shot_20` | 生成成沙漠 | 改為暴風雪山口 |
| `shot_30` | 出現現代舉手禮 | 改為中國抱拳禮 |
| `shot_40` | 構圖變成大殿人群 | 改為門外拍她進房關門 |
| `shot_41` | 手部偏男性、胭脂盒過紅 | 改為女性手、深色盒 |
| `shot_43` | 雙兔背對鏡頭 | 改為側面並跑 |
| `shot_45` | 妝感過重、無疤 | 改為自然膚質、左眉舊疤 |

`scripts/build_jobs.py` 會自動套用 `scripts/overrides.json`，重建 `jobs.json` 不會覆蓋這些修正；同時產出 `jobs_16x9.json`。

## 指令

```bash
python3 scripts/build_jobs.py                 # 重建 jobs.json 與 jobs_16x9.json
python3 scripts/comfy_batch.py --kind ref     # 生成參考圖
python3 scripts/comfy_batch.py --kind shot --only shot_30 --force
python3 scripts/comfy_batch.py --jobs scripts/jobs_16x9.json --only shot_01_16x9 --force
python3 scripts/comfy_batch.py --jobs scripts/jobs_16x9.json --start 2 --limit 18 --manifest assets/generated/manifest_16x9.jsonl
python3 scripts/to_jpg.py                   # PNG 資產轉 JPEG（已轉過會自動跳過）
```

## 已知問題

1. **16:9 非裁切**：橫式構圖與直式不同，人物大小與留白需重新對點；不可直接把 9:16 當成 16:9 的安全框。
2. **花鈿顏色文件矛盾**：`design/00-視覺聖經.md` 將花鈿列為紅色，`design/01-人物設定.md` 與 `02-場景設定.md` 明定金箔。目前生成採金箔，待導演定案。
3. **敵軍面具**：遠景（22、25）未完全落實黑鐵面具，近景需補或以後製處理。
4. **三張木蘭臉**：A／B／C 仍有年齡與骨相差異；單場可過，跨場剪接需對臉或補拍。
5. **首幀非成片**：表情、運鏡、衣擺與頭髮動態仍需 i2v 或實拍補足。
6. **`shot_01` 9:16 胸甲比例偏小**：16:9 版本已改善；直式可作為特寫起點，若拉遠需重生成。
