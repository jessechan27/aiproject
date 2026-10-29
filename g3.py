"""
================================================================
 ALIEN SHOOTER  -  太空船射擊遊戲
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
   方向鍵 / WASD  移動
   空白鍵          射擊（按住可連射）
   P              暫停
   R              遊戲結束後重新開始
   ESC            離開

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

# 顏色
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (235, 70, 70)
GREEN = (90, 220, 130)
CYAN = (110, 230, 240)
YELLOW = (255, 210, 80)
ORANGE = (255, 150, 50)
PURPLE = (190, 120, 255)
GREY = (120, 130, 150)

# 素材資料夾 = 這支程式所在的資料夾
# （這樣不論你從哪個目錄執行 python，都能正確找到圖片和音效）
if getattr(sys, "frozen", False):
    ASSET_DIR = os.path.dirname(sys.executable)
else:
    ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------
# 素材載入工具
# ---------------------------------------------------------------
def find_asset(*candidates):
    """在素材資料夾裡尋找檔案，忽略大小寫與底線/空白的差異。找不到回傳 None。"""
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
    """載入圖片並轉成適合快速繪製的格式；找不到時用色塊代替，讓遊戲照樣能玩。"""
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
    """載入音效；找不到回傳 None，播放時會自動略過。"""
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
    把 explosion_graph.jpg 切成 9 張連續動畫。
    這張圖是 3x3 排列，由左到右、由上到下就是爆炸的時間順序。

    因為是 JPG（沒有透明度），底色是深褐色。這裡先把底色「減掉」，
    畫的時候再用加亮模式疊上去，火光就會自然融進夜空，不會出現方形邊框。
    """
    sheet = pygame.image.load(path).convert()
    sw, sh = sheet.get_size()
    fw, fh = sw // 3, sh // 3
    bg = sheet.get_at((2, 2))[:3]          # 取左上角當作底色

    frames = []
    for row in range(3):
        for col in range(3):
            rect = pygame.Rect(col * fw, row * fh, fw, fh)
            frame = sheet.subsurface(rect).copy()
            frame = pygame.transform.smoothscale(frame, (frame_size, frame_size))
            # 每個像素減掉底色；底色區域變成全黑，加亮時等於不存在
            frame.fill((*bg, 0), special_flags=pygame.BLEND_RGB_SUB)
            frames.append(frame)
    return frames


