import pygame
import random
import math
import sys
import os
from pathlib import Path

# 初始化 Pygame
pygame.init()

# ==================== 檔案診斷 ====================
print("🔍 檢查圖片文件...")
current_dir = os.getcwd()
print(f"當前資料夾: {current_dir}")

required_files = ["jet.jpg", "E1.png", "E2.png", "E3.png", "E4.png"]
for file in required_files:
    if os.path.exists(file):
        print(f"✅ {file} - 找到")
    else:
        print(f"❌ {file} - 沒找到")
        # 檢查是否有其他變體
        for variation in [file.upper(), file.lower(), file.replace('.jpg', '.JPG'), file.replace('.png', '.PNG')]:
            if os.path.exists(variation):
                print(f"   💡 找到類似檔案: {variation}")
print()

# 遊戲設置
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)

# 創建遊戲窗口
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("外星生物射擊遊戲")
clock = pygame.time.Clock()

# ==================== 遊戲對象類 ====================

class Player(pygame.sprite.Sprite):
    """玩家太空船"""
    def __init__(self):
        super().__init__()
        
        # 嘗試多種檔案名變體
        jet_variants = ["jet.png", "jet.PNG", "jet.jpg", "jet.JPG", "jet.jpeg", "jet.JPEG", "Jet.png", "JET.png"]
        loaded = False
        
        for filename in jet_variants:
            try:
                if os.path.exists(filename):
                    self.image = pygame.image.load(filename)
                    self.image = pygame.transform.scale(self.image, (50, 40))
                    print(f"✅ 成功加載太空船: {filename}")
                    loaded = True
                    break
            except Exception as e:
                print(f"❌ 加載 {filename} 失敗: {e}")
                continue
        
        if not loaded:
            # 如果找不到圖片，創建一個簡單的矩形
            print("⚠️ 沒找到 jet 圖片，使用綠色矩形代替")
            self.image = pygame.Surface((50, 40))
            self.image.fill(GREEN)
        
        self.rect = self.image.get_rect()
        self.rect.centerx = SCREEN_WIDTH // 2
        self.rect.bottom = SCREEN_HEIGHT - 10
        self.speed_x = 0
        self.health = 3
        self.shoot_cooldown = 0

    def update(self):
        # 控制移動
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] and self.rect.left > 0:
            self.rect.x -= 7
        if keys[pygame.K_RIGHT] and self.rect.right < SCREEN_WIDTH:
            self.rect.x += 7
        
        # 冷卻計時
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1

    def shoot(self):
        """發射子彈"""
        if self.shoot_cooldown <= 0:
            bullet = Bullet(self.rect.centerx, self.rect.top)
            all_sprites.add(bullet)
            bullets.add(bullet)
            self.shoot_cooldown = 10

    def draw_health(self):
        """顯示生命值"""
        font = pygame.font.Font(None, 36)
        health_text = font.render(f"生命: {self.health}", True, RED)
        screen.blit(health_text, (10, 10))


class Enemy(pygame.sprite.Sprite):
    """外星敵人"""
    def __init__(self, enemy_type):
        super().__init__()
        self.enemy_type = enemy_type
        
        # 根據類型加載不同的敵人圖片，嘗試多種變體
        enemy_variants = [
            f"E{enemy_type}.png",
            f"E{enemy_type}.PNG",
            f"e{enemy_type}.png",
            f"e{enemy_type}.PNG",
            f"enemy{enemy_type}.png",
            f"Enemy{enemy_type}.png"
        ]
        
        loaded = False
        for filename in enemy_variants:
            try:
                if os.path.exists(filename):
                    self.image = pygame.image.load(filename)
                    self.image = pygame.transform.scale(self.image, (40, 40))
                    loaded = True
                    break
            except Exception as e:
                continue
        
        if not loaded:
            # 如果找不到圖片，創建不同顏色的矩形
            self.image = pygame.Surface((40, 40))
            colors = [(255, 100, 100), (100, 255, 100), (100, 100, 255), (255, 255, 100)]
            self.image.fill(colors[enemy_type - 1])
        
        self.rect = self.image.get_rect()
        self.rect.x = random.randint(0, SCREEN_WIDTH - self.rect.width)
        self.rect.y = random.randint(-100, -40)
        
        # 根據類型設置不同的速度和行為
        self.speed_y = random.randint(2, 5) + (enemy_type * 0.5)  # 更高等級更快
        self.speed_x = random.uniform(-2, 2)
        self.health = enemy_type  # 高等級需要多發子彈擊殺

    def update(self):
        self.rect.y += self.speed_y
        self.rect.x += self.speed_x
        
        # 邊界反彈
        if self.rect.left < 0 or self.rect.right > SCREEN_WIDTH:
            self.speed_x = -self.speed_x
        
        # 移出螢幕時刪除
        if self.rect.top > SCREEN_HEIGHT:
            self.kill()


