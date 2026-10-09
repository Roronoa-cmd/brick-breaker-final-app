import random
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.properties import NumericProperty, StringProperty
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, Ellipse
from kivy.utils import platform

# Virtual game width. Height adapts to the phone's shape, so nothing is stretched.
GAME_W = 600
PADDLE_H = 14
PADDLE_Y = 100
PADDLE_W0 = 100
BALL_R = 8
BALL_SPEED = 5
ROWS, COLS = 5, 10
BRICK_H = 24
PAD, TOP, LEFT = 4, 100, 20

COLORS = [
    [0.91, 0.30, 0.24, 1],  # Red
    [0.90, 0.49, 0.13, 1],  # Orange
    [0.95, 0.77, 0.06, 1],  # Yellow
    [0.18, 0.80, 0.44, 1],  # Green
    [0.20, 0.60, 0.86, 1],  # Blue
]
DURABLE_COLOR = [0.50, 0.55, 0.55, 1]
CRACKED_COLOR = [0.74, 0.76, 0.78, 1]

# Each powerup has its own color and letter so you can tell them apart.
POWERUP_STYLE = {
    'expand':    ([0.18, 0.80, 0.44, 1], 'W'),  # green  W = wider paddle
    'multiball': ([0.95, 0.60, 0.10, 1], 'M'),  # orange M = extra ball
    'sticky':    ([0.69, 0.35, 0.85, 1], 'S'),  # purple S = sticky paddle
}

Window.clearcolor = (0.06, 0.09, 0.16, 1)


