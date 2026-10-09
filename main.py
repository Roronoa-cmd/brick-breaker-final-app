import random
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.properties import NumericProperty, ReferenceListProperty, ObjectProperty, ListProperty, BooleanProperty
from kivy.vector import Vector
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Ellipse

# Set game virtual size aspect ratio
GAME_WIDTH, GAME_HEIGHT = 800, 600
PADDLE_H = 15
BALL_R = 8
BALL_SPEED = 6
ROWS, COLS = 5, 10
BRICK_W, BRICK_H = 88, 27  # <-- MAKE SURE THIS LINE HAS BOTH BRICK_W AND BRICK_H
PAD, TOP, LEFT = 5, 60, 35

COLORS = [
    [0.91, 0.30, 0.24, 1],  # Red
    [0.90, 0.49, 0.13, 1],  # Orange
    [0.95, 0.77, 0.06, 1],  # Yellow
    [0.18, 0.80, 0.44, 1],  # Green
    [0.20, 0.60, 0.86, 1]   # Blue
]
DURABLE_COLOR = [0.50, 0.55, 0.55, 1]
CRACKED_COLOR = [0.74, 0.76, 0.78, 1]

class BrickBreakerGame(Widget):
    score = NumericProperty(0)
    lives = NumericProperty(3)
    state = ObjectProperty("start") # start, playing, paused, won, lost

    def __init__(self, **kwargs):
        super(BrickBreakerGame, self).__init__(**kwargs)
        self.paddle_w = 120
        self.paddle_x = (GAME_WIDTH - self.paddle_w) / 2
        self.paddle_y = 40
        
        self.balls = []
        self.powerups = []
        self.bricks = []
        
        self.is_sticky = False
        self.make_bricks()
        
        # PC Keyboard Support
        self._keyboard = Window.request_keyboard(self._keyboard_closed, self)
        self._keyboard.bind(on_key_down=self._on_keyboard_down)
        self._keyboard.bind(on_key_up=self._on_keyboard_up)
        self.key_left = False
        self.key_right = False
        
        # Main Game Clock Loop
        Clock.schedule_interval(self.update, 1.0 / 60.0)
        self.bind(size=self._on_size)

    def _keyboard_closed(self):
        self._keyboard.unbind(on_key_down=self._on_keyboard_down)
        self._keyboard.unbind(on_key_up=self._on_keyboard_up)
        self._keyboard = None

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        if keycode[1] in ['left', 'a']: self.key_left = True
        elif keycode[1] in ['right', 'd']: self.key_right = True
        elif keycode[1] == 'space': self.handle_space()
        elif keycode[1] == 'p': self.toggle_pause()
        elif keycode[1] == 'r': self.restart()
        return True

    def _on_keyboard_up(self, keyboard, keycode):
        if keycode[1] in ['left', 'a']: self.key_left = False
        elif keycode[1] in ['right', 'd']: self.key_right = False
        return True

    def make_bricks(self):
        self.bricks.clear()
        # Scale math to match grid layout safely
        brick_w = (GAME_WIDTH - (LEFT * 2) - (PAD * (COLS - 1))) / COLS
        for r in range(ROWS):
            for c in range(COLS):
                x = LEFT + c * (brick_w + PAD)
                y = GAME_HEIGHT - TOP - r * (BRICK_H + PAD)
                hp = 2 if r == 0 else 1
                color = DURABLE_COLOR if hp == 2 else COLORS[r % len(COLORS)]
                self.bricks.append({
                    'x': x, 'y': y, 'w': brick_w, 'h': BRICK_H,
                    'color': color, 'hp': hp, 'pts': (ROWS - r) * 10, 'alive': True
                })

    def _on_size(self, *args):
        self.draw_everything()

    # 📱 TOUCH AND DRAG CONTROLS FOR MOBILE 📱
    def on_touch_down(self, touch):
        if self.state == "start":
            self.state = "playing"
            self.reset_ball()
            return True
        elif self.state in ["won", "lost"]:
            self.restart()
            return True
            
        if self.state == "playing":
            # If ball is caught, tapping screen launches it
            for ball in self.balls:
                if ball['caught']:
                    ball['caught'] = False
                    ball['dx'] = BALL_SPEED * random.choice([-1, 1])
                    ball['dy'] = BALL_SPEED
            
            # Snap paddle to touch x coordinate
            tx = (touch.x / self.width) * GAME_WIDTH
            self.paddle_x = max(0, min(tx - self.paddle_w / 2, GAME_WIDTH - self.paddle_w))
            return True

    def on_touch_move(self, touch):
        if self.state == "playing":
            # Smoothly slide paddle as finger drags across glass screen
            tx = (touch.x / self.width) * GAME_WIDTH
            self.paddle_x = max(0, min(tx - self.paddle_w / 2, GAME_WIDTH - self.paddle_w))
            return True

    def spawn_ball(self, x, y, dx, dy, caught=False):
        self.balls.append({'x': x, 'y': y, 'dx': dx, 'dy': dy, 'caught': caught})

    def reset_ball(self):
        self.balls.clear()
        self.powerups.clear()
        self.paddle_w = 120
        self.is_sticky = False
        self.spawn_ball(self.paddle_x + self.paddle_w / 2, self.paddle_y + PADDLE_H + BALL_R, 0, 0, caught=True)

    def handle_space(self):
        if self.state == "start":
            self.state = "playing"
            self.reset_ball()
        elif self.state == "playing":
            for ball in self.balls:
                if ball['caught']:
                    ball['caught'] = False
                    ball['dx'] = BALL_SPEED * random.choice([-1, 1])
                    ball['dy'] = BALL_SPEED

    def toggle_pause(self):
        self.state = "paused" if self.state == "playing" else "playing" if self.state == "paused" else self.state

    def restart(self):
        self.paddle_x = (GAME_WIDTH - 120) / 2
        self.score, self.lives = 0, 3
        self.state = "playing"
        self.make_bricks()
        self.reset_ball()

    def update(self, dt):
        if self.state != "playing":
            self.draw_everything()
            return

        # Smooth Desktop Keyboard Moving fallback
        if self.key_left: self.paddle_x = max(0, self.paddle_x - 10)
        if self.key_right: self.paddle_x = min(GAME_WIDTH - self.paddle_w, self.paddle_x + 10)

        # Update caught balls tracking positioning
        for ball in self.balls:
            if ball['caught']:
                ball['x'] = self.paddle_x + self.paddle_w / 2

        # Powerups falling physics
        for p in self.powerups[:]:
            p['y'] -= 3
            if self.paddle_y <= p['y'] <= self.paddle_y + PADDLE_H and self.paddle_x <= p['x'] <= self.paddle_x + self.paddle_w:
                self.apply_powerup(p['type'])
                self.powerups.remove(p)
            elif p['y'] < 0:
                self.powerups.remove(p)

        # Ball Engine Vector updates
        for ball in self.balls[:]:
            if ball['caught']: continue
            ball['x'] += ball['dx']
            ball['y'] += ball['dy']

            # Wall bounces
            if ball['x'] - BALL_R <= 0 or ball['x'] + BALL_R >= GAME_WIDTH: ball['dx'] = -ball['dx']
            if ball['y'] + BALL_R >= GAME_HEIGHT: ball['dy'] = -ball['dy']

            # Paddle Collision
            if self.paddle_y <= ball['y'] - BALL_R <= self.paddle_y + PADDLE_H and self.paddle_x <= ball['x'] <= self.paddle_x + self.paddle_w:
                if self.is_sticky:
                    ball['caught'] = True
                    ball['dx'], ball['dy'] = 0, 0
                    ball['y'] = self.paddle_y + PADDLE_H + BALL_R
                    continue
                hit = (ball['x'] - self.paddle_x) / self.paddle_w - 0.5
                ball['dx'] = hit * 10
                ball['dy'] = abs(ball['dy'])

            # Brick Collision
            for b in self.bricks:
                if not b['alive']: continue
                if b['x'] <= ball['x'] <= b['x'] + b['w'] and b['y'] <= ball['y'] <= b['y'] + b['h']:
                    b['hp'] -= 1
                    if b['hp'] <= 0:
                        b['alive'] = False
                        self.score += b['pts']
                        if random.random() < 0.25:
                            self.powerups.append({'x': b['x'] + b['w']/2, 'y': b['y'], 'type': random.choice(['expand', 'multiball', 'sticky'])})
                    else:
                        b['color'] = CRACKED_COLOR
                    ball['dy'] = -ball['dy']
                    break

            # Out of bounds dropping
            if ball['y'] < 0:
                self.balls.remove(ball)

        # Checking Win/Loss Metrics
        if not self.balls:
            self.lives -= 1
            if self.lives <= 0: self.state = "lost"
            else: self.reset_ball()

        if all(not b['alive'] for b in self.bricks): self.state = "won"
        self.draw_everything()

    def apply_powerup(self, p_type):
        if p_type == "expand": self.paddle_w = min(200, self.paddle_w + 30)
        elif p_type == "sticky": self.is_sticky = True
        elif p_type == "multiball": self.spawn_ball(GAME_WIDTH/2, GAME_HEIGHT/2, random.choice([-4, 4]), BALL_SPEED)

    def draw_everything(self):
        self.canvas.clear()
        with self.canvas:
            # Scaler matrix calculations to preserve dimensions across arbitrary screens
            sx, sy = self.width / GAME_WIDTH, self.height / GAME_HEIGHT
            
            # Draw Background Box
            Color(0.06, 0.09, 0.16, 1)
            Rectangle(pos=self.pos, size=self.size)

            # Draw Bricks
            for b in self.bricks:
                if b['alive']:
                    Color(*b['color'])
                    Rectangle(pos=(self.x + b['x']*sx, self.y + b['y']*sy), size=(b['w']*sx, b['h']*sy))

            # Draw Paddle Slider
            Color(0.22, 0.74, 0.97, 1)
            Rectangle(pos=(self.x + self.paddle_x*sx, self.y + self.paddle_y*sy), size=(self.paddle_w*sx, PADDLE_H*sy))

            # Draw Rolling Powerups
            for p in self.powerups:
                Color(0.6, 0.3, 0.7, 1) # Purple icon nodes
                Ellipse(pos=(self.x + (p['x']-10)*sx, self.y + (p['y']-10)*sy), size=(20*sx, 20*sy))

            # Draw Projectile Balls
            Color(0.97, 0.98, 0.98, 1)
            for ball in self.balls:
                Ellipse(pos=(self.x + (ball['x']-BALL_R)*sx, self.y + (ball['y']-BALL_R)*sy), size=(BALL_R*2*sx, BALL_R*2*sy))

class BrickBreakerApp(App):
    def build(self):
        return BrickBreakerGame()

if __name__ == '__main__':
    BrickBreakerApp().run()
