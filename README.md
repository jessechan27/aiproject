# ALIEN ADVENTURE 3D

純 pygame 手寫的 3D 飛機射擊遊戲 —— 不依賴 OpenGL，透視投影引擎全部自己實作。

七種武器、炸彈與衝擊波大絕、多階段魔王戰，桌機版還有取自南極 REMA 地形資料的冰原地表。

## 直接玩（瀏覽器）

https://jessechan27.github.io/aiproject/

需要電腦鍵盤，手機不能玩。第一次進入要下載約 15 MB，之後瀏覽器會快取。

## 操作

| 按鍵 | 功能 |
|---|---|
| 方向鍵 / WASD | 操縱戰機 |
| 空白鍵 / 滑鼠左鍵 | 射擊 |
| 1~7 / Q / E / 滑鼠滾輪 | 切換武器 |
| X / B | 炸彈（清掉身邊彈幕） |
| K / V / Enter | 衝擊波大絕（全場限用 5 次） |
| P / F / R / ESC | 暫停 / 顯示FPS / 重新開始 / 離開 |

第 7 把「原子光束」要按住空白鍵蓄力，放開發射。

不使用 Ctrl 和 Shift：在 Windows 上這兩個鍵會切換中英文輸入法，切到中文後空白鍵和數字鍵會被輸入法攔截。

## 在自己電腦上跑

```
pip install pygame numpy
python alien_shooter_3d_iceground.py
```

## 重新建置網頁版

```
pip install pygbag soundfile scipy pillow
python build_web.py       # 產生 web_build/build/web/
python deploy_pages.py    # 複製到 docs/ 給 GitHub Pages
git add -A && git commit -m "更新網頁版" && git push
```

`build_web.py` 會自動篩選素材、把 MP3 轉成 OGG 並統一取樣率、把過大的圖集降解析度 ——
整個資料夾 347 MB，實際送到瀏覽器的只有約 15 MB。

## 網頁版與桌機版的差異

兩邊共用同一份 `alien_shooter_3d_iceground.py`，用 `IS_WEB` 旗標切換差異：

| 項目 | 桌機 | 瀏覽器 |
|---|---|---|
| 地形 | 南極冰原（REMA 真實地形） | 外星地貌 |
| 音訊 | MP3 | OGG，統一 44100 Hz |
| 最高分 | `highscore3d.txt` | 瀏覽器 localStorage |
| 啟動畫面 | 全螢幕 | 視窗（F11 可全螢幕） |

地形不同是因為南極冰原需要 numpy，而 pygbag 0.9.3 的 numpy wasm wheel 會破壞 SDL 的
視訊初始化（`pygame.error: The video driver did not add any displays`），只要那個 wheel
被載入，遊戲連視窗都開不起來。程式裡因此不能出現匯入 numpy 的字面語句 —— pygbag 是
掃描原始碼決定預載哪些套件的，寫在 try 裡或函式內一樣會被掃到。

## 開發紀錄

`g1.py` ~ `g4.py`、`Claude3d*.py` 是開發過程的早期版本，保留當紀錄，不參與網頁版建置。
