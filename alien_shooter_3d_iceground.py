"""
================================================================
 ALIEN ADVENTURE 3D
================================================================
 純 pygame 手寫的透視投影 3D 引擎，不需要 OpenGL、不需要額外套件。

 素材放在跟這個 .py 同一個資料夾即可（大小寫不拘）：
   E1.png ~ E4.png      四種外星生物（以深度縮放的 billboard 呈現）
   explosion_graph.jpg  爆炸連續圖（3x3，共 9 格）
   shoot.wav / explosion.mp3 / background.mp3 / gameover.mp3
   jet.png              （選用，本版戰機改用 3D 多邊形模型）

 操作：
   方向鍵 / WASD   操縱戰機（會隨操作滾轉、俯仰）
   空白鍵           射擊
   1~7 / Q / E     切換武器（也可以用滑鼠滾輪；下方武器欄會顯示目前武器）
   原子光束（7）    按住空白鍵蓄力、放開發射；蓄滿會自動發射
   X / B           炸彈（防禦：瞬間清掉身邊彈幕）
   K / V / Enter   衝擊波大絕（攻擊：環形波往深處掃蕩，全場限用 5 次）
   滑鼠左鍵         也可以射擊（不受中文輸入法影響）
   ※ 不使用 Ctrl、Shift：在 Windows 上 Ctrl+空白鍵、Shift 會切換中英文輸入法，
     切到中文後空白鍵和數字鍵會被輸入法攔截，造成「不能射擊、不能選武器」
                   ※ 給多組替代鍵是因為部分鍵盤同時按住空白鍵與方向鍵時
                     會漏掉第 4 顆鍵（鍵盤重影），換一顆鍵就能解決
   P 暫停    F 顯示FPS    R 重新開始    ESC 離開

 ---------------------------------------------------------------
 3D 原理（三行講完）：
   攝影機在原點看向 +Z。世界座標 (x, y, z) 投影到螢幕的公式是
       螢幕x = 中心x + x * f / z
       螢幕y = 中心y + y * f / z
   f 是焦距。z 越大（越遠）除出來越小 —— 這就是近大遠小。
 ---------------------------------------------------------------
 武器系統（撿六角形武器包取得，重複撿同一把會升級）：
   1 PULSE   無限彈藥的主砲，其他武器打完一定回得來
   2 SPREAD  廣角散射，打成群小怪
   3 COMET   藍焰彗星：螺旋交纏前進、命中範圍大、可穿透 3 個敵人
   4 HOMING  自動鎖定飛彈，不用瞄準
   5 PLASMA  慢速大彈 + 範圍爆傷，清場用
   6 FIRE    一次 6 枚 3D 火焰彈，螺旋前進，威力強大

 需求： pip install pygame
================================================================
"""

import os
import sys
import math
import random
import pygame
import pygame.gfxdraw

# ---------------------------------------------------------------
# 場景選擇："antarctic" = 南極冰原（需要 numpy）   "alien" = 原本的外星地貌
# ---------------------------------------------------------------
ENVIRONMENT = "antarctic"
try:
    import numpy
except ImportError:
    numpy = None
    if ENVIRONMENT == "antarctic":
        print("[提示] 南極冰原需要 numpy：pip install numpy  —— 暫時改用外星地貌")
        ENVIRONMENT = "alien"
ICE = ENVIRONMENT == "antarctic"

# ---------------------------------------------------------------
# 基本設定
# ---------------------------------------------------------------
SCREEN_W, SCREEN_H = 1280, 720   # 16:9 寬螢幕：全螢幕時能佈滿一般螢幕，左右多看到更多場景
FULLSCREEN = True                 # 啟動就全螢幕；F11 或 Alt+Enter 可切換全螢幕 / 視窗
FPS = 60

FOCAL = 520.0              # 焦距：越大視野越窄（望遠感）
CX = SCREEN_W / 2          # 消失點
CY = SCREEN_H / 2 - 30     # 消失點/地平線高度
NEAR = 60.0                # 近裁剪面：z 小於這個值就不畫（避免除以零爆炸）
FAR = 4200.0               # 遠裁剪面

PLAYER_Z = 560.0           # 戰機所在深度（決定戰機在畫面上的大小）
SPAWN_Z = 3200.0           # 敵人生成深度
GROUND_Y = 520.0           # 地面高度（y 向下為正）

# 由投影公式反推戰機的世界座標邊界，保證機身永遠留在畫面內。
# 螢幕位移 = 世界位移 * FOCAL / PLAYER_Z，所以世界邊界 = 螢幕邊界 * PLAYER_Z / FOCAL
_SHIP_SCALE = FOCAL / PLAYER_Z
X_LIMIT = (SCREEN_W / 2 - 110) / _SHIP_SCALE
Y_TOP = -(CY - 110) / _SHIP_SCALE
Y_BOTTOM = (SCREEN_H - CY - 105) / _SHIP_SCALE

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (235, 70, 70)
GREEN = (90, 220, 130)
CYAN = (110, 230, 240)
YELLOW = (255, 210, 80)
ORANGE = (255, 150, 50)
PURPLE = (190, 120, 255)
PINK = (255, 130, 220)
GREY = (120, 130, 150)

if getattr(sys, "frozen", False):
    ASSET_DIR = os.path.dirname(sys.executable)
else:
    ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------
# 3D 數學核心
# ---------------------------------------------------------------
def project(x, y, z):
    """
    世界座標 -> 螢幕座標。
    回傳 (螢幕x, 螢幕y, 縮放比)；z 太近或太遠回傳 None。
    縮放比 = FOCAL / z，任何物件的螢幕大小都乘上它。
    """
    if z <= NEAR or z > FAR:
        return None
    s = FOCAL / z
    return CX + x * s, CY + y * s, s


def rot_x(p, a):
    """繞 X 軸旋轉（俯仰 pitch）。"""
    c, s = math.cos(a), math.sin(a)
    x, y, z = p
    return (x, y * c - z * s, y * s + z * c)


def rot_y(p, a):
    """繞 Y 軸旋轉（偏航 yaw）。"""
    c, s = math.cos(a), math.sin(a)
    x, y, z = p
    return (x * c + z * s, y, -x * s + z * c)


def rot_z(p, a):
    """繞 Z 軸旋轉（滾轉 roll）。"""
    c, s = math.cos(a), math.sin(a)
    x, y, z = p
    return (x * c - y * s, x * s + y * c, z)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def normalize(v):
    m = math.sqrt(dot(v, v))
    if m == 0:
        return (0.0, 0.0, 0.0)
    return (v[0] / m, v[1] / m, v[2] / m)


# ---------------------------------------------------------------
# 素材載入
# ---------------------------------------------------------------
def find_asset(*candidates):
    try:
        files = os.listdir(ASSET_DIR)
    except OSError:
        return None

    def norm(s):
        return s.lower().replace(" ", "").replace("_", "").replace("-", "")

    table = {norm(f): f for f in files}
    for cand in candidates:
        hit = table.get(norm(cand))
        if hit:
            return os.path.join(ASSET_DIR, hit)
    return None


def load_image(candidates, size=None, fallback_color=None):
    path = find_asset(*candidates)
    if path:
        try:
            img = pygame.image.load(path).convert_alpha()
            if size:
                img = pygame.transform.smoothscale(img, size)
            print(f"  [OK]   image  {os.path.basename(path)}")
            return img
        except pygame.error as e:
            print(f"  [FAIL] image  {os.path.basename(path)}: {e}")
    print(f"  [MISS] image  {candidates[0]}  -> 使用色塊代替")
    surf = pygame.Surface(size or (64, 64), pygame.SRCALPHA)
    pygame.draw.circle(surf, fallback_color or GREY,
                       (surf.get_width() // 2, surf.get_height() // 2),
                       surf.get_width() // 2)
    return surf


def split_footsteps(sound, volume, keep=4):
    """
    把腳步聲檔案切成一步一步的音效，讓遊戲在魔王的腳落地那一刻播放（聲音與畫面同步）。
    做法：算出音量包絡，找出「音量突然升高 10 dB 以上」的落地瞬間，每一步切到下一步落地前；
    只取前面節奏規律的幾步（這個檔案後半段是一段持續的轟鳴，不是步伐）。
    沒有 numpy 或偵測失敗時，回傳整個檔案（改為整檔循環）。
    """
    if numpy is None:
        return [sound]
    np = numpy
    try:
        sr = pygame.mixer.get_init()[0]
        a = pygame.sndarray.array(sound)
        mono = a.astype(np.float32).reshape(len(a), -1).mean(axis=1) / 32768.0
        hop = max(1, int(sr * 0.01))
        n = len(mono) // hop
        env = np.sqrt((mono[:n * hop].reshape(n, hop) ** 2).mean(axis=1))
        db = 20 * np.log10(env + 1e-9)
        on = []
        for i in range(15, n):
            if db[i] - db[i - 15:i].mean() > 10 and db[i] > -35 and (not on or i - on[-1] > 40):
                on.append(i)
        if len(on) < 2:
            return [sound]
        steps = []
        pre = int(0.03 * sr)
        for k in range(min(keep, len(on) - 1)):
            s0 = max(0, on[k] * hop - pre)
            s1 = on[k + 1] * hop - pre
            seg = a[s0:s1].astype(np.float32)
            fade = np.ones(len(seg), np.float32)
            fi, fo = int(0.005 * sr), int(0.08 * sr)          # 前後淡入淡出，避免爆音
            fade[:fi] = np.linspace(0, 1, fi)
            fade[-fo:] = np.linspace(1, 0, fo)
            seg = (seg * (fade[:, None] if seg.ndim > 1 else fade)).astype(a.dtype)
            snd = pygame.sndarray.make_sound(np.ascontiguousarray(seg))
            snd.set_volume(volume)
            steps.append(snd)
        print(f"  [OK]   腳步聲切成 {len(steps)} 步（步距約 {np.diff(on).mean() * 0.01:.1f} 秒）")
        return steps
    except Exception as e:
        print(f"  [FAIL] 腳步聲切割失敗，改為整檔循環：{e}")
        return [sound]


def boost_sound(sound, gain):
    """
    把音效放大到超過 pygame 音量上限（1.0）：直接放大波形，再用柔性限幅器圓滑地壓住峰值，
    避免硬破音。大部分聲音照實放大，只有最強的瞬間被壓縮。沒有 numpy 時退回最大音量 1.0。
    """
    if gain <= 1.0 or numpy is None:
        sound.set_volume(min(1.0, gain))
        return sound
    np = numpy
    try:
        a = pygame.sndarray.array(sound)
        full = float(np.iinfo(a.dtype).max) if a.dtype.kind == "i" else 1.0
        x = a.astype(np.float32) / full * gain
        T = 0.75                                        # 限幅門檻：低於滿刻度 75% 的聲音不受影響
        mag = np.abs(x)
        over = mag > T
        x[over] = np.sign(x[over]) * (T + (1 - T) * np.tanh((mag[over] - T) / (1 - T)))
        out = pygame.sndarray.make_sound(np.ascontiguousarray((x * full).astype(a.dtype)))
        out.set_volume(1.0)
        return out
    except Exception as e:
        print(f"  [FAIL] 音效放大失敗，改用最大音量：{e}")
        sound.set_volume(1.0)
        return sound


def slice_and_boost(sound, start_s, gain):
    """從 start_s 秒開始截取，再放大 gain 倍（超過 1.0 的部分用柔性限幅器圓滑壓住）。"""
    np = numpy
    sr = pygame.mixer.get_init()[0]
    a = pygame.sndarray.array(sound)[int(start_s * sr):]
    part = pygame.sndarray.make_sound(np.ascontiguousarray(a))
    return boost_sound(part, gain)


def load_sound(candidates, volume=0.5):
    path = find_asset(*candidates)
    if path:
        try:
            snd = pygame.mixer.Sound(path)
            snd.set_volume(volume)
            print(f"  [OK]   sound  {os.path.basename(path)}")
            return snd
        except pygame.error as e:
            print(f"  [FAIL] sound  {os.path.basename(path)}: {e}")
    print(f"  [MISS] sound  {candidates[0]}")
    return None


def slice_explosion_sheet(path, frame_size):
    """explosion_graph.jpg 是 3x3 連續圖；先減掉深色底，繪製時用加亮模式疊上。"""
    sheet = pygame.image.load(path).convert()
    sw, sh = sheet.get_size()
    fw, fh = sw // 3, sh // 3
    bg = sheet.get_at((2, 2))[:3]
    frames = []
    for row in range(3):
        for col in range(3):
            f = sheet.subsurface(pygame.Rect(col * fw, row * fh, fw, fh)).copy()
            f = pygame.transform.smoothscale(f, (frame_size, frame_size))
            f.fill((*bg, 0), special_flags=pygame.BLEND_RGB_SUB)
            frames.append(f)
    return frames


EXPLOSION_TIMING = (2, 2, 3, 3, 4, 4, 5, 6, 8)   # 每格停留幀數：開頭閃光快、中段火球停留、結尾煙霧慢慢散
EXPLOSION_FLIPS = {}          # 原始畫格清單的 id -> 旋轉 180° 的版本（每次爆炸隨機選一種，看起來不重複）
EXPLOSION_ALPHA = False       # True = 已正確去背，用一般透明混合繪製


def process_explosion_sheet(path, master=512):
    """
    把 explosion_graph.jpg（3x3 連續圖、深紅底）正確去背並做成動畫畫格：
      1. 顏色轉透明（color-to-alpha）：已知背景色，對每個像素反推「多不透明、原本是什麼顏色」，
         疊回背景剛好還原。火焰不透明、外圍柔光半透明、煙團保留原本的深紅色。
      2. 逐格重新置中：原圖各格的爆炸中心並沒有對齊，不修正的話播放時會上下亂跳。
      3. 每個像素只歸屬離它最近的那一格，相鄰格的光暈不會闖進來。
      4. 半透明的外圍光暈做非線性淡化：在亮的雪地上不會變成一圈髒髒的圓盤。
    所有畫格用同一個比例，爆炸由小變大的節奏與原圖一致。
    """
    np = numpy
    sheet = pygame.image.load(path).convert()
    W, H = sheet.get_size()
    k = 2250 / max(W, H)
    if k < 1:
        sheet = pygame.transform.smoothscale(sheet, (int(W * k), int(H * k)))
    a = pygame.surfarray.array3d(sheet).astype(np.float32) / 255.0          # (x, y, 3)
    bg = a[3, 3].copy()
    # (1) 光暈：低飽和度的褐色漸層才是真正半透明 —— 用顏色轉透明反解，並大幅淡化
    up = np.where(a > bg, (a - bg) / np.maximum(1 - bg, 1e-6), 0)
    dn = np.where(a < bg, (bg - a) / np.maximum(bg, 1e-6), 0)
    raw = np.clip(np.maximum(up, dn).max(axis=2), 0, 1)
    glow_fg = np.clip((a - bg) / np.maximum(raw[..., None], 1e-3) + bg, 0, 1)
    glow_a = raw * raw * 0.65
    # (2) 實心物體：火焰、煙團、碎片。飽和度高或很亮的地方，再「閉合」把內部的深色陰影補滿。
    #     這部分完全不透明、直接用原圖顏色 —— 插畫裡刻意畫的深紅陰影才不會被當成半透明。
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1e-3)
    # 量測原圖得到的分界：同樣亮度下，光暈偏橘褐（綠/紅比 0.28 以上），煙團陰影是純暗紅（約 0.2）
    gr = a[..., 1] / np.maximum(a[..., 0], 1e-3)
    obj = ((sat > 0.9) & (gr < 0.27) & (mx > 0.30)) | ((sat > 0.78) & (mx > 0.55)) | (mx > 0.86)

    def dilate(m, r):
        out = m.copy()
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if 0 < dx * dx + dy * dy <= r * r:
                    out |= np.roll(np.roll(m, dx, 0), dy, 1)
        return out

    obj = ~dilate(~dilate(obj, 2), 2)                                        # 閉合：補滿小縫隙
    # 光暈只保留在火焰周圍：在縮小 4 倍的遮罩上擴張再放大回來（快很多），
    # 離火焰太遠的光暈圓盤與它邊緣那道描邊就會淡出
    small = dilate(obj[::4, ::4], 3)
    near = np.repeat(np.repeat(small, 4, 0), 4, 1)[:obj.shape[0], :obj.shape[1]].astype(np.float32)
    near = sum(np.roll(np.roll(near, dx, 0), dy, 1) for dx in (-4, 0, 4) for dy in (-4, 0, 4)) / 9.0
    glow_a = glow_a * near
    objf = obj.astype(np.float32)
    objf = sum(np.roll(np.roll(objf, dx, 0), dy, 1) for dx in (-1, 0, 1) for dy in (-1, 0, 1)) / 9.0  # 邊緣抗鋸齒
    alpha = np.maximum(objf, glow_a * (1 - objf))
    fg = a * objf[..., None] + glow_fg * (1 - objf[..., None])
    fg = np.where(alpha[..., None] < 0.03, np.array([1.0, 0.62, 0.3], np.float32), fg)  # 透明處填暖色，縮放時邊緣不發黑
    alpha = np.where(alpha < 0.03, 0, alpha)
    w, h = alpha.shape
    cw, ch = w / 3.0, h / 3.0
    centers = []
    for row in range(3):
        for col in range(3):
            x0, y0 = int(col * cw), int(row * ch)
            sub = alpha[x0:int(x0 + cw), y0:int(y0 + ch)]
            core = sub > 0.6
            if core.sum() < 50:
                core = sub > 0.2
            xs, ys = np.nonzero(core)
            centers.append((x0 + xs.mean(), y0 + ys.mean()))
    R = int(min(cw, ch) * 0.465)
    frames = []
    for i, (cx, cy) in enumerate(centers):
        sx0, sy0 = int(cx) - R, int(cy) - R
        A = np.zeros((2 * R, 2 * R), np.float32)
        F = np.zeros((2 * R, 2 * R, 3), np.float32)
        xa, xb = max(0, sx0), min(w, sx0 + 2 * R)
        ya, yb = max(0, sy0), min(h, sy0 + 2 * R)
        A[xa - sx0:xb - sx0, ya - sy0:yb - sy0] = alpha[xa:xb, ya:yb]
        F[xa - sx0:xb - sx0, ya - sy0:yb - sy0] = fg[xa:xb, ya:yb]
        gx, gy = np.mgrid[0:2 * R, 0:2 * R].astype(np.float32)
        gx += sx0
        gy += sy0
        dself = np.hypot(gx - cx, gy - cy)
        for j, (ox, oy) in enumerate(centers):              # 只保留離自己中心最近的像素
            if j != i:
                A *= (dself <= np.hypot(gx - ox, gy - oy) + 1)
        A *= np.clip((R - dself) / (0.07 * R), 0, 1)
        surf = pygame.Surface((2 * R, 2 * R), pygame.SRCALPHA)
        pygame.surfarray.pixels3d(surf)[:] = (F * 255).astype(np.uint8)
        pygame.surfarray.pixels_alpha(surf)[:] = (A * 255).astype(np.uint8)
        frames.append(pygame.transform.smoothscale(surf, (master, master)))
    return frames


_GLOW_BASE = {}        # 半徑 -> 灰階光暈模板
_GLOW_CACHE = {}       # (半徑, 顏色) -> 著色後的光暈
_SCALE_CACHE = {}      # (圖片id, 尺寸) -> 縮放後的圖


def _glow_base(radius):
    """灰階光暈模板。只會依「量化後的半徑」建立少數幾張，之後重複使用。"""
    b = _GLOW_BASE.get(radius)
    if b is None:
        b = pygame.Surface((radius * 2, radius * 2))
        for i in range(radius, 0, -1):
            t = 1 - i / radius
            v = int(255 * t * t)
            pygame.draw.circle(b, (v, v, v), (radius, radius), i)
        _GLOW_BASE[radius] = b
    return b


def glow(radius, color):
    """
    取得指定半徑與顏色的光暈。
    效能關鍵：半徑與顏色都先量化，否則連續變化的深度會讓快取永遠 miss，
    每幀重畫上百萬個圓 —— 這是這支程式最大的效能陷阱。
    """
    rq = max(6, min(132, (int(radius) // 6) * 6))
    cq = (color[0] // 32 * 32, color[1] // 32 * 32, color[2] // 32 * 32)
    key = (rq, cq)
    g = _GLOW_CACHE.get(key)
    if g is None:
        g = _glow_base(rq).copy()
        g.fill(cq, special_flags=pygame.BLEND_RGB_MULT)   # 用乘法著色，不用重畫圓
        _GLOW_CACHE[key] = g
    return g


_GLOW_ALPHA = {}


def glow_alpha(radius, color):
    """
    雪地版光暈：帶透明度的顏色圈，用一般混合疊上去。
    加亮混合在暗背景很漂亮，但疊在接近白色的雪上等於什麼都沒加。
    """
    rq = max(6, min(132, (int(radius) // 6) * 6))
    cq = (color[0] // 32 * 32, color[1] // 32 * 32, color[2] // 32 * 32)
    key = (rq, cq)
    g = _GLOW_ALPHA.get(key)
    if g is None:
        peak = max(cq) or 1
        g = pygame.Surface((rq * 2, rq * 2), pygame.SRCALPHA)
        g.fill((min(255, cq[0] * 255 // peak), min(255, cq[1] * 255 // peak),
                min(255, cq[2] * 255 // peak), 0))
        a = pygame.surfarray.array3d(_glow_base(rq))[:, :, 0].astype(float)
        pygame.surfarray.pixels_alpha(g)[:] = numpy.clip(a * (peak / 255) * 1.3, 0, 255).astype("uint8")
        _GLOW_ALPHA[key] = g
    return g


def blit_glow(surf, center, radius, color):
    if ICE:
        g = glow_alpha(radius, color)
        surf.blit(g, (center[0] - g.get_width() // 2, center[1] - g.get_height() // 2))
        return
    g = glow(radius, color)
    surf.blit(g, (center[0] - g.get_width() // 2, center[1] - g.get_height() // 2),
              special_flags=pygame.BLEND_RGB_ADD)


def to_alpha_frames(frames):
    """把黑底的爆炸影格轉成帶透明度的版本：越亮越不透明。"""
    out = []
    for f in frames:
        rgb = pygame.surfarray.array3d(f).astype(float)
        lum = rgb.max(axis=2)
        s = pygame.Surface(f.get_size(), pygame.SRCALPHA)
        col = numpy.clip(rgb / numpy.maximum(lum, 1)[..., None] * 255, 0, 255)
        pygame.surfarray.pixels3d(s)[:] = col.astype("uint8")
        pygame.surfarray.pixels_alpha(s)[:] = numpy.clip(lum * 1.5, 0, 255).astype("uint8")
        out.append(s)
    return out


def scaled(img, size, smooth=True):
    """
    依深度縮放 billboard。

    三段式策略，是效能與記憶體的折衷：
      1. 小尺寸  -> 量化後快取（最常用，命中率最高）
      2. 大尺寸  -> 不快取。一張 900x900 的表面就要 3MB，
                   快取幾十張記憶體直接失控，寧可每幀重算。
      3. 爆炸等發光物 -> 用 scale 而非 smoothscale。
                   火光本來就是模糊的亮塊，差別看不出來，但快好幾倍。
    """
    size = max(2, min(1100, size))
    if size > 420:
        # 超過這個尺寸代表物件就貼在鏡頭前，只會停留幾幀，
        # 用快速縮放換取穩定幀率是划算的取捨。
        return pygame.transform.scale(img, (size, size))
    q = size if size <= 24 else (size // 3) * 3
    key = (id(img), q, smooth)
    s = _SCALE_CACHE.get(key)
    if s is None:
        if len(_SCALE_CACHE) > 1200:
            _SCALE_CACHE.clear()
        s = (pygame.transform.smoothscale if smooth else pygame.transform.scale)(img, (q, q))
        _SCALE_CACHE[key] = s
    return s


# ---------------------------------------------------------------
# 3D 星流（往攝影機衝來的星點，拉出速度線）
# ---------------------------------------------------------------
class StarField3D:
    def __init__(self, count=220):
        self.stars = [self._new(random.uniform(NEAR, FAR)) for _ in range(count)]

    def _new(self, z=None):
        return [random.uniform(-2600, 2600),
                random.uniform(-1500, 260),
                z if z is not None else FAR]

    def update(self, speed):
        for s in self.stars:
            s[2] -= speed
            if s[2] <= NEAR + 10:
                s[0] = random.uniform(-2600, 2600)
                s[1] = random.uniform(-1500, 260)
                s[2] = FAR

    def draw(self, surf, speed):
        for x, y, z in self.stars:
            p = project(x, y, z)
            if not p:
                continue
            sx, sy, sc = p
            p2 = project(x, y, z + speed * 3)
            b = min(255, int(40 + 900 * sc))
            col = (b, b, min(255, b + 30))
            if p2 and sc > 0.25:
                pygame.draw.line(surf, col, (sx, sy), (p2[0], p2[1]), 1)
            else:
                r = max(1, int(sc * 2.2))
                pygame.draw.circle(surf, col, (int(sx), int(sy)), r)


# ---------------------------------------------------------------
# 外星球地表（透視網格 + 地平線）
# ---------------------------------------------------------------
TRAVEL = 0.0      # 已飛行距離（模組層級，讓敵人與戰機共用同一份地形）


ACTIVE_TERRAIN = None   # 冰原地形建立後會掛在這裡


def ground_at(x, z):
    """取得世界座標 (x, z) 處的地面高度，已計入飛行捲動。"""
    if ACTIVE_TERRAIN is not None:
        return ACTIVE_TERRAIN.height_at(x, z)
    return terrain_height(x, z + TRAVEL)


def terrain_height(x, z):
    """
    地形高度場：三個不同頻率的正弦波疊加。
    低頻決定大山脈走向，中頻決定丘陵，高頻加上細碎起伏 ——
    這是程序化地形最基本也最有效的做法（分形雜訊的簡化版）。
    回傳世界座標的 y（記住 y 向下為正，所以值越小代表山越高）。
    """
    return (GROUND_Y
            - 150.0 * math.sin(x * 0.0016 + z * 0.0011)
            - 70.0 * math.sin(x * 0.0041 - z * 0.0026 + 1.7)
            - 34.0 * math.sin(x * 0.0093 + z * 0.0061 + 0.4))


class Terrain:
    """
    外星球地表：真正的 3D 高度場網格，不是平面。
    每一格四個角都去取樣高度，投影後填色 ——
    山脊會遮住山谷、越遠越融入天色，這是 3D 縱深感的主要來源。
    """
    COL_X = [i * 370.0 for i in range(-7, 8)]          # 橫向取樣位置（要夠寬，否則畫面邊緣會露出網格邊界）
    ROW_Z = [NEAR + 40 + i * 230.0 for i in range(16)]  # 縱向取樣位置

    def __init__(self):
        self.travel = 0.0        # 已飛行距離，用來捲動地形
        self.horizon = self._make_horizon()
        self.ridges = self._make_ridges()

    def _make_horizon(self):
        h = 150
        surf = pygame.Surface((SCREEN_W, h), pygame.SRCALPHA)
        for i in range(h):
            t = i / h
            surf_col = (int(70 + 60 * t), int(20 + 20 * t), int(90 + 70 * t))
            pygame.draw.line(surf, (*surf_col, int(26 * t ** 2)), (0, i), (SCREEN_W, i))
        return surf

    def _make_ridges(self):
        surf = pygame.Surface((SCREEN_W, 150), pygame.SRCALPHA)
        rng = random.Random(1234)
        for col, amp, base in [((42, 24, 68), 52, 112), ((26, 14, 46), 84, 140)]:
            pts = [(0, 150)]
            x = 0
            while x < SCREEN_W:
                x += rng.randint(28, 70)
                pts.append((x, base - rng.randint(0, amp)))
            pts.append((SCREEN_W, 150))
            pygame.draw.polygon(surf, col, pts)
        return surf

    def height_at(self, x, z):
        return ground_at(x, z)

    def update(self, speed):
        global TRAVEL
        self.travel += speed
        TRAVEL = self.travel

    def draw(self, surf):
        hy = int(CY)
        surf.blit(self.horizon, (0, hy - 150), special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(self.ridges, (0, hy - 150))

        # 先把整張網格的頂點算好，避免重複計算相鄰格共用的角
        grid = []
        for z in self.ROW_Z:
            row = []
            for x in self.COL_X:
                y = self.height_at(x, z)
                row.append((y, project(x, y, z)))
            grid.append(row)

        # 由遠而近畫（畫家演算法），近的山脊自然蓋住遠的山谷
        for r in range(len(self.ROW_Z) - 2, -1, -1):
            z_near = self.ROW_Z[r]
            fog = max(0.0, min(1.0, 1.0 - z_near / 3400.0))    # 越遠越淡
            for c in range(len(self.COL_X) - 1):
                p00 = grid[r][c][1]
                p01 = grid[r][c + 1][1]
                p10 = grid[r + 1][c][1]
                p11 = grid[r + 1][c + 1][1]
                if not (p00 and p01 and p10 and p11):
                    continue

                # 視錐剔除：近處的網格有大半在畫面外，不剔除等於白畫一半的多邊形。
                # 這是整支程式最有效的單項優化。
                x0 = p00[0]
                x1 = p01[0]
                if x1 < x0:
                    x0, x1 = x1, x0
                if x1 < -40 or x0 > SCREEN_W + 40:
                    continue
                ytop = p00[1] if p00[1] < p01[1] else p01[1]
                ybot = p10[1] if p10[1] > p11[1] else p11[1]
                if ybot < -40 or ytop > SCREEN_H + 40:
                    continue

                # 高度越高（y 越小）顏色越亮，做出山頂受光的感覺
                avg_y = (grid[r][c][0] + grid[r][c + 1][0]
                         + grid[r + 1][c][0] + grid[r + 1][c + 1][0]) * 0.25
                lift = (GROUND_Y + 120 - avg_y) / 380.0
                lift = 0.0 if lift < 0.0 else (1.0 if lift > 1.0 else lift)
                inv = 1.0 - fog
                col = (int((34 + 96 * lift) * fog + 34 * inv),
                       int((44 + 124 * lift) * fog + 16 * inv),
                       int((76 + 150 * lift) * fog + 56 * inv))
                pygame.draw.polygon(surf, col, [(p00[0], p00[1]), (p01[0], p01[1]),
                                                (p11[0], p11[1]), (p10[0], p10[1])])
                # 網格線：保留原本的科幻感，但只畫近處以免雜亂
                if fog > 0.45:
                    line = tuple(min(255, int(c_ * 1.7) + 26) for c_ in col)
                    pygame.draw.line(surf, line, (p00[0], p00[1]), (p01[0], p01[1]), 1)
                    pygame.draw.line(surf, line, (p00[0], p00[1]), (p10[0], p10[1]), 1)


# ---------------------------------------------------------------
# 南極冰原地形（ENVIRONMENT = "antarctic" 時使用）
# ---------------------------------------------------------------
class IceTerrain:
    """
    依照真實冰川地形學程序生成的南極地貌：
      - 中央冰河谷：藍冰與橫向冰裂縫，偶有「壓力脊」橫越河谷（低飛要拉升）
      - 兩側高原：風蝕雪脊（sastrugi）紋理
      - 外側岩峰（nunatak）：陡坡露出黑色岩石
      - 依太陽方向做光照與「真實投影的山影」，陰影中的雪呈藍色
    全部在啟動時用 numpy 預先算好；每幀只做投影與填色。

    真實資料接口（放在素材資料夾就會自動採用）：
      ice_heightmap.png  灰階高程圖（越亮越高），例如由 REMA 轉出
      ice_texture.jpg    表面材質，例如 LIMA 衛星影像的冰原區塊
    """
    CELL = 20.0                    # 高程圖解析度（世界單位 / 格）
    S = 120.0                      # 網格間距（= 6 格）
    STEP = 6
    NQX = 72                       # 寬螢幕視野較寬：地形左右加寬，遠處兩側才不會超出範圍                       # 橫向網格數
    NKZ = 120                      # 縱向網格數（一個循環）
    XMIN = -NQX * S / 2
    ZLEN = NKZ * S                 # 14400：地形每飛這麼遠就無縫重複
    NX = NQX * STEP
    NZ = NKZ * STEP
    SUN = normalize((0.42, -0.5, 0.76))      # 右前方、仰角約 30° 的太陽
    HAZE = (204, 220, 235)                  # 遠方大氣霧色（與天空地平線同色才不會有接縫）

    # 光線投射的內部解析度：算完再平滑放大到全螢幕。
    # 400x300 是實測的甜蜜點 —— 再高就吃掉 60fps 的預算。
    RW, RH, SLICES = 416, 234, 170          # 內部解析度與畫面同為 16:9，放大後才不會變形；實測魔王戰 96% 的幀在 60fps 內

    def __init__(self):
        self.travel = 0.0
        np = numpy
        up, valley, dist = self._build_height()
        up = self._smooth(up, 2)                      # 去掉單格尖刺：光線投射會把它放大成一根細針
        hm = GROUND_Y + 40.0 - up                      # y 向下為正
        color = self._build_color(hm, up, valley, dist)
        self.hm = hm.astype(np.float32)
        # 每個格點和右邊鄰居打包成一個複數：雙線性取樣一次讀取就拿到兩個值（4 次讀取 -> 2 次）
        self.hmc = (self.hm[:, :-1] + 1j * self.hm[:, 1:]).astype(np.complex64)
        self.hm_list = self.hm.tolist()                # 碰撞查詢用（純 Python 取值比 numpy 快）
        # 顏色表在啟動時用雙線性放大四倍，之後每幀只要「取最近的一格」：
        # 畫面跟每幀做雙線性一樣平滑，但省掉四次浮點取樣（原本佔 40% 的時間）。
        c4 = np.clip(self._upsample(color.astype(np.float32), 4), 0, 255).astype(np.uint32)
        # RGB 打包成一個 32 位元整數：每個像素只要讀一次記憶體（原本 R、G、B 各讀一次）
        self.col4p = (c4[..., 0] << 16) | (c4[..., 1] << 8) | c4[..., 2]
        self._prepare_rays()
        self.sky_lr = None
        self.backdrop = self._make_backdrop()
        self.frame = pygame.Surface((self.RW, self.RH), 0, 32)
        self.quality = "high"                          # 目前畫質（自動畫質調整會讀這個值）

    @staticmethod
    def _smooth(a, passes=1):
        """[1,2,1] 平滑濾波：z 方向週期性（地形會循環），x 方向邊緣延伸。"""
        np = numpy
        for _ in range(passes):
            a = (np.roll(a, 1, 0) + 2 * a + np.roll(a, -1, 0)) * 0.25
            p = np.pad(a, ((0, 0), (1, 1)), mode="edge")
            a = (p[:, :-2] + 2 * p[:, 1:-1] + p[:, 2:]) * 0.25
        return a

    @staticmethod
    def _upsample(a, f):
        """真正的雙線性放大（不依賴 scipy，玩家電腦只需要 numpy）。"""
        np = numpy
        nz, nx = a.shape[:2]
        zi = np.arange(nz * f) / f
        z0 = np.floor(zi).astype(np.int64)
        tz = (zi - z0).astype(np.float32)[:, None, None]
        a = a[z0 % nz] * (1 - tz) + a[(z0 + 1) % nz] * tz          # z 方向循環
        xi = np.clip(np.arange(nx * f) / f, 0, nx - 1.0001)
        x0 = np.floor(xi).astype(np.int64)
        tx = (xi - x0).astype(np.float32)[None, :, None]
        return a[:, x0] * (1 - tx) + a[:, x0 + 1] * tx

    def _prepare_rays(self):
        """
        固定不變的部分先算好：每一「層」深度 z、每一欄對應的世界 x。
        攝影機不轉動，所以只有「往前飛」會變，每幀只需要重算 z 方向的取樣。
        """
        np = numpy
        RW, RH, S = self.RW, self.RH, self.SLICES
        k = RW / SCREEN_W
        self.rcx, self.rcy, self.rf = CX * k, CY * k, FOCAL * k
        # 深度層用等比級數：近處密、遠處疏（遠處一層覆蓋的像素本來就少）
        self.zs = (170.0 * (4150.0 / 170.0) ** (np.arange(S) / (S - 1))).astype(np.float32)
        xs = (np.arange(RW)[None, :] + 0.5 - self.rcx) * self.zs[:, None] / self.rf
        fx = np.clip((xs - self.XMIN) / self.CELL, 0, self.NX - 1.001)
        self.ix0 = fx.astype(np.int64)
        self.ix1 = self.ix0 + 1
        self.tx = (fx - self.ix0).astype(np.float32)
        self.ix4 = np.clip(np.round(fx * 4).astype(np.int64), 0, self.NX * 4 - 1)
        f = 1.0 - np.exp(-self.zs / 4300.0)
        f = f * f * (3 - 2 * f)
        e = np.clip((self.zs - 3300.0) / 800.0, 0, 1)
        f = np.maximum(f, e * e * (3 - 2 * e))          # 最遠處完全融入霧色
        self.fog = f[:, None, None].astype(np.float32)
        self.hazefog = (np.array(self.HAZE, np.float32) * self.fog).astype(np.float32)
        # 霧改用整數運算：霧濃度只跟深度有關，預先換成 0~256 的整數倍率（避免浮點運算被升級成雙精度）
        self.f1i = np.round((1 - f) * 256).astype(np.uint32)[:, None]
        hz = np.round(np.array(self.HAZE, np.float64)[None, :] * f[:, None] * 256).astype(np.uint32)
        self.hzr, self.hzg, self.hzb = hz[:, :1], hz[:, 1:2], hz[:, 2:3]
        self.colidx = np.arange(RW)
        self.rowidx = np.arange(RH)[:, None]

    # 畫質等級：(內部寬, 內部高, 深度層數)
    QUALITY = {"high": (416, 234, 170), "medium": (352, 198, 150), "low": (288, 162, 120)}

    def set_quality(self, level):
        """切換光線投射的內部解析度（電腦跑不動時自動降級用）。"""
        self.RW, self.RH, self.SLICES = self.QUALITY[level]
        self.quality = level
        self._prepare_rays()
        self.frame = pygame.Surface((self.RW, self.RH), 0, 32)
        if getattr(self, "_sky_src", None) is not None:
            self.set_sky(self._sky_src)

    def set_sky(self, sky_surface):
        """天空（含遠山剪影）縮到內部解析度，之後跟地形一起合成。"""
        self._sky_src = sky_surface
        sky = sky_surface.copy()
        sky.blit(self.backdrop, (0, int(CY) - self.backdrop.get_height() + 6))
        small = pygame.transform.smoothscale(sky, (self.RW, self.RH))
        sk = pygame.surfarray.array3d(small).swapaxes(0, 1).astype(numpy.uint32)   # (RH, RW, 3)
        self.sky_lr = self._pack(sk[..., 0], sk[..., 1], sk[..., 2])

    def _pack(self, r, g, b):
        """依畫布實際的像素格式打包 RGB，打包結果可以直接寫進畫布。"""
        rs, gs, bs, _ = self.frame.get_shifts()
        return (r.astype(numpy.uint32) << rs) | (g.astype(numpy.uint32) << gs) | \
               (b.astype(numpy.uint32) << bs)

    # ---------- 地形高度 ----------
    def _fractal(self, beta, seed, band=None):
        """頻譜合成的分形雜訊（週期性，可無縫拼接）。beta 越大越平滑。"""
        np = numpy
        r = np.random.default_rng(seed)
        kz = np.fft.fftfreq(self.NZ)[:, None]
        kx = np.fft.rfftfreq(self.NX)[None, :]
        k = np.sqrt(kz ** 2 + kx ** 2)
        k[0, 0] = 1.0
        amp = k ** (-beta / 2)
        if band:                                         # 只保留某個尺度的起伏
            lo, hi = band
            amp *= np.exp(-((np.log(k) - np.log((lo * hi) ** 0.5)) / np.log(hi / lo)) ** 2 * 2)
        spec = (r.standard_normal(amp.shape) + 1j * r.standard_normal(amp.shape)) * amp
        spec[0, 0] = 0
        f = np.fft.irfft2(spec, s=(self.NZ, self.NX))
        return f / (np.abs(f).max() + 1e-9)

    def _load_real_heightmap(self):
        path = find_asset("ice_heightmap.png", "ice_heightmap.jpg")
        if not path:
            return None
        try:
            img = pygame.image.load(path)
            a = pygame.surfarray.array3d(img).mean(axis=2).T.astype(float)   # (h, w)
            a = self._fit(a)
            a = (a - a.min()) / (a.max() - a.min() + 1e-9)
            print(f"  [OK]   真實高程圖 {os.path.basename(path)}")
            return a
        except Exception as e:
            print(f"  [FAIL] 高程圖 {e}")
            return None

    def _fit(self, a):
        """把任意尺寸影像縮放到地形網格，並上下鏡像拼接成可無縫循環。"""
        np = numpy
        h, w = a.shape[:2]
        zi = (np.arange(self.NZ // 2) * h / (self.NZ // 2)).astype(int)
        xi = (np.arange(self.NX) * w / self.NX).astype(int)
        a = a[zi][:, xi]
        return np.concatenate([a, a[::-1]], axis=0)

    def _build_height(self):
        np = numpy
        z = (np.arange(self.NZ) * self.CELL)[:, None]
        x = (self.XMIN + np.arange(self.NX) * self.CELL)[None, :]
        tau = 2 * np.pi
        # 冰河谷中心線（整數個週期 = 無縫循環）。擺幅刻意小於戰機的活動範圍，
        # 保證飛行通道永遠在谷底，不會一頭撞進山壁。
        xc = 150 * np.sin(tau * z / self.ZLEN * 2) + 60 * np.sin(tau * z / self.ZLEN * 5 + 1.3)
        dist = np.abs(x - xc)

        def smooth(e0, e1, v):
            t = np.clip((v - e0) / (e1 - e0), 0, 1)
            return t * t * (3 - 2 * t)

        valley = 1 - smooth(720, 1250, dist)            # 1 = 谷底, 0 = 高原
        base = self._fractal(2.4, 1)
        detail = self._fractal(1.6, 2)
        ridged = 1 - np.abs(self._fractal(1.8, 3, band=(0.005, 0.028)))
        ridged = ridged ** 2.2                          # 脊狀多重分形：有稜有角但不是細針
        # 山壁從距中線 820 起拔高。戰機離中線最多約 610（活動範圍 398 + 河谷擺幅 210），
        # 所以山再近也不會長進飛行通道。
        mount = 1150 * ridged * smooth(820, 1700, dist) * (0.65 + 0.35 * base)

        real = self._load_real_heightmap()
        if real is not None:
            mount = 1100 * real * smooth(820, 1700, dist)   # 真實高程只用在河谷兩側

        plateau = 95 + 70 * base + 12 * detail
        floor = 18 * detail
        if real is not None:
            # 真實地形也用在谷底與高原，只是幅度壓小，讓飛行通道保持可飛
            plateau = 70 + 210 * real + 8 * detail
            floor = 16 * detail + 90 * (real - real.mean())
        # 壓力脊：冰河流動受阻時擠出的橫向冰脊，會侵入飛行高度
        bumps = np.zeros_like(dist)
        for zr, a_ in ((1800, 270), (5600, 390), (9300, 320), (12600, 410)):
            dz = (z - zr + self.ZLEN / 2) % self.ZLEN - self.ZLEN / 2
            bumps += a_ * np.exp(-(dz / 230) ** 2) * (0.8 + 0.2 * np.sin(x / 90 + zr))
        up = valley * (floor + bumps) + (1 - valley) * plateau + mount
        return up, valley, dist

    # ---------- 表面材質與光照 ----------
    def _build_color(self, hm, up, valley, dist):
        np = numpy
        C = self.CELL
        gz, gx = np.gradient(hm, C, C)
        slope = np.sqrt(gx ** 2 + gz ** 2)
        z = (np.arange(self.NZ) * C)[:, None]
        x = (self.XMIN + np.arange(self.NX) * C)[None, :]

        snow = np.array([0.93, 0.955, 0.985])
        blue_ice = np.array([0.60, 0.79, 0.92])
        crevasse = np.array([0.22, 0.42, 0.62])
        rock = np.array([0.23, 0.22, 0.235])

        patch = self._fractal(1.9, 5)
        streak = self._fractal(1.2, 6)                  # 風蝕雪脊的細紋
        alb = np.broadcast_to(snow, hm.shape + (3,)).copy()
        alb *= (0.965 + 0.05 * streak)[..., None]
        # 谷底藍冰（風把表層雪吹走，露出老冰）
        bi = valley * np.clip((patch + 0.1) * 2.2, 0, 1)
        alb = alb * (1 - bi[..., None]) + blue_ice * bi[..., None]
        # 冰裂縫：谷壁附近應力大的地方，橫向排列
        zone = valley * np.clip((dist - 300) / 500, 0, 1)      # 離河谷中線越遠、越靠谷壁，裂縫越多
        lines = (np.abs(np.sin(z / 55 + 2.5 * patch)) < 0.12).astype(float)
        cr = zone * lines * 0.8
        alb = alb * (1 - cr[..., None]) + crevasse * cr[..., None]
        # 岩石：太陽曬不住雪的陡坡
        rk = np.clip((slope - 0.42) / 0.45, 0, 1) * np.clip((up - 220) / 200, 0, 1)
        alb = alb * (1 - rk[..., None]) + rock * rk[..., None]

        # 真實衛星材質：用它的明暗與色偏調變程序材質
        tpath = find_asset("ice_texture.jpg", "ice_texture.png", "ice_texture.jpeg")
        if tpath:
            try:
                img = pygame.image.load(tpath)
                t = self._fit(pygame.surfarray.array3d(img).transpose(1, 0, 2).astype(float) / 255)
                lum = t.mean(axis=2)
                alb *= np.clip(1 + 0.25 * (lum - lum.mean()) / (lum.std() + 1e-6), 0.6, 1.3)[..., None]
                alb = alb * 0.72 + t * 0.28
                print(f"  [OK]   真實表面材質 {os.path.basename(tpath)}")
            except Exception as e:
                print(f"  [FAIL] 材質 {e}")

        # 光照：法向量 = (dy/dx, -1, dy/dz)
        n = np.stack([gx, -np.ones_like(gx), gz], axis=-1)
        n /= np.linalg.norm(n, axis=-1, keepdims=True)
        lam = np.clip(n @ np.array(self.SUN), 0, 1)

        # 山影：沿太陽方向逐格往前看，只要前方地形比光線高就在陰影裡
        sx, sy, sz = self.SUN
        horiz = (sx * sx + sz * sz) ** 0.5
        dxs, dzs = sx / horiz, sz / horiz
        rise = -sy / horiz * C                          # 每前進一格光線上升多少
        lit = np.ones_like(hm)
        for k in range(1, 90):
            ox, oz = int(round(k * dxs)), int(round(k * dzs))
            ahead = np.roll(np.roll(hm, -oz, axis=0), -ox, axis=1)
            dist_ = (ox * ox + oz * oz) ** 0.5
            lit = np.minimum(lit, np.clip((ahead - hm + rise * dist_) / 30 + 1, 0, 1))
        sky = np.array([0.53, 0.63, 0.80])
        sun = np.array([1.0, 0.96, 0.88])
        light = sky * 0.86 + sun * (lam * lit)[..., None] * 1.0
        return np.clip(alb * light * 0.95 * 255, 0, 255)

    # ---------- 遠景 ----------
    def _make_backdrop(self):
        """地平線外的遠山剪影，顏色逐層融入大氣霧色。"""
        h = 170
        s = pygame.Surface((SCREEN_W, h), pygame.SRCALPHA)
        rng = random.Random(9)
        for depth, (col, amp, base) in enumerate([((178, 196, 216), 120, 150),
                                                  ((160, 180, 204), 80, 162)]):
            pts = [(0, h)]
            x = 0
            y = base - rng.randint(0, amp)
            while x < SCREEN_W:
                x += rng.randint(18, 55)
                y = max(8, min(h - 4, y + rng.randint(-26, 26)))
                if rng.random() < 0.12:
                    y = base - rng.randint(amp // 2, amp)
                pts.append((x, y if y < base else base))
            pts.append((SCREEN_W, h))
            pygame.draw.polygon(s, col, pts)
        return s

    # ---------- 查詢 ----------
    def height_at(self, x, z):
        """世界 (x, 相機 z) 的地面高度，與畫面用同一張高程圖、同樣的雙線性取樣。"""
        fz = (z + self.travel) / self.CELL
        fx = (x - self.XMIN) / self.CELL
        if fx < 0:
            fx = 0.0
        elif fx > self.NX - 1.001:
            fx = self.NX - 1.001
        iz = int(math.floor(fz))
        ix = int(fx)
        tz, tx = fz - iz, fx - ix
        r0 = self.hm_list[iz % self.NZ]
        r1 = self.hm_list[(iz + 1) % self.NZ]
        a = r0[ix] + (r0[ix + 1] - r0[ix]) * tx
        b = r1[ix] + (r1[ix + 1] - r1[ix]) * tx
        return a + (b - a) * tz

    def update(self, speed):
        global TRAVEL
        self.travel += speed
        TRAVEL = self.travel

    # ---------- 繪製：高度場光線投射（Voxel Space） ----------
    def draw(self, surf):
        """
        不畫多邊形，而是對「每一欄像素」由近到遠掃描高程圖：
          1. 每一層深度 z，算出這一欄看到的地面高度 -> 投影成螢幕 y
          2. 由近到遠取「累積最小值」：比前面更高的地形才看得到（遮擋）
          3. 每個像素找出「第一個蓋到它的深度層」，取那一層的顏色
        全部用 numpy 一次處理整個畫面，沒有逐像素的 Python 迴圈。
        結果是逐像素連續的地表，不會有網格接縫。
        """
        np = numpy
        C, S, RW, RH = self.CELL, self.SLICES, self.RW, self.RH
        zw = (self.zs + self.travel) / C
        izf = np.floor(zw)
        tz = (zw - izf)[:, None].astype(np.float32)
        iz0 = (izf.astype(np.int64) % self.NZ)[:, None]
        iz1 = (iz0 + 1) % self.NZ
        tx = self.tx
        a_ = self.hmc[iz0, self.ix0]                   # 一次讀取 = 這格與右邊鄰居
        b_ = self.hmc[iz1, self.ix0]
        h = (a_.real * (1 - tx) + a_.imag * tx) * (1 - tz) + (b_.real * (1 - tx) + b_.imag * tx) * tz
        iz4 = (np.round(zw * 4).astype(np.int64) % (self.NZ * 4))[:, None]
        v = self.col4p[iz4, self.ix4]                                       # (S, RW) 打包色
        f1 = self.f1i                                                       # 全程整數運算
        r = ((v >> 16) & 255) * f1 + self.hzr
        g = ((v >> 8) & 255) * f1 + self.hzg
        b = (v & 255) * f1 + self.hzb
        rs, gs, bs, _ = self.frame.get_shifts()
        col = ((r >> 8) << rs) | ((g >> 8) << gs) | ((b >> 8) << bs)
        top = self.rcy + h * self.rf / self.zs[:, None]
        cm = np.minimum.accumulate(top, axis=0)                             # 遮擋
        rows = np.clip(np.ceil(cm), 0, RH).astype(np.int64)
        hist = np.bincount((rows * RW + self.colidx).ravel(),
                           minlength=(RH + 1) * RW).reshape(RH + 1, RW)
        k = S - np.cumsum(hist[:RH], axis=0)                               # 每像素的可見層
        # 天空接在顏色表後面：k == S 的像素改指向天空那一列，一次取完不用再合成
        palette = np.concatenate([col, self.sky_lr], axis=0)
        idx = np.where(k < S, k, S + self.rowidx)
        img = palette[idx.T, self.colidx[:, None]]                          # (RW, RH) 打包色
        pygame.surfarray.blit_array(self.frame, img)                        # 格式相同，直接寫入
        surf.blit(pygame.transform.smoothscale(self.frame, (SCREEN_W, SCREEN_H)), (0, 0))


# ---------------------------------------------------------------
# 3D 多邊形戰機（手刻模型 + 平行光著色 + 背面剔除）
# ---------------------------------------------------------------
def build_fighter():
    """
    程序化建構戰機模型，回傳 (頂點表, 面表)。
    座標：x 右、y 下、z 前（機鼻朝畫面深處，我們從後上方看它）。
    面的頂點順序決定法線方向，進而決定背面剔除與受光 —— 左右兩側要鏡像反轉。
    """
    V = []
    F = []
    K = 0.7        # 整體縮小 30%，讓畫面不擁擠、敵我更容易分辨

    def v(x, y, z):
        V.append((x * K, y * K, z * K))
        return len(V) - 1

    # ---- 機身：機鼻 + 三個四邊形剖面環 ----
    nose = v(0, -4, 112)
    rings = []
    for z, ty, side, by, hw in [(48, -22, -6, 16, 24),
                                (-6, -27, -7, 20, 30),
                                (-58, -20, -5, 14, 22)]:
        rings.append((v(0, ty, z), v(-hw, side, z), v(0, by, z), v(hw, side, z)))
    body_top, body_side, body_bot = (96, 150, 215), (64, 108, 168), (40, 66, 104)

    t, l, b, r = rings[0]
    F += [((nose, t, l), body_top), ((nose, l, b), body_side),
          ((nose, b, r), body_bot), ((nose, r, t), body_top)]
    for i in range(len(rings) - 1):
        t0, l0, b0, r0 = rings[i]
        t1, l1, b1, r1 = rings[i + 1]
        F += [((t0, t1, l1, l0), body_top), ((l0, l1, b1, b0), body_side),
              ((b0, b1, r1, r0), body_bot), ((r0, r1, t1, t0), body_side)]
    t, l, b, r = rings[-1]
    F.append(((t, r, b, l), (26, 40, 66)))

    # ---- 主翼（有厚度：上下兩片加前後緣） ----
    wing_col, wing_top, wing_edge = (80, 128, 192), (112, 170, 232), (150, 210, 250)
    for sx in (-1, 1):
        rf_u = v(sx * 20, -8, 26)
        rb_u = v(sx * 22, -8, -52)
        tf_u = v(sx * 104, -2, -24)
        tb_u = v(sx * 108, -2, -58)
        rf_d = v(sx * 20, 2, 26)
        rb_d = v(sx * 22, 2, -52)
        tf_d = v(sx * 104, 4, -24)
        tb_d = v(sx * 108, 4, -58)
        if sx < 0:
            F += [((rf_u, tf_u, tb_u, rb_u), wing_top), ((rb_d, tb_d, tf_d, rf_d), wing_col),
                  ((rf_d, tf_d, tf_u, rf_u), wing_col), ((tb_u, tb_d, rb_d, rb_u), wing_col),
                  ((tf_u, tf_d, tb_d, tb_u), wing_edge)]
        else:
            F += [((rb_u, tb_u, tf_u, rf_u), wing_top), ((rf_d, tf_d, tb_d, rb_d), wing_col),
                  ((rf_u, tf_u, tf_d, rf_d), wing_col), ((rb_u, rb_d, tb_d, tb_u), wing_col),
                  ((tb_u, tb_d, tf_d, tf_u), wing_edge)]

    # ---- 雙垂直尾翼（外傾，是俯視角下最能表現「高度」的部位） ----
    for sx in (-1, 1):
        bf = v(sx * 16, -12, -18)
        bb = v(sx * 18, -12, -60)
        tf = v(sx * 34, -52, -34)
        tb = v(sx * 36, -52, -60)
        if sx < 0:
            F += [((bf, tf, tb, bb), (120, 180, 235)), ((bb, tb, tf, bf), (74, 118, 178))]
        else:
            F += [((bb, tb, tf, bf), (120, 180, 235)), ((bf, tf, tb, bb), (74, 118, 178))]

    # ---- 座艙罩 ----
    c1 = v(0, -30, 34)
    c2 = v(-13, -20, 12)
    c3 = v(13, -20, 12)
    c4 = v(-11, -22, -16)
    c5 = v(11, -22, -16)
    F += [((c1, c2, c3), (150, 220, 255)), ((c2, c4, c5, c3), (110, 180, 230))]

    # ---- 引擎莢艙 ----
    for sx in (-1, 1):
        a = v(sx * 10, -10, -46)
        b_ = v(sx * 26, -10, -46)
        c = v(sx * 26, 6, -46)
        d = v(sx * 10, 6, -46)
        a2 = v(sx * 12, -9, -74)
        b2 = v(sx * 24, -9, -74)
        c2_ = v(sx * 24, 5, -74)
        d2 = v(sx * 12, 5, -74)
        pod, pod_t, pod_end = (70, 100, 150), (100, 140, 200), (24, 34, 56)
        if sx < 0:
            F += [((a, a2, b2, b_), pod_t), ((b_, b2, c2_, c), pod), ((c, c2_, d2, d), pod),
                  ((d, d2, a2, a), pod), ((a2, d2, c2_, b2), pod_end)]
        else:
            F += [((b_, b2, a2, a), pod_t), ((c, c2_, b2, b_), pod), ((d, d2, c2_, c), pod),
                  ((a, a2, d2, d), pod), ((b2, c2_, d2, a2), pod_end)]

    return V, F


class Ship3D:
    """
    真 3D 多邊形戰機：58 個頂點、39 個面，含背面剔除與平行光著色。
    這是 billboard 貼圖做不到的 —— 它會隨著操作真的滾轉、俯仰。
    """
    V, F = build_fighter()
    LIGHT = normalize((-0.45, -0.75, -0.5))     # 平行光方向

    def __init__(self):
        self.x = 0.0
        self.y = 250.0
        self.z = PLAYER_Z
        self.roll = 0.0
        self.pitch = 0.0
        self.max_hp = 100
        self.hp = self.max_hp
        self.lives = 3
        # 武器庫：key = 武器 id, value = {"level":1~3, "ammo":剩餘彈藥}
        # PULSE 是內建主砲，彈藥無限（ammo = None）
        self.arsenal = {"PULSE": {"level": 1, "ammo": None}}
        self.weapon = "PULSE"
        self.shield = 0
        self.invincible = 0
        self.cooldown = 0
        self.missile_cd = 0
        self.radius = 44          # 碰撞半徑（世界單位，配合縮小後的機體）
        self.ground_warn = False  # 接近地面警告

    # ---- 控制 ----
    def update(self, keys, particles, terrain):
        ax = ay = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            ax -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            ax += 1
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            ay -= 1
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            ay += 1

        speed = 11.0
        if ax and ay:
            speed *= 0.707
        self.x += ax * speed
        self.y += ay * speed
        # 用投影反推邊界，確保戰機永遠留在畫面內
        self.x = max(-X_LIMIT, min(X_LIMIT, self.x))
        self.y = max(Y_TOP, min(Y_BOTTOM, self.y))

        # 姿態：往目標角度平滑靠近（手感的關鍵）
        self.roll += (ax * 0.62 - self.roll) * 0.12
        self.pitch += (ay * 0.24 - self.pitch) * 0.12

        if self.cooldown > 0:
            self.cooldown -= 1
        if self.missile_cd > 0:
            self.missile_cd -= 1
        if self.shield > 0:
            self.shield -= 1
        if self.invincible > 0:
            self.invincible -= 1

        # 地形碰撞：山脊會把戰機頂回去並造成損傷
        ground = terrain.height_at(self.x, self.z)
        clearance = ground - self.y          # 距離地面還有多少（正值 = 在地面上方）
        self.ground_warn = clearance < 130
        if clearance < 46:
            self.y = ground - 46
            if self.hit(16):
                particles.burst((self.x, self.y + 30, self.z), 10, (255, 170, 90), speed=9)
                return True                   # 回傳「撞到地面」讓主迴圈加上震動

        # 引擎噴流粒子（3D）
        for side in (-1, 1):
            if random.random() < 0.7:
                particles.emit(self.x + side * 15, self.y - 2, self.z - 40,
                               random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6),
                               -random.uniform(7, 13),
                               random.randint(7, 13), (90, 190, 255), 4.2)

    BASE_PITCH = 0.12      # 固定顯示俯仰，讓機體上表面朝向攝影機

    def transform(self, p):
        """模型座標 -> 世界座標（先滾轉，再俯仰，最後平移）。"""
        p = rot_z(p, self.roll)
        p = rot_x(p, self.pitch + self.BASE_PITCH)
        return (p[0] + self.x, p[1] + self.y, p[2] + self.z)

    def gun_ports(self):
        """兩側機翼的槍口世界座標。"""
        return [self.transform((-44, 1, 0)), self.transform((44, 1, 0))]

    # ---- 武器庫 ----
    def owned(self):
        """目前持有的武器，依固定順序排列（HUD 與切換都用這個順序）。"""
        return [w for w in WEAPON_ORDER if w in self.arsenal]

    def add_weapon(self, wid, auto_equip=True):
        """
        撿到武器包：沒有就加入，已有就補彈藥並升級。
        只有「新武器」會自動換上；補彈藥不切換（玩家正在用的武器不該被打斷）。
        """
        spec = WEAPONS[wid]
        if wid in self.arsenal:
            slot = self.arsenal[wid]
            slot["level"] = min(3, slot["level"] + 1)
            if slot["ammo"] is not None:
                slot["ammo"] = min(spec["ammo"] * 2, slot["ammo"] + spec["ammo"])
            return f"{spec['label']} Lv{slot['level']}"
        self.arsenal[wid] = {"level": 1, "ammo": spec["ammo"]}
        if auto_equip:
            self.weapon = wid
        return f"{spec['label']} ACQUIRED"

    def upgrade_current(self):
        """火力道具：升級目前裝備的武器。"""
        slot = self.arsenal[self.weapon]
        if slot["level"] < 3:
            slot["level"] += 1
            return f"{WEAPONS[self.weapon]['label']} Lv{slot['level']}"
        if slot["ammo"] is not None:
            slot["ammo"] += WEAPONS[self.weapon]["ammo"] // 2
            return "AMMO +"
        return "MAX LEVEL"

    def switch(self, step=1):
        own = self.owned()
        i = own.index(self.weapon)
        self.weapon = own[(i + step) % len(own)]

    def select(self, wid):
        if wid in self.arsenal:
            self.weapon = wid
            return True
        return False

    def consume(self, n=1):
        """扣彈藥；打完就自動退回主砲，玩家不會卡在沒子彈的狀態。"""
        slot = self.arsenal[self.weapon]
        if slot["ammo"] is None:
            return True
        if slot["ammo"] <= 0:
            return False
        slot["ammo"] -= n
        if slot["ammo"] <= 0:
            del self.arsenal[self.weapon]
            self.weapon = "PULSE"
            return True
        return True

    def hit(self, damage):
        if self.invincible > 0:
            return False
        if self.shield > 0:
            self.shield = 0
            self.invincible = 40
            return False
        self.hp -= damage
        self.invincible = 55
        return True

    def draw(self, surf):
        if self.invincible > 0 and (self.invincible // 4) % 2 == 0:
            return

        world = [self.transform(v) for v in self.V]
        screen = [project(*w) for w in world]

        faces = []
        for idx, color in self.F:
            pts = [screen[i] for i in idx]
            if any(p is None for p in pts):
                continue
            a, b, c = world[idx[0]], world[idx[1]], world[idx[2]]
            n = normalize(cross((b[0] - a[0], b[1] - a[1], b[2] - a[2]),
                                (c[0] - a[0], c[1] - a[1], c[2] - a[2])))
            # 背面剔除：面朝離攝影機而去就不畫
            view = normalize(a)
            if dot(n, view) > 0:
                continue
            # 平行光著色
            lam = max(0.0, dot(n, self.LIGHT))
            shade = 0.38 + 0.62 * lam
            col = tuple(min(255, int(c_ * shade)) for c_ in color)
            depth = sum(world[i][2] for i in idx) / len(idx)
            faces.append((depth, [(p[0], p[1]) for p in pts], col))

        # 畫家演算法：遠的先畫
        faces.sort(key=lambda f: -f[0])
        for _d, pts, col in faces:
            pygame.draw.polygon(surf, col, pts)
            pygame.draw.polygon(surf, tuple(min(255, c + 26) for c in col), pts, 1)

        # 引擎光
        for side in (-1, 1):
            p = project(*self.transform((side * 13, -1, -52)))
            if p:
                r = max(3, int(9 * p[2] * 1.6))
                blit_glow(surf, (int(p[0]), int(p[1])), r * 2, (70, 150, 255))

        # 護盾泡泡
        if self.shield > 0:
            p = project(self.x, self.y, self.z)
            if p:
                r = int(self.radius * 1.5 * p[2])
                a = 90 + int(60 * math.sin(pygame.time.get_ticks() * 0.01))
                sh = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(sh, (110, 220, 255, a), (r + 2, r + 2), r, 3)
                surf.blit(sh, (p[0] - r - 2, p[1] - r - 2))


# ---------------------------------------------------------------
# 3D 粒子
# ---------------------------------------------------------------
class Particles3D:
    MAX = 420

    def __init__(self):
        self.parts = []

    def emit(self, x, y, z, vx, vy, vz, life, color, size):
        if len(self.parts) >= self.MAX:
            return
        self.parts.append([x, y, z, vx, vy, vz, life, life, color, size])

    def burst(self, pos, n, color, speed=9.0, size=10.0):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            b = random.uniform(-1, 1)
            s = random.uniform(speed * 0.3, speed)
            self.emit(pos[0], pos[1], pos[2],
                      math.cos(a) * s, math.sin(a) * s, b * s,
                      random.randint(14, 30), color, size)

    def update(self, world_speed):
        for p in self.parts:
            p[0] += p[3]
            p[1] += p[4]
            p[2] += p[5] - world_speed * 0.35
            p[6] -= 1
        self.parts = [p for p in self.parts if p[6] > 0 and p[2] > NEAR]

    def collect(self, out):
        for x, y, z, _vx, _vy, _vz, life, maxl, color, size in self.parts:
            out.append((z, "particle", (x, y, z, life / maxl, color, size)))


# ---------------------------------------------------------------
# 敵人（深度縮放 billboard）
# ---------------------------------------------------------------
# 依素材實際內容：E3.png 是飛碟（精英），E4.png 是深藍獵人怪
# world = 世界尺寸（決定投影後的螢幕大小），radius = 3D 碰撞半徑。
# 兩者都已縮小 30%，畫面才不會擠。
ENEMY_TYPES = {
    1: {"name": "Drifter", "world": 91, "hp": 2, "speed": (7.5, 10.0), "score": 10,
        "behavior": "drift", "shoot": 0.000, "damage": 12, "color": (80, 200, 180), "radius": 43},
    2: {"name": "Weaver", "world": 95, "hp": 3, "speed": (8.0, 11.0), "score": 20,
        "behavior": "wave", "shoot": 0.006, "damage": 14, "color": (230, 90, 70), "radius": 45},
    # 飛碟 = 小 BOSS：單獨登場，體型比一般敵人大 50%
    3: {"name": "Saucer", "world": 200, "hp": 32, "speed": (5.0, 7.0), "score": 180,
        "behavior": "saucer", "shoot": 0.020, "damage": 25, "color": (210, 90, 200), "radius": 96},
    4: {"name": "Hunter", "world": 98, "hp": 5, "speed": (6.5, 9.0), "score": 35,
        "behavior": "hunt", "shoot": 0.012, "damage": 18, "color": (60, 90, 140), "radius": 46},
}


class Enemy3D:
    RETREAT_AFTER = 1500      # 小 BOSS 盤旋這麼多幀（25 秒）後撤離

    def __init__(self, etype, image, wave, x=None, y=None, z=None):
        cfg = ENEMY_TYPES[etype]
        self.etype = etype
        self.cfg = cfg
        self.image = image
        self.world_size = cfg["world"]
        self.radius = cfg["radius"]
        self.max_hp = cfg["hp"] + wave // 3
        self.hp = self.max_hp
        self.score = cfg["score"]
        self.damage = cfg["damage"]
        self.shoot_chance = cfg["shoot"] * (1 + wave * 0.05)

        lo, hi = cfg["speed"]
        self.vz = -(random.uniform(lo, hi) + wave * 0.25)
        self.x = random.uniform(-420, 420) if x is None else x
        self.y = random.uniform(-210, 260) if y is None else y
        self.z = SPAWN_Z if z is None else z
        self.phase = random.uniform(0, math.tau)
        self.amp = random.uniform(70, 150)
        self.drift = random.uniform(-2.5, 2.5)
        self.flash = 0
        self.alive = True
        self.hover_target = random.uniform(-380, 380)
        self.hover_time = 0

    def update(self, ship, enemy_bullets, game):
        b = self.cfg["behavior"]
        self.z += self.vz

        if b == "drift":
            self.x += self.drift
            self.y += math.sin(self.phase) * 0.8
            self.phase += 0.03
        elif b == "wave":
            self.phase += 0.045
            self.x += math.cos(self.phase) * 4.5
            self.y += math.sin(self.phase * 1.6) * 2.4
        elif b == "hunt":
            # 往玩家位置靠攏（越近越積極）
            k = 0.035 if self.z > 1200 else 0.075
            self.x += (ship.x - self.x) * k
            self.y += (ship.y - self.y) * k * 0.7
        elif b == "saucer":
            # 小 BOSS：減速後在中距離盤旋掃射
            self.hover_time += 1
            if self.hover_time > self.RETREAT_AFTER and not getattr(self, "scripted", False):
                # 安全閥：牠在場時不會出其他敵人，如果玩家一直打不掉，
                # 遊戲會永遠停在這裡。所以撐過一段時間就俯衝離場，
                # 讓戰鬥節奏繼續走下去。
                self.vz = -15.0
            elif self.z < 1500:
                self.vz *= 0.985
                if abs(self.x - self.hover_target) < 30:
                    self.hover_target = random.uniform(-420, 420)
                self.x += (self.hover_target - self.x) * 0.02
            self.phase += 0.035
            self.y += math.sin(self.phase) * 1.8

        self.x = max(-700, min(700, self.x))
        self.y = max(-300, min(GROUND_Y - 70, self.y))
        ground = ground_at(self.x, self.z)
        if self.y > ground - 50:
            self.y = ground - 50

        if self.flash > 0:
            self.flash -= 1

        if random.random() < self.shoot_chance and NEAR * 4 < self.z < 3000:
            self.fire(ship, enemy_bullets)

        # 飛過玩家 -> 消失
        if self.z <= NEAR + 20:
            self.alive = False

    def fire(self, ship, enemy_bullets):
        if self.cfg["behavior"] == "saucer":
            col = PINK if not getattr(self, "scripted", False) or self.cfg["color"] == ENEMY_TYPES[3]["color"] \
                else self.cfg["color"]                      # 藍色、黑色小魔王射出同色系的子彈
            bub = MINIBOSS_BUBBLE[getattr(self, "variant", 0) % 3]    # 每隻小魔王只發射一種顏色的電漿泡泡
            for off in (-0.16, 0.0, 0.16):
                self._shot(ship, enemy_bullets, off, col, 17.0, bubble=bub)
        else:
            self._shot(ship, enemy_bullets, 0.0, (255, 120, 90), 15.0,
                       kind={1: "gold", 2: "fireball", 4: "meteor"}.get(self.etype))  # 每種小兵各自的 3D 武器

    def _shot(self, ship, enemy_bullets, spread, color, speed, kind=None, bubble=None):
        dx = ship.x - self.x
        dy = ship.y - self.y
        dz = ship.z - self.z
        d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        vx, vy, vz = dx / d * speed, dy / d * speed, dz / d * speed
        vx += spread * speed
        enemy_bullets.append(EnemyBullet3D(self.x, self.y, self.z, vx, vy, vz, color, kind, bubble))

    def take_damage(self, dmg=1):
        self.hp -= dmg
        self.flash = 4
        return self.hp <= 0

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        size = max(4, int(self.world_size * sc))
        if size < 3:
            return
        frames = MINION_SPRITES.get(self.etype)
        if self.etype == 3 and SAUCER_SPRITES:              # 小魔王飛碟：3D 旋轉
            img = saucer_frame(self, getattr(self, "variant", 0), size)
        elif frames:
            # 3D 小兵：依自己的動畫進度挑畫格；在畫面左右兩側時改用側轉角度（右側用鏡像）
            self.anim = getattr(self, "anim", random.uniform(0, math.tau)) + 0.12
            k = int((self.anim % math.tau) / math.tau * 8) % 8
            ang = math.degrees(math.atan2(abs(self.x), max(1.0, self.z)))
            row = 0 if ang < 7 else (2 if self.x > 0 else 1)
            img = scaled(frames[row][k], max(4, int(size * MINION_SCALE)))
        else:
            img = scaled(self.image, size)
        rect = img.get_rect(center=(int(sx), int(sy)))
        surf.blit(img, rect)
        if self.flash > 0:
            surf.blit(img, rect, special_flags=pygame.BLEND_RGB_ADD)

        # 遠距離時加個光暈，讓玩家看得見來襲方向
        if sc < 0.35:
            blit_glow(surf, (int(sx), int(sy)), max(8, size),
                      tuple(c // 4 for c in self.cfg["color"]))

        # 血條（只在受傷且夠近時顯示）
        if self.hp < self.max_hp and size > 26:
            w = size
            ratio = max(0, self.hp / self.max_hp)
            bx, by = rect.left, rect.top - 7
            pygame.draw.rect(surf, (60, 20, 20), (bx, by, w, 4))
            pygame.draw.rect(surf, (90, 230, 120), (bx, by, int(w * ratio), 4))


# ---------------------------------------------------------------
# BOSS 母艦
# ---------------------------------------------------------------
class Boss3D:
    def __init__(self, image, wave):
        self.image = image
        self.world_size = 460
        self.radius = 185
        tier = wave // 5
        self.max_hp = 150 + tier * 90
        self.hp = self.max_hp
        self.score = 1500 + tier * 500
        self.damage = 34
        self.x = 0.0
        self.y = -40.0
        self.z = SPAWN_Z
        self.target_z = 1500.0
        self.phase = 0.0
        self.flash = 0
        self.dying = False
        self.death_timer = 0
        self.entering = True
        self.t_aim = 0
        self.t_ring = 0

    @property
    def stage(self):
        r = self.hp / self.max_hp
        return 1 if r > 0.66 else (2 if r > 0.33 else 3)

    def pos(self):
        return (self.x, self.y, self.z)

    def update(self, ship, enemy_bullets, game):
        if self.entering:
            self.z += (self.target_z - self.z) * 0.02
            if abs(self.z - self.target_z) < 40:
                self.entering = False
            return
        if self.dying:
            return

        st = self.stage
        self.phase += {1: 0.011, 2: 0.016, 3: 0.022}[st]
        self.x = math.sin(self.phase) * 420
        self.y = -40 + math.sin(self.phase * 2.1) * 90
        # 第三階段會壓迫性地往前逼近
        self.z = self.target_z + math.sin(self.phase * 0.7) * 260 - (260 if st == 3 else 0)

        self.t_aim += 1
        self.t_ring += 1
        aim_cd = {1: 55, 2: 42, 3: 30}[st]
        if self.t_aim >= aim_cd:
            self.t_aim = 0
            n = {1: 3, 2: 5, 3: 5}[st]
            self.volley = getattr(self, "volley", 0) + 1
            for i in range(n):                                       # 七彩：每發一色，每輪起始顏色往後輪替
                self._aimed(ship, enemy_bullets, (i - (n - 1) / 2) * 0.10, RAINBOW[(i + self.volley * 2) % 7])

        if st >= 2 and self.t_ring >= {2: 85, 3: 60}[st]:
            self.t_ring = 0
            n = 12 if st == 2 else 16
            for i in range(n):
                a = i * math.tau / n + random.uniform(0, 0.4)
                enemy_bullets.append(EnemyBullet3D(                     # 彩虹環：一整圈依序七種顏色
                    self.x, self.y, self.z,
                    math.cos(a) * 7.0, math.sin(a) * 7.0, -15.0, (255, 170, 90), bubble=RAINBOW[i % 7]))

        if self.flash > 0:
            self.flash -= 1

    def _aimed(self, ship, enemy_bullets, spread, bubble=None):
        dx, dy, dz = ship.x - self.x, ship.y - self.y, ship.z - self.z
        d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        s = 19.0
        enemy_bullets.append(EnemyBullet3D(
            self.x, self.y, self.z,
            dx / d * s + spread * s, dy / d * s, dz / d * s, PINK, bubble=bubble))

    def take_damage(self, dmg=1, at=None):
        if self.entering or self.dying:
            return False
        self.hp -= dmg
        self.flash = 3
        return self.hp <= 0

    def draw(self, surf, p):
        sx, sy, sc = p
        size = max(8, int(self.world_size * sc))
        img = saucer_frame(self, 3, size) if SAUCER_SPRITES else scaled(self.image, size)   # 母艦：金屬紫 3D 旋轉
        rect = img.get_rect(center=(int(sx), int(sy)))
        blit_glow(surf, (int(sx), int(sy)), int(size * 0.75), (70, 20, 70))
        surf.blit(img, rect)
        if self.flash > 0:
            surf.blit(img, rect, special_flags=pygame.BLEND_RGB_ADD)


# ---------------------------------------------------------------
# 3D 彈藥
# ---------------------------------------------------------------
class Bullet3D:
    """我方光束：往 +z 飛，離開時在畫面上縮向消失點。"""

    def __init__(self, x, y, z, vx, vy, vz=62.0, dmg=1):
        self.x, self.y, self.z = x, y, z
        self.vx, self.vy, self.vz = vx, vy, vz
        self.dmg = dmg
        self.alive = True
        self.radius = 39          # 畫面放大 3 倍，判定只放大 1.5 倍：太大會讓遊戲變得太簡單

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.z += self.vz
        if self.z > FAR:
            self.alive = False

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        p2 = project(self.x - self.vx * 2.4, self.y - self.vy * 2.4, self.z - self.vz * 2.4)
        w = max(2, int(21 * sc))                         # 子彈放大 3 倍（原本 7）
        blit_glow(surf, (int(sx), int(sy)), max(8, int(48 * sc)), (50, 110, 150))
        if p2:
            if ICE:      # 白雪上要用飽和的藍，淺色光束會消失
                pygame.draw.line(surf, (10, 110, 230), (p2[0], p2[1]), (sx, sy), w + 4)
                pygame.draw.line(surf, (90, 200, 255), (p2[0], p2[1]), (sx, sy), max(1, w - 2))
            else:
                pygame.draw.line(surf, (120, 210, 255), (p2[0], p2[1]), (sx, sy), w + 2)
            pygame.draw.line(surf, (240, 252, 255), (p2[0], p2[1]), (sx, sy), max(1, w // 3))   # 亮白核心
        pygame.draw.circle(surf, (235, 250, 255), (int(sx), int(sy)), max(2, w // 2))


SAUCER_SPRITES = []           # 飛碟 3D 精靈：[粉紅, 藍, 黑, 金屬紫]，各 12 格旋轉（60° 一個無縫循環）
SAUCER_SCALE = 1.2            # 模型在畫格裡留有邊距，放大一點讓畫面上的大小與原本一致


def load_saucer_sprites():
    path = find_asset("saucer_sprites.png")
    if not path:
        print("  [MISS] saucer_sprites.png -> 飛碟維持平面圖")
        return
    try:
        atlas = pygame.image.load(path).convert_alpha()
        S = atlas.get_height() // 4
        SAUCER_SPRITES[:] = [[atlas.subsurface((c * S, r * S, S, S)).copy() for c in range(atlas.get_width() // S)]
                             for r in range(4)]
        print("  [OK]   飛碟 3D 精靈（4 種配色 × 12 格旋轉）")
    except pygame.error as e:
        print(f"  [FAIL] saucer_sprites.png：{e}")


def saucer_frame(obj, variant, size):
    """飛碟不停旋轉：每個物件有自己的旋轉進度。"""
    obj.spin = getattr(obj, "spin", random.uniform(0, 12)) + 0.45
    frames = SAUCER_SPRITES[variant]
    return scaled(frames[int(obj.spin) % len(frames)], max(4, int(size * SAUCER_SCALE)))


MINION_SPRITES = {}           # 小兵 3D 精靈：{敵人種類: [正面 8 格, 側轉 8 格, 側轉鏡像 8 格]}
MINION_SCALE = 1.25           # 3D 模型在畫格裡留有邊距，放大一點讓畫面上的大小與原本一致（命中範圍不變）


def load_minion_sprites():
    path = find_asset("minion_sprites.png")
    if not path:
        print("  [MISS] minion_sprites.png -> 小兵維持平面圖")
        return
    try:
        atlas = pygame.image.load(path).convert_alpha()
        S = atlas.get_width() // 8
        for r, et in enumerate((1, 2, 4)):                 # 每種兩列：正面、側轉 20°
            rows = []
            for yi in (0, 1):
                rows.append([atlas.subsurface((c * S, (r * 2 + yi) * S, S, S)).copy() for c in range(8)])
            rows.append([pygame.transform.flip(f, True, False) for f in rows[1]])
            MINION_SPRITES[et] = rows
        print(f"  [OK]   小兵 3D 精靈（3 種 × 8 格動畫 × 3 個角度）")
    except pygame.error as e:
        print(f"  [FAIL] minion_sprites.png：{e}")


FIRE_FRAMES = []              # 火焰彈 8 格動畫（遊戲啟動時用程式產生）


def make_fire_frames(size=112, n=8, palette="fire"):
    """
    原創的 3D 火球：每個像素依離球心的距離，從白熱核心漸變到暗紅外緣（看起來像發光的立體球體），
    疊上隨時間翻騰的分形雜訊當火焰紋理，邊緣因此呈不規則的火舌，外圍再加一圈柔和光暈。
    """
    if numpy is None:
        return []
    np = numpy
    rng = np.random.default_rng(11)
    lat = rng.random((4, 16, 16)).astype(np.float32)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    u = (xx + 0.5) / size * 2 - 1
    v = (yy + 0.5) / size * 2 - 1
    r = np.sqrt(u * u + v * v)

    def vnoise(g, x, y):
        x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
        fx = x - x0; fy = y - y0
        fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy)
        a = g[y0 % 16, x0 % 16]; b = g[y0 % 16, (x0 + 1) % 16]
        c = g[(y0 + 1) % 16, x0 % 16]; d = g[(y0 + 1) % 16, (x0 + 1) % 16]
        return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy

    stops = np.array([0.0, 0.3, 0.52, 0.72, 0.88, 1.0])
    if palette == "green":                                           # Megalon 綠色衝擊波：深綠 -> 黃綠 -> 白熾
        cols = np.array([(10, 60, 10), (40, 150, 30), (120, 230, 60), (205, 255, 120), (240, 255, 210), (255, 255, 240)],
                        np.float32)
        rim = np.array([90, 220, 60], np.float32)
    elif palette == "nova":                                          # 原子吐息：深紫 -> 藍紫 -> 白熾核心
        cols = np.array([(30, 10, 90), (80, 40, 220), (125, 110, 255), (195, 185, 255), (242, 238, 255), (255, 255, 255)],
                        np.float32)
        rim = np.array([110, 80, 255], np.float32)
    elif palette == "blue":                                          # 藍焰：深藍 -> 電藍 -> 青白核心
        cols = np.array([(8, 18, 90), (20, 70, 220), (40, 150, 255), (120, 215, 255), (215, 245, 255), (255, 255, 255)],
                        np.float32)
        rim = np.array([50, 130, 255], np.float32)
    else:
        cols = np.array([(110, 8, 0), (220, 35, 5), (255, 110, 15), (255, 200, 50), (255, 245, 190), (255, 255, 245)],
                        np.float32)
        rim = np.array([255, 90, 20], np.float32)
    frames = []
    for f in range(n):
        ph = f / n * math.tau
        sph = np.sqrt(np.clip(1 - r * r, 0, 1))
        nx, ny = u * 3 + math.cos(ph) * 1.5, v * 3 + math.sin(ph) * 1.5 + f * 0.35
        noise = sum(vnoise(lat[k], nx * 2 ** k, ny * 2 ** k) / 2 ** k for k in range(4)) / 1.875
        edge = 0.78 + 0.22 * noise                                   # 不規則的火舌邊緣
        body = np.clip((edge - r) / 0.16, 0, 1)
        swirl = noise ** 1.6                                          # 加強紋理對比：亮暗分明的火焰
        lit = np.clip(-(u + v) * 0.35, -0.2, 0.3) * sph               # 左上受光：立體球感
        heat = np.clip(0.12 + 0.62 * sph * (0.45 + 0.85 * swirl) + lit, 0, 1)
        if palette in ("blue", "nova", "green"):                     # 整體提亮、加大白熱核心
            heat = np.clip(heat * 0.85 + 0.35 * sph ** 2 + 0.12, 0, 1)
        rgb = np.stack([np.interp(heat, stops, cols[:, k]) for k in range(3)], -1)
        corona = 0.45 * np.exp(-((r - 0.75) / 0.22) ** 2) * (0.6 + 0.6 * noise)
        alpha = np.clip(body + corona * (1 - body), 0, 1)
        rgb = rgb * body[..., None] + rim * (1 - body[..., None])
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.surfarray.pixels3d(surf)[:] = np.transpose(np.clip(rgb, 0, 255), (1, 0, 2)).astype(np.uint8)
        pygame.surfarray.pixels_alpha(surf)[:] = (alpha.T * 255).astype(np.uint8)
        frames.append(surf)
    return frames


class FireOrb3D:
    """
    火焰彈：6 枚平均分佈在圓上，繞著前進方向螺旋旋轉，半徑越轉越大（火焰漩渦）。
    介面與追蹤飛彈相同（update / pos / radius / dmg / alive），所以命中、爆炸、繪製都沿用飛彈的流程。
    """
    SPEED = 44.0

    def __init__(self, x, y, z, k, n, dmg, level):
        self.ox, self.oy = x, y
        self.z = z + 30
        self.phase = k * math.tau / n
        self.r = 18.0
        self.R = 90 + level * 20                                     # 螺旋半徑加大：6 枚分得開，看得出漩渦
        self.hist = []                                               # 最近幾個位置：畫彗星拖尾
        self.omega = 0.19
        self.dmg = dmg
        self.level = level
        self.radius = 40 + level * 4
        self.alive = True
        self.t = 0
        self.anim = random.randint(0, 7)
        self.x = self.ox + math.cos(self.phase) * self.r
        self.y = self.oy + math.sin(self.phase) * self.r

    def update(self, target, particles):
        self.t += 1
        self.z += self.SPEED
        self.phase += self.omega
        self.r = min(self.R, self.r + 4.0)
        self.hist.append((self.x, self.y, self.z))
        if len(self.hist) > 7:
            self.hist.pop(0)
        self.x = self.ox + math.cos(self.phase) * self.r
        self.y = self.oy + math.sin(self.phase) * self.r * 0.85
        if self.z > SPAWN_Z + 300:                                     # 飛過出怪距離就消失，不必畫到地平線
            self.alive = False
            return
        if self.t % 2 == 0:                                          # 火星（有拖尾後減量）
            particles.emit(self.x + random.uniform(-6, 6), self.y + random.uniform(-6, 6), self.z - 24,
                           random.uniform(-1.5, 1.5), random.uniform(-1.5, 1.0), -3.0, random.randint(10, 16),
                           random.choice([(255, 210, 60), (255, 130, 25), (240, 60, 10)]), 10.0)
        if self.t % 5 == 0:
            particles.emit(self.x, self.y, self.z - 40, random.uniform(-1, 1), random.uniform(-2, 0), -2.0,
                           random.randint(16, 24), (70, 55, 50), 9.0)                             # 黑煙

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        size = max(8, int((66 + self.level * 8) * sc) // 4 * 4)        # 以 4 像素為單位：縮圖快取才能重複使用
        n = len(self.hist)                                            # 彗星拖尾：由大到小、由黃轉紅，順著螺旋軌跡
        for i, (hx, hy, hz) in enumerate(self.hist):
            q = project(hx, hy, hz)
            if not q:
                continue
            k = (i + 1) / (n + 1)
            rr = max(2, int(size * 0.42 * k))
            col = (255, int(60 + 150 * k), int(10 + 40 * k))
            pygame.draw.circle(surf, col, (int(q[0]), int(q[1])), rr)
        blit_glow(surf, (int(sx), int(sy)), max(4, int(size * 0.85) // 4 * 4), (255, 110, 20))
        if FIRE_FRAMES:
            img = scaled(FIRE_FRAMES[(self.t // 2 + self.anim) % len(FIRE_FRAMES)], size)
            surf.blit(img, img.get_rect(center=(int(sx), int(sy))))
        else:
            pygame.draw.circle(surf, (255, 150, 40), (int(sx), int(sy)), max(2, size // 3))


COMET_FRAMES = []             # 藍焰彗頭 8 格動畫
NOVA_FRAMES = []              # 原子吐息能量彈 8 格動畫


class NovaOrb3D:
    """
    原子吐息：蓄力後射出的巨型能量彈（3D 動畫）。
      - 彗頭：白熾核心 + 藍紫光暈（程式產生的動畫）
      - 能量殼：繞著彗頭旋轉的三層藍紫弧線（弓形震波）
      - 長條尾巴：沿著軌跡往後延伸、由粗到細的三層光帶（發射後弧形上揚，尾巴在畫面上拉成一道弧）
      - 閃爍光點：沿著尾巴散布
    命中範圍很大、穿透一切；撞上魔王會減速卡住持續研磨，約 1 秒後引爆。
    """
    SPEED = 30.0

    def __init__(self, x, y, z, level, ratio, dmg):
        self.x, self.y, self.z = x, y, z + 120
        self.scale = 0.6 + 0.4 * ratio                               # 蓄力越久越大
        self.radius = 190 * self.scale
        self.dmg = dmg * (0.6 + 0.4 * ratio)
        self.level = level
        self.alive = True
        self.t = 0
        self.spin = 0.0
        self.hit_ids = set()
        self.grind = 0                                               # 卡在魔王身上的幀數
        self.detonate = False
        self.seed = random.randint(0, 9999)
        self.hist = []                                               # 最近的位置：畫長條尾巴
        self.y0 = self.y                                             # 發射後弧形上揚：尾巴才會在畫面上拉開

    def update(self, particles):
        self.t += 1
        self.spin += 0.13
        self.hist.append((self.x, self.y, self.z))
        if len(self.hist) > 60:                                       # 約 1 秒的軌跡：尾巴末端延伸到戰機附近（近處透視放大）
            self.hist.pop(0)
        self.z += 5.0 if self.grind else self.SPEED
        self.y = self.y0 - 230 * (1 - math.exp(-self.t / 20))   # 弧形往上爬升（筆直飛的話尾巴會在透視下疊成一點）
        if self.t % 2 == 0:
            particles.emit(self.x + random.uniform(-80, 80) * self.scale, self.y + random.uniform(-80, 80) * self.scale,
                           self.z - random.uniform(60, 300) * self.scale, 0, 0, -4.0, random.randint(12, 22),
                           random.choice([(220, 90, 255), (120, 255, 200), (160, 140, 255)]), 7.0)

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        S = self.scale
        head = max(12, int(180 * S * sc) // 4 * 4)
        # 長條尾巴：沿著最近的軌跡，從能量彈往後延伸、由粗到細的三層光帶
        pts = [(q, (i + 1) / (len(self.hist) + 1)) for i, h in enumerate(self.hist) for q in [project(*h)] if q]
        pts.append((p, 1.0))
        if len(pts) >= 3:
            for wmul, col in ((1.0, (100, 60, 255)), (0.6, (150, 175, 255)), (0.26, (238, 242, 255))):
                left, right = [], []
                for i, (q, k) in enumerate(pts):
                    a_ = pts[min(i + 1, len(pts) - 1)][0]
                    b_ = pts[max(i - 1, 0)][0]
                    dx, dy = a_[0] - b_[0], a_[1] - b_[1]
                    Lq = math.hypot(dx, dy) or 1.0
                    wob = 1 + 0.12 * math.sin(self.t * 0.6 + i * 0.9)
                    w = 120 * S * q[2] * k ** 1.6 * wmul * wob
                    nx, ny = -dy / Lq * w, dx / Lq * w
                    left.append((q[0] + nx, q[1] + ny))
                    right.append((q[0] - nx, q[1] - ny))
                pygame.draw.polygon(surf, col, left + right[::-1])
        # 閃爍光點：沿著尾巴散布
        rr = random.Random(self.seed + self.t // 3)
        for _ in range(14):
            if not self.hist:
                break
            hx, hy, hz = self.hist[rr.randrange(len(self.hist))]
            q = project(hx + rr.uniform(-90, 90) * S, hy + rr.uniform(-90, 90) * S, hz)
            if q:
                pygame.draw.circle(surf, rr.choice([(225, 100, 255), (255, 160, 240), (170, 240, 255)]),
                                   (int(q[0]), int(q[1])), max(1, int(rr.uniform(2, 5) * S * q[2])))
        blit_glow(surf, (int(sx), int(sy)), max(8, int(head * 1.25) // 4 * 4), (110, 70, 255))
        # 能量殼：三層藍紫弧線繞著彗頭旋轉
        for i, col in enumerate(((90, 90, 255), (170, 120, 255), (70, 170, 255))):
            rw = head * (0.62 + 0.13 * i) * (1 + 0.05 * math.sin(self.t * 0.3 + i))
            rect = pygame.Rect(0, 0, int(rw * 2), int(rw * 1.7))
            rect.center = (int(sx), int(sy))
            a0 = self.spin * (1.4 - 0.3 * i) * (1 if i % 2 == 0 else -1)
            pygame.draw.arc(surf, col, rect, a0, a0 + 2.4, max(2, int(4 * S * sc + 1)))
            pygame.draw.arc(surf, col, rect, a0 + math.pi, a0 + math.pi + 1.6, max(2, int(3 * S * sc + 1)))
        if NOVA_FRAMES:
            img = scaled(NOVA_FRAMES[(self.t // 2) % len(NOVA_FRAMES)], head)
            surf.blit(img, img.get_rect(center=(int(sx), int(sy))))


class CometShot3D:
    """
    藍焰彗星：2~3 枚緊密交纏成螺旋前進，拖著又長又飄逸的藍色火焰緞帶。
    命中範圍大（約一般彈的兩倍），可以穿透：每枚記住打過哪些敵人，打穿 3 個才消失。
    介面與追蹤飛彈相同，沿用飛彈的更新與繪製流程；穿透另外處理。
    """
    SPEED = 42.0
    TRAIL = 12

    def __init__(self, x, y, z, k, n, dmg, level):
        self.ox, self.oy = x, y
        self.z = z + 130                                             # 在戰機前方生成：不會在機頭糊成一團
        self.phase = k * math.tau / n
        self.r = 10.0
        self.R = 58 + level * 10
        self.omega = 0.24
        self.dmg = dmg
        self.level = level
        self.radius = 82 + level * 6                                  # 命中範圍大
        self.pierce = 3                                               # 可穿透 3 個敵人
        self.hit_ids = set()
        self.boss_cd = 0
        self.alive = True
        self.t = 0
        self.anim = random.randint(0, 7)
        self.hist = []
        self.x = self.ox + math.cos(self.phase) * self.r
        self.y = self.oy + math.sin(self.phase) * self.r

    def update(self, target, particles):
        self.t += 1
        if self.boss_cd > 0:
            self.boss_cd -= 1
        self.hist.append((self.x, self.y, self.z))
        if len(self.hist) > self.TRAIL:
            self.hist.pop(0)
        self.z += self.SPEED
        self.phase += self.omega
        self.r = min(self.R, self.r + 3.5)
        self.x = self.ox + math.cos(self.phase) * self.r
        self.y = self.oy + math.sin(self.phase) * self.r * 0.85
        if self.z > SPAWN_Z + 300:
            self.alive = False
            return
        if self.t % 3 == 0:
            particles.emit(self.x, self.y, self.z - 30, random.uniform(-2, 2), random.uniform(-2, 2), -2.0,
                           random.randint(10, 18), random.choice([(120, 210, 255), (40, 120, 255)]), 9.0)

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        size = max(8, int((50 + self.level * 6) * sc) // 4 * 4)
        pts = [q for q in (project(*h) for h in self.hist) if q] + [p]
        if len(pts) >= 3:                                              # 三層火焰緞帶：深藍、亮藍、近白細芯
            for wmul, col in ((0.42, (25, 70, 210)), (0.28, (60, 160, 255)), (0.15, (215, 245, 255))):   # 外層收窄、亮芯加寬
                left, right = [], []
                for i, q in enumerate(pts):
                    k = (i + 1) / len(pts)                             # 0 = 尾端、1 = 彗頭
                    a = pts[min(i + 1, len(pts) - 1)]
                    b = pts[max(i - 1, 0)]
                    dx, dy = a[0] - b[0], a[1] - b[1]
                    L = math.hypot(dx, dy) or 1.0
                    wob = 1 + 0.35 * math.sin(self.t * 0.5 + i * 1.3)  # 波浪擺動：飄逸的火焰感
                    w = size * wmul * k ** 0.8 * wob
                    nx, ny = -dy / L * w, dx / L * w
                    left.append((q[0] + nx, q[1] + ny))
                    right.append((q[0] - nx, q[1] - ny))
                pygame.draw.polygon(surf, col, left + right[::-1])
        blit_glow(surf, (int(sx), int(sy)), max(4, int(size * 0.9) // 4 * 4), (40, 120, 255))
        if COMET_FRAMES:
            img = scaled(COMET_FRAMES[(self.t // 2 + self.anim) % len(COMET_FRAMES)], size)
            surf.blit(img, img.get_rect(center=(int(sx), int(sy))))


MISSILE_SPRITES = []          # 13 張：飛彈軸與視線夾角 0°（背對飛走）~ 180°（迎面而來），每 15° 一張
MISSILE_PPU = 160 / 180.0     # 精靈中每世界單位幾像素
_MISSILE_CACHE = {}


def load_missile_sprites():
    path = find_asset("missile_sprites.png")
    if not path:
        print("  [MISS] missile_sprites.png -> 飛彈改用簡單圖形")
        return
    try:
        strip = pygame.image.load(path).convert_alpha()
        h = strip.get_height()
        MISSILE_SPRITES[:] = [strip.subsurface((i * h, 0, h, h)).copy() for i in range(strip.get_width() // h)]
        print(f"  [OK]   飛彈 3D 精靈 {len(MISSILE_SPRITES)} 個角度")
    except pygame.error as e:
        print(f"  [FAIL] missile_sprites.png：{e}")


class Missile3D:
    """追蹤飛彈：在 3D 空間平滑轉向鎖定目標。"""
    SPEED = 40.0
    TURN = 0.14
    NOSE_OFF, TAIL_OFF = 60, 72          # 機頭、尾焰離中心的距離（世界單位）
    PPU = None                           # 精靈每世界單位幾像素（None = 一般飛彈的設定）

    def sprites(self):
        return MISSILE_SPRITES

    def __init__(self, x, y, z, side, dmg=2):
        self.x, self.y, self.z = x, y, z
        self.vx, self.vy, self.vz = side * 9.0, -3.0, self.SPEED
        self.dmg = dmg
        self.life = 150
        self.alive = True
        self.radius = 34
        self.target = None

    def update(self, target, particles):
        self.target = target
        if target is not None:
            tx, ty, tz = target.pos()
            dx, dy, dz = tx - self.x, ty - self.y, tz - self.z
            d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
            dx, dy, dz = dx / d * self.SPEED, dy / d * self.SPEED, dz / d * self.SPEED
            self.vx += (dx - self.vx) * self.TURN
            self.vy += (dy - self.vy) * self.TURN
            self.vz += (dz - self.vz) * self.TURN
        m = math.sqrt(self.vx ** 2 + self.vy ** 2 + self.vz ** 2) or 1.0
        k = self.SPEED / m
        self.vx, self.vy, self.vz = self.vx * k, self.vy * k, self.vz * k
        self.x += self.vx
        self.y += self.vy
        self.z += self.vz

        m2 = math.sqrt(self.vx ** 2 + self.vy ** 2 + self.vz ** 2) or 1.0
        tx_, ty_, tz_ = (self.x - self.vx / m2 * 75, self.y - self.vy / m2 * 75, self.z - self.vz / m2 * 75)
        particles.emit(tx_, ty_, tz_, -self.vx * 0.05, -self.vy * 0.05, -self.vz * 0.05,
                       random.randint(8, 15), (255, 170, 80), 9.0)                  # 尾焰火星
        if getattr(self, "SMOKE", True) or random.random() < 0.35:
            particles.emit(tx_, ty_, tz_, random.uniform(-1, 1), random.uniform(-1.5, 0.5), random.uniform(-1, 1),
                           random.randint(22, 34), (150, 152, 160), 11.0 * getattr(self, "FLAME", 1.0) ** 0.5)  # 灰色煙跡

        self.life -= 1
        if self.life <= 0 or self.z > FAR or self.z < NEAR:
            self.alive = False

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        """
        依飛行方向挑精靈：先算飛彈軸與視線的夾角（決定用哪一張），
        再算軸線在畫面上的方向（決定旋轉角度）。尾焰依前後關係畫在彈體之前或之後。
        """
        sx, sy, sc = p
        m = math.sqrt(self.vx ** 2 + self.vy ** 2 + self.vz ** 2) or 1.0
        ax, ay, az = self.vx / m, self.vy / m, self.vz / m
        nose = project(self.x + ax * self.NOSE_OFF, self.y + ay * self.NOSE_OFF, self.z + az * self.NOSE_OFF)
        tail = project(self.x - ax * self.TAIL_OFF, self.y - ay * self.TAIL_OFF, self.z - az * self.TAIL_OFF)
        SPR = self.sprites()
        ppu = self.PPU or MISSILE_PPU
        if not SPR or not nose or not tail:
            r = max(2, int(14 * sc))
            pygame.draw.circle(surf, ORANGE, (int(sx), int(sy)), r)
            pygame.draw.circle(surf, YELLOW, (int(sx), int(sy)), max(1, r // 2))
            return
        flick = 0.8 + 0.4 * random.random()

        def flame():
            tp = (int(tail[0]), int(tail[1]))
            fm = getattr(self, "FLAME", 1.0)                       # 尾焰大小（炸彈火箭比較小，才不會蓋住彈身）
            blit_glow(surf, tp, max(4, int(30 * fm * tail[2] * flick)), (255, 140, 50))
            pygame.draw.circle(surf, (255, 235, 170), tp, max(2, int(6 * fm * tail[2] * flick)))

        vm = math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2) or 1.0
        cos_t = max(-1.0, min(1.0, (ax * self.x + ay * self.y + az * self.z) / vm))
        theta = math.degrees(math.acos(cos_t))
        idx = min(len(SPR) - 1, int(round(theta / 15)))
        size = 160 * sc / ppu * getattr(self, "SIZE_MUL", 1.0)
        if size < 14:                                       # 很遠很小：簡化畫法
            pygame.draw.line(surf, (215, 220, 228), tail[:2], nose[:2], 2)
            flame()
            return
        phi = math.degrees(math.atan2(-(nose[1] - tail[1]), nose[0] - tail[0]))
        rot = int(round((phi - 90) / 8)) * 8
        sq = max(8, int(size / 4) * 4)
        key = (id(SPR), idx, rot, sq)
        img = _MISSILE_CACHE.get(key)
        if img is None:
            if len(_MISSILE_CACHE) > 400:
                _MISSILE_CACHE.clear()
            img = pygame.transform.rotozoom(SPR[idx], rot, sq / 160.0)
            _MISSILE_CACHE[key] = img
        toward_viewer = theta > 90                          # 迎面而來：尾焰在彈體後方
        if toward_viewer:
            flame()
        surf.blit(img, img.get_rect(center=(int(sx), int(sy))))
        if not toward_viewer:
            flame()


ROCKET_SPRITES = []           # 炸彈火箭 13 個角度（黃色卡通火箭）


def load_rocket_sprites():
    path = find_asset("rocket_sprites.png")
    if not path:
        print("  [MISS] rocket_sprites.png -> 炸彈火箭改用飛彈外觀")
        return
    try:
        strip = pygame.image.load(path).convert_alpha()
        h = strip.get_height()
        ROCKET_SPRITES[:] = [strip.subsurface((i * h, 0, h, h)).copy() for i in range(strip.get_width() // h)]
        print(f"  [OK]   炸彈火箭 3D 精靈 {len(ROCKET_SPRITES)} 個角度")
    except pygame.error as e:
        print(f"  [FAIL] rocket_sprites.png：{e}")


class BombRocket3D(Missile3D):
    """
    炸彈火箭：黃色卡通火箭，鎖定自己的目標追蹤（8 枚各追不同敵人）。
    命中時範圍爆炸；沒打中、燃料耗盡也會自爆。
    """
    SPEED = 36.0
    TURN = 0.22                          # 比一般飛彈更靈活
    SIZE_MUL = 1.5                       # 彈身放大：黃色火箭是主角
    FLAME = 0.5                          # 尾焰縮小一半、煙霧減量，才不會把短胖的彈身淹沒
    SMOKE = False
    NOSE_OFF, TAIL_OFF = 48, 52
    PPU = 160 / 140.0
    BLAST = 260.0

    def __init__(self, x, y, z, vx, vy, vz, lock):
        super().__init__(x, y, z, 1, dmg=8)
        self.vx, self.vy, self.vz = vx, vy, vz
        self.lock = lock
        self.life = 190
        self.radius = 42
        self.blasted = False

    def sprites(self):
        return ROCKET_SPRITES or MISSILE_SPRITES

    def update(self, target, particles):
        lk = self.lock
        if lk is not None and getattr(lk, "alive", True) and not getattr(lk, "dying", False):
            target = lk                                  # 追自己鎖定的目標；目標倒下才改追最近的
        super().update(target, particles)


SHOT_SPRITES = {}             # 小兵子彈的彗頭：gold / fireball / meteor（隕石為 8 格翻滾動畫）
SHOT_SIZE = 1 / 3             # 小兵子彈整體大小（彗頭、尾巴寬度與長度、命中範圍一起縮放）


def make_shot_sprites(S=72):
    """用程式產生三種小兵子彈的彗頭（原創，參考使用者提供的模板風格）。"""
    if numpy is None:
        return {}
    np = numpy
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    u = (xx + 0.5) / S * 2 - 1
    v = (yy + 0.5) / S * 2 - 1
    r = np.sqrt(u * u + v * v)
    sph = np.sqrt(np.clip(1 - (r / 0.78) ** 2, 0, 1))
    inside = np.clip((0.78 - r) / 0.04, 0, 1)
    lit = np.clip(sph * 0.6 + np.clip(-(u + v) * 0.5, 0, 1) * 0.5, 0, 1)

    def to_surf(rgb, a):
        surf = pygame.Surface((S, S), pygame.SRCALPHA)
        pygame.surfarray.pixels3d(surf)[:] = np.transpose(np.clip(rgb, 0, 255), (1, 0, 2)).astype(np.uint8)
        pygame.surfarray.pixels_alpha(surf)[:] = (np.clip(a, 0, 1).T * 255).astype(np.uint8)
        return surf

    def ramp(t, stops, cols):
        cols = np.array(cols, np.float32)
        return np.stack([np.interp(t, stops, cols[:, k]) for k in range(3)], -1)

    def hilite(cx, cy, rad, strength):
        return np.clip(1 - np.hypot(u - cx, v - cy) / rad, 0, 1) ** 2 * strength

    out = {}
    # 金色能量球：白熱核心 -> 金黃 -> 橘
    rgb = ramp(lit, [0.0, 0.45, 0.8, 1.0], [(225, 110, 10), (255, 185, 30), (255, 230, 120), (255, 252, 230)])
    glow = 0.5 * np.exp(-((r - 0.8) / 0.16) ** 2)
    rgb = rgb * inside[..., None] + np.array([255, 190, 40], np.float32) * (1 - inside[..., None])
    rgb += (hilite(-0.3, -0.35, 0.25, 1.0) * 255)[..., None]
    out["gold"] = to_surf(rgb, np.maximum(inside, glow))
    # 亮面火球：橘紅卡通球 + 黃色熾熱核心 + 兩個白色高光
    rgb = ramp(sph, [0.0, 0.5, 1.0], [(205, 55, 30), (240, 95, 45), (255, 130, 70)])
    core = np.clip(1 - np.hypot(u + 0.05, v + 0.02) / 0.42, 0, 1) ** 1.5
    rgb = rgb * (1 - core[..., None]) + np.array([255, 215, 70], np.float32) * core[..., None]
    rgb += (hilite(-0.32, -0.38, 0.2, 0.9) * 255 + hilite(0.3, -0.42, 0.12, 0.6) * 255)[..., None]
    out["fireball"] = to_surf(rgb, inside)
    # 隕石：凹凸岩石、坑洞、邊緣映著火光；8 格翻滾
    rng = np.random.default_rng(5)
    lat = rng.random((24, 24)).astype(np.float32)

    def vn(x, y):
        x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int); fx = x - x0; fy = y - y0
        fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy)
        g = lambda a, b: lat[b % 24, a % 24]
        return (g(x0, y0) * (1 - fx) + g(x0 + 1, y0) * fx) * (1 - fy) + (g(x0, y0 + 1) * (1 - fx) + g(x0 + 1, y0 + 1) * fx) * fy

    ang = np.arctan2(v, u)
    frames = []
    for f in range(8):
        rot = f / 8 * math.tau
        edge = 0.70 + 0.07 * vn(np.cos(ang + rot) * 2 + 5, np.sin(ang + rot) * 2 + 5)     # 凹凸輪廓
        body = np.clip((edge - r) / 0.03, 0, 1)
        sp = np.sqrt(np.clip(1 - (r / np.maximum(edge, 0.3)) ** 2, 0, 1))
        tu = u * np.cos(rot) - v * np.sin(rot); tv = u * np.sin(rot) + v * np.cos(rot)
        bump = vn(tu * 5 + 10, tv * 5 + 10) * 0.6 + vn(tu * 11 + 3, tv * 11 + 7) * 0.4
        crater = np.clip((bump - 0.62) / 0.12, 0, 1)
        shade = np.clip(0.25 + 0.75 * (sp * 0.55 + np.clip(-(u + v) * 0.6, 0, 1) * 0.45) - crater * 0.35 + (bump - 0.5) * 0.25, 0.05, 1)
        rgb = np.array([82, 84, 98], np.float32) * shade[..., None] * 1.25
        rim = (1 - sp) ** 3 * body
        rgb += np.array([255, 120, 30], np.float32) * rim[..., None] * 0.9                    # 邊緣映著火焰橘光
        frames.append(to_surf(rgb, body))
    out["meteor"] = frames
    return out


RAINBOW = ("red", "orange", "yellow", "green", "blue", "indigo", "violet")
BUBBLE_COLORS = {"red": (255, 70, 70), "orange": (255, 150, 40), "yellow": (255, 225, 60), "green": (80, 235, 110),
                 "blue": (70, 180, 255), "indigo": (100, 100, 255), "violet": (190, 95, 255),
                 "pink": (255, 110, 215)}
MINIBOSS_BUBBLE = ("pink", "blue", "violet")       # 小魔王 1 粉紅、2 藍、3 紫（黑色泡泡在暗背景上看不清楚）
BUBBLE_FRAMES = {}


def make_bubble_frames(S=96, n=8):
    """
    電漿泡泡（原創，參考使用者提供的圖）：半透明發光球體。
      - 內部：會旋轉翻騰的雲霧紋理，中央較透明
      - 菲涅耳邊緣：越靠邊緣越亮、越不透明（立體球感）
      - 新月形高光：左下側特別亮的一彎光弧
      - 外圍柔和光暈 + 幾顆閃爍的小光點
    """
    if numpy is None:
        return {}
    np = numpy
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    u = (xx + 0.5) / S * 2 - 1
    v = (yy + 0.5) / S * 2 - 1
    r = np.hypot(u, v)
    R0 = 0.74
    sph = np.sqrt(np.clip(1 - (r / R0) ** 2, 0, 1))
    body = np.clip((R0 - r) / 0.025, 0, 1)
    rng = np.random.default_rng(9)
    lat = rng.random((16, 16)).astype(np.float32)

    def vn(x, y):
        x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int); fx = x - x0; fy = y - y0
        fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy)
        g = lambda a, b: lat[b % 16, a % 16]
        return (g(x0, y0) * (1 - fx) + g(x0 + 1, y0) * fx) * (1 - fy) + (g(x0, y0 + 1) * (1 - fx) + g(x0 + 1, y0 + 1) * fx) * fy

    dirx, diry = -0.62, 0.55                                     # 新月高光的方向（左下）
    nd = math.hypot(dirx, diry)
    cres = np.clip((u * dirx + v * diry) / nd / np.maximum(r, 1e-3), 0, 1) ** 2 * (r / R0) ** 5
    fres = (1 - sph) ** 2.5
    glow = 0.38 * np.exp(-((r - R0) / 0.1) ** 2) * (r > R0 * 0.98)
    spark_pos = [(rng.uniform(0, math.tau), rng.uniform(0.82, 0.97)) for _ in range(7)]
    out = {}
    for name, col in BUBBLE_COLORS.items():
        c = np.array(col, np.float32)
        frames = []
        for f in range(n):
            ang = f / n * math.tau * 0.5
            tw = ang + r * 2.2                                   # 越往外扭得越多：漩渦狀的雲霧
            cu, cv = u * np.cos(tw) - v * np.sin(tw), u * np.sin(tw) + v * np.cos(tw)
            cloud = vn(cu * 3.5 + 8, cv * 3.5 + 8) * 0.65 + vn(cu * 7 + 3, cv * 7 + 5) * 0.35
            inner = c * (0.18 + 0.72 * cloud[..., None])                    # 內部壓暗：在白色雪地上才有對比
            rim = c * 0.45 + 255 * 0.55
            k = np.clip(fres * 1.2 + cres * 1.4, 0, 1)[..., None]
            rgb = inner * (1 - k) + rim * k
            a = (0.42 + 0.3 * cloud * (1 - 0.4 * sph) + 0.75 * fres + 0.9 * cres) * body   # 降低透明度
            a = np.maximum(a, glow)
            rgb = np.where((r > R0)[..., None], c * 0.8 + 50, rgb)
            for th, rr in spark_pos:                             # 閃爍小光點
                tw_ = 0.5 + 0.5 * math.sin(f / n * math.tau * 2 + th * 3)
                px, py = math.cos(th) * rr, math.sin(th) * rr
                d = np.hypot(u - px, v - py)
                sp = np.clip(1 - d / 0.035, 0, 1) * tw_
                a = np.maximum(a, sp)
                rgb = rgb * (1 - sp[..., None]) + 255 * sp[..., None]
            surf = pygame.Surface((S, S), pygame.SRCALPHA)
            pygame.surfarray.pixels3d(surf)[:] = np.transpose(np.clip(rgb, 0, 255), (1, 0, 2)).astype(np.uint8)
            pygame.surfarray.pixels_alpha(surf)[:] = (np.clip(a, 0, 1).T * 255).astype(np.uint8)
            frames.append(surf)
        out[name] = frames
    return out


def _ribbon(surf, pts, widths, color):
    """沿一串螢幕座標畫漸變寬度的帶狀多邊形（彗星尾、火舌、火焰）。"""
    if len(pts) < 2:
        return
    left, right = [], []
    for i, (x, y) in enumerate(pts):
        a = pts[min(i + 1, len(pts) - 1)]
        b = pts[max(i - 1, 0)]
        dx, dy = a[0] - b[0], a[1] - b[1]
        L = math.hypot(dx, dy) or 1.0
        w = widths[i]
        left.append((x - dy / L * w, y + dx / L * w))
        right.append((x + dy / L * w, y - dx / L * w))
    pygame.draw.polygon(surf, color, left + right[::-1])


class EnemyBullet3D:
    """敵彈：朝攝影機飛來，越近越大 —— 這是 3D 射擊最直觀的威脅感。"""

    def __init__(self, x, y, z, vx, vy, vz, color=(255, 120, 90), kind=None, bubble=None):
        self.x, self.y, self.z = x, y, z
        self.vx, self.vy, self.vz = vx, vy, vz
        self.color = color
        self.kind = kind              # None：一般光點；gold / fireball / meteor：小兵各自的 3D 武器
        self.alive = True
        self.radius = 26 * SHOT_SIZE if kind else 26                 # 命中範圍跟著外觀縮小：看到多大就是多大
        self.t = random.randint(0, 99)
        self.seed = random.random() * 10
        self.bubble = bubble          # 電漿泡泡的顏色名稱（小魔王與母艦）

    def update(self):
        self.t += 1
        self.x += self.vx
        self.y += self.vy
        self.z += self.vz
        if self.z <= NEAR + 6 or self.z > FAR or abs(self.x) > 2400 or abs(self.y) > 1800:
            self.alive = False

    def pos(self):
        return (self.x, self.y, self.z)

    def _tail(self, length, n=9):
        """尾巴的螢幕座標：沿飛行方向的反方向延伸（子彈朝你飛來，尾巴往敵人那邊）。"""
        m = math.sqrt(self.vx ** 2 + self.vy ** 2 + self.vz ** 2) or 1.0
        pts = []
        for i in range(n):
            k = i / (n - 1)
            q = project(self.x - self.vx / m * length * k, self.y - self.vy / m * length * k,
                        self.z - self.vz / m * length * k)
            if q:
                pts.append((q[0], q[1], q[2], k))
        return pts

    def draw(self, surf, p):
        sx, sy, sc = p
        if self.bubble and self.bubble in BUBBLE_FRAMES:          # 電漿泡泡：微微脈動、內部翻騰
            r = 30 * sc * (1 + 0.06 * math.sin(self.t * 0.25 + self.seed))
            img = scaled(BUBBLE_FRAMES[self.bubble][(self.t // 3) % 8], max(6, int(r * 2 / 0.74) // 2 * 2))
            surf.blit(img, img.get_rect(center=(int(sx), int(sy))))
            return
        kind = self.kind if self.kind in SHOT_SPRITES else None
        if kind is None:
            r = max(2, int(26 * sc))
            blit_glow(surf, (int(sx), int(sy)), r * 3, tuple(c // 3 for c in self.color))
            pygame.draw.circle(surf, self.color, (int(sx), int(sy)), r)
            pygame.draw.circle(surf, WHITE, (int(sx), int(sy)), max(1, r // 3))
            return
        t = self.t
        if kind == "gold":                                         # 金色能量球：又直又長的三層金色光尾
            r = 24 * sc * SHOT_SIZE
            tail = self._tail(300 * SHOT_SIZE)
            pts = [(q[0], q[1]) for q in tail]
            for wm, col in ((1.0, (215, 125, 15)), (0.6, (255, 200, 60)), (0.25, (255, 250, 215))):
                _ribbon(surf, pts, [r * wm * (1 - q[3]) ** 1.3 * q[2] / max(sc, 1e-3) for q in tail], col)
            blit_glow(surf, (int(sx), int(sy)), max(3, int(r * 2.6)), (130, 85, 10))
            img = scaled(SHOT_SPRITES["gold"], max(6, int(r * 2.6) // 2 * 2))
        elif kind == "fireball":                                    # 亮面火球：5 條長短不一、會擺動的火舌
            r = 28 * sc * SHOT_SIZE
            for j, (off, ln, col) in enumerate(((-0.9, 0.75, (200, 55, 30)), (0.9, 0.7, (200, 55, 30)),
                                                (-0.45, 1.0, (240, 95, 45)), (0.45, 0.9, (240, 95, 45)),
                                                (0.0, 0.85, (255, 140, 85)))):
                tail = self._tail(240 * ln * SHOT_SIZE, 8)
                if len(tail) < 2:
                    continue
                pts = []
                for i, (qx, qy, qs, k) in enumerate(tail):
                    a = tail[min(i + 1, len(tail) - 1)]; b = tail[max(i - 1, 0)]
                    dx, dy = a[0] - b[0], a[1] - b[1]; L = math.hypot(dx, dy) or 1.0
                    o = off * r * (0.5 + 0.9 * k) + math.sin(t * 0.35 + j * 1.7 + k * 4) * r * 0.25 * k
                    pts.append((qx - dy / L * o, qy + dx / L * o))
                _ribbon(surf, pts, [r * 0.42 * (1 - q[3]) ** 0.9 * q[2] / max(sc, 1e-3) for q in tail], col)
            img = scaled(SHOT_SPRITES["fireball"], max(6, int(r * 2.6) // 2 * 2))
        else:                                                       # 隕石：寬闊、邊緣搖曳的紅橘黃火焰
            r = 32 * sc * SHOT_SIZE
            tail = self._tail(320 * SHOT_SIZE, 10)
            pts = [(q[0], q[1]) for q in tail]
            for wm, col in ((1.45, (225, 45, 20)), (1.05, (255, 125, 30)), (0.62, (255, 215, 70))):
                ws = [r * wm * (1 - q[3]) ** 0.75 * q[2] / max(sc, 1e-3) * (1 + 0.18 * math.sin(t * 0.5 + i * 1.9 + self.seed))
                      for i, q in enumerate(tail)]
                _ribbon(surf, pts, ws, col)
            img = scaled(SHOT_SPRITES["meteor"][(t // 3) % 8], max(6, int(r * 2.6) // 2 * 2))
        surf.blit(img, img.get_rect(center=(int(sx), int(sy))))


class Explosion3D:
    def __init__(self, pos, frames, delay=3, world_size=260):
        self.x, self.y, self.z = pos
        if id(frames) in EXPLOSION_FLIPS and random.random() < 0.5:
            frames = EXPLOSION_FLIPS[id(frames)]          # 一半的爆炸用旋轉 180° 的版本，看起來不重複
        self.frames = frames
        self.index = 0
        self.timer = 0
        self.delay = delay
        self.world_size = world_size
        self.alive = True

    def frame_time(self):
        """每格停留幀數：處理過的畫格用不均勻節奏，delay 是整體快慢（3 = 標準）。"""
        if EXPLOSION_ALPHA and len(self.frames) == len(EXPLOSION_TIMING):
            return max(1, round(EXPLOSION_TIMING[self.index] * self.delay / 3))
        return self.delay

    def update(self, world_speed):
        self.z -= world_speed * 0.25
        self.timer += 1
        if self.index < len(self.frames) and self.timer >= self.frame_time():
            self.timer = 0
            self.index += 1
            if self.index >= len(self.frames):
                self.alive = False

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        if self.index >= len(self.frames):
            return
        sx, sy, sc = p
        size = max(6, int(self.world_size * sc))
        if EXPLOSION_ALPHA:
            if size <= 420:
                img = scaled(self.frames[self.index], size, smooth=True)
            else:                                        # 近距離的大爆炸：平滑放大，邊緣不會有鋸齒
                img = pygame.transform.smoothscale(self.frames[self.index], (min(size, 900), min(size, 900)))
            if self.index == len(self.frames) - 1:       # 最後一格（煙霧）逐漸淡出
                img = img.copy()
                img.set_alpha(int(255 * (1 - self.timer / max(1, self.frame_time()))))
            surf.blit(img, img.get_rect(center=(int(sx), int(sy))))
            return
        img = scaled(self.frames[self.index], size, smooth=False)
        if ICE:
            surf.blit(img, img.get_rect(center=(int(sx), int(sy))))
        else:
            surf.blit(img, img.get_rect(center=(int(sx), int(sy))),
                      special_flags=pygame.BLEND_RGB_ADD)


# ---------------------------------------------------------------
# 武器系統
# ---------------------------------------------------------------
# 設計原則：每把武器解決不同的問題，不是數值高低的排列。
#   PULSE  基礎、無限彈藥，其他武器打完一定回得來
#   SPREAD 近距離廣角，打成群的小怪
#   COMET   藍焰彗星：螺旋交纏前進、命中範圍大、可穿透 3 個敵人
#   HOMING 自動鎖定，不用瞄準，打高機動目標
#   PLASMA 慢速大彈 + 範圍傷害，清場
#   FIRE   一次 6 枚 3D 火焰彈，繞著前進方向螺旋旋轉，命中會爆炸
# cd_lv / dmg_lv / n_lv 是三個等級各自的冷卻、單發傷害、發數。
# 數值是靶場實測後配平的：每把武器只在「一個維度」最強，避免出現全能王。
WEAPONS = {
    "PULSE":  {"label": "PULSE",  "key": pygame.K_1, "color": (150, 230, 255),
               "ammo": None, "cd_lv": (9, 8, 7),    "dmg_lv": (1, 1, 1), "n_lv": (1, 2, 3),
               "desc": "Rapid beam - infinite ammo"},
    "SPREAD": {"label": "SPREAD", "key": pygame.K_2, "color": (255, 200, 90),
               "ammo": 70,   "cd_lv": (16, 14, 12), "dmg_lv": (1, 1, 2), "n_lv": (5, 7, 9),
               "desc": "Widest cone - crowd control"},
    "COMET":  {"label": "COMET",  "key": pygame.K_3, "color": (60, 170, 255),
               "ammo": 40,   "cd_lv": (22, 20, 18), "dmg_lv": (2, 3, 4), "n_lv": (2, 3, 3),
               "desc": "Blue flame comets - spiral & pierce"},
    "LASER":  {"label": "LASER",  "key": pygame.K_3, "color": (120, 255, 190),
               "ammo": 900,  "cd_lv": (10, 8, 6),   "dmg_lv": (1, 2, 3), "n_lv": (1, 1, 1),
               "desc": "Sustained pierce - burns ammo"},
    "HOMING": {"label": "HOMING", "key": pygame.K_4, "color": (255, 150, 60),
               "ammo": 44,   "cd_lv": (22, 20, 18), "dmg_lv": (2, 2, 3), "n_lv": (2, 2, 3),
               "desc": "Auto-lock - no aiming needed"},
    "PLASMA": {"label": "PLASMA", "key": pygame.K_5, "color": (200, 120, 255),
               "ammo": 30,   "cd_lv": (28, 26, 24), "dmg_lv": (3, 5, 7), "n_lv": (1, 1, 1),
               "desc": "Splash blast - hits everything near"},
    "FIRE":   {"label": "FIRE",   "key": pygame.K_6, "color": (255, 120, 30),
               "ammo": 18,   "cd_lv": (32, 28, 24), "dmg_lv": (3, 4, 5), "n_lv": (6, 6, 6),
               "desc": "6 spiral fireballs - massive damage"},
    # 原子光束：按住蓄力、放開發射。ammo = 可發射次數；cd_lv = 發射後的冷卻幀數；
    # dmg_lv = 光束每次判定（每 4 幀）的傷害。
    "ATOMIC": {"label": "ATOMIC", "key": pygame.K_7, "color": (80, 170, 255),
               "ammo": 4,    "cd_lv": (70, 60, 50), "dmg_lv": (3, 4, 6), "n_lv": (1, 1, 1),
               "desc": "Hold to charge, release to unleash"},
}
WEAPON_ORDER = ["PULSE", "SPREAD", "COMET", "HOMING", "PLASMA", "FIRE", "ATOMIC"]   # 第 3 種：雷射換成藍焰彗星
DROPPABLE_WEAPONS = WEAPON_ORDER[1:]     # PULSE 是內建的，不會掉落

# 開局附送的武器與彈藥（一開始就能切換武器、試用原子光束）。
# 想要開局只有主砲，把這裡改成空的 {} 即可。
STARTING_LOADOUT = {"SPREAD": 40, "ATOMIC": 2}
# 關卡劇本（共 5 關）：
#   第 1~3 關：先打小兵，打完規定數量後，場面清空、該關的小魔王單獨登場；擊敗才進下一關
#   第 4 關：中魔王母艦（金屬紫）     第 5 關：最終魔王虛淵
MINI_BOSS_WAVES = (1, 2, 3)
MINI_BOSS_STYLE = (("MINI BOSS 1", (240, 120, 210)),     # 原色（粉紫）
                   ("MINI BOSS 2", (90, 170, 255)),      # 藍色
                   ("MINI BOSS 3", (150, 150, 170)))     # 黑色（字用銀灰，雪地上才看得清）
MID_BOSS_WAVE = 4             # 中魔王：母艦
FINAL_BOSS_WAVE = 5           # 最終魔王：虛淵


def gradient_map(surface, stops):
    """
    換色：依原圖每個像素的明暗，對應到新的漸層色（stops = [(位置0~1, (r,g,b)), ...]）。
    陰影、高光、細節完整保留，只換掉色調。沒有 numpy 時回傳原圖。
    """
    if numpy is None:
        return surface
    np = numpy
    out = surface.copy()
    rgb = pygame.surfarray.array3d(surface).astype(np.float32) / 255.0
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    lo, hi = np.percentile(lum[pygame.surfarray.array_alpha(surface) > 40], [2, 98]) \
        if (pygame.surfarray.array_alpha(surface) > 40).any() else (0.0, 1.0)
    lum = np.clip((lum - lo) / max(hi - lo, 1e-3), 0, 1)              # 拉滿明暗範圍，金屬感才夠
    pos = np.array([p for p, _ in stops], np.float32)
    col = np.array([c for _, c in stops], np.float32)
    res = np.stack([np.interp(lum, pos, col[:, k]) for k in range(3)], axis=-1)
    pygame.surfarray.pixels3d(out)[:] = np.clip(res, 0, 255).astype(np.uint8)
    return out


SAUCER_BLUE = ((0.0, (8, 20, 60)), (0.45, (30, 95, 210)), (0.8, (120, 200, 255)), (1.0, (230, 248, 255)))
SAUCER_BLACK = ((0.0, (4, 4, 8)), (0.5, (28, 30, 38)), (0.85, (95, 100, 118)), (1.0, (210, 215, 230)))
METAL_PURPLE = ((0.0, (14, 4, 26)), (0.35, (60, 20, 105)), (0.65, (130, 70, 200)),
                (0.85, (200, 160, 245)), (1.0, (255, 245, 255)))


# ---------------------------------------------------------------
# 即時合成音效（不需要額外音效檔；沒有 numpy 時自動略過）
# ---------------------------------------------------------------
def synth_sounds():
    if numpy is None or not pygame.mixer.get_init():
        return {}
    np = numpy
    try:
        sr, size, ch = pygame.mixer.get_init()
        rng = np.random.default_rng(3)

        def t_(d):
            return np.arange(int(sr * d)) / sr

        def lowpass(x, fc):
            X = np.fft.rfft(x)
            f = np.fft.rfftfreq(len(x), 1 / sr)
            return np.fft.irfft(X / (1 + (f / fc) ** 2), len(x))

        def mk(x, vol=0.8):
            x = np.clip(x / (np.max(np.abs(x)) + 1e-9), -1, 1) * vol
            a = (x * 32767).astype(np.int16)
            if ch == 2:
                a = np.repeat(a[:, None], 2, axis=1)
            return pygame.sndarray.make_sound(np.ascontiguousarray(a))

        out = {}
        # 蓄力：音高一路往上爬，顫音越來越快
        t = t_(1.4)
        f = 70 + 380 * (t / 1.4) ** 1.5
        ph = 2 * np.pi * np.cumsum(f) / sr
        trem = 1 + 0.35 * np.sin(2 * np.pi * (4 + 18 * t / 1.4) * t)
        x = (np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.25 * np.sin(3 * ph)) * trem
        x += lowpass(rng.standard_normal(len(t)), 900) * 3 * (t / 1.4)
        out["charge"] = mk(x * np.clip(t / 0.3, 0, 1) * (0.3 + 0.7 * t / 1.4), 0.55)
        # 光束：低頻咆哮 + 嗡鳴，加破音
        t = t_(2.0)
        roar = np.cumsum(rng.standard_normal(len(t)))
        roar = lowpass(roar - lowpass(roar, 30), 700)
        buzz = np.sign(np.sin(2 * np.pi * 55 * t)) * 0.5 + np.sin(2 * np.pi * 82.5 * t)
        x = np.tanh((roar / (np.std(roar) + 1e-9) * 0.8 + lowpass(buzz, 900)) * 1.6)
        env = np.clip(t / 0.05, 0, 1) * np.clip((2.0 - t) / 0.5, 0, 1)
        out["beam"] = mk(x * env, 0.75)
        # 震波：下沉的低頻掃頻 + 噪音爆破
        t = t_(1.1)
        f = 160 * np.exp(-t * 3.2) + 35
        x = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 2.2)
        x += lowpass(rng.standard_normal(len(t)), 500) * 4 * np.exp(-t * 7)
        out["shock"] = mk(x, 0.9)
        # 切換武器：短促的提示音
        t = t_(0.07)
        f = 880 + 440 * t / 0.07
        x = np.sign(np.sin(2 * np.pi * np.cumsum(f) / sr)) * np.exp(-t * 45)
        out["switch"] = mk(x, 0.25)
        out["locked"] = mk(np.sign(np.sin(2 * np.pi * 180 * t)) * np.exp(-t * 30), 0.25)

        # ===== 每種武器的發射音效（主砲沿用使用者的 shoot.wav） =====
        hp = lambda x, fc: x - lowpass(x, fc)
        # 散彈：幾顆彈丸接連的短促爆音 + 低頻悶響
        t = t_(0.24)
        x = np.zeros(len(t))
        for off in (0.0, 0.012, 0.026):
            k = np.clip(t - off, 0, None)
            x += lowpass(rng.standard_normal(len(t)), 3200) * np.exp(-k * 28) * (t >= off)
        x += np.sin(2 * np.pi * 90 * t) * np.exp(-t * 18) * 1.5
        out["w_SPREAD"] = mk(np.tanh(x * 1.4), 0.42)
        # 藍焰彗星：冰冷空靈的呼嘯（上揚音高 + 顫音 + 氣流聲）
        t = t_(0.40)
        f = 900 + 900 * (t / 0.40) ** 0.7
        tone = np.sin(2 * np.pi * np.cumsum(f * (1 + 0.03 * np.sin(2 * np.pi * 30 * t))) / sr)
        air = hp(lowpass(rng.standard_normal(len(t)), 5000), 1200)
        env = np.clip(t / 0.02, 0, 1) * np.exp(-t * 7)
        out["w_COMET"] = mk((tone * 0.6 + air * 1.2) * env, 0.34)
        # 追蹤飛彈：點火聲 + 上升的推進器嘶鳴
        t = t_(0.55)
        click = np.exp(-t * 400) * np.sign(np.sin(2 * np.pi * 1800 * t))
        hiss = lowpass(rng.standard_normal(len(t)), 1600) * np.clip(t / 0.04, 0, 1) * np.exp(-t * 4.5)
        rise = np.sin(2 * np.pi * np.cumsum(120 + 260 * t / 0.55) / sr) * np.exp(-t * 4) * 0.6
        out["w_HOMING"] = mk(click * 0.8 + hiss * 2.2 + rise, 0.4)
        # 電漿：「啵嗡」（頻率調變、音高快速下墜）
        t = t_(0.32)
        fc = 220 * np.exp(-t * 7) + 60
        mod = np.sin(2 * np.pi * np.cumsum(fc * 2) / sr) * 4 * np.exp(-t * 6)
        x = np.sin(2 * np.pi * np.cumsum(fc) / sr + mod)
        out["w_PLASMA"] = mk(x * np.clip(t / 0.005, 0, 1) * np.exp(-t * 7), 0.42)
        # 火焰彈：低沉的火焰呼嘯 + 劈啪爆裂
        t = t_(0.50)
        roar = lowpass(rng.standard_normal(len(t)), 1100) * np.clip(t / 0.03, 0, 1) * np.exp(-t * 5)
        crack = np.zeros(len(t))
        for _ in range(14):
            i = rng.integers(0, len(t) - 200)
            crack[i:i + 60] += rng.standard_normal(60) * np.exp(-np.arange(60) / 12)
        crack = hp(crack, 2500) * np.exp(-t * 4)
        rumble = np.sin(2 * np.pi * 58 * t) * np.exp(-t * 6)
        out["w_FIRE"] = mk(np.tanh(roar * 2.6 + crack * 0.35 + rumble * 1.3), 0.45)   # 轟鳴為主、劈啪點綴
        # 原子吐息：發射（超低頻轟擊 + 閃爍上揚和弦 + 氣流）
        t = t_(1.3)
        sub = np.sin(2 * np.pi * np.cumsum(70 * np.exp(-t * 2) + 32) / sr) * np.exp(-t * 2.2) * 2.0
        chord = sum(np.sin(2 * np.pi * np.cumsum(fq * (1 + 0.6 * t / 1.3)) / sr) for fq in (440, 660, 880))
        chord *= (0.5 + 0.5 * np.sin(2 * np.pi * 14 * t)) * np.clip(t / 0.08, 0, 1) * np.exp(-t * 1.8) * 0.5
        whoosh = lowpass(rng.standard_normal(len(t)), 2400) * np.clip(t / 0.05, 0, 1) * np.exp(-t * 3)
        out["nova"] = mk(np.tanh(sub + chord + whoosh * 1.2), 0.8)
        # 原子吐息：引爆（巨大爆炸）
        t = t_(1.8)
        boom = lowpass(rng.standard_normal(len(t)), 420) * np.exp(-t * 2.4) * 4
        sub = np.sin(2 * np.pi * np.cumsum(55 * np.exp(-t * 1.5) + 28) / sr) * np.exp(-t * 1.6) * 1.6
        out["nova_boom"] = mk(np.tanh(boom + sub), 0.95)
        return out
    except Exception as e:
        print(f"[音效] 合成失敗，略過：{e}")
        return {}


class Plasma3D:
    """電漿球：慢速大彈，命中後造成範圍傷害。"""
    def __init__(self, x, y, z, level, dmg):
        self.x, self.y, self.z = x, y, z
        self.vz = 30.0
        self.level = level
        self.radius = 40 + level * 6
        self.splash = 200 + level * 55
        self.dmg = dmg
        self.alive = True
        self.phase = 0.0
        self.hist = []                                               # 最近的位置：畫拖曳的光點尾巴
        rr = random.Random(random.randint(0, 99999))
        self.jit = [(rr.uniform(-1, 1), rr.uniform(-1, 1), rr.uniform(0.75, 1.25)) for _ in range(16)]

    def update(self):
        self.hist.append((self.x, self.y, self.z))
        if len(self.hist) > 14:
            self.hist.pop(0)
        self.z += self.vz
        self.phase += 0.3
        if self.z > FAR:
            self.alive = False

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        r = max(3, int((30 + self.level * 5) * sc * (1 + 0.12 * math.sin(self.phase))))
        n = len(self.hist)
        for i in range(n - 1, -1, -2):                               # 拖曳尾巴：由新到舊越來越小、粉紅 -> 深紫
            hx, hy, hz = self.hist[i]
            jx, jy, js = self.jit[i]
            k = (i + 1) / (n + 1)
            q = project(hx + jx * 14, hy + jy * 14, hz)
            if not q:
                continue
            rr = max(1, int((30 + self.level * 5) * q[2] * (0.18 + 0.55 * k) * js))
            col = (int(130 + 125 * k), int(40 + 90 * k), 255)
            if rr > 4:
                blit_glow(surf, (int(q[0]), int(q[1])), rr * 3, (int(90 * k + 30), 20, int(110 * k + 40)))
            pygame.draw.circle(surf, col, (int(q[0]), int(q[1])), rr)
            pygame.draw.circle(surf, (255, 225, 255), (int(q[0]), int(q[1])), max(1, rr // 3))
        blit_glow(surf, (int(sx), int(sy)), r * 4, (150, 40, 170))   # 彗頭：洋紅光暈、粉紫球體、白熱核心
        pygame.draw.circle(surf, (255, 120, 255), (int(sx), int(sy)), r)
        pygame.draw.circle(surf, (255, 205, 255), (int(sx), int(sy)), max(1, int(r * 0.72)))
        pygame.draw.circle(surf, (255, 250, 255), (int(sx), int(sy)), max(1, int(r * 0.45)))


class Rail3D:
    """軌道炮：高速穿透彈，打到的敵人全部受傷且不消失。"""
    def __init__(self, x, y, z, level, dmg):
        self.x, self.y, self.z = x, y, z
        self.vz = 150.0
        self.level = level
        self.radius = 34 + level * 8
        self.dmg = dmg
        self.alive = True
        self.hit_ids = set()          # 記住打過誰，避免同一個敵人被重複扣血
        self.trail = z

    def update(self):
        self.trail = self.z
        self.z += self.vz
        if self.z > FAR:
            self.alive = False

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        p2 = project(self.x, self.y, max(NEAR + 1, self.trail - self.vz * 1.5))
        w = max(2, int((10 + self.level * 3) * sc))
        if p2:
            pygame.draw.line(surf, (255, 150, 190), (p2[0], p2[1]), (sx, sy), w)
            pygame.draw.line(surf, WHITE, (p2[0], p2[1]), (sx, sy), max(1, w // 3))
        blit_glow(surf, (int(sx), int(sy)), max(6, int(30 * sc)), (120, 40, 70))


def magnet(item, ship, reach=560.0, strength=0.13):
    """
    道具磁吸：進入一定距離後往戰機靠過來。
    3D 空間比 2D 難撿太多（多一個維度要對準），沒有磁吸的話
    道具幾乎都會擦身而過 —— 這是實測玩家撿不到武器包的主因。
    """
    if ship is None:
        return
    dx = ship.x - item.x
    dy = ship.y - item.y
    dz = ship.z - item.z
    d2 = dx * dx + dy * dy + dz * dz
    if d2 > reach * reach or d2 < 1.0:
        return
    pull = strength * (1.0 - math.sqrt(d2) / reach)
    item.x += dx * pull
    item.y += dy * pull
    item.z += dz * pull * 0.5      # z 方向拉一半，避免道具突然衝過頭


def _shock_spiral(arms=4, per_arm=34):
    """球面上的 4 條螺旋臂：緯度由南到北，經度隨緯度扭轉；每點附帶大小權重。"""
    pts = []
    rr = random.Random(3)
    for a in range(arms):
        for j in range(per_arm):
            th = -1.35 + 2.7 * j / (per_arm - 1)
            ph = a * math.tau / arms + 2.3 * th + rr.uniform(-0.12, 0.12)
            pts.append((math.cos(th) * math.cos(ph), math.sin(th), math.cos(th) * math.sin(ph),
                        rr.uniform(0.6, 1.4) * (0.75 + 0.25 * math.cos(th))))
    for _ in range(26):                                             # 臂與臂之間零星的光點：更有質感
        th = rr.uniform(-1.4, 1.4); ph = rr.uniform(0, math.tau)
        pts.append((math.cos(th) * math.cos(ph), math.sin(th), math.cos(th) * math.sin(ph), rr.uniform(0.3, 0.7)))
    return pts


SHOCK_SPIRAL = _shock_spiral()
SHOCK_DOT = []                # [正面光點, 背面光點]：柔邊的綠色光點精靈
SHOCK_BALL = []               # 柔邊能量球（中心透明、往外漸亮、邊緣柔和淡出）


def make_shock_ball(S=256):
    if numpy is None:
        return []
    np = numpy
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    r = np.hypot((xx + 0.5) / S * 2 - 1, (yy + 0.5) / S * 2 - 1) * 1.25   # 能量球本體半徑 = 0.8（外圍留給柔邊）
    shell = np.clip((r - 0.35) / 0.55, 0, 1) ** 1.6                  # 往外漸亮
    edge = np.clip((1.18 - r) / 0.38, 0, 1) ** 2                     # 邊緣柔和淡出（不畫輪廓線）
    a = (0.12 + 0.55 * shell) * edge
    k = np.clip(r, 0, 1)[..., None]
    rgb = np.array([40, 200, 100], np.float32) * (1 - k) + np.array([150, 255, 175], np.float32) * k
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = np.transpose(rgb, (1, 0, 2)).astype(np.uint8)
    pygame.surfarray.pixels_alpha(surf)[:] = (np.clip(a, 0, 1).T * 255).astype(np.uint8)
    return [surf]


def make_shock_dots(S=32):
    surfs = []
    for core, edge in (((235, 255, 235), (80, 255, 120)), ((80, 170, 100), (30, 110, 60))):
        img = pygame.Surface((S, S), pygame.SRCALPHA)
        for i in range(S // 2, 0, -1):
            k = i / (S / 2)
            col = tuple(int(edge[c] * k + core[c] * (1 - k)) for c in range(3))
            a = int(255 * (1 - k) ** 1.4)
            pygame.draw.circle(img, col + (a,), (S // 2, S // 2), i)
        surfs.append(img)
    return surfs


class ShockWave3D:
    """
    衝擊波大絕：一道「能量隧道」從戰機往畫面深處推進，沿途貫穿所有敵人與敵彈。

    3D 感來自這幾件事：
      - 不是一個圓，而是前後排列的多層環 —— 近的大、遠的小，形成往深處收束的錐形
      - 環上是斷續、會抖動旋轉的電弧，不是死板的圓線
      - 環碰到地面的部分會被地形「吃掉」（真的被擋住），並在交界處掀起雪浪
      - 發射瞬間在戰機周圍炸開一顆球形能量殼（以多個截面圓組成，透視下就是立體球）

    和炸彈的分工：炸彈 = 防禦性瞬間清場；衝擊波 = 攻擊性縱深掃蕩。
    """
    SPEED = 52.0
    GROWTH = 7.5                  # 擴張變慢：越飛越遠在畫面上逐漸變小（旋轉著飛向遠方）
    BAND = 170.0
    DAMAGE = 14
    MAX_RADIUS = 1050.0
    SEGS = 72
    LAYERS = 4
    LAYER_GAP = 120.0

    LIFE = 66                     # 壽命（幀）：要比飛到最遠距離（約 70 幀）短，淡出才來得及完成
    FADE = 26                     # 最後 26 幀逐漸淡出

    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z
        self.x0, self.y0 = x, y                                      # 盤旋的中心軸（發射位置）
        self.orbit = random.uniform(0, math.tau)
        self.z0 = z
        self.radius = 155.0
        self.alive = True
        self.hit_ids = set()
        self.life = 0
        self.phase = random.uniform(0, math.tau)

    def update(self, game=None):
        self.z += self.SPEED
        self.radius = min(self.MAX_RADIUS, self.radius + self.GROWTH)
        self.life += 1
        self.phase += 0.13
        self.orbit += 0.15                                           # 繞著發射方向盤旋前進，盤旋半徑越來越大
        amp = min(540.0, 20 + self.life * 8.5)                   # 盤旋半徑要跟球的大小相當，螺旋才看得出來
        self.x = self.x0 + math.cos(self.orbit) * amp
        self.y = self.y0 + math.sin(self.orbit) * amp * 0.8
        if game is not None and self.life % 2 == 0:
            # 環與地面的交界掀起雪浪：沿環取樣，落在地面以下的點就在地表噴雪
            for _ in range(7):
                a = random.uniform(0.15 * math.pi, 0.85 * math.pi)     # 環的下半圈
                wx = self.x + math.cos(a) * self.radius
                wy = self.y + math.sin(a) * self.radius
                g = ground_at(wx, self.z)
                if wy > g:
                    col = (120, 230, 150) if ICE else (150, 255, 160)
                    game.particles.emit(wx, g - 6, self.z, random.uniform(-4, 4),
                                        -random.uniform(9, 18), random.uniform(-4, 6),
                                        random.randint(20, 38), col, random.uniform(11, 17))
        if self.z > FAR or self.life >= self.LIFE:
            self.alive = False

    def fade(self):
        """0~1：開頭 4 幀淡入、最後 FADE 幀淡出（直到消失，不會突然不見）。"""
        return max(0.0, min(1.0, self.life / 4, (self.LIFE - self.life) / self.FADE))

    def covers(self, pos, r=0.0):
        if abs(pos[2] - self.z) > self.BAND:
            return False
        dx = pos[0] - self.x
        dy = pos[1] - self.y
        return dx * dx + dy * dy <= (self.radius + r) ** 2

    def pos(self):
        return (self.x, self.y, self.z)

    def _ring(self, z, radius, rot, wob, segs=None):
        """環上的螢幕座標；被地形擋住的點回傳 None（造成斷口）。"""
        segs = segs or self.SEGS
        pts = []
        for i in range(segs + 1):
            a = i * math.tau / segs + rot
            r = radius * (1 + wob * math.sin(6 * a + self.phase * 1.7))
            wx = self.x + math.cos(a) * r
            wy = self.y + math.sin(a) * r
            if wy > ground_at(wx, z) - 4:
                pts.append(None)
                continue
            p = project(wx, wy, z)
            pts.append(p if p else None)
        return pts

    def _ground_line(self, z, radius):
        """震波平面與地形的交線：沿著冰脊與坡面起伏的亮線，看得出震波正在犁過地面。"""
        runs, cur = [], []
        n = 28
        for i in range(n + 1):
            wx = self.x - radius + 2 * radius * i / n
            gy = ground_at(wx, z)
            inside = (wx - self.x) ** 2 + (gy - self.y) ** 2 <= radius * radius
            p = project(wx, gy - 3, z) if inside else None
            if p:
                cur.append(p)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        return runs

    def draw(self, surf, p):
        """
        綠色能量球（3D 螺旋）：4 條螺旋臂的光點貼著球面持續旋轉。
        朝向鏡頭的正面光點又亮又大、背面的暗而小 —— 看得出是一顆會轉的立體球。
        繪製順序：背面光點 -> 半透明球體 -> 正面光點 -> 邊緣光環。
        """
        sx, sy, sc = p
        Rs = max(6, int(self.radius * sc))
        cx, cy = int(sx), int(sy)
        spin = self.phase * 0.55
        cs, ss = math.cos(spin), math.sin(spin)
        ct, st = math.cos(0.38), math.sin(0.38)                    # 旋轉軸稍微傾斜：更有立體感
        back, front = [], []
        for ux, uy, uz, w in SHOCK_SPIRAL:
            x1, z1 = ux * cs + uz * ss, -ux * ss + uz * cs          # 繞垂直軸自轉
            y2, z2 = uy * ct - z1 * st, uy * st + z1 * ct           # 傾斜
            px_, py_ = cx + x1 * Rs, cy + y2 * Rs
            r = max(1, int(Rs * 0.085 * w * (1.15 - 0.45 * z2)))     # 近大遠小
            (front if z2 < 0 else back).append((px_, py_, r, z2))
        dot = SHOCK_DOT[0] if SHOCK_DOT else None
        fd = self.fade()
        if fd <= 0.02:
            return

        def blob(px_, py_, r, z2, bright):
            if dot is None:
                pygame.draw.circle(surf, (120, 255, 150) if bright else (40, 140, 70), (int(px_), int(py_)), r)
                return
            sz = max(4, int(r * 4 * (0.4 + 0.6 * fd)) // 2 * 2)
            img = scaled(SHOCK_DOT[0 if bright else 1], sz)
            surf.blit(img, img.get_rect(center=(int(px_), int(py_))))

        for b_ in sorted(back, key=lambda q: -q[3]):
            blob(*b_, False)
        if SHOCK_BALL:                                               # 柔邊能量球：沒有銳利的輪廓
            size = max(8, int(Rs * 2.5) // 4 * 4)
            ball = scaled(SHOCK_BALL[0], size)
            if fd < 1:
                ball = ball.copy()
                ball.set_alpha(int(255 * fd))
            surf.blit(ball, ball.get_rect(center=(cx, cy)))
        for f_ in sorted(front, key=lambda q: -q[3]):
            blob(*f_, True)

class AtomicBeam:
    """
    原子光束（原創設計）：按住射擊鍵蓄力，放開後機首噴出一道藍色螺旋光束。

    3D 呈現的關鍵：
      - 光束是一根真正沿 z 軸延伸的圓柱，透視投影後往消失點收束
      - 兩條螺旋能量帶繞著光束軸旋轉，越遠越細、越密
      - 一圈圈光環沿著光束往前推進、越走越小
      - 光束碰到地形（冰脊、山壁）就在撞擊點截斷、持續爆炸並噴雪
      - 光束切成很多段放進深度排序：敵人在光束前面還是後面都畫得正確
    """
    CHARGE_MIN = 24          # 最少蓄力 0.4 秒才發得出去
    CHARGE_MAX = 75          # 蓄滿 1.25 秒自動發射
    NSEG = 26

    def __init__(self, level, charge_ratio):
        self.level = level
        self.charge = charge_ratio
        self.duration = int((75 + 20 * level) * (0.7 + 0.3 * charge_ratio))
        self.radius = (40 + 10 * level) * (0.8 + 0.4 * charge_ratio)
        self.dmg = WEAPONS["ATOMIC"]["dmg_lv"][level - 1] + (2 if charge_ratio >= 0.99 else 0)
        self.t = 0
        self.phase = 0.0
        self.alive = True
        self.origin = (0.0, 0.0, 0.0)
        self.end_z = FAR
        self.hit_terrain = False
        self.segs = []
        self.proj = []
        self.hit_tick = {}

    def envelope(self):
        """寬度包絡：前 8 幀快速張開，最後 18 幀收細消失。"""
        a = min(1.0, self.t / 8.0)
        b = min(1.0, (self.duration - self.t) / 18.0)
        return max(0.0, min(a, b))

    def update(self, game):
        s = game.ship
        self.t += 1
        self.phase += 0.33
        if self.t >= self.duration:
            self.alive = False
            return
        ox, oy, oz = s.transform((0, -3, 80))          # 機首
        self.origin = (ox, oy, oz)
        env = self.envelope()
        R = self.radius * env
        # 找光束盡頭：沿 z 前進，地形高過光束下緣就截斷
        self.end_z = FAR - 60
        self.hit_terrain = False
        z = oz + 60
        while z < FAR - 60:
            if ground_at(ox, z) < oy + R * 0.4:
                self.end_z = z
                self.hit_terrain = True
                break
            z += 70
        # 分段（近處密、遠處疏）供繪製與深度排序
        z0, z1 = oz + 20, self.end_z
        segs = []
        for i in range(self.NSEG):
            z = z0 * (z1 / z0) ** (i / (self.NSEG - 1))
            wob = self.radius * 0.10 * env
            cx = ox + wob * math.sin(z * 0.004 - self.phase * 0.6)
            cy = oy + wob * math.cos(z * 0.0035 - self.phase * 0.5)
            segs.append((cx, cy, z))
        self.segs = segs
        self.proj = [project(*sg) for sg in segs]
        # 傷害：圓柱範圍內的一切，每 4 幀判定一次
        if self.t % 4 == 0:
            for e in list(game.enemies):
                if e.alive and oz < e.z < self.end_z and \
                        (e.x - ox) ** 2 + (e.y - oy) ** 2 <= (R + e.radius) ** 2:
                    game.particles.burst(e.pos(), 4, (120, 200, 255), speed=10)
                    if e.take_damage(self.dmg):
                        e.alive = False
                        game.on_kill(e)
            b = game.boss
            if b and not b.dying and not b.entering and oz < b.z < self.end_z and \
                    (b.x - ox) ** 2 + (b.y - oy) ** 2 <= (R + b.radius) ** 2:
                b.take_damage(self.dmg + 2)
                game.particles.burst(b.pos(), 6, (120, 200, 255), speed=12)
        for eb in game.enemy_bullets:
            if eb.alive and oz < eb.z < self.end_z and (eb.x - ox) ** 2 + (eb.y - oy) ** 2 <= (R * 1.4) ** 2:
                eb.alive = False
        # 沿光束表面迸出火花
        for _ in range(2):
            z = random.uniform(oz + 80, self.end_z)
            a = random.uniform(0, math.tau)
            game.particles.emit(ox + math.cos(a) * R, oy + math.sin(a) * R, z,
                                math.cos(a) * 9, math.sin(a) * 9, random.uniform(-4, 4),
                                random.randint(10, 20), (110, 190, 255), 7.0)
        # 撞擊點：持續爆炸 + 噴雪
        if self.hit_terrain and self.t % 5 == 0:
            hp = (ox + random.uniform(-R, R) * 0.5, oy + R * 0.3, self.end_z)
            game.explosions.append(Explosion3D(hp, game.frames_small, world_size=200 + 60 * self.level))
            for _ in range(5):
                game.particles.emit(hp[0], hp[1], hp[2], random.uniform(-8, 8),
                                    -random.uniform(8, 18), random.uniform(-10, 2),
                                    random.randint(20, 36), (170, 215, 255), 11.0)
        game.shake = max(game.shake, 4 + 3 * self.level * env)

    CHUNK = 5     # 每 5 段合成一塊連續多邊形：接縫從 25 道減到 5 道，仍保有深度排序

    def items(self):
        """回傳要放進深度排序的區塊（以區塊中點的 z 排序）。"""
        out = []
        n = len(self.segs) - 1
        for k0 in range(0, n, self.CHUNK):
            k1 = min(n, k0 + self.CHUNK)
            out.append(((self.segs[k0][2] + self.segs[k1][2]) * 0.5, (k0, k1)))
        return out

    def _strip(self, k0, k1, mul):
        """第 k0..k1 個節點組成的一整塊光束外形（左緣一路往前、右緣一路往回）。"""
        R = self.radius * self.envelope() * mul
        left, right = [], []
        n = len(self.proj)
        for k in range(k0, k1 + 1):
            p = self.proj[k]
            if not p:
                return None
            q = self.proj[k + 1] if k + 1 < n and self.proj[k + 1] else self.proj[k - 1]
            if not q:
                return None
            dx, dy = (q[0] - p[0], q[1] - p[1]) if k + 1 < n else (p[0] - q[0], p[1] - q[1])
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L * R * p[2], dx / L * R * p[2]
            left.append((p[0] + nx, p[1] + ny))
            right.append((p[0] - nx, p[1] - ny))
        return left + right[::-1]

    def _edge(self, i, radius_mul):
        """第 i 段的左右邊緣（螢幕座標），光束寬度依透視縮放。"""
        pa, pb = self.proj[i], self.proj[i + 1]
        if not pa or not pb:
            return None
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        R = self.radius * self.envelope() * radius_mul
        ra, rb = R * pa[2], R * pb[2]
        return [(pa[0] + nx * ra, pa[1] + ny * ra), (pb[0] + nx * rb, pb[1] + ny * rb),
                (pb[0] - nx * rb, pb[1] - ny * rb), (pa[0] - nx * ra, pa[1] - ny * ra)], pa, pb

    def glow_box(self):
        """光暈（含冰面光帶）在螢幕上的大致範圍。"""
        R = self.radius * self.envelope()
        xs, ys = [], []
        for cx, cy, z in self.segs:
            for gx, gy in ((cx - R * 3.4, cy - R * 2.4), (cx + R * 3.4, ground_at(cx, z) + 4)):
                q = project(gx, gy, z)
                if q:
                    xs.append(q[0])
                    ys.append(q[1])
        if not xs:
            return pygame.Rect(0, 0, 0, 0)
        return pygame.Rect(int(min(xs)) - 4, int(min(ys)) - 4,
                           int(max(xs) - min(xs)) + 8, int(max(ys) - min(ys)) + 8)

    def draw_glow(self, layer):
        """
        畫在半透明圖層上（整條光束一次）：
          - 冰面上的光帶：光束把正下方的雪照亮。這是最強的高度線索 ——
            一眼就看得出光束是懸浮在地面上方
          - 外層光暈：讓光束有體積
          - 隨機電弧：沿光束表面劈啪作響
        """
        env = self.envelope()
        R = self.radius * env
        for i in range(len(self.segs) - 1):
            (c0x, _, z0), (c1x, _, z1) = self.segs[i], self.segs[i + 1]
            pts = []
            for cx, z, side in ((c0x, z0, -1), (c1x, z1, -1), (c1x, z1, 1), (c0x, z0, 1)):
                gx = cx + side * R * 3.2
                q = project(gx, ground_at(gx, z) - 2, z)
                if not q:
                    pts = None
                    break
                pts.append(q[:2])
            if pts:
                pygame.draw.polygon(layer, (110, 185, 255, int(70 * env)), pts)
        for i in range(len(self.segs) - 1):
            for mul, alpha in ((2.3, 55), (1.55, 75)):
                e = self._edge(i, mul)
                if e:
                    pygame.draw.polygon(layer, (70, 160, 255, alpha), e[0])
        n = len(self.segs)
        for _ in range(3):                          # 電弧
            k0 = random.randint(0, max(0, n - 7))
            a0 = random.uniform(0, math.tau)
            bolt = []
            for k in range(k0, min(n, k0 + 7)):
                cx, cy, z = self.segs[k]
                a = a0 + random.uniform(-0.5, 0.5)
                r = R * random.uniform(1.2, 1.8)
                q = project(cx + math.cos(a) * r, cy + math.sin(a) * r, z)
                if q:
                    bolt.append(q[:2])
            if len(bolt) > 1:
                pygame.draw.lines(layer, (215, 240, 255, 220), False, bolt, 2)

    # 圓柱明暗：由外到內七層，深藍 -> 青藍 -> 白熱核心（層數多、色差小，漸層才平滑）
    LAYERS = ((1.00, (20, 85, 225)), (0.84, (35, 120, 245)), (0.68, (60, 160, 255)),
              (0.53, (105, 195, 255)), (0.39, (165, 225, 255)), (0.26, (220, 243, 255)),
              (0.14, (255, 255, 255)))

    def draw_segment(self, surf, chunk):
        k0, k1 = chunk
        flick = 1.0 + 0.07 * math.sin(self.phase * 3.1)       # 整條一起閃爍
        for mul, col in self.LAYERS:
            poly = self._strip(k0, k1, mul * (flick if mul < 0.45 else 1.0))
            if poly:
                pygame.draw.polygon(surf, col, poly)
        env = self.envelope()
        hr = self.radius * env * 1.25
        for strand in (0, 1):                          # 兩條螺旋能量帶
            pts = []
            for k in range(k0, k1 + 1):
                cx, cy, z = self.segs[k]
                th = z * 0.006 - self.phase * 1.4 + strand * math.pi
                q = project(cx + math.cos(th) * hr, cy + math.sin(th) * hr, z)
                if q:
                    pts.append(q)
            for a_, b_ in zip(pts, pts[1:]):
                w = max(2, int(11 * a_[2]))
                pygame.draw.line(surf, (120, 200, 255), a_[:2], b_[:2], w)
                pygame.draw.line(surf, (235, 250, 255), a_[:2], b_[:2], max(1, w // 3))
        z0, z1 = self.segs[k0][2], self.segs[k1][2]     # 沿光束往前推進的光環
        span = max(1.0, self.end_z - self.origin[2])
        for k in range(6):
            zr = self.origin[2] + ((self.t * 60 + k * span / 6) % span)
            if z0 <= zr < z1:
                cx, cy, _ = self.segs[k0]
                q = project(cx, cy, zr)
                if q:
                    rr = int(self.radius * env * 1.75 * q[2])
                    if rr > 2:
                        pygame.draw.circle(surf, (60, 160, 255), (int(q[0]), int(q[1])), rr,
                                           max(2, int(7 * q[2])))
                        pygame.draw.circle(surf, (220, 245, 255), (int(q[0]), int(q[1])), rr,
                                           max(1, int(2.5 * q[2])))
        last = self.proj[-1]
        if self.hit_terrain and k1 == len(self.segs) - 1 and last:   # 撞擊點強光
            blit_glow(surf, (int(last[0]), int(last[1])), max(10, int(self.radius * 2.8 * last[2])),
                      (120, 190, 255))


class WeaponPack3D:
    """武器包：撿到就加入武器庫；已經有的話補彈藥並升級。"""
    IMAGES = {}

    @classmethod
    def build_images(cls, font):
        for wid in DROPPABLE_WEAPONS:
            color = WEAPONS[wid]["color"]
            base = pygame.Surface((72, 72), pygame.SRCALPHA)
            pygame.draw.circle(base, (*color, 70), (36, 36), 36)
            # 六角形外框，跟圓形的補給道具一眼就能分辨
            pts = [(36 + 27 * math.cos(math.radians(a)), 36 + 27 * math.sin(math.radians(a)))
                   for a in range(0, 360, 60)]
            pygame.draw.polygon(base, color, pts)
            pygame.draw.polygon(base, WHITE, pts, 3)
            t = font.render(WEAPONS[wid]["label"][0], True, (20, 20, 30))
            base.blit(t, t.get_rect(center=(36, 36)))
            cls.IMAGES[wid] = base

    def __init__(self, pos, wid):
        self.x, self.y, self.z = pos
        self.wid = wid
        self.color = WEAPONS[wid]["color"]
        self.base = self.IMAGES[wid]
        self.vz = -9.0
        self.phase = random.uniform(0, math.tau)
        self.alive = True
        self.radius = 135          # 拾取判定要夠寬，否則玩家幾乎撿不到

    def update(self, world_speed, ship=None):
        self.z += self.vz
        self.phase += 0.09
        self.x += math.sin(self.phase) * 3.0
        self.y += 1.2
        magnet(self, ship)
        if self.z <= NEAR + 10:
            self.alive = False

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        size = max(6, int(125 * sc))
        img = scaled(self.base, size)
        blit_glow(surf, (int(sx), int(sy)), size, tuple(c // 3 for c in self.color))
        surf.blit(img, img.get_rect(center=(int(sx), int(sy))))


class PowerUp3D:
    KINDS = {"power": (YELLOW, "P"), "heal": (GREEN, "+"),
             "shield": (CYAN, "S"), "bomb": (PURPLE, "B")}
    IMAGES = {}          # 全域共用：每種道具只建一張圖

    @classmethod
    def build_images(cls, font):
        """在遊戲啟動時呼叫一次。每個實例各自建圖會讓縮放快取的 id 被回收重用。"""
        for kind, (color, label) in cls.KINDS.items():
            base = pygame.Surface((64, 64), pygame.SRCALPHA)
            pygame.draw.circle(base, (*color, 80), (32, 32), 32)
            pygame.draw.circle(base, color, (32, 32), 24)
            pygame.draw.circle(base, WHITE, (32, 32), 24, 3)
            t = font.render(label, True, (20, 20, 30))
            base.blit(t, t.get_rect(center=(32, 32)))
            cls.IMAGES[kind] = base

    def __init__(self, pos, kind, font=None):
        self.x, self.y, self.z = pos
        self.kind = kind
        self.color = self.KINDS[kind][0]
        self.base = self.IMAGES[kind]
        self.vz = -9.0
        self.phase = random.uniform(0, math.tau)
        self.alive = True
        self.radius = 135          # 拾取判定要夠寬，否則玩家幾乎撿不到

    def update(self, world_speed, ship=None):
        self.z += self.vz
        self.phase += 0.08
        self.x += math.sin(self.phase) * 3.0
        self.y += 1.2
        magnet(self, ship)
        if self.z <= NEAR + 10:
            self.alive = False

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        size = max(6, int(110 * sc))
        img = scaled(self.base, size)
        blit_glow(surf, (int(sx), int(sy)), size, tuple(c // 4 for c in self.color))
        surf.blit(img, img.get_rect(center=(int(sx), int(sy))))


class FloatText3D:
    """飄字（螢幕空間，但生成位置來自 3D 投影）。"""

    def __init__(self, screen_pos, text, color, font, life=50, rise=1.2):
        fg = font.render(text, True, color)
        self.image = pygame.Surface((fg.get_width() + 2, fg.get_height() + 2), pygame.SRCALPHA)
        self.image.blit(font.render(text, True, (10, 14, 30)), (2, 2))
        self.image.blit(fg, (0, 0))
        self.x, self.y = screen_pos
        self.life = life
        self.max_life = life
        self.rise = rise
        self.alive = True

    def update(self):
        self.y -= self.rise
        self.life -= 1
        if self.life <= 0:
            self.alive = False
        else:
            self.image.set_alpha(int(255 * min(1, self.life / (self.max_life * 0.5))))

    def draw(self, surf):
        surf.blit(self.image, self.image.get_rect(center=(int(self.x), int(self.y))))


# ---------------------------------------------------------------
# 主遊戲
# ---------------------------------------------------------------
# ---------------------------------------------------------------
# 最終魔王：MEGALON（依使用者「虛淵」設定圖建模的骨甲虛空巨獸，預先算圖的精靈）
# ---------------------------------------------------------------
# 精靈圖集 kuoyuan_sprites.png 的規格（由算圖程式輸出）
KAIJU_W, KAIJU_H = 440, 480
KAIJU_ANCHOR = ((220.0, 404.16), (220.0, 404.16))   # 地面接觸點在畫格中的位置（正面、側轉 16°）
KAIJU_PPU = 0.336                                     # 算圖時：每世界單位幾像素
KAIJU_CORE = (0.0, 655.0, 185.0)                      # 虛空之眼在模型中的位置（模型 +z = 朝向玩家）


def load_kaiju_frames():
    """把圖集切成 [階段][角度][姿勢] 的本體與自發光畫格；側轉角度再預先做好鏡像版。"""
    path = find_asset("megalon_sprites.png", "kuoyuan_sprites.png")      # 熔岩型（紅黑）優先
    if not path:
        print("  [MISS] kuoyuan_sprites.png -> 最終魔王改用母艦")
        return None
    try:
        atlas = pygame.image.load(path).convert_alpha()
    except pygame.error as e:
        print(f"  [FAIL] kuoyuan_sprites.png: {e}")
        return None
    W, H, cols, rows = KAIJU_W, KAIJU_H, 10, 4
    frames = {"base": {}, "glow": {}}
    for ph in (0, 1):
        for yi in (0, 1):
            r = ph * 2 + yi
            for c in range(cols):
                b = atlas.subsurface((c * W, r * H, W, H)).copy()
                g = atlas.subsurface((c * W, (rows + r) * H, W, H)).convert()
                frames["base"][(ph, yi, c, False)] = b
                frames["glow"][(ph, yi, c, False)] = g
                if yi == 1:
                    frames["base"][(ph, yi, c, True)] = pygame.transform.flip(b, True, False)
                    frames["glow"][(ph, yi, c, True)] = pygame.transform.flip(g, True, False)
    print(f"  [OK]   虛淵精靈 {os.path.basename(path)}（{len(frames['base'])} 格）")
    return frames


class KBeam:
    """
    熔界閃電光束（紅色）：眼睛先蓄光、拉出瞄準線，接著噴出一道會橫掃的閃電光束。
    立體感來自：
      - 七層圓柱漸層：由外而內 暗紅 -> 紅 -> 橘 -> 白熱核心
      - 外圍半透明光暈（畫在獨立的透明圖層上）
      - 繞著光束劈啪亂竄的 3D 閃電（含分岔），每 2 幀重新生成；每一段都參與深度排序
    """
    WARN, FIRE = 60, 120
    NSEG = 22
    LAYERS = ((1.00, (90, 6, 4)), (0.82, (160, 18, 8)), (0.65, (225, 45, 15)), (0.48, (255, 95, 30)),
              (0.32, (255, 160, 70)), (0.18, (255, 228, 175)), (0.08, (255, 255, 240)))

    def __init__(self, boss, ship, fast=False):
        self.boss = boss
        self.t = 0
        self.alive = True
        self.tx = ship.x + random.uniform(-60, 60)
        self.ty = ship.y
        self.sweep = random.choice((-1, 1)) * (520 if not fast else 640)
        self.radius = 58.0
        self.segs, self.proj, self.bolts = [], [], []
        self.z = boss.z

    def origin(self):
        return self.boss.core_world()

    def target(self):
        k = max(0.0, (self.t - self.WARN) / self.FIRE)
        return self.tx + self.sweep * (k - 0.5), self.ty

    def firing(self):
        return self.t >= self.WARN

    def envelope(self):
        if not self.firing():
            return 0.0
        a = min(1.0, (self.t - self.WARN) / 8.0)
        b = min(1.0, (self.WARN + self.FIRE - self.t) / 14.0)
        return max(0.0, min(a, b))

    def _axes(self):
        (ax, ay, az), (bx, by, bz) = self.segs[0], self.segs[-1]
        w = (bx - ax, by - ay, bz - az)
        n = math.sqrt(sum(c * c for c in w)) or 1.0
        w = tuple(c / n for c in w)
        u = (w[2], 0.0, -w[0])                              # 與光束垂直、水平方向
        nu = math.sqrt(u[0] ** 2 + u[2] ** 2) or 1.0
        u = (u[0] / nu, 0.0, u[2] / nu)
        v = (w[1] * u[2] - w[2] * u[1], w[2] * u[0] - w[0] * u[2], w[0] * u[1] - w[1] * u[0])
        return u, v

    def _make_bolts(self):
        """6 道閃電：沿著光束前進，繞軸的角度與半徑隨機抖動；部分帶分岔。"""
        u, v = self._axes()
        R = self.radius * max(0.3, self.envelope())
        bolts = []
        for _ in range(4):                                  # 4 道主閃電（6 道太耗效能，外觀差異不大）
            ang = random.uniform(0, math.tau)
            rr = R * random.uniform(1.0, 1.6)
            k0 = random.randint(0, 4)
            pts = []
            for k in range(k0, self.NSEG):
                ang += random.uniform(-0.65, 0.65)
                rr = max(R * 0.9, min(R * 2.4, rr + random.uniform(-0.35, 0.35) * R))
                cx, cy, cz = self.segs[k]
                ca, sa = math.cos(ang) * rr, math.sin(ang) * rr
                pts.append((k, (cx + u[0] * ca + v[0] * sa, cy + u[1] * ca + v[1] * sa, cz + u[2] * ca + v[2] * sa)))
            bolts.append(pts)
            if len(pts) > 6 and random.random() < 0.7:     # 分岔：往外岔出一小段
                i = random.randint(1, len(pts) - 4)
                k, (px, py, pz) = pts[i]
                ox, oy = random.uniform(-1, 1) * R * 1.4, random.uniform(-1, 1) * R * 1.4
                fork = [pts[i]]
                for j in range(1, 4):
                    kk = min(self.NSEG - 1, k + j)
                    cx, cy, cz = self.segs[kk]
                    fork.append((kk, (px + (cx - self.segs[k][0]) + ox * j / 3, py + (cy - self.segs[k][1]) + oy * j / 3,
                                      cz + (self.segs[kk][2] - self.segs[k][2]))))
                bolts.append(fork)
        self.bolts = bolts

    def update(self, game):
        self.t += 1
        if self.t >= self.WARN + self.FIRE or self.boss.dying:
            self.alive = False
            return
        ox, oy, oz = self.origin()
        tx, ty = self.target()
        tz = NEAR + 50
        n = self.NSEG
        self.segs = [(ox + (tx - ox) * i / (n - 1), oy + (ty - oy) * i / (n - 1), oz + (tz - oz) * i / (n - 1))
                     for i in range(n)]
        self.proj = [project(*sg) for sg in self.segs]
        self.z = oz
        if self.firing():
            if self.t % 2 == 0 or not self.bolts:
                self._make_bolts()
            env = self.envelope()
            s = game.ship
            ax, ay, az = self.segs[0]
            bx, by, bz = self.segs[-1]
            vx, vy, vz = bx - ax, by - ay, bz - az
            L2 = vx * vx + vy * vy + vz * vz
            u = max(0.0, min(1.0, ((s.x - ax) * vx + (s.y - ay) * vy + (s.z - az) * vz) / L2))
            dx, dy, dz = s.x - (ax + vx * u), s.y - (ay + vy * u), s.z - (az + vz * u)
            if dx * dx + dy * dy + dz * dz < (self.radius * env + s.radius) ** 2:
                if s.hit(20):
                    game.shake = max(game.shake, 10)
                    game.particles.burst((s.x, s.y, s.z), 10, (255, 120, 50), speed=12)
            game.shake = max(game.shake, 5)
            for _ in range(2):                              # 光束表面迸出紅色火星
                p = self.segs[random.randint(0, n - 1)]
                game.particles.emit(p[0] + random.uniform(-40, 40), p[1] + random.uniform(-40, 40), p[2],
                                    random.uniform(-9, 9), random.uniform(-9, 9), random.uniform(-6, 6),
                                    random.randint(10, 18), random.choice([(255, 90, 30), (255, 170, 80)]), 9.0)

    def items(self):
        out = []
        if not self.firing() or len(self.segs) < 2:
            return out
        n = len(self.segs) - 1
        for k0 in range(0, n, 3):
            k1 = min(n, k0 + 3)
            out.append(((self.segs[k0][2] + self.segs[k1][2]) * 0.5, (k0, k1)))
        return out

    def _strip(self, k0, k1, mul):
        R = self.radius * self.envelope() * mul
        left, right = [], []
        n = len(self.proj)
        for k in range(k0, k1 + 1):
            p = self.proj[k]
            if not p:
                return None
            q = self.proj[k + 1] if k + 1 < n and self.proj[k + 1] else self.proj[k - 1]
            if not q:
                return None
            dx, dy = (q[0] - p[0], q[1] - p[1]) if k + 1 < n else (p[0] - q[0], p[1] - q[1])
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L * R * p[2], dx / L * R * p[2]
            left.append((p[0] + nx, p[1] + ny))
            right.append((p[0] - nx, p[1] - ny))
        return left + right[::-1]

    def draw_glow(self, layer):
        """外圍半透明光暈：讓光束有體積感。"""
        if not self.firing() or len(self.segs) < 2:
            return
        n = len(self.segs) - 1
        box = None
        for mul, a in ((2.1, 34), (1.55, 62)):              # 收窄、調淡：是光暈，不是一片紅色板子
            poly = self._strip(0, n, mul)
            if poly:
                r = pygame.draw.polygon(layer, (255, 50, 15, a), poly)
                box = r if box is None else box.union(r)
        return box

    def draw_chunk(self, surf, chunk):
        k0, k1 = chunk
        flick = 1 + 0.08 * math.sin(self.t * 0.9)
        for mul, col in self.LAYERS:
            poly = self._strip(k0, k1, mul * (flick if mul < 0.5 else 1.0))
            if poly:
                pygame.draw.polygon(surf, col, poly)
        for bolt in self.bolts:                             # 閃電：只畫落在這個區塊的那幾段
            pts = [(k, project(*p3)) for k, p3 in bolt if k0 <= k <= k1 + 1]
            pts = [(k, q) for k, q in pts if q]
            for (ka, qa), (kb, qb) in zip(pts, pts[1:]):
                w = max(2, int(9 * qa[2]))
                pygame.draw.line(surf, (255, 60, 20), qa[:2], qb[:2], w + 2)
                pygame.draw.line(surf, (255, 240, 200), qa[:2], qb[:2], max(1, w // 3))

    def draw_warning(self, surf):
        """預警：眼睛到瞄準點之間一條閃爍的紅線，越接近發射越亮、越粗。"""
        if self.firing():
            return
        k = self.t / self.WARN
        a = project(*self.origin())
        tx, ty = self.target()
        b = project(tx, ty, game_ship_z())
        if a and b and (self.t // 4) % 2 == 0:
            pygame.draw.line(surf, (255, int(60 + 120 * k), 40), a[:2], b[:2], max(1, int(1 + 4 * k)))
            pygame.draw.circle(surf, (255, 90, 50), (int(b[0]), int(b[1])), int(18 + 20 * (1 - k)), 2)


_SHIP_Z = [PLAYER_Z]


def game_ship_z():
    return _SHIP_Z[0]


class KPillar:
    """隕石天降：地面出現預警圈並隨地面朝玩家逼近，隕石從高空墜落砸在圈內。"""
    WARN, FALL, BLAST = 54, 18, 26
    R = 100.0

    def __init__(self, x, z):
        self.x, self.z = x, z
        self.t = 0
        self.alive = True

    def pos(self):
        return (self.x, ground_at(self.x, self.z), self.z)

    def update(self, game):
        self.t += 1
        self.z -= game.world_speed                       # 跟著地面一起朝玩家流過來
        if self.t >= self.WARN + self.BLAST or self.z < NEAR + 20:
            self.alive = False
            return
        g = ground_at(self.x, self.z)
        if self.t == self.WARN:                          # 落地
            game.boom(self.pos(), big=True)
            for _ in range(14):
                game.particles.emit(self.x, g - 20, self.z, random.uniform(-14, 14), -random.uniform(8, 22),
                                    random.uniform(-8, 8), random.randint(18, 34), (255, 112, 85), 13.0)
        if self.WARN <= self.t < self.WARN + 10:         # 只有落地瞬間有傷害：公平、閃得掉
            s = game.ship
            if abs(s.z - self.z) < self.R + s.radius and abs(s.x - self.x) < self.R + s.radius and s.y > g - 560:
                if s.hit(22):
                    game.shake = max(game.shake, 12)

    def draw(self, surf, p):
        g = ground_at(self.x, self.z)
        if self.t < self.WARN:
            k = self.t / self.WARN
            if (self.t // max(2, int(8 - 6 * k))) % 2 == 0:      # 預警圈：越接近落地閃得越快
                pts = []
                for i in range(20):
                    a = i * math.tau / 20
                    q = project(self.x + math.cos(a) * self.R * 1.2, g - 4, self.z + math.sin(a) * self.R * 1.2)
                    if q:
                        pts.append(q[:2])
                if len(pts) > 2:
                    pygame.draw.polygon(surf, (int(150 + 90 * k), 70, 255), pts, max(2, int(4 * k + 2)))
            if self.t >= self.WARN - self.FALL:          # 隕石墜落中
                f = (self.t - (self.WARN - self.FALL)) / self.FALL
                h = g - 1500 * (1 - f)
                top = project(self.x + 160 * (1 - f), h - 320, self.z + 200 * (1 - f))
                rock = project(self.x, h, self.z)
                if rock:
                    if top:
                        pygame.draw.line(surf, (220, 78, 55), top[:2], rock[:2], max(2, int(40 * rock[2])))
                        pygame.draw.line(surf, (255, 177, 148), top[:2], rock[:2], max(1, int(12 * rock[2])))
                    r = max(3, int(self.R * 0.7 * rock[2]))
                    blit_glow(surf, (int(rock[0]), int(rock[1])), r * 3, (200, 68, 47))
                    pygame.draw.circle(surf, (60, 24, 17), (int(rock[0]), int(rock[1])), r)
                    pygame.draw.circle(surf, (255, 141, 113), (int(rock[0]), int(rock[1])), r, max(1, r // 4))
            return
        k = (self.t - self.WARN) / self.BLAST            # 落地後的紫色衝擊柱
        h = 700 * (1 - k)
        bot = project(self.x, g, self.z)
        top = project(self.x, g - h, self.z)
        if not bot or not top:
            return
        for mul, col in ((1.0, (140, 36, 22)), (0.72, (230, 80, 55)), (0.45, (255, 148, 120)), (0.2, (250, 240, 255))):
            wb = self.R * mul * (1.3 - 0.5 * k) * bot[2]
            wt = self.R * mul * 0.4 * top[2]
            pygame.draw.polygon(surf, col, ((bot[0] - wb, bot[1]), (bot[0] + wb, bot[1]),
                                            (top[0] + wt, top[1]), (top[0] - wt, top[1])))
        blit_glow(surf, (int(bot[0]), int(bot[1])), int(self.R * 2.4 * bot[2]), (220, 78, 55))


class KSlash:
    """前肢橫掃：一道橫貫全場的弧形斬擊朝玩家飛來。只有一個高度會被斬到，要上下閃。"""
    SPEED = 36.0
    HALF = 78.0

    def __init__(self, boss, band_y):
        self.x0 = boss.x
        self.z = boss.z - 300
        self.band = band_y
        self.alive = True
        self.hit_done = False

    def y_at(self, x):
        u = (x - self.x0) / 1100.0
        return self.band - 70 * (1 - u * u)

    def z_at(self, x):
        u = (x - self.x0) / 1100.0
        return self.z - 160 * (1 - u * u)          # 弧形：中央先到

    def pos(self):
        return (self.x0, self.band, self.z)

    def update(self, game):
        self.z -= self.SPEED
        if self.z < NEAR + 10:
            self.alive = False
            return
        s = game.ship
        if not self.hit_done and abs(s.z - self.z_at(s.x)) < 55 and abs(s.y - self.y_at(s.x)) < self.HALF:
            self.hit_done = True
            if s.hit(24):
                game.shake = max(game.shake, 14)
                game.particles.burst((s.x, s.y, s.z), 12, (255, 120, 92), speed=13)

    def _arc(self, dz, dy=0.0):
        pts = []
        for i in range(25):
            x = self.x0 - 1100 + 2200 * i / 24
            q = project(x, self.y_at(x) + dy, self.z_at(x) + dz)
            if q:
                pts.append(q)
        return pts

    def draw(self, surf, p):
        for dz, cols, wmul in ((180, ((90, 25, 15),), 0.5), (90, ((170, 52, 34),), 0.75),
                               (0, ((190, 51, 32), (255, 120, 92), (255, 206, 176)), 1.0)):
            pts = self._arc(dz)
            if len(pts) < 2:
                continue
            w = max(2, int(self.HALF * 0.9 * pts[len(pts) // 2][2] * wmul))
            for j, col in enumerate(cols):
                pygame.draw.lines(surf, col, False, [q[:2] for q in pts], max(1, w // (1 + j * 2)))


class KVortex:
    """異界扭曲：紫黑色重力漩渦，把戰機往中心拉。碰到中心會持續受傷。"""
    LIFE = 270

    def __init__(self, x, y, strong=False):
        self.x, self.y, self.z = x, y, 1150.0
        self.t = 0
        self.alive = True
        self.pull = 0.022 if strong else 0.015

    def pos(self):
        return (self.x, self.y, self.z)

    def scale(self):
        a = min(1.0, self.t / 30)
        b = min(1.0, (self.LIFE - self.t) / 30)
        return max(0.0, min(a, b))

    def update(self, game):
        self.t += 1
        if self.t >= self.LIFE:
            self.alive = False
            return
        k = self.scale()
        s = game.ship
        s.pos_pull = (self.x, self.y, self.pull * k)
        s.x += (self.x - s.x) * self.pull * k
        s.y += (self.y - s.y) * self.pull * k * 0.7
        if (s.x - self.x) ** 2 + (s.y - self.y) ** 2 < 95 ** 2 and self.t % 25 == 0:
            if s.hit(10):
                game.shake = max(game.shake, 8)
        if self.t % 2 == 0:                              # 被吸進去的碎屑
            a = random.uniform(0, math.tau)
            r = random.uniform(260, 420) * k
            px, py = self.x + math.cos(a) * r, self.y + math.sin(a) * r
            v = 10
            game.particles.emit(px, py, self.z, (self.x - px) / r * v - math.sin(a) * 6,
                                (self.y - py) / r * v + math.cos(a) * 6, game.world_speed * 0.35,
                                int(r / v), (255, 105, 78), 8.0)

    def draw(self, surf, p):
        k = self.scale()
        if k <= 0:
            return
        c = project(self.x, self.y, self.z)
        if not c:
            return
        for arm in range(4):                             # 四條旋臂
            pts = []
            for i in range(36):
                a = arm * math.pi / 2 + i * 0.22 + self.t * 0.11
                r = (20 + i * 10) * k
                q = project(self.x + math.cos(a) * r, self.y + math.sin(a) * r, self.z + i * 3)
                if q:
                    pts.append(q[:2])
            if len(pts) > 1:
                for w, col in ((max(2, int(14 * c[2])), (120, 33, 21)), (max(1, int(6 * c[2])), (255, 127, 99))):
                    pygame.draw.lines(surf, col, False, pts, w)
        rr = int(70 * k * c[2])
        pygame.draw.circle(surf, (70, 18, 11), (int(c[0]), int(c[1])), max(2, rr + 6))
        pygame.draw.circle(surf, (18, 2, 1), (int(c[0]), int(c[1])), max(1, rr))
        pygame.draw.circle(surf, (255, 148, 120), (int(c[0]), int(c[1])), int(380 * k * c[2]), 2)


GREEN_FRAMES = []             # Megalon 綠色衝擊波的彗頭動畫


def _rune_shapes(n=28, seed=4):
    """發光符文：每個符文是 2~3 條短線段（在 -1~1 的方格內），用來畫黑洞吸積盤上旋轉的符文圈。"""
    rr = random.Random(seed)
    shapes = []
    for _ in range(n):
        segs = []
        for _ in range(rr.randint(2, 3)):
            segs.append(((rr.uniform(-1, 1), rr.uniform(-1, 1)), (rr.uniform(-1, 1), rr.uniform(-1, 1))))
        shapes.append(segs)
    return shapes


RUNES = _rune_shapes()


class KScytheSlash:
    """
    鐮刀揮砍：紅色新月形能量刃沿著一道弧線劃過畫面（在戰機所在的深度）。
    先有一道閃爍的紅色預警弧線（剛好通過戰機目前的位置），往上或往下移動就能躲開。
    """
    WARN, SWING, LINGER = 32, 18, 14
    HALF = 62                                                      # 刀刃的厚度（半寬）

    def __init__(self, boss, ship, flip=False, delay=0):
        self.t = -delay
        self.alive = True
        self.done_hit = False
        self.z = ship.z + 70
        self.cx = boss.x * 0.3 + ship.x * 0.7
        self.cy = ship.y - 560                                     # 圓心在戰機上方：刀刃從上方弧形劃過
        dx, dy = ship.x - self.cx, ship.y - self.cy
        self.R = max(220.0, math.hypot(dx, dy))
        aim = math.atan2(dy, dx)
        self.dir = -1 if flip else 1
        self.a0 = aim - self.dir * 1.25
        self.a1 = aim + self.dir * 1.25
        self.blade = 0.85
        self.prev = self.a0

    def angle(self):
        k = max(0.0, min(1.0, (self.t - self.WARN) / self.SWING))
        k = 1 - (1 - k) ** 2                                       # 先快後慢：揮砍的力道感
        return self.a0 + (self.a1 - self.a0) * k

    def pos(self):
        a = self.angle()
        return (self.cx + math.cos(a) * self.R, self.cy + math.sin(a) * self.R, self.z)

    def update(self, game):
        self.t += 1
        if self.t >= self.WARN + self.SWING + self.LINGER:
            self.alive = False
            return
        a = self.angle()
        if self.WARN <= self.t < self.WARN + self.SWING:
            s = game.ship
            d = math.hypot(s.x - self.cx, s.y - self.cy)
            sa = math.atan2(s.y - self.cy, s.x - self.cx)
            lo, hi = sorted((self.prev - self.dir * 0.15, a))
            if not self.done_hit and abs(d - self.R) < self.HALF + s.radius and lo <= sa <= hi:
                self.done_hit = True
                if s.hit(26):
                    game.shake = max(game.shake, 14)
                    game.particles.burst((s.x, s.y, s.z), 14, (255, 90, 50), speed=14)
            for _ in range(3):                                     # 刀刃劃過迸出的火星
                rr = self.R + random.uniform(-self.HALF, self.HALF)
                game.particles.emit(self.cx + math.cos(a) * rr, self.cy + math.sin(a) * rr, self.z,
                                    random.uniform(-6, 6), random.uniform(-6, 6), random.uniform(-3, 3),
                                    random.randint(10, 18), random.choice([(255, 120, 50), (255, 220, 160)]), 9.0)
            game.shake = max(game.shake, 6)
        self.prev = a

    def _arc(self, a_from, a_to, radius, n=24):
        pts = []
        for i in range(n + 1):
            a = a_from + (a_to - a_from) * i / n
            q = project(self.cx + math.cos(a) * radius, self.cy + math.sin(a) * radius, self.z)
            if q:
                pts.append((q[0], q[1]))
        return pts

    def draw(self, surf, p):
        if self.t < 0:
            return
        if self.t < self.WARN:                                     # 預警：閃爍的紅色弧線
            if (self.t // 4) % 2 == 0:
                pts = self._arc(self.a0, self.a1, self.R, 30)
                if len(pts) > 1:
                    pygame.draw.lines(surf, (255, 60, 40), False, pts, 3)
                    for off in (-self.HALF, self.HALF):
                        q = self._arc(self.a0, self.a1, self.R + off, 30)
                        if len(q) > 1:
                            pygame.draw.lines(surf, (255, 140, 100), False, q, 1)
            return
        a = self.angle()
        fade = 1.0 if self.t < self.WARN + self.SWING else max(0.0, 1 - (self.t - self.WARN - self.SWING) / self.LINGER)
        for ghost in (3, 2, 1, 0):                                 # 殘影 + 刀刃本體
            ag = a - self.dir * ghost * 0.22
            k_g = (1 - ghost * 0.24) * fade
            if k_g <= 0.05:
                continue
            tail = ag - self.dir * self.blade
            for wmul, col in ((1.0, (150, 20, 20)), (0.68, (240, 70, 30)), (0.36, (255, 190, 120)), (0.14, (255, 250, 230))):
                outer, inner = [], []
                for i in range(19):
                    u = i / 18
                    aa = tail + (ag - tail) * u
                    w = self.HALF * wmul * math.sin(math.pi * min(1.0, u * 1.15)) ** 0.7 * k_g
                    qo = project(self.cx + math.cos(aa) * (self.R + w), self.cy + math.sin(aa) * (self.R + w), self.z)
                    qi = project(self.cx + math.cos(aa) * (self.R - w), self.cy + math.sin(aa) * (self.R - w), self.z)
                    if qo and qi:
                        outer.append(qo[:2]); inner.append(qi[:2])
                if len(outer) > 2:
                    pygame.draw.polygon(surf, col, outer + inner[::-1])
                if ghost:
                    break                                          # 殘影只畫最外層


class KGreenComet:
    """綠色衝擊波：從胸口射出 2~3 枚巨大綠色彗星，交纏螺旋衝向戰機，拖著長長的綠黃光帶。"""
    SPEED = 26.0

    def __init__(self, boss, ship, k, n):
        self.ox, self.oy, self.oz = boss.core_world()
        tx, ty, tz = ship.x, ship.y, ship.z
        ax, ay, az = tx - self.ox, ty - self.oy, tz - self.oz
        L = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
        self.ax, self.ay, self.az = ax / L, ay / L, az / L
        ux, uz = self.az, -self.ax                                  # 與飛行方向垂直的兩個軸
        nu = math.hypot(ux, uz) or 1.0
        self.u = (ux / nu, 0.0, uz / nu)
        self.v = (self.ay * self.u[2] - self.az * self.u[1], self.az * self.u[0] - self.ax * self.u[2],
                  self.ax * self.u[1] - self.ay * self.u[0])
        self.phase = k * math.tau / n
        self.s = 0.0
        self.r = 10.0
        self.t = 0
        self.alive = True
        self.done_hit = False
        self.hist = []
        self.x, self.y, self.z = self.ox, self.oy, self.oz

    def pos(self):
        return (self.x, self.y, self.z)

    def update(self, game):
        self.t += 1
        self.hist.append((self.x, self.y, self.z))
        if len(self.hist) > 16:
            self.hist.pop(0)
        self.s += self.SPEED
        self.phase += 0.2
        self.r = min(120.0, self.r + 5.0)
        c, sn = math.cos(self.phase) * self.r, math.sin(self.phase) * self.r
        self.x = self.ox + self.ax * self.s + self.u[0] * c + self.v[0] * sn
        self.y = self.oy + self.ay * self.s + self.u[1] * c + self.v[1] * sn
        self.z = self.oz + self.az * self.s + self.u[2] * c + self.v[2] * sn
        if self.z < NEAR + 20:
            self.alive = False
            return
        s = game.ship
        if not self.done_hit and (s.x - self.x) ** 2 + (s.y - self.y) ** 2 + (s.z - self.z) ** 2 < (78 + s.radius) ** 2:
            self.done_hit = True
            if s.hit(20):
                game.shake = max(game.shake, 12)
                game.particles.burst((s.x, s.y, s.z), 14, (150, 255, 90), speed=13)
        if self.t % 2 == 0:
            game.particles.emit(self.x, self.y, self.z, random.uniform(-3, 3), random.uniform(-3, 3), 4.0,
                                random.randint(10, 18), random.choice([(150, 255, 80), (230, 255, 170)]), 10.0)

    def draw(self, surf, p):
        sx, sy, sc = p
        size = max(8, int(150 * sc) // 4 * 4)
        pts = [q for q in (project(*h) for h in self.hist) if q] + [p]
        if len(pts) >= 3:                                          # 長長的綠黃光帶（三層）
            for wmul, col in ((0.5, (40, 160, 30)), (0.32, (150, 255, 60)), (0.15, (240, 255, 190))):
                _ribbon(surf, [(q[0], q[1]) for q in pts],
                        [size * wmul * ((i + 1) / len(pts)) ** 0.8 * (1 + 0.3 * math.sin(self.t * 0.5 + i))
                         for i in range(len(pts))], col)
        blit_glow(surf, (int(sx), int(sy)), max(6, int(size * 0.95) // 4 * 4), (70, 200, 40))
        if GREEN_FRAMES:
            img = scaled(GREEN_FRAMES[(self.t // 2) % len(GREEN_FRAMES)], size)
            surf.blit(img, img.get_rect(center=(int(sx), int(sy))))


class KPurpleOrb:
    """紫色擊波：白熾核心 + 紫色光暈與十字光芒，拖著紫色能量絲線與閃爍光點；速度慢但會追蹤戰機。"""
    SPEED = 19.0

    def __init__(self, boss, ship):
        self.x, self.y, self.z = boss.core_world()
        dx, dy, dz = ship.x - self.x, ship.y - self.y, ship.z - self.z
        d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        self.vx, self.vy, self.vz = dx / d * self.SPEED, dy / d * self.SPEED, dz / d * self.SPEED
        self.t = 0
        self.alive = True
        self.hist = []
        self.seed = random.randint(0, 9999)

    def pos(self):
        return (self.x, self.y, self.z)

    def update(self, game):
        self.t += 1
        self.hist.append((self.x, self.y, self.z))
        if len(self.hist) > 18:
            self.hist.pop(0)
        s = game.ship
        if self.t < 80:                                            # 前段會追蹤
            dx, dy, dz = s.x - self.x, s.y - self.y, s.z - self.z
            d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
            self.vx += (dx / d * self.SPEED - self.vx) * 0.04
            self.vy += (dy / d * self.SPEED - self.vy) * 0.04
            self.vz += (dz / d * self.SPEED - self.vz) * 0.04
        self.x += self.vx; self.y += self.vy; self.z += self.vz
        if self.z < NEAR + 20:
            self.alive = False
            return
        if (s.x - self.x) ** 2 + (s.y - self.y) ** 2 + (s.z - self.z) ** 2 < (88 + s.radius) ** 2:
            self.alive = False
            if s.hit(24):
                game.shake = max(game.shake, 14)
            game.particles.burst((self.x, self.y, self.z), 24, (210, 130, 255), speed=15)

    def draw(self, surf, p):
        sx, sy, sc = p
        size = max(8, int(230 * sc) // 4 * 4)                     # 加大：從遠處射出時才不會太小
        pts = [q for q in (project(*h) for h in self.hist) if q] + [p]
        n = len(pts)
        if n >= 3:                                                 # 三條紫色能量絲線：往後收束
            for j in (-1, 0, 1):
                line = []
                for i, q in enumerate(pts):
                    a = pts[min(i + 1, n - 1)]; b = pts[max(i - 1, 0)]
                    dx, dy = a[0] - b[0], a[1] - b[1]; L = math.hypot(dx, dy) or 1.0
                    o = j * size * 0.22 * ((i + 1) / n) * (1 + 0.25 * math.sin(self.t * 0.4 + i * 0.8 + j))
                    line.append((q[0] - dy / L * o, q[1] + dx / L * o))
                pygame.draw.lines(surf, (120, 60, 255), False, line, max(2, int(size * 0.06)))
                pygame.draw.lines(surf, (215, 180, 255), False, line, 1)
        rr = random.Random(self.seed + self.t // 3)                # 閃爍光點
        for _ in range(10):
            if not self.hist:
                break
            hx, hy, hz = self.hist[rr.randrange(len(self.hist))]
            q = project(hx + rr.uniform(-60, 60), hy + rr.uniform(-60, 60), hz)
            if q:
                pygame.draw.circle(surf, (240, 220, 255), (int(q[0]), int(q[1])), max(1, int(rr.uniform(2, 5) * q[2])))
        blit_glow(surf, (int(sx), int(sy)), max(8, int(size * 1.5) // 4 * 4), (150, 40, 220))
        rot = self.t * 0.05                                        # 十字光芒
        for k in (0, 1):
            a = rot + k * math.pi / 2
            L = size * 0.95
            pygame.draw.line(surf, (230, 170, 255), (sx - math.cos(a) * L, sy - math.sin(a) * L),
                             (sx + math.cos(a) * L, sy + math.sin(a) * L), max(1, int(size * 0.03)))
        if NOVA_FRAMES:
            img = scaled(NOVA_FRAMES[(self.t // 2) % len(NOVA_FRAMES)], max(8, int(size * 0.9) // 4 * 4))
            surf.blit(img, img.get_rect(center=(int(sx), int(sy))))
        pygame.draw.circle(surf, (255, 250, 255), (int(sx), int(sy)), max(2, int(size * 0.2)))


class KBlackHole:
    """
    黑洞：漆黑核心 + 亮白光環，外面是傾斜的吸積盤，兩圈發光符文瘋狂旋轉，光點螺旋被吸入。
    超強重力把戰機往中心拖；被吸進核心會持續受傷。
    """
    def __init__(self, x, y, z, strong=False):
        self.x, self.y, self.z = x, y, z
        self.t = 0
        self.life = 360 if strong else 300
        self.alive = True
        self.pull = 0.045 if strong else 0.032
        self.spin = 0.0
        self.parts = [[random.uniform(0, math.tau), random.uniform(1.2, 3.3)] for _ in range(46)]

    def scale(self):
        return max(0.0, min(1.0, self.t / 40, (self.life - self.t) / 30))

    def pos(self):
        return (self.x, self.y, self.z)

    def update(self, game):
        self.t += 1
        if self.t >= self.life:
            self.alive = False
            return
        k = self.scale()
        self.spin += 0.16 + 0.1 * k                                 # 瘋狂旋轉
        for pt in self.parts:                                      # 光點螺旋被吸入
            pt[0] += 0.5 / (pt[1] + 0.3)
            pt[1] -= 0.035
            if pt[1] < 0.9:
                pt[0], pt[1] = random.uniform(0, math.tau), random.uniform(2.8, 3.4)
        s = game.ship
        s.pos_pull = (self.x, self.y, self.pull * k)
        s.x += (self.x - s.x) * self.pull * k                     # 超強重力
        s.y += (self.y - s.y) * self.pull * k * 0.8
        if k > 0.5 and self.t % 20 == 0 and math.hypot(s.x - self.x, s.y - self.y) < 105 * k + s.radius * 0.5:
            if s.hit(6):
                game.shake = max(game.shake, 10)
                game.particles.burst((s.x, s.y, s.z), 10, (150, 180, 255), speed=10)
        game.shake = max(game.shake, int(3 * k))

    def draw(self, surf, p):
        sx, sy, sc = p
        k = self.scale()
        if k <= 0.02:
            return
        Rs = max(4, int(105 * sc * k))
        cx, cy = int(sx), int(sy)
        blit_glow(surf, (cx, cy), max(8, Rs * 4 // 4 * 4), (50, 70, 200))
        ell = 0.42                                                 # 吸積盤的傾斜（橢圓扁度）

        def ring(mul, col, w):
            rect = pygame.Rect(0, 0, int(Rs * mul * 2), int(Rs * mul * 2 * ell))
            rect.center = (cx, cy)
            pygame.draw.ellipse(surf, col, rect, w)

        def runes(mul, sp, col, front):
            n = 14
            for i in range(n):
                a = sp + i * math.tau / n
                if (math.sin(a) > 0) != front:
                    continue
                px, py = cx + math.cos(a) * Rs * mul, cy + math.sin(a) * Rs * mul * ell
                g = Rs * 0.11
                for (x0, y0), (x1, y1) in RUNES[i % len(RUNES)]:
                    pygame.draw.line(surf, col, (px + x0 * g, py + y0 * g), (px + x1 * g, py + y1 * g), 2)

        def swirl(front):
            for a, r in self.parts:
                aa = a + self.spin
                if (math.sin(aa) > 0) != front:
                    continue
                px, py = cx + math.cos(aa) * Rs * r, cy + math.sin(aa) * Rs * r * ell
                pygame.draw.circle(surf, (210, 230, 255) if r < 2 else (120, 160, 255), (int(px), int(py)),
                                   max(1, int(Rs * 0.05)))

        for mul, col, w in ((3.2, (60, 90, 230), 2), (2.6, (120, 160, 255), 2), (2.0, (200, 220, 255), 3)):
            ring(mul, col, w)
        runes(2.85, self.spin, (190, 215, 255), False)             # 後半圈（被核心擋住的那一側先畫）
        runes(2.25, -self.spin * 1.6, (230, 240, 255), False)
        swirl(False)
        pygame.draw.circle(surf, (4, 4, 10), (cx, cy), Rs)         # 漆黑核心
        for i in range(4):                                         # 亮白光環（光子環）
            pygame.gfxdraw.aacircle(surf, cx, cy, Rs + i, (230, 240, 255, 220 - i * 50))
        runes(2.85, self.spin, (190, 215, 255), True)              # 前半圈蓋在核心前面
        runes(2.25, -self.spin * 1.6, (230, 240, 255), True)
        swirl(True)


class KaijuBoss:
    """
    熔界獸：踏著冰原走來的六足巨獸。介面與母艦相同（位置、半徑、受傷、死亡），
    所以玩家的每一種武器都能直接對牠造成傷害。
    五招：熔界光束、地殼崩裂、前肢橫掃、異界扭曲；血量剩一半進入終焉形態（第二階段）。
    """
    name = "MEGALON"

    def __init__(self, frames, wave):
        self.frames = frames
        self.max_hp = 900                     # 固定血量，不隨關卡編號變動
        self.hp = self.max_hp
        self.score = 8000
        self.damage = 30
        self.radius = 330.0
        self.x, self.z = 0.0, 3800.0
        self.y = 0.0
        self.t = 0
        self.walk = 0.0
        self.entering = True
        self.dying = False
        self.death_timer = 0
        self.phase2 = False
        self.roar = 0
        self.flash = 0
        self.sink = 0.0
        self.effects = []
        self.beams = []
        self.state = "idle"
        self.state_t = 0
        self.cooldown = 150
        self.shard_t = 0
        self.raise_arms = 0
        self.glow_k = 1.0
        self.cache = {}
        self.last = None
        self.crit = 0
        self.next_roar = 50                   # 登場約 1 秒後第一聲吼叫

    # ---- 位置 ----
    def ground(self):
        return ground_at(self.x, self.z)

    def pos(self):
        return (self.x, self.ground() - 560 + self.sink, self.z)

    def core_world(self):
        g = self.ground() + self.sink
        return (self.x + KAIJU_CORE[0], g - KAIJU_CORE[1], self.z - KAIJU_CORE[2])

    @property
    def stage(self):
        return 2 if self.phase2 else 1

    def take_damage(self, dmg=1, at=None):
        if self.entering or self.dying:
            return False
        if at is not None:                                   # 弱點：胸口熔核雙倍傷害
            cx, cy, cz = self.core_world()
            if (at[0] - cx) ** 2 + (at[1] - cy) ** 2 + (at[2] - cz) ** 2 < 115 ** 2:
                dmg *= 2
                self.crit = 6
        self.hp -= dmg
        self.flash = 3
        return self.hp <= 0

    # ---- 行為 ----
    def update(self, ship, enemy_bullets, game):
        self.t += 1
        _SHIP_Z[0] = ship.z
        if self.flash > 0:
            self.flash -= 1
        for fx in self.effects:
            fx.update(game)
        self.effects = [f for f in self.effects if f.alive]
        for bm in self.beams:
            bm.update(game)
        self.beams = [b for b in self.beams if b.alive]
        if self.dying:
            self.sink += 2.2
            self.glow_k = max(0.0, self.glow_k - 0.008)
            return
        spd = 1.5 if self.phase2 else 1.0
        # 叫聲：叫聲 1、2 輪流，上一聲結束後隔 1~3 秒（隨機）再吼下一聲
        if self.t >= self.next_roar:
            length = game.kaiju_roar(self)
            self.next_roar = self.t + int(length * 60) + random.randint(60, 180)
        if self.entering:
            self.z -= 9.0
            self.walk += 0.05
            if int(self.walk / math.pi) != int((self.walk - 0.05) / math.pi):
                game.kaiju_step(self, shake=9)                 # 腳落地：腳步聲 + 畫面震動
            if self.z <= 1750:
                self.entering = False
            return
        if self.roar > 0:                                      # 終焉形態變身中
            self.roar -= 1
            self.raise_arms = 2
            game.shake = max(game.shake, 14 if self.roar > 20 else 6)
            return
        zt = 1450.0 if self.phase2 else 1750.0
        nx = (380 if self.phase2 else 320) * math.sin(self.t * 0.006 * spd)
        nz = zt + 120 * math.sin(self.t * 0.004 * spd)
        moved = abs(nx - self.x) + abs(nz - self.z)
        self.x, self.z = nx, nz
        inc = 0.022 + moved * 0.004                            # 巨獸步伐沉重：約 2 秒一步，與腳步聲的步距一致
        if int(self.walk / math.pi) != int((self.walk + inc) / math.pi):
            game.kaiju_step(self)
        self.walk += inc
        # 結晶碎片：從背部射出的散彈，維持壓力
        self.shard_t += 1
        if self.shard_t >= (45 if self.phase2 else 75):
            self.shard_t = 0
            ox, oy, oz = self.x, self.ground() - 900, self.z + 100
            for sp in ((-0.12, 0.0, 0.12) if self.phase2 else (-0.08, 0.08)):
                dx, dy, dz = ship.x - ox, ship.y - oy, ship.z - oz
                d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1
                v = 17.0
                enemy_bullets.append(EnemyBullet3D(ox, oy, oz, dx / d * v + sp * v, dy / d * v, dz / d * v,
                                                   (255, 127, 99)))
        # 招式排程
        if self.state == "idle":
            self.raise_arms = max(0, self.raise_arms - 1)
            self.cooldown -= 1
            if self.cooldown <= 0:
                self.start_attack(game)
        else:
            self.state_t += 1
            st = self.state_t
            if self.state == "scythe":                           # 鐮刀揮砍：舉臂（同時出現預警弧線）-> 揮下
                self.raise_arms = 1 if st < 14 else (2 if st < 44 else 0)
                if st == 12:
                    self.effects.append(KScytheSlash(self, ship, flip=random.random() < 0.5))
                    if self.phase2:                                # 第二階段：連砍兩刀，交叉成 X
                        self.effects.append(KScytheSlash(self, ship, flip=random.random() < 0.5, delay=18))
                if st == 44:
                    game.shake = max(game.shake, 10)
                    self._sfx(game, "w_FIRE")
                if st > 100:
                    self.end_attack()
            elif self.state == "comet":                          # 綠色衝擊波：胸口蓄光 -> 2~3 枚螺旋彗星
                if st == 30:
                    n = 3 if self.phase2 else 2
                    for k in range(n):
                        self.effects.append(KGreenComet(self, ship, k, n))
                    self._sfx(game, "w_COMET")
                if st > 70:
                    self.end_attack()
            elif self.state == "orb":                            # 紫色擊波：蓄光 -> 追蹤能量彈（第二階段連發兩顆）
                if st == 34 or (self.phase2 and st == 66):
                    self.effects.append(KPurpleOrb(self, ship))
                    self._sfx(game, "w_PLASMA")
                if st > 96:
                    self.end_attack()
            elif self.state == "blackhole":
                if st > 40:
                    self.end_attack()
        # 熔核亮度：蓄力光束時變亮
        target = 1.0 + 0.15 * math.sin(self.t * 0.07)
        if (self.state == "comet" and self.state_t < 30) or (self.state == "orb" and self.state_t < 34):
            target = 1.9                                           # 發射前：胸口的虛空之眼蓄光變亮
        self.glow_k += (target - self.glow_k) * 0.12
        if not self.phase2 and self.hp <= self.max_hp * 0.5:     # 進入終焉形態
            self.phase2 = True
            self.roar = 70
            length = game.kaiju_roar(self)                     # 變身時立刻吼叫
            self.next_roar = self.t + int(length * 60) + random.randint(60, 180)
            self.effects.clear()
            self.beams.clear()
            self.state = "idle"
            self.cooldown = 80
            game.flash = 150
            game.freeze = 6
            for _ in range(60):
                game.particles.emit(self.x + random.uniform(-300, 300), self.ground() - random.uniform(400, 800),
                                    self.z, random.uniform(-14, 14), random.uniform(-16, 4), random.uniform(-10, 10),
                                    random.randint(24, 44), (255, 155, 127), 12.0)
            game.texts.append(FloatText3D((CX, CY - 40), "VOID AWAKENING", (255, 170, 141), game.font_l,
                                          life=110, rise=0.2))

    def _sfx(self, game, name):
        snd = game.sfx.get(name) if getattr(game, "audio", False) else None
        if snd:
            snd.play()

    def _spawn_blackhole(self, game):
        s = game.ship
        side = random.choice((-1, 1))                               # 生成在戰機旁邊一段距離：先被拖過去，有機會逃脫
        self.effects.append(KBlackHole(s.x + side * random.uniform(260, 380), s.y + random.uniform(-80, 80), s.z + 520,
                                       strong=self.phase2))
        self._sfx(game, "nova_boom")

    def start_attack(self, game):
        """四招：鐮刀揮砍、綠色衝擊波、紫色擊波、黑洞。"""
        choices = ["scythe", "comet", "orb", "blackhole"]
        weights = [3, 3, 3, 2]
        if any(isinstance(fx, KBlackHole) for fx in self.effects):
            weights[3] = 0                                        # 場上同時只會有一個黑洞
        if self.last in choices:                                  # 避免同一招連續出現
            weights[choices.index(self.last)] *= 0.2
        kind = random.choices(choices, weights)[0]
        self.last = kind
        self.state, self.state_t = kind, 0
        if kind == "blackhole":
            self._spawn_blackhole(game)
        elif self.phase2 and kind in ("scythe", "comet") and random.random() < 0.35 and \
                not any(isinstance(fx, KBlackHole) for fx in self.effects):
            self._spawn_blackhole(game)                           # 第二階段：黑洞 + 另一招的組合技

    def end_attack(self):
        self.state = "idle"
        self.cooldown = random.randint(60, 90) if self.phase2 else random.randint(110, 160)

    # ---- 繪製 ----
    def frame_key(self):
        ph = 1 if self.phase2 else 0
        ang = math.degrees(math.atan2(abs(self.x), max(1.0, self.z)))
        yi, mirror = (0, False) if ang < 7 else (1, self.x > 0)
        if self.raise_arms:
            pose = 8 if self.raise_arms == 1 else 9
        else:
            pose = int((self.walk % math.tau) / math.tau * 8) % 8
        return ph, yi, pose, mirror

    def _scaled(self, kind, key, w, h):
        ck = (kind, key, w)
        s = self.cache.get(ck)
        if s is None:
            if len(self.cache) > 40:
                self.cache.clear()
            s = pygame.transform.smoothscale(self.frames[kind][key], (w, h))
            self.cache[ck] = s
        return s

    def draw(self, surf, p):
        g = self.ground() + self.sink
        q = project(self.x, g, self.z)
        if not q:
            return
        key = self.frame_key()
        k = q[2] / KAIJU_PPU
        w = max(8, int(KAIJU_W * k / 6) * 6)
        h = int(w * KAIJU_H / KAIJU_W)
        kk = w / KAIJU_W
        ax, ay = KAIJU_ANCHOR[key[1]]
        if key[3]:
            ax = KAIJU_W - ax
        x0, y0 = q[0] - ax * kk, q[1] - ay * kk
        # 地面陰影：橢圓形暗影，讓巨獸「站」在冰原上
        sw, sh = int(1250 * q[2]), int(260 * q[2])
        if sw > 4:
            shd = pygame.Surface((sw, max(2, sh)), pygame.SRCALPHA)
            pygame.draw.ellipse(shd, (20, 30, 50, 90), shd.get_rect())
            surf.blit(shd, (q[0] - sw // 2, q[1] - sh // 2))
        base = self._scaled("base", key, w, h)
        surf.blit(base, (x0, y0))
        if self.flash > 0:
            surf.blit(base, (x0, y0), special_flags=pygame.BLEND_RGB_ADD)
        glow = self._scaled("glow", key, w, h)
        gk = max(0.0, self.glow_k)
        if gk > 0.02:
            gl = glow.copy()
            m = int(255 * min(1.0, gk))
            if m < 255:
                gl.fill((m, m, m), special_flags=pygame.BLEND_RGB_MULT)
            surf.blit(gl, (x0, y0), special_flags=pygame.BLEND_RGB_ADD)
            if gk > 1.05:                                       # 超過 1 的亮度：再疊一層
                gl2 = glow.copy()
                m2 = int(255 * min(1.0, gk - 1.0))
                gl2.fill((m2, m2, m2), special_flags=pygame.BLEND_RGB_MULT)
                surf.blit(gl2, (x0, y0), special_flags=pygame.BLEND_RGB_ADD)
        c = project(*self.core_world())
        if c and gk > 0.05:
            blit_glow(surf, (int(c[0]), int(c[1])), int(150 * c[2] * gk), (230, 72, 48))
        for bm in self.beams:
            bm.draw_warning(surf)



class Game:
    STATE_TITLE = "title"
    STATE_PLAY = "play"
    STATE_PAUSE = "pause"
    STATE_OVER = "over"
    STATE_WIN = "win"

    def __init__(self):
        pygame.init()
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(24)
            pygame.mixer.set_reserved(4)           # 0 號魔王叫聲、1、2 號腳步聲、3 號破關音樂：不會被爆炸音效擠掉
            self.ch_roar = pygame.mixer.Channel(0)
            self.ch_step = [pygame.mixer.Channel(1), pygame.mixer.Channel(2)]
            self.ch_victory = pygame.mixer.Channel(3)
            self.audio = True
        except pygame.error as e:
            print(f"[WARN] 音效無法啟動：{e}")
            self.audio = False

        self.screen = self.open_window(FULLSCREEN)
        self.disable_ime()
        self.ime_warn_t = -9999
        pygame.display.set_caption("Alien Adventure 3D")
        self.clock = pygame.time.Clock()
        self.canvas = pygame.Surface((SCREEN_W, SCREEN_H))

        self.font_s = pygame.font.Font(None, 24)
        self.font_m = pygame.font.Font(None, 34)
        self.font_l = pygame.font.Font(None, 54)
        self.font_xl = pygame.font.Font(None, 84)
        # 勝利畫面字型：Audiowide（Google Fonts，SIL 開放字型授權，可隨遊戲散布）
        fpath = find_asset("Audiowide-Regular.ttf")
        if fpath:
            self.font_win = pygame.font.Font(fpath, 128)
            self.font_win_m = pygame.font.Font(fpath, 40)
            self.font_win_s = pygame.font.Font(fpath, 22)
        else:
            self.font_win = pygame.font.Font(None, 160)
            self.font_win_m = pygame.font.Font(None, 52)
            self.font_win_s = pygame.font.Font(None, 30)
        self._win_cache = None
        # 標題（Dela Gothic One：極粗、支援片假名）與計分板（Bebas Neue：窄長大寫）
        dpath = find_asset("DelaGothicOne-Regular.ttf")
        bpath = find_asset("BebasNeue-Regular.ttf")
        self.font_title = pygame.font.Font(dpath, 88) if dpath else pygame.font.Font(None, 120)
        self.font_badge = pygame.font.Font(dpath, 96) if dpath else pygame.font.Font(None, 130)
        self.font_go = pygame.font.Font(dpath, 100) if dpath else None      # 「ゴ」需要日文字形
        self.font_hud = pygame.font.Font(bpath, 30) if bpath else pygame.font.Font(None, 34)
        self.font_hud_s = pygame.font.Font(bpath, 19) if bpath else pygame.font.Font(None, 22)
        self.font_press = pygame.font.Font(bpath, 46) if bpath else pygame.font.Font(None, 52)
        self._title_cache = None

        self.load_assets()
        PowerUp3D.build_images(self.font_m)
        self.sfx = synth_sounds()                      # 蓄力、光束、震波、切換的合成音效
        self.font_xs = pygame.font.Font(None, 20)
        self.fx_layer = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.tint = pygame.Surface((SCREEN_W, SCREEN_H))
        self.tint.fill((30, 80, 200))
        WeaponPack3D.build_images(self.font_m)
        self.stars = StarField3D()
        if ICE:
            global ACTIVE_TERRAIN
            print("生成南極冰原地形 ...")
            self.terrain = IceTerrain()
            ACTIVE_TERRAIN = self.terrain
        else:
            self.terrain = Terrain()
        self.sky = self._make_ice_sky() if ICE else self._make_sky()
        if ICE:
            self.terrain.set_sky(self.sky)
        self.vignette = self._make_vignette()
        self.white = pygame.Surface((SCREEN_W, SCREEN_H))
        self.white.fill((255, 245, 230))

        self.high_score = self.load_high_score()
        self.show_fps = False
        self.state = self.STATE_TITLE
        self.reset()

    # ---------- 素材 ----------
    def load_assets(self):
        print(f"\n素材資料夾：{ASSET_DIR}")
        print("載入中 ...")
        self.img_enemies = {}
        for i in (1, 2, 3, 4):
            self.img_enemies[i] = load_image([f"E{i}.png", f"E{i}.jpg"], size=(256, 256),
                                             fallback_color=ENEMY_TYPES[i]["color"])
        self.img_boss = load_image(["E3.png", "E3.jpg"], size=(512, 512),
                                   fallback_color=ENEMY_TYPES[3]["color"])
        self.img_boss = gradient_map(self.img_boss, METAL_PURPLE)          # 中魔王母艦：金屬紫
        base = self.img_enemies[3]
        self.img_saucers = [base, gradient_map(base, SAUCER_BLUE), gradient_map(base, SAUCER_BLACK)]

        self.frames_small = self.frames_big = None
        self.load_explosions()
        if self.frames_small is None:
            self.frames_small = self._fallback_frames(256)
            self.frames_big = self._fallback_frames(384)
            self.asset_warning = ("Explosion art not found - put explosion_frames.png or explosion_graph.jpg in:",
                                  ASSET_DIR)
            print(f"  [MISS] 爆炸圖 -> 程式繪製的簡單圓形（請把 explosion_frames.png 或 explosion_graph.jpg 放在 {ASSET_DIR}）")

        self.kaiju_frames = load_kaiju_frames()
        load_missile_sprites()
        load_rocket_sprites()
        SHOCK_DOT[:] = make_shock_dots()
        SHOCK_BALL[:] = make_shock_ball()
        SHOT_SPRITES.update(make_shot_sprites())
        BUBBLE_FRAMES.update(make_bubble_frames())
        FIRE_FRAMES[:] = make_fire_frames()
        COMET_FRAMES[:] = make_fire_frames(palette="blue")
        NOVA_FRAMES[:] = make_fire_frames(size=144, palette="nova")
        GREEN_FRAMES[:] = make_fire_frames(size=128, palette="green")
        load_minion_sprites()
        load_saucer_sprites()
        self.snd_shoot = load_sound(["shoot.wav", "shoot.mp3"], 0.2) if self.audio else None
        self.snd_explode = load_sound(["explosion.mp3", "exploresion.mp3"], 0.45) if self.audio else None
        self.snd_over = load_sound(["gameover.mp3"], 0.6) if self.audio else None
        self.music_path = find_asset("background.mp3", "background.ogg") if self.audio else None
        # 魔王虛淵：兩種叫聲（叫聲 2 比叫聲 1 小聲約 5 dB，用音量補齊）與腳步聲
        self.snd_roars = []
        self.snd_steps = []
        if self.audio:
            g = self.BOSS_SFX_GAIN
            r1 = load_sound(["roar_1.mp3", "roar_1.wav"], 1.0)
            r2 = load_sound(["roar_2.mp3", "roar_2.wav"], 1.0)
            self.snd_roars = [boost_sound(x, v * g) for x, v in ((r1, 0.6), (r2, 1.0)) if x]
            step = load_sound(["monster_footstep.mp3", "monster_footstep.wav"], 1.0)
            if step:
                self.snd_steps = split_footsteps(boost_sound(step, 0.45 * g), 1.0)
        self.roar_i = 0
        self.step_i = 0
        # 背景音樂與三位魔王的出場音樂
        self.music_files = {}
        if self.audio:
            for key, (names, _vol) in self.MUSIC.items():
                path = find_asset(*names)
                if path:
                    self.music_files[key] = path
                    if key == "intro":
                        print(f"  [OK]   片頭音樂 {os.path.basename(path)}")
                    elif key != "stage":
                        print(f"  [OK]   魔王音樂 {os.path.basename(path)}")
        self.music_cur = None
        self.music_next = None
        self.music_wait = 0
        # 破關音樂（使用者自己作的曲子）
        self.victory_path = find_asset("final music.mp3", "final_music.mp3", "Final Music.mp3",
                                       "final music.ogg") if self.audio else None
        self.victory_snd = None
        if self.victory_path:
            print(f"  [OK]   破關音樂 {os.path.basename(self.victory_path)}")
            # 破關音樂要放大到超過音量上限：串流播放做不到，所以先整首解碼、截掉開頭、放大波形
            if numpy is not None:
                try:
                    self.victory_snd = slice_and_boost(pygame.mixer.Sound(self.victory_path),
                                                       self.VICTORY_START, self.VICTORY_GAIN)
                except Exception as e:
                    print(f"  [FAIL] 破關音樂放大失敗，改用一般播放：{e}")
        if self.music_path:
            print(f"  [OK]   music  {os.path.basename(self.music_path)}")
        print()

    def load_explosions(self):
        """
        爆炸動畫的載入順序（任何一步失敗都會往下一步退，並印出原因）：
          1. explosion_frames.png：已經去背、置中好的 9 格動畫（最可靠，不需要 numpy）
          2. explosion_graph.jpg：遊戲啟動時自動去背（需要 numpy）
          3. 同一張原圖，用舊的簡易方式切格（至少還是你的圖）
          4. 都沒有才用程式畫的簡單圓形，並在標題畫面顯示警告
        檔名不必完全一致：資料夾裡名稱含有 explosion 的圖片都會被找到。
        """
        global EXPLOSION_ALPHA
        self.asset_warning = None

        def search(prefer):
            """
            先找精確檔名；找不到就往下搜尋子資料夾（最多兩層）。
            從素材網站下載解壓縮的資料夾，常常是「explosion-...」資料夾裡放著一張數字檔名的圖，
            所以資料夾名稱或檔名含有 explosion 的圖片都算；有多張時挑最大的（素材包常附小縮圖）。
            """
            hit = find_asset(*prefer)
            if hit:
                return hit
            want_frames = "frames" in prefer[0]
            best, best_size = None, 0
            base_depth = ASSET_DIR.rstrip(os.sep).count(os.sep)
            try:
                for root, dirs, files in os.walk(ASSET_DIR):
                    if root.count(os.sep) - base_depth >= 2:
                        dirs[:] = []
                    rel = os.path.relpath(root, ASSET_DIR).lower()
                    for name in files:
                        low = name.lower()
                        if not low.endswith((".png", ".jpg", ".jpeg")):
                            continue
                        if "explosion" not in low and "explosion" not in rel:
                            continue
                        if ("frames" in low) != want_frames:
                            continue
                        path = os.path.join(root, name)
                        size = os.path.getsize(path)
                        if size > best_size:
                            best, best_size = path, size
            except OSError:
                pass
            return best

        def finish(frames, how):
            global EXPLOSION_ALPHA
            self.frames_big = frames
            self.frames_small = [pygame.transform.smoothscale(f, (256, 256)) for f in frames]
            for fl in (self.frames_big, self.frames_small):
                EXPLOSION_FLIPS[id(fl)] = [pygame.transform.flip(f, True, True) for f in fl]
            EXPLOSION_ALPHA = True
            print(f"  [OK]   爆炸動畫 {how}")

        pre = search(("explosion_frames.png",))
        if pre:
            try:
                strip = pygame.image.load(pre).convert_alpha()
                fh = strip.get_height()
                n = strip.get_width() // fh
                frames = [strip.subsurface((i * fh, 0, fh, fh)).copy() for i in range(n)]
                if fh != 512:
                    frames = [pygame.transform.smoothscale(f, (512, 512)) for f in frames]
                finish(frames, f"{os.path.basename(pre)}（已去背的 {n} 格）")
                return
            except Exception as e:
                print(f"  [FAIL] {os.path.basename(pre)}：{e}")
        sheet = search(("explosion_graph.jpg", "explosion graph.jpg", "explosion_graph.png", "explosion_graph.jpeg"))
        if sheet:
            if numpy is not None:
                try:
                    finish(process_explosion_sheet(sheet), f"{os.path.basename(sheet)}（啟動時自動去背）")
                    return
                except Exception as e:
                    print(f"  [FAIL] 自動去背失敗，改用簡易切格：{type(e).__name__}: {e}")
            try:
                self.frames_small = slice_explosion_sheet(sheet, 256)
                self.frames_big = slice_explosion_sheet(sheet, 384)
                if ICE:
                    self.frames_small = to_alpha_frames(self.frames_small)
                    self.frames_big = to_alpha_frames(self.frames_big)
                print(f"  [OK]   爆炸動畫 {os.path.basename(sheet)}（簡易切格）")
            except Exception as e:
                print(f"  [FAIL] {os.path.basename(sheet)}：{e}")

    def _fallback_frames(self, size):
        frames = []
        for i in range(9):
            t = i / 8
            s = pygame.Surface((size, size), pygame.SRCALPHA)
            r = int(size / 2 * min(1.0, 0.25 + t * 1.2))
            fade = max(0.0, 1 - max(0.0, (t - 0.5) * 2))
            for rr, col in ((r, (200, 60, 20)), (int(r * .66), (255, 160, 40)),
                            (int(r * .35), (255, 245, 210))):
                if rr > 0:
                    pygame.draw.circle(s, tuple(int(v * fade) for v in col),
                                       (size // 2, size // 2), rr)
            frames.append(s)
        return frames

    def _make_sky(self):
        sky = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
        top, bottom = (18, 8, 38), (46, 18, 70)
        for y in range(SCREEN_H):
            t = y / SCREEN_H
            sky_col = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            pygame.draw.line(sky, sky_col, (0, y), (SCREEN_W, y))
        # 遠方巨大行星
        rng = random.Random(77)
        px, py, pr = SCREEN_W - 190, 120, 105
        for i in range(pr, 0, -1):
            t = i / pr
            c = (int(80 + 80 * (1 - t)), int(40 + 50 * (1 - t)), int(110 + 60 * (1 - t)))
            pygame.draw.circle(sky, c, (px, py), i)
        for _ in range(60):
            x, y = rng.randint(0, SCREEN_W), rng.randint(0, int(CY))
            b = rng.randint(90, 200)
            pygame.draw.circle(sky, (b, b, b), (x, y), 1)
        return sky

    def _make_ice_sky(self):
        """南極晴空：頂部深藍、地平線泛白，右上方低角度太陽與 22° 日暈（冰晶折射，極地特有）。"""
        sky = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
        top, hz = (36, 84, 156), IceTerrain.HAZE
        for y in range(SCREEN_H):
            t = min(1.0, y / CY) ** 1.6
            pygame.draw.line(sky, tuple(int(top[i] + (hz[i] - top[i]) * t) for i in range(3)),
                             (0, y), (SCREEN_W, y))
        sx, sy, sz = IceTerrain.SUN
        spx, spy = CX + sx / sz * FOCAL, CY + sy / sz * FOCAL
        glow_s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        for r in range(260, 0, -4):
            a = int(90 * (1 - r / 260) ** 2)
            pygame.draw.circle(glow_s, (255, 250, 235, a), (int(spx), int(spy)), r)
        halo_r = int(FOCAL * math.tan(math.radians(22)))
        for dr, col in ((-3, (255, 200, 180, 38)), (0, (255, 255, 255, 46)), (3, (190, 210, 255, 34))):
            pygame.draw.circle(glow_s, col, (int(spx), int(spy)), halo_r + dr, 3)
        sky.blit(glow_s, (0, 0))
        return sky

    def _make_vignette(self):
        v = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        depth = 95
        for i in range(depth):
            a = int(110 * (1 - i / depth) ** 2)
            pygame.draw.rect(v, (220, 30, 30, a), (i, i, SCREEN_W - 2 * i, SCREEN_H - 2 * i), 1)
        return v

    # ---------- 紀錄 / 音樂 ----------
    def load_high_score(self):
        try:
            with open(os.path.join(ASSET_DIR, "highscore3d.txt"), "r") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return 0

    def save_high_score(self):
        try:
            with open(os.path.join(ASSET_DIR, "highscore3d.txt"), "w") as f:
                f.write(str(self.high_score))
        except OSError:
            pass

    # 音樂：（檔名候選, 播放音量）。魔王音樂原檔比背景音樂大聲 8~10 dB，
    # 音量調成「比背景音樂略大聲約 3 dB」：有戰鬥升溫的感覺，但不會突然爆音
    MUSIC = {
        "stage": (("background.mp3", "background.ogg"), 0.30),
        # 片頭音樂：原檔比背景音樂大聲約 8 dB（-14.7 LUFS），音量 0.22 = 比背景音樂略大聲 3 dB
        "intro": (("intro_music.mp3", "intro_music.ogg"), 0.22),
        "mini":  (("smallbossmusic.mp3", "small_boss_music.mp3"), 0.85),          # 原本 0.17，加大 5 倍
        "mid":   (("mediumbossmusic.mp3", "medium_boss_music.mp3"), 0.80),        # 原本 0.16，加大 5 倍
        "final": (("final-boss-music.mp3", "final_boss_music.mp3", "finalbossmusic.mp3"), 0.80),  # 原本 0.16
    }

    def _start_music(self, key):
        path = self.music_files.get(key)
        self.music_cur = key
        if not path:
            return
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.MUSIC[key][1])
            pygame.mixer.music.play(-1, fade_ms=800)
        except pygame.error as e:
            print(f"  [FAIL] 音樂 {os.path.basename(path)}：{e}")

    def music_to(self, key):
        """切換音樂：舊的淡出 0.6 秒，再讓新的淡入 0.8 秒，不會硬切。"""
        if key == self.music_cur and self.music_next is None or key == self.music_next:
            return
        if key not in self.music_files and key != "stage":
            key = "stage"                                   # 缺少魔王音樂檔：維持背景音樂
            if key == self.music_cur and self.music_next is None:
                return
        if self.music_cur is None or not pygame.mixer.music.get_busy():
            self.music_next = None
            self._start_music(key)
            return
        pygame.mixer.music.fadeout(600)
        self.music_next = key
        self.music_wait = 38                                # 約 0.63 秒後接上新音樂

    def desired_music(self):
        b = self.boss
        if isinstance(b, KaijuBoss):
            return "final"                                  # 大魔王：虛淵（倒下過程中也維持）
        if b is not None:
            return "mid"                                    # 中魔王：母艦
        if any(e.alive and e.etype == 3 for e in self.enemies):
            return "mini"                                   # 小魔王：飛碟（擊落或撤退後切回）
        return "stage"

    def update_music(self):
        """每幀呼叫：處理淡出後的接續，並在遊戲中依場上魔王決定該播哪首。"""
        if not self.audio:
            return
        if self.music_next is not None:
            self.music_wait -= 1
            if self.music_wait <= 0:
                key, self.music_next = self.music_next, None
                self._start_music(key)
        if self.state == self.STATE_PLAY:
            self.music_to(self.desired_music())

    def play_music(self):
        """新局：直接從背景音樂開始。"""
        if not self.audio:
            return
        self.ch_victory.stop()                              # 勝利畫面按 R 重玩：停掉破關音樂
        self.music_next = None
        self._start_music("stage")

    # ---------- 魔王虛淵的叫聲與腳步聲 ----------
    def boss_pan(self, b):
        """距離越近越大聲；在畫面左邊時聲音偏左邊喇叭。"""
        k = max(0.3, min(1.0, (3600 - b.z) / 1900))
        pan = max(-1.0, min(1.0, b.x / 600))
        return k * (1 - 0.55 * max(0.0, pan)), k * (1 + 0.55 * min(0.0, pan))

    def kaiju_step(self, b, shake=4):
        """虛淵的腳落地：播放下一步的腳步聲（輪流使用切出來的幾步），畫面跟著震一下。"""
        self.shake = max(self.shake, shake)
        if not self.snd_steps or not self.audio:
            return
        if len(self.snd_steps) == 1:                    # 切割失敗：整檔循環
            if not self.ch_step[0].get_busy():
                self.ch_step[0].play(self.snd_steps[0], loops=-1)
            self.ch_step[0].set_volume(*self.boss_pan(b))
            return
        snd = self.snd_steps[self.step_i % len(self.snd_steps)]
        ch = self.ch_step[self.step_i % 2]               # 兩個聲道輪流：上一步的餘韻不會被切掉
        self.step_i += 1
        ch.play(snd)
        ch.set_volume(*self.boss_pan(b))

    def kaiju_roar(self, b, which=None):
        """叫聲 1、叫聲 2 輪流；回傳這一聲的長度（秒），用來排下一聲的時間。"""
        if not self.snd_roars or not self.audio:
            return 4.0
        if which is None:
            which = self.roar_i % len(self.snd_roars)
            self.roar_i += 1
        snd = self.snd_roars[which % len(self.snd_roars)]
        self.ch_roar.play(snd)
        self.ch_roar.set_volume(*self.boss_pan(b))
        return snd.get_length()

    def stop_boss_audio(self):
        if self.audio:
            self.ch_roar.stop()
            for ch in self.ch_step:
                ch.stop()

    def sync_boss_audio(self):
        """暫停時魔王的聲音一起暫停；回到標題或遊戲結束就停掉。叫聲會跟著魔王的位置移動聲像。"""
        if not self.audio:
            return
        chans = [self.ch_roar] + self.ch_step
        if self.state == self.STATE_PAUSE:
            for ch in chans:
                ch.pause()
            return
        for ch in chans:
            ch.unpause()
        if self.state in (self.STATE_TITLE, self.STATE_OVER):
            self.stop_boss_audio()
        elif isinstance(self.boss, KaijuBoss) and not self.boss.dying and self.ch_roar.get_busy():
            self.ch_roar.set_volume(*self.boss_pan(self.boss))

    BOSS_SFX_GAIN = 3.0           # 魔王虛淵的叫聲與腳步聲整體放大倍數
    VICTORY_START = 5.0           # 破關音樂從第 5 秒開始播
    VICTORY_GAIN = 1.35           # 破關音樂音量：原本 0.45 再加大 3 倍（超過上限 1.0，改用放大波形）
    VICTORY_VOLUME = 1.0          # 無法放大波形時（沒有 numpy）的退路：直接用最大音量

    def play_victory_music(self):
        """擊敗虛淵：播放破關音樂，從第 5 秒切入並淡入 1.5 秒（中途切入才不會太突兀）。"""
        if not self.victory_path:
            return
        self.music_cur = "victory"
        self.music_next = None
        if self.victory_snd is not None:                   # 已放大的版本：用專屬聲道播放
            pygame.mixer.music.stop()
            self.ch_victory.play(self.victory_snd, fade_ms=1500)
            return
        try:
            pygame.mixer.music.load(self.victory_path)
            pygame.mixer.music.set_volume(self.VICTORY_VOLUME)
            try:
                pygame.mixer.music.play(0, start=self.VICTORY_START, fade_ms=1500)
            except (pygame.error, TypeError):
                pygame.mixer.music.play(0)              # 不支援指定起點時：至少從頭播
        except pygame.error as e:
            print(f"  [FAIL] 破關音樂：{e}")

    def stop_music(self):
        if self.audio:
            pygame.mixer.music.stop()
            self.ch_victory.stop()
        self.music_cur = None
        self.music_next = None

    # ---------- 新局 ----------
    def reset(self):
        self.stop_boss_audio() if hasattr(self, "ch_roar") else None
        self.ship = Ship3D()
        self.enemies = []
        self.bullets = []
        self.missiles = []
        self.novas = []               # 原子吐息能量彈
        self.plasmas = []
        self.rails = []
        self.enemy_bullets = []
        self.explosions = []
        self.powerups = []
        self.texts = []
        self.particles = Particles3D()
        for wid, ammo in STARTING_LOADOUT.items():     # 開局附送的武器
            self.ship.arsenal[wid] = {"level": 1, "ammo": ammo}
        self.beam = None              # 正在發射的原子光束
        self.charge = 0               # 原子光束蓄力幀數
        self.atomic_cd = 0
        self.charge_snd = None
        self.switch_popup = None      # 切換武器時的提示（文字, 說明, 顏色, 剩餘幀數）
        self.slot_pulse = 0
        self.prev_wkeys = {}
        self.boss_med_t = 0           # 魔王戰補血包的投放計時
        self.frame_no = 0
        self.play_frames = 0          # 任務計時 T+（遊玩的幀數）
        self.last_fire = 0
        self.fire_stuck = 0
        self.wheel_cd = 0
        # 開局提示：很多人沒注意到 7 號是原子光束、也不知道它要「按住蓄力、放開發射」
        self.switch_popup = ("PRESS 7: ATOMIC BREATH", "Hold SPACE to charge, release to fire",
                             (120, 200, 255), 240)

        self.boss = None
        self.boss_spawned = False

        self.score = 0
        self.wave = 1
        self.kills = 0
        self.kills_needed = 8
        self.combo = 0
        self.combo_timer = 0
        self.max_combo = 0
        self.bombs = 2
        self.bomb_cd = 0
        self.prev_bomb_key = False
        self.prev_shock_key = False
        self.shockwaves = []          # 場上飛行中的衝擊波
        self.shock_charges = 5        # 大絕使用次數
        self.shock_cd = 0             # 避免一口氣把五次按完
        self.spawn_timer = 0
        self.miniboss_pending = False   # 已抽到小 BOSS，正在等場面清空
        self.miniboss_stage = 0         # 0 打小兵、1 小魔王登場中、2 已擊敗
        self.shake = 0.0
        self.flash = 0
        self.freeze = 0
        self.over_handled = False
        self.laser_on = 0
        self.laser_level = 1
        self.laser_tick = 0
        self.world_speed = 26.0        # 星流與地面的前進速度

    # ---------- 生成 ----------
    def is_boss_wave(self):
        return self.wave in (MID_BOSS_WAVE, FINAL_BOSS_WAVE)

    def spawn_interval(self):
        base = max(16, 46 - self.wave * 3)
        return int(base * 2.4) if self.boss else base

    def miniboss_on_field(self):
        """場上是否有小 BOSS（飛碟）。"""
        return any(e.alive and e.cfg["behavior"] == "saucer" for e in self.enemies)

    def spawn(self):
        # --- 小 BOSS 單挑規則 ---
        # 1. 牠在場上時，完全不出其他敵人
        if self.miniboss_on_field():
            return
        # 2. 抽到牠之後先暫停出怪，等場面自然清空，牠才單獨登場。
        #    這個空檔本身就是節奏：畫面先安靜下來，然後大傢伙出現。
        if self.miniboss_pending:
            # 大 BOSS 戰期間不放小 BOSS：兩者用同一張飛碟圖，
            # 同時出現會讓玩家分不清該打哪一個。排程保留到母艦被打掉之後。
            if self.boss or self.enemies:
                return
            self.miniboss_pending = False
            v = max(0, min(2, self.wave - 1))                 # 第幾隻小魔王：0 原色、1 藍、2 黑
            e = Enemy3D(3, self.img_saucers[v], self.wave, random.uniform(-220, 220), random.uniform(-120, 60))
            e.scripted = True                                 # 劇本魔王：不會自動撤退，擊敗才過關
            e.variant = v                                     # 3D 飛碟配色：0 粉紅、1 藍、2 黑
            e.hp += v * 10                                    # 一隻比一隻強
            if v:                                             # 光暈與子彈顏色跟著機身：藍色 / 深色
                e.cfg = dict(e.cfg, color=((70, 150, 255), (45, 45, 62))[v - 1])
            self.enemies.append(e)
            name, col = MINI_BOSS_STYLE[v]
            self.texts.append(FloatText3D((CX, CY - 30), f"!! {name} !!", col, self.font_l, life=110, rise=0.22))
            return

        if self.boss:
            etype = random.choice((1, 2))
        else:
            w = self.wave
            # 順序對應 [E1漂移, E2蛇行, E3飛碟(小BOSS), E4獵人]
            weights = [max(1, 55 - w * 4), 30 + w, 0, 10 + w * 2]      # 小魔王改由關卡劇本安排，不再隨機出現
            etype = random.choices([1, 2, 3, 4], weights=weights)[0]

        if etype == 3:
            self.miniboss_pending = True     # 排程小 BOSS，等場面清空
            return

        if random.random() < 0.12:
            # 編隊：橫向一列或 V 字
            cx = random.uniform(-380, 380)
            cy = random.uniform(-160, 200)
            for i, (ox, oy, oz) in enumerate([(0, 0, 0), (-190, -40, 220), (190, -40, 220),
                                              (-380, -80, 440), (380, -80, 440)]):
                self.enemies.append(Enemy3D(1, self.img_enemies[1], self.wave,
                                            cx + ox, cy + oy, SPAWN_Z + oz))
        else:
            self.enemies.append(Enemy3D(etype, self.img_enemies[etype], self.wave))

    # ---------- 效果 ----------
    def boom(self, pos, big=False):
        self.explosions.append(Explosion3D(
            pos, self.frames_big if big else self.frames_small,
            world_size=420 if big else 260))
        if self.snd_explode:
            self.snd_explode.play()
        p = project(*pos)
        depth_scale = p[2] if p else 0.3
        self.shake = max(self.shake, min(14, (9 if big else 5) * (0.5 + depth_scale * 2)))
        self.particles.burst(pos, 14 if big else 8, (255, 190, 90),
                             speed=14 if big else 9)

    def add_score(self, base, pos):
        mult = min(5, 1 + self.combo // 4)
        gained = base * mult
        self.score += gained
        p = project(*pos)
        if p:
            label = f"+{gained}" + (f"  x{mult}" if mult > 1 else "")
            self.texts.append(FloatText3D((p[0], p[1]), label, YELLOW, self.font_s))
        return gained

    def on_kill(self, enemy):
        if getattr(enemy, "scripted", False):
            self.miniboss_stage = 2                             # 擊敗劇本小魔王：過關
        self.kills += 1
        self.combo += 1
        self.combo_timer = 110
        self.max_combo = max(self.max_combo, self.combo)
        pos = enemy.pos()
        self.add_score(enemy.score, pos)
        big = enemy.cfg["behavior"] == "saucer"
        self.boom(pos, big=big)
        self.particles.burst(pos, 10, enemy.cfg["color"], speed=11)
        if big:
            self.freeze = 3
        self.maybe_drop(enemy)

    def drop_heal(self, pos):
        self.powerups.append(PowerUp3D(pos, "heal"))

    def heal_supply(self, ahead=700):
        """在玩家前方投放一個補血包（會被磁吸過來）。"""
        s = self.ship
        self.drop_heal((s.x + random.uniform(-150, 150), s.y - 60, s.z + ahead))

    def maybe_drop(self, enemy):
        # 補血包獨立擲骰：不跟武器包、其他補給搶同一次機會，而且血越少越容易掉
        ratio = self.ship.hp / self.ship.max_hp
        heal_p = {1: 0.07, 2: 0.09, 3: 0.55, 4: 0.13}[enemy.etype]
        if ratio < 0.5:
            heal_p *= 2.0
        if ratio < 0.25:
            heal_p *= 1.6
        if ratio < 0.95 and random.random() < heal_p:
            self.drop_heal(enemy.pos())
            return
        chance = {1: 0.12, 2: 0.17, 3: 0.80, 4: 0.26}[enemy.etype]
        if random.random() >= chance:
            return
        low = self.ship.hp < self.ship.max_hp * 0.5
        kinds, w = (["heal", "power", "shield", "bomb"], [0.45, 0.25, 0.18, 0.12]) if low \
            else (["power", "shield", "heal", "bomb"], [0.4, 0.24, 0.22, 0.14])
        # 三成機率掉武器包而不是一般補給；飛碟一定掉武器
        weapon_chance = 0.9 if enemy.cfg["behavior"] == "saucer" else 0.42
        if random.random() < weapon_chance:
            self.powerups.append(WeaponPack3D(enemy.pos(), random.choice(DROPPABLE_WEAPONS)))
        else:
            self.powerups.append(PowerUp3D(enemy.pos(), random.choices(kinds, w)[0]))

    def open_window(self, fullscreen):
        """
        全螢幕：交給顯示卡把 1280x720 的畫面等比放大到整個螢幕（SCALED）。
        16:9 螢幕會剛好佈滿；其他比例的螢幕會自動加上最少的黑邊，畫面不會被拉長變形。
        """
        self.fullscreen = fullscreen
        flags = pygame.SCALED | (pygame.FULLSCREEN if fullscreen else 0)
        for kw in ({"vsync": 1}, {}):                    # 先試垂直同步（畫面不撕裂），不支援就不用
            try:
                scr = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags, **kw)
                pygame.mouse.set_visible(not fullscreen)    # 全螢幕時隱藏游標（滑鼠左鍵射擊照常）
                return scr
            except pygame.error:
                continue
        self.fullscreen = False
        return pygame.display.set_mode((SCREEN_W, SCREEN_H))

    def toggle_fullscreen(self):
        try:
            pygame.display.toggle_fullscreen()
            self.fullscreen = not self.fullscreen
            pygame.mouse.set_visible(not self.fullscreen)
        except pygame.error:
            pass
        self.disable_ime()

    def disable_ime(self):
        """
        停用遊戲視窗的文字輸入（輸入法）。pygame 2 預設會開啟文字輸入，
        中文輸入法因此能攔截空白鍵與數字鍵拿去選字，遊戲就收不到射擊與選武器的按鍵。
        """
        try:
            pygame.key.stop_text_input()
        except Exception:
            pass
        self.prev_wkeys = {}

    # ---------- 標題畫面：金屬風主視覺 + JoJo 風（集中線、粗描邊、ゴゴゴ） ----------
    @staticmethod
    def _chrome_text(font, text, stops, outline=6, depth=0, depth_col=(70, 0, 60)):
        """金屬漸層字：立體厚度（往右下堆疊）+ 粗黑描邊 + 漸層填色。"""
        mask = font.render(text, True, (255, 255, 255))
        w, h = mask.get_size()
        grad = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            t = y / max(1, h - 1)
            for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
                if p0 <= t <= p1:
                    k = (t - p0) / max(1e-6, p1 - p0)
                    col = tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3))
                    break
            pygame.draw.line(grad, col + (255,), (0, y), (w, y))
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        pad = outline + depth + 4
        out = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        black = font.render(text, True, (8, 4, 12))
        for d in range(depth, 0, -1):                     # 立體厚度
            ext = font.render(text, True, depth_col)
            for ox in range(-outline, outline + 1, 3):
                out.blit(black, (pad + d + ox, pad + d - outline))
                out.blit(black, (pad + d + ox, pad + d + outline))
            out.blit(ext, (pad + d, pad + d))
        for ox in range(-outline, outline + 1, 2):        # 粗黑描邊
            for oy in range(-outline, outline + 1, 2):
                if ox * ox + oy * oy <= outline * outline:
                    out.blit(black, (pad + ox, pad + oy))
        out.blit(grad, (pad, pad))
        return out

    # ---------- 標題主視覺：MEGALON 與戰機交戰 ----------
    def _init_title_scene(self):
        """獨立的一組 MEGALON、戰機、子彈、爆炸、粒子，不會影響正式遊戲的狀態。"""
        class _Proxy:                                       # 光束需要「目標」與「遊戲」：給它假的，不會造成傷害
            pass
        ts = _Proxy()
        ts.t = 0
        ts.boss = None
        if self.kaiju_frames:
            b = KaijuBoss(self.kaiju_frames, FINAL_BOSS_WAVE)
            b.entering, b.phase2 = False, True              # 第二階段：白熾形態最有壓迫感
            b.x, b.z = 230.0, 1700.0
            ts.boss = b
        sh = Ship3D()
        sh.x, sh.y, sh.z = -250.0, 170.0, 420.0          # 拉近到前景：戰機是主角之一
        ts.ship = sh
        ts.bullets, ts.booms, ts.beam = [], [], None
        ts.hole = None                                      # Megalon 的黑洞攻擊
        ts.novas = []                                       # 戰機的原子吐息
        ts.charge = 0.0
        ts.particles = Particles3D()
        ts.target = _Proxy()
        ts.target.radius = 1
        ts.target.hit = lambda d: False
        ts.game = _Proxy()
        ts.game.ship, ts.game.particles, ts.game.shake, ts.game.world_speed = ts.target, ts.particles, 0, 0
        self.title_scene = ts

    def update_title_scene(self):
        ts = getattr(self, "title_scene", None)
        if ts is None:
            self._init_title_scene()
            ts = self.title_scene
        ts.t += 1
        t = ts.t
        s, b = ts.ship, ts.boss
        # 戰機：大角度傾斜、上下微微浮動
        s.x = -215 + 22 * math.sin(t * 0.017)
        s.y = 165 + 18 * math.sin(t * 0.03)
        s.roll = 0.42 + 0.08 * math.sin(t * 0.025)
        s.pitch = -0.06
        if b:
            cyc = t % 300                                   # 鐮刀臂輪流高舉
            b.raise_arms = 2 if 175 < cyc < 250 else (1 if 155 < cyc <= 175 or 250 <= cyc < 268 else 0)
            if ts.hole is not None and ts.hole.t < 50:
                b.raise_arms = 2                           # 發動黑洞時高舉雙臂
            b.x = 230 + 40 * math.sin(t * 0.01)
            b.walk += 0.02
            charging = ts.hole is not None and ts.hole.t < 45
            target = 1.9 if charging else (1.4 if ts.hole else 1.15 + 0.25 * math.sin(t * 0.07))
            b.glow_k += (target - b.glow_k) * 0.1
            if b.flash > 0:
                b.flash -= 1
            # 戰機的原子吐息：蓄力約 0.8 秒 -> 發射巨型能量彈 -> 轉向飛往 MEGALON 胸口 -> 命中連環爆炸
            cyc = t % 200
            ts.charge = (cyc - 140) / 50 if 140 <= cyc < 190 else 0.0
            if cyc == 190:
                ts.novas.append(NovaOrb3D(s.x, s.y - 20, s.z, 3, 1.0, 0))
            cx, cy, cz = b.core_world()
            for n in ts.novas:
                n.update(ts.particles)
                n.x += (cx - n.x) * 0.06                          # 轉向 MEGALON 的胸口
                n.y0 += (cy - n.y) * 0.06
                if n.z >= cz - 140:
                    n.alive = False
                    b.flash = 8
                    for k in range(3):
                        ts.booms.append(Explosion3D((cx + random.uniform(-120, 120), cy + random.uniform(-120, 120), cz - 60),
                                                    self.frames_big, delay=2 + k, world_size=random.uniform(360, 520)))
                    ts.particles.burst((cx, cy, cz - 60), 30, (210, 140, 255), speed=18)
            ts.novas = [n for n in ts.novas if n.alive]
            # MEGALON 每隔幾秒發動黑洞攻擊：在戰機右前方生成黑洞，把戰機往中心拖
            if ts.hole is None and t % 420 == 90:
                ts.hole = KBlackHole(s.x + 260, s.y - 40, s.z + 420)
            if ts.hole is not None:
                ts.target.x, ts.target.y, ts.target.z = s.x, s.y, s.z
                ts.hole.update(ts.game)
                k = ts.hole.scale()
                s.x += (ts.hole.x - s.x) * 0.22 * k                # 戰機被重力拉偏、機身傾斜（奮力抵抗）
                s.y += (ts.hole.y - s.y) * 0.08 * k
                s.roll -= 0.3 * k
                if not ts.hole.alive:
                    ts.hole = None
        for ex in ts.booms:
            ex.update(0)
        ts.booms = [e for e in ts.booms if e.alive]
        ts.particles.update(0)

    def draw_boss_beam_glow(self, c, beams):
        """MEGALON 閃電光束的外圍光暈：畫在獨立的透明圖層，再整張疊上。"""
        beams = [b for b in beams if b.firing()]
        if not beams:
            return
        if not hasattr(self, "fx_layer2"):
            self.fx_layer2 = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            self.fx_layer2.fill((0, 0, 0, 0))
            self._glow2_box = None
        if self._glow2_box is not None:                    # 只清掉上一幀畫過的範圍
            self.fx_layer2.fill((0, 0, 0, 0), self._glow2_box)
        box = None
        for bm in beams:
            r = bm.draw_glow(self.fx_layer2)
            if r:
                box = r if box is None else box.union(r)
        if box is not None:
            box = box.clip(self.fx_layer2.get_rect())
            c.blit(self.fx_layer2, box.topleft, box)      # 只合成光束實際覆蓋的範圍
        self._glow2_box = box

    def draw_title_scene(self, c):
        ts = getattr(self, "title_scene", None)
        if ts is None:
            return
        items = []
        b = ts.boss
        if b:
            items.append((b.z, lambda: b.draw(c, None)))
            if ts.hole is not None:
                q = project(*ts.hole.pos())
                if q:
                    items.append((ts.hole.z, lambda q=q: ts.hole.draw(c, q)))
        for bl in ts.bullets:
            p = project(*bl.pos())
            if p:
                items.append((bl.z, lambda bl=bl, p=p: bl.draw(c, p)))
        for ex in ts.booms:
            p = project(ex.x, ex.y, ex.z)
            if p:
                items.append((ex.z - 1, lambda ex=ex, p=p: ex.draw(c, p)))
        parts = []
        ts.particles.collect(parts)
        for z, _k, obj in parts:
            x, y, pz, tt, color, size = obj
            p = project(x, y, pz)
            if p:
                r = max(1, int(size * p[2] * tt * 2.4))
                items.append((z, lambda p=p, r=r, color=color, tt=tt:
                              blit_glow(c, (int(p[0]), int(p[1])), r * 2, tuple(int(v * tt) for v in color))))
        for n in getattr(ts, "novas", []):
            q = project(*n.pos())
            if q:
                items.append((n.z, lambda n=n, q=q: n.draw(c, q)))
        items.append((ts.ship.z, lambda: ts.ship.draw(c)))
        if getattr(ts, "charge", 0) > 0:                       # 蓄力：機頭聚集越來越大的紫色光球
            gp = ts.ship.gun_ports()
            q = project(sum(g[0] for g in gp) / len(gp), sum(g[1] for g in gp) / len(gp) - 10,
                        sum(g[2] for g in gp) / len(gp) + 40)
            if q:
                k = ts.charge
                items.append((ts.ship.z - 1, lambda q=q, k=k: (
                    blit_glow(c, (int(q[0]), int(q[1])), max(6, int((20 + 70 * k) * q[2])), (150, 70, 255)),
                    pygame.draw.circle(c, (245, 235, 255), (int(q[0]), int(q[1])), max(2, int((4 + 16 * k) * q[2]))))))
        for _z, fn in sorted(items, key=lambda it: -it[0]):
            fn()


    def _build_title(self):
        W, H = SCREEN_W, SCREEN_H
        # 紫到洋紅的斜向漸層 + 漫畫集中線（中央留空給標題）
        over = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(H):                                   # 只在上下緣加紫色漸層，中央留給戰鬥場景
            t = y / H
            a = max(0.0, 1 - t / 0.34) ** 1.4 * 190 + max(0.0, (t - 0.72) / 0.28) ** 1.4 * 200
            pygame.draw.line(over, (int(70 + 90 * t), 0, int(110 - 20 * t), int(a)), (0, y), (W, y))
        rng = random.Random(7)
        cx, cy = W // 2, int(H * 0.42)
        for i in range(90):
            a = i / 90 * math.tau + rng.uniform(-0.02, 0.02)
            r0 = rng.uniform(560, 700)                        # 集中線只留在外圍
            spread = rng.uniform(0.006, 0.016)
            far = 1600
            pts = [(cx + math.cos(a) * r0, cy + math.sin(a) * r0 * 0.62),
                   (cx + math.cos(a - spread) * far, cy + math.sin(a - spread) * far * 0.62),
                   (cx + math.cos(a + spread) * far, cy + math.sin(a + spread) * far * 0.62)]
            pygame.draw.polygon(over, (10, 0, 20, rng.randint(50, 110)), pts)
        chrome = ((0.0, (205, 235, 255)), (0.46, (255, 255, 255)), (0.5, (70, 40, 120)),
                  (0.78, (170, 110, 235)), (1.0, (245, 210, 255)))
        title = self._chrome_text(self.font_title, "ALIEN ADVENTURE", chrome, outline=6, depth=9)
        title = pygame.transform.rotozoom(title, 5, 0.78)
        gold = ((0.0, (255, 250, 190)), (0.5, (255, 215, 40)), (0.52, (220, 110, 0)), (1.0, (255, 180, 40)))
        badge = pygame.transform.rotozoom(self._chrome_text(self.font_badge, "3D", gold, outline=7, depth=7,
                                                            depth_col=(120, 40, 0)), -10, 0.72)
        gos = []
        if self.font_go:
            for size, col in ((1.0, (170, 70, 235)), (0.75, (200, 90, 255)), (0.55, (140, 50, 210))):
                g = self._chrome_text(self.font_go, "ゴ", ((0.0, (230, 170, 255)), (1.0, col)), outline=5)
                gos.append(pygame.transform.rotozoom(g, 0, size))
        self._title_cache = (over, title, badge, gos)

    def draw_title(self, c):
        if self._title_cache is None:
            self._build_title()
        over, title, badge, gos = self._title_cache
        t = pygame.time.get_ticks() / 1000.0
        self.draw_title_scene(c)                           # MEGALON 與戰機交戰
        c.blit(over, (0, 0))
        # ゴゴゴ：圍繞在 MEGALON 身邊（JoJo 的威壓感）
        ts = getattr(self, "title_scene", None)
        bx, by = SCREEN_W * 0.7, SCREEN_H * 0.4
        if ts is not None and ts.boss is not None:
            q = project(ts.boss.x, ts.boss.ground() - 650, ts.boss.z)
            if q:
                bx, by = q[0], q[1]
        spots = ((bx + 270, by + 70, 0, 0.0), (bx + 330, by + 210, 1, 0.7), (bx + 230, by + 330, 2, 1.3),
                 (bx - 250, by - 10, 1, 0.4))
        for x, y, k, ph in spots:
            if k < len(gos):
                g = gos[k]
                dy = math.sin(t * 2.2 + ph) * 8
                sc = 1 + 0.06 * math.sin(t * 3.1 + ph)
                im = pygame.transform.rotozoom(g, math.sin(t + ph) * 6, sc)
                c.blit(im, im.get_rect(center=(x, y + dy)))
        bob = math.sin(t * 1.6) * 5
        r = title.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.15 + bob)))
        c.blit(title, r)
        c.blit(badge, badge.get_rect(center=(r.right - 110, r.bottom + 22 + bob * 0.5)))
        # PRESS SPACE：閃爍
        a = int(150 + 105 * math.sin(t * 4))
        txt = "PRESS  SPACE"
        img = self.font_press.render(txt, True, (255, 255, 255))
        blk = self.font_press.render(txt, True, (10, 0, 20))
        pos = img.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.87)))
        layer = pygame.Surface((img.get_width() + 8, img.get_height() + 8), pygame.SRCALPHA)
        for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2), (3, 3)):
            layer.blit(blk, (4 + ox, 4 + oy))
        layer.blit(img, (4, 4))
        layer.set_alpha(a)
        c.blit(layer, pos.move(-4, -4))
        hint = self.font_hud_s.render("B  FINAL BOSS      F11  FULLSCREEN      ESC  QUIT", True, (215, 200, 235))
        c.blit(hint, hint.get_rect(center=(SCREEN_W // 2, SCREEN_H - 34)))

    # ---------- 遙測儀表板：火箭發射直播風（白色細線、圓弧儀表、任務時間軸） ----------
    def _tel_fonts(self):
        if getattr(self, "_tf", None):
            return self._tf
        L, R, B = (find_asset(f"Barlow-{w}.ttf") for w in ("Light", "Regular", "SemiBold"))
        mk = lambda path, size: pygame.font.Font(path, size) if path else pygame.font.Font(None, int(size * 1.35))
        self._tf = dict(val=mk(B, 30), valsm=mk(B, 23), lab=mk(R, 13), clock=mk(L, 30), tl=mk(R, 12),
                        unit=mk(L, 13), pct=mk(B, 15), labb=mk(B, 14), pop=mk(B, 26), popd=mk(L, 16),
                        warn=mk(B, 28))
        self._spaced_cache = {}
        return self._tf

    def spaced(self, font, text, color, track=3):
        """字距拉寬的小型大寫標籤（逐字繪製；同樣的字串會快取起來重複使用）。"""
        key = (id(font), text, color, track)
        img = self._spaced_cache.get(key)
        if img is None:
            glyphs = [font.render(ch, True, color) for ch in text]
            w = sum(g.get_width() for g in glyphs) + track * (len(glyphs) - 1)
            img = pygame.Surface((max(1, w), max(g.get_height() for g in glyphs)), pygame.SRCALPHA)
            x = 0
            for g in glyphs:
                img.blit(g, (x, 0))
                x += g.get_width() + track
            if len(self._spaced_cache) > 300:
                self._spaced_cache.clear()
            self._spaced_cache[key] = img
        return img

    @staticmethod
    def _arc_pts(cx, cy, r, t0, t1, steps=60):
        """儀表弧線上的點：t=0 在左下、t=1 在右下，順時針掃過 270°（像速度表）。"""
        pts = []
        for i in range(steps + 1):
            t = t0 + (t1 - t0) * i / steps
            a = math.radians(225 - 270 * t)
            pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
        return pts

    def _aa_arc(self, surf, cx, cy, r, t0, t1, color, width):
        """抗鋸齒弧線：用幾條相鄰半徑的抗鋸齒細線疊出粗細。"""
        if t1 - t0 < 0.003:
            return
        steps = max(4, int(70 * (t1 - t0)))
        for k in range(width):
            pygame.draw.aalines(surf, color, False, self._arc_pts(cx, cy, r - (width - 1) / 2 + k, t0, t1, steps))

    @staticmethod
    def _aa_dot(surf, x, y, r, color):
        pygame.gfxdraw.filled_circle(surf, int(x), int(y), r, color)
        pygame.gfxdraw.aacircle(surf, int(x), int(y), r, color)

    def draw_status(self, surf):
        """左上：機體狀態（JoJo 風紫色面板）。"""
        f = self._jj_fonts()
        s = self.ship
        x, y = 10, 8
        surf.blit(self._jj_panel(258, 104, 16, (140, 50, 200)), (x, y))
        ratio = max(0.0, s.hp / s.max_hp)
        surf.blit(self._jj_t(f["lab"], "HULL", (255, 228, 40)), (x + 30, y + 12))
        pi = self._jj_t(f["pct"], f"{int(ratio * 100)}%", (255, 255, 255))
        surf.blit(pi, (x + 250 - pi.get_width(), y + 6))
        c0, c1 = ((90, 230, 120), (210, 255, 90)) if ratio > 0.5 else (((255, 200, 40), (255, 240, 120)) if ratio > 0.25
                                                                        else ((255, 50, 40), (255, 140, 60)))
        self._jj_bar(surf, x + 26, y + 38, 218, 16, ratio, c0, c1)
        ix = x + 28
        surf.blit(self._jj_t(f["chip"], "LIFE", (255, 255, 255)), (ix, y + 66))
        for i in range(max(3, s.lives)):
            self._star(surf, ix + 52 + i * 18, y + 74, 7, (255, 228, 40) if i < s.lives else (70, 60, 80))
        bx = ix + 120
        surf.blit(self._jj_t(f["chip"], "BOMB", (255, 255, 255)), (bx, y + 66))
        for i in range(max(3, self.bombs)):
            cx, cy = bx + 54 + i * 16, y + 74
            pts = [(cx, cy - 7), (cx + 6, cy), (cx, cy + 7), (cx - 6, cy)]
            pygame.draw.polygon(surf, (255, 70, 180) if i < self.bombs else (70, 60, 80), pts)
            pygame.draw.polygon(surf, (8, 4, 12), pts, 2)
        surf.blit(self._jj_t(f["chip"], "SHOCK", (255, 255, 255)), (ix, y + 88))
        ready = self.shock_cd == 0
        for i in range(max(5, self.shock_charges)):
            cx, cy = ix + 60 + i * 18, y + 96
            have = i < self.shock_charges
            pygame.draw.circle(surf, ((80, 230, 255) if ready else (60, 140, 160)) if have else (70, 60, 80), (cx, cy), 6)
            pygame.draw.circle(surf, (8, 4, 12), (cx, cy), 6, 2)
        surf.blit(self._jj_t(f["chip"], "K", (255, 255, 255)), (ix + 60 + max(5, self.shock_charges) * 18, y + 88))

    def draw_telemetry(self, surf):
        """上方中央：關卡卡片 + 進度條 + 任務計時；右上：分數與連擊；魔王血條。（JoJo 風）"""
        f = self._jj_fonts()
        W = SCREEN_W
        t = pygame.time.get_ticks() / 1000.0
        names = ("STAGE 1", "STAGE 2", "STAGE 3", "MOTHERSHIP", "MEGALON")
        n = len(names)
        step = 112
        x0 = W // 2 - step * n // 2 + step // 2
        cur = max(0, min(self.wave, n) - 1)
        for i, name in enumerate(names):                                   # 關卡卡片
            if i == cur:
                continue
            col = (140, 50, 200) if i < cur else (70, 70, 84)
            card = self._jj_panel(94, 22, 8, col, tone=False)
            cx = x0 + i * step
            surf.blit(card, card.get_rect(center=(cx, 26)))
            ti = self._jj_t(f["chip"], name, (255, 255, 255) if i < cur else (165, 165, 178))
            surf.blit(ti, ti.get_rect(center=(cx + 2, 25)))
        cx = x0 + cur * step                                               # 目前關卡：黃色放大、輕微浮動
        card = pygame.transform.rotozoom(self._jj_panel(94, 22, 8, (255, 214, 40), tone=False), 3, 1.18)
        bob = math.sin(t * 4) * 1.5
        surf.blit(card, card.get_rect(center=(cx, 25 + bob)))
        ti = pygame.transform.rotozoom(self._jj_t(f["chip"], names[cur], (8, 4, 12), ow=0), 3, 1.18)
        surf.blit(ti, ti.get_rect(center=(cx + 2, 24 + bob)))
        if self.boss is not None:
            prog = 1 - max(0.0, self.boss.hp / self.boss.max_hp)
        elif self.miniboss_stage:
            prog = 0.92
        else:
            prog = 0.85 * min(1.0, self.kills / max(1, self.kills_needed))
        bw = step * (n - 1) + 60
        bx = W // 2 - bw // 2
        self._jj_bar(surf, bx, 48, bw - 120, 10, prog, (255, 200, 40), (255, 245, 140), sk=4)
        sec = self.play_frames // 60
        ci = self._jj_t(f["chip"], f"T+ {sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}", (255, 255, 255))
        surf.blit(ci, (bx + bw - 110, 45))
        if self.boss is not None:                                          # 魔王血條
            r = max(0.0, self.boss.hp / self.boss.max_hp)
            bw2 = 520
            bx2 = W // 2 - bw2 // 2
            self._jj_bar(surf, bx2, 78, bw2, 18, r, (255, 40, 40), (255, 170, 50), sk=8)
            nm = self._jj_t(f["boss"], getattr(self.boss, "name", "MOTHERSHIP"), (255, 255, 255), ow=3)
            surf.blit(nm, (bx2 - 4, 100))
            pc = self._jj_t(f["hits"], f"{int(r * 100)}%", (255, 228, 40))
            surf.blit(pc, (bx2 + bw2 - pc.get_width(), 102))
            if getattr(self.boss, "phase2", False):
                ph = pygame.transform.rotozoom(self._jj_t(f["hits"], "PHASE 2!!", (255, 80, 60), ow=3), 6, 1.0)
                surf.blit(ph, ph.get_rect(midleft=(bx2 + nm.get_width() + 10, 114)))
        # 右上：分數
        px = W - 300
        dy = 14                                                            # 整塊往下移：標籤不再貼著畫面上緣
        surf.blit(self._jj_panel(262, 62, 16, (235, 60, 140)), (px, 8 + dy))
        tag = self._jj_panel(60, 16, 6, (255, 228, 40), tone=False)
        surf.blit(tag, (px + 8, dy))
        lab = self._jj_t(f["chip"], "SCORE", (8, 4, 12), ow=0)
        surf.blit(lab, lab.get_rect(center=(px + 8 + 8 + 33, dy + 8 + 8)))  # 對齊黃色標籤的中心
        key = ("score", self.score)
        si = self._jj_cache.get(key)
        if si is None:
            stops = ((0.0, (255, 255, 255)), (0.48, (255, 250, 200)), (0.52, (255, 170, 40)), (1.0, (255, 230, 120)))
            si = self._chrome_text(f["score"], f"{self.score:,}", stops, outline=3, depth=3, depth_col=(90, 0, 50))
            self._jj_cache[key] = si
        surf.blit(si, si.get_rect(midright=(px + 266, 44 + dy)))
        rec = max(self.high_score, self.score)
        ri = self._jj_t(f["chip"], f"RECORD {rec:,}", (255, 255, 255))
        surf.blit(ri, ri.get_rect(topright=(px + 270, 80 + dy)))
        if self.combo > 1:                                                 # 連擊：黃色爆炸放射 + 倍數
            mult = min(5, 1 + self.combo // 4)
            fade = min(1.0, self.combo_timer / 30)
            bcx, bcy = W - 70, 128 + dy
            burst = self._jj_burst(bcx, bcy, 30 + 4 * math.sin(t * 8), t)
            pygame.draw.polygon(surf, (255, 214, 40), burst)
            pygame.draw.polygon(surf, (8, 4, 12), burst, 3)
            mi = pygame.transform.rotozoom(self._jj_t(f["combo"], f"x{mult}", (255, 255, 255), ow=3), -6, 1.0)
            surf.blit(mi, mi.get_rect(center=(bcx, bcy)))
            hi = pygame.transform.rotozoom(self._jj_t(f["hits"], f"{self.combo} HITS!!", (255, 80, 160), ow=3), 6, 1.0)
            hi.set_alpha(int(255 * (0.4 + 0.6 * fade)))
            surf.blit(hi, hi.get_rect(midright=(bcx - 44, bcy + 4)))

    def draw_gauge(self, surf, cx, cy, r, frac, value, label, unit):
        f = self._tel_fonts()
        self._aa_arc(surf, cx, cy, r, 0.0, 1.0, (80, 86, 98), 1)                 # 底軌：細灰線
        for k in range(11):                                                        # 刻度
            a = math.radians(225 - 27 * k)
            r0, r1 = (r - 9, r - 5) if k % 5 else (r - 11, r - 5)
            pygame.draw.aaline(surf, (120, 126, 140), (cx + r0 * math.cos(a), cy - r0 * math.sin(a)),
                               (cx + r1 * math.cos(a), cy - r1 * math.sin(a)))
        frac = max(0.0, min(1.0, frac))
        self._aa_arc(surf, cx, cy, r, 0.0, frac, (255, 255, 255), 3)              # 數值弧：白色
        if frac > 0.003:
            ex, ey = self._arc_pts(cx, cy, r, frac, frac, 1)[0]
            self._aa_dot(surf, ex, ey, 4, (255, 255, 255))
        vf = f["val"] if f["val"].size(value)[0] < 2 * r - 22 else f["valsm"]
        vi = vf.render(value, True, (255, 255, 255))
        surf.blit(vi, vi.get_rect(center=(cx, cy - 4)))
        if unit:
            ui = self.spaced(f["unit"], unit, (170, 176, 190), 2)
            surf.blit(ui, ui.get_rect(midtop=(cx, cy + 13)))
        li = self.spaced(f["lab"], label, (225, 228, 235), 4)
        surf.blit(li, li.get_rect(midtop=(cx, cy + r + 2)))

    def draw_scoreboard(self, surf):
        W, Hh = 310, 172
        x0, y0 = SCREEN_W - W - 12, 10
        p = pygame.Surface((W, Hh), pygame.SRCALPHA)
        bg = (0, 0, 0, 165)
        pygame.draw.rect(p, bg, (0, 0, W, Hh), border_radius=22)
        # L 形框架：頂部橫條 + 左側直條 + 圓角轉角（內側用底色挖出內圓角）
        pygame.draw.rect(p, self.LC_ORANGE, (0, 0, 92, 54), border_top_left_radius=30)
        pygame.draw.rect(p, bg, (24, 22, 80, 40), border_top_left_radius=14)
        pygame.draw.rect(p, self.LC_ORANGE, (96, 0, W - 96, 22), border_top_right_radius=11,
                         border_bottom_right_radius=11)
        pygame.draw.rect(p, self.LC_PEACH, (0, 58, 24, 46))
        pygame.draw.rect(p, self.LC_LAV, (0, 108, 24, 34))
        pygame.draw.rect(p, self.LC_ORANGE, (0, 146, 24, Hh - 146), border_bottom_left_radius=12,
                         border_bottom_right_radius=12)
        tag = self.font_hud_s.render(f"TACTICAL  {4700 + self.wave * 13:04d}", True, (0, 0, 0))
        p.blit(tag, (W - tag.get_width() - 14, 1))
        combo = f"{self.combo}  X{min(5, 1 + self.combo // 4)}" if self.combo > 1 else "--"
        rows = (("SCORE", f"{self.score}", self.LC_ORANGE),
                ("STAGE", f"{self.wave} / {FINAL_BOSS_WAVE}", self.LC_LAV),
                ("RECORD", f"{max(self.high_score, self.score)}", self.LC_BLUE),
                ("COMBO", combo, self.LC_PEACH if self.combo > 1 else (120, 110, 130)))
        for i, (lab, val, col) in enumerate(rows):
            y = 30 + i * 30
            pygame.draw.rect(p, col, (34, y, 84, 24), border_radius=12)               # 膠囊標籤
            li = self.font_hud_s.render(lab, True, (0, 0, 0))
            p.blit(li, (34 + 84 - li.get_width() - 12, y + 2))
            vi = self.font_hud.render(val, True, col)
            p.blit(vi, (W - vi.get_width() - 14, y - 4))
        # 分段式進度條：魔王關改為紅色 BOSS 警示
        y = Hh - 22
        if self.is_boss_wave():
            on = (pygame.time.get_ticks() // 400) % 2 == 0
            pygame.draw.rect(p, self.LC_RED if on else (120, 40, 40), (34, y, W - 48, 14), border_radius=7)
            bi = self.font_hud_s.render("BOSS  ENGAGED", True, (0, 0, 0))
            p.blit(bi, (34 + (W - 48 - bi.get_width()) // 2, y - 3))
        else:
            segs = 12
            prog = 1.0 if self.miniboss_stage else min(1.0, self.kills / max(1, self.kills_needed))
            sw = (W - 48 - (segs - 1) * 4) / segs
            for k in range(segs):
                lit = k < round(prog * segs)
                col = (self.LC_ORANGE if k < segs * 0.6 else self.LC_PEACH) if lit else (50, 45, 60)
                pygame.draw.rect(p, col, (34 + k * (sw + 4), y, sw, 14), border_radius=5)
        surf.blit(p, (x0, y0))

    # ---------- 勝利畫面 ----------
    def _build_win_title(self):
        """YOU WIN：80 年代科幻電影的鉻金屬漸層 + 深色描邊 + 紫色光暈（只建一次，之後重複使用）。"""
        f = self.font_win
        mask = f.render("YOU WIN", True, (255, 255, 255))
        w, h = mask.get_size()
        pad = 40
        grad = pygame.Surface((w, h), pygame.SRCALPHA)
        stops = ((0.0, (190, 230, 255)), (0.47, (255, 255, 255)), (0.5, (60, 30, 120)),
                 (0.75, (150, 80, 230)), (1.0, (235, 190, 255)))
        for y in range(h):
            t = y / max(1, h - 1)
            for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
                if p0 <= t <= p1:
                    k = (t - p0) / max(1e-6, p1 - p0)
                    col = tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3))
                    break
            pygame.draw.line(grad, col + (255,), (0, y), (w, y))
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)     # 漸層只留在字形裡
        title = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        dark = f.render("YOU WIN", True, (18, 8, 40))
        for dx, dy in ((-4, 0), (4, 0), (0, -4), (0, 4), (-3, -3), (3, 3), (-3, 3), (3, -3), (5, 6)):
            title.blit(dark, (pad + dx, pad + dy))                      # 描邊與厚度
        title.blit(grad, (pad, pad))
        glow = pygame.Surface(title.get_size(), pygame.SRCALPHA)
        glow.blit(f.render("YOU WIN", True, (170, 90, 255)), (pad, pad))
        sw, sh = glow.get_size()
        for _ in range(2):                              # 縮小再放大 = 模糊，兩次讓光暈更柔和、更寬
            glow = pygame.transform.smoothscale(pygame.transform.smoothscale(glow, (sw // 8, sh // 8)), (sw, sh))
        self._win_cache = (title, glow, mask, pad)

    def draw_win(self, c):
        self.win_t = getattr(self, "win_t", 0) + 1
        t = self.win_t
        if self._win_cache is None:
            self._build_win_title()
        title, glow, mask, pad = self._win_cache
        # 電影感的暗色橫帶
        band = pygame.Surface((SCREEN_W, 420), pygame.SRCALPHA)
        for y in range(420):
            a = int(200 * math.sin(math.pi * y / 420) ** 0.6)
            pygame.draw.line(band, (6, 4, 18, a), (0, y), (SCREEN_W, y))
        c.blit(band, (0, int(CY) - 250))
        # 登場：彈跳放大（ease-out-back）
        k = min(1.0, t / 28)
        s = 1 + 2.2 * (k - 1) ** 3 + 1.2 * (k - 1) ** 2 if k < 1 else 1.0
        s = max(0.2, s)
        cx, cy = SCREEN_W // 2, int(CY) - 95
        gl = glow.copy()
        pulse = 0.75 + 0.25 * math.sin(t * 0.08)
        gl.set_alpha(int(255 * pulse))
        for img in (gl, title):                       # 光暈用一般透明混合：加亮混合會無視透明度、整塊矩形發亮
            im = img if s == 1.0 else pygame.transform.smoothscale(
                img, (max(1, int(img.get_width() * s)), max(1, int(img.get_height() * s))))
            c.blit(im, im.get_rect(center=(cx, cy)))
        # 光澤掃過：每 3 秒一次，斜向的亮帶只出現在字形上
        ph = (t % 180) / 60.0
        if s == 1.0 and ph < 1.0:
            mw, mh = mask.get_size()
            shine = pygame.Surface((mw, mh), pygame.SRCALPHA)
            x0 = int(-mh + (mw + mh * 2) * ph)
            pygame.draw.polygon(shine, (255, 255, 255, 170),
                                ((x0, 0), (x0 + 50, 0), (x0 + 50 - mh, mh), (x0 - mh, mh)))
            shine.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            c.blit(shine, (cx - title.get_width() // 2 + pad, cy - title.get_height() // 2 + pad),
                   special_flags=pygame.BLEND_RGB_ADD)
        # 副標、分數、操作提示（文字依序淡入）
        lines = (("MEGALON HAS BEEN BANISHED TO THE VOID", self.font_win_s, (215, 200, 255), 70, 30),
                 (f"SCORE  {self.score}", self.font_win_m, (255, 215, 90), 120, 45),
                 ("PRESS  R  TO PLAY AGAIN      ESC  TO QUIT", self.font_win_s, (170, 175, 195), 180, 60))
        for text, font, col, dy, start in lines:
            a = max(0, min(255, (t - start) * 12))
            if a <= 0:
                continue
            img = font.render(text, True, col)
            shd = font.render(text, True, (8, 6, 20))
            img.set_alpha(a)
            shd.set_alpha(a)
            r = img.get_rect(center=(cx, int(CY) + dy - 40))
            c.blit(shd, r.move(2, 3))
            c.blit(img, r)

    # ---------- 最終魔王 ----------
    def start_boss_rush(self):
        """直接挑戰虛淵：給一套完整的武器，跳到最終關。"""
        self.state = self.STATE_PLAY
        self.reset()
        self.wave = FINAL_BOSS_WAVE
        for wid in DROPPABLE_WEAPONS:
            self.ship.arsenal[wid] = {"level": 2, "ammo": WEAPONS[wid]["ammo"] * 2}
        self.bombs = 3
        self.switch_popup = ("FINAL BOSS: MEGALON", "Aim for the void eye - double damage", (255, 120, 70), 200)
        self.play_music()

    def kaiju_dying(self, b):
        """虛淵崩毀：全身連環爆炸、骨片四散、沉入冰原，最後進入勝利畫面。"""
        b.update(self.ship, self.enemy_bullets, self)
        b.death_timer -= 1
        g = b.ground()
        self.shake = max(self.shake, 8)
        if b.death_timer % 6 == 0:
            self.boom((b.x + random.uniform(-380, 380), g - random.uniform(80, 950), b.z + random.uniform(-150, 150)),
                      big=random.random() < 0.3)
        if b.death_timer % 2 == 0:
            self.particles.emit(b.x + random.uniform(-300, 300), g - random.uniform(300, 1000), b.z,
                                random.uniform(-10, 10), random.uniform(2, 12), random.uniform(-8, 8),
                                random.randint(26, 44), random.choice([(70, 40, 35), (255, 110, 40)]), 11.0)
        if b.death_timer <= 0:
            for _ in range(5):
                self.boom((b.x + random.uniform(-300, 300), g - random.uniform(100, 800), b.z), big=True)
            self.flash = 230
            self.freeze = 8
            self.add_score(b.score, b.pos())
            self.boss = None
            self.state = self.STATE_WIN
            self.win_t = 0
            self.play_victory_music()


    # ---------- 切換武器 ----------
    def show_switch(self, wid):
        spec = WEAPONS[wid]
        lv = self.ship.arsenal[wid]["level"]
        self.switch_popup = (f"{spec['label']}  Lv{lv}", spec["desc"], spec["color"], 70)
        self.slot_pulse = 12
        if self.sfx.get("switch"):
            self.sfx["switch"].play()

    def try_select(self, wid):
        s = self.ship
        if wid == s.weapon:
            return
        if wid in s.arsenal:
            s.select(wid)
            self.cancel_charge()
            self.show_switch(wid)
        else:
            self.switch_popup = (f"{WEAPONS[wid]['label']}  LOCKED", "Collect hexagon weapon packs to unlock",
                                 (150, 156, 170), 60)
            if self.sfx.get("locked"):
                self.sfx["locked"].play()

    def cycle_weapon(self, step):
        s = self.ship
        if len(s.owned()) <= 1:
            self.switch_popup = ("PULSE ONLY", "Collect hexagon weapon packs to unlock more",
                                 (150, 156, 170), 60)
            return
        s.switch(step)
        self.cancel_charge()
        self.show_switch(s.weapon)

    def fire_watchdog(self, fire):
        """
        最後一道防線：按住射擊超過 2 秒卻什麼都沒射出去（也不是在蓄力、不是光束發射中），
        就自動把武器重設回主砲，並把當下狀態寫進 fire_debug.txt。
        如果這種情況真的發生，那個檔案能直接告訴我原因。
        """
        if not fire or self.charge > 0 or self.beam is not None:
            self.fire_stuck = 0
            return
        if self.frame_no - self.last_fire <= 1:
            self.fire_stuck = 0
            return
        self.fire_stuck += 1
        if self.fire_stuck < 120:
            return
        s = self.ship
        state = (f"wave={self.wave} weapon={s.weapon} cooldown={s.cooldown} freeze={self.freeze} "
                 f"atomic_cd={self.atomic_cd} charge={self.charge} beam={self.beam is not None} "
                 f"arsenal={ {w: (v['level'], v['ammo']) for w, v in s.arsenal.items()} }")
        print("[射擊偵測] 按住射擊 2 秒沒有反應，已自動重設武器：" + state)
        try:
            with open(os.path.join(ASSET_DIR, "fire_debug.txt"), "a", encoding="utf-8") as f:
                f.write(state + "\n")
        except OSError:
            pass
        s.weapon = "PULSE"
        s.cooldown = 0
        self.cancel_charge()
        self.switch_popup = ("WEAPON RESET", "Switched back to PULSE", (255, 210, 120), 70)
        self.fire_stuck = 0

    # ---------- 原子光束 ----------
    def cancel_charge(self):
        self.charge = 0
        if self.charge_snd is not None:
            self.charge_snd.stop()
            self.charge_snd = None

    def update_atomic(self, fire):
        if self.beam is not None or self.atomic_cd > 0 or "ATOMIC" not in self.ship.arsenal:
            return
        if fire:
            if self.charge == 0 and self.sfx.get("charge"):
                self.charge_snd = self.sfx["charge"].play()
            self.charge += 1
            # 能量從四面八方吸進機首：在機首周圍的球面上生成粒子，速度指向機首
            nx, ny, nz = self.ship.transform((0, -3, 80))
            for _ in range(1 + self.charge // 20):
                a = random.uniform(0, math.tau)
                b = random.uniform(-1, 1)
                r = random.uniform(110, 230)
                q = math.sqrt(1 - b * b)
                px, py, pz = nx + math.cos(a) * q * r, ny + math.sin(a) * q * r, nz + b * r
                v = 15.0
                self.particles.emit(px, py, pz, (nx - px) / r * v, (ny - py) / r * v,
                                    (nz - pz) / r * v + self.world_speed * 0.35,
                                    int(r / v), (110, 195, 255), 6.0)
            if self.charge >= AtomicBeam.CHARGE_MAX:
                self.fire_atomic()
        elif self.charge > 0:
            if self.charge >= AtomicBeam.CHARGE_MIN:
                self.fire_atomic()
            else:
                self.cancel_charge()

    def fire_atomic(self):
        s = self.ship
        level = s.arsenal["ATOMIC"]["level"]
        ratio = min(1.0, self.charge / AtomicBeam.CHARGE_MAX)
        self.cancel_charge()
        if not s.consume():
            return
        dmg = WEAPONS["ATOMIC"]["dmg_lv"][level - 1]
        self.novas.append(NovaOrb3D(s.x, s.y - 20, s.z, level, ratio, dmg))   # 原子吐息：巨型能量彈
        self.atomic_cd = 120 + WEAPONS["ATOMIC"]["cd_lv"][level - 1]
        self.flash = max(self.flash, 60)
        self.shake = max(self.shake, 12)
        label = "MAX ATOMIC BREATH!" if ratio >= 0.99 else "ATOMIC BREATH!"
        self.texts.append(FloatText3D((CX, CY + 150), label, (190, 150, 255), self.font_l, life=55))
        snd = self.sfx.get("nova") or self.snd_explode
        if snd:
            snd.play()

    def update_novas(self):
        """原子吐息：穿透一切；小兵每隻重擊一次、抹除敵彈；撞上魔王就卡住研磨，約 1 秒後引爆。"""
        for n in self.novas:
            n.update(self.particles)
            for e in self.enemies:
                if e.alive and id(e) not in n.hit_ids and self.hit3d(n.pos(), n.radius, e.pos(), e.radius):
                    n.hit_ids.add(id(e))
                    self.particles.burst(e.pos(), 12, (200, 120, 255), speed=12)
                    if e.take_damage(n.dmg * 6):
                        e.alive = False
                        self.on_kill(e)
            for eb in self.enemy_bullets:
                if getattr(eb, "alive", True) and self.hit3d(n.pos(), n.radius, (eb.x, eb.y, eb.z), 20):
                    eb.alive = False
            b = self.boss
            if b is not None and not b.dying and not getattr(b, "entering", False) and \
                    self.hit3d(n.pos(), n.radius, b.pos(), b.radius):
                n.grind += 1
                if n.grind % 4 == 0:
                    b.take_damage(n.dmg * 3, at=n.pos())
                    self.particles.burst(n.pos(), 10, (220, 140, 255), speed=14)
                self.shake = max(self.shake, 7)
                if n.grind > 60:
                    n.detonate = True
            if n.detonate or n.z > SPAWN_Z + 200:
                self.nova_blast(n)
        self.novas = [n for n in self.novas if n.alive]

    def nova_blast(self, n):
        """能量彈引爆：大爆炸 + 範圍傷害。"""
        n.alive = False
        for _ in range(5):
            self.boom((n.x + random.uniform(-160, 160), n.y + random.uniform(-160, 160), n.z), big=True)
        self.flash = max(self.flash, 120)
        self.shake = max(self.shake, 16)
        R = 450 * n.scale
        for e in self.enemies:
            if e.alive and self.hit3d(n.pos(), R, e.pos(), e.radius):
                if e.take_damage(n.dmg * 8):
                    e.alive = False
                    self.on_kill(e)
        b = self.boss
        if b is not None and not b.dying and not getattr(b, "entering", False) and self.hit3d(n.pos(), R, b.pos(), b.radius):
            b.take_damage(n.dmg * 10, at=n.pos())
        if self.sfx.get("nova_boom"):
            self.sfx["nova_boom"].play()

    def draw_charge(self, surf):
        """蓄力中：機首光球逐漸變大，外圈是蓄力進度環。冷卻中：顯示充能進度。"""
        if self.state != self.STATE_PLAY:
            return
        if self.charge <= 0:
            if self.ship.weapon == "ATOMIC" and (self.beam is not None or self.atomic_cd > 0):
                p = project(*self.ship.transform((0, -3, 80)))
                if p and self.beam is None:
                    full = max(1, WEAPONS["ATOMIC"]["cd_lv"][0] + 120)
                    k = 1 - min(1.0, self.atomic_cd / full)
                    cx, cy, r = int(p[0]), int(p[1]), 40
                    pygame.draw.arc(surf, (40, 60, 90), (cx - r, cy - r, 2 * r, 2 * r), 0, math.tau, 3)
                    pygame.draw.arc(surf, (150, 160, 180), (cx - r, cy - r, 2 * r, 2 * r),
                                    math.pi / 2 - math.tau * k, math.pi / 2, 4)
                    img = self.font_xs.render("RECHARGING - firing PULSE", True, (200, 210, 230))
                    surf.blit(img, (cx - img.get_width() // 2, cy - r - 20))
            return
        p = project(*self.ship.transform((0, -3, 80)))
        if not p:
            return
        cx, cy = int(p[0]), int(p[1])
        k = min(1.0, self.charge / AtomicBeam.CHARGE_MAX)
        ready = self.charge >= AtomicBeam.CHARGE_MIN
        blit_glow(surf, (cx, cy), int(14 + 70 * k), (90, 170, 255))
        pygame.draw.circle(surf, (230, 248, 255), (cx, cy), int(4 + 12 * k))
        r = 52
        col = (255, 255, 255) if ready else (110, 190, 255)
        pygame.draw.arc(surf, (30, 50, 90), (cx - r, cy - r, 2 * r, 2 * r), 0, math.tau, 3)
        pygame.draw.arc(surf, col, (cx - r, cy - r, 2 * r, 2 * r),
                        math.pi / 2 - math.tau * k, math.pi / 2, 5)
        msg = "RELEASE!" if ready else "CHARGING"
        img = self.font_s.render(msg, True, col)
        sh = self.font_s.render(msg, True, (10, 14, 30))
        surf.blit(sh, (cx - img.get_width() // 2 + 2, cy - r - 24 + 2))
        surf.blit(img, (cx - img.get_width() // 2, cy - r - 24))

    # ---------- 武器欄：JoJo 風格（傾斜卡片、粗黑描邊、網點、爆炸放射） ----------
    def _jj_fonts(self):
        if getattr(self, "_jjf", None):
            return self._jjf
        d = find_asset("DelaGothicOne-Regular.ttf")
        mk = lambda size: pygame.font.Font(d, size) if d else pygame.font.Font(None, int(size * 1.5))
        self._jjf = dict(num=mk(24), name=mk(13), pop=mk(46), popd=mk(15), hint=mk(12), go=mk(34),
                         score=mk(34), pct=mk(20), lab=mk(12), chip=mk(11), combo=mk(30), hits=mk(16),
                         boss=mk(22), warn=mk(44))
        self._jj_cache = {}
        return self._jjf

    @staticmethod
    def _jj_text(font, text, fill, outline=(8, 4, 12), ow=3):
        """白字（或彩字）加粗黑描邊：漫畫字的基本款。"""
        core = font.render(text, True, fill)
        edge = font.render(text, True, outline)
        out = pygame.Surface((core.get_width() + ow * 2, core.get_height() + ow * 2), pygame.SRCALPHA)
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx * dx + dy * dy <= ow * ow + 1:
                    out.blit(edge, (ow + dx, ow + dy))
        out.blit(core, (ow, ow))
        return out

    @staticmethod
    def _star(surf, cx, cy, r, fill):
        pts = []
        for k in range(10):
            rr = r if k % 2 == 0 else r * 0.45
            a = -math.pi / 2 + k * math.pi / 5
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        pygame.draw.polygon(surf, fill, pts)
        pygame.draw.polygon(surf, (8, 4, 12), pts, 2)

    def _jj_card(self, i, wid, owned, cur, level, frac, label):
        """一張武器卡（快取）：傾斜平行四邊形、黑色投影、上亮下暗、網點、粗黑描邊、編號、名稱、星星、彈藥條。"""
        key = (wid, owned, cur, level, round(frac * 20), label)
        img = self._jj_cache.get(key)
        if img is not None:
            return img
        f = self._jj_fonts()
        w, h, sk, pad = 106, 62, 16, 10
        img = pygame.Surface((w + sk + pad * 2 + 6, h + pad * 2 + 6), pygame.SRCALPHA)
        P = lambda dx=0, dy=0: [(pad + sk + dx, pad + dy), (pad + sk + w + dx, pad + dy),
                                (pad + w + dx, pad + h + dy), (pad + dx, pad + h + dy)]
        base = WEAPONS[wid]["color"] if owned else (78, 78, 92)
        if owned:                                                      # 顏色加飽和、加亮：漫畫的鮮豔感
            m = max(base)
            base = tuple(min(255, int(c * 255 / max(m, 1) * (0.55 + 0.45 * c / max(m, 1)) + 20)) for c in base)
        dark = tuple(int(c * 0.6) for c in base)
        pygame.draw.polygon(img, (8, 4, 12), P(5, 5))                  # 偏移的黑色投影
        pygame.draw.polygon(img, dark, P())
        top = [(pad + sk, pad), (pad + sk + w, pad), (pad + sk * 0.5 + w, pad + h * 0.5), (pad + sk * 0.5, pad + h * 0.5)]
        pygame.draw.polygon(img, base, top)                            # 上半部亮色
        tone = pygame.Surface(img.get_size(), pygame.SRCALPHA)         # 網點 / 未解鎖的斜線網紋
        if owned:
            for yy in range(0, img.get_height(), 7):
                for xx in range((yy // 7) % 2 * 3, img.get_width(), 7):
                    pygame.draw.circle(tone, (0, 0, 0, 45), (xx, yy), 1)
        else:
            for xx in range(-img.get_height(), img.get_width(), 9):
                pygame.draw.line(tone, (0, 0, 0, 70), (xx, img.get_height()), (xx + img.get_height(), 0), 2)
        mask = pygame.Surface(img.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255), P())
        tone.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        img.blit(tone, (0, 0))
        pygame.draw.polygon(img, (8, 4, 12), P(), 3)                   # 粗黑描邊
        num = self._jj_text(f["num"], str(i + 1), (255, 228, 40) if owned else (150, 150, 160), ow=3)
        img.blit(num, (pad + sk - 2, pad - 12))
        nm = self._jj_text(f["name"], label, (255, 255, 255) if owned else (165, 165, 178), ow=2)
        img.blit(nm, (pad + 10, pad + h - nm.get_height() - 9))
        if owned:
            for k in range(3):                                         # 等級星星
                self._star(img, pad + sk + w - 12 - k * 15, pad + 13, 6,
                           (255, 228, 40) if k < level else (60, 60, 70))
            bx, by, bw = pad + 8, pad + h - 7, w - 6                   # 彈藥條
            pygame.draw.rect(img, (8, 4, 12), (bx - 1, by - 1, bw + 2, 6))
            pygame.draw.rect(img, (255, 255, 255), (bx, by, int(bw * frac), 4))
        if len(self._jj_cache) > 200:
            self._jj_cache.clear()
        self._jj_cache[key] = img
        return img

    def _jj_panel(self, w, h, sk, col, tone=True):
        """傾斜面板（快取）：黑色投影、上亮下暗、網點、粗黑描邊。"""
        key = ("panel", w, h, sk, col, tone)
        img = self._jj_cache.get(key) if hasattr(self, "_jj_cache") else None
        if img is not None:
            return img
        self._jj_fonts()
        pad = 8
        img = pygame.Surface((w + sk + pad * 2 + 6, h + pad * 2 + 6), pygame.SRCALPHA)
        P = lambda dx=0, dy=0: [(pad + sk + dx, pad + dy), (pad + sk + w + dx, pad + dy),
                                (pad + w + dx, pad + h + dy), (pad + dx, pad + h + dy)]
        pygame.draw.polygon(img, (8, 4, 12), P(5, 5))
        pygame.draw.polygon(img, tuple(int(c * 0.62) for c in col), P())
        pygame.draw.polygon(img, col, [(pad + sk, pad), (pad + sk + w, pad), (pad + sk * 0.55 + w, pad + h * 0.45),
                                       (pad + sk * 0.55, pad + h * 0.45)])
        if tone:
            t = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            for yy in range(0, img.get_height(), 7):
                for xx in range((yy // 7) % 2 * 3, img.get_width(), 7):
                    pygame.draw.circle(t, (0, 0, 0, 45), (xx, yy), 1)
            m = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            pygame.draw.polygon(m, (255, 255, 255, 255), P())
            t.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            img.blit(t, (0, 0))
        pygame.draw.polygon(img, (8, 4, 12), P(), 3)
        self._jj_cache[key] = img
        return img

    def _jj_t(self, font, text, fill, ow=2):
        """白字黑邊（快取）。"""
        key = ("t", id(font), text, fill, ow)
        img = self._jj_cache.get(key)
        if img is None:
            img = self._jj_text(font, text, fill, ow=ow)
            if len(self._jj_cache) > 400:
                self._jj_cache.clear()
            self._jj_cache[key] = img
        return img

    @staticmethod
    def _jj_bar(surf, x, y, w, h, frac, c0, c1, sk=6):
        """粗黑框的斜條：黑色投影 + 由 c0 漸變到 c1 的填色 + 粗黑描邊。"""
        P = lambda x0, x1, dy=0: [(x0 + sk, y + dy), (x1 + sk, y + dy), (x1, y + h + dy), (x0, y + h + dy)]
        pygame.draw.polygon(surf, (8, 4, 12), [(px + 3, py + 3) for px, py in P(x, x + w)])
        pygame.draw.polygon(surf, (40, 30, 50), P(x, x + w))
        fw = int(w * max(0.0, min(1.0, frac)))
        if fw > 0:
            steps = max(1, fw // 6)
            for k in range(steps):
                a0, a1 = x + fw * k / steps, x + fw * (k + 1) / steps
                tt = (k + 0.5) / steps
                col = tuple(int(c0[i] + (c1[i] - c0[i]) * tt) for i in range(3))
                pygame.draw.polygon(surf, col, P(a0, a1 + 0.8))
            pygame.draw.line(surf, (255, 255, 255), (x + sk + 2, y + 3), (x + fw + sk - 2, y + 3), 2)
        pygame.draw.polygon(surf, (8, 4, 12), P(x, x + w), 3)

    def _jj_burst(self, cx, cy, r, t):
        """選中武器背後的爆炸放射圖形（黃色鋸齒 + 黑邊），會慢慢旋轉。"""
        pts = []
        n = 16
        for k in range(n * 2):
            rr = r if k % 2 == 0 else r * 0.62
            a = t * 0.8 + k * math.pi / n
            pts.append((cx + rr * math.cos(a) * 1.35, cy + rr * math.sin(a) * 0.8))
        return pts

    def draw_weapon_bar(self, surf):
        f = self._jj_fonts()
        s = self.ship
        W, H = SCREEN_W, SCREEN_H
        if not hasattr(self, "_jj_grad"):                                          # 淡淡的下緣漸層（卡片有黑邊，不需要太深）
            g = pygame.Surface((W, 150), pygame.SRCALPHA)
            for y in range(150):
                pygame.draw.line(g, (20, 0, 30, int(120 * (y / 150) ** 1.6)), (0, y), (W, y))
            self._jj_grad = g
        surf.blit(self._jj_grad, (0, H - 150))
        t = pygame.time.get_ticks() / 1000.0
        n = len(WEAPON_ORDER)
        step = 124                                                                 # 間距拉開：選中的卡片放大後不會蓋住隔壁的名稱
        x0 = W // 2 - step * n // 2 + step // 2
        cy = H - 58
        cur_draw = None
        for i, wid in enumerate(WEAPON_ORDER):
            owned = wid in s.arsenal
            cur = wid == s.weapon
            spec = WEAPONS[wid]
            label = spec["label"]
            level, frac = 0, 0.0
            if owned:
                slotd = s.arsenal[wid]
                level = slotd["level"]
                if wid == "ATOMIC":
                    label = f"ATOMIC x{slotd['ammo']}"
                    if self.beam is not None:
                        frac = 0.0
                    elif self.atomic_cd > 0:
                        frac = 1 - min(1.0, self.atomic_cd / (WEAPONS["ATOMIC"]["cd_lv"][0] + 120))
                    else:
                        frac = 1.0
                elif slotd["ammo"] is None or not spec["ammo"]:          # 無限彈藥
                    frac = 1.0
                else:
                    frac = max(0.0, min(1.0, slotd["ammo"] / (spec["ammo"] * 2)))
            card = self._jj_card(i, wid, owned, cur, level, frac, label)
            cx = x0 + i * step
            if cur:
                cur_draw = (cx, card)
            else:
                surf.blit(card, card.get_rect(center=(cx, cy)))
        if cur_draw:                                                               # 選中的卡片最後畫：放大、上浮、轉角度
            cx, card = cur_draw
            pop = 1.16 + 0.06 * (self.slot_pulse / 12)
            bob = math.sin(t * 4) * 2
            burst = self._jj_burst(cx, cy - 14 + bob, 66, t)                       # 放大：要從卡片邊緣露出來
            pygame.draw.polygon(surf, (255, 214, 40), burst)
            pygame.draw.polygon(surf, (8, 4, 12), burst, 3)
            big = pygame.transform.rotozoom(card, 4, pop)
            surf.blit(big, big.get_rect(center=(cx, cy - 14 + bob)))
            go = self._jj_text(f["go"], "ゴ", (180, 80, 240), ow=3) if self.font_go else None
            if go:
                g2 = pygame.transform.rotozoom(go, -8 + 6 * math.sin(t * 3), 1 + 0.08 * math.sin(t * 5))
                surf.blit(g2, g2.get_rect(center=(cx + 92, cy - 52)))
        hint = self._jj_text(f["hint"], "1-7  Q/E  WHEEL", (255, 255, 255), ow=2)
        surf.blit(hint, hint.get_rect(bottomright=(x0 + step * (n - 1) + 70, cy - 46)))
        if self.switch_popup:                                                      # 切換：傾斜的金屬漸層大字
            title, desc, col, tt = self.switch_popup
            key = ("pop", title)
            img = self._jj_cache.get(key)
            if img is None:
                c = tuple(min(255, int(v * 1.1) + 30) for v in col)
                stops = ((0.0, (255, 255, 255)), (0.48, c), (0.52, tuple(int(v * 0.55) for v in c)), (1.0, c))
                img = pygame.transform.rotozoom(self._chrome_text(f["pop"], title + "!!", stops, outline=5, depth=6,
                                                                  depth_col=(30, 0, 40)), 6, 1.0)
                self._jj_cache[key] = img
            a = min(255, int(255 * min(1.0, tt / 18)))
            k = min(1.0, (70 - tt) / 8) if tt > 62 else 1.0                       # 彈出時有個放大的瞬間
            im = pygame.transform.rotozoom(img, 0, 0.6 + 0.4 * k) if k < 1 else img.copy()
            im.set_alpha(a)
            surf.blit(im, im.get_rect(center=(W // 2, cy - 128)))
            di = self._jj_text(f["popd"], desc, (255, 255, 255), ow=2)
            di.set_alpha(a)
            surf.blit(di, di.get_rect(center=(W // 2 + 10, cy - 86)))
            self.switch_popup = (title, desc, col, tt - 1) if tt > 1 else None
        if self.slot_pulse > 0:
            self.slot_pulse -= 1

    def use_shockwave(self):
        """K 鍵大絕。有短冷卻，避免一瞬間把五次全按掉。"""
        if self.state != self.STATE_PLAY or self.shock_charges <= 0 or self.shock_cd > 0:
            return
        self.shock_charges -= 1
        self.shock_cd = 45
        s = self.ship
        self.shockwaves.append(ShockWave3D(s.x, s.y, s.z + 60))
        self.flash = 110
        self.shake = 13
        self.freeze = 3
        self.particles.burst((s.x, s.y, s.z + 40), 16, (150, 220, 255), speed=16, size=9)
        self.texts.append(FloatText3D((CX, CY + 150), "SHOCKWAVE", CYAN, self.font_l, life=55))
        if self.sfx.get("shock"):
            self.sfx["shock"].play()
        elif self.snd_explode:
            self.snd_explode.play()

    def update_shockwaves(self):
        """波前掃過的東西：敵人受重傷、敵彈直接蒸發、BOSS 也吃傷害。"""
        for w in self.shockwaves:
            w.update(self)
            for e in self.enemies:
                if e.alive and id(e) not in w.hit_ids and w.covers(e.pos(), e.radius):
                    w.hit_ids.add(id(e))
                    self.particles.burst(e.pos(), 5, (140, 255, 160), speed=10)
                    if e.take_damage(w.DAMAGE):
                        e.alive = False
                        self.on_kill(e)
            for b in self.enemy_bullets:
                if b.alive and w.covers(b.pos()):
                    b.alive = False
                    self.particles.burst(b.pos(), 2, (160, 255, 180), speed=5, size=5)
            b = self.boss
            if b and not b.dying and id(b) not in w.hit_ids and w.covers(b.pos(), b.radius):
                w.hit_ids.add(id(b))
                b.take_damage(w.DAMAGE + 6)
                self.boom(b.pos())
        self.shockwaves = [w for w in self.shockwaves if w.alive]
        if self.shock_cd > 0:
            self.shock_cd -= 1
        if self.bomb_cd > 0:
            self.bomb_cd -= 1
        if self.atomic_cd > 0:
            self.atomic_cd -= 1

    def use_bomb(self):
        """
        炸彈：立刻清除戰機周圍的敵彈（保留防禦功能），同時扇形射出 8 枚追蹤火箭，
        各自鎖定不同的敵人（沒有小兵時全部衝向魔王），命中時範圍爆炸。
        """
        if self.bombs <= 0 or self.state != self.STATE_PLAY or self.bomb_cd > 0:
            return
        s = self.ship
        self.bombs -= 1
        self.bomb_cd = 45
        self.flash = 70
        self.shake = 8
        for b in self.enemy_bullets:                                  # 防禦：身邊的敵彈立刻清除
            if (b.x - s.x) ** 2 + (b.y - s.y) ** 2 + (b.z - s.z) ** 2 < 560 ** 2:
                b.alive = False
                self.particles.burst(b.pos(), 2, (255, 210, 90), speed=6)
        targets = sorted([e for e in self.enemies if e.alive], key=lambda e: e.z)
        boss = self.boss if self.boss is not None and not self.boss.dying else None
        n = 8
        for k in range(n):
            lock = targets[k] if k < len(targets) else (boss or (targets[k % len(targets)] if targets else None))
            a = math.pi * (0.15 + 0.7 * k / (n - 1))                  # 扇形放射：從左上到右上散開
            vx, vy = -math.cos(a) * 20, -math.sin(a) * 16 - 4
            self.missiles.append(BombRocket3D(s.x + vx * 1.5, s.y + 10, s.z + 30, vx, vy, 22.0, lock))
        snd = self.sfx.get("w_HOMING") or self.snd_explode
        if snd:
            snd.play()
        self.texts.append(FloatText3D((CX, CY + 120), "ROCKET BOMB!", (255, 210, 60), self.font_m))

    def rocket_blast(self, m):
        """火箭爆炸：範圍內的敵人受傷、敵彈清除，魔王也會被炸到。"""
        if m.blasted:
            return
        m.blasted = True
        R = m.BLAST
        self.boom(m.pos(), big=True)
        self.shake = max(self.shake, 7)
        for e in self.enemies:
            if e.alive and self.hit3d(m.pos(), R, e.pos(), e.radius):
                if e.take_damage(6):
                    e.alive = False
                    self.on_kill(e)
        for b in self.enemy_bullets:
            if b.alive and self.hit3d(m.pos(), R, b.pos(), 10):
                b.alive = False
        bs = self.boss
        if bs is not None and not bs.dying and not getattr(bs, "entering", False) and \
                self.hit3d(m.pos(), R, bs.pos(), bs.radius):
            bs.take_damage(6, at=m.pos())

    def shoot(self, override=None):
        """
        依目前裝備的武器分派。每把武器有自己的冷卻、彈藥與彈道。
        override="PULSE"：原子光束冷卻中時改用主砲射擊（主砲無限彈藥，不扣任何彈藥）。
        """
        s = self.ship
        if s.cooldown > 0:
            return
        wid = override or s.weapon
        if wid == "ATOMIC":
            return                          # 原子光束走蓄力流程，不在這裡發射
        spec = WEAPONS[wid]
        level = s.arsenal[wid]["level"]
        ports = s.gun_ports()
        mid = tuple((ports[0][i] + ports[1][i]) / 2 for i in range(3))

        if wid == "LASER":
            self.fire_laser(level)
            return

        if override is None and not s.consume():
            return
        s.cooldown = spec["cd_lv"][level - 1]
        self.last_fire = self.frame_no                  # 給「無法射擊偵測」用
        count = spec["n_lv"][level - 1]
        dmg = spec["dmg_lv"][level - 1]

        if wid == "PULSE":
            muzzles = [mid] if count == 1 else (ports if count == 2 else [ports[0], mid, ports[1]])
            for mx, my, mz in muzzles:
                # 稍微向中心收斂，讓遠處彈道會合，比較好命中
                self.bullets.append(Bullet3D(mx, my, mz,
                                             (s.x - mx) * 0.035, (s.y - my) * 0.035, dmg=dmg))

        elif wid == "SPREAD":
            # 散射要真的夠廣：橫向速度決定在目標距離處能張開多寬
            spread = 17.0
            for i in range(count):
                t = (i - (count - 1) / 2) / max(1, (count - 1) / 2)
                self.bullets.append(Bullet3D(mid[0], mid[1], mid[2],
                                             t * spread, -abs(t) * 3.0 + 1.5, 38.0, dmg=dmg))

        elif wid == "HOMING":
            for i in range(count):
                side = -1 if i % 2 == 0 else 1
                self.missiles.append(Missile3D(s.x + side * 30, s.y, s.z + 20, side, dmg=dmg))

        elif wid == "PLASMA":
            self.plasmas.append(Plasma3D(mid[0], mid[1], mid[2], level, dmg))

        elif wid == "COMET":                                   # 藍焰彗星：2~3 枚緊密交纏成螺旋
            n = spec["n_lv"][level - 1]
            for k in range(n):
                self.missiles.append(CometShot3D(mid[0], mid[1], mid[2], k, n, dmg, level))
            self.shake = max(self.shake, 3)

        elif wid == "FIRE":                                    # 6 枚火焰彈，平均分佈在圓上、螺旋前進
            n = spec["n_lv"][level - 1]
            for k in range(n):
                self.missiles.append(FireOrb3D(mid[0], mid[1], mid[2], k, n, dmg, level))
            self.shake = max(self.shake, 5)

        self.particles.burst((s.x, s.y, s.z + 30), 2, spec["color"], speed=4, size=5)
        snd = self.sfx.get("w_" + wid) or self.snd_shoot          # 每種武器各自的音效（主砲用 shoot.wav）
        if snd:
            snd.play()

    def fire_laser(self, level):
        """
        雷射是持續光束，不是發射物：每幀直接判定「以戰機為軸心的圓柱」內有誰。
        彈藥按幀數消耗，所以 HUD 上的數字等於還能射幾幀。
        """
        s = self.ship
        if not s.consume():
            self.laser_on = 0
            return
        self.last_fire = self.frame_no
        self.laser_on = 3
        self.laser_level = level
        spec = WEAPONS["LASER"]
        radius = 46 + level * 18
        self.laser_tick += 1
        if self.laser_tick % spec["cd_lv"][level - 1] != 0:
            return
        dmg = spec["dmg_lv"][level - 1]
        for e in list(self.enemies):
            if not e.alive or e.z < s.z:
                continue
            if (e.x - s.x) ** 2 + (e.y - s.y) ** 2 <= (radius + e.radius) ** 2:
                self.particles.burst(e.pos(), 2, (120, 255, 190), speed=5, size=5)
                if e.take_damage(dmg):
                    e.alive = False
                    self.on_kill(e)
        b = self.boss
        if b and not b.dying and not b.entering and b.z > s.z:
            if (b.x - s.x) ** 2 + (b.y - s.y) ** 2 <= (radius + b.radius) ** 2:
                b.take_damage(dmg)

    def draw_laser(self, surf):
        """光束從兩側槍口射向遠方，在消失點會合。"""
        s = self.ship
        far = project(s.x, s.y, min(FAR - 10, s.z + 3000))
        if not far:
            return
        w = 4 + self.laser_level * 3
        for port in s.gun_ports():
            near = project(*port)
            if not near:
                continue
            pygame.draw.line(surf, (60, 200, 150), (near[0], near[1]), (far[0], far[1]), w + 6)
            pygame.draw.line(surf, (120, 255, 190), (near[0], near[1]), (far[0], far[1]), w)
            pygame.draw.line(surf, WHITE, (near[0], near[1]), (far[0], far[1]), max(1, w // 3))
        blit_glow(surf, (int(far[0]), int(far[1])), 26, (40, 110, 80))

    # ---------- 事件 ----------
    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            if e.type in (pygame.TEXTEDITING, pygame.TEXTINPUT) or \
                    e.type == getattr(pygame, "WINDOWFOCUSGAINED", -1):
                # 收到「組字中」訊號 = 中文輸入法正在攔截按鍵；視窗重新取得焦點時也可能重新啟用
                self.disable_ime()
                if e.type == pygame.TEXTEDITING and self.state == self.STATE_PLAY:
                    if pygame.time.get_ticks() - self.ime_warn_t > 4000:
                        self.ime_warn_t = pygame.time.get_ticks()
                        self.switch_popup = ("INPUT METHOD DETECTED", "Switch your keyboard to English, "
                                             "or fire with the LEFT MOUSE button", (255, 210, 120), 200)
                        print("[輸入法] 偵測到中文輸入法正在攔截按鍵：請切換成英文輸入，或改用滑鼠左鍵射擊")
            if e.type == pygame.MOUSEWHEEL and self.state == self.STATE_PLAY and e.y != 0:
                # 只認垂直捲動，且兩次切換至少隔 0.15 秒：
                # 筆電觸控板放著手指時會一直送出微小捲動，不擋的話武器會被亂切
                if self.frame_no - self.wheel_cd >= 9:
                    self.wheel_cd = self.frame_no
                    self.cycle_weapon(-1 if e.y > 0 else 1)
            if e.type == pygame.KEYDOWN and (e.key == pygame.K_F11 or
                                             (e.key == pygame.K_RETURN and e.mod & pygame.KMOD_ALT)):
                self.toggle_fullscreen()                      # F11 / Alt+Enter：全螢幕 <-> 視窗
                continue
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    return False
                if e.key == pygame.K_f:
                    self.show_fps = not self.show_fps
                if e.key == pygame.K_p and self.state in (self.STATE_PLAY, self.STATE_PAUSE):
                    if self.state == self.STATE_PLAY:
                        self.state = self.STATE_PAUSE
                        if self.audio:
                            pygame.mixer.music.pause()
                    else:
                        self.state = self.STATE_PLAY
                        if self.audio:
                            pygame.mixer.music.unpause()
                # 炸彈與大絕改在 update_play 以「每幀輪詢」處理，不放在這裡。
                # 原因：同時按住空白鍵與方向鍵時，很多薄膜鍵盤會漏掉第 4 顆鍵的
                # KEYDOWN 事件（鍵盤重影）。輪詢讀的是按鍵當下狀態，可靠得多。
                # 切換武器同樣改在 update_play 以輪詢處理（理由同上：避免鍵盤重影）
                if e.key == pygame.K_b and self.state == self.STATE_TITLE:
                    self.start_boss_rush()                 # 標題畫面按 B：直接挑戰最終魔王
                if e.key in (pygame.K_SPACE, pygame.K_RETURN) and self.state == self.STATE_TITLE:
                    self.state = self.STATE_PLAY
                    self.reset()
                    self.play_music()
                if e.key == pygame.K_r and self.state in (self.STATE_OVER, self.STATE_WIN):
                    self.state = self.STATE_PLAY
                    self.reset()
                    self.play_music()
        return True

    # ---------- 目標選擇 ----------
    def nearest_target(self):
        best, bd = None, float("inf")
        cands = list(self.enemies)
        if self.boss and not self.boss.dying and not self.boss.entering:
            cands.append(self.boss)
        for e in cands:
            x, y, z = e.pos()
            d = (x - self.ship.x) ** 2 + (y - self.ship.y) ** 2 + (z - self.ship.z) ** 2
            if d < bd:
                bd, best = d, e
        return best

    # ---------- 3D 碰撞 ----------
    @staticmethod
    def hit3d(a_pos, a_r, b_pos, b_r):
        dx = a_pos[0] - b_pos[0]
        dy = a_pos[1] - b_pos[1]
        dz = a_pos[2] - b_pos[2]
        r = a_r + b_r
        return dx * dx + dy * dy + dz * dz <= r * r

    # ---------- 每幀 ----------
    def poll_actions(self, keys):
        """讀取炸彈、大絕、切換武器的按鍵（邊緣觸發）。在定格判斷之前呼叫，定格才不會吞掉輸入。"""
        # 炸彈與衝擊波：輪詢按鍵狀態（不是靠 KEYDOWN 事件），並各給多組替代鍵。
        # 原因：同時按住空白鍵與方向鍵時，很多鍵盤會漏掉第 4 顆鍵的事件（重影）。
        # 但輪詢要配合「邊緣觸發」——只在按下的那一幀算數，
        # 否則按著不放會在幾秒內把存量全部燒光。
        # 不用 Ctrl / Shift：Ctrl+空白鍵、Shift 會切換中文輸入法，切過去之後空白鍵與數字鍵會被攔截
        bomb_key = keys[pygame.K_x] or keys[pygame.K_b]
        shock_key = keys[pygame.K_k] or keys[pygame.K_v] or keys[pygame.K_RETURN]
        if bomb_key and not self.prev_bomb_key:
            self.use_bomb()
        if shock_key and not self.prev_shock_key:
            self.use_shockwave()
        self.prev_bomb_key = bomb_key
        self.prev_shock_key = shock_key

        # 切換武器：數字鍵 1~7（含右側數字鍵盤）直選、Q/E 循環，一樣用邊緣觸發
        kp = (pygame.K_KP1, pygame.K_KP2, pygame.K_KP3, pygame.K_KP4,
              pygame.K_KP5, pygame.K_KP6, pygame.K_KP7)
        now = {}
        for i, wid in enumerate(WEAPON_ORDER):
            now[wid] = keys[WEAPONS[wid]["key"]] or keys[kp[i]]
        now["Q"] = keys[pygame.K_q]
        now["E"] = keys[pygame.K_e]
        for k, down in now.items():
            if down and not self.prev_wkeys.get(k):
                if k == "Q":
                    self.cycle_weapon(-1)
                elif k == "E":
                    self.cycle_weapon(1)
                else:
                    self.try_select(k)
        self.prev_wkeys = now

    def update_play(self):
        keys = pygame.key.get_pressed()
        self.poll_actions(keys)            # 先讀按鍵：擊殺定格只暫停畫面，不會吞掉換武器、炸彈、大絕的按鍵
        if self.freeze > 0:
            self.freeze -= 1
            return

        s = self.ship
        if s.update(keys, self.particles, self.terrain):
            self.shake = max(self.shake, 11)

        self.frame_no += 1
        self.play_frames += 1
        if s.weapon not in s.arsenal:       # 防呆：目前武器不在武器庫裡就退回主砲
            s.weapon = "PULSE"
        fire = keys[pygame.K_SPACE] or pygame.mouse.get_pressed()[0]   # 滑鼠左鍵也能射擊（不受輸入法影響）
        if s.weapon == "ATOMIC":
            if self.beam is None and self.atomic_cd == 0:
                self.update_atomic(fire)    # 原子光束：按住蓄力、放開發射
            elif fire:
                # 原子光束冷卻中：按住射擊自動改用主砲，絕不會出現「按了沒反應」
                self.shoot(override="PULSE")
        else:
            if self.charge:
                self.cancel_charge()
            if fire:
                self.shoot()
        self.fire_watchdog(fire)

        self.world_speed = 26.0 + self.wave * 1.2
        self.stars.update(self.world_speed)
        self.terrain.update(self.world_speed)

        for e in self.enemies:
            e.update(s, self.enemy_bullets, self)
        for b in self.bullets:
            b.update()
        target = self.nearest_target()
        for m in self.missiles:
            m.update(target, self.particles)
        self.update_shockwaves()
        self.update_novas()
        # 魔王戰補給：小怪很少、補血包幾乎掉不出來，所以定期在玩家前方投放
        b = self.boss
        if b is not None and not b.dying and not b.entering:
            self.boss_med_t += 1
            low = self.ship.hp < self.ship.max_hp * 0.5
            if self.boss_med_t >= (480 if low else 780):
                self.boss_med_t = 0
                if self.ship.hp < self.ship.max_hp * 0.9:
                    self.heal_supply()
        if self.beam is not None:
            self.beam.update(self)
            if not self.beam.alive:
                self.beam = None
        for b in self.plasmas:
            b.update()
        for b in self.rails:
            b.update()
        for b in self.enemy_bullets:
            b.update()
        for ex in self.explosions:
            ex.update(self.world_speed)
        for pu in self.powerups:
            pu.update(self.world_speed, self.ship)
        for t in self.texts:
            t.update()
        self.particles.update(self.world_speed)

        # --- 生成 ---
        self.spawn_timer += 1
        if self.spawn_timer >= self.spawn_interval():
            self.spawn_timer = 0
            self.spawn()

        if self.is_boss_wave() and not self.boss_spawned:
            self.boss_spawned = True
            if self.wave >= FINAL_BOSS_WAVE and self.kaiju_frames:
                self.boss = KaijuBoss(self.kaiju_frames, self.wave)
                self.texts.append(FloatText3D((CX, CY - 60), "!! MEGALON !!", (255, 90, 50),
                                              self.font_l, life=140, rise=0.15))
            else:
                self.boss = Boss3D(self.img_boss, max(self.wave, 5))   # 第 4 關登場，強度維持原本第 5 關
                self.texts.append(FloatText3D((CX, CY - 60), "!! MOTHERSHIP !!", RED,
                                              self.font_l, life=100, rise=0.2))

        # --- BOSS ---
        if self.boss:
            b = self.boss
            b.update(s, self.enemy_bullets, self)
            if not b.dying:
                for bl in self.bullets:
                    if bl.alive and self.hit3d(bl.pos(), bl.radius, b.pos(), b.radius):
                        bl.alive = False
                        b.take_damage(bl.dmg, at=bl.pos())     # 帶命中位置：虛淵的眼睛是弱點
                        self.particles.burst(bl.pos(), 2, (255, 220, 150), speed=5)
                for m in self.missiles:
                    if m.alive and self.hit3d(m.pos(), m.radius, b.pos(), b.radius):
                        if isinstance(m, CometShot3D):              # 彗星穿透：每 10 幀判定一次，打 3 次才消失
                            if m.boss_cd > 0:
                                continue
                            m.boss_cd = 10
                            b.take_damage(m.dmg, at=m.pos())
                            self.particles.burst(m.pos(), 8, (120, 210, 255), speed=10)
                            m.pierce -= 1
                            if m.pierce <= 0:
                                m.alive = False
                            continue
                        m.alive = False
                        b.take_damage(m.dmg)
                        self.boom(m.pos())
                if b.hp <= 0:
                    b.dying = True
                    b.death_timer = 80
                    self.enemy_bullets.clear()
                    if isinstance(b, KaijuBoss):
                        self.stop_boss_audio()
                        self.kaiju_roar(b, which=0)        # 倒下前的最後一聲
                        b.death_timer = 200
                        b.effects.clear()
                        b.beams.clear()
                if self.hit3d((s.x, s.y, s.z), s.radius, b.pos(), b.radius * 0.7):
                    if s.hit(b.damage):
                        self.shake = max(self.shake, 10)
            elif isinstance(b, KaijuBoss):
                self.kaiju_dying(b)
            else:
                b.death_timer -= 1
                if b.death_timer % 9 == 0:
                    self.boom((b.x + random.uniform(-200, 200),
                               b.y + random.uniform(-150, 150),
                               b.z + random.uniform(-150, 150)))
                if b.death_timer <= 0:
                    self.boom(b.pos(), big=True)
                    self.flash = 170
                    self.freeze = 5
                    self.combo += 3
                    self.combo_timer = 130
                    self.add_score(b.score, b.pos())
                    self.texts.append(FloatText3D((CX, CY - 40), "MOTHERSHIP DESTROYED!",
                                                  CYAN, self.font_l, life=110, rise=0.2))
                    for _ in range(2):
                        self.grant_weapon(ahead=600)
                    for _ in range(3):
                        self.powerups.append(PowerUp3D(
                            (b.x + random.uniform(-150, 150), b.y, b.z),
                            random.choice(["power", "heal", "shield", "bomb"])))
                    self.boss = None
                    self.next_wave()

        # --- 我方彈 vs 敵人 ---
        for bl in self.bullets:
            if not bl.alive:
                continue
            for e in self.enemies:
                if e.alive and self.hit3d(bl.pos(), bl.radius, e.pos(), e.radius):
                    bl.alive = False
                    self.particles.burst(bl.pos(), 2, (200, 240, 255), speed=5, size=6)
                    if e.take_damage(bl.dmg):
                        e.alive = False
                        self.on_kill(e)
                    break

        # --- 電漿 vs 敵人（命中後範圍爆傷） ---
        for b in self.plasmas:
            if not b.alive:
                continue
            for e in self.enemies:
                if e.alive and self.hit3d(b.pos(), b.radius, e.pos(), e.radius):
                    b.alive = False
                    self.boom(b.pos(), big=True)
                    for o in self.enemies:
                        if o.alive and self.hit3d(b.pos(), b.splash, o.pos(), o.radius):
                            dmg = b.dmg if o is e else max(1, b.dmg - 1)
                            if o.take_damage(dmg):
                                o.alive = False
                                self.on_kill(o)
                    break
            if b.alive and self.boss and not self.boss.dying and \
                    self.hit3d(b.pos(), b.radius + 40, self.boss.pos(), self.boss.radius):
                b.alive = False
                self.boom(b.pos(), big=True)
                self.boss.take_damage(b.dmg + 2)

        # --- 軌道炮 vs 敵人（穿透，一路打穿整排） ---
        for b in self.rails:
            if not b.alive:
                continue
            for e in self.enemies:
                if e.alive and id(e) not in b.hit_ids and \
                        self.hit3d(b.pos(), b.radius, e.pos(), e.radius):
                    b.hit_ids.add(id(e))
                    self.particles.burst(e.pos(), 4, (255, 150, 190), speed=8)
                    if e.take_damage(b.dmg):
                        e.alive = False
                        self.on_kill(e)
            if self.boss and not self.boss.dying and id(self.boss) not in b.hit_ids and \
                    self.hit3d(b.pos(), b.radius, self.boss.pos(), self.boss.radius):
                b.hit_ids.add(id(self.boss))
                self.boss.take_damage(b.dmg)

        # --- 飛彈 vs 敵人 ---
        for m in self.missiles:
            if not m.alive:
                continue
            if isinstance(m, CometShot3D):                              # 彗星：穿透，同一隻敵人只打一次
                for e in self.enemies:
                    if e.alive and id(e) not in m.hit_ids and self.hit3d(m.pos(), m.radius, e.pos(), e.radius):
                        m.hit_ids.add(id(e))
                        self.particles.burst(e.pos(), 10, (120, 210, 255), speed=11)
                        if e.take_damage(m.dmg):
                            e.alive = False
                            self.on_kill(e)
                        m.pierce -= 1
                        if m.pierce <= 0:
                            m.alive = False
                            break
                continue
            for e in self.enemies:
                if e.alive and self.hit3d(m.pos(), m.radius, e.pos(), e.radius):
                    m.alive = False
                    self.boom(m.pos())
                    if e.take_damage(m.dmg):
                        e.alive = False
                        self.on_kill(e)
                    break

        # --- 敵彈 vs 我方 ---
        ship_pos = (s.x, s.y, s.z)
        for bl in self.enemy_bullets:
            if bl.alive and self.hit3d(bl.pos(), bl.radius, ship_pos, s.radius):
                bl.alive = False
                if s.hit(14):
                    self.shake = max(self.shake, 8)
                    self.particles.burst(ship_pos, 8, (255, 120, 90), speed=10)

        # --- 敵人撞我方 ---
        for e in self.enemies:
            if e.alive and self.hit3d(e.pos(), e.radius, ship_pos, s.radius):
                e.alive = False
                self.boom(e.pos(), big=True)
                s.hit(e.damage)

        # --- 撿道具 ---
        for pu in self.powerups:
            if pu.alive and self.hit3d(pu.pos(), pu.radius, ship_pos, s.radius):
                pu.alive = False
                self.apply_powerup(pu)

        # --- 清除死亡物件 ---
        self.enemies = [e for e in self.enemies if e.alive]
        self.bullets = [b for b in self.bullets if b.alive]
        for m in self.missiles:
            if not m.alive and isinstance(m, BombRocket3D):
                self.rocket_blast(m)                            # 命中或燃料耗盡：都會爆炸
        self.missiles = [m for m in self.missiles if m.alive]
        self.plasmas = [b for b in self.plasmas if b.alive]
        self.rails = [b for b in self.rails if b.alive]
        self.enemy_bullets = [b for b in self.enemy_bullets if b.alive]
        self.explosions = [e for e in self.explosions if e.alive]
        self.powerups = [p for p in self.powerups if p.alive]
        self.texts = [t for t in self.texts if t.alive]

        # --- 連擊 ---
        if self.combo_timer > 0:
            self.combo_timer -= 1
            if self.combo_timer == 0:
                self.combo = 0

        # --- 死亡 ---
        if s.hp <= 0:
            s.lives -= 1
            self.boom((s.x, s.y, s.z), big=True)
            self.enemy_bullets.clear()
            if s.lives > 0:
                s.hp = s.max_hp
                slot = s.arsenal.get(s.weapon)
                if slot:
                    slot["level"] = max(1, slot["level"] - 1)
                s.invincible = 130
                s.x, s.y = 0.0, 250.0
                self.combo = 0
            else:
                self.state = self.STATE_OVER

        if not self.is_boss_wave():
            if self.wave in MINI_BOSS_WAVES:
                if self.miniboss_stage == 0 and self.kills >= self.kills_needed:
                    self.miniboss_stage = 1                     # 小兵打完：場面清空後小魔王登場
                    self.miniboss_pending = True
                elif self.miniboss_stage == 1 and not self.miniboss_pending and not self.miniboss_on_field():
                    self.miniboss_stage = 2                     # 保險：小魔王意外離場也照常過關
                if self.miniboss_stage == 2:
                    self.next_wave()
            elif self.kills >= self.kills_needed:
                self.next_wave()

        if self.laser_on > 0:
            self.laser_on -= 1
        if self.shake > 0:
            self.shake = max(0, self.shake - 0.6)
        if self.flash > 0:
            self.flash = max(0, self.flash - 9)

    def apply_powerup(self, pu):
        s = self.ship
        self.particles.burst(pu.pos(), 10, pu.color, speed=8)

        if isinstance(pu, WeaponPack3D):
            # 蓄力中或光束發射中不自動換武器，避免打斷原子光束
            busy = self.charge > 0 or self.beam is not None
            before = s.weapon
            # 原子光束不自動換上：它是「按住蓄力」，自動換上會讓按住射擊突然變成沒反應
            label = s.add_weapon(pu.wid, auto_equip=not busy and pu.wid != "ATOMIC")
            if s.weapon != before:
                self.show_switch(s.weapon)
            p = project(s.x, s.y, s.z)
            if p:
                self.texts.append(FloatText3D((p[0], p[1] - 40), label, pu.color,
                                              self.font_m, life=60))
            return

        if pu.kind == "power":
            label = s.upgrade_current()
        elif pu.kind == "heal":
            s.hp = min(s.max_hp, s.hp + 35)
            label = "+35 HP"
        elif pu.kind == "shield":
            s.shield = 60 * 8
            label = "SHIELD"
        else:
            self.bombs = min(3, self.bombs + 1)
            label = "+1 BOMB"
        p = project(s.x, s.y, s.z)
        if p:
            self.texts.append(FloatText3D((p[0], p[1] - 40), label, pu.color, self.font_s))

    def grant_weapon(self, ahead=900):
        """
        在玩家前方投放一個武器包。優先給還沒有的武器，
        全部都有了才給現有武器補彈藥升級。
        這確保武器系統一定會被玩家發現，不會因為運氣差而整場只用主砲。
        """
        missing = [w for w in DROPPABLE_WEAPONS if w not in self.ship.arsenal]
        wid = random.choice(missing) if missing else random.choice(DROPPABLE_WEAPONS)
        atomic = self.ship.arsenal.get("ATOMIC")
        if (atomic is None or atomic["ammo"] <= 1) and random.random() < 0.5:
            wid = "ATOMIC"                  # 原子光束快用完了：過關補給優先給它
        self.powerups.append(WeaponPack3D(
            (self.ship.x + random.uniform(-120, 120), self.ship.y - 60,
             self.ship.z + ahead), wid))

    def next_wave(self):
        self.miniboss_stage = 0
        self.miniboss_pending = False
        self.kills = 0
        self.wave += 1
        self.grant_weapon()
        if self.ship.hp < self.ship.max_hp * 0.7:          # 過關保底：血量不到七成就送一個補血包
            self.heal_supply(ahead=1000)
        self.kills_needed = 8 + self.wave * 2
        self.boss_spawned = False
        if not self.is_boss_wave():
            self.texts.append(FloatText3D((CX, CY - 40), f"WAVE {self.wave}",
                                          CYAN, self.font_l, life=80, rise=0.5))

    # ---------- HUD ----------
    def draw_reticle(self, surf):
        """兩層準星：顯示彈道在遠近兩個深度的落點，是 3D 射擊瞄準的關鍵。"""
        s = self.ship
        cols = ((0, 130, 220), (0, 100, 180)) if ICE else ((120, 230, 255), (90, 180, 210))
        for dz, r, col in ((520, 26, cols[0]), (1500, 14, cols[1])):
            p = project(s.x * (1 - dz / 4200), s.y * (1 - dz / 4200), s.z + dz)
            if not p:
                continue
            x, y, sc = int(p[0]), int(p[1]), p[2]
            rr = max(5, int(r * sc * 2.4))
            pygame.draw.circle(surf, col, (x, y), rr, 1)
            for a in (0, 90, 180, 270):
                dx = math.cos(math.radians(a))
                dy = math.sin(math.radians(a))
                pygame.draw.line(surf, col,
                                 (x + dx * rr * 0.6, y + dy * rr * 0.6),
                                 (x + dx * rr * 1.5, y + dy * rr * 1.5), 1)

    def draw_radar(self, surf):
        """右下深度雷達（JoJo 風）：深藍斜面板 + 網點、黃色標籤，所有點都帶黑邊。"""
        f = self._jj_fonts()
        w, h, sk = 170, 108, 14
        x0, y0 = SCREEN_W - w - sk - 30, SCREEN_H - h - 36
        surf.blit(self._jj_panel(w, h, sk, (40, 44, 96)), (x0 - 8, y0 - 8))
        tag = self._jj_panel(62, 16, 6, (255, 228, 40), tone=False)
        surf.blit(tag, (x0 + 4, y0 - 20))
        surf.blit(self._jj_t(f["chip"], "DEPTH", (8, 4, 12), ow=0), (x0 + 22, y0 - 14))
        cx = x0 + sk // 2 + w // 2
        for k in (1, 2, 3):
            tt = (k * 1000 - NEAR) / (SPAWN_Z - NEAR)
            yy = int(y0 + h - 8 - tt * (h - 16))
            pygame.draw.line(surf, (90, 96, 150), (x0 + 12 + sk * (1 - (yy - y0) / h), yy), (x0 + w - 4, yy), 1)
        pygame.draw.line(surf, (90, 96, 150), (cx, y0 + 6), (cx, y0 + h - 6), 1)

        def pos(ex, ez):
            tt = max(0.0, min(1.0, (ez - NEAR) / (SPAWN_Z - NEAR)))
            return int(cx + (ex / 800) * (w // 2 - 10)), int(y0 + h - 8 - tt * (h - 16))
        for e in self.enemies:
            px, py = pos(e.x, e.z)
            if e.etype == 3:
                pygame.draw.circle(surf, (255, 70, 60), (px, py), 6)
                pygame.draw.circle(surf, (8, 4, 12), (px, py), 6, 2)
            else:
                pygame.draw.circle(surf, (255, 255, 255), (px, py), 3)
                pygame.draw.circle(surf, (8, 4, 12), (px, py), 3, 1)
        if self.boss:
            px, py = pos(self.boss.x, self.boss.z)
            r = int(8 + 2 * math.sin(pygame.time.get_ticks() * 0.01))
            pygame.draw.circle(surf, (255, 228, 40), (px, py), r + 3)
            pygame.draw.circle(surf, (255, 50, 40), (px, py), r)
            pygame.draw.circle(surf, (8, 4, 12), (px, py), r + 3, 2)
        bx, by = cx, y0 + h - 2
        tri = [(bx, by - 9), (bx - 7, by + 2), (bx + 7, by + 2)]
        pygame.draw.polygon(surf, (255, 228, 40), tri)
        pygame.draw.polygon(surf, (8, 4, 12), tri, 2)

    def draw_hud(self, surf):
        s = self.ship
        self.draw_telemetry(surf)                     # 先畫：上緣的深色漸層要墊在所有狀態資訊底下
        self.draw_status(surf)
        self.draw_weapon_bar(surf)

        if self.ship.ground_warn and self.state == self.STATE_PLAY:
            if (pygame.time.get_ticks() // 220) % 2 == 0:
                f = self._jj_fonts()
                key = ("pullup",)
                img = self._jj_cache.get(key)
                if img is None:
                    stops = ((0.0, (255, 230, 200)), (0.48, (255, 120, 90)), (0.52, (170, 10, 10)), (1.0, (255, 70, 50)))
                    img = pygame.transform.rotozoom(self._chrome_text(f["warn"], "PULL UP!!", stops, outline=5,
                                                                      depth=5, depth_col=(60, 0, 0)), -5, 1.0)
                    self._jj_cache[key] = img
                surf.blit(img, img.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.6))))   # 避開下方的切換提示

        self.draw_radar(surf)

        if self.show_fps:
            f = self.font_s.render(f"{self.clock.get_fps():.0f} FPS  "
                                   f"obj {len(self.enemies)+len(self.bullets)+len(self.enemy_bullets)}",
                                   True, GREEN)
            surf.blit(f, (18, SCREEN_H - 28))

    def draw_panel(self, surf, lines, pad=42):
        rendered = [(f.render(t, True, c), g) for t, f, c, g in lines]
        content = sum(g for _, g in rendered[:-1]) + rendered[-1][0].get_height()
        box = content + pad * 2
        p = pygame.Surface((SCREEN_W, box), pygame.SRCALPHA)
        p.fill((8, 10, 24, 212))
        top = SCREEN_H // 2 - box // 2
        surf.blit(p, (0, top))
        pygame.draw.line(surf, (90, 110, 190), (0, top), (SCREEN_W, top), 2)
        pygame.draw.line(surf, (90, 110, 190), (0, top + box), (SCREEN_W, top + box), 2)
        y = top + pad + rendered[0][0].get_height() // 2
        for img, gap in rendered:
            surf.blit(img, img.get_rect(center=(SCREEN_W // 2, y)))
            y += gap

    def draw_ship_shadow(self, surf):
        """戰機在冰面上的影子：最直接的高度線索，貼地飛行時一看就知道有多低。"""
        if self.state == self.STATE_OVER:
            return
        s = self.ship
        g = ground_at(s.x, s.z)
        p = project(s.x, g, s.z)
        if not p:
            return
        h = max(0.0, g - s.y)
        k = max(0.4, 1.0 - h / 600)
        w, hh = int(120 * p[2] * k), int(26 * p[2] * k)
        if w < 4:
            return
        sh = pygame.Surface((w * 2, hh * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (25, 45, 75, int(150 * k)), (0, 0, w * 2, hh * 2))
        surf.blit(sh, (p[0] - w, p[1] - hh))

    # ---------- 繪製（畫家演算法：全部依 z 由遠而近） ----------
    def draw(self):
        c = self.canvas
        if ICE:
            self.terrain.draw(c)                      # 天空與地形一起由光線投射合成
            self.stars.draw(c, self.world_speed)      # 冰原上變成迎面吹來的飄雪
            self.draw_ship_shadow(c)
        else:
            c.blit(self.sky, (0, 0))
            self.stars.draw(c, self.world_speed)
            self.terrain.draw(c)

        # 收集所有 3D 物件，依深度排序
        if self.beam is not None and self.beam.segs:   # 光束外層光暈（半透明，整條一次畫）
            # 只清除與合成實際畫到的範圍（上一幀的範圍也要清掉），省去整個螢幕的透明混合
            box = self.beam.glow_box().clip(self.fx_layer.get_rect())
            clear = box.union(self._glow_box) if getattr(self, "_glow_box", None) else box
            self.fx_layer.fill((0, 0, 0, 0), clear)
            self.beam.draw_glow(self.fx_layer)
            c.blit(self.fx_layer, box.topleft, box)
            self._glow_box = box
        self.draw_boss_beam_glow(c, self.boss.beams if isinstance(self.boss, KaijuBoss) else [])
        items = []
        for e in self.enemies:
            items.append((e.z, "enemy", e))
        for b in self.bullets:
            items.append((b.z, "obj", b))
        for m in self.missiles:
            items.append((m.z, "obj", m))
        for n in self.novas:
            items.append((n.z, "obj", n))
        for b in self.plasmas:
            items.append((b.z, "obj", b))
        for b in self.rails:
            items.append((b.z, "obj", b))
        for w in self.shockwaves:
            items.append((w.z, "obj", w))
        if self.beam is not None and self.beam.segs:
            for z, i in self.beam.items():            # 光束分段放進深度排序
                items.append((z, "beam", i))
        for b in self.enemy_bullets:
            items.append((b.z, "obj", b))
        for pu in self.powerups:
            items.append((pu.z, "obj", pu))
        for ex in self.explosions:
            items.append((ex.z, "obj", ex))
        if self.boss:
            items.append((self.boss.z, "obj", self.boss))
            if isinstance(self.boss, KaijuBoss):         # 虛淵的招式特效也放進深度排序
                for fx in self.boss.effects:
                    items.append((fx.z, "obj", fx))
                for bm in self.boss.beams:
                    for z, ch in bm.items():
                        items.append((z, "kbeam", (bm, ch)))
        self.particles.collect(items)
        items.sort(key=lambda t: -t[0])

        ship_z = self.ship.z
        ship_drawn = False
        for z, kind, obj in items:
            # 戰機插在正確的深度位置
            if not ship_drawn and z < ship_z:
                if self.state not in (self.STATE_OVER, self.STATE_TITLE):
                    self.ship.draw(c)
                ship_drawn = True

            if kind == "beam":
                self.beam.draw_segment(c, obj)
                continue
            if kind == "kbeam":
                obj[0].draw_chunk(c, obj[1])
                continue
            if kind == "particle":
                x, y, pz, t, color, size = obj
                p = project(x, y, pz)
                if p:
                    r = max(1, int(size * p[2] * t * 2.4))
                    if r <= 3:
                        # 小粒子直接畫實心圓：肉眼看不出差別，成本卻差十倍以上
                        pygame.draw.circle(c, color, (int(p[0]), int(p[1])), r)
                    else:
                        blit_glow(c, (int(p[0]), int(p[1])), r * 2,
                                  tuple(int(v * t) for v in color))
                continue

            p = project(*obj.pos())
            if p:
                obj.draw(c, p)

        if not ship_drawn and self.state not in (self.STATE_OVER, self.STATE_TITLE):
            self.ship.draw(c)
        self.draw_charge(c)
        if self.beam is not None and self.beam.t < 18:   # 發射瞬間整個畫面閃一下藍光
            self.tint.set_alpha(int(40 * (1 - self.beam.t / 18)))
            c.blit(self.tint, (0, 0))

        if self.laser_on > 0 and self.state == self.STATE_PLAY:
            self.draw_laser(c)
        if self.state == self.STATE_PLAY:
            self.draw_reticle(c)

        for t in self.texts:
            t.draw(c)

        if self.flash > 0:
            self.white.set_alpha(min(200, self.flash))
            c.blit(self.white, (0, 0))

        if self.state == self.STATE_PLAY and self.ship.hp <= self.ship.max_hp * 0.3:
            pulse = 0.6 + 0.4 * math.sin(pygame.time.get_ticks() * 0.012)
            self.vignette.set_alpha(int(255 * pulse))
            c.blit(self.vignette, (0, 0))

        if self.state != self.STATE_TITLE:
            self.draw_hud(c)

        if self.state == self.STATE_TITLE and getattr(self, "asset_warning", None):
            for k, line in enumerate(self.asset_warning):          # 素材缺少時直接在畫面上提醒
                img = self.font_s.render(line, True, (255, 150, 90))
                c.blit(img, (SCREEN_W // 2 - img.get_width() // 2, 18 + k * 24))
        if self.state == self.STATE_TITLE:
            self.draw_title(c)
        elif self.state == self.STATE_PAUSE:
            self.draw_panel(c, [("PAUSED", self.font_xl, WHITE, 56),
                                ("Press P to resume", self.font_m, GREY, 0)])
        elif self.state == self.STATE_WIN:
            self.draw_win(c)
        elif self.state == self.STATE_OVER:
            best = ("NEW HIGH SCORE!" if self.score >= self.high_score and self.score > 0
                    else f"BEST  {self.high_score}")
            self.draw_panel(c, [
                ("GAME OVER", self.font_xl, RED, 60),
                (f"SCORE  {self.score}", self.font_l, WHITE, 42),
                (f"WAVE {self.wave}      MAX COMBO {self.max_combo}", self.font_m, CYAN, 34),
                (best, self.font_m, YELLOW, 44),
                ("Press R to restart      ESC to quit", self.font_s, GREY, 0),
            ])

        if self.shake > 0.5:
            sh = self.shake
            self.screen.fill(BLACK)
            self.screen.blit(c, (random.uniform(-sh, sh) * 0.6, random.uniform(-sh, sh) * 0.6))
        else:
            self.screen.blit(c, (0, 0))
        pygame.display.flip()

    # ---------- 主迴圈 ----------
    def auto_quality(self, work_ms):
        """
        自動畫質：記錄最近 2 秒每幀的實際運算時間，平均超過 14 ms
        （60fps 的預算是 16.7 ms，留一點餘裕）就把冰原地形降一級。
        這樣慢一點的電腦也不會卡頓，快的電腦則維持最高畫質。
        """
        if not ICE or self.state != self.STATE_PLAY:
            return
        if self.beam is not None or self.shockwaves:
            # 大型特效只持續一兩秒，不該因此永久降低整局的地形畫質
            return
        self._work.append(work_ms)
        if len(self._work) < 120:
            return
        avg = sum(self._work) / len(self._work)
        self._work.clear()
        order = ["high", "medium", "low"]
        q = getattr(self.terrain, "quality", "high")
        if avg > 14.0 and q != "low":
            nq = order[order.index(q) + 1]
            self.terrain.set_quality(nq)
            print(f"[畫質] 平均每幀 {avg:.1f} ms，冰原地形自動調整為 {nq}")

    def run(self):
        running = True
        self._work = []
        if self.state == self.STATE_TITLE and self.audio and "intro" in self.music_files:
            self._start_music("intro")                       # 標題畫面：片頭音樂循環播放
        while running:
            self.clock.tick(FPS)
            t_work = pygame.time.get_ticks()
            running = self.handle_events()

            if self.state == self.STATE_PLAY:
                self.update_play()
            elif self.state == self.STATE_TITLE:
                self.stars.update(14)
                self.terrain.update(14)
                self.update_title_scene()
            elif self.state in (self.STATE_OVER, self.STATE_WIN):
                self.stars.update(8)
                self.terrain.update(8)
                for ex in self.explosions:
                    ex.update(8)
                for t in self.texts:
                    t.update()
                self.particles.update(8)
                self.explosions = [e for e in self.explosions if e.alive]
                self.texts = [t for t in self.texts if t.alive]
                if self.flash > 0:
                    self.flash = max(0, self.flash - 9)
                if self.shake > 0:
                    self.shake = max(0, self.shake - 0.6)
                if not self.over_handled:
                    self.over_handled = True
                    if self.state == self.STATE_OVER:
                        self.stop_music()
                        if self.snd_over:
                            self.snd_over.play()
                    if self.score > self.high_score:
                        self.high_score = self.score
                        self.save_high_score()

            self.sync_boss_audio()
            self.update_music()
            self.draw()
            self.auto_quality(pygame.time.get_ticks() - t_work)

        self.stop_music()
        pygame.quit()
        sys.exit()


def run_with_crash_log():
    """
    包一層錯誤攔截：Windows 上遊戲出錯時視窗會瞬間關閉，連錯誤訊息都看不到。
    這裡把完整錯誤與環境版本存到 crash_log.txt，並讓視窗停住，方便回報問題。
    """
    try:
        Game().run()
    except SystemExit:
        raise
    except Exception:
        import traceback
        import platform
        info = (f"Python {sys.version.split()[0]} ({platform.architecture()[0]}), "
                f"pygame {pygame.version.ver}, "
                f"numpy {numpy.__version__ if numpy else '未安裝'}, "
                f"環境 {ENVIRONMENT}, 系統 {platform.platform()}")
        text = "遊戲發生錯誤\n" + info + "\n\n" + traceback.format_exc()
        try:
            with open(os.path.join(ASSET_DIR, "crash_log.txt"), "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass
        print("\n" + "=" * 60 + "\n" + text + "=" * 60)
        print("錯誤內容已存成 crash_log.txt，請把這個檔案的內容回報。")
        try:
            pygame.quit()
            input("按 Enter 關閉視窗 ...")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    run_with_crash_log()
