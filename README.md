# 《雌雄》· 從〈木蘭辭〉到 60 秒短片

一份完整的 AI 短片前期製作專案：設計文件、45 鏡分鏡、Qwen Image 2.1 生成、9:16 普通話與 16:9 粵語雙版本。

## 先看這個

- **教學網站（SOP + 133 張圖庫 + 粗剪播放器）**：[`site/index.html`](./site/index.html)
- **手剪版（16:9 粵語＋普通話）**：[`assets/video/cuts/雌雄_手剪_16x9_粵語_v1.mp4`](./assets/video/cuts/雌雄_手剪_16x9_粵語_v1.mp4)、[`雌雄_手剪_16x9_普通話_v1.mp4`](./assets/video/cuts/雌雄_手剪_16x9_普通話_v1.mp4)（1920×1080 / 115.4s，網站章節：06B）
- **60 秒粵語粗剪**：[`assets/video/cuts/雌雄_粗剪_16x9_粵語_v1.mp4`](./assets/video/cuts/雌雄_粗剪_16x9_粵語_v1.mp4)（網站章節：06B）
- **45 鏡完整清單（時間碼／劇本／聲音／首幀與動態提示詞）**：[`site/index.html#shots`](./site/index.html#shots)
- **8 份設計文件的生成提示詞（可直接複製）**：[`site/index.html#doc-prompts`](./site/index.html#doc-prompts)
- **設計文件索引**：[`design/README.md`](./design/README.md)
- **生成資產報告**：[`assets/generated/README.md`](./assets/generated/README.md)

## 開啟教學網站

```bash
python3 scripts/build_site.py
python3 -m http.server 8000
open http://localhost:8000/site/
```

## 專案結構

| 路徑 | 內容 |
|---|---|
| `design/` | 8 份設計文件：視覺聖經、視覺設定（人物＋場景＋道具）、分鏡表（靜態＋動態）、臺詞與雙語版本、AI 生成提示詞包、音樂與音效、聲音設計（音色＋選角＋試鏡）、配音執行包（真人錄音＋AI 備援） |
| `scripts/` | `build_jobs.py` 產生任務、`comfy_batch.py` 批次生成、`h3_i2v.py` 以 MiniMax H3 生成 i2v 動態素材、`assemble_cut.py` 依時間碼組接 60 秒粗剪、`build_site.py` 建置教學網站、`shotlist.py` 由設計文件解析 45 鏡清單、`doc_prompts.py` 文件生成提示詞、`voice_common.py` 配音共用模組、`post_voices.py` 真人錄音後期與對點、`minimax_import.py` MiniMax 產出匯入、`tts_voices.py` edge-tts 備用方案 |
| `assets/generated/` | 133 張生成資產（JPG q90）、contact sheets、manifest 與資產索引 |
| `assets/video/` | 90 支 16:9 i2v 片段（`shots_169/`）、60 秒粵語粗剪（`cuts/`）、生成紀錄 |
| `assets/audio/` | 配音工作區：回收原始檔、處理後單句 WAV、對點 DX 音軌、字幕、驗收報告、AI 備用稿 |
| `site/` | 教學網站原始碼、133 張縮圖與可下載的 `prompts.md` |

## 目前狀態

- [x] 設計文件 8 份（00–07，原 13 份已合併）
- [x] 9:16 資產 78 張
- [x] 16:9 獨立重生成 55 張
- [x] 8 顆問題鏡頭重生成
- [x] 教學網站與圖庫
- [x] 45 鏡完整清單章節（由 `design/` 解析，時間碼、劇本、聲音、首幀與動態提示詞；16:9 片段已內嵌播放器，9:16 仍為佔位）
- [x] 動態分鏡設計（45 鏡動態規格與 i2v 提示詞）
- [x] i2v 改用 MiniMax H3：45 條提示詞把視覺描述與原生音軌（環境聲 + 音效）合為一段，音樂與人聲留後期；規格改為 5–15 秒整秒、原生 24fps、慢動作以提示詞描述 + 後期變速
- [x] 生成提示詞樣式去重（`design/04` V1.1）：`scripts/build_jobs.py` 改以文件第二節的 STYLE-A/B/C 為單一來源，場景與鏡頭各只套一次樣式，並自動去除提示詞裡重複的 `cinematic`／`9:16`／`5th century`／`35mm`；S2 用 STYLE-B、S8／S9 用 STYLE-C，16:9 版本沿用同一套替換規則
- [x] 關鍵音效改以「對應鏡次」歸屬（`design/05` V1.4）：45 個音效依分鏡表聲音欄落到正確鏡次，網站每鏡的「音效（H3 原生）」不再錯位
- [x] 時間碼放寬（`design/02` V1.1），台詞視窗可容自然氣口
- [x] 錄音執行包（`design/07`：cue 卡、交件規格、回收驗收；附 AI 備援方案）
- [x] 真人錄音後期／對點／驗收腳本（`scripts/post_voices.py`）
- [ ] 真人錄音（普通話＋粵語，8 句 × 4 版本）
- [x] 組接粗剪（45 鏡 × 時間碼，對白不變速＋L cut，61.4s；`scripts/assemble_cut.py` → `assets/video/cuts/`）
- [x] i2v 測試（S1 鏡 01–03，16:9 / 0.9MP / 1280×736 / 5.17s / 原生立體聲，`scripts/h3_i2v.py`）
- [x] i2v 全 45 鏡 × 2 個 seed：16:9 共 90 支片段（v1 ＋ v2，提示詞不變只換 seed），1280×736／24fps／原生立體聲，紀錄在 `assets/video/manifest_i2v.jsonl`
- [x] 教學網站接上動態素材：每鏡雙 seed 並排播放器、45 鏡 × 2 支的片段索引表（可依場景篩選）、四張重點動態卡播放器；片段以相對路徑引用 `../assets/video/shots_169/`
- [ ] i2v 9:16 直式片段未生成（`assets/video/shots_916/`）
- [x] 設計文件合併為 8 份（人物＋場景＋道具／靜態＋動態／臺詞＋雙語／音色＋試鏡／錄音包＋AI 語音），教學網站同步更新
- [ ] 對嘴、混音、調色與交付
