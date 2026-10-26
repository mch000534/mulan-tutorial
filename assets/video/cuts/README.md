# 《雌雄》粗剪（16:9 粵語）

45 鏡依 `design/02` V1.1 時間碼組接，混入 DX 對白軌與 H3 原生環境聲。
**對白不變速**（minimax/cantonese 只壓停頓），某句比窗格長時以 **L cut** 跨到下一畫面，
下一句順延到前一句結束；尾句超過 60s 時延長最後一鏡（V8 完整收尾，總長 61.417s）。

| 檔案 | 內容 |
|---|---|
| `雌雄_手剪_16x9_粵語_v1.mp4` | 手動剪輯版（2026-10-24 更新，重編碼）；H.264 1920×1080 / 24fps / 2770 幀＝115.417s；AAC 48k 立體聲；約 26 MB |
| `雌雄_手剪_16x9_普通話_v1.mp4` | 手動剪輯版普通話（2026-10-24）；規格同上 |
| `雌雄_手剪_16x9_MV_v1.mp4` | 手動剪輯 MV 版本；H.264 1920×1080 / 24fps / 135.189s；AAC；約 31 MB |
| `雌雄_粗剪_16x9_粵語_v1.mp4` | 全 v1 seed 粗剪；H.264 1280×720 / 24fps / 1474 幀＝61.417s；AAC 48k 立體聲；內嵌粵語軟字幕 |
| `雌雄_粗剪_16x9_粵語_v1.json` | 逐鏡紀錄（時間碼、幀數、tail_frames、採用 seed、來源檔名） |

## 對白實際落點（L cut 後）

| 句 | 設計窗格 | 實際落點 | 說明 |
|---|---|---|---|
| V1 | 1.00–4.35 | 1.00–6.18 | 跨剪輯點延到下一畫面 |
| V2 | 4.60–8.60 | 6.18–12.13 | 順延（等 V1 講完） |
| V3 | 16.20–18.80 | 16.20–18.85 | 原位 |
| V4 | 22.60–25.20 | 22.60–26.50 | 微延 |
| V5 | 30.90–34.70 | 30.90–34.35 | 原位 |
| V6 | 39.40–42.60 | 39.40–43.00 | 微延 |
| V7 | 54.30–57.30 | 54.30–58.18 | 微延 |
| V8 | 57.40–59.90 | 58.18–61.41 | 順延＋片尾延長 34 幀 |

## 重跑

```bash
python3 scripts/assemble_cut.py                      # 預設全 v1
python3 scripts/assemble_cut.py --round v2           # 全改 v2
python3 scripts/assemble_cut.py --ambience-gain 0.5  # 環境聲再小聲
python3 scripts/assemble_cut.py --no-subs            # 不要字幕軌
python3 scripts/assemble_cut.py --keep-work          # 保留逐鏡中間檔（_work/）
```

逐鏡換 seed：先寫 `seed_overrides.json`（例：`{"24": "v2", "42": "v1"}`），再：

```bash
python3 scripts/assemble_cut.py --overrides seed_overrides.json
```

## 組接規格

- 時間碼以 `scripts/shotlist.py` 解析 `design/02` 為準；幀數＝`round(end×24) − round(start×24)`
- 片段 1280×736 居中裁為 1280×720（去上下各 8px）
- 每鏡取素材開頭的所需幀數；素材不足才以 `setpts` 拉伸（目前沒有鏡頭用到）
- 對白：`minimax/cantonese/V*.wav` → `minimax_import.py --max-tempo 1.0`（只壓停頓不變速）
  → `post_voices.py` → `tracks/MULAN_60s_16x9_CANTONESE_DX.wav`（61.41s，L cut 順延）
- 環境聲：各鏡 H3 原生音軌，預設增益 0.85，於接點加 5ms 淡入出防爆音
- 中間片段用 MOV＋PCM（避免 MKV 1ms timebase 破壞 24fps），串接後 `-c:v copy` 進 MP4
- `--tail auto`（預設）：DX 尾音超過 60s 時，最後一鏡延長 34 幀讓 V8 講完

## 已知未完（粗剪 → 定剪）

- [ ] 逐鏡看 v1／v2，用 `--overrides` 定案 seed
- [ ] 鏡 15／25／43 後期變速（0.4×／0.25×／0.6×；目前直接取原速前段）
- [ ] 鏡 31 粵語對嘴素材（另生成）
- [ ] 音樂鋪底（`design/05` cue sheet，尚無音樂檔）
- [ ] 真人錄音取代 MiniMax DX（`assets/audio/recorded_raw/` 進料後跑 `post_voices.py`）
- [ ] 環境聲跨鏡交叉淡化（目前硬切，粗剪可接受）
- [ ] 調色與交付版（9:16 普通話版待 `shots_916/` 素材）

## 快速檢視

```bash
open "assets/video/cuts/雌雄_粗剪_16x9_粵語_v1.mp4"
# 或用 ffplay / IINA / VLC
```
