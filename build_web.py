# -*- coding: utf-8 -*-
"""
把遊戲打包成可以在瀏覽器裡跑的 WebAssembly 版本（pygbag）。

用法：
    python build_web.py            # 建置，輸出到 web_build/build/web/
    python build_web.py --serve    # 建置並在 http://localhost:8000 本機試玩

這個腳本處理三件 pygbag 不會幫你做的事：

1. 篩選素材。pygbag 會把 main.py 所在資料夾的「所有」檔案打包進網頁，而這個專案裡
   有 98 MB 的南極地形原始資料集、遊戲錄影 mp4、爆炸圖的原始 eps、以及開發過程的
   舊版程式，學生完全不需要下載這些。

2. 音訊轉檔。瀏覽器版的 SDL_mixer 解不開 MP3，pygbag 會直接拒絕建置。這裡用
   libsndfile 把 MP3/WAV 轉成 OGG Vorbis，順便把音樂的體積壓下來。
   桌機版不受影響：程式的 find_asset() 會把音訊副檔名視為可互換。

3. UTF-8。pygbag 讀 main.py 時用系統預設編碼，在繁體中文 Windows 上是 cp950，
   會被程式裡的中文註解噎到。這裡強制子程序進入 Python 的 UTF-8 模式。
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "web_build")
GAME = "alien_shooter_3d_iceground.py"

AUDIO_IN = {".mp3", ".wav"}        # 轉成 .ogg 再放進網頁包

# 所有音訊統一成這個取樣率，必須和遊戲 pygame.mixer.pre_init() 的設定一致。
MIXER_RATE = 44100

# 縮小解析度再打包。這裡的瓶頸是記憶體而不是檔案大小：WebAssembly 的線性記憶體
# 裝不下原尺寸圖集解開後的點陣（megalon 4400x3840 = 64 MB），載入時會直接
# "memory access out of bounds" 當掉。這幾張圖的切格都是依圖集實際尺寸換算，
# 縮小不會破壞格線（魔王圖集的格子常數由 load_kaiju_frames() 自動等比換算）。
#   不要縮 explosion_frames.png：程式切完後若格高不是 512 會再放大回 512，縮了也白縮。
DOWNSCALE = {
    "megalon_sprites.png": 0.5,    # 64.5 MB -> 16.1 MB
    "saucer_sprites.png": 0.5,     #  6.8 MB ->  1.7 MB
    "minion_sprites.png": 0.5,     #  3.0 MB ->  0.8 MB
}

# 不放進網頁版的檔案（理由寫在旁邊）
SKIP_EXT = {
    ".mp4",      # 遊戲錄影，執行時不需要
    ".gz",       # rema_...tar.gz：98 MB 南極地形原始資料集，已經轉成 ice_heightmap.png
    ".eps",      # 爆炸圖的原始向量檔
    ".pyc",
}
SKIP_FILES = {
    GAME,                      # 會改名成 main.py 複製
    "build_web.py",
    "background_0.mp3",        # 舊版背景音樂，find_asset 正規化後比對不到，程式不會載入
    "rema_overview.png",       # 資料集的預覽圖，程式沒有引用
    "make_ice_heightmap.py",   # 產生 ice_heightmap.png 的前處理工具，執行時不需要
    "highscore.txt",           # 網頁版的最高分存在瀏覽器 localStorage
    "highscore3d.txt",
    "kuoyuan_sprites.png",     # 最終魔王圖集的備援版：find_asset 優先選 megalon，這張載不到
    "熔界獸.png",          # 程式裡只出現在一行註解，沒有任何地方載入它
    ".gitignore",
    # 開發過程的舊版程式：留在 repo 當紀錄，但不必讓學生下載
    "Claude3d.py", "Claude3d2.py", "Claude3d3.py",
    "g1.py", "g2.py", "g3.py", "g4.py",
}
SKIP_DIRS = {"web_build", ".git", "__pycache__",
             "explosion-process-set-with-explosion-stages-symbols-cartoon-vector-illustration"}


def to_ogg(src, dst):
    """
    把 MP3/WAV 轉成 OGG Vorbis。回傳 (原始大小, 輸出大小)。

    分塊串流讀寫，不要一次 sf.read() 整首再 sf.write()：幾分鐘長的立體聲音樂
    解開後是很大的陣列，soundfile 一次性寫入會在 cffi 層堆疊溢位（整個行程
    無聲無息地死掉，連 traceback 都看不到）。
    """
    import soundfile as sf
    # compression_level：0.0 = 最高品質/最大檔案，1.0 = 最小檔案。
    # 音樂壓多一點（學生要下載），短音效保留品質。
    level = 0.6 if os.path.getsize(src) > 1_000_000 else 0.3

    with sf.SoundFile(src) as fin:
        need_resample = fin.samplerate != MIXER_RATE
        if need_resample:
            # 素材裡 48000 Hz 和 44100 Hz 混雜，混音器只能設定一個取樣率，
            # 剩下的就得在播放時即時換算 —— WASM 下這件事會爆音、走音。
            # 所以在打包階段一次換算好，執行時完全不需要重新取樣。
            import numpy as np
            from scipy.signal import resample_poly
            from math import gcd
            data = fin.read(dtype="float32")
            g = gcd(MIXER_RATE, fin.samplerate)
            data = resample_poly(data, MIXER_RATE // g, fin.samplerate // g, axis=0)
            data = np.clip(data, -1.0, 1.0).astype("float32")
            if data.ndim == 1:
                data = data.reshape(-1, 1)
            # 分塊寫入：一次把整首丟給 sf.write()，長音樂會在 cffi 層堆疊溢位，
            # 整個行程無聲無息地結束（exit 127，連 traceback 都沒有）。
            with sf.SoundFile(dst, "w", samplerate=MIXER_RATE, channels=data.shape[1],
                              format="OGG", subtype="VORBIS",
                              compression_level=level) as fout:
                for i in range(0, len(data), 65536):
                    fout.write(data[i:i + 65536])
        else:
            with sf.SoundFile(dst, "w", samplerate=fin.samplerate, channels=fin.channels,
                              format="OGG", subtype="VORBIS", compression_level=level) as fout:
                for block in fin.blocks(blocksize=65536, dtype="float32"):
                    fout.write(block)

    return os.path.getsize(src), os.path.getsize(dst), need_resample


def collect():
    """清空並重建 web_build/。回傳 (檔案清單, 音訊轉檔統計)。"""
    if os.path.isdir(BUILD):
        shutil.rmtree(BUILD)
    os.makedirs(BUILD)

    # pygbag 規定進入點必須叫 main.py
    shutil.copy2(os.path.join(ROOT, GAME), os.path.join(BUILD, "main.py"))

    audio_before = audio_after = 0
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name)
        if os.path.isdir(path) or name in SKIP_FILES:
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in SKIP_EXT:
            continue
        if name in DOWNSCALE:
            from PIL import Image
            im = Image.open(path)
            f = DOWNSCALE[name]
            small = im.resize((int(im.width * f), int(im.height * f)), Image.LANCZOS)
            small.save(os.path.join(BUILD, name))
            print("      縮圖  %-28s %dx%d -> %dx%d（記憶體 %.1f -> %.1f MB）"
                  % (name, im.width, im.height, small.width, small.height,
                     im.width * im.height * 4 / 1048576,
                     small.width * small.height * 4 / 1048576))
        elif ext in AUDIO_IN:
            out = os.path.join(BUILD, os.path.splitext(name)[0] + ".ogg")
            b, a, rs = to_ogg(path, out)
            audio_before += b
            audio_after += a
            print("      轉檔  %-28s %6.1f KB -> %6.1f KB%s"
                  % (name, b / 1024, a / 1024, "  (已重新取樣)" if rs else ""))
        else:
            shutil.copy2(path, os.path.join(BUILD, name))

    files = sorted(os.listdir(BUILD))
    return files, (audio_before, audio_after)


def main():
    print("[1/2] 整理素材到 web_build/")
    files, (a_before, a_after) = collect()
    total = sum(os.path.getsize(os.path.join(BUILD, f)) for f in files)
    if a_before:
        print("      音訊：%.1f MB -> %.1f MB（省下 %.0f%%）"
              % (a_before / 1048576, a_after / 1048576,
                 100 * (1 - a_after / a_before)))
    print("      共 %d 個檔案，%.1f MB" % (len(files), total / 1048576))

    cmd = [sys.executable, "-m", "pygbag",
           "--width", "1280", "--height", "720",
           "--title", "ALIEN ADVENTURE 3D"]
    if "--serve" not in sys.argv:
        cmd.append("--build")          # 只建置，不啟動本機測試伺服器
    cmd.append(os.path.join(BUILD, "main.py"))

    # pygbag 用系統預設編碼讀 main.py，繁中 Windows 上是 cp950，會被中文註解噎到
    env = dict(os.environ, PYTHONUTF8="1")
    print("\n[2/2] 執行 pygbag\n")
    rc = subprocess.call(cmd, env=env)

    out = os.path.join(BUILD, "build", "web")
    if rc == 0 and os.path.isfile(os.path.join(out, "index.html")):
        size = sum(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out)
                   if os.path.isfile(os.path.join(out, f)))
        print("\n完成：%s（%.1f MB）" % (out, size / 1048576))
    return rc


if __name__ == "__main__":
    sys.exit(main())
