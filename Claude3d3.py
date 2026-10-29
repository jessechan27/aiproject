"""
================================================================
 ALIEN SHOOTER 3D
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
   1~6 / Q / E     切換武器
   X / B / Ctrl    炸彈（防禦：瞬間清掉身邊彈幕）
   K / V / Shift   衝擊波大絕（攻擊：環形波往深處掃蕩，全場限用 5 次）
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
   3 LASER   持續穿透光束，打排成一列的敵人
   4 HOMING  自動鎖定飛彈，不用瞄準
   5 PLASMA  慢速大彈 + 範圍爆傷，清場用
   6 RAIL    高傷穿透、射速極慢，打 BOSS 與硬目標

 需求： pip install pygame
================================================================
"""

import os
import sys
import math
import random
import pygame

# ---------------------------------------------------------------
# 基本設定
# ---------------------------------------------------------------
SCREEN_W, SCREEN_H = 960, 720
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


def blit_glow(surf, center, radius, color):
    g = glow(radius, color)
    surf.blit(g, (center[0] - g.get_width() // 2, center[1] - g.get_height() // 2),
              special_flags=pygame.BLEND_RGB_ADD)


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


def ground_at(x, z):
    """取得世界座標 (x, z) 處的地面高度，已計入飛行捲動。"""
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

    def add_weapon(self, wid):
        """撿到武器包：沒有就加入並自動裝備，已有就補彈藥並升級。"""
        spec = WEAPONS[wid]
        if wid in self.arsenal:
            slot = self.arsenal[wid]
            slot["level"] = min(3, slot["level"] + 1)
            if slot["ammo"] is not None:
                slot["ammo"] = min(spec["ammo"] * 2, slot["ammo"] + spec["ammo"])
            self.weapon = wid
            return f"{spec['label']} Lv{slot['level']}"
        self.arsenal[wid] = {"level": 1, "ammo": spec["ammo"]}
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
            if self.hover_time > self.RETREAT_AFTER:
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
            for off in (-0.16, 0.0, 0.16):
                self._shot(ship, enemy_bullets, off, PINK, 17.0)
        else:
            self._shot(ship, enemy_bullets, 0.0, (255, 120, 90), 15.0)

    def _shot(self, ship, enemy_bullets, spread, color, speed):
        dx = ship.x - self.x
        dy = ship.y - self.y
        dz = ship.z - self.z
        d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        vx, vy, vz = dx / d * speed, dy / d * speed, dz / d * speed
        vx += spread * speed
        enemy_bullets.append(EnemyBullet3D(self.x, self.y, self.z, vx, vy, vz, color))

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
            for i in range(n):
                self._aimed(ship, enemy_bullets, (i - (n - 1) / 2) * 0.10)

        if st >= 2 and self.t_ring >= {2: 85, 3: 60}[st]:
            self.t_ring = 0
            n = 12 if st == 2 else 16
            for i in range(n):
                a = i * math.tau / n + random.uniform(0, 0.4)
                enemy_bullets.append(EnemyBullet3D(
                    self.x, self.y, self.z,
                    math.cos(a) * 7.0, math.sin(a) * 7.0, -15.0, (255, 170, 90)))

        if self.flash > 0:
            self.flash -= 1

    def _aimed(self, ship, enemy_bullets, spread):
        dx, dy, dz = ship.x - self.x, ship.y - self.y, ship.z - self.z
        d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        s = 19.0
        enemy_bullets.append(EnemyBullet3D(
            self.x, self.y, self.z,
            dx / d * s + spread * s, dy / d * s, dz / d * s, PINK))

    def take_damage(self, dmg=1):
        if self.entering or self.dying:
            return False
        self.hp -= dmg
        self.flash = 3
        return self.hp <= 0

    def draw(self, surf, p):
        sx, sy, sc = p
        size = max(8, int(self.world_size * sc))
        img = scaled(self.image, size)
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
        self.radius = 26

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
        p2 = project(self.x - self.vx * 1.6, self.y - self.vy * 1.6, self.z - self.vz * 1.6)
        w = max(1, int(7 * sc))
        if p2:
            pygame.draw.line(surf, (190, 245, 255), (p2[0], p2[1]), (sx, sy), w)
        blit_glow(surf, (int(sx), int(sy)), max(4, int(16 * sc)), (50, 110, 150))


class Missile3D:
    """追蹤飛彈：在 3D 空間平滑轉向鎖定目標。"""
    SPEED = 40.0
    TURN = 0.14

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

        particles.emit(self.x, self.y, self.z,
                       -self.vx * 0.05, -self.vy * 0.05, -self.vz * 0.05,
                       random.randint(8, 15), (255, 170, 80), 9.0)

        self.life -= 1
        if self.life <= 0 or self.z > FAR or self.z < NEAR:
            self.alive = False

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        r = max(2, int(14 * sc))
        pygame.draw.circle(surf, ORANGE, (int(sx), int(sy)), r)
        pygame.draw.circle(surf, YELLOW, (int(sx), int(sy)), max(1, r // 2))
        blit_glow(surf, (int(sx), int(sy)), r * 3, (120, 70, 20))


class EnemyBullet3D:
    """敵彈：朝攝影機飛來，越近越大 —— 這是 3D 射擊最直觀的威脅感。"""

    def __init__(self, x, y, z, vx, vy, vz, color=(255, 120, 90)):
        self.x, self.y, self.z = x, y, z
        self.vx, self.vy, self.vz = vx, vy, vz
        self.color = color
        self.alive = True
        self.radius = 26

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.z += self.vz
        if self.z <= NEAR + 6 or self.z > FAR or abs(self.x) > 2400 or abs(self.y) > 1800:
            self.alive = False

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        r = max(2, int(26 * sc))
        blit_glow(surf, (int(sx), int(sy)), r * 3, tuple(c // 3 for c in self.color))
        pygame.draw.circle(surf, self.color, (int(sx), int(sy)), r)
        pygame.draw.circle(surf, WHITE, (int(sx), int(sy)), max(1, r // 3))


class Explosion3D:
    def __init__(self, pos, frames, delay=3, world_size=260):
        self.x, self.y, self.z = pos
        self.frames = frames
        self.index = 0
        self.timer = 0
        self.delay = delay
        self.world_size = world_size
        self.alive = True

    def update(self, world_speed):
        self.z -= world_speed * 0.25
        self.timer += 1
        if self.timer >= self.delay:
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
        img = scaled(self.frames[self.index], size, smooth=False)
        surf.blit(img, img.get_rect(center=(int(sx), int(sy))),
                  special_flags=pygame.BLEND_RGB_ADD)


# ---------------------------------------------------------------
# 武器系統
# ---------------------------------------------------------------
# 設計原則：每把武器解決不同的問題，不是數值高低的排列。
#   PULSE  基礎、無限彈藥，其他武器打完一定回得來
#   SPREAD 近距離廣角，打成群的小怪
#   LASER  持續穿透，適合排成一列的敵人
#   HOMING 自動鎖定，不用瞄準，打高機動目標
#   PLASMA 慢速大彈 + 範圍傷害，清場
#   RAIL   高傷穿透、射速極慢，打 BOSS 與硬目標
# cd_lv / dmg_lv / n_lv 是三個等級各自的冷卻、單發傷害、發數。
# 數值是靶場實測後配平的：每把武器只在「一個維度」最強，避免出現全能王。
WEAPONS = {
    "PULSE":  {"label": "PULSE",  "key": pygame.K_1, "color": (150, 230, 255),
               "ammo": None, "cd_lv": (9, 8, 7),    "dmg_lv": (1, 1, 1), "n_lv": (1, 2, 3),
               "desc": "Rapid beam - infinite ammo"},
    "SPREAD": {"label": "SPREAD", "key": pygame.K_2, "color": (255, 200, 90),
               "ammo": 70,   "cd_lv": (16, 14, 12), "dmg_lv": (1, 1, 2), "n_lv": (5, 7, 9),
               "desc": "Widest cone - crowd control"},
    "LASER":  {"label": "LASER",  "key": pygame.K_3, "color": (120, 255, 190),
               "ammo": 900,  "cd_lv": (10, 8, 6),   "dmg_lv": (1, 2, 3), "n_lv": (1, 1, 1),
               "desc": "Sustained pierce - burns ammo"},
    "HOMING": {"label": "HOMING", "key": pygame.K_4, "color": (255, 150, 60),
               "ammo": 44,   "cd_lv": (22, 20, 18), "dmg_lv": (2, 2, 3), "n_lv": (2, 2, 3),
               "desc": "Auto-lock - no aiming needed"},
    "PLASMA": {"label": "PLASMA", "key": pygame.K_5, "color": (200, 120, 255),
               "ammo": 30,   "cd_lv": (28, 26, 24), "dmg_lv": (3, 5, 7), "n_lv": (1, 1, 1),
               "desc": "Splash blast - hits everything near"},
    "RAIL":   {"label": "RAIL",   "key": pygame.K_6, "color": (255, 90, 140),
               "ammo": 16,   "cd_lv": (44, 40, 36), "dmg_lv": (9, 14, 19), "n_lv": (1, 1, 1),
               "desc": "Boss killer - pierces the whole line"},
}
WEAPON_ORDER = ["PULSE", "SPREAD", "LASER", "HOMING", "PLASMA", "RAIL"]
DROPPABLE_WEAPONS = WEAPON_ORDER[1:]     # PULSE 是內建的，不會掉落


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

    def update(self):
        self.z += self.vz
        self.phase += 0.3
        if self.z > FAR:
            self.alive = False

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        r = max(3, int((26 + self.level * 5) * sc * (1 + 0.12 * math.sin(self.phase))))
        blit_glow(surf, (int(sx), int(sy)), r * 4, (90, 40, 130))
        pygame.draw.circle(surf, (200, 120, 255), (int(sx), int(sy)), r)
        pygame.draw.circle(surf, (245, 220, 255), (int(sx), int(sy)), max(1, r // 2))


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


class ShockWave3D:
    """
    衝擊波大絕：一道環形波從戰機往畫面深處推進，沿途貫穿所有敵人與敵彈。

    和炸彈的分工：
      炸彈   = 防禦性瞬間清場，只處理「現在貼在你臉上」的威脅
      衝擊波 = 攻擊性縱深掃蕩，沿著整條通道一路清到底
    所以它不是瞬間生效，而是會飛行好幾秒，看著它把整排敵人掃掉。
    """
    SPEED = 52.0          # 前進速度
    GROWTH = 13.0         # 環半徑擴張速度
    BAND = 170.0          # 波前厚度：物件的 z 與波前差在這個範圍內才算被掃到
    DAMAGE = 14
    MAX_RADIUS = 1050.0

    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z
        self.radius = 155.0
        self.alive = True
        self.hit_ids = set()      # 每個目標只被同一道波掃到一次
        self.life = 0

    def update(self):
        self.z += self.SPEED
        self.radius = min(self.MAX_RADIUS, self.radius + self.GROWTH)
        self.life += 1
        if self.z > FAR or self.radius >= self.MAX_RADIUS and self.life > 110:
            self.alive = False

    def covers(self, pos, r=0.0):
        """目標是否落在波前的環帶內。"""
        if abs(pos[2] - self.z) > self.BAND:
            return False
        dx = pos[0] - self.x
        dy = pos[1] - self.y
        return dx * dx + dy * dy <= (self.radius + r) ** 2

    def pos(self):
        return (self.x, self.y, self.z)

    def draw(self, surf, p):
        sx, sy, sc = p
        fade = max(0.0, 1.0 - self.radius / self.MAX_RADIUS * 0.75)
        # 三層同心圓：外圈淡、中圈主體、內圈亮心
        for k, (mul, w, col) in enumerate((
                (1.00, 8, (140, 215, 255)),
                (0.84, 5, (225, 248, 255)),
                (0.66, 3, (100, 165, 235)))):
            r = int(self.radius * mul * sc)
            if r < 2:
                continue
            c = tuple(int(v * fade) for v in col)
            pygame.draw.circle(surf, c, (int(sx), int(sy)), r, max(1, int(w * sc) + 1))
        blit_glow(surf, (int(sx), int(sy)), max(8, int(self.radius * 0.42 * sc)),
                  (int(30 * fade), int(60 * fade), int(90 * fade)))


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
        self.image = font.render(text, True, color)
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
class Game:
    STATE_TITLE = "title"
    STATE_PLAY = "play"
    STATE_PAUSE = "pause"
    STATE_OVER = "over"

    def __init__(self):
        pygame.init()
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(24)
            self.audio = True
        except pygame.error as e:
            print(f"[WARN] 音效無法啟動：{e}")
            self.audio = False

        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Alien Shooter 3D")
        self.clock = pygame.time.Clock()
        self.canvas = pygame.Surface((SCREEN_W, SCREEN_H))

        self.font_s = pygame.font.Font(None, 24)
        self.font_m = pygame.font.Font(None, 34)
        self.font_l = pygame.font.Font(None, 54)
        self.font_xl = pygame.font.Font(None, 84)

        self.load_assets()
        PowerUp3D.build_images(self.font_m)
        WeaponPack3D.build_images(self.font_m)
        self.stars = StarField3D()
        self.terrain = Terrain()
        self.sky = self._make_sky()
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

        self.frames_small = self.frames_big = None
        exp = find_asset("explosion_graph.jpg", "explosion graph.jpg")
        if exp:
            try:
                self.frames_small = slice_explosion_sheet(exp, 256)
                self.frames_big = slice_explosion_sheet(exp, 384)
                print(f"  [OK]   sheet  {os.path.basename(exp)} -> 9 格動畫")
            except pygame.error as e:
                print(f"  [FAIL] sheet  {e}")
        if self.frames_small is None:
            self.frames_small = self._fallback_frames(256)
            self.frames_big = self._fallback_frames(384)
            print("  [MISS] 爆炸圖 -> 程式繪製")

        self.snd_shoot = load_sound(["shoot.wav", "shoot.mp3"], 0.2) if self.audio else None
        self.snd_explode = load_sound(["explosion.mp3", "exploresion.mp3"], 0.45) if self.audio else None
        self.snd_over = load_sound(["gameover.mp3"], 0.6) if self.audio else None
        self.music_path = find_asset("background.mp3", "background.ogg") if self.audio else None
        if self.music_path:
            print(f"  [OK]   music  {os.path.basename(self.music_path)}")
        print()

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

    def play_music(self):
        if self.music_path:
            try:
                pygame.mixer.music.load(self.music_path)
                pygame.mixer.music.set_volume(0.3)
                pygame.mixer.music.play(-1)
            except pygame.error:
                pass

    def stop_music(self):
        if self.audio:
            pygame.mixer.music.stop()

    # ---------- 新局 ----------
    def reset(self):
        self.ship = Ship3D()
        self.enemies = []
        self.bullets = []
        self.missiles = []
        self.plasmas = []
        self.rails = []
        self.enemy_bullets = []
        self.explosions = []
        self.powerups = []
        self.texts = []
        self.particles = Particles3D()

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
        return self.wave % 5 == 0

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
            self.enemies.append(Enemy3D(3, self.img_enemies[3], self.wave,
                                        random.uniform(-220, 220),
                                        random.uniform(-120, 60)))
            self.texts.append(FloatText3D((CX, CY - 30), "!! MINI BOSS !!", PINK,
                                          self.font_l, life=90, rise=0.25))
            return

        if self.boss:
            etype = random.choice((1, 2))
        else:
            w = self.wave
            # 順序對應 [E1漂移, E2蛇行, E3飛碟(小BOSS), E4獵人]
            weights = [max(1, 55 - w * 4), 30 + w, max(0, w - 1) * 2, 10 + w * 2]
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

    def maybe_drop(self, enemy):
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
        if self.snd_explode:
            self.snd_explode.play()

    def update_shockwaves(self):
        """波前掃過的東西：敵人受重傷、敵彈直接蒸發、BOSS 也吃傷害。"""
        for w in self.shockwaves:
            w.update()
            for e in self.enemies:
                if e.alive and id(e) not in w.hit_ids and w.covers(e.pos(), e.radius):
                    w.hit_ids.add(id(e))
                    self.particles.burst(e.pos(), 5, (150, 220, 255), speed=10)
                    if e.take_damage(w.DAMAGE):
                        e.alive = False
                        self.on_kill(e)
            for b in self.enemy_bullets:
                if b.alive and w.covers(b.pos()):
                    b.alive = False
                    self.particles.burst(b.pos(), 2, (170, 220, 255), speed=5, size=5)
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

    def use_bomb(self):
        if self.bombs <= 0 or self.state != self.STATE_PLAY or self.bomb_cd > 0:
            return
        self.bombs -= 1
        self.bomb_cd = 45
        self.flash = 150
        self.shake = 15
        self.freeze = 4
        for b in self.enemy_bullets:
            self.particles.burst(b.pos(), 2, (255, 200, 120), speed=6)
        self.enemy_bullets.clear()
        for e in list(self.enemies):
            if e.take_damage(8):
                e.alive = False
                self.on_kill(e)
        if self.boss:
            self.boss.take_damage(12)
        if self.snd_explode:
            self.snd_explode.play()
        self.texts.append(FloatText3D((CX, CY + 120), "BOMB!", PURPLE, self.font_m))

    def shoot(self):
        """依目前裝備的武器分派。每把武器有自己的冷卻、彈藥與彈道。"""
        s = self.ship
        if s.cooldown > 0:
            return
        wid = s.weapon
        spec = WEAPONS[wid]
        level = s.arsenal[wid]["level"]
        ports = s.gun_ports()
        mid = tuple((ports[0][i] + ports[1][i]) / 2 for i in range(3))

        if wid == "LASER":
            self.fire_laser(level)
            return

        if not s.consume():
            return
        s.cooldown = spec["cd_lv"][level - 1]
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

        elif wid == "RAIL":
            self.rails.append(Rail3D(mid[0], mid[1], mid[2], level, dmg))
            self.shake = max(self.shake, 6)

        self.particles.burst((s.x, s.y, s.z + 30), 2, spec["color"], speed=4, size=5)
        if self.snd_shoot:
            self.snd_shoot.play()

    def fire_laser(self, level):
        """
        雷射是持續光束，不是發射物：每幀直接判定「以戰機為軸心的圓柱」內有誰。
        彈藥按幀數消耗，所以 HUD 上的數字等於還能射幾幀。
        """
        s = self.ship
        if not s.consume():
            self.laser_on = 0
            return
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
                if self.state == self.STATE_PLAY:
                    if e.key == pygame.K_q:
                        self.ship.switch(-1)
                    elif e.key == pygame.K_e:
                        self.ship.switch(1)
                    else:
                        for wid, spec in WEAPONS.items():
                            if e.key == spec["key"]:
                                self.ship.select(wid)
                                break
                if e.key in (pygame.K_SPACE, pygame.K_RETURN) and self.state == self.STATE_TITLE:
                    self.state = self.STATE_PLAY
                    self.reset()
                    self.play_music()
                if e.key == pygame.K_r and self.state == self.STATE_OVER:
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
    def update_play(self):
        if self.freeze > 0:
            self.freeze -= 1
            return

        keys = pygame.key.get_pressed()
        s = self.ship
        if s.update(keys, self.particles, self.terrain):
            self.shake = max(self.shake, 11)

        # 炸彈與衝擊波：輪詢按鍵狀態（不是靠 KEYDOWN 事件），並各給多組替代鍵。
        # 原因：同時按住空白鍵與方向鍵時，很多鍵盤會漏掉第 4 顆鍵的事件（重影）。
        # 但輪詢要配合「邊緣觸發」——只在按下的那一幀算數，
        # 否則按著不放會在幾秒內把存量全部燒光。
        bomb_key = (keys[pygame.K_x] or keys[pygame.K_b]
                    or keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL])
        shock_key = (keys[pygame.K_k] or keys[pygame.K_v] or keys[pygame.K_LSHIFT]
                     or keys[pygame.K_RSHIFT] or keys[pygame.K_RETURN])
        if bomb_key and not self.prev_bomb_key:
            self.use_bomb()
        if shock_key and not self.prev_shock_key:
            self.use_shockwave()
        self.prev_bomb_key = bomb_key
        self.prev_shock_key = shock_key

        if keys[pygame.K_SPACE]:
            self.shoot()

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
            self.boss = Boss3D(self.img_boss, self.wave)
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
                        b.take_damage(bl.dmg)
                        self.particles.burst(bl.pos(), 2, (255, 220, 150), speed=5)
                for m in self.missiles:
                    if m.alive and self.hit3d(m.pos(), m.radius, b.pos(), b.radius):
                        m.alive = False
                        b.take_damage(m.dmg)
                        self.boom(m.pos())
                if b.hp <= 0:
                    b.dying = True
                    b.death_timer = 80
                    self.enemy_bullets.clear()
                if self.hit3d((s.x, s.y, s.z), s.radius, b.pos(), b.radius * 0.7):
                    if s.hit(b.damage):
                        self.shake = max(self.shake, 10)
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

        if not self.is_boss_wave() and self.kills >= self.kills_needed:
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
            label = s.add_weapon(pu.wid)
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
        self.powerups.append(WeaponPack3D(
            (self.ship.x + random.uniform(-120, 120), self.ship.y - 60,
             self.ship.z + ahead), wid))

    def next_wave(self):
        self.kills = 0
        self.wave += 1
        self.grant_weapon()
        self.kills_needed = 8 + self.wave * 2
        self.boss_spawned = False
        if not self.is_boss_wave():
            self.texts.append(FloatText3D((CX, CY - 40), f"WAVE {self.wave}",
                                          CYAN, self.font_l, life=80, rise=0.5))

    # ---------- HUD ----------
    def draw_reticle(self, surf):
        """兩層準星：顯示彈道在遠近兩個深度的落點，是 3D 射擊瞄準的關鍵。"""
        s = self.ship
        for dz, r, col in ((520, 26, (120, 230, 255)), (1500, 14, (90, 180, 210))):
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
        """右下深度雷達：縱軸是距離，讓玩家掌握還有多少敵人在逼近。"""
        w, h = 150, 110
        x0, y0 = SCREEN_W - w - 18, SCREEN_H - h - 18
        pygame.draw.rect(surf, (10, 16, 30), (x0, y0, w, h), border_radius=6)
        pygame.draw.rect(surf, (60, 90, 140), (x0, y0, w, h), 1, border_radius=6)
        pygame.draw.line(surf, (40, 60, 90), (x0 + w // 2, y0), (x0 + w // 2, y0 + h), 1)
        for e in self.enemies:
            t = max(0.0, min(1.0, (e.z - NEAR) / (SPAWN_Z - NEAR)))
            ex = x0 + w // 2 + (e.x / 800) * (w // 2 - 6)
            ey = y0 + h - 8 - t * (h - 16)
            pygame.draw.circle(surf, e.cfg["color"], (int(ex), int(ey)), 3)
        if self.boss:
            t = max(0.0, min(1.0, (self.boss.z - NEAR) / (SPAWN_Z - NEAR)))
            pygame.draw.circle(surf, PINK,
                               (int(x0 + w // 2 + (self.boss.x / 800) * (w // 2 - 6)),
                                int(y0 + h - 8 - t * (h - 16))), 6)
        # 玩家
        pygame.draw.polygon(surf, CYAN,
                            [(x0 + w // 2, y0 + h - 4), (x0 + w // 2 - 5, y0 + h - 1),
                             (x0 + w // 2 + 5, y0 + h - 1)])
        lab = self.font_s.render("DEPTH", True, GREY)
        surf.blit(lab, (x0 + 4, y0 + 2))

    def draw_hud(self, surf):
        s = self.ship
        bar_w, bar_h = 220, 16
        x, y = 16, 16
        ratio = max(0, s.hp / s.max_hp)
        pygame.draw.rect(surf, (20, 25, 40), (x - 2, y - 2, bar_w + 4, bar_h + 4), border_radius=4)
        pygame.draw.rect(surf, (55, 20, 25), (x, y, bar_w, bar_h), border_radius=3)
        col = GREEN if ratio > 0.5 else (YELLOW if ratio > 0.25 else RED)
        pygame.draw.rect(surf, col, (x, y, int(bar_w * ratio), bar_h), border_radius=3)
        surf.blit(self.font_s.render(f"HULL {max(0, int(s.hp))}", True, WHITE), (x + 6, y + 21))

        for i in range(s.lives):
            cx, cy = x + 6 + i * 22, y + 52
            pygame.draw.polygon(surf, CYAN, [(cx, cy - 7), (cx - 7, cy + 7), (cx + 7, cy + 7)])
        for i in range(self.bombs):
            cx, cy = x + 6 + i * 22, y + 76
            pygame.draw.polygon(surf, PURPLE,
                                [(cx, cy - 8), (cx + 7, cy), (cx, cy + 8), (cx - 7, cy)])
        # 衝擊波大絕：用同心弧表示，跟炸彈的菱形一眼可分辨
        for i in range(self.shock_charges):
            cx, cy = x + 8 + i * 20, y + 98
            ready = self.shock_cd == 0
            col = CYAN if ready else (70, 110, 130)
            pygame.draw.circle(surf, col, (cx, cy), 8, 2)
            pygame.draw.circle(surf, col, (cx, cy), 4, 1)
        klabel = self.font_s.render("K", True, GREY if self.shock_cd else CYAN)
        surf.blit(klabel, (x + 8 + self.shock_charges * 20 + 2, y + 90))
        # 武器庫：目前裝備的高亮，其餘暗示可切換；有彈藥條的表示會耗盡
        wy = y + 118
        panel_h = len(s.owned()) * 22 + 8
        panel = pygame.Surface((182, panel_h), pygame.SRCALPHA)
        panel.fill((8, 12, 26, 165))
        surf.blit(panel, (x - 4, wy - 7))
        for wid in s.owned():
            spec = WEAPONS[wid]
            slot = s.arsenal[wid]
            cur = (wid == s.weapon)
            col = spec["color"] if cur else tuple(c // 3 + 30 for c in spec["color"])
            if cur:
                pygame.draw.rect(surf, (30, 40, 62), (x, wy - 3, 176, 22), border_radius=4)
                pygame.draw.rect(surf, spec["color"], (x, wy - 3, 3, 22))
            idx = WEAPON_ORDER.index(wid) + 1
            surf.blit(self.font_s.render(f"{idx}", True, GREY), (x + 8, wy))
            lv = "I" * slot["level"]
            surf.blit(self.font_s.render(f"{spec['label']} {lv}", True, col), (x + 24, wy))
            if slot["ammo"] is not None:
                full = WEAPONS[wid]["ammo"] * 2
                r = max(0.0, min(1.0, slot["ammo"] / full))
                pygame.draw.rect(surf, (40, 44, 60), (x + 120, wy + 5, 50, 5))
                pygame.draw.rect(surf, col, (x + 120, wy + 5, int(50 * r), 5))
            wy += 22

        s1 = self.font_m.render(f"SCORE  {self.score}", True, WHITE)
        s2 = self.font_m.render(f"WAVE  {self.wave}", True, CYAN)
        s3 = self.font_s.render(f"BEST  {max(self.high_score, self.score)}", True, GREY)
        surf.blit(s1, (SCREEN_W - s1.get_width() - 18, 16))
        surf.blit(s2, (SCREEN_W - s2.get_width() - 18, 50))
        surf.blit(s3, (SCREEN_W - s3.get_width() - 18, 82))

        if self.combo > 1:
            mult = min(5, 1 + self.combo // 4)
            c = self.font_m.render(f"COMBO {self.combo}  x{mult}", True, ORANGE)
            surf.blit(c, (SCREEN_W - c.get_width() - 18, 112))

        if not self.is_boss_wave():
            prog = self.kills / self.kills_needed
            pw = 160
            pygame.draw.rect(surf, (35, 40, 60), (SCREEN_W - pw - 18, 144, pw, 5), border_radius=3)
            pygame.draw.rect(surf, PURPLE,
                             (SCREEN_W - pw - 18, 144, int(pw * min(1, prog)), 5), border_radius=3)

        if self.boss:
            bw = 440
            bx, by = SCREEN_W // 2 - bw // 2, 14
            r = max(0, self.boss.hp / self.boss.max_hp)
            pygame.draw.rect(surf, (25, 15, 30), (bx - 3, by - 3, bw + 6, 20), border_radius=5)
            pygame.draw.rect(surf, (70, 20, 40), (bx, by, bw, 14), border_radius=4)
            pygame.draw.rect(surf, (255, 80, 130), (bx, by, int(bw * r), 14), border_radius=4)
            n = self.font_s.render("MOTHERSHIP", True, PINK)
            surf.blit(n, (SCREEN_W // 2 - n.get_width() // 2, by + 18))

        if self.ship.ground_warn and self.state == self.STATE_PLAY:
            if (pygame.time.get_ticks() // 220) % 2 == 0:
                w = self.font_m.render("PULL UP", True, RED)
                surf.blit(w, (SCREEN_W // 2 - w.get_width() // 2, SCREEN_H - 92))

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

    # ---------- 繪製（畫家演算法：全部依 z 由遠而近） ----------
    def draw(self):
        c = self.canvas
        c.blit(self.sky, (0, 0))
        self.stars.draw(c, self.world_speed)
        self.terrain.draw(c)

        # 收集所有 3D 物件，依深度排序
        items = []
        for e in self.enemies:
            items.append((e.z, "enemy", e))
        for b in self.bullets:
            items.append((b.z, "obj", b))
        for m in self.missiles:
            items.append((m.z, "obj", m))
        for b in self.plasmas:
            items.append((b.z, "obj", b))
        for b in self.rails:
            items.append((b.z, "obj", b))
        for w in self.shockwaves:
            items.append((w.z, "obj", w))
        for b in self.enemy_bullets:
            items.append((b.z, "obj", b))
        for pu in self.powerups:
            items.append((pu.z, "obj", pu))
        for ex in self.explosions:
            items.append((ex.z, "obj", ex))
        if self.boss:
            items.append((self.boss.z, "obj", self.boss))
        self.particles.collect(items)
        items.sort(key=lambda t: -t[0])

        ship_z = self.ship.z
        ship_drawn = False
        for z, kind, obj in items:
            # 戰機插在正確的深度位置
            if not ship_drawn and z < ship_z:
                if self.state != self.STATE_OVER:
                    self.ship.draw(c)
                ship_drawn = True

            if kind == "particle":
                x, y, pz, t, color, size = obj
                p = project(x, y, pz)
                if p:
                    r = max(1, int(size * p[2] * t * 2.4))
                    blit_glow(c, (int(p[0]), int(p[1])), r * 2,
                              tuple(int(v * t) for v in color))
                continue

            p = project(*obj.pos())
            if p:
                obj.draw(c, p)

        if not ship_drawn and self.state != self.STATE_OVER:
            self.ship.draw(c)

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

        if self.state == self.STATE_TITLE:
            self.draw_panel(c, [
                ("ALIEN SHOOTER 3D", self.font_xl, CYAN, 58),
                ("Arrows / WASD to fly    SPACE fire    X bomb    K shockwave", self.font_m, WHITE, 32),
                ("1-6 or Q/E to switch weapons - collect hex packs to arm them", self.font_s, GREY, 26),
                ("6 weapons: pulse, spread, laser, homing, plasma, rail", self.font_s, GREY, 26),
                ("P pause    F fps    ESC quit", self.font_s, GREY, 46),
                ("PRESS SPACE TO START", self.font_l, YELLOW, 0),
            ])
        elif self.state == self.STATE_PAUSE:
            self.draw_panel(c, [("PAUSED", self.font_xl, WHITE, 56),
                                ("Press P to resume", self.font_m, GREY, 0)])
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
    def run(self):
        running = True
        while running:
            self.clock.tick(FPS)
            running = self.handle_events()

            if self.state == self.STATE_PLAY:
                self.update_play()
            elif self.state == self.STATE_TITLE:
                self.stars.update(14)
                self.terrain.update(14)
            elif self.state == self.STATE_OVER:
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
                    self.stop_music()
                    if self.snd_over:
                        self.snd_over.play()
                    if self.score > self.high_score:
                        self.high_score = self.score
                        self.save_high_score()

            self.draw()

        self.stop_music()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()
