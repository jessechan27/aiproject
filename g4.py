"""
================================================================
 ALIEN SHOOTER DX  -  太空船射擊遊戲（優化版）
================================================================
 素材放在跟這個 .py 同一個資料夾即可（大小寫不拘）：
   jet.png              太空船
   E1.png ~ E4.png      四種外星生物
   explosion_graph.jpg  爆炸連續圖（3x3，共 9 格）
   shoot.wav            射擊音效
   explosion.mp3        爆炸音效
   background.mp3       背景音樂
   gameover.mp3         遊戲結束音樂

 操作：
   方向鍵 / WASD   移動
   空白鍵           射擊（按住連射）
   X 或 B          炸彈（清空敵彈、全場傷害）
   P               暫停        F  顯示FPS
   R               遊戲結束後重新開始
   ESC             離開

 系統特色：
   - 連擊倍率：連續擊殺不中斷，分數最高 x5
   - 每 5 波出現 BOSS 母艦（三階段彈幕）
   - 火力三段升級；滿火力再吃 P 會發射追蹤飛彈
   - 道具：P 火力 / + 補血 / S 護盾 / B 炸彈
   - 敵人出現前有紅色預警標記，偶爾以編隊進場

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
SCREEN_W, SCREEN_H = 900, 700
FPS = 60

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

# 素材資料夾 = 程式所在資料夾（不論從哪裡執行 python 都找得到）
if getattr(sys, "frozen", False):
    ASSET_DIR = os.path.dirname(sys.executable)
else:
    ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------
def find_asset(*candidates):
    """在素材資料夾裡尋找檔案，忽略大小寫與底線/空白差異。找不到回傳 None。"""
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


def load_image(candidates, size=None, fallback_color=None, fallback_size=(40, 40)):
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
    surf = pygame.Surface(size or fallback_size, pygame.SRCALPHA)
    surf.fill(fallback_color or GREY)
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
    """
    explosion_graph.jpg 是 3x3 的爆炸連續圖（左到右、上到下 = 時間順序）。
    JPG 沒有透明度，所以先把深色底「減掉」，繪製時用加亮模式疊上去，
    火光就會自然融進夜空，不會出現方形邊框。
    """
    sheet = pygame.image.load(path).convert()
    sw, sh = sheet.get_size()
    fw, fh = sw // 3, sh // 3
    bg = sheet.get_at((2, 2))[:3]

    frames = []
    for row in range(3):
        for col in range(3):
            rect = pygame.Rect(col * fw, row * fh, fw, fh)
            frame = sheet.subsurface(rect).copy()
            frame = pygame.transform.smoothscale(frame, (frame_size, frame_size))
            frame.fill((*bg, 0), special_flags=pygame.BLEND_RGB_SUB)
            frames.append(frame)
    return frames


_GLOW_CACHE = {}


def glow(radius, color):
    """
    產生一張中心亮、往外漸暗的光暈圖並快取。
    用 BLEND_RGB_ADD 疊到畫面上就是發光效果（黑色部分等於不存在）。
    """
    radius = max(2, int(radius))
    key = (radius, color)
    cached = _GLOW_CACHE.get(key)
    if cached:
        return cached
    surf = pygame.Surface((radius * 2, radius * 2))
    for i in range(radius, 0, -1):
        t = 1 - i / radius
        c = (int(color[0] * t * t), int(color[1] * t * t), int(color[2] * t * t))
        pygame.draw.circle(surf, c, (radius, radius), i)
    _GLOW_CACHE[key] = surf
    return surf


def blit_glow(surf, center, radius, color):
    g = glow(radius, color)
    surf.blit(g, (center[0] - g.get_width() // 2, center[1] - g.get_height() // 2),
              special_flags=pygame.BLEND_RGB_ADD)


# ---------------------------------------------------------------
# 粒子系統（火花、碎片、尾焰、煙霧全靠它）
# ---------------------------------------------------------------
class ParticleSystem:
    MAX = 480          # 粒子上限，保護效能

    def __init__(self):
        self.parts = []

    def emit(self, x, y, vx, vy, life, color, size, grav=0.0, additive=False, drag=1.0):
        if len(self.parts) >= self.MAX:
            return
        self.parts.append([x, y, vx, vy, life, life, color, size, grav, additive, drag])

    # ---- 常用效果 ----
    def sparks(self, center, n, color, speed=5.0, life=(14, 30)):
        """向四面八方噴射的亮火花。"""
        for _ in range(n):
            a = random.uniform(0, math.tau)
            s = random.uniform(speed * 0.3, speed)
            self.emit(center[0], center[1],
                      math.cos(a) * s, math.sin(a) * s,
                      random.randint(*life), color,
                      random.uniform(2, 4), additive=True, drag=0.94)

    def debris(self, center, n, color):
        """帶重力的碎片。"""
        for _ in range(n):
            a = random.uniform(0, math.tau)
            s = random.uniform(1.5, 5.5)
            self.emit(center[0], center[1],
                      math.cos(a) * s, math.sin(a) * s - 1.5,
                      random.randint(24, 46), color,
                      random.uniform(2, 4), grav=0.12, drag=0.985)

    def update(self):
        parts = self.parts
        for p in parts:
            p[0] += p[2]
            p[1] += p[3]
            p[2] *= p[10]
            p[3] = p[3] * p[10] + p[8]
            p[4] -= 1
        self.parts = [p for p in parts if p[4] > 0]

    def draw(self, surf):
        for x, y, _vx, _vy, life, max_life, color, size, _g, additive, _d in self.parts:
            t = life / max_life
            r = max(1, int(size * t))
            if additive:
                blit_glow(surf, (int(x), int(y)), r * 2, color)
            else:
                c = (int(color[0] * t), int(color[1] * t), int(color[2] * t))
                pygame.draw.circle(surf, c, (int(x), int(y)), r)


# ---------------------------------------------------------------
# 背景（外星球高空）
# ---------------------------------------------------------------
class Background:
    """
    1. 固定漸層天空 + 環狀行星 + 星雲（畫一次重複使用）
    2. 三層視差星點
    3. 兩層半透明雲氣帶緩慢下捲
    4. 偶爾劃過的流星
    """

    def __init__(self):
        self.sky = self._make_sky()
        self.stars = []
        for layer, (count, speed, size) in enumerate([(70, 0.35, 1), (45, 0.8, 2), (22, 1.6, 2)]):
            for _ in range(count):
                self.stars.append({
                    "x": random.uniform(0, SCREEN_W),
                    "y": random.uniform(0, SCREEN_H),
                    "spd": speed, "r": size, "b": 90 + layer * 60,
                })
        self.cloud_a = self._make_cloud_band(alpha=26, color=(150, 90, 200))
        self.cloud_b = self._make_cloud_band(alpha=20, color=(70, 130, 200))
        self.off_a = 0.0
        self.off_b = 0.0
        self.comets = []
        self.comet_timer = random.randint(200, 420)

    def _make_sky(self):
        sky = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
        top, bottom = (26, 10, 44), (12, 20, 52)
        for y in range(SCREEN_H):
            t = y / SCREEN_H
            col = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            pygame.draw.line(sky, col, (0, y), (SCREEN_W, y))

        neb = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        for _ in range(16):
            cx, cy = random.randint(0, SCREEN_W), random.randint(0, SCREEN_H)
            rad = random.randint(70, 190)
            col = random.choice([(150, 60, 190), (60, 90, 200), (190, 70, 120)])
            for i in range(rad, 0, -14):
                pygame.draw.circle(neb, (*col, int(7 * (1 - i / rad))), (cx, cy), i)
        sky.blit(neb, (0, 0))

        # 遠方環狀行星
        px, py, pr = 150, 130, 95
        planet = pygame.Surface((pr * 2 + 60, pr * 2 + 60), pygame.SRCALPHA)
        c = (pr + 30, pr + 30)
        for i in range(pr, 0, -1):
            t = i / pr
            col = (int(90 + 90 * (1 - t)), int(40 + 60 * (1 - t)), int(110 + 70 * (1 - t)))
            pygame.draw.circle(planet, col, c, i)
        ring = pygame.Surface((pr * 3, pr * 3), pygame.SRCALPHA)
        pygame.draw.ellipse(ring, (200, 170, 220, 55), (0, pr * 1.15, pr * 3, pr * 0.7), 9)
        ring = pygame.transform.rotate(ring, 18)
        planet.blit(ring, (c[0] - ring.get_width() // 2, c[1] - ring.get_height() // 2))
        sky.blit(planet, (px - c[0], py - c[1]))
        return sky

    def _make_cloud_band(self, alpha, color):
        band = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        for _ in range(26):
            cx, cy = random.randint(0, SCREEN_W), random.randint(0, SCREEN_H)
            rad = random.randint(60, 150)
            for i in range(rad, 0, -12):
                a = int(alpha * (1 - i / rad))
                for dy in (-SCREEN_H, 0, SCREEN_H):
                    pygame.draw.circle(band, (*color, a), (cx, cy + dy), i)
        return band

    def update(self, speed_scale=1.0):
        for s in self.stars:
            s["y"] += s["spd"] * speed_scale
            if s["y"] > SCREEN_H:
                s["y"] = -2
                s["x"] = random.uniform(0, SCREEN_W)
        self.off_a = (self.off_a + 0.25 * speed_scale) % SCREEN_H
        self.off_b = (self.off_b + 0.55 * speed_scale) % SCREEN_H

        # 流星
        self.comet_timer -= 1
        if self.comet_timer <= 0:
            self.comet_timer = random.randint(260, 560)
            self.comets.append({
                "x": random.uniform(SCREEN_W * 0.2, SCREEN_W),
                "y": random.uniform(-20, SCREEN_H * 0.3),
                "vx": random.uniform(-7, -4.5),
                "vy": random.uniform(2.5, 4.0),
                "life": 55,
            })
        for cm in self.comets:
            cm["x"] += cm["vx"]
            cm["y"] += cm["vy"]
            cm["life"] -= 1
        self.comets = [c for c in self.comets if c["life"] > 0]

    def draw(self, surf):
        surf.blit(self.sky, (0, 0))
        surf.blit(self.cloud_a, (0, self.off_a - SCREEN_H))
        surf.blit(self.cloud_a, (0, self.off_a))
        for s in self.stars:
            b = s["b"]
            pygame.draw.circle(surf, (b, b, min(255, b + 40)), (int(s["x"]), int(s["y"])), s["r"])
        for cm in self.comets:
            t = cm["life"] / 55
            tail = (cm["x"] - cm["vx"] * 6, cm["y"] - cm["vy"] * 6)
            pygame.draw.line(surf, (int(180 * t), int(200 * t), int(255 * t)),
                             tail, (cm["x"], cm["y"]), 2)
            blit_glow(surf, (int(cm["x"]), int(cm["y"])), 6, (150, 180, 255))
        surf.blit(self.cloud_b, (0, self.off_b - SCREEN_H))
        surf.blit(self.cloud_b, (0, self.off_b))


# ---------------------------------------------------------------
# 玩家
# ---------------------------------------------------------------
class Player(pygame.sprite.Sprite):
    SPEED = 6.4
    MAX_TILT = 16          # 左右移動時機身傾斜角度

    def __init__(self, image):
        super().__init__()
        self.base_image = image
        # 預先做好各角度的傾斜圖，遊戲中直接查表，不用即時旋轉
        self.tilt_images = {
            a: pygame.transform.rotozoom(image, -a, 1.0)
            for a in range(-self.MAX_TILT, self.MAX_TILT + 1, 4)
        }
        self.tilt = 0.0
        self.image = image
        self.rect = self.image.get_rect(center=(SCREEN_W // 2, SCREEN_H - 90))
        self.mask = pygame.mask.from_surface(image)
        self.pos = pygame.Vector2(self.rect.center)

        self.max_hp = 100
        self.hp = self.max_hp
        self.lives = 3
        self.power = 1              # 火力 1~3；滿火力再吃 P -> 追蹤飛彈
        self.missiles_on = False
        self.shield = 0
        self.invincible = 0
        self.cooldown = 0
        self.missile_cd = 0
        self.engine_phase = 0.0

    def update(self, keys, particles):
        vx = vy = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            vx -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            vx += 1
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            vy -= 1
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            vy += 1

        if vx or vy:
            v = pygame.Vector2(vx, vy).normalize() * self.SPEED
            self.pos += v

        self.pos.x = max(self.rect.width / 2, min(SCREEN_W - self.rect.width / 2, self.pos.x))
        self.pos.y = max(SCREEN_H * 0.35, min(SCREEN_H - self.rect.height / 2 - 8, self.pos.y))

        # 機身傾斜：往目標角度平滑靠近，再取最接近的預算圖
        target = vx * self.MAX_TILT
        self.tilt += (target - self.tilt) * 0.25
        snapped = round(self.tilt / 4) * 4
        snapped = max(-self.MAX_TILT, min(self.MAX_TILT, snapped))
        self.image = self.tilt_images[snapped]
        self.rect = self.image.get_rect(center=(round(self.pos.x), round(self.pos.y)))

        if self.cooldown > 0:
            self.cooldown -= 1
        if self.missile_cd > 0:
            self.missile_cd -= 1
        if self.shield > 0:
            self.shield -= 1
        if self.invincible > 0:
            self.invincible -= 1
        self.engine_phase += 0.4

        # 引擎尾焰粒子
        if random.random() < 0.9:
            particles.emit(
                self.rect.centerx + random.uniform(-6, 6), self.rect.bottom - 2,
                random.uniform(-0.4, 0.4), random.uniform(2.0, 3.4),
                random.randint(8, 16), (90, 190, 255), random.uniform(1.5, 3),
                additive=True, drag=0.92,
            )

    def shoot(self, game):
        if self.cooldown > 0:
            return
        self.cooldown = 9 if self.power < 3 else 7

        if self.power == 1:
            specs = [(0, -13, 0)]
        elif self.power == 2:
            specs = [(-11, -13, 0), (11, -13, 0)]
        else:
            specs = [(-15, -12.5, -2.2), (0, -14, 0), (15, -12.5, 2.2)]

        for dx, sy, sx in specs:
            b = PlayerBullet(self.rect.centerx + dx, self.rect.top + 6, sx, sy)
            game.bullets.add(b)
        # 槍口閃光
        game.particles.sparks((self.rect.centerx, self.rect.top + 2), 2,
                              (170, 230, 255), speed=2.5, life=(4, 8))
        if game.snd_shoot:
            game.snd_shoot.play()

        # 滿火力 + 飛彈模組：週期性補射兩發追蹤彈
        if self.missiles_on and self.missile_cd <= 0:
            self.missile_cd = 26
            for side in (-1, 1):
                game.missiles.add(Missile(self.rect.centerx + side * 20,
                                          self.rect.centery, side))

    def hit(self, damage):
        """回傳 True 表示真的扣到血。"""
        if self.invincible > 0:
            return False
        if self.shield > 0:
            self.shield = 0
            self.invincible = 40
            return False
        self.hp -= damage
        self.invincible = 55
        return True

    def draw_engine(self, surf):
        flicker = 8 + 5 * math.sin(self.engine_phase) + random.uniform(-2, 2)
        cx, by = self.rect.centerx, self.rect.bottom - 4
        for off in (-9, 9):
            pygame.draw.polygon(surf, (120, 200, 255),
                                [(cx + off - 4, by), (cx + off + 4, by), (cx + off, by + flicker)])
        pygame.draw.polygon(surf, (255, 240, 200),
                            [(cx - 3, by), (cx + 3, by), (cx, by + flicker * 0.6)])

    def draw(self, surf):
        if self.invincible > 0 and (self.invincible // 4) % 2 == 0:
            return
        self.draw_engine(surf)
        surf.blit(self.image, self.rect)
        if self.shield > 0:
            r = max(self.rect.width, self.rect.height) // 2 + 12
            alpha = 90 + int(60 * math.sin(pygame.time.get_ticks() * 0.01))
            sh = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(sh, (110, 220, 255, alpha), (r, r), r, 3)
            surf.blit(sh, (self.rect.centerx - r, self.rect.centery - r))


# ---------------------------------------------------------------
# 各種彈藥
# ---------------------------------------------------------------
class PlayerBullet(pygame.sprite.Sprite):
    def __init__(self, x, y, vx, vy):
        super().__init__()
        self.image = pygame.Surface((6, 18), pygame.SRCALPHA)
        pygame.draw.ellipse(self.image, (180, 240, 255), (0, 0, 6, 18))
        pygame.draw.ellipse(self.image, WHITE, (2, 3, 2, 12))
        self.rect = self.image.get_rect(center=(x, y))
        self.mask = pygame.mask.from_surface(self.image)
        self.v = pygame.Vector2(vx, vy)
        self.pos = pygame.Vector2(self.rect.center)

    def update(self, *_):
        self.pos += self.v
        self.rect.center = (round(self.pos.x), round(self.pos.y))
        if self.rect.bottom < -20:
            self.kill()

    def draw(self, surf):
        blit_glow(surf, self.rect.center, 9, (60, 120, 160))
        surf.blit(self.image, self.rect)


class Missile(pygame.sprite.Sprite):
    """追蹤飛彈：緩慢轉向最近的敵人。"""
    SPEED = 8.2
    TURN = 0.14            # 轉向靈敏度（0~1）

    def __init__(self, x, y, side):
        super().__init__()
        self.base = pygame.Surface((12, 22), pygame.SRCALPHA)
        pygame.draw.polygon(self.base, ORANGE, [(6, 0), (11, 16), (6, 13), (1, 16)])
        pygame.draw.polygon(self.base, YELLOW, [(6, 3), (9, 13), (6, 11), (3, 13)])
        self.image = self.base
        self.rect = self.image.get_rect(center=(x, y))
        self.mask = pygame.mask.from_surface(self.image)
        self.pos = pygame.Vector2(x, y)
        self.v = pygame.Vector2(side * 3.2, -6.0)
        self.life = 150

    def update(self, target, particles):
        if target is not None:
            desired = pygame.Vector2(target.rect.center) - self.pos
            if desired.length_squared() > 1:
                desired = desired.normalize() * self.SPEED
                self.v = self.v.lerp(desired, self.TURN)
        if self.v.length_squared() > 0:
            self.v.scale_to_length(self.SPEED)
        self.pos += self.v

        # 依飛行方向旋轉外觀
        ang = math.degrees(math.atan2(self.v.x, -self.v.y))
        self.image = pygame.transform.rotozoom(self.base, -ang, 1.0)
        self.rect = self.image.get_rect(center=(round(self.pos.x), round(self.pos.y)))
        self.mask = pygame.mask.from_surface(self.image)

        # 尾煙
        particles.emit(self.pos.x, self.pos.y, -self.v.x * 0.1, -self.v.y * 0.1,
                       random.randint(8, 14), (255, 170, 80), 2.2, additive=True, drag=0.9)

        self.life -= 1
        if self.life <= 0 or not (-40 < self.pos.x < SCREEN_W + 40 and -60 < self.pos.y < SCREEN_H + 40):
            self.kill()


class EnemyBullet(pygame.sprite.Sprite):
    def __init__(self, x, y, vx, vy, color=(255, 120, 90)):
        super().__init__()
        self.color = color
        self.image = pygame.Surface((14, 14), pygame.SRCALPHA)
        pygame.draw.circle(self.image, (*color, 90), (7, 7), 7)
        pygame.draw.circle(self.image, color, (7, 7), 5)
        pygame.draw.circle(self.image, WHITE, (7, 7), 2)
        self.rect = self.image.get_rect(center=(x, y))
        self.mask = pygame.mask.from_surface(self.image)
        self.v = pygame.Vector2(vx, vy)
        self.pos = pygame.Vector2(self.rect.center)

    def update(self, *_):
        self.pos += self.v
        self.rect.center = (round(self.pos.x), round(self.pos.y))
        if (self.rect.top > SCREEN_H + 30 or self.rect.bottom < -30
                or self.rect.right < -30 or self.rect.left > SCREEN_W + 30):
            self.kill()

    def draw(self, surf):
        blit_glow(surf, self.rect.center, 10, tuple(c // 3 for c in self.color))
        surf.blit(self.image, self.rect)


# ---------------------------------------------------------------
# 敵人
# ---------------------------------------------------------------
# 注意：依照素材實際內容，E3.png 是飛碟（精英）、E4.png 是深藍獵人怪
ENEMY_TYPES = {
    1: {"name": "Drifter", "size": 56, "hp": 2, "speed": (1.6, 2.6), "score": 10,
        "behavior": "drift", "shoot": 0, "damage": 12, "color": (80, 200, 180)},
    2: {"name": "Weaver", "size": 58, "hp": 3, "speed": (1.8, 2.8), "score": 20,
        "behavior": "wave", "shoot": 0.004, "damage": 14, "color": (230, 90, 70)},
    3: {"name": "Saucer", "size": 76, "hp": 9, "speed": (1.0, 1.6), "score": 60,
        "behavior": "saucer", "shoot": 0.014, "damage": 25, "color": (210, 90, 200)},
    4: {"name": "Hunter", "size": 60, "hp": 5, "speed": (1.4, 2.2), "score": 35,
        "behavior": "hunt", "shoot": 0.009, "damage": 18, "color": (60, 90, 140)},
}


class Enemy(pygame.sprite.Sprite):
    def __init__(self, etype, image, wave, x=None):
        super().__init__()
        cfg = ENEMY_TYPES[etype]
        self.etype = etype
        self.cfg = cfg
        self.image = image
        self.rect = self.image.get_rect()
        self.mask = pygame.mask.from_surface(self.image)

        self.max_hp = cfg["hp"] + wave // 3
        self.hp = self.max_hp
        self.score = cfg["score"]
        self.damage = cfg["damage"]
        self.shoot_chance = cfg["shoot"] * (1 + wave * 0.05)

        lo, hi = cfg["speed"]
        self.speed = random.uniform(lo, hi) + wave * 0.06
        if x is None:
            x = random.uniform(self.rect.width, SCREEN_W - self.rect.width)
        self.pos = pygame.Vector2(x, random.uniform(-140, -60))
        self.rect.center = self.pos
        self.phase = random.uniform(0, math.tau)
        self.amp = random.uniform(1.4, 3.0)
        self.drift = random.uniform(-1.0, 1.0)
        self.flash = 0

    def update(self, player, enemy_bullets):
        b = self.cfg["behavior"]
        if b == "drift":
            self.pos.y += self.speed
            self.pos.x += self.drift
        elif b == "wave":
            self.pos.y += self.speed
            self.phase += 0.055
            self.pos.x += math.sin(self.phase) * self.amp * 1.8
        elif b == "hunt":
            self.pos.y += self.speed * 0.85
            if player.rect.centerx > self.pos.x + 6:
                self.pos.x += 1.5
            elif player.rect.centerx < self.pos.x - 6:
                self.pos.x -= 1.5
        elif b == "saucer":
            if self.pos.y < SCREEN_H * 0.26:
                self.pos.y += self.speed
            else:
                self.phase += 0.02
                self.pos.x += math.sin(self.phase) * 2.6
                self.pos.y += math.sin(self.phase * 2) * 0.4

        self.pos.x = max(self.rect.width / 2, min(SCREEN_W - self.rect.width / 2, self.pos.x))
        self.rect.center = (round(self.pos.x), round(self.pos.y))

        if self.flash > 0:
            self.flash -= 1

        if random.random() < self.shoot_chance and self.rect.bottom > 0:
            self.fire(player, enemy_bullets)

        if self.rect.top > SCREEN_H + 40:
            self.kill()

    def fire(self, player, enemy_bullets):
        if self.cfg["behavior"] == "saucer":
            for ang in (-0.35, 0, 0.35):
                enemy_bullets.add(EnemyBullet(
                    self.rect.centerx, self.rect.bottom,
                    math.sin(ang) * 5.0, math.cos(ang) * 5.0, PINK))
        else:
            d = pygame.Vector2(player.rect.center) - pygame.Vector2(self.rect.center)
            if d.length() > 0:
                d = d.normalize() * 4.6
                enemy_bullets.add(EnemyBullet(self.rect.centerx, self.rect.bottom, d.x, d.y))

    def take_damage(self, dmg=1):
        self.hp -= dmg
        self.flash = 4
        return self.hp <= 0

    def draw(self, surf):
        surf.blit(self.image, self.rect)
        if self.flash > 0:
            surf.blit(self.image, self.rect, special_flags=pygame.BLEND_RGB_ADD)
        if self.hp < self.max_hp:
            w = self.rect.width
            ratio = max(0, self.hp / self.max_hp)
            bx, by = self.rect.left, self.rect.top - 7
            pygame.draw.rect(surf, (60, 20, 20), (bx, by, w, 4))
            pygame.draw.rect(surf, (90, 230, 120), (bx, by, int(w * ratio), 4))


# ---------------------------------------------------------------
# BOSS 母艦（每 5 波登場）
# ---------------------------------------------------------------
class Boss(pygame.sprite.Sprite):
    def __init__(self, image, wave):
        super().__init__()
        size = 190
        self.image = pygame.transform.smoothscale(image, (size, size))
        self.rect = self.image.get_rect(center=(SCREEN_W // 2, -160))
        self.mask = pygame.mask.from_surface(self.image)
        self.pos = pygame.Vector2(self.rect.center)

        tier = wave // 5                     # 第幾隻 boss
        self.max_hp = 140 + tier * 80
        self.hp = self.max_hp
        self.contact_damage = 30
        self.score = 1200 + tier * 400
        self.phase_t = 0.0
        self.timer_aim = 0
        self.timer_ring = 0
        self.flash = 0
        self.dying = False
        self.entering = True

    @property
    def stage(self):
        """依剩餘血量分三階段：1 溫和、2 加壓、3 狂暴。"""
        r = self.hp / self.max_hp
        if r > 0.66:
            return 1
        if r > 0.33:
            return 2
        return 3

    def update(self, player, enemy_bullets):
        if self.entering:
            self.pos.y += 2.2
            if self.pos.y >= 150:
                self.entering = False
        else:
            speed = {1: 0.010, 2: 0.014, 3: 0.019}[self.stage]
            self.phase_t += speed
            self.pos.x = SCREEN_W / 2 + math.sin(self.phase_t) * (SCREEN_W / 2 - 140)
            self.pos.y = 150 + math.sin(self.phase_t * 2.3) * 26

        self.rect.center = (round(self.pos.x), round(self.pos.y))
        if self.flash > 0:
            self.flash -= 1
        if self.dying or self.entering:
            return

        # --- 彈幕 ---
        st = self.stage
        self.timer_aim += 1
        self.timer_ring += 1

        aim_cd = {1: 62, 2: 50, 3: 38}[st]
        if self.timer_aim >= aim_cd:
            self.timer_aim = 0
            base = pygame.Vector2(player.rect.center) - pygame.Vector2(self.rect.center)
            base_ang = math.atan2(base.y, base.x)
            n = {1: 3, 2: 5, 3: 5}[st]
            spread = 0.24
            spd = 4.4 + st * 0.3
            for i in range(n):
                a = base_ang + (i - (n - 1) / 2) * spread
                enemy_bullets.add(EnemyBullet(
                    self.rect.centerx, self.rect.centery + 40,
                    math.cos(a) * spd, math.sin(a) * spd, PINK))

        if st >= 2:
            ring_cd = {2: 95, 3: 68}[st]
            if self.timer_ring >= ring_cd:
                self.timer_ring = 0
                n = 14 if st == 2 else 18
                offset = random.uniform(0, math.tau)
                for i in range(n):
                    a = offset + i * math.tau / n
                    enemy_bullets.add(EnemyBullet(
                        self.rect.centerx, self.rect.centery,
                        math.cos(a) * 3.3, math.sin(a) * 3.3, (255, 170, 90)))

    def take_damage(self, dmg=1):
        if self.entering or self.dying:
            return False
        self.hp -= dmg
        self.flash = 3
        return self.hp <= 0

    def draw(self, surf):
        blit_glow(surf, self.rect.center, self.rect.width // 2 + 14, (60, 20, 60))
        surf.blit(self.image, self.rect)
        if self.flash > 0:
            surf.blit(self.image, self.rect, special_flags=pygame.BLEND_RGB_ADD)


# ---------------------------------------------------------------
# 道具、飄字
# ---------------------------------------------------------------
class PowerUp(pygame.sprite.Sprite):
    KINDS = {
        "power": (YELLOW, "P"),
        "heal": (GREEN, "+"),
        "shield": (CYAN, "S"),
        "bomb": (PURPLE, "B"),
    }

    def __init__(self, center, kind):
        super().__init__()
        self.kind = kind
        color, label = self.KINDS[kind]
        self.color = color
        self.image = pygame.Surface((30, 30), pygame.SRCALPHA)
        pygame.draw.circle(self.image, (*color, 70), (15, 15), 15)
        pygame.draw.circle(self.image, color, (15, 15), 11)
        pygame.draw.circle(self.image, WHITE, (15, 15), 11, 2)
        font = pygame.font.Font(None, 22)
        txt = font.render(label, True, (20, 20, 30))
        self.image.blit(txt, txt.get_rect(center=(15, 15)))
        self.rect = self.image.get_rect(center=center)
        self.mask = pygame.mask.from_surface(self.image)
        self.pos = pygame.Vector2(self.rect.center)
        self.phase = random.uniform(0, math.tau)

    def update(self, *_):
        self.pos.y += 2.1
        self.phase += 0.08
        self.pos.x += math.sin(self.phase) * 1.2
        self.rect.center = (round(self.pos.x), round(self.pos.y))
        if self.rect.top > SCREEN_H:
            self.kill()

    def draw(self, surf):
        blit_glow(surf, self.rect.center, 16, tuple(c // 4 for c in self.color))
        surf.blit(self.image, self.rect)


class FloatingText(pygame.sprite.Sprite):
    def __init__(self, center, text, color, font, life=45, rise=1.1):
        super().__init__()
        self.image = font.render(text, True, color)
        self.rect = self.image.get_rect(center=center)
        self.pos = pygame.Vector2(self.rect.center)
        self.life = life
        self.max_life = life
        self.rise = rise

    def update(self, *_):
        self.pos.y -= self.rise
        self.rect.center = (round(self.pos.x), round(self.pos.y))
        self.life -= 1
        if self.life <= 0:
            self.kill()
        else:
            self.image.set_alpha(int(255 * min(1, self.life / (self.max_life * 0.55))))


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
            print(f"[WARN] 音效系統無法啟動：{e}（遊戲仍可進行，只是沒有聲音）")
            self.audio = False

        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Alien Shooter DX")
        self.clock = pygame.time.Clock()
        self.canvas = pygame.Surface((SCREEN_W, SCREEN_H))   # 固定畫布，方便整體震動

        self.font_s = pygame.font.Font(None, 24)
        self.font_m = pygame.font.Font(None, 34)
        self.font_l = pygame.font.Font(None, 54)
        self.font_xl = pygame.font.Font(None, 86)

        self.load_assets()
        self.background = Background()
        self.vignette = self._make_vignette()
        self.white_overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        self.white_overlay.fill((255, 245, 230))

        self.high_score = self.load_high_score()
        self.show_fps = False
        self.state = self.STATE_TITLE
        self.reset()

    # ---------- 素材 ----------
    def load_assets(self):
        print(f"\n素材資料夾：{ASSET_DIR}")
        print("載入中 ...")
        self.img_player = load_image(["jet.png", "jet.jpg"], size=(58, 55), fallback_color=GREEN)

        self.img_enemies = {}
        for i in (1, 2, 3, 4):
            sz = ENEMY_TYPES[i]["size"]
            self.img_enemies[i] = load_image(
                [f"E{i}.png", f"E{i}.jpg"], size=(sz, sz),
                fallback_color=ENEMY_TYPES[i]["color"])
        self.img_boss_src = load_image(["E3.png", "E3.jpg"], size=(200, 200),
                                       fallback_color=ENEMY_TYPES[3]["color"])

        self.frames_big = self.frames_small = None
        exp_path = find_asset("explosion_graph.jpg", "explosion graph.jpg", "explosion.png")
        if exp_path:
            try:
                self.frames_small = slice_explosion_sheet(exp_path, 90)
                self.frames_big = slice_explosion_sheet(exp_path, 160)
                print(f"  [OK]   sheet  {os.path.basename(exp_path)} -> 切成 9 格動畫")
            except pygame.error as e:
                print(f"  [FAIL] sheet  {e}")
        if self.frames_small is None:
            self.frames_small = self._fallback_frames(90)
            self.frames_big = self._fallback_frames(160)
            print("  [MISS] 爆炸圖 -> 使用程式繪製的爆炸")

        self.snd_shoot = load_sound(["shoot.wav", "shoot.mp3"], 0.22) if self.audio else None
        self.snd_explode = load_sound(["explosion.mp3", "exploresion.mp3"], 0.45) if self.audio else None
        self.snd_over = load_sound(["gameover.mp3", "game_over.mp3"], 0.6) if self.audio else None
        self.music_path = find_asset("background.mp3", "background.ogg") if self.audio else None
        if self.music_path:
            print(f"  [OK]   music  {os.path.basename(self.music_path)}")
        elif self.audio:
            print("  [MISS] music  background.mp3")
        print()

    def _fallback_frames(self, size):
        frames = []
        for i in range(9):
            t = i / 8
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            r = int(size / 2 * min(1.0, 0.25 + t * 1.2))
            fade = max(0.0, 1 - max(0.0, (t - 0.5) * 2))
            for rr, col in ((r, (200, 60, 20)), (int(r * 0.66), (255, 160, 40)),
                            (int(r * 0.35), (255, 245, 210))):
                if rr > 0:
                    pygame.draw.circle(surf, tuple(int(v * fade) for v in col),
                                       (size // 2, size // 2), rr)
            frames.append(surf)
        return frames

    def _make_vignette(self):
        """低血量時的紅色邊框警示（先畫好，遊戲中只調整透明度）。"""
        v = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        depth = 90
        for i in range(depth):
            a = int(110 * (1 - i / depth) ** 2)
            pygame.draw.rect(v, (220, 30, 30, a),
                             (i, i, SCREEN_W - 2 * i, SCREEN_H - 2 * i), 1)
        return v

    # ---------- 紀錄 / 音樂 ----------
    def load_high_score(self):
        try:
            with open(os.path.join(ASSET_DIR, "highscore.txt"), "r") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return 0

    def save_high_score(self):
        try:
            with open(os.path.join(ASSET_DIR, "highscore.txt"), "w") as f:
                f.write(str(self.high_score))
        except OSError:
            pass

    def play_music(self):
        if self.music_path:
            try:
                pygame.mixer.music.load(self.music_path)
                pygame.mixer.music.set_volume(0.32)
                pygame.mixer.music.play(-1)
            except pygame.error:
                pass

    def stop_music(self):
        if self.audio:
            pygame.mixer.music.stop()

    # ---------- 開新局 ----------
    def reset(self):
        self.enemies = pygame.sprite.Group()
        self.bullets = pygame.sprite.Group()
        self.missiles = pygame.sprite.Group()
        self.enemy_bullets = pygame.sprite.Group()
        self.explosions = pygame.sprite.Group()
        self.powerups = pygame.sprite.Group()
        self.texts = pygame.sprite.Group()
        self.particles = ParticleSystem()

        self.player = Player(self.img_player)
        self.boss = None
        self.boss_spawned_for_wave = False
        self.boss_death_timer = 0

        self.score = 0
        self.wave = 1
        self.kills = 0
        self.kills_for_next_wave = 8
        self.combo = 0
        self.combo_timer = 0
        self.max_combo = 0
        self.bombs = 2
        self.bomb_rings = []

        self.pending = []           # 排程中的敵人（含預警標記）
        self.spawn_timer = 0
        self.shake = 0.0
        self.flash = 0
        self.freeze = 0             # 擊殺瞬間的極短暫停（打擊感）
        self.over_handled = False

    # ---------- 敵人生成（先預警再出現） ----------
    def is_boss_wave(self):
        return self.wave % 5 == 0

    def schedule(self, etype, x=None, delay=42):
        if x is None:
            x = random.uniform(60, SCREEN_W - 60)
        self.pending.append({"etype": etype, "x": x, "timer": delay})

    def queue_formation(self):
        """偶爾整隊進場：V 字隊或橫排。"""
        if random.random() < 0.5:
            cx = random.randint(170, SCREEN_W - 170)
            for dx, extra in ((0, 0), (-58, 14), (58, 14), (-116, 28), (116, 28)):
                self.schedule(1, cx + dx, 42 + extra)
        else:
            y0 = random.randint(120, SCREEN_W - 120 - 3 * 70)
            for i in range(4):
                self.schedule(2, y0 + i * 70, 42 + i * 4)

    def spawn_interval(self):
        base = max(18, 52 - self.wave * 3)
        return int(base * 2.6) if self.boss else base

    def update_spawns(self):
        self.spawn_timer += 1
        if self.spawn_timer >= self.spawn_interval():
            self.spawn_timer = 0
            if self.boss:
                # BOSS 戰時只有少量小兵
                self.schedule(random.choice((1, 2)))
            elif random.random() < 0.10:
                self.queue_formation()
            else:
                w = self.wave
                # 順序對應 [E1漂移, E2蛇行, E3飛碟(稀有精英), E4獵人]
                weights = [max(1, 55 - w * 4), 30 + w, max(0, w - 1) * 2, 10 + w * 2]
                self.schedule(random.choices([1, 2, 3, 4], weights=weights)[0])

        # 倒數結束 -> 真正出現
        for p in self.pending:
            p["timer"] -= 1
            if p["timer"] <= 0:
                self.enemies.add(Enemy(p["etype"], self.img_enemies[p["etype"]],
                                       self.wave, x=p["x"]))
        self.pending = [p for p in self.pending if p["timer"] > 0]

        # BOSS 進場
        if self.is_boss_wave() and not self.boss_spawned_for_wave:
            self.boss_spawned_for_wave = True
            self.boss = Boss(self.img_boss_src, self.wave)

    # ---------- 爆炸 / 連擊 / 掉寶 ----------
    def boom(self, center, big=False):
        frames = self.frames_big if big else self.frames_small
        self.explosions.add(_Explosion(center, frames))
        if self.snd_explode:
            self.snd_explode.play()
        self.shake = max(self.shake, 9 if big else 5)
        self.particles.sparks(center, 14 if big else 8,
                              (255, 190, 90), speed=6 if big else 4.5)

    def add_score(self, base, center):
        mult = min(5, 1 + self.combo // 4)
        gained = base * mult
        self.score += gained
        label = f"+{gained}" + (f"  x{mult}" if mult > 1 else "")
        self.texts.add(FloatingText(center, label, YELLOW, self.font_s))
        return gained

    def on_kill(self, enemy):
        self.kills += 1
        self.combo += 1
        self.combo_timer = 110
        self.max_combo = max(self.max_combo, self.combo)
        self.add_score(enemy.score, enemy.rect.center)
        big = enemy.cfg["behavior"] == "saucer"
        self.boom(enemy.rect.center, big=big)
        self.particles.debris(enemy.rect.center, 10, enemy.cfg["color"])
        if big:
            self.freeze = 3
        self.maybe_drop(enemy)

    def maybe_drop(self, enemy):
        chance = {1: 0.06, 2: 0.09, 3: 0.55, 4: 0.15}[enemy.etype]
        if random.random() >= chance:
            return
        low_hp = self.player.hp < self.player.max_hp * 0.5
        pool = (["heal", "power", "shield", "bomb"], [0.45, 0.25, 0.18, 0.12]) if low_hp \
            else (["power", "shield", "heal", "bomb"], [0.4, 0.24, 0.22, 0.14])
        self.powerups.add(PowerUp(enemy.rect.center, random.choices(*pool)[0]))

    # ---------- 炸彈 ----------
    def use_bomb(self):
        if self.bombs <= 0 or self.state != self.STATE_PLAY:
            return
        self.bombs -= 1
        self.flash = 130
        self.shake = 14
        self.freeze = 4
        self.bomb_rings.append({"r": 30, "max": SCREEN_W * 0.9,
                                "cx": self.player.rect.centerx,
                                "cy": self.player.rect.centery})
        # 清空敵彈（每顆變成小火花）
        for bl in self.enemy_bullets:
            self.particles.sparks(bl.rect.center, 3, (255, 200, 120), speed=3)
        self.enemy_bullets.empty()
        # 全場傷害
        for e in list(self.enemies):
            if e.take_damage(8):
                e.kill()
                self.on_kill(e)
        if self.boss and self.boss.take_damage(12):
            pass          # 死亡流程交給 update_boss
        if self.snd_explode:
            self.snd_explode.play()
        self.texts.add(FloatingText(self.player.rect.midtop, "BOMB!", PURPLE, self.font_m))

    # ---------- 事件 ----------
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_f:
                    self.show_fps = not self.show_fps
                if event.key == pygame.K_p and self.state in (self.STATE_PLAY, self.STATE_PAUSE):
                    if self.state == self.STATE_PLAY:
                        self.state = self.STATE_PAUSE
                        if self.audio:
                            pygame.mixer.music.pause()
                    else:
                        self.state = self.STATE_PLAY
                        if self.audio:
                            pygame.mixer.music.unpause()
                if event.key in (pygame.K_x, pygame.K_b):
                    self.use_bomb()
                if event.key in (pygame.K_SPACE, pygame.K_RETURN) and self.state == self.STATE_TITLE:
                    self.state = self.STATE_PLAY
                    self.reset()
                    self.play_music()
                if event.key == pygame.K_r and self.state == self.STATE_OVER:
                    self.state = self.STATE_PLAY
                    self.reset()
                    self.play_music()
        return True

    # ---------- BOSS 流程 ----------
    def nearest_target(self, pos):
        best, bd = None, float("inf")
        candidates = list(self.enemies)
        if self.boss and not self.boss.dying:
            candidates.append(self.boss)
        for e in candidates:
            d = (pygame.Vector2(e.rect.center) - pos).length_squared()
            if d < bd:
                bd, best = d, e
        return best

    def update_boss(self):
        if not self.boss:
            return
        b = self.boss
        b.update(self.player, self.enemy_bullets)

        if not b.dying:
            # 子彈 / 飛彈打 BOSS
            hits = pygame.sprite.spritecollide(b, self.bullets, True, pygame.sprite.collide_mask)
            if hits:
                b.take_damage(len(hits))
                for h in hits:
                    self.particles.sparks(h.rect.midtop, 3, (255, 220, 150), speed=3)
            mhits = pygame.sprite.spritecollide(b, self.missiles, True, pygame.sprite.collide_mask)
            if mhits:
                b.take_damage(len(mhits) * 2)
                for h in mhits:
                    self.boom(h.rect.center)

            # 撞到玩家
            if pygame.sprite.collide_mask(b, self.player):
                if self.player.hit(b.contact_damage):
                    self.shake = max(self.shake, 8)

            if b.hp <= 0:
                b.dying = True
                self.boss_death_timer = 80
                self.enemy_bullets.empty()
        else:
            # 死亡連環爆
            self.boss_death_timer -= 1
            if self.boss_death_timer % 9 == 0:
                off = (random.uniform(-70, 70), random.uniform(-60, 60))
                self.boom((b.rect.centerx + off[0], b.rect.centery + off[1]))
            if self.boss_death_timer <= 0:
                center = b.rect.center
                self.boom(center, big=True)
                self.flash = 160
                self.freeze = 5
                self.combo += 3
                self.combo_timer = 130
                self.add_score(b.score, center)
                self.texts.add(FloatingText((SCREEN_W // 2, SCREEN_H * 0.42),
                                            "MOTHERSHIP DESTROYED!", CYAN, self.font_l,
                                            life=110, rise=0.2))
                for _ in range(3):
                    self.powerups.add(PowerUp(
                        (center[0] + random.uniform(-50, 50), center[1]),
                        random.choice(["power", "heal", "shield", "bomb"])))
                self.boss = None
                self.next_wave()

    def next_wave(self):
        self.kills = 0
        self.wave += 1
        self.kills_for_next_wave = 8 + self.wave * 2
        self.boss_spawned_for_wave = False
        if self.is_boss_wave():
            banner, col = "!! MOTHERSHIP INCOMING !!", RED
        else:
            banner, col = f"WAVE {self.wave}", CYAN
        self.texts.add(FloatingText((SCREEN_W // 2, SCREEN_H // 2 - 60),
                                    banner, col, self.font_l, life=80, rise=0.5))

    # ---------- 每一幀 ----------
    def update_play(self):
        if self.freeze > 0:            # 擊殺瞬間的定格
            self.freeze -= 1
            return

        keys = pygame.key.get_pressed()
        self.player.update(keys, self.particles)
        if keys[pygame.K_SPACE]:
            self.player.shoot(self)

        for e in self.enemies:
            e.update(self.player, self.enemy_bullets)
        self.bullets.update()
        target = self.nearest_target(pygame.Vector2(self.player.rect.center))
        for m in self.missiles:
            m.update(target, self.particles)
        self.enemy_bullets.update()
        self.explosions.update()
        self.powerups.update()
        self.texts.update()
        self.particles.update()
        self.background.update(1.0 + self.wave * 0.05)
        self.update_spawns()
        self.update_boss()

        # 連擊倒數
        if self.combo_timer > 0:
            self.combo_timer -= 1
            if self.combo_timer == 0:
                self.combo = 0

        # 炸彈衝擊波
        for ring in self.bomb_rings:
            ring["r"] += 26
        self.bomb_rings = [r for r in self.bomb_rings if r["r"] < r["max"]]

        # 我方子彈 vs 敵人
        hits = pygame.sprite.groupcollide(self.enemies, self.bullets, False, True,
                                          pygame.sprite.collide_mask)
        for enemy, bl in hits.items():
            self.particles.sparks(bl[0].rect.midtop, 2, (200, 240, 255), speed=2.5, life=(5, 10))
            if enemy.take_damage(len(bl)):
                enemy.kill()
                self.on_kill(enemy)

        # 飛彈 vs 敵人
        mh = pygame.sprite.groupcollide(self.enemies, self.missiles, False, True,
                                        pygame.sprite.collide_mask)
        for enemy, ms in mh.items():
            self.boom(ms[0].rect.center)
            if enemy.take_damage(len(ms) * 2):
                enemy.kill()
                self.on_kill(enemy)

        # 敵彈 vs 玩家
        for _ in pygame.sprite.spritecollide(self.player, self.enemy_bullets, True,
                                             pygame.sprite.collide_mask):
            if self.player.hit(14):
                self.shake = max(self.shake, 6)
                self.particles.sparks(self.player.rect.center, 6, (255, 120, 90))

        # 敵人撞玩家
        for enemy in pygame.sprite.spritecollide(self.player, self.enemies, False,
                                                 pygame.sprite.collide_mask):
            enemy.kill()
            self.boom(enemy.rect.center, big=True)
            self.player.hit(enemy.damage)

        # 撿道具
        for pu in pygame.sprite.spritecollide(self.player, self.powerups, True,
                                              pygame.sprite.collide_mask):
            self.apply_powerup(pu)

        # 血量歸零 -> 扣命 / 結束
        if self.player.hp <= 0:
            self.player.lives -= 1
            self.boom(self.player.rect.center, big=True)
            self.enemy_bullets.empty()          # 重生時清彈幕，避免落地秒死
            if self.player.lives > 0:
                self.player.hp = self.player.max_hp
                self.player.power = max(1, self.player.power - 1)
                self.player.missiles_on = False
                self.player.invincible = 130
                self.player.pos = pygame.Vector2(SCREEN_W // 2, SCREEN_H - 90)
                self.combo = 0
            else:
                self.state = self.STATE_OVER

        # 一般波：殺滿數量升波（BOSS 波由 BOSS 死亡觸發）
        if not self.is_boss_wave() and self.kills >= self.kills_for_next_wave:
            self.next_wave()

        if self.shake > 0:
            self.shake = max(0, self.shake - 0.6)
        if self.flash > 0:
            self.flash = max(0, self.flash - 9)

    def apply_powerup(self, pu):
        self.particles.sparks(pu.rect.center, 10, pu.color, speed=3.5)
        if pu.kind == "power":
            if self.player.power < 3:
                self.player.power += 1
                label = "POWER UP!"
            elif not self.player.missiles_on:
                self.player.missiles_on = True
                label = "HOMING MISSILES!"
            else:
                self.add_score(50, pu.rect.center)
                label = "MAX POWER"
        elif pu.kind == "heal":
            self.player.hp = min(self.player.max_hp, self.player.hp + 35)
            label = "+35 HP"
        elif pu.kind == "shield":
            self.player.shield = 60 * 8
            label = "SHIELD"
        else:
            self.bombs = min(3, self.bombs + 1)
            label = "+1 BOMB"
        self.texts.add(FloatingText(self.player.rect.midtop, label, pu.color, self.font_s))

    # ---------- HUD ----------
    def draw_hud(self, surf):
        # 血條
        bar_w, bar_h = 210, 16
        x, y = 16, 16
        ratio = max(0, self.player.hp / self.player.max_hp)
        pygame.draw.rect(surf, (20, 25, 40), (x - 2, y - 2, bar_w + 4, bar_h + 4), border_radius=4)
        pygame.draw.rect(surf, (55, 20, 25), (x, y, bar_w, bar_h), border_radius=3)
        col = GREEN if ratio > 0.5 else (YELLOW if ratio > 0.25 else RED)
        pygame.draw.rect(surf, col, (x, y, int(bar_w * ratio), bar_h), border_radius=3)
        surf.blit(self.font_s.render(f"HULL {max(0, int(self.player.hp))}", True, WHITE),
                  (x + 6, y + 21))

        # 生命
        for i in range(self.player.lives):
            cx, cy = x + 6 + i * 22, y + 52
            pygame.draw.polygon(surf, CYAN, [(cx, cy - 7), (cx - 7, cy + 7), (cx + 7, cy + 7)])
        # 炸彈
        for i in range(self.bombs):
            cx, cy = x + 6 + i * 22, y + 76
            pygame.draw.polygon(surf, PURPLE,
                                [(cx, cy - 8), (cx + 7, cy), (cx, cy + 8), (cx - 7, cy)])
        # 火力
        ptxt = f"POWER {self.player.power}" + ("+M" if self.player.missiles_on else "")
        surf.blit(self.font_s.render(ptxt, True, YELLOW), (x + 6, y + 92))

        # 分數 / 波數
        s1 = self.font_m.render(f"SCORE  {self.score}", True, WHITE)
        s2 = self.font_m.render(f"WAVE  {self.wave}", True, CYAN)
        s3 = self.font_s.render(f"BEST  {max(self.high_score, self.score)}", True, GREY)
        surf.blit(s1, (SCREEN_W - s1.get_width() - 18, 16))
        surf.blit(s2, (SCREEN_W - s2.get_width() - 18, 50))
        surf.blit(s3, (SCREEN_W - s3.get_width() - 18, 82))

        # 連擊
        if self.combo > 1:
            mult = min(5, 1 + self.combo // 4)
            ctxt = self.font_m.render(f"COMBO {self.combo}  x{mult}", True, ORANGE)
            surf.blit(ctxt, (SCREEN_W - ctxt.get_width() - 18, 112))
            w = 140
            pygame.draw.rect(surf, (50, 40, 30), (SCREEN_W - w - 18, 142, w, 5))
            pygame.draw.rect(surf, ORANGE,
                             (SCREEN_W - w - 18, 142, int(w * self.combo_timer / 110), 5))

        # 本波進度（非 BOSS 波）
        if not self.is_boss_wave():
            prog = self.kills / self.kills_for_next_wave
            pw_, py_ = 160, 106
            pygame.draw.rect(surf, (35, 40, 60), (SCREEN_W - pw_ - 18, py_, pw_, 5), border_radius=3)
            pygame.draw.rect(surf, PURPLE,
                             (SCREEN_W - pw_ - 18, py_, int(pw_ * min(1, prog)), 5), border_radius=3)

        # BOSS 血條
        if self.boss:
            bw = 420
            bx = SCREEN_W // 2 - bw // 2
            by = 14
            r = max(0, self.boss.hp / self.boss.max_hp)
            pygame.draw.rect(surf, (25, 15, 30), (bx - 3, by - 3, bw + 6, 20), border_radius=5)
            pygame.draw.rect(surf, (70, 20, 40), (bx, by, bw, 14), border_radius=4)
            pygame.draw.rect(surf, (255, 80, 130), (bx, by, int(bw * r), 14), border_radius=4)
            name = self.font_s.render("MOTHERSHIP", True, PINK)
            surf.blit(name, (SCREEN_W // 2 - name.get_width() // 2, by + 18))

        if self.show_fps:
            fps = self.font_s.render(f"{self.clock.get_fps():.0f} FPS", True, GREEN)
            surf.blit(fps, (SCREEN_W // 2 - 30, SCREEN_H - 26))

    def draw_center_panel(self, surf, lines, pad=42):
        rendered = [(font.render(text, True, color), gap) for text, font, color, gap in lines]
        content_h = sum(gap for _, gap in rendered[:-1]) + rendered[-1][0].get_height()
        box_h = content_h + pad * 2
        panel = pygame.Surface((SCREEN_W, box_h), pygame.SRCALPHA)
        panel.fill((8, 10, 24, 210))
        top = SCREEN_H // 2 - box_h // 2
        surf.blit(panel, (0, top))
        pygame.draw.line(surf, (90, 110, 190), (0, top), (SCREEN_W, top), 2)
        pygame.draw.line(surf, (90, 110, 190), (0, top + box_h), (SCREEN_W, top + box_h), 2)
        y = top + pad + rendered[0][0].get_height() // 2
        for img, gap in rendered:
            surf.blit(img, img.get_rect(center=(SCREEN_W // 2, y)))
            y += gap

    # ---------- 繪製 ----------
    def draw(self):
        c = self.canvas
        self.background.draw(c)

        # 預警標記（敵人即將出現的位置）
        blink = (pygame.time.get_ticks() // 120) % 2 == 0
        if blink:
            for p in self.pending:
                x = int(p["x"])
                pygame.draw.polygon(c, RED, [(x, 22), (x - 9, 6), (x + 9, 6)])

        for pu in self.powerups:
            pu.draw(c)
        for bl in self.bullets:
            bl.draw(c)
        for m in self.missiles:
            c.blit(m.image, m.rect)
        for e in self.enemies:
            e.draw(c)
        if self.boss:
            self.boss.draw(c)
        for bl in self.enemy_bullets:
            bl.draw(c)
        if self.state != self.STATE_OVER:
            self.player.draw(c)
        for ex in self.explosions:
            ex.draw(c)
        self.particles.draw(c)
        for t in self.texts:
            c.blit(t.image, t.rect)

        # 炸彈衝擊波
        for ring in self.bomb_rings:
            pygame.draw.circle(c, (200, 160, 255), (ring["cx"], ring["cy"]), int(ring["r"]), 4)
            pygame.draw.circle(c, WHITE, (ring["cx"], ring["cy"]), max(1, int(ring["r"]) - 6), 2)

        # 白色閃光（炸彈 / BOSS 死亡）
        if self.flash > 0:
            self.white_overlay.set_alpha(min(200, self.flash))
            c.blit(self.white_overlay, (0, 0))

        # 低血量紅框警示
        if self.state == self.STATE_PLAY and self.player.hp <= self.player.max_hp * 0.3:
            pulse = 0.6 + 0.4 * math.sin(pygame.time.get_ticks() * 0.012)
            self.vignette.set_alpha(int(255 * pulse))
            c.blit(self.vignette, (0, 0))

        if self.state != self.STATE_TITLE:
            self.draw_hud(c)

        if self.state == self.STATE_TITLE:
            self.draw_center_panel(c, [
                ("ALIEN SHOOTER DX", self.font_xl, CYAN, 60),
                ("Arrows / WASD to fly     SPACE to fire     X bomb", self.font_m, WHITE, 34),
                ("P pause      F fps      ESC quit", self.font_s, GREY, 30),
                ("Chain kills for combo x5  -  Boss every 5 waves", self.font_s, GREY, 50),
                ("PRESS SPACE TO START", self.font_l, YELLOW, 0),
            ])
        elif self.state == self.STATE_PAUSE:
            self.draw_center_panel(c, [
                ("PAUSED", self.font_xl, WHITE, 56),
                ("Press P to resume", self.font_m, GREY, 0),
            ])
        elif self.state == self.STATE_OVER:
            best = ("NEW HIGH SCORE!" if self.score >= self.high_score and self.score > 0
                    else f"BEST  {self.high_score}")
            self.draw_center_panel(c, [
                ("GAME OVER", self.font_xl, RED, 60),
                (f"SCORE  {self.score}", self.font_l, WHITE, 42),
                (f"WAVE {self.wave}      MAX COMBO {self.max_combo}", self.font_m, CYAN, 34),
                (best, self.font_m, YELLOW, 44),
                ("Press R to restart      ESC to quit", self.font_s, GREY, 0),
            ])

        # 畫布 -> 螢幕（帶震動位移）
        if self.shake > 0.5:
            s = self.shake
            off = (random.uniform(-s, s) * 0.6, random.uniform(-s, s) * 0.6)
            self.screen.fill(BLACK)
            self.screen.blit(c, off)
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
                self.background.update(0.6)
                self.particles.update()
            elif self.state == self.STATE_OVER:
                self.explosions.update()
                self.texts.update()
                self.particles.update()
                self.background.update(0.4)
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


# ---------------------------------------------------------------
# 爆炸動畫（放最後避免前向引用問題）
# ---------------------------------------------------------------
class _Explosion(pygame.sprite.Sprite):
    def __init__(self, center, frames, frame_delay=3):
        super().__init__()
        self.frames = frames
        self.index = 0
        self.timer = 0
        self.delay = frame_delay
        self.image = frames[0]
        self.rect = self.image.get_rect(center=center)

    def update(self, *_):
        self.timer += 1
        if self.timer >= self.delay:
            self.timer = 0
            self.index += 1
            if self.index >= len(self.frames):
                self.kill()
                return
            self.image = self.frames[self.index]
            self.rect = self.image.get_rect(center=self.rect.center)

    def draw(self, surf):
        surf.blit(self.image, self.rect, special_flags=pygame.BLEND_RGB_ADD)


if __name__ == "__main__":
    Game().run()
