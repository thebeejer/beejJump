import pygame
import sys
import random
import math
import array

# ── Audio pre-init (must precede pygame.init) ─────────────────────────────────
SAMPLE_RATE = 22050
pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, 512)

# ── Game constants ─────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 900, 400
FPS      = 60
GROUND_Y = 320

SKY    = (30,  20,  50)
GND    = (80,  60,  40)
GND_LN = (60,  45,  30)

PLAYER_X = 120
BEEJER_W = 100
BEEJER_H = 75

GRAVITY  = 0.8
JUMP_VEL = -18

LAVA_SPEED     = 5
GARGOYLE_W     = 54
GARGOYLE_H     = 48
GARGOYLE_SPEED = 4

# Beejer body hitbox (offsets within bounding box)
HIT_OX, HIT_OY = 12, 38
HIT_W,  HIT_H  = 68, 36

# Tail-swipe hitbox (offsets from PLAYER_X / player_y)
SWIPE_OX, SWIPE_OY = 18, -85
SWIPE_W,  SWIPE_H  = 185, 135

# Tail-swing timing
SWING_DURATION = 24          # total frames per swing
SWING_HI, SWING_LO = 20, 6  # hitbox is live while tail_swing is in (LO, HI]
SWING_COOLDOWN = 38

# Pop explosion
POP_DURATION = 24

STATE_PLAY = "play"
STATE_OVER = "over"


# ── Sound generation ───────────────────────────────────────────────────────────

