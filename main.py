"""
STREET CHASE - simple top-down police-chase racing game (Kivy)

Controls (touch):
  - Screen ka LEFT 40%  -> left steer
  - Screen ka RIGHT 40% -> right steer
  - Screen ka MIDDLE    -> NITRO (hold)
Controls (PC): Left/Right arrow ya A/D, Space = nitro

Goal: traffic se bachte hue police se door raho. Traffic se takraoge to
speed kam hogi aur police nazdeek aa jayegi. Police pakad le to BUSTED!
"""
import random

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.widget import Widget


TRAFFIC_COLORS = [
    (0.9, 0.2, 0.2),
    (0.2, 0.5, 0.9),
    (0.95, 0.8, 0.2),
    (0.3, 0.8, 0.4),
    (0.8, 0.8, 0.8),
    (0.7, 0.3, 0.8),
]

LANES = 4


class Game(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.touches = {}
        self.keys = set()
        self.state = "play"
        self.ready = False

        self.hud = Label(
            text="",
            font_size=dp(16),
            halign="left",
            valign="top",
            size_hint=(None, None),
        )
        self.msg = Label(
            text="",
            font_size=dp(34),
            halign="center",
            valign="middle",
            size_hint=(None, None),
            bold=True,
        )
        self.add_widget(self.hud)
        self.add_widget(self.msg)

        Window.bind(on_key_down=self.on_kd, on_key_up=self.on_ku)
        self.bind(size=self.on_resize)
        Clock.schedule_interval(self.update, 1 / 60.0)

    # ------------------------------------------------------------------ setup
    def on_resize(self, *args):
        if self.width > 1 and self.height > 1:
            self.reset()

    def reset(self):
        W, H = self.size
        self.road_w = W * 0.8
        self.road_x = (W - self.road_w) / 2.0
        self.car_w = self.road_w / (LANES * 1.5)
        self.car_h = self.car_w * 1.9

        self.px = W / 2.0
        self.py = H * 0.22
        self.speed = 250.0
        self.nitro = 100.0
        self.gap = 350.0          # police kitna peeche hai (pixels)
        self.pol_x = W / 2.0
        self.dist = 0.0
        self.time = 0.0
        self.line_off = 0.0
        self.spawn_t = 0.5
        self.traffic = []
        self.shake = 0.0
        self.state = "play"
        self.ready = True

        self.hud.size = (W, dp(60))
        self.hud.text_size = (W - dp(20), dp(60))
        self.hud.pos = (dp(10), H - dp(70))
        self.msg.size = (W, H * 0.3)
        self.msg.text_size = (W, H * 0.3)
        self.msg.pos = (0, H * 0.35)
        self.msg.text = ""

    # ---------------------------------------------------------------- input
    def on_kd(self, window, key, *args):
        self.keys.add(key)

    def on_ku(self, window, key, *args):
        self.keys.discard(key)

    def on_touch_down(self, touch):
        if self.state == "over":
            self.reset()
            return True
        self.touches[touch.uid] = touch.x
        return True

    def on_touch_move(self, touch):
        if touch.uid in self.touches:
            self.touches[touch.uid] = touch.x
        return True

    def on_touch_up(self, touch):
        self.touches.pop(touch.uid, None)
        return True

    def read_controls(self):
        left = right = nitro = False
        W = max(self.width, 1)
        for x in self.touches.values():
            f = x / W
            if f < 0.4:
                left = True
            elif f > 0.6:
                right = True
            else:
                nitro = True
        if 276 in self.keys or 97 in self.keys:
            left = True
        if 275 in self.keys or 100 in self.keys:
            right = True
        if 32 in self.keys:
            nitro = True
        direction = (1 if right else 0) - (1 if left else 0)
        return direction, nitro

    # --------------------------------------------------------------- update
    def update(self, dt):
        if not self.ready:
            return
        dt = min(dt, 0.05)

        if self.state == "play":
            self.step(dt)
        self.draw()

    def step(self, dt):
        W, H = self.size
        self.time += dt
        direction, nitro_on = self.read_controls()

        # steering
        self.px += direction * W * 0.65 * dt
        left_lim = self.road_x + self.car_w / 2.0
        right_lim = self.road_x + self.road_w - self.car_w / 2.0
        off_road = False
        if self.px < left_lim:
            self.px = left_lim
            off_road = direction < 0
        if self.px > right_lim:
            self.px = right_lim
            off_road = direction > 0

        # speed / nitro
        target = 450.0
        if nitro_on and self.nitro > 0:
            target = 800.0
            self.nitro = max(0.0, self.nitro - 35.0 * dt)
        else:
            self.nitro = min(100.0, self.nitro + 10.0 * dt)
        if off_road:
            target = 250.0
        self.speed += (target - self.speed) * min(1.0, 2.0 * dt)

        # police
        police_speed = min(700.0, 420.0 + self.dist / 8.0)
        self.gap += (self.speed - police_speed) * dt
        self.gap = min(self.gap, H * 0.9)
        self.pol_x += (self.px - self.pol_x) * min(1.0, 3.0 * dt)
        if self.gap <= 0:
            self.state = "over"
            self.msg.text = "BUSTED!\nTap to restart  |  %d m" % int(self.dist)

        # world movement
        self.dist += self.speed * dt / 20.0
        self.line_off = (self.line_off + self.speed * dt) % 60.0
        self.shake = max(0.0, self.shake - dt)

        # spawn traffic
        self.spawn_t -= dt
        if self.spawn_t <= 0:
            self.spawn_t = random.uniform(0.5, 1.2) * (450.0 / max(self.speed, 200.0))
            lane = random.randint(0, LANES - 1)
            lane_w = self.road_w / LANES
            self.traffic.append({
                "x": self.road_x + (lane + 0.5) * lane_w,
                "y": H + self.car_h * 2,
                "speed": random.uniform(120.0, 250.0),
                "color": random.choice(TRAFFIC_COLORS),
            })

        # move traffic + collisions
        alive = []
        for t in self.traffic:
            t["y"] -= (self.speed - t["speed"]) * dt
            if t["y"] < -self.car_h * 2 or t["y"] > H + self.car_h * 4:
                continue
            if (abs(t["x"] - self.px) < self.car_w * 0.85 and
                    abs(t["y"] - self.py) < self.car_h * 0.9):
                self.speed = 120.0
                self.gap -= 150.0
                self.shake = 0.3
                continue
            alive.append(t)
        self.traffic = alive

    # ----------------------------------------------------------------- draw
    def draw_car(self, x, y, color, police_lights=False):
        w, h = self.car_w, self.car_h
        # wheels
        Color(0.05, 0.05, 0.05)
        Rectangle(pos=(x - w / 2 - w * 0.08, y - h * 0.38), size=(w * 0.16, h * 0.22))
        Rectangle(pos=(x + w / 2 - w * 0.08, y - h * 0.38), size=(w * 0.16, h * 0.22))
        Rectangle(pos=(x - w / 2 - w * 0.08, y + h * 0.16), size=(w * 0.16, h * 0.22))
        Rectangle(pos=(x + w / 2 - w * 0.08, y + h * 0.16), size=(w * 0.16, h * 0.22))
        # body
        Color(*color)
        Rectangle(pos=(x - w / 2, y - h / 2), size=(w, h))
        # windshield / roof
        Color(0.1, 0.12, 0.18)
        Rectangle(pos=(x - w * 0.36, y + h * 0.02), size=(w * 0.72, h * 0.22))
        Rectangle(pos=(x - w * 0.36, y - h * 0.32), size=(w * 0.72, h * 0.14))
        if police_lights:
            blink = int(self.time * 8) % 2
            Color(1, 0, 0) if blink else Color(0, 0.3, 1)
            Rectangle(pos=(x - w * 0.34, y - h * 0.08), size=(w * 0.34, h * 0.1))
            Color(0, 0.3, 1) if blink else Color(1, 0, 0)
            Rectangle(pos=(x, y - h * 0.08), size=(w * 0.34, h * 0.1))

    def draw(self):
        W, H = self.size
        canvas = self.canvas.before
        canvas.clear()
        with canvas:
            # grass
            Color(0.1, 0.35, 0.12)
            Rectangle(pos=(0, 0), size=(W, H))
            # road
            Color(0.18, 0.18, 0.2)
            Rectangle(pos=(self.road_x, 0), size=(self.road_w, H))
            # road edges
            Color(1, 1, 1)
            Rectangle(pos=(self.road_x - dp(3), 0), size=(dp(3), H))
            Rectangle(pos=(self.road_x + self.road_w, 0), size=(dp(3), H))
            # lane dashes
            Color(0.9, 0.9, 0.9)
            lane_w = self.road_w / LANES
            for i in range(1, LANES):
                lx = self.road_x + i * lane_w - dp(2)
                k = 0
                while k * 60 - self.line_off < H:
                    Rectangle(pos=(lx, k * 60 - self.line_off), size=(dp(4), 30))
                    k += 1

            # traffic
            for t in self.traffic:
                self.draw_car(t["x"], t["y"], t["color"])

            # police
            pol_y = self.py - self.gap
            if pol_y > -self.car_h:
                self.draw_car(self.pol_x, pol_y, (0.95, 0.95, 0.95), police_lights=True)

            # player (shake on crash)
            sx = random.uniform(-4, 4) if self.shake > 0 else 0
            self.draw_car(self.px + sx, self.py, (0.9, 0.1, 0.1))

            # nitro bar
            Color(0.2, 0.2, 0.2)
            Rectangle(pos=(dp(10), dp(10)), size=(W * 0.4, dp(10)))
            Color(0.1, 0.7, 1.0)
            Rectangle(pos=(dp(10), dp(10)), size=(W * 0.4 * self.nitro / 100.0, dp(10)))

            # police gap bar (kam = khatra)
            Color(0.2, 0.2, 0.2)
            Rectangle(pos=(W - dp(10) - W * 0.4, dp(10)), size=(W * 0.4, dp(10)))
            ratio = max(0.0, min(1.0, self.gap / (H * 0.5)))
            Color(1 - ratio, ratio, 0.1)
            Rectangle(pos=(W - dp(10) - W * 0.4, dp(10)), size=(W * 0.4 * ratio, dp(10)))

        self.hud.text = "%d m    %d km/h\nNITRO %d%%    POLICE GAP %d" % (
            int(self.dist), int(self.speed / 4), int(self.nitro), max(0, int(self.gap))
        )


class StreetChaseApp(App):
    def build(self):
        self.title = "Street Chase"
        return Game()


if __name__ == "__main__":
    StreetChaseApp().run()
