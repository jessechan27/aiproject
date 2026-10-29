import pygame
import random
import math
import sys
import os
from pathlib import Path

# Initialize Pygame
pygame.init()
pygame.mixer.init()  # Initialize mixer for sound

# ==================== File Diagnosis ====================
print("🔍 Checking required files...")
current_dir = os.getcwd()
print(f"Current folder: {current_dir}")

required_files = ["jet.png", "E1.png", "E2.png", "E3.png", "E4.png", "explosion graph.jpg", 
                  "shoot.mp3", "background.mp3", "exploresion.mp3", "gameover.mp3"]
for file in required_files:
    if os.path.exists(file):
        print(f"✅ {file} - Found")
    else:
        print(f"❌ {file} - Not found")
        # Check for variations
        for variation in [file.upper(), file.lower(), file.replace('.jpg', '.JPG'), file.replace('.mp3', '.MP3')]:
            if os.path.exists(variation):
                print(f"   💡 Found similar file: {variation}")
print()

# Game settings
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)

# Create game window
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Alien Shooter Game")
clock = pygame.time.Clock()

# ==================== Load Sounds ====================
sounds = {}
sound_files = {
    'shoot': 'shoot.mp3',
    'explosion': 'exploresion.mp3',
    'game_over': 'gameover.mp3'
}

for sound_name, filename in sound_files.items():
    try:
        if os.path.exists(filename):
            sounds[sound_name] = pygame.mixer.Sound(filename)
            print(f"✅ Sound loaded: {filename}")
        else:
            print(f"⚠️ Sound not found: {filename}")
            sounds[sound_name] = None
    except Exception as e:
        print(f"❌ Failed to load {filename}: {e}")
        sounds[sound_name] = None

# Load background music
background_music = None
try:
    if os.path.exists('background.mp3'):
        pygame.mixer.music.load('background.mp3')
        background_music = True
        print("✅ Background music loaded: background.mp3")
    else:
        print("⚠️ Background music not found: background.mp3")
except Exception as e:
    print(f"❌ Failed to load background music: {e}")

# Load explosion image
explosion_image = None
explosion_variants = ["explosion graph.jpg", "explosion graph.JPG", "explosion_graph.jpg", "Explosion.jpg"]
for filename in explosion_variants:
    try:
        if os.path.exists(filename):
            explosion_image = pygame.image.load(filename)
            explosion_image = pygame.transform.scale(explosion_image, (60, 60))
            print(f"✅ Explosion image loaded: {filename}")
            break
    except Exception as e:
        continue

if explosion_image is None:
    print("⚠️ Explosion image not found")

# ==================== Game Objects ====================

class Player(pygame.sprite.Sprite):
    """Player spaceship"""
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
                    print(f"✅ Successfully loaded jet: {filename}")
                    loaded = True
                    break
            except Exception as e:
                print(f"❌ Failed to load {filename}: {e}")
                continue
        
        if not loaded:
            # 如果找不到圖片，創建一個簡單的矩形
            print("⚠️ Jet image not found, using green rectangle instead")
            self.image = pygame.Surface((50, 40))
            self.image.fill(GREEN)
        
        self.rect = self.image.get_rect()
        self.rect.centerx = SCREEN_WIDTH // 2
        self.rect.bottom = SCREEN_HEIGHT - 10
        self.speed_x = 0
        self.health = 3
        self.shoot_cooldown = 0

    def update(self):
        # Control movement
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] and self.rect.left > 0:
            self.rect.x -= 7
        if keys[pygame.K_RIGHT] and self.rect.right < SCREEN_WIDTH:
            self.rect.x += 7
        
        # Cooldown timer
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1

    def shoot(self):
        """Fire bullet"""
        if self.shoot_cooldown <= 0:
            # Play shoot sound
            if sounds.get('shoot'):
                sounds['shoot'].play()
            
            bullet = Bullet(self.rect.centerx, self.rect.top)
            all_sprites.add(bullet)
            bullets.add(bullet)
            self.shoot_cooldown = 10

    def draw_health(self):
        """Display health"""
        font = pygame.font.Font(None, 36)
        health_text = font.render(f"Health: {self.health}", True, RED)
        screen.blit(health_text, (10, 10))


class Enemy(pygame.sprite.Sprite):
    """Alien enemy"""
    def __init__(self, enemy_type):
        super().__init__()
        self.enemy_type = enemy_type
        
        # Load different enemy images based on type, try multiple variants
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
            # If image not found, create colored rectangle
            self.image = pygame.Surface((40, 40))
            colors = [(255, 100, 100), (100, 255, 100), (100, 100, 255), (255, 255, 100)]
            self.image.fill(colors[enemy_type - 1])
        
        self.rect = self.image.get_rect()
        self.rect.x = random.randint(0, SCREEN_WIDTH - self.rect.width)
        self.rect.y = random.randint(-100, -40)
        
        # Set different speeds based on type
        self.speed_y = random.randint(2, 5) + (enemy_type * 0.5)  # Higher level = faster
        self.speed_x = random.uniform(-2, 2)
        self.health = enemy_type  # Higher level requires more hits

    def update(self):
        self.rect.y += self.speed_y
        self.rect.x += self.speed_x
        
        # Bounce off edges
        if self.rect.left < 0 or self.rect.right > SCREEN_WIDTH:
            self.speed_x = -self.speed_x
        
        # Remove when off screen
        if self.rect.top > SCREEN_HEIGHT:
            self.kill()


