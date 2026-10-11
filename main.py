import base64
import math
import os
import random
import zlib
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.properties import NumericProperty, StringProperty
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, Ellipse, RoundedRectangle, Line, Triangle, Quad
from kivy.graphics.texture import Texture
from kivy.utils import platform
from kivy.metrics import dp

try:
    from kivy.core.audio import SoundLoader
except Exception:
    SoundLoader = None
try:
    import audio_data        # the generated sounds and music (see audio_data.py)
except Exception:
    audio_data = None

# Virtual game width. Height adapts to the phone's shape, so nothing is stretched.
GAME_W = 600
PADDLE_H = 18
PADDLE_Y = 160          # paddle sits higher so your finger doesn't cover it
PADDLE_W0 = 100
BALL_R = 8
BALL_SPEED = 5
ROWS, COLS = 8, 12      # more bricks
BRICK_H = 24
PAD, TOP, LEFT = 4, 100, 20

LOAD_TIME = 2.8          # seconds the loading screen is shown
LOAD_ROWS, LOAD_COLS = 4, 8
DRAG_SENS = 1.15         # the paddle only moves by sliding; how far it goes per finger movement

# Bricks get random colors from this palette every game.
BRICK_PALETTE = [
    (0.91, 0.30, 0.24, 1),  # red
    (0.95, 0.55, 0.15, 1),  # orange
    (0.97, 0.80, 0.10, 1),  # yellow
    (0.62, 0.85, 0.20, 1),  # lime
    (0.18, 0.80, 0.44, 1),  # green
    (0.10, 0.74, 0.69, 1),  # teal
    (0.20, 0.78, 0.95, 1),  # cyan
    (0.24, 0.55, 0.95, 1),  # blue
    (0.43, 0.40, 0.95, 1),  # indigo
    (0.66, 0.38, 0.88, 1),  # purple
    (0.95, 0.40, 0.70, 1),  # pink
    (0.85, 0.25, 0.55, 1),  # magenta
]
ACCENT = (0.22, 0.74, 0.97, 1)

TIPS = [
    "Tip: Slide your finger to move the paddle.",
    "Tip: Catch the falling power-ups!",
    "Tip: Silver-framed bricks take 2 hits.",
    "Tip: Hit with the paddle edge to change the angle.",
    "Tip: Sticky paddle lets you aim your launch.",
    "Tip: Multi-ball makes clearing bricks faster.",
]

# Each powerup has its own color (and a drawn picture, see _draw_pictogram).
POWERUP_STYLE = {
    'expand':    ([0.18, 0.80, 0.44, 1], 'W'),  # green  = wider paddle
    'multiball': ([0.95, 0.60, 0.10, 1], 'M'),  # orange = extra ball
    'sticky':    ([0.69, 0.35, 0.85, 1], 'S'),  # purple = sticky paddle
}

POWERUP_SFX = {'expand': 'pu_expand', 'multiball': 'pu_multi', 'sticky': 'pu_sticky'}

Window.clearcolor = (0.06, 0.09, 0.16, 1)


class Audio:
    """Loads the sounds carried by audio_data.py and plays them.
    Every call is crash-proof: if anything goes wrong the game simply stays silent."""

    def __init__(self, data_dir):
        self.dir = data_dir
        self.sfx = {}
        self.music = None
        self.sfx_on = True
        self.music_on = True
        self._queue = []
        if data_dir and audio_data is not None and SoundLoader is not None:
            self._queue = list(audio_data.SFX.keys()) + ['__music__']
        self.ok = bool(self._queue)

    @property
    def ready(self):
        return not self._queue

    def load_next(self):
        """Loads one sound per call, so the loading screen keeps animating smoothly."""
        if not self._queue:
            return
        name = self._queue.pop(0)
        try:
            is_music = name == '__music__'
            b64 = audio_data.MUSIC if is_music else audio_data.SFX[name]
            wav = zlib.decompress(base64.b64decode(b64))
            path = os.path.join(self.dir, ('music' if is_music else name) + '.wav')
            if not os.path.exists(path) or os.path.getsize(path) != len(wav):
                with open(path, 'wb') as f:
                    f.write(wav)
            snd = SoundLoader.load(path)
            if snd is None:
                return
            if is_music:
                snd.loop = True
                self.music = snd
            else:
                self.sfx[name] = snd
        except Exception:
            pass

    def play(self, name, vol=1.0):
        if not self.sfx_on:
            return
        snd = self.sfx.get(name)
        if snd is None:
            return
        try:
            snd.volume = vol
            if snd.state == 'play':
                snd.stop()
            snd.play()
        except Exception:
            pass

    def set_music(self, on):
        self.music_on = on
        if not on:
            self.music_stop()

    def music_play(self, vol):
        if not self.music_on or self.music is None:
            return
        try:
            self.music.volume = vol
            if self.music.state != 'play':
                self.music.play()
        except Exception:
            pass

    def music_stop(self):
        if self.music is None:
            return
        try:
            self.music.stop()
        except Exception:
            pass