class Bullet(pygame.sprite.Sprite):
    """玩家子彈"""
    def __init__(self, x, y):
        super().__init__()
        self.image = pygame.Surface((5, 15))
        self.image.fill(WHITE)
        self.rect = self.image.get_rect()
        self.rect.centerx = x
        self.rect.bottom = y
        self.speed_y = -10

    def update(self):
        self.rect.y += self.speed_y
        # 移出螢幕時刪除
        if self.rect.bottom < 0:
            self.kill()


class Explosion(pygame.sprite.Sprite):
    """爆炸效果"""
    def __init__(self, x, y, size=20):
        super().__init__()
        self.image = pygame.Surface((size, size))
        self.image.fill((255, 165, 0))
        self.rect = self.image.get_rect()
        self.rect.center = (x, y)
        self.lifetime = 10

    def update(self):
        self.lifetime -= 1
        if self.lifetime <= 0:
            self.kill()


# ==================== 精靈組 ====================
all_sprites = pygame.sprite.Group()
enemies = pygame.sprite.Group()
bullets = pygame.sprite.Group()
explosions = pygame.sprite.Group()

# 創建玩家
player = Player()
all_sprites.add(player)

# ==================== 遊戲狀態 ====================
score = 0
wave = 1
enemy_spawn_timer = 0
game_over = False
game_over_time = 0

# ==================== 主遊戲循環 ====================
running = True
while running:
    clock.tick(FPS)
    
    # 事件處理
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE and not game_over:
                player.shoot()
            if event.key == pygame.K_r and game_over:
                # 重新開始
                player.health = 3
                score = 0
                wave = 1
                enemy_spawn_timer = 0
                game_over = False
                for enemy in enemies:
                    enemy.kill()

    if not game_over:
        # 更新所有精靈
        all_sprites.update()
        
        # 生成敵人
        enemy_spawn_timer += 1
        spawn_rate = max(30 - (wave * 3), 15)  # 隨著波數加快生成速度
        if enemy_spawn_timer > spawn_rate:
            enemy_type = random.randint(1, 4)
            enemy = Enemy(enemy_type)
            all_sprites.add(enemy)
            enemies.add(enemy)
            enemy_spawn_timer = 0
        
        # 檢測子彈與敵人碰撞
        collisions = pygame.sprite.groupcollide(enemies, bullets, False, False)
        for enemy in collisions:
            enemy.health -= 1
            bullets_hit = collisions[enemy]
            for bullet in bullets_hit:
                bullet.kill()
            
            if enemy.health <= 0:
                enemy.kill()
                explosion = Explosion(enemy.rect.centerx, enemy.rect.centery, 30)
                all_sprites.add(explosion)
                explosions.add(explosion)
                score += enemy.enemy_type * 10  # 高等級敵人獲得更多分數
        
        # 檢測敵人與玩家碰撞
        enemy_hits = pygame.sprite.spritecollide(player, enemies, True)
        for enemy in enemy_hits:
            player.health -= 1
            explosion = Explosion(player.rect.centerx, player.rect.centery, 40)
            all_sprites.add(explosion)
            explosions.add(explosion)
        
        # 檢查遊戲結束
        if player.health <= 0:
            game_over = True
            game_over_time = pygame.time.get_ticks()
        
        # 檢測波數升級
        if len(enemies) == 0 and enemy_spawn_timer > 100:
            wave += 1
            enemy_spawn_timer = 0
    
    # ==================== 渲染 ====================
    screen.fill(BLACK)
    
    # 繪製星空背景效果
    for i in range(10):
        star_x = random.randint(0, SCREEN_WIDTH)
        star_y = random.randint(0, SCREEN_HEIGHT)
        pygame.draw.circle(screen, WHITE, (star_x, star_y), 1)
    
    # 繪製所有精靈
    all_sprites.draw(screen)
    
    # 繪製UI
    font = pygame.font.Font(None, 36)
    score_text = font.render(f"分數: {score}", True, WHITE)
    wave_text = font.render(f"波數: {wave}", True, WHITE)
    screen.blit(score_text, (SCREEN_WIDTH - 200, 10))
    screen.blit(wave_text, (SCREEN_WIDTH - 200, 50))
    player.draw_health()
    
    # 遊戲結束畫面
    if game_over:
        font_large = pygame.font.Font(None, 72)
        game_over_text = font_large.render("遊戲結束", True, RED)
        restart_text = font.render("按 R 重新開始", True, WHITE)
        final_score_text = font.render(f"最終分數: {score}", True, WHITE)
        screen.blit(game_over_text, (SCREEN_WIDTH//2 - 150, SCREEN_HEIGHT//2 - 100))
        screen.blit(final_score_text, (SCREEN_WIDTH//2 - 100, SCREEN_HEIGHT//2))
        screen.blit(restart_text, (SCREEN_WIDTH//2 - 100, SCREEN_HEIGHT//2 + 100))
    
    pygame.display.flip()

pygame.quit()
sys.exit()