# ---------------------------------------------------------------
# 背景（外星球高空）
# ---------------------------------------------------------------
class Background:
    """
    分三層：
      1. 固定的天空漸層 + 遠方行星（畫一次，之後重複使用）
      2. 三層視差星點（越亮越快，製造深度）
      3. 兩層半透明雲氣帶，緩慢向下捲動 = 高空飛行感
    """

    def __init__(self):
        self.sky = self._make_sky()
        self.stars = []
        for layer, (count, speed, size) in enumerate([(70, 0.35, 1), (45, 0.8, 2), (22, 1.6, 2)]):
            for _ in range(count):
                self.stars.append({
                    "x": random.uniform(0, SCREEN_W),
                    "y": random.uniform(0, SCREEN_H),
                    "spd": speed,
                    "r": size,
                    "b": 90 + layer * 60,
                })
        self.cloud_a = self._make_cloud_band(alpha=26, color=(150, 90, 200))
        self.cloud_b = self._make_cloud_band(alpha=20, color=(70, 130, 200))
        self.off_a = 0.0
        self.off_b = 0.0

    def _make_sky(self):
        """由上而下的漸層天空，再加一顆遠方的環狀行星。"""
        sky = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
        top = (26, 10, 44)       # 高空深紫
        bottom = (12, 20, 52)    # 靠近地表的藍
        for y in range(SCREEN_H):
            t = y / SCREEN_H
            col = (
                int(top[0] + (bottom[0] - top[0]) * t),
                int(top[1] + (bottom[1] - top[1]) * t),
                int(top[2] + (bottom[2] - top[2]) * t),
            )
            pygame.draw.line(sky, col, (0, y), (SCREEN_W, y))

        # 星雲：幾團很淡的光暈
        neb = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        for _ in range(16):
            cx = random.randint(0, SCREEN_W)
            cy = random.randint(0, SCREEN_H)
            rad = random.randint(70, 190)
            col = random.choice([(150, 60, 190), (60, 90, 200), (190, 70, 120)])
            for i in range(rad, 0, -14):
                a = int(7 * (1 - i / rad))
                pygame.draw.circle(neb, (*col, a), (cx, cy), i)
        sky.blit(neb, (0, 0))

        # 遠方行星（左上角），用同心圓做出球體受光的感覺
        px, py, pr = 150, 130, 95
        planet = pygame.Surface((pr * 2 + 60, pr * 2 + 60), pygame.SRCALPHA)
        c = (pr + 30, pr + 30)
        for i in range(pr, 0, -1):
            t = i / pr
            col = (int(90 + 90 * (1 - t)), int(40 + 60 * (1 - t)), int(110 + 70 * (1 - t)))
            pygame.draw.circle(planet, col, c, i)
        # 行星環
        ring = pygame.Surface((pr * 3, pr * 3), pygame.SRCALPHA)
        pygame.draw.ellipse(ring, (200, 170, 220, 55), (0, pr * 1.15, pr * 3, pr * 0.7), 9)
        ring = pygame.transform.rotate(ring, 18)
        planet.blit(ring, (c[0] - ring.get_width() // 2, c[1] - ring.get_height() // 2))
        sky.blit(planet, (px - c[0], py - c[1]))
        return sky

    def _make_cloud_band(self, alpha, color):
        """做一條可無縫上下接續的雲氣帶。"""
        band = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        for _ in range(26):
            cx = random.randint(0, SCREEN_W)
            cy = random.randint(0, SCREEN_H)
            rad = random.randint(60, 150)
            for i in range(rad, 0, -12):
                a = int(alpha * (1 - i / rad))
                pygame.draw.circle(band, (*color, a), (cx, cy), i)
                # 上下各補一份，讓捲動時可以無縫銜接
                pygame.draw.circle(band, (*color, a), (cx, cy - SCREEN_H), i)
                pygame.draw.circle(band, (*color, a), (cx, cy + SCREEN_H), i)
        return band

    def update(self, speed_scale=1.0):
        for s in self.stars:
            s["y"] += s["spd"] * speed_scale
            if s["y"] > SCREEN_H:
                s["y"] = -2
                s["x"] = random.uniform(0, SCREEN_W)
        self.off_a = (self.off_a + 0.25 * speed_scale) % SCREEN_H
        self.off_b = (self.off_b + 0.55 * speed_scale) % SCREEN_H

    def draw(self, surf):
        surf.blit(self.sky, (0, 0))
        surf.blit(self.cloud_a, (0, self.off_a - SCREEN_H))
        surf.blit(self.cloud_a, (0, self.off_a))
        for s in self.stars:
            b = s["b"]
            pygame.draw.circle(surf, (b, b, min(255, b + 40)), (int(s["x"]), int(s["y"])), s["r"])
        surf.blit(self.cloud_b, (0, self.off_b - SCREEN_H))
        surf.blit(self.cloud_b, (0, self.off_b))


# ---------------------------------------------------------------
# 遊戲物件
# ---------------------------------------------------------------
class Player(pygame.sprite.Sprite):
    SPEED = 6.2

    def __init__(self, image):
        super().__init__()
        self.base_image = image
        self.image = image
        self.rect = self.image.get_rect(center=(SCREEN_W // 2, SCREEN_H - 90))
        self.mask = pygame.mask.from_surface(self.image)
        self.pos = pygame.Vector2(self.rect.center)

        self.max_hp = 100
        self.hp = self.max_hp
        self.lives = 3
        self.power = 1              # 火力等級 1~3
        self.shield = 0             # 護盾剩餘時間（frame）
        self.invincible = 0         # 被撞後的無敵時間
        self.cooldown = 0
        self.engine_phase = 0.0

    def update(self, keys):
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

        # 限制活動範圍：左右滿版，上下只能在畫面下半部飛
        self.pos.x = max(self.rect.width / 2, min(SCREEN_W - self.rect.width / 2, self.pos.x))
        self.pos.y = max(SCREEN_H * 0.35, min(SCREEN_H - self.rect.height / 2 - 8, self.pos.y))
        self.rect.center = (round(self.pos.x), round(self.pos.y))

        if self.cooldown > 0:
            self.cooldown -= 1
        if self.shield > 0:
            self.shield -= 1
        if self.invincible > 0:
            self.invincible -= 1
        self.engine_phase += 0.4

    def shoot(self, bullet_group, all_group, sound):
        """依火力等級決定同時射出幾發、往哪些方向射。"""
        if self.cooldown > 0:
            return
        self.cooldown = 9 if self.power < 3 else 7

        if self.power == 1:
            specs = [(0, -13, 0)]
        elif self.power == 2:
            specs = [(-11, -13, 0), (11, -13, 0)]
        else:
            specs = [(-15, -12.5, -2.2), (0, -14, 0), (15, -12.5, 2.2)]

        for dx, speed_y, speed_x in specs:
            b = PlayerBullet(self.rect.centerx + dx, self.rect.top + 6, speed_x, speed_y)
            bullet_group.add(b)
            all_group.add(b)

        if sound:
            sound.play()

    def hit(self, damage):
        """回傳 True 表示這次真的扣到血。"""
        if self.invincible > 0:
            return False
        if self.shield > 0:
            self.shield = 0            # 護盾擋掉一次傷害後消失
            self.invincible = 40
            return False
        self.hp -= damage
        self.invincible = 55
        return True

    def draw_engine(self, surf):
        """引擎尾焰：用兩個會抖動的三角形表現推進。"""
        flicker = 8 + 5 * math.sin(self.engine_phase) + random.uniform(-2, 2)
        cx, by = self.rect.centerx, self.rect.bottom - 4
        for off, col in ((-9, (120, 200, 255)), (9, (120, 200, 255))):
            pygame.draw.polygon(
                surf, col,
                [(cx + off - 4, by), (cx + off + 4, by), (cx + off, by + flicker)]
            )
        pygame.draw.polygon(
            surf, (255, 240, 200),
            [(cx - 3, by), (cx + 3, by), (cx, by + flicker * 0.6)]
        )

    def draw(self, surf):
        # 無敵時閃爍
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


class EnemyBullet(pygame.sprite.Sprite):
    def __init__(self, x, y, vx, vy, color=(255, 120, 90)):
        super().__init__()
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


# 四種敵人的設定。把「數值」跟「程式邏輯」分開，之後要調平衡只改這張表就好。
ENEMY_TYPES = {
    1: {"name": "Drifter", "size": 56, "hp": 2, "speed": (1.6, 2.6), "score": 10,
        "behavior": "drift", "shoot": 0, "damage": 12},
    2: {"name": "Weaver", "size": 58, "hp": 3, "speed": (1.8, 2.8), "score": 20,
        "behavior": "wave", "shoot": 0.004, "damage": 14},
    3: {"name": "Hunter", "size": 60, "hp": 5, "speed": (1.4, 2.2), "score": 35,
        "behavior": "hunt", "shoot": 0.009, "damage": 18},
    4: {"name": "Saucer", "size": 76, "hp": 9, "speed": (1.0, 1.6), "score": 60,
        "behavior": "saucer", "shoot": 0.014, "damage": 25},
}


class Enemy(pygame.sprite.Sprite):
    def __init__(self, etype, image, wave):
        super().__init__()
        cfg = ENEMY_TYPES[etype]
        self.etype = etype
        self.cfg = cfg
        self.image = image
        self.rect = self.image.get_rect()
        self.mask = pygame.mask.from_surface(self.image)

        self.max_hp = cfg["hp"] + wave // 3        # 每三波稍微變硬
        self.hp = self.max_hp
        self.score = cfg["score"]
        self.damage = cfg["damage"]
        self.shoot_chance = cfg["shoot"] * (1 + wave * 0.05)

        lo, hi = cfg["speed"]
        self.speed = random.uniform(lo, hi) + wave * 0.06
        self.pos = pygame.Vector2(
            random.uniform(self.rect.width, SCREEN_W - self.rect.width),
            random.uniform(-160, -60),
        )
        self.rect.center = self.pos
        self.phase = random.uniform(0, math.tau)
        self.amp = random.uniform(1.4, 3.0)
        self.drift = random.uniform(-1.0, 1.0)
        self.flash = 0

    def update(self, player, enemy_bullets, all_group):
        b = self.cfg["behavior"]

        if b == "drift":
            self.pos.y += self.speed
            self.pos.x += self.drift

        elif b == "wave":
            self.pos.y += self.speed
            self.phase += 0.055
            self.pos.x += math.sin(self.phase) * self.amp * 1.8

        elif b == "hunt":
            # 慢慢往玩家的水平位置靠過去
            self.pos.y += self.speed * 0.85
            if player.rect.centerx > self.pos.x + 6:
                self.pos.x += 1.5
            elif player.rect.centerx < self.pos.x - 6:
                self.pos.x -= 1.5

        elif b == "saucer":
            # 飛碟：下降到一定高度就開始左右巡航
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

        # 開火
        if random.random() < self.shoot_chance and self.rect.bottom > 0:
            self.fire(player, enemy_bullets, all_group)

        if self.rect.top > SCREEN_H + 40:
            self.kill()

    def fire(self, player, enemy_bullets, all_group):
        if self.etype == 4:
            # 飛碟：三方向散射
            for ang in (-0.35, 0, 0.35):
                vx = math.sin(ang) * 5.0
                vy = math.cos(ang) * 5.0
                bl = EnemyBullet(self.rect.centerx, self.rect.bottom, vx, vy, (255, 140, 240))
                enemy_bullets.add(bl)
                all_group.add(bl)
        else:
            # 其他敵人：朝玩家瞄準射一發
            d = pygame.Vector2(player.rect.center) - pygame.Vector2(self.rect.center)
            if d.length() > 0:
                d = d.normalize() * 4.6
                bl = EnemyBullet(self.rect.centerx, self.rect.bottom, d.x, d.y)
                enemy_bullets.add(bl)
                all_group.add(bl)

    def take_damage(self, dmg=1):
        self.hp -= dmg
        self.flash = 4
        return self.hp <= 0

    def draw(self, surf):
        if self.flash > 0:
            # 被打中時整隻閃白
            white = self.image.copy()
            white.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGB_ADD)
            surf.blit(white, self.rect)
            surf.blit(self.image, self.rect, special_flags=pygame.BLEND_RGB_ADD)
        else:
            surf.blit(self.image, self.rect)

        # 受傷後才顯示血條，畫面比較乾淨
        if self.hp < self.max_hp:
            w = self.rect.width
            ratio = max(0, self.hp / self.max_hp)
            bx, by = self.rect.left, self.rect.top - 7
            pygame.draw.rect(surf, (60, 20, 20), (bx, by, w, 4))
            pygame.draw.rect(surf, (90, 230, 120), (bx, by, int(w * ratio), 4))


class Explosion(pygame.sprite.Sprite):
    """用 explosion_graph.jpg 切出來的 9 格連續動畫播放爆炸。"""

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
        # 原圖是深色底的 JPG，用「加亮」模式疊上去，深色底會自然消失，
        # 只留下火光 —— 不需要去背也不需要 numpy。
        surf.blit(self.image, self.rect, special_flags=pygame.BLEND_RGB_ADD)


class PowerUp(pygame.sprite.Sprite):
    KINDS = {
        "power": (YELLOW, "P"),
        "heal": (GREEN, "+"),
        "shield": (CYAN, "S"),
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


class FloatingText(pygame.sprite.Sprite):
    """擊殺時往上飄的分數數字。"""

    def __init__(self, center, text, color, font):
        super().__init__()
        self.image = font.render(text, True, color)
        self.rect = self.image.get_rect(center=center)
        self.pos = pygame.Vector2(self.rect.center)
        self.life = 45

    def update(self, *_):
        self.pos.y -= 1.1
        self.rect.center = (round(self.pos.x), round(self.pos.y))
        self.life -= 1
        if self.life <= 0:
            self.kill()
        else:
            self.image.set_alpha(int(255 * min(1, self.life / 25)))


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
            self.audio = True
        except pygame.error as e:
            print(f"[WARN] 音效系統無法啟動：{e}（遊戲仍可進行，只是沒有聲音）")
            self.audio = False

        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Alien Shooter")
        self.clock = pygame.time.Clock()

        self.font_s = pygame.font.Font(None, 24)
        self.font_m = pygame.font.Font(None, 34)
        self.font_l = pygame.font.Font(None, 54)
        self.font_xl = pygame.font.Font(None, 86)

        self.load_assets()
        self.background = Background()
        self.high_score = self.load_high_score()
        self.state = self.STATE_TITLE
        self.reset()

    # ---------- 素材 ----------
    def load_assets(self):
        print(f"\n素材資料夾：{ASSET_DIR}")
        print("載入中 ...")

        self.img_player = load_image(["jet.png", "jet.jpg"], size=(58, 55), fallback_color=GREEN)

        self.img_enemies = {}
        colors = {1: (80, 200, 180), 2: (230, 90, 70), 3: (60, 90, 140), 4: (210, 90, 200)}
        for i in (1, 2, 3, 4):
            sz = ENEMY_TYPES[i]["size"]
            self.img_enemies[i] = load_image(
                [f"E{i}.png", f"E{i}.jpg"], size=(sz, sz), fallback_color=colors[i]
            )

        # 爆炸連續圖
        self.frames_big = None
        self.frames_small = None
        exp_path = find_asset("explosion_graph.jpg", "explosion graph.jpg", "explosion.png")
        if exp_path:
            try:
                self.frames_small = slice_explosion_sheet(exp_path, 90)
                self.frames_big = slice_explosion_sheet(exp_path, 150)
                print(f"  [OK]   sheet  {os.path.basename(exp_path)} -> 切成 9 格動畫")
            except pygame.error as e:
                print(f"  [FAIL] sheet  {e}")
        if self.frames_small is None:
            self.frames_small = self._fallback_frames(90)
            self.frames_big = self._fallback_frames(150)
            print("  [MISS] 爆炸圖 -> 使用程式繪製的爆炸")

        self.snd_shoot = load_sound(["shoot.wav", "shoot.mp3", "shoot.ogg"], 0.28) if self.audio else None
        self.snd_explode = load_sound(["explosion.mp3", "exploresion.mp3", "explosion.wav"], 0.45) if self.audio else None
        self.snd_over = load_sound(["gameover.mp3", "game_over.mp3"], 0.6) if self.audio else None

        self.music_path = find_asset("background.mp3", "background.ogg", "background.wav") if self.audio else None
        if self.music_path:
            print(f"  [OK]   music  {os.path.basename(self.music_path)}")
        elif self.audio:
            print("  [MISS] music  background.mp3")
        print()

    def _fallback_frames(self, size):
        """沒有爆炸圖時，用程式畫出 9 格漸強漸弱的火球。"""
        frames = []
        for i in range(9):
            t = i / 8
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            r = int(size / 2 * min(1.0, 0.25 + t * 1.2))
            fade = max(0.0, 1 - max(0.0, (t - 0.5) * 2))
            for rr, col in ((r, (200, 60, 20)), (int(r * 0.66), (255, 160, 40)), (int(r * 0.35), (255, 245, 210))):
                if rr > 0:
                    c = tuple(int(v * fade) for v in col)
                    pygame.draw.circle(surf, c, (size // 2, size // 2), rr)
            frames.append(surf)
        return frames

    # ---------- 最高分紀錄 ----------
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

    # ---------- 音樂 ----------
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
        self.all_sprites = pygame.sprite.Group()
        self.enemies = pygame.sprite.Group()
        self.bullets = pygame.sprite.Group()
        self.enemy_bullets = pygame.sprite.Group()
        self.explosions = pygame.sprite.Group()
        self.powerups = pygame.sprite.Group()
        self.texts = pygame.sprite.Group()

        self.player = Player(self.img_player)
        self.score = 0
        self.wave = 1
        self.kills = 0
        self.kills_for_next_wave = 8
        self.spawn_timer = 0
        self.shake = 0
        self.over_handled = False

    # ---------- 生成敵人 ----------
    def spawn_enemy(self):
        # 波數越高，高階敵人出現的機率越大
        w = self.wave
        weights = [
            max(1, 55 - w * 4),          # E1
            30 + w,                      # E2
            10 + w * 2,                  # E3
            max(0, w - 1) * 2,           # E4（第二波之後才登場）
        ]
        etype = random.choices([1, 2, 3, 4], weights=weights)[0]
        e = Enemy(etype, self.img_enemies[etype], self.wave)
        self.enemies.add(e)

    def spawn_interval(self):
        return max(18, 52 - self.wave * 3)

    # ---------- 爆炸 ----------
    def boom(self, center, big=False):
        frames = self.frames_big if big else self.frames_small
        self.explosions.add(Explosion(center, frames, frame_delay=3))
        if self.snd_explode:
            self.snd_explode.play()
        self.shake = max(self.shake, 9 if big else 5)

    # ---------- 事件 ----------
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_p and self.state in (self.STATE_PLAY, self.STATE_PAUSE):
                    if self.state == self.STATE_PLAY:
                        self.state = self.STATE_PAUSE
                        if self.audio:
                            pygame.mixer.music.pause()
                    else:
                        self.state = self.STATE_PLAY
                        if self.audio:
                            pygame.mixer.music.unpause()
                if event.key in (pygame.K_SPACE, pygame.K_RETURN) and self.state == self.STATE_TITLE:
                    self.state = self.STATE_PLAY
                    self.reset()
                    self.play_music()
                if event.key == pygame.K_r and self.state == self.STATE_OVER:
                    self.state = self.STATE_PLAY
                    self.reset()
                    self.play_music()
        return True

    # ---------- 每一幀的遊戲邏輯 ----------
    def update_play(self):
        keys = pygame.key.get_pressed()
        self.player.update(keys)
        if keys[pygame.K_SPACE]:
            self.player.shoot(self.bullets, self.all_sprites, self.snd_shoot)

        self.enemies.update(self.player, self.enemy_bullets, self.all_sprites)
        self.bullets.update()
        self.enemy_bullets.update()
        self.explosions.update()
        self.powerups.update()
        self.texts.update()
        self.background.update(1.0 + self.wave * 0.05)

        # 生成敵人
        self.spawn_timer += 1
        if self.spawn_timer >= self.spawn_interval():
            self.spawn_timer = 0
            self.spawn_enemy()

        # 我方子彈 vs 敵人
        hits = pygame.sprite.groupcollide(
            self.enemies, self.bullets, False, True, pygame.sprite.collide_mask
        )
        for enemy, bl in hits.items():
            if enemy.take_damage(len(bl)):
                enemy.kill()
                self.kills += 1
                gained = enemy.score * self.wave
                self.score += gained
                self.boom(enemy.rect.center, big=(enemy.etype == 4))
                self.texts.add(FloatingText(enemy.rect.center, f"+{gained}", YELLOW, self.font_s))
                self.maybe_drop(enemy)

        # 敵人子彈 vs 我方
        for bl in pygame.sprite.spritecollide(
            self.player, self.enemy_bullets, True, pygame.sprite.collide_mask
        ):
            if self.player.hit(14):
                self.shake = max(self.shake, 6)

        # 敵人撞上我方
        for enemy in pygame.sprite.spritecollide(
            self.player, self.enemies, False, pygame.sprite.collide_mask
        ):
            enemy.kill()
            self.boom(enemy.rect.center, big=True)
            self.player.hit(enemy.damage)

        # 撿道具
        for pu in pygame.sprite.spritecollide(self.player, self.powerups, True, pygame.sprite.collide_mask):
            if pu.kind == "power":
                self.player.power = min(3, self.player.power + 1)
                label = "POWER UP!"
            elif pu.kind == "heal":
                self.player.hp = min(self.player.max_hp, self.player.hp + 35)
                label = "+35 HP"
            else:
                self.player.shield = 60 * 8
                label = "SHIELD"
            self.texts.add(FloatingText(self.player.rect.midtop, label, pu.color, self.font_s))

        # 血量歸零 -> 扣命
        if self.player.hp <= 0:
            self.player.lives -= 1
            self.boom(self.player.rect.center, big=True)
            if self.player.lives > 0:
                self.player.hp = self.player.max_hp
                self.player.power = max(1, self.player.power - 1)
                self.player.invincible = 120
                self.player.pos = pygame.Vector2(SCREEN_W // 2, SCREEN_H - 90)
            else:
                self.state = self.STATE_OVER

        # 過關升波
        if self.kills >= self.kills_for_next_wave:
            self.kills = 0
            self.wave += 1
            self.kills_for_next_wave = 8 + self.wave * 2
            self.texts.add(FloatingText(
                (SCREEN_W // 2, SCREEN_H // 2 - 60), f"WAVE {self.wave}", CYAN, self.font_l
            ))

        if self.shake > 0:
            self.shake -= 1

    def maybe_drop(self, enemy):
        """高階敵人掉寶機率較高；血少的時候比較容易掉補血。"""
        chance = {1: 0.06, 2: 0.09, 3: 0.14, 4: 0.5}[enemy.etype]
        if random.random() < chance:
            if self.player.hp < self.player.max_hp * 0.5:
                kind = random.choices(["heal", "power", "shield"], [0.5, 0.3, 0.2])[0]
            else:
                kind = random.choices(["power", "shield", "heal"], [0.45, 0.3, 0.25])[0]
            self.powerups.add(PowerUp(enemy.rect.center, kind))

    # ---------- 畫面 ----------
    def draw_hud(self, surf):
        # 血條
        bar_w, bar_h = 210, 16
        x, y = 16, 16
        ratio = max(0, self.player.hp / self.player.max_hp)
        pygame.draw.rect(surf, (20, 25, 40), (x - 2, y - 2, bar_w + 4, bar_h + 4), border_radius=4)
        pygame.draw.rect(surf, (55, 20, 25), (x, y, bar_w, bar_h), border_radius=3)
        col = GREEN if ratio > 0.5 else (YELLOW if ratio > 0.25 else RED)
        pygame.draw.rect(surf, col, (x, y, int(bar_w * ratio), bar_h), border_radius=3)
        surf.blit(self.font_s.render(f"HULL {int(self.player.hp)}", True, WHITE), (x + 6, y + 21))

        # 剩餘生命（用小三角形表示）
        for i in range(self.player.lives):
            cx = x + 6 + i * 22
            cy = y + 52
            pygame.draw.polygon(surf, CYAN, [(cx, cy - 7), (cx - 7, cy + 7), (cx + 7, cy + 7)])

        # 火力等級
        pw = self.font_s.render(f"POWER {self.player.power}", True, YELLOW)
        surf.blit(pw, (x + 6, y + 70))

        # 分數 / 波數
        s1 = self.font_m.render(f"SCORE  {self.score}", True, WHITE)
        s2 = self.font_m.render(f"WAVE  {self.wave}", True, CYAN)
        s3 = self.font_s.render(f"BEST  {max(self.high_score, self.score)}", True, GREY)
        surf.blit(s1, (SCREEN_W - s1.get_width() - 18, 16))
        surf.blit(s2, (SCREEN_W - s2.get_width() - 18, 50))
        surf.blit(s3, (SCREEN_W - s3.get_width() - 18, 82))

        # 本波進度條
        prog = self.kills / self.kills_for_next_wave
        pw_, ph_ = 160, 5
        px_, py_ = SCREEN_W - pw_ - 18, 106
        pygame.draw.rect(surf, (35, 40, 60), (px_, py_, pw_, ph_), border_radius=3)
        pygame.draw.rect(surf, PURPLE, (px_, py_, int(pw_ * min(1, prog)), ph_), border_radius=3)

    def draw_center_panel(self, surf, lines, pad=42):
        """
        半透明面板 + 置中文字，給標題 / 暫停 / 結束畫面共用。
        面板高度依內容自動計算，文字永遠垂直置中。
        lines 的每一項是 (文字, 字型, 顏色, 與下一行的間距)
        """
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

    def draw(self):
        # 用一張暫存畫布，方便做畫面震動
        canvas = self.screen
        offset = (0, 0)
        if self.shake > 0:
            offset = (random.randint(-self.shake, self.shake) // 2,
                      random.randint(-self.shake, self.shake) // 2)

        self.background.draw(canvas)

        # 位移一次，讓所有物件一起震
        surf = canvas
        if offset != (0, 0):
            surf = pygame.Surface((SCREEN_W, SCREEN_H))
            surf.blit(canvas, (0, 0))

        for pu in self.powerups:
            surf.blit(pu.image, pu.rect)
        for bl in self.bullets:
            surf.blit(bl.image, bl.rect)
        for e in self.enemies:
            e.draw(surf)
        for bl in self.enemy_bullets:
            surf.blit(bl.image, bl.rect)
        if self.state != self.STATE_OVER:
            self.player.draw(surf)
        for ex in self.explosions:
            ex.draw(surf)
        for t in self.texts:
            surf.blit(t.image, t.rect)

        if offset != (0, 0):
            canvas.blit(surf, offset)

        # 標題畫面不顯示 HUD，畫面比較乾淨
        if self.state != self.STATE_TITLE:
            self.draw_hud(canvas)

        if self.state == self.STATE_TITLE:
            self.draw_center_panel(canvas, [
                ("ALIEN SHOOTER", self.font_xl, CYAN, 62),
                ("Arrows / WASD to fly     SPACE to fire", self.font_m, WHITE, 34),
                ("P pause      ESC quit", self.font_s, GREY, 52),
                ("PRESS SPACE TO START", self.font_l, YELLOW, 0),
            ])

        elif self.state == self.STATE_PAUSE:
            self.draw_center_panel(canvas, [
                ("PAUSED", self.font_xl, WHITE, 56),
                ("Press P to resume", self.font_m, GREY, 0),
            ])

        elif self.state == self.STATE_OVER:
            best = ("NEW HIGH SCORE!" if self.score >= self.high_score and self.score > 0
                    else f"BEST  {self.high_score}")
            self.draw_center_panel(canvas, [
                ("GAME OVER", self.font_xl, RED, 62),
                (f"SCORE  {self.score}", self.font_l, WHITE, 42),
                (f"WAVE REACHED  {self.wave}", self.font_m, CYAN, 34),
                (best, self.font_m, YELLOW, 44),
                ("Press R to restart      ESC to quit", self.font_s, GREY, 0),
            ])

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
            elif self.state == self.STATE_OVER:
                # 結束畫面仍讓爆炸播完、背景繼續飄
                self.explosions.update()
                self.texts.update()
                self.background.update(0.4)
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