class Bullet(pygame.sprite.Sprite):
    """Player bullet"""
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
        # Remove when off screen
        if self.rect.bottom < 0:
            self.kill()


class Explosion(pygame.sprite.Sprite):
    """Explosion effect"""
    def __init__(self, x, y, size=20):
        super().__init__()
        
        # Use explosion image if available, otherwise use colored circle
        if explosion_image:
            self.image = explosion_image.copy()
        else:
            self.image = pygame.Surface((size, size))
            self.image.fill((255, 165, 0))
        
        self.rect = self.image.get_rect()
        self.rect.center = (x, y)
        self.lifetime = 15

    def update(self):
        self.lifetime -= 1
        if self.lifetime <= 0:
            self.kill()


# ==================== Sprite Groups ====================
all_sprites = pygame.sprite.Group()
enemies = pygame.sprite.Group()
bullets = pygame.sprite.Group()
explosions = pygame.sprite.Group()

# Create player
player = Player()
all_sprites.add(player)

# ==================== Game State ====================
score = 0
wave = 1
enemy_spawn_timer = 0
game_over = False
game_over_time = 0
game_over_music_played = False

# Start background music
if background_music:
    pygame.mixer.music.play(-1)  # -1 means loop indefinitely

# ==================== Main Game Loop ====================
running = True
while running:
    clock.tick(FPS)
    
    # Event handling
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE and not game_over:
                player.shoot()
            if event.key == pygame.K_r and game_over:
                # Restart game
                player.health = 3
                score = 0
                wave = 1
                enemy_spawn_timer = 0
                game_over = False
                game_over_music_played = False
                for enemy in enemies:
                    enemy.kill()
                
                # Resume background music
                if background_music:
                    pygame.mixer.music.play(-1)

    if not game_over:
        # Update all sprites
        all_sprites.update()
        
        # Spawn enemies
        enemy_spawn_timer += 1
        spawn_rate = max(30 - (wave * 3), 15)  # Faster spawn with higher waves
        if enemy_spawn_timer > spawn_rate:
            enemy_type = random.randint(1, 4)
            enemy = Enemy(enemy_type)
            all_sprites.add(enemy)
            enemies.add(enemy)
            enemy_spawn_timer = 0
        
        # Check bullet-enemy collisions
        collisions = pygame.sprite.groupcollide(enemies, bullets, False, False)
        for enemy in collisions:
            enemy.health -= 1
            bullets_hit = collisions[enemy]
            for bullet in bullets_hit:
                bullet.kill()
            
            if enemy.health <= 0:
                enemy.kill()
                # Play explosion sound
                if sounds.get('explosion'):
                    sounds['explosion'].play()
                
                explosion = Explosion(enemy.rect.centerx, enemy.rect.centery, 30)
                all_sprites.add(explosion)
                explosions.add(explosion)
                score += enemy.enemy_type * 10  # Higher level enemies give more points
        
        # Check enemy-player collisions
        enemy_hits = pygame.sprite.spritecollide(player, enemies, True)
        for enemy in enemy_hits:
            player.health -= 1
            # Play explosion sound
            if sounds.get('explosion'):
                sounds['explosion'].play()
            
            explosion = Explosion(player.rect.centerx, player.rect.centery, 40)
            all_sprites.add(explosion)
            explosions.add(explosion)
        
        # Check game over
        if player.health <= 0:
            game_over = True
            game_over_time = pygame.time.get_ticks()
            
            # Stop background music and play game over music
            if not game_over_music_played:
                pygame.mixer.music.stop()
                if sounds.get('game_over'):
                    sounds['game_over'].play()
                game_over_music_played = True
        
        # Check wave upgrade
        if len(enemies) == 0 and enemy_spawn_timer > 100:
            wave += 1
            enemy_spawn_timer = 0
    
    # ==================== Rendering ====================
    screen.fill(BLACK)
    
    # Draw starfield background
    for i in range(10):
        star_x = random.randint(0, SCREEN_WIDTH)
        star_y = random.randint(0, SCREEN_HEIGHT)
        pygame.draw.circle(screen, WHITE, (star_x, star_y), 1)
    
    # Draw all sprites
    all_sprites.draw(screen)
    
    # Draw UI
    font = pygame.font.Font(None, 36)
    score_text = font.render(f"Score: {score}", True, WHITE)
    wave_text = font.render(f"Wave: {wave}", True, WHITE)
    screen.blit(score_text, (SCREEN_WIDTH - 200, 10))
    screen.blit(wave_text, (SCREEN_WIDTH - 200, 50))
    player.draw_health()
    
    # Game Over screen
    if game_over:
        font_large = pygame.font.Font(None, 72)
        game_over_text = font_large.render("GAME OVER", True, RED)
        restart_text = font.render("Press R to Restart", True, WHITE)
        final_score_text = font.render(f"Final Score: {score}", True, WHITE)
        screen.blit(game_over_text, (SCREEN_WIDTH//2 - 200, SCREEN_HEIGHT//2 - 100))
        screen.blit(final_score_text, (SCREEN_WIDTH//2 - 150, SCREEN_HEIGHT//2))
        screen.blit(restart_text, (SCREEN_WIDTH//2 - 150, SCREEN_HEIGHT//2 + 100))
    
    pygame.display.flip()

# Stop all sounds before quitting
pygame.mixer.music.stop()
pygame.mixer.stop()

pygame.quit()
sys.exit()