class BrickBreakerGame(Widget):
    score = NumericProperty(0)
    lives = NumericProperty(3)
    state = StringProperty("loading")  # loading, start, playing, paused, powerups, won, lost

    def __init__(self, **kwargs):
        data_dir = kwargs.pop('data_dir', None)
        super(BrickBreakerGame, self).__init__(**kwargs)
        self.audio = Audio(data_dir)
        self._drag_uid = None
        self._last_wall_sfx = -1.0
        self.gw = GAME_W
        self.gh = 1000.0
        self.s = 1.0
        self.t = 0.0                     # animation clock
        self._amul = 1.0                 # alpha multiplier (used for fades)
        self.paddle_w = PADDLE_W0
        self.paddle_x = (self.gw - self.paddle_w) / 2
        self.paddle_y = PADDLE_Y

        self.balls = []
        self.powerups = []
        self.bricks = []
        self.is_sticky = False
        self.key_left = False
        self.key_right = False
        self._tex_cache = {}
        self._buttons = []
        self._strip_colors = random.sample(BRICK_PALETTE, 5)
        self._bricks_dirty = True
        self.brick_layer = Widget()          # bricks live on their own layer (redrawn only when they change)
        self.add_widget(self.brick_layer)
        self._make_textures()
        self._stars = [(random.random(), random.random(), random.uniform(1.0, 2.6),
                        random.uniform(0, 6.28), random.uniform(0.8, 2.2), random.uniform(4, 14))
                       for _ in range(46)]
        self._setup_loading()
        self.make_bricks()

        # Keyboard only on desktop. On Android this would pop up the soft keyboard.
        self._keyboard = None
        if platform in ('win', 'linux', 'macosx'):
            self._keyboard = Window.request_keyboard(self._keyboard_closed, self)
            if self._keyboard:
                self._keyboard.bind(on_key_down=self._on_keyboard_down)
                self._keyboard.bind(on_key_up=self._on_keyboard_up)

        Clock.schedule_interval(self.update, 1.0 / 60.0)
        self.bind(size=self._on_size, pos=self._on_size)
        Window.bind(on_keyboard=self._on_window_key)

    def _setup_loading(self):
        self.load_t = 0.0
        self._load_end = None
        n = LOAD_ROWS * LOAD_COLS
        self._tip = random.choice(TIPS)
        self._load_order = list(range(n))
        random.shuffle(self._load_order)
        self._load_colors = [random.choice(BRICK_PALETTE) for _ in range(n)]

    def on_state(self, instance, value):
        if getattr(self, 'audio', None) is None:
            return
        if value != "playing":
            self._drag_uid = None
        if value == "won":
            self.audio.play('win')
        elif value == "lost":
            self.audio.play('over')
        self._sync_music()

    def _sync_music(self):
        a = self.audio
        st = self.state
        if st == "start":
            a.music_play(0.35)
        elif st == "playing":
            a.music_play(0.5)
        elif st in ("paused", "powerups"):
            a.music_play(0.18)          # quieter while a menu is open
        elif st in ("won", "lost"):
            a.music_stop()

    # ---------- keyboard (desktop only) ----------
    def _keyboard_closed(self):
        if self._keyboard:
            self._keyboard.unbind(on_key_down=self._on_keyboard_down)
            self._keyboard.unbind(on_key_up=self._on_keyboard_up)
        self._keyboard = None

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        if keycode[1] in ['left', 'a']:
            self.key_left = True
        elif keycode[1] in ['right', 'd']:
            self.key_right = True
        elif keycode[1] == 'space':
            self.handle_space()
        elif keycode[1] == 'p':
            self.toggle_pause()
        elif keycode[1] == 'r':
            self.restart()
        return True

    def _on_keyboard_up(self, keyboard, keycode):
        if keycode[1] in ['left', 'a']:
            self.key_left = False
        elif keycode[1] in ['right', 'd']:
            self.key_right = False
        return True

    def _on_window_key(self, window, key, *args):
        # Android back button (and Esc on desktop)
        if key == 27:
            if self.state == "playing":
                self.state = "paused"
                return True
            if self.state == "powerups":
                self.state = "paused"
                return True
            if self.state == "paused":
                self.state = "playing"
                return True
        return False

    # ---------- layout ----------
    def make_bricks(self):
        """Random colors: no two neighbours (left / above) share a color."""
        self.bricks = []
        bw = (self.gw - LEFT * 2 - PAD * (COLS - 1)) / COLS
        prev_row = [None] * COLS
        for r in range(ROWS):
            left = None
            for c in range(COLS):
                choices = [col for col in BRICK_PALETTE if col != left and col != prev_row[c]]
                color = random.choice(choices)
                tough = random.random() < 0.18          # silver-framed, needs 2 hits
                self.bricks.append({
                    'r': r, 'c': c,
                    'x': LEFT + c * (bw + PAD), 'y': 0,
                    'w': bw, 'h': BRICK_H,
                    'color': color, 'hp': 2 if tough else 1, 'cracked': False,
                    'pts': (ROWS - r) * 10 + (10 if tough else 0), 'alive': True,
                })
                left = color
                prev_row[c] = color
        self.layout_bricks()

    def layout_bricks(self):
        for b in self.bricks:
            b['y'] = self.gh - TOP - b['r'] * (BRICK_H + PAD)
        self._bricks_dirty = True

    def _on_size(self, *args):
        if self.width <= 0 or self.height <= 0:
            return
        self.s = self.width / self.gw          # same scale on both axes: no stretching
        self.gh = self.height / self.s
        self.layout_bricks()
        self.paddle_x = max(0, min(self.paddle_x, self.gw - self.paddle_w))
        self.draw_everything()

    # ---------- touch ----------
    def _launch_balls(self):
        launched = False
        for ball in self.balls:
            if ball['caught']:
                ball['caught'] = False
                ball['dx'] = BALL_SPEED * random.choice([-1, 1])
                ball['dy'] = BALL_SPEED
                launched = True
        if launched:
            self.audio.play('launch')

    def _hit_button(self, touch):
        gx = (touch.x - self.x) / self.s
        gy = (touch.y - self.y) / self.s
        for key, x0, y0, x1, y1 in self._buttons:
            if x0 <= gx <= x1 and y0 <= gy <= y1:
                return key
        return None

    def on_touch_down(self, touch):
        if self.state == "loading":
            touch.ud['menu'] = True
            return True
        if self.state == "start":
            touch.ud['menu'] = True
            self.audio.play('click')
            self.state = "playing"
            self.reset_ball()
            return True
        if self.state in ("won", "lost"):
            touch.ud['menu'] = True
            self.audio.play('click')
            self.restart()
            return True
        if self.state == "paused":
            touch.ud['menu'] = True
            hit = self._hit_button(touch)
            if hit == 'sound':
                self.audio.sfx_on = not self.audio.sfx_on
                self.audio.play('click')
            elif hit == 'music':
                self.audio.set_music(not self.audio.music_on)
                self._sync_music()
                self.audio.play('click')
            elif hit:
                self.audio.play('click')
                if hit == 'resume':
                    self.state = "playing"
                elif hit == 'powerups':
                    self.state = "powerups"
                elif hit == 'restart':
                    self.restart()
            return True
        if self.state == "powerups":
            touch.ud['menu'] = True
            if self._hit_button(touch) == 'back':
                self.audio.play('click')
                self.state = "paused"
            return True
        if self.state == "playing":
            if self._hit_button(touch) == 'pause':
                touch.ud['menu'] = True
                self.audio.play('click')
                self.state = "paused"
                return True
            # Touching the screen does NOT move the paddle. It only starts a slide.
            if self._drag_uid is None:
                self._drag_uid = touch.uid
                touch.ud['x0'] = touch.x
                touch.ud['lx'] = touch.x
                touch.ud['moved'] = False
            return True

    def on_touch_move(self, touch):
        if touch.ud.get('menu'):
            return True
        if self.state == "playing" and touch.uid == self._drag_uid:
            if abs(touch.x - touch.ud['x0']) > dp(10):
                touch.ud['moved'] = True
            # the paddle follows how far the finger SLIDES, not where it is
            dx = (touch.x - touch.ud['lx']) / self.s * DRAG_SENS
            touch.ud['lx'] = touch.x
            self.paddle_x = max(0, min(self.paddle_x + dx, self.gw - self.paddle_w))
            return True

    def on_touch_up(self, touch):
        if touch.uid == self._drag_uid:
            self._drag_uid = None
            # a quick tap (no sliding) launches the ball
            if not touch.ud.get('moved') and self.state == "playing":
                self._launch_balls()
            return True
        return False

    # ---------- game flow ----------
    def spawn_ball(self, x, y, dx, dy, caught=False):
        self.balls.append({'x': x, 'y': y, 'dx': dx, 'dy': dy, 'caught': caught})

    def reset_ball(self):
        self.balls.clear()
        self.powerups.clear()
        self.paddle_w = PADDLE_W0
        self.is_sticky = False
        self.paddle_x = max(0, min(self.paddle_x, self.gw - self.paddle_w))
        self.spawn_ball(self.paddle_x + self.paddle_w / 2,
                        self.paddle_y + PADDLE_H + BALL_R, 0, 0, caught=True)

    def handle_space(self):
        if self.state == "start":
            self.state = "playing"
            self.reset_ball()
        elif self.state == "playing":
            self._launch_balls()

    def toggle_pause(self):
        if self.state == "playing":
            self.state = "paused"
        elif self.state == "paused":
            self.state = "playing"

    def restart(self):
        self.paddle_w = PADDLE_W0
        self.paddle_x = (self.gw - self.paddle_w) / 2
        self.score, self.lives = 0, 3
        self.state = "playing"
        self.make_bricks()
        self.reset_ball()

    def apply_powerup(self, p_type):
        self.audio.play(POWERUP_SFX.get(p_type, 'click'))
        if p_type == "expand":
            self.paddle_w = min(180, self.paddle_w + 30)
            self.paddle_x = max(0, min(self.paddle_x, self.gw - self.paddle_w))
        elif p_type == "sticky":
            self.is_sticky = True
        elif p_type == "multiball":
            self.spawn_ball(self.gw / 2, self.gh / 2,
                            random.choice([-BALL_SPEED * 0.8, BALL_SPEED * 0.8]), BALL_SPEED)

    def update(self, dt):
        self.t += dt

        if self.state == "loading":
            self.load_t += dt
            self.audio.load_next()              # one sound per frame
            if self._load_end is None and self.load_t >= LOAD_TIME and self.audio.ready:
                self._load_end = self.load_t + 0.4      # start fading out
            if self._load_end is not None and self.load_t >= self._load_end:
                self.state = "start"
            self.draw_everything()
            return

        if self.state != "playing":
            self.draw_everything()
            return

        # Desktop keyboard movement
        if self.key_left:
            self.paddle_x = max(0, self.paddle_x - 8)
        if self.key_right:
            self.paddle_x = min(self.gw - self.paddle_w, self.paddle_x + 8)

        # Caught balls ride on the paddle
        for ball in self.balls:
            if ball['caught']:
                ball['x'] = self.paddle_x + self.paddle_w / 2
                ball['y'] = self.paddle_y + PADDLE_H + BALL_R

        # Falling powerups
        for p in self.powerups[:]:
            p['y'] -= 3
            if (self.paddle_y - 10 <= p['y'] <= self.paddle_y + PADDLE_H
                    and self.paddle_x <= p['x'] <= self.paddle_x + self.paddle_w):
                self.apply_powerup(p['type'])
                self.powerups.remove(p)
            elif p['y'] < 0:
                self.powerups.remove(p)

        # Balls
        for ball in self.balls[:]:
            if ball['caught']:
                continue
            ball['x'] += ball['dx']
            ball['y'] += ball['dy']

            # Walls (always push the ball away from the wall to avoid sticking)
            bounced = False
            if ball['x'] - BALL_R <= 0:
                bounced = bounced or ball['dx'] < 0
                ball['dx'] = abs(ball['dx'])
            elif ball['x'] + BALL_R >= self.gw:
                bounced = bounced or ball['dx'] > 0
                ball['dx'] = -abs(ball['dx'])
            if ball['y'] + BALL_R >= self.gh:
                bounced = bounced or ball['dy'] > 0
                ball['dy'] = -abs(ball['dy'])
            if bounced and self.t - self._last_wall_sfx > 0.06:
                self._last_wall_sfx = self.t
                self.audio.play('wall', 0.6)

            # Paddle (only when the ball is moving down)
            if (ball['dy'] < 0
                    and self.paddle_y <= ball['y'] - BALL_R <= self.paddle_y + PADDLE_H
                    and self.paddle_x <= ball['x'] <= self.paddle_x + self.paddle_w):
                self.audio.play('paddle')
                if self.is_sticky:
                    ball['caught'] = True
                    ball['dx'], ball['dy'] = 0, 0
                    ball['y'] = self.paddle_y + PADDLE_H + BALL_R
                    continue
                hit = (ball['x'] - self.paddle_x) / self.paddle_w - 0.5
                ball['dx'] = hit * BALL_SPEED * 2
                ball['dy'] = abs(ball['dy'])

            # Bricks
            for b in self.bricks:
                if not b['alive']:
                    continue
                if (b['x'] <= ball['x'] <= b['x'] + b['w']
                        and b['y'] <= ball['y'] <= b['y'] + b['h']):
                    b['hp'] -= 1
                    self._bricks_dirty = True
                    if b['hp'] <= 0:
                        b['alive'] = False
                        self.score += b['pts']
                        self.audio.play('brick%d' % (3 - min(3, b['r'] // 2)))   # higher rows = higher pitch
                        if random.random() < 0.25:
                            self.powerups.append({
                                'x': b['x'] + b['w'] / 2, 'y': b['y'],
                                'type': random.choice(list(POWERUP_STYLE.keys())),
                            })
                    else:
                        b['cracked'] = True
                        self.audio.play('tough')
                    ball['dy'] = -ball['dy']
                    break

            # Fell off the bottom
            if ball['y'] < 0:
                self.balls.remove(ball)

        # Lost all balls
        if not self.balls:
            self.lives -= 1
            if self.lives <= 0:
                self.state = "lost"
            else:
                self.audio.play('life')
                self.reset_ball()

        if all(not b['alive'] for b in self.bricks):
            self.state = "won"
        self.draw_everything()

    # ---------- background ----------
    def _make_textures(self):
        """A smooth gradient and a soft round glow, built once. Falls back to a flat color on any error."""
        self._bg_tex = None
        self._glow_tex = None
        try:
            stops = [(0.0, (0.04, 0.11, 0.21)), (0.5, (0.09, 0.08, 0.25)), (1.0, (0.03, 0.04, 0.11))]
            n = 128
            buf = bytearray()
            for i in range(n):
                f = i / (n - 1.0)
                k = 0 if f <= 0.5 else 1
                f0, c0 = stops[k]
                f1, c1 = stops[k + 1]
                u = (f - f0) / (f1 - f0)
                buf += bytes([int((c0[j] + (c1[j] - c0[j]) * u) * 255) for j in range(3)]) + b'\xff'
            tex = Texture.create(size=(1, n), colorfmt='rgba')
            tex.blit_buffer(bytes(buf), colorfmt='rgba', bufferfmt='ubyte')
            self._bg_tex = tex

            size = 64
            gb = bytearray()
            for yy in range(size):
                for xx in range(size):
                    d = math.hypot((xx + 0.5) / size * 2 - 1, (yy + 0.5) / size * 2 - 1)
                    a = max(0.0, 1.0 - d)
                    a = a * a * (3 - 2 * a)
                    gb += bytes([255, 255, 255, int(a * 255)])
            gt = Texture.create(size=(size, size), colorfmt='rgba')
            gt.blit_buffer(bytes(gb), colorfmt='rgba', bufferfmt='ubyte')
            self._glow_tex = gt
        except Exception:
            self._bg_tex = None
            self._glow_tex = None

    def _glow(self, gx, gy, rw, rh, color):
        if self._glow_tex is None:
            return
        s = self.s
        self._color(color)
        Rectangle(texture=self._glow_tex,
                  pos=(self.x + (gx - rw) * s, self.y + (gy - rh) * s),
                  size=(2 * rw * s, 2 * rh * s))

    def _draw_background(self):
        s = self.s
        if self._bg_tex is not None:
            Color(1, 1, 1, 1)
            Rectangle(texture=self._bg_tex, pos=self.pos, size=self.size)
        else:
            Color(0.06, 0.09, 0.16, 1)
            Rectangle(pos=self.pos, size=self.size)

        # slow-moving colored nebula glows
        sway = math.sin(self.t * 0.25) * 18
        self._glow(self.gw * 0.18 + sway, self.gh * 0.80, 300, 300, (0.55, 0.30, 0.95, 0.22))
        self._glow(self.gw * 0.88 - sway, self.gh * 0.40, 320, 320, (0.15, 0.65, 0.95, 0.16))
        self._glow(self.gw * 0.50, self.gh * 0.58, 230, 230, (0.95, 0.35, 0.65, 0.07))
        # soft light on the floor around the paddle
        self._glow(self.gw * 0.5, self.paddle_y, 400, 130, (0.20, 0.70, 0.97, 0.20))

        # twinkling stars drifting slowly downward
        for fx, fy, sz, ph, sp, drift in self._stars:
            gx = fx * self.gw
            gy = (fy * self.gh - self.t * drift) % self.gh
            a = 0.25 + 0.55 * (0.5 + 0.5 * math.sin(self.t * sp + ph))
            Color(0.80, 0.88, 1.0, a)
            Rectangle(pos=(self.x + (gx - sz / 2) * s, self.y + (gy - sz / 2) * s), size=(sz * s, sz * s))

    def _redraw_bricks(self):
        layer = self.brick_layer
        layer.canvas.clear()
        with layer.canvas:
            for b in self.bricks:
                if b['alive']:
                    self._draw_brick(b)
        self._bricks_dirty = False

    # ---------- drawing primitives (all coordinates are game units) ----------
    def _text_tex(self, text, px):
        key = (text, px)
        tex = self._tex_cache.get(key)
        if tex is None:
            if len(self._tex_cache) > 250:
                self._tex_cache.clear()
            lbl = CoreLabel(text=text, font_size=px, bold=True)
            lbl.refresh()
            tex = lbl.texture
            self._tex_cache[key] = tex
        return tex

    def _color(self, c):
        a = c[3] if len(c) > 3 else 1.0
        Color(c[0], c[1], c[2], a * self._amul)

    def _draw_text(self, text, gx, gy, size, color=(1, 1, 1, 1), align='center'):
        s = self.s
        tex = self._text_tex(text, max(8, int(size * s)))
        self._color(color)
        px = self.x + gx * s
        if align == 'center':
            px -= tex.width / 2
        Rectangle(texture=tex, pos=(px, self.y + gy * s - tex.height / 2), size=tex.size)

    def _circle(self, gx, gy, r, color):
        s = self.s
        self._color(color)
        Ellipse(pos=(self.x + (gx - r) * s, self.y + (gy - r) * s), size=(2 * r * s, 2 * r * s))

    def _rect(self, gx, gy, w, h, color):
        s = self.s
        self._color(color)
        Rectangle(pos=(self.x + gx * s, self.y + gy * s), size=(w * s, h * s))

    def _rrect(self, gx, gy, w, h, r, color):
        s = self.s
        self._color(color)
        RoundedRectangle(pos=(self.x + gx * s, self.y + gy * s), size=(w * s, h * s), radius=[r * s])

    def _rborder(self, gx, gy, w, h, r, color, width=2):
        s = self.s
        self._color(color)
        Line(rounded_rectangle=(self.x + gx * s, self.y + gy * s, w * s, h * s, r * s),
             width=max(1.0, width * s))

    def _tri(self, pts, color):
        s = self.s
        self._color(color)
        flat = []
        for (gx, gy) in pts:
            flat += [self.x + gx * s, self.y + gy * s]
        Triangle(points=flat)

    def _quad(self, pts, color):
        s = self.s
        self._color(color)
        flat = []
        for (gx, gy) in pts:
            flat += [self.x + gx * s, self.y + gy * s]
        Quad(points=flat)

    def _draw_overlay(self, alpha):
        Color(0.02, 0.04, 0.09, alpha)
        Rectangle(pos=self.pos, size=self.size)

    # ---------- small icons used on buttons ----------
    def _draw_icon(self, kind, gx, gy, k, color=(1, 1, 1, 1)):
        s = self.s
        if kind == 'play':
            self._tri([(gx - k * 0.55, gy - k * 0.8), (gx - k * 0.55, gy + k * 0.8),
                       (gx + k * 0.85, gy)], color)
        elif kind == 'back':
            self._tri([(gx + k * 0.6, gy - k * 0.8), (gx + k * 0.6, gy + k * 0.8),
                       (gx - k * 0.85, gy)], color)
        elif kind == 'sparkle':
            w = k * 0.3
            self._quad([(gx, gy + k), (gx + w, gy), (gx, gy - k), (gx - w, gy)], color)
            self._quad([(gx - k, gy), (gx, gy + w), (gx + k, gy), (gx, gy - w)], color)
        elif kind == 'restart':
            R = k * 0.75
            a0, a1 = math.radians(40), math.radians(330)   # clockwise from the top
            pts = []
            n = 24
            for i in range(n + 1):
                a = a0 + (a1 - a0) * i / n
                pts += [self.x + (gx + R * math.sin(a)) * s, self.y + (gy + R * math.cos(a)) * s]
            self._color(color)
            Line(points=pts, width=max(2.0, 3.2 * s))
            ex, ey = gx + R * math.sin(a1), gy + R * math.cos(a1)
            tx, ty = math.cos(a1), -math.sin(a1)            # direction of travel at the end
            nx, ny = -ty, tx
            hs = k * 0.6
            self._tri([(ex + tx * hs, ey + ty * hs),
                       (ex + nx * hs * 0.85, ey + ny * hs * 0.85),
                       (ex - nx * hs * 0.85, ey - ny * hs * 0.85)], color)

    # ---------- power-up pictures (white drawings inside the colored circle) ----------
    def _draw_pictogram(self, key, gx, gy, k=1.15):
        white = (1, 1, 1, 1)
        if key == 'expand':
            # a paddle with arrows pointing outward
            self._rrect(gx - 14 * k, gy - 4 * k, 28 * k, 8 * k, 3 * k, white)
            self._tri([(gx - 33 * k, gy), (gx - 20 * k, gy + 9 * k), (gx - 20 * k, gy - 9 * k)], white)
            self._tri([(gx + 33 * k, gy), (gx + 20 * k, gy + 9 * k), (gx + 20 * k, gy - 9 * k)], white)
        elif key == 'multiball':
            # three balls
            self._circle(gx, gy + 12 * k, 9 * k, white)
            self._circle(gx - 14 * k, gy - 9 * k, 9 * k, white)
            self._circle(gx + 14 * k, gy - 9 * k, 9 * k, white)
        elif key == 'sticky':
            # ball resting on a paddle with glue drips
            self._rrect(gx - 26 * k, gy - 20 * k, 52 * k, 9 * k, 3 * k, white)
            self._circle(gx, gy + 2 * k, 11 * k, white)
            self._circle(gx - 15 * k, gy - 27 * k, 3.5 * k, white)
            self._circle(gx + 9 * k, gy - 29 * k, 3.5 * k, white)

    def _draw_powerup_badge(self, key, gx, gy, r, pulse):
        """Same picture as the Power-ups page, used for the falling pick-ups."""
        color = POWERUP_STYLE[key][0]
        self._circle(gx, gy, r * 1.3, (color[0], color[1], color[2], 0.14 + 0.10 * pulse))
        self._circle(gx, gy, r + 1.5, (color[0] * 0.6, color[1] * 0.6, color[2] * 0.6, 1))
        self._circle(gx, gy + 0.8, r, color)
        self._draw_pictogram(key, gx, gy, r / 44.0 * 1.15)

    # ---------- game objects ----------
    def _draw_brick(self, b):
        s = self.s
        x0 = self.x + b['x'] * s
        y0 = self.y + b['y'] * s
        w = b['w'] * s
        h = b['h'] * s
        c = b['color']
        if b['hp'] > 1:
            # tough brick: silver frame around a darker inner bevel
            Color(0.86, 0.89, 0.93, 1)
            Rectangle(pos=(x0, y0), size=(w, h))
            i = 2.5 * s
            Color(c[0] * 0.55, c[1] * 0.55, c[2] * 0.55, 1)
            Rectangle(pos=(x0 + i, y0 + i), size=(w - 2 * i, h - 2 * i))
            Color(c[0], c[1], c[2], 1)
            Rectangle(pos=(x0 + i, y0 + i + 2 * s), size=(w - 2 * i, h - 2 * i - 2 * s))
            Color(1, 1, 1, 0.28)
            Rectangle(pos=(x0 + i + 2 * s, y0 + h - i - 4 * s), size=(w - 2 * i - 4 * s, 2 * s))
        else:
            Color(c[0] * 0.58, c[1] * 0.58, c[2] * 0.58, 1)       # dark lower edge
            Rectangle(pos=(x0, y0), size=(w, h))
            Color(c[0], c[1], c[2], 1)                             # face
            Rectangle(pos=(x0, y0 + 3 * s), size=(w, h - 3 * s))
            Color(1, 1, 1, 0.30)                                   # shine
            Rectangle(pos=(x0 + 2 * s, y0 + h - 6 * s), size=(w - 4 * s, 3 * s))
        if b['cracked']:
            Color(0, 0, 0, 0.6)
            Line(points=[x0 + w * 0.30, y0 + h, x0 + w * 0.42, y0 + h * 0.62,
                         x0 + w * 0.33, y0 + h * 0.40, x0 + w * 0.52, y0 + h * 0.12,
                         x0 + w * 0.50, y0],
                 width=max(1.0, 1.5 * s))
            Line(points=[x0 + w * 0.42, y0 + h * 0.62, x0 + w * 0.62, y0 + h * 0.50,
                         x0 + w * 0.74, y0 + h * 0.20],
                 width=max(1.0, 1.2 * s))

    def _draw_paddle(self, pulse):
        x, y, w, h = self.paddle_x, self.paddle_y, self.paddle_w, PADDLE_H
        r = h / 2.0
        if self.is_sticky:
            col = (0.72, 0.40, 0.92, 1)
        else:
            col = (0.22, 0.74, 0.97, 1)
        dark = (col[0] * 0.45, col[1] * 0.45, col[2] * 0.45, 1)

        # neon glow
        self._rrect(x - 10, y - 10, w + 20, h + 20, r + 10, (col[0], col[1], col[2], 0.07 + 0.04 * pulse))
        self._rrect(x - 5, y - 5, w + 10, h + 10, r + 5, (col[0], col[1], col[2], 0.12 + 0.05 * pulse))
        # body: dark lower edge, bright face, top shine
        self._rrect(x, y - 3, w, h, r, dark)
        self._rrect(x, y, w, h, r, col)
        self._rrect(x + r, y + h * 0.56, w - 2 * r, h * 0.30, h * 0.15, (1, 1, 1, 0.5))
        # darker end bumpers and a center badge
        self._circle(x + r, y + h / 2, r * 0.62, (dark[0], dark[1], dark[2], 0.6))
        self._circle(x + w - r, y + h / 2, r * 0.62, (dark[0], dark[1], dark[2], 0.6))
        self._rrect(x + w / 2 - 15, y + h * 0.30, 30, h * 0.40, h * 0.20, (dark[0], dark[1], dark[2], 0.5))
        # sticky: wobbling glue drips under the paddle
        if self.is_sticky:
            for i in range(4):
                px = x + w * (i + 1) / 5.0
                d = 6 + 3 * math.sin(self.t * 3 + i * 1.7)
                self._rect(px - 1.5, y - 3 - d, 3, d + 3, col)
                self._circle(px, y - 3 - d, 3.6, col)

    def _draw_ball(self, ball, pulse):
        self._circle(ball['x'], ball['y'], BALL_R + 7, (0.7, 0.88, 1, 0.14 + 0.06 * pulse))
        self._circle(ball['x'], ball['y'], BALL_R, (0.86, 0.93, 1, 1))
        self._circle(ball['x'] - 2.5, ball['y'] + 2.5, BALL_R * 0.38, (1, 1, 1, 1))

    # ---------- buttons and menus ----------
    def _draw_button(self, key, label, icon, cx, cy, w, h, color):
        x, y = cx - w / 2, cy - h / 2
        dark = (color[0] * 0.55, color[1] * 0.55, color[2] * 0.55, 1)
        self._rrect(x, y - 7, w, h, 18, (0, 0, 0, 0.45))             # drop shadow
        self._rrect(x, y - 4, w, h, 18, dark)                         # 3D edge
        self._rrect(x, y, w, h, 18, color)                            # face
        self._rrect(x + 6, y + h * 0.5, w - 12, h * 0.5 - 6, 12, (1, 1, 1, 0.15))  # gloss
        self._rborder(x, y, w, h, 18, (1, 1, 1, 0.35), 1.5)
        self._draw_icon(icon, x + 50, cy, 15)
        self._draw_text(label, cx + 20, cy, 25)
        self._buttons.append((key, x, y - 4, x + w, y + h))

    def _draw_toggle(self, key, label, on, cx, cy, w, h):
        x, y = cx - w / 2, cy - h / 2
        col = (0.18, 0.62, 0.38, 1) if on else (0.34, 0.37, 0.45, 1)
        dark = (col[0] * 0.55, col[1] * 0.55, col[2] * 0.55, 1)
        self._rrect(x, y - 6, w, h, 14, (0, 0, 0, 0.45))
        self._rrect(x, y - 3, w, h, 14, dark)
        self._rrect(x, y, w, h, 14, col)
        self._rrect(x + 5, y + h * 0.5, w - 10, h * 0.5 - 5, 9, (1, 1, 1, 0.13))
        self._rborder(x, y, w, h, 14, (1, 1, 1, 0.3), 1.2)
        self._draw_text("%s: %s" % (label, "ON" if on else "OFF"), cx, cy, 20)
        self._buttons.append((key, x, y - 3, x + w, y + h))

    def _draw_pause_menu(self, cx, cy):
        pulse = 0.5 + 0.5 * math.sin(self.t * 3)
        self._draw_overlay(0.74)

        pw, ph = 440, 500
        x, y = cx - pw / 2, cy - 262

        # soft pulsing glow around the panel
        for i in (3, 2, 1, 0):
            self._rrect(x - 5 - i * 6, y - 5 - i * 6, pw + 10 + i * 12, ph + 10 + i * 12,
                        30 + i * 5, (0.22, 0.74, 0.97, 0.035 + 0.02 * pulse))
        self._rrect(x, y - 9, pw, ph, 28, (0, 0, 0, 0.5))           # shadow
        self._rrect(x, y, pw, ph, 28, (0.08, 0.12, 0.22, 0.98))      # panel
        self._rrect(x + 8, y + ph * 0.55, pw - 16, ph * 0.45 - 8, 22, (1, 1, 1, 0.04))
        self._rborder(x, y, pw, ph, 28, (0.22, 0.74, 0.97, 0.5 + 0.35 * pulse), 2.5)

        # row of mini bricks as decoration
        sx0 = cx - (5 * 40 + 4 * 6) / 2
        for i, col in enumerate(self._strip_colors):
            self._rrect(sx0 + i * 46, cy + 205, 40, 16, 4, col)
            self._rrect(sx0 + i * 46 + 3, cy + 212, 34, 5, 2, (1, 1, 1, 0.25))

        # title with glow
        self._draw_text("PAUSED", cx, cy + 160, 48, (0.22, 0.74, 0.97, 0.22 + 0.2 * pulse))
        self._draw_text("PAUSED", cx, cy + 160, 42, (0.85, 0.95, 1, 1))
        self._draw_text("Score %d     Lives %d" % (self.score, self.lives), cx, cy + 118, 20,
                        (0.6, 0.68, 0.78, 1))

        # buttons
        self._draw_button('resume', "Resume", 'play', cx, cy + 50, 360, 66, (0.18, 0.62, 0.38, 1))
        self._draw_button('powerups', "Power-ups?", 'sparkle', cx, cy - 40, 360, 66, (0.20, 0.45, 0.80, 1))
        self._draw_button('restart', "Restart", 'restart', cx, cy - 130, 360, 66, (0.72, 0.28, 0.28, 1))
        self._draw_toggle('music', "Music", self.audio.music_on, cx - 92, cy - 215, 172, 54)
        self._draw_toggle('sound', "Sound", self.audio.sfx_on, cx + 92, cy - 215, 172, 54)

    def _draw_powerups_page(self, cx, cy):
        pulse = 0.5 + 0.5 * math.sin(self.t * 3)
        self._draw_overlay(0.97)
        self._draw_text("POWER-UPS", cx, cy + 300, 40, ACCENT)
        self._rrect(cx - 75, cy + 268, 150, 4, 2, (0.22, 0.74, 0.97, 0.8))

        items = [
            ('expand', "Wide Paddle",
             ["Your paddle gets wider,", "so it's easier to catch the ball."]),
            ('multiball', "Multi-Ball",
             ["The balls will multiply with this.", "An extra ball joins the game."]),
            ('sticky', "Sticky Paddle",
             ["The ball sticks to your paddle.", "Tap to launch it again."]),
        ]
        for i, (key, name, lines) in enumerate(items):
            color = POWERUP_STYLE[key][0]
            yc = cy + 150 - i * 160
            x, w, h = cx - 270, 540, 140
            by = yc - h / 2
            self._rrect(x, by - 6, w, h, 22, (0, 0, 0, 0.45))
            self._rrect(x, by, w, h, 22, (0.09, 0.13, 0.23, 1))
            self._rrect(x + 5, by + h * 0.5, w - 10, h * 0.5 - 5, 18, (1, 1, 1, 0.04))
            self._rborder(x, by, w, h, 22, (color[0], color[1], color[2], 0.65), 2)

            self._draw_powerup_badge(key, x + 82, yc, 44, pulse)

            self._draw_text(name, x + 150, yc + 34, 26, color, align='left')
            for j, line in enumerate(lines):
                self._draw_text(line, x + 150, yc - 4 - j * 28, 18, (0.86, 0.89, 0.93, 1), align='left')

        self._draw_text("Catch falling power-ups with your paddle.", cx, cy - 275, 18,
                        (0.6, 0.67, 0.76, 1))
        self._draw_button('back', "Back", 'back', cx, cy - 345, 300, 62, (0.20, 0.45, 0.80, 1))

    # ---------- loading screen ----------
    def _draw_loading(self, cx, cy):
        p = min(1.0, self.load_t / LOAD_TIME)
        if self._load_end is None:
            p = min(p, 0.97)                                      # wait at 97% until the sounds are loaded
            fade = 1.0
        else:
            fade = max(0.0, min(1.0, (self._load_end - self.load_t) / 0.4))   # fades out at the end
        e = p * p * (3 - 2 * p)                                   # smooth progress

        Color(0.06, 0.09, 0.16, fade)
        Rectangle(pos=self.pos, size=self.size)
        self._amul = fade

        # soft glow behind the logo
        for rad, al in ((270, 0.025), (205, 0.03), (145, 0.04)):
            self._circle(cx, cy + 170, rad, (0.22, 0.74, 0.97, al))

        # a wall of random-colored bricks that builds up as the bar fills
        bw, bh, gap = 40, 16, 6
        x0 = cx - (LOAD_COLS * bw + (LOAD_COLS - 1) * gap) / 2
        ytop = cy + 215
        n = LOAD_ROWS * LOAD_COLS
        for r in range(LOAD_ROWS):
            for c in range(LOAD_COLS):
                i = r * LOAD_COLS + c
                t = max(0.0, min(1.0, (e * (n + 6) - self._load_order[i]) / 5.0))
                if t <= 0:
                    continue
                sc = 0.4 + 0.6 * t                                  # pop-in
                col = self._load_colors[i]
                w_, h_ = bw * sc, bh * sc
                bx = x0 + c * (bw + gap) + bw / 2 - w_ / 2
                by = ytop - r * (bh + gap) - bh / 2 - h_ / 2
                self._rect(bx, by, w_, h_, (col[0] * 0.58, col[1] * 0.58, col[2] * 0.58, t))
                self._rect(bx, by + 3 * sc, w_, h_ - 3 * sc, (col[0], col[1], col[2], t))
                self._rect(bx + 2, by + h_ - 6 * sc, max(0.0, w_ - 4), 3 * sc, (1, 1, 1, 0.3 * t))

        # title
        self._draw_text("BRICK BREAKER", cx, cy + 60, 50, (0.22, 0.74, 0.97, 0.25))
        self._draw_text("BRICK BREAKER", cx, cy + 60, 44, (0.87, 0.95, 1, 1))
        self._draw_text("Smash every brick!", cx, cy + 15, 22, (0.55, 0.63, 0.75, 1))

        # progress bar with a ball at the head
        barw, barh = 420, 20
        bx, by = cx - barw / 2, cy - 80
        fill = max(barh, barw * e)
        self._rrect(bx, by, barw, barh, 10, (1, 1, 1, 0.10))
        self._rrect(bx, by, fill, barh, 10, (0.20, 0.55, 0.95, 1))
        self._rrect(bx + 3, by + barh * 0.5, max(1.0, fill - 6), barh * 0.4, 4, (1, 1, 1, 0.25))
        self._rborder(bx, by, barw, barh, 10, (1, 1, 1, 0.25), 1.5)
        hx = bx + max(barh / 2.0, barw * e)
        self._circle(hx, by + barh / 2, 22, (0.55, 0.85, 1, 0.22))
        self._circle(hx, by + barh / 2, 13, (0.86, 0.93, 1, 1))
        self._circle(hx - 3, by + barh / 2 + 3, 5, (1, 1, 1, 1))

        self._draw_text("Loading... %d%%" % int(e * 100), cx, cy - 125, 22, (0.85, 0.9, 0.95, 1))
        self._draw_text(self._tip, cx, cy - 190, 18, (0.55, 0.63, 0.75, 1))

        self._amul = 1.0

    # ---------- main draw ----------
    def draw_everything(self):
        if self._bricks_dirty:
            self._redraw_bricks()
        # Three layers, drawn in this order: canvas.before (background), canvas (holds the
        # bricks' layer, never cleared!), canvas.after (everything else).
        self.canvas.before.clear()
        with self.canvas.before:
            self._draw_background()
        self.canvas.after.clear()
        self._buttons = []
        with self.canvas.after:
            s = self.s
            pulse = 0.5 + 0.5 * math.sin(self.t * 3)

            # Paddle
            self._draw_paddle(pulse)

            # Falling powerups: same pictures as the Power-ups page
            for p in self.powerups:
                self._draw_powerup_badge(p['type'], p['x'], p['y'], 26, pulse)

            # Balls
            for ball in self.balls:
                self._draw_ball(ball, pulse)

            # HUD
            hud_y = self.gh - 55
            self._rrect(30, hud_y - 20, 140, 40, 20, (1, 1, 1, 0.08))
            self._rrect(self.gw - 170, hud_y - 20, 140, 40, 20, (1, 1, 1, 0.08))
            self._draw_text("Score: %d" % self.score, 100, hud_y, 21)
            self._draw_text("Lives: %d" % self.lives, self.gw - 100, hud_y, 21)

            cx, cy = self.gw / 2, self.gh / 2

            # Pause button (top centre) while playing
            if self.state == "playing":
                bx, by = self.gw / 2, hud_y
                self._circle(bx, by, 27, (1, 1, 1, 0.10))
                Color(1, 1, 1, 0.4)
                Line(circle=(self.x + bx * s, self.y + by * s, 27 * s), width=max(1.0, 1.5 * s))
                self._rrect(bx - 9, by - 12, 6, 24, 2, (1, 1, 1, 0.95))
                self._rrect(bx + 3, by - 12, 6, 24, 2, (1, 1, 1, 0.95))
                self._buttons.append(('pause', bx - 40, by - 34, bx + 40, by + 34))

            # Messages and menus
            if self.state in ("start", "loading"):
                self._draw_overlay(0.45)
                self._draw_text("BRICK BREAKER", cx, cy + 25, 40, (0.22, 0.74, 0.97, 0.25 + 0.2 * pulse))
                self._draw_text("BRICK BREAKER", cx, cy + 25, 36, (0.85, 0.95, 1, 1))
                self._draw_text("Tap to start", cx, cy - 25, 24, (1, 1, 1, 0.55 + 0.45 * pulse))
                self._draw_text("Slide your finger to move the paddle", cx, cy - 75, 18, (0.7, 0.78, 0.88, 1))
            elif self.state == "paused":
                self._draw_pause_menu(cx, cy)
            elif self.state == "powerups":
                self._draw_powerups_page(cx, cy)
            elif self.state == "won":
                self._draw_overlay(0.6)
                self._draw_text("You win!", cx, cy + 25, 40, (0.18, 0.80, 0.44, 1))
                self._draw_text("Score: %d" % self.score, cx, cy - 15, 22, (0.85, 0.9, 0.95, 1))
                self._draw_text("Tap to play again", cx, cy - 55, 24, (1, 1, 1, 0.55 + 0.45 * pulse))
            elif self.state == "lost":
                self._draw_overlay(0.6)
                self._draw_text("Game over", cx, cy + 25, 40, (0.91, 0.30, 0.24, 1))
                self._draw_text("Score: %d" % self.score, cx, cy - 15, 22, (0.85, 0.9, 0.95, 1))
                self._draw_text("Tap to play again", cx, cy - 55, 24, (1, 1, 1, 0.55 + 0.45 * pulse))
            elif self.state == "playing" and any(b['caught'] for b in self.balls):
                self._draw_text("Slide to move, tap to launch", cx, self.paddle_y + 120, 22,
                                (0.8, 0.85, 0.9, 0.55 + 0.45 * pulse))

            # Loading screen sits on top of everything and fades out into the start screen
            if self.state == "loading":
                self._draw_loading(cx, cy)


class BrickBreakerApp(App):
    def build(self):
        data_dir = self.user_data_dir
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception:
            data_dir = None
        return BrickBreakerGame(data_dir=data_dir)

    def on_pause(self):
        # Auto-pause (and silence the music) when the app goes to the background.
        game = self.root
        if game is not None:
            if game.state == "playing":
                game.state = "paused"
            game.audio.music_stop()
        return True

    def on_resume(self):
        game = self.root
        if game is not None:
            game._sync_music()


if __name__ == '__main__':
    BrickBreakerApp().run()
