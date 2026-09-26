"""Brawl Arena - точка входу. Запуск: python main.py"""
import json
import os

from kivy.config import Config
from kivy.utils import platform

# Налаштування мають іти до імпорту решти модулів Kivy
IS_MOBILE = platform in ("android", "ios")

Config.set("input", "mouse", "mouse,multitouch_on_demand")
Config.set("kivy", "exit_on_escape", "0")
if not IS_MOBILE:
    # На телефоне/планшете система сама даёт полноэкранное окно нужного
    # размера (см. buildozer.spec: fullscreen=1, orientation=landscape).
    # Фиксированный размер нужен только для запуска с компьютера.
    Config.set("graphics", "width", "1280")
    Config.set("graphics", "height", "720")

from kivy.core.window import Window  # noqa: E402
from kivy.uix.screenmanager import FadeTransition  # noqa: E402
from kivymd.app import MDApp  # noqa: E402
from kivymd.uix.screenmanager import MDScreenManager  # noqa: E402

from screens import GameScreen, MenuScreen  # noqa: E402

if IS_MOBILE:
    Window.softinput_mode = "below_target"


class BrawlApp(MDApp):
    title = "Brawl Arena"

    def build(self):
        # На телефоне мышки и клавиатуры нет - джойстики включены сразу.
        self.settings = {"weapon": 0, "joysticks": IS_MOBILE}
        self.best = self.load_best()
        self.sm = MDScreenManager(transition=FadeTransition(duration=0.25))
        self.menu_screen = MenuScreen(self)
        self.game_screen = GameScreen(self)
        self.sm.add_widget(self.menu_screen)
        self.sm.add_widget(self.game_screen)
        return self.sm

    def start_game(self):
        self.game_screen.new_game()
        self.sm.current = "game"

    def to_menu(self):
        self.sm.current = "menu"

    @property
    def save_path(self):
        return os.path.join(self.user_data_dir, "brawl_save.json")

    def load_best(self):
        try:
            with open(self.save_path, "r", encoding="utf-8") as f:
                return int(json.load(f).get("best", 0))
        except (OSError, ValueError):
            return 0

    def save_best(self):
        try:
            with open(self.save_path, "w", encoding="utf-8") as f:
                json.dump({"best": self.best}, f)
        except OSError:
            pass


if __name__ == "__main__":
    BrawlApp().run()