class BrickBreakerGame(Widget):
    score = NumericProperty(0)
    lives = NumericProperty(3)
    state = StringProperty("start")  # start, playing, paused, won, lost

    def __init__(self, **kwargs):
        super(BrickBreakerGame, self).__init__(**kwargs)
        self.gw = GAME_W
        self.gh = 1000.0
        self.s = 1.0
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

    # ---------- layout ----------
    def make_bricks(self):
        self.bricks = []
        bw = (self.gw - LEFT * 2 - PAD * (COLS - 1)) / COLS
        for r in range(ROWS):
            for c in range(COLS):
                hp = 2 if r == 0 else 1
                self.bricks.append({
                    'r': r, 'c': c,
                    'x': LEFT + c * (bw + PAD), 'y': 0,
                    'w': bw, 'h': BRICK_H,
                    'color': DURABLE_COLOR if hp == 2 else COLORS[r % len(COLORS)],
                    'hp': hp, 'pts': (ROWS - r) * 10, 'alive': True,
                })
        self.layout_bricks()

    def layout_bricks(self):
        for b in self.bricks:
            b['y'] = self.gh - TOP - b['r'] * (BRICK_H + PAD)

    def _on_size(self, *args):
        if self.width <= 0 or self.height <= 0:
            return
        self.s = self.width / self.gw          # same scale on both axes: no stretching
        self.gh = self.height / self.s
        self.layout_bricks()
        self.paddle_x = max(0, min(self.paddle_x, self.gw - self.paddle_w))
        self.draw_everything()

    # ---------- touch ----------
    def _move_paddle_to(self, touch):
        tx = (touch.x - self.x) / self.s
        self.paddle_x = max(0, min(tx - self.paddle_w / 2, self.gw - self.paddle_w))

    def _launch_balls(self):
        for ball in self.balls:
            if ball['caught']:
                ball['caught'] = False
                ball['dx'] = BALL_SPEED * random.choice([-1, 1])
                ball['dy'] = BALL_SPEED

    def on_touch_down(self, touch):
        if self.state == "start":
            self.state = "playing"
            self.reset_ball()
            return True
        if self.state in ("won", "lost"):
            self.restart()
            return True
        if self.state == "paused":
            self.state = "playing"
            return True
        if self.state == "playing":
            self._launch_balls()
            self._move_paddle_to(touch)
            return True

    def on_touch_move(self, touch):
        if self.state == "playing":
            self._move_paddle_to(touch)
            return True

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
        if p_type == "expand":
            self.paddle_w = min(180, self.paddle_w + 30)
            self.paddle_x = max(0, min(self.paddle_x, self.gw - self.paddle_w))
        elif p_type == "sticky":
            self.is_sticky = True
        elif p_type == "multiball":
            self.spawn_ball(self.gw / 2, self.gh / 2,
                            random.choice([-BALL_SPEED * 0.8, BALL_SPEED * 0.8]), BALL_SPEED)

    def update(self, dt):
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
            if ball['x'] - BALL_R <= 0:
                ball['dx'] = abs(ball['dx'])
            elif ball['x'] + BALL_R >= self.gw:
                ball['dx'] = -abs(ball['dx'])
            if ball['y'] + BALL_R >= self.gh:
                ball['dy'] = -abs(ball['dy'])

            # Paddle (only when the ball is moving down)
            if (ball['dy'] < 0
                    and self.paddle_y <= ball['y'] - BALL_R <= self.paddle_y + PADDLE_H
                    and self.paddle_x <= ball['x'] <= self.paddle_x + self.paddle_w):
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
                    if b['hp'] <= 0:
                        b['alive'] = False
                        self.score += b['pts']
                        if random.random() < 0.25:
                            self.powerups.append({
                                'x': b['x'] + b['w'] / 2, 'y': b['y'],
                                'type': random.choice(list(POWERUP_STYLE.keys())),
                            })
                    else:
                        b['color'] = CRACKED_COLOR
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
                self.reset_ball()

        if all(not b['alive'] for b in self.bricks):
            self.state = "won"
        self.draw_everything()

    # ---------- drawing ----------
    def _text_tex(self, text, px):
        key = (text, px)
        tex = self._tex_cache.get(key)
        if tex is None:
            if len(self._tex_cache) > 200:
                self._tex_cache.clear()
            lbl = CoreLabel(text=text, font_size=px, bold=True)
            lbl.refresh()
            tex = lbl.texture
            self._tex_cache[key] = tex
        return tex

    def _draw_text(self, text, gx, gy, size, color=(1, 1, 1, 1)):
        s = self.s
        tex = self._text_tex(text, max(8, int(size * s)))
        Color(*color)
        Rectangle(texture=tex,
                  pos=(self.x + gx * s - tex.width / 2, self.y + gy * s - tex.height / 2),
                  size=tex.size)

    def draw_everything(self):
        self.canvas.clear()
        with self.canvas:
            s = self.s

            # Background
            Color(0.06, 0.09, 0.16, 1)
            Rectangle(pos=self.pos, size=self.size)

            # Bricks
            for b in self.bricks:
                if b['alive']:
                    Color(*b['color'])
                    Rectangle(pos=(self.x + b['x'] * s, self.y + b['y'] * s),
                              size=(b['w'] * s, b['h'] * s))

            # Paddle
            Color(0.22, 0.74, 0.97, 1)
            Rectangle(pos=(self.x + self.paddle_x * s, self.y + self.paddle_y * s),
                      size=(self.paddle_w * s, PADDLE_H * s))

            # Powerups: colored circle with a letter
            for p in self.powerups:
                color, letter = POWERUP_STYLE[p['type']]
                r = 14
                Color(*color)
                Ellipse(pos=(self.x + (p['x'] - r) * s, self.y + (p['y'] - r) * s),
                        size=(2 * r * s, 2 * r * s))
                self._draw_text(letter, p['x'], p['y'], 18, (1, 1, 1, 1))

            # Balls
            Color(0.97, 0.98, 0.98, 1)
            for ball in self.balls:
                Ellipse(pos=(self.x + (ball['x'] - BALL_R) * s, self.y + (ball['y'] - BALL_R) * s),
                        size=(BALL_R * 2 * s, BALL_R * 2 * s))

            # HUD
            hud_y = self.gh - 55
            self._draw_text("Score: %d" % self.score, 100, hud_y, 22)
            self._draw_text("Lives: %d" % self.lives, self.gw - 90, hud_y, 22)

            # Messages
            cx, cy = self.gw / 2, self.gh / 2
            if self.state == "start":
                self._draw_text("BRICK BREAKER", cx, cy + 20, 34, (0.22, 0.74, 0.97, 1))
                self._draw_text("Tap to start", cx, cy - 25, 24)
            elif self.state == "paused":
                self._draw_text("Paused - tap to resume", cx, cy, 24)
            elif self.state == "won":
                self._draw_text("You win!", cx, cy + 20, 34, (0.18, 0.80, 0.44, 1))
                self._draw_text("Tap to play again", cx, cy - 25, 24)
            elif self.state == "lost":
                self._draw_text("Game over", cx, cy + 20, 34, (0.91, 0.30, 0.24, 1))
                self._draw_text("Tap to play again", cx, cy - 25, 24)
            elif self.state == "playing" and any(b['caught'] for b in self.balls):
                self._draw_text("Tap to launch", cx, self.paddle_y + 120, 22, (0.8, 0.85, 0.9, 1))


class BrickBreakerApp(App):
    def build(self):
        return BrickBreakerGame()


if __name__ == '__main__':
    BrickBreakerApp().run()