def _note_samples(freq, n, vol, wave, phase):
    attack  = min(int(SAMPLE_RATE * 0.008), n // 4)
    release = max(n - int(SAMPLE_RATE * 0.04), n * 3 // 4)
    out = []
    for i in range(n):
        if freq <= 0:
            out += [0, 0]
            continue
        phase += 2 * math.pi * freq / SAMPLE_RATE
        s = math.sin(phase)
        if wave == 'square':
            raw = 1.0 if s >= 0 else -1.0
        elif wave == 'triangle':
            p = (phase % (2 * math.pi)) / (2 * math.pi)
            raw = 4*p - 1 if p < 0.5 else 3 - 4*p
        else:
            raw = s
        if i < attack:
            env = i / attack if attack else 1.0
        elif i >= release:
            denom = n - release
            env = (n - i) / denom if denom else 0.0
        else:
            env = 1.0
        val = int(vol * 32767 * raw * max(0.0, env))
        out += [val, val]
    return out, phase


def make_melody():
    """
    Original "Beejer's Grotto" Theme.
    A calm, atmospheric loop using a Triangle wave and a Pentatonic scale.
    """
    # Frequencies for A Minor Pentatonic (Soft and harmonious)
    A4, C5, D5, E5, G5, A5 = 440.00, 523.25, 587.33, 659.25, 783.99, 880.00
    R = 0  # Rest

    BPM  = 110
    BEAT = 60.0 / BPM

    # An 8-bar ambient loop
    notes = [
        (A4, 1.0), (C5, 1.0), (E5, 2.0),
        (D5, 1.0), (G5, 1.0), (E5, 2.0),
        (A5, 1.0), (G5, 1.0), (E5, 1.0), (C5, 1.0),
        (D5, 2.0), (R,  2.0),
        (A4, 1.0), (C5, 1.0), (D5, 1.0), (A4, 1.0),
        (E5, 2.0), (G5, 2.0),
        (A5, 1.0), (E5, 1.0), (D5, 1.0), (C5, 1.0),
        (A4, 4.0),
    ]

    buf   = array.array('h')
    phase = 0.0
    for freq, beats in notes:
        n = int(SAMPLE_RATE * beats * BEAT)
        # Triangle wave for a softer, less aggressive sound
        samps, phase = _note_samples(freq, n, 0.20, 'triangle', phase)
        buf.extend(samps)
    return pygame.mixer.Sound(buffer=buf)


def make_jump_sound():
    n = int(SAMPLE_RATE * 0.11)
    phase = 0.0
    buf = array.array('h')
    for i in range(n):
        t = i / n
        freq = 200 + 580 * t
        phase += 2 * math.pi * freq / SAMPLE_RATE
        raw = 1.0 if math.sin(phase) >= 0 else -1.0
        val = int(0.28 * 32767 * raw * (1.0 - t))
        buf += array.array('h', [val, val])
    return pygame.mixer.Sound(buffer=buf)


def make_death_sound():
    n = int(SAMPLE_RATE * 0.65)
    phase = 0.0
    rng = random.Random(7)
    buf = array.array('h')
    for i in range(n):
        t = i / n
        freq = 440 * (1 - t) + 55
        phase += 2 * math.pi * freq / SAMPLE_RATE
        tone  = 1.0 if math.sin(phase) >= 0 else -1.0
        noise = rng.uniform(-1.0, 1.0)
        raw   = tone * (1 - t * 0.6) + noise * (t * 0.45)
        env   = max(0.0, 1.0 - t * 0.65)
        val   = max(-32767, min(32767, int(0.45 * 32767 * raw * env)))
        buf  += array.array('h', [val, val])
    return pygame.mixer.Sound(buffer=buf)


def make_swipe_sound():
    """Quick downward whoosh — pitch drops as the tail sweeps forward."""
    n = int(SAMPLE_RATE * 0.14)
    phase = 0.0
    rng = random.Random(3)
    buf = array.array('h')
    for i in range(n):
        t = i / n
        freq  = 900 - 700 * t          # 900 → 200 Hz sweep
        phase += 2 * math.pi * freq / SAMPLE_RATE
        tone  = 1.0 if math.sin(phase) >= 0 else -1.0
        noise = rng.uniform(-1.0, 1.0)
        raw   = tone * 0.55 + noise * 0.45
        env   = (1.0 - t) * min(1.0, t * 10)
        val   = int(0.32 * 32767 * raw * env)
        buf  += array.array('h', [val, val])
    return pygame.mixer.Sound(buffer=buf)


def make_pop_sound():
    """Punchy gargoyle-destruction thump with crunchy noise tail."""
    n = int(SAMPLE_RATE * 0.20)
    phase = 0.0
    rng = random.Random(55)
    buf = array.array('h')
    for i in range(n):
        t = i / n
        freq  = max(80, 700 - 3000 * t)   # rapid pitch drop
        phase += 2 * math.pi * freq / SAMPLE_RATE
        tone  = math.sin(phase)
        noise = rng.uniform(-1.0, 1.0)
        raw   = tone * max(0, 1 - t * 3) + noise * min(1.0, t * 4) * 0.6
        env   = max(0.0, 1.0 - t * 1.4)
        val   = max(-32767, min(32767, int(0.55 * 32767 * raw * env)))
        buf  += array.array('h', [val, val])
    return pygame.mixer.Sound(buffer=buf)


# ── Beejer sprite ──────────────────────────────────────────────────────────────

def draw_beejer(surf, bx, by):
    D   = ( 35,  30,  25)
    STR = (235, 232, 220)
    CLW = (210, 195, 140)
    TLD = ( 55,  48,  38)
    TLL = ( 90,  78,  58)
    STG = (190, 165,  25)
    EYE = (255,  40,  40)
    NSE = (190,  50,  50)
    BLK = (  0,   0,   0)

    def r(col, x, y, w, h, brd=0):
        pygame.draw.rect(surf, col, (bx+x, by+y, w, h))
        if brd:
            pygame.draw.rect(surf, BLK, (bx+x, by+y, w, h), brd)

    def poly(col, pts, brd=0):
        ap = [(bx+x, by+y) for x, y in pts]
        pygame.draw.polygon(surf, col, ap)
        if brd:
            pygame.draw.polygon(surf, BLK, ap, brd)

    r(TLD,  2, 48, 12, 10, 1)
    r(TLL,  1, 36, 10, 14, 1)
    r(TLD,  4, 23, 12, 14, 1)
    r(TLL, 12, 12, 15, 10, 1)
    r(TLD, 23,  5, 15,  9, 1)
    r(TLL, 35,  3, 12,  7, 1)
    poly(STG, [(45,3),(53,9),(46,15)], brd=1)

    r(D,   10, 40, 52, 22, 1)
    r(STR, 18, 40, 10, 22)

    for lx in (14, 26, 42, 54):
        r(D,   lx,     62,  7, 9)
        r(CLW, lx - 1, 71,  9, 4)

    r(D,   60, 32, 22, 20, 1)
    r(STR, 67, 32,  7, 20)
    r(D,   80, 39, 10,  8, 1)
    r(NSE, 87, 40,  5,  5)
    r(EYE,            68, 36, 6, 5)
    r((255,200,200),  69, 37, 2, 2)

    poly(D,   [(62,32),(66,22),(70,32)])
    poly(STR, [(63,32),(66,26),(69,32)])

    for cx, cy, ch in ((88,44,12),(92,41,12),(96,46,10)):
        r(CLW, cx, cy,      3, ch)
        r(STG, cx, cy + ch, 3,  3)


def draw_swipe_effect(surf, bx, by, swing_progress):
    """Gold fan of lines + flying stinger tip during active tail swing."""
    if swing_progress <= 0.05:
        return
    gold    = (255, 215, 30)
    dim_g   = (200, 160, 20)
    pivot   = (bx + 50, by + 10)   # rough stinger launch point

    # Fan of 5 radial lines sweeping forward-and-down
    for i in range(5):
        angle  = math.radians(-15 + i * 20)   # –15° … +65°
        length = int(65 * swing_progress)
        if length < 4:
            continue
        ex = int(pivot[0] + math.cos(angle) * length)
        ey = int(pivot[1] + math.sin(angle) * length)
        w  = max(1, int(3 * swing_progress))
        pygame.draw.line(surf, gold if i == 2 else dim_g, pivot, (ex, ey), w)

    # Stinger at the tip of the centre line
    ang = math.radians(25)
    sx  = int(pivot[0] + math.cos(ang) * 65 * swing_progress)
    sy  = int(pivot[1] + math.sin(ang) * 65 * swing_progress)
    pygame.draw.polygon(surf, (255, 245, 120), [(sx,sy),(sx+9,sy+4),(sx+2,sy+10)])


# ── Gargoyle sprite ────────────────────────────────────────────────────────────

def draw_gargoyle(surf, gx, gy, flap):
    """
    Stone gargoyle facing LEFT (toward the player).
    flap=0 → wings up, flap=1 → wings down.
    Bounding box: GARGOYLE_W × GARGOYLE_H  (54 × 48)
    """
    C_STONE = (105,  98, 118)
    C_DARK  = ( 62,  56,  74)
    C_WING  = ( 80,  74,  96)
    C_WING2 = ( 55,  50,  68)   # wing underside
    C_EYE   = (255,  50,  50)
    C_HORN  = (135, 122, 100)
    BLK     = (  0,   0,   0)

    def r(col, x, y, w, h, brd=0):
        pygame.draw.rect(surf, col, (gx+x, gy+y, w, h))
        if brd:
            pygame.draw.rect(surf, BLK, (gx+x, gy+y, w, h), brd)

    def poly(col, pts, brd=0):
        ap = [(gx+x, gy+y) for x, y in pts]
        pygame.draw.polygon(surf, col, ap)
        if brd:
            pygame.draw.polygon(surf, BLK, ap, brd)

    # ── Wings (animated) ───────────────────────────────────────────────────
    if flap == 0:   # wings raised
        poly(C_WING,  [( 8, 28),(  0,  4),(22, 18)], brd=1)   # left wing
        poly(C_WING2, [( 8, 28),(  4, 10),(18, 22)])
        poly(C_WING,  [(36, 28),( 54,  4),(32, 18)], brd=1)   # right wing
        poly(C_WING2, [(36, 28),( 50, 10),(38, 22)])
    else:           # wings lowered
        poly(C_WING,  [( 8, 28),(  0, 38),(22, 28)], brd=1)
        poly(C_WING2, [( 8, 28),(  4, 34),(18, 28)])
        poly(C_WING,  [(36, 28),( 54, 38),(32, 28)], brd=1)
        poly(C_WING2, [(36, 28),( 50, 34),(38, 28)])

    # ── Body ───────────────────────────────────────────────────────────────
    r(C_STONE, 16, 20, 22, 24, 1)
    # Stone texture lines
    r(C_DARK,  18, 26,  6,  1)
    r(C_DARK,  24, 32,  8,  1)

    # ── Head (faces left) ──────────────────────────────────────────────────
    r(C_STONE,  2, 14, 18, 22, 1)
    # Snout / jaw
    r(C_DARK,   2, 28,  8,  8, 1)
    # Teeth
    r((230,220,200),  3, 34, 3, 3)
    r((230,220,200),  7, 34, 3, 3)
    # Eyes
    r(C_EYE,    4, 16, 6, 5)
    r(C_EYE,   11, 16, 6, 5)
    r((255,180,180),  5, 17, 2, 2)  # glint
    r((255,180,180), 12, 17, 2, 2)

    # ── Horns ──────────────────────────────────────────────────────────────
    poly(C_HORN, [( 2, 14),( 5,  3),( 9, 14)])
    poly(C_HORN, [( 9, 14),(13,  3),(17, 14)])

    # ── Feet / claws ───────────────────────────────────────────────────────
    poly(C_DARK, [(18, 44),(21, 48),(25, 44)])   # left foot
    poly(C_DARK, [(29, 44),(32, 48),(36, 44)])   # right foot
    r(C_STONE, 16, 40,  8,  6, 1)               # left ankle
    r(C_STONE, 28, 40,  8,  6, 1)               # right ankle


# ── Pop explosion ──────────────────────────────────────────────────────────────

def draw_pop(surf, px, py, timer, max_timer):
    t = 1.0 - (timer / max_timer)          # 0 → 1 as effect ages

    # Expanding ring
    radius = int(44 * t)
    if radius > 0:
        brightness = int(255 * (1 - t))
        col = (255, max(0, 200 - int(200 * t)), max(0, 40 - int(40 * t)))
        pygame.draw.circle(surf, col, (px, py), radius, max(1, 3 - int(t * 3)))

    # 8 particles radiating outward
    p_cols = [(255,230,60),(255,110,20),(255,255,200)]
    for i in range(8):
        angle = math.pi * 2 * i / 8
        dist  = int(52 * t)
        psize = max(1, 5 - int(t * 5))
        ex    = px + int(math.cos(angle) * dist)
        ey    = py + int(math.sin(angle) * dist)
        pygame.draw.rect(surf, p_cols[i % 3], (ex, ey, psize, psize))

    # Bright centre flash (first 40% of animation)
    if t < 0.4:
        fr = max(1, int(18 * (1 - t / 0.4)))
        pygame.draw.circle(surf, (255, 255, 220), (px, py), fr)


# ── Lava obstacle ──────────────────────────────────────────────────────────────

def draw_lava(surf, lx, lw, lh):
    C_BASE = (140,  15,   0)
    C_MID  = (215,  55,   0)
    C_GLOW = (255, 135,  15)
    C_CORE = (255, 220,  50)

    top = GROUND_Y - lh
    pygame.draw.rect(surf, C_BASE, (lx,    top,     lw,    lh))
    if lw > 10:
        pygame.draw.rect(surf, C_MID,  (lx+3,  top+8,  lw-6,  lh-8))
    if lw > 18:
        pygame.draw.rect(surf, C_GLOW, (lx+7,  top+18, lw-14, lh-18))
    if lh > 25:
        pygame.draw.rect(surf, C_CORE, (lx + lw//2 - 2, top+22, 4, lh-22))

    num_spikes = max(1, lw // 11)
    sw = lw / num_spikes
    sh = max(10, lh // 5)
    for i in range(num_spikes):
        sx = lx + i * sw
        pygame.draw.polygon(surf, C_GLOW, [
            (int(sx),          top),
            (int(sx + sw/2),   top - sh),
            (int(sx + sw),     top),
        ])
    csx = lx + lw//2 - int(sw)//2
    pygame.draw.polygon(surf, C_CORE, [
        (csx,              top),
        (csx + int(sw)//2, top - sh - 8),
        (csx + int(sw),    top),
    ])


# ── Hitbox helpers ─────────────────────────────────────────────────────────────

def beejer_hitbox(player_y):
    return pygame.Rect(PLAYER_X + HIT_OX, int(player_y) + HIT_OY, HIT_W, HIT_H)

def swipe_hitbox(player_y):
    return pygame.Rect(PLAYER_X + SWIPE_OX, int(player_y) + SWIPE_OY, SWIPE_W, SWIPE_H)

def lava_rect(obs):
    return pygame.Rect(int(obs[0]), GROUND_Y - obs[2], obs[1], obs[2])

def gargoyle_body(g):
    return pygame.Rect(int(g['x']) + 4, int(g['y']) + 8, 46, 34)


# ── Scene renderer ─────────────────────────────────────────────────────────────

def draw_scene(screen, player_y, obstacles, gargoyles, pops, tail_swing):
    screen.fill(SKY)
    pygame.draw.rect(screen, GND,   (0, GROUND_Y, SCREEN_W, SCREEN_H - GROUND_Y))
    pygame.draw.line(screen, GND_LN, (0, GROUND_Y), (SCREEN_W, GROUND_Y), 3)

    for obs in obstacles:
        draw_lava(screen, int(obs[0]), obs[1], obs[2])

    for g in gargoyles:
        draw_gargoyle(screen, int(g['x']), int(g['y']), (g['flap'] // 15) % 2)

    for p in pops:
        draw_pop(screen, p['x'], p['y'], p['timer'], POP_DURATION)

    # Swing progress: 0 outside active window, peaks at 1.0 at mid-swing
    swing_progress = 0.0
    if SWING_LO < tail_swing <= SWING_HI:
        mid = (SWING_LO + SWING_HI) / 2
        swing_progress = 1.0 - abs(tail_swing - mid) / (mid - SWING_LO)

    draw_beejer(screen, PLAYER_X, int(player_y))
    draw_swipe_effect(screen, PLAYER_X, int(player_y), swing_progress)


def center_blit(screen, surf, cy):
    screen.blit(surf, (SCREEN_W // 2 - surf.get_width() // 2, cy))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Beejer")
    clock = pygame.time.Clock()

    font_big   = pygame.font.SysFont("monospace", 72, bold=True)
    font_med   = pygame.font.SysFont("monospace", 34, bold=True)
    font_small = pygame.font.SysFont("monospace", 22)

    dim = pygame.Surface((SCREEN_W, SCREEN_H))
    dim.set_alpha(165)
    dim.fill((0, 0, 0))

    # ── Generate all sounds at startup ─────────────────────────────────────
    screen.fill(SKY)
    center_blit(screen, font_med.render("loading sounds...", True, (160, 160, 140)),
                SCREEN_H // 2 - 20)
    pygame.display.flip()

    melody_snd = make_melody()
    jump_snd   = make_jump_sound()
    death_snd  = make_death_sound()
    swipe_snd  = make_swipe_sound()
    pop_snd    = make_pop_sound()

    music_chan = pygame.mixer.Channel(0)
    music_chan.play(melody_snd, loops=-1)

    high_score = 0
    running    = True

    while running:
        # ── Per-run reset ───────────────────────────────────────────────────
        player_y   = float(GROUND_Y - BEEJER_H)
        player_vy  = 0.0
        on_ground  = True

        obstacles           = []
        spawn_timer         = 100

        gargoyles           = []
        gargoyle_spawn_timer = 160

        tail_swing    = 0
        tail_cooldown = 0

        pops  = []
        score = 0
        state = STATE_PLAY

        # ── Play loop ───────────────────────────────────────────────────────
        while running and state == STATE_PLAY:
            clock.tick(FPS)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                        if on_ground:
                            player_vy = JUMP_VEL
                            on_ground = False
                            jump_snd.play()

                    if event.key == pygame.K_s:
                        if tail_cooldown <= 0:
                            tail_swing    = SWING_DURATION
                            tail_cooldown = SWING_COOLDOWN
                            swipe_snd.play()

            # ── Physics ─────────────────────────────────────────────────────
            player_vy += GRAVITY
            player_y  += player_vy
            if player_y >= GROUND_Y - BEEJER_H:
                player_y  = float(GROUND_Y - BEEJER_H)
                player_vy = 0.0
                on_ground = True

            # ── Score ────────────────────────────────────────────────────────
            score += 1

            # ── Tail swing timers ────────────────────────────────────────────
            if tail_swing    > 0: tail_swing    -= 1
            if tail_cooldown > 0: tail_cooldown -= 1

            # ── Lava obstacles ───────────────────────────────────────────────
            spawn_timer -= 1
            if spawn_timer <= 0:
                lw = random.randint(20, 45)
                lh = random.randint(40, 110)
                obstacles.append([float(SCREEN_W), lw, lh])
                spawn_timer = random.randint(80, 180)
            for obs in obstacles:
                obs[0] -= LAVA_SPEED
            obstacles = [o for o in obstacles if o[0] + o[1] > 0]

            # ── Gargoyles ────────────────────────────────────────────────────
            gargoyle_spawn_timer -= 1
            if gargoyle_spawn_timer <= 0:
                # Two height bands: low (head-level when standing) and high (mid-air threat)
                band = random.choice(['low', 'high'])
                gy   = random.randint(215, 262) if band == 'low' else random.randint(90, 185)
                gargoyles.append({'x': float(SCREEN_W), 'y': float(gy), 'flap': 0})
                gargoyle_spawn_timer = random.randint(160, 300)

            for g in gargoyles:
                g['x']   -= GARGOYLE_SPEED
                g['flap'] = (g['flap'] + 1) % 30

            # ── Tail swipe destroys gargoyles (check before beejer collision) ─
            if SWING_LO < tail_swing <= SWING_HI:
                swr       = swipe_hitbox(player_y)
                survivors = []
                for g in gargoyles:
                    if swr.colliderect(gargoyle_body(g)):
                        cx = int(g['x']) + GARGOYLE_W // 2
                        cy = int(g['y']) + GARGOYLE_H // 2
                        pops.append({'x': cx, 'y': cy, 'timer': POP_DURATION})
                        pop_snd.play()
                    else:
                        survivors.append(g)
                gargoyles = survivors

            # Remove off-screen gargoyles
            gargoyles = [g for g in gargoyles if g['x'] + GARGOYLE_W > 0]

            # ── Pop timers ───────────────────────────────────────────────────
            for p in pops:
                p['timer'] -= 1
            pops = [p for p in pops if p['timer'] > 0]

            # ── Collision (lava and un-swiped gargoyles) ─────────────────────
            bh  = beejer_hitbox(player_y)
            hit = any(bh.colliderect(lava_rect(o)) for o in obstacles) or \
                  any(bh.colliderect(gargoyle_body(g)) for g in gargoyles)

            if hit:
                state      = STATE_OVER
                high_score = max(high_score, score // 6)
                death_snd.play()

            # ── Draw ─────────────────────────────────────────────────────────
            draw_scene(screen, player_y, obstacles, gargoyles, pops, tail_swing)

            sc_surf = font_small.render(f"SCORE  {score // 6:05d}", True, (200, 200, 180))
            screen.blit(sc_surf, (SCREEN_W - sc_surf.get_width() - 16, 14))

            # Swipe cooldown pip (small indicator, bottom-left)
            ready = tail_cooldown <= 0
            pip_col = (190, 165, 25) if ready else (80, 70, 30)
            pygame.draw.rect(screen, pip_col, (14, SCREEN_H - 22, 18, 10))
            label = font_small.render("S-SWIPE", True, pip_col)
            screen.blit(label, (36, SCREEN_H - 24))

            pygame.display.flip()

        # ── Game-over loop ──────────────────────────────────────────────────
        restart = False
        while running and state == STATE_OVER:
            clock.tick(FPS)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        restart = True
                        state   = None
                    elif event.key == pygame.K_ESCAPE:
                        running = False

            draw_scene(screen, player_y, obstacles, gargoyles, pops, 0)
            screen.blit(dim, (0, 0))

            center_blit(screen, font_big.render("GAME OVER", True, (255, 70, 20)),  70)
            center_blit(screen, font_med.render(f"SCORE   {score // 6:05d}", True, (255, 220, 80)),  175)
            center_blit(screen, font_med.render(f"BEST    {high_score:05d}",  True, (200, 170, 60)),  220)
            center_blit(screen, font_small.render("SPACE  play again          ESC  quit",
                                                   True, (140, 140, 140)), 305)
            pygame.display.flip()

        if not restart:
            break

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
