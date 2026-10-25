# 《雌雄》配音工作區

本目錄是配音的**工作區**，分成兩條線：

| 目錄 | 內容 | 狀態 |
|---|---|---|
| `recorded_raw/` | 配音員回收的**原始乾聲**（放這裡，`post_voices.py` 從這裡讀） | 待錄入 |
| `9x16_mandarin/`、`16x9_cantonese/` | 處理後的**單句乾聲 WAV**（48k/24bit/mono，峰值 −6 dBFS） | 待產生 |
| `tracks/` | 60 秒**對點 DX 對白軌** | 待產生 |
| `srt/` | 字幕（9:16 書面、16:9 書面、16:9 粵語） | 待產生 |
| `manifest.json` | 每檔參數與驗收數值 | 待產生 |
| `驗收報告.md` | 回收後的逐句驗收表 | 待產生 |
| `tts_draft/` | **AI 備用方案**（edge-tts）產物：64 個 WAV ＋ DX 軌 ＋ 字幕 | 已完成，僅供佔位與對照 |

---

## 正式流程：真人錄音

### 1. 委託

把 `design/07-配音執行包-真人錄音與AI備援.md` 轉寄給配音員。該文件包含：

- 選角規格與試鏡（`design/06`）
- 錄音技術規格（48k/24bit/mono、麥克風距離、底噪、每句四版本）
- **逐句 cue 卡**（文字、停頓、表演指示、目標視窗與字速、禁止事項）
- 粵語版的高風險字詞與粵拼
- 交件命名規則與自檢表

### 2. 回收與處理

把回收的檔案依語言放進：

```
assets/audio/recorded_raw/9x16_mandarin/    VO_V1_A.wav  MULAN_V6_C.wav  LEI_V7_EAR.wav ...
assets/audio/recorded_raw/16x9_cantonese/   同上
```

然後執行：

```bash
# 先檢查長度與峰值（不輸出檔案）
python3 scripts/post_voices.py --check

# 正式處理：套後期鏈 → 對齊 −6 dBFS → 對點 → 出 DX 軌、字幕、manifest、驗收報告
python3 scripts/post_voices.py

# 若某句超出時間碼，可選擇處理方式
python3 scripts/post_voices.py --fit stretch   # 微調速度對齊（最多 1.10×）
python3 scripts/post_voices.py --fit trim      # 裁掉尾端（錄音時已留 0.5s 靜默）
```

腳本會做的事（`design/06 §七`）：

```
讀入乾聲 → 去頭尾靜默 → 長度檢查 → HPF／De-ess／EQ／Compressor
        → 大殿殘響（只有 V6 木蘭台詞）→ 峰值對齊 −6 dBFS
        → 寫單句 WAV → 組 60 秒 DX 對白軌 → 出 SRT → 出 manifest 與驗收報告
```

### 3. 驗收

`assets/audio/驗收報告.md` 會列出每句的視窗、實測長度、峰值、是否對點。數值之外還有五項**必須用耳朵確認**（見報告末段）：VO 與木蘭是否同一人、句尾有無播音腔式下墜、V5/V7/V8 的三個關鍵表演、粵語高風險字詞、噴麥與呼吸。

---

## 備用流程一：MiniMax（人工生成 + 自動匯入）

1. 在 [minimax.io/audio](https://www.minimax.io/audio) 用 `design/07 §十一` 的提示詞生成，
   把檔案放成 `assets/audio/minimax/{mandarin,cantonese}/V1..V8.wav`。
2. 匯入＋整形＋對點：

```bash
python3 scripts/minimax_import.py --dry-run   # 只量數字
python3 scripts/minimax_import.py             # 停頓符合化 + 對點 → recorded_raw
python3 scripts/post_voices.py                # 後期、DX 軌、字幕、驗收報告
```

> 第一批實測：音色符合設計（老雷 125Hz、木蘭 174Hz），但模型加了 0.9–1.2 秒的
> 「莊重拖腔」空白，單句多出 2–3 秒。修正版提示詞見 `design/07 §十一 之 11.6.2`。

## 備用流程二：edge-tts（純程式生成）

```bash
python3 scripts/tts_voices.py --out assets/audio/tts_draft
```

> 通用 TTS 無法表現 `design/06` 要求的風格、真實停頓與真結巴，機械感明顯，**不可作為定稿**。
> 用途只有兩個：真人未到齊時的佔位音、純合成旁白的教學示範版。

---

## 時間碼

所有時間碼以 `design/02` **V1.1（時間碼放寬版）** 為準，與 `design/03` 同步。
放寬前後對照見 `design/07-配音執行包-真人錄音與AI備援.md` §十。共同資料表在 `scripts/voice_common.py`。

---

## 相關文件

| 文件 | 內容 |
|---|---|
| `design/02-分鏡表-靜態與動態.md` | 45 顆鏡頭與時間碼（V1.1 已放寬） |
| `design/03-臺詞與雙語版本.md` | 台詞、斷句、重音、字速、字幕時間碼 |
| `design/06-聲音設計-音色選角與試鏡.md` | 聲線、選角、錄音規格、後期鏈 |
| `design/06-聲音設計-音色選角與試鏡.md` | 試鏡台詞與評分表 |
| `design/03-臺詞與雙語版本.md` | 粵語台詞、粵拼、字幕 |
| `design/07-配音執行包-真人錄音與AI備援.md` | cue 卡、交件規格、回收流程與驗收 |
