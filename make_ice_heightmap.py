"""
把 REMA 南極高程資料轉成遊戲用的 ice_heightmap.png

用法（在遊戲資料夾打開命令提示字元）：
    pip install tifffile imagecodecs numpy pygame
    python make_ice_heightmap.py rema_mosaic_1km_v2.0_filled_cop30.tar.gz

可以直接吃下載來的 .tar.gz（不用先解壓縮），也可以吃 .tif。
程式會自動在整個南極大陸裡找「山最多、起伏最大」的區塊裁下來用，
並另存一張 rema_overview.png，用紅框標出它選了哪裡。

資料來源（CC BY 4.0，免帳號）：
    https://pgc-web-data-prd-01.pgc.umn.edu/elev/dem/setsm/REMA/mosaics/v2.0/1km/
公開發布遊戲時請註明：Reference Elevation Model of Antarctica (REMA), Polar Geospatial Center.
"""
import io
import os
import sys
import tarfile
import numpy as np


def read_dem(src):
    import tifffile
    if src.endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(src) as tar:
            tifs = [m for m in tar.getmembers() if m.name.lower().endswith(".tif")]
            dems = [m for m in tifs if m.name.lower().endswith("_dem.tif")] or \
                   [m for m in tifs if "dem" in os.path.basename(m.name).lower()]
            if not dems:
                raise SystemExit("壓縮檔裡找不到高程檔（*_dem.tif）。檔案內容：\n  " +
                                 "\n  ".join(m.name for m in tifs))
            m = dems[0]
            print(f"讀取壓縮檔內的 {os.path.basename(m.name)} ...")
            return tifffile.imread(io.BytesIO(tar.extractfile(m).read()))
    print(f"讀取 {src} ...")
    return tifffile.imread(src)


def most_rugged_window(dem, valid, win):
    """
    找起伏最大的區塊：把地圖切成小方格，算每格的高程標準差，
    再找標準差總和最大、而且完全沒有「無資料」（海洋）的視窗。
    排除有無資料的視窗很重要 —— 否則會選到海岸線，那裡的高低差是補值造成的假懸崖。
    """
    b = max(1, win // 8)
    H, W = dem.shape[0] // b, dem.shape[1] // b
    d = dem[:H * b, :W * b].reshape(H, b, W, b)
    v = valid[:H * b, :W * b].reshape(H, b, W, b)
    rough = d.std(axis=(1, 3))
    clean = v.all(axis=(1, 3))
    k = win // b
    best, best_pos = -1.0, None
    csum = np.pad(np.where(clean, rough, -1e9), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    for i in range(0, H - k + 1):
        for j in range(0, W - k + 1):
            s = csum[i + k, j + k] - csum[i, j + k] - csum[i + k, j] + csum[i, j]
            if s > best:
                best, best_pos = s, (i * b, j * b)
    return best_pos


def main(src, dst="ice_heightmap.png", win=260, out_size=512):
    import pygame
    dem = read_dem(src).astype("float64")
    if dem.ndim > 2:
        dem = dem[..., 0]
    valid = np.isfinite(dem) & (dem > -1000)
    if not valid.any():
        raise SystemExit("這個檔案沒有有效的高程資料")
    print(f"高程圖尺寸 {dem.shape[1]} x {dem.shape[0]}，有效資料 {100 * valid.mean():.0f}%")

    if min(dem.shape) > win * 1.5:
        y0, x0 = most_rugged_window(dem, valid, win)
        crop = dem[y0:y0 + win, x0:x0 + win].copy()
        print(f"自動選取最多山的區塊：左上角 ({x0}, {y0})，大小 {win} x {win} 像素")
        # 總覽圖：整片南極縮小，紅框標出選到的區塊
        step = max(1, max(dem.shape) // 800)
        ov = dem[::step, ::step].copy()
        ov[~valid[::step, ::step]] = np.nan
        lo, hi = np.nanpercentile(ov, [1, 99])
        g = np.nan_to_num(np.clip((ov - lo) / (hi - lo), 0, 1) * 220 + 20, nan=0).astype("uint8")
        rgb = np.stack([g, g, g], axis=-1)
        yy0, xx0, ww = y0 // step, x0 // step, max(2, win // step)
        for t in range(3):
            rgb[yy0 + t, xx0:xx0 + ww] = rgb[yy0 + ww - 1 - t, xx0:xx0 + ww] = (255, 40, 40)
            rgb[yy0:yy0 + ww, xx0 + t] = rgb[yy0:yy0 + ww, xx0 + ww - 1 - t] = (255, 40, 40)
        pygame.image.save(pygame.surfarray.make_surface(rgb.transpose(1, 0, 2)), "rema_overview.png")
        print("已存 rema_overview.png（紅框 = 選取的區塊）")
    else:
        crop = dem.copy()
    cv = np.isfinite(crop) & (crop > -1000)
    crop[~cv] = crop[cv].min()

    step = max(1, int(np.ceil(max(crop.shape) / out_size)))
    crop = crop[::step, ::step]
    lo, hi = np.percentile(crop, [1, 99.5])
    img = (np.clip((crop - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype("uint8")
    pygame.image.save(pygame.surfarray.make_surface(np.stack([img.T] * 3, axis=-1)), dst)
    print(f"完成：{dst}（{img.shape[1]}x{img.shape[0]}），這塊地的高程 {lo:.0f} ~ {hi:.0f} 公尺")
    print("接著直接執行 python alien_shooter_3d.py，啟動訊息出現「真實高程圖」就代表成功。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        main(sys.argv[1])
