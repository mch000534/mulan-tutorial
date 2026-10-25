# GitHub Pages Implementation Plan

**Goal:** 在新倉庫發布既有教學網站。

**Architecture:** 保留 site 與素材目錄結構，以 Actions 打包靜態內容。

**Tech Stack:** HTML、CSS、JavaScript、GitHub Actions、GitHub Pages。

- [x] 檢查既有網站、素材大小、相對連結與 GitHub 登入。
- [x] 建立 `.gitignore`、根目錄入口與 `.github/workflows/pages.yml`。
- [x] 本機模擬打包，驗證發布內容的相對連結（961 次引用，無缺檔）。
- [x] 建立公開倉庫、推送並啟用 Pages Actions。
- [x] 確認部署結果及線上網址：Actions 40195062992 成功；首頁、教學頁、CSS、JS、提示詞、縮圖、分鏡影片、剪輯及設計文件抽查均回應 HTTP 200。

線上網址：https://mch000534.github.io/mulan-tutorial/

倉庫：https://github.com/mch000534/mulan-tutorial
