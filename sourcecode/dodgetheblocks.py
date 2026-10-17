import tkinter as tk
import random
import os
import json
import ctypes
from ctypes import wintypes
from pathlib import Path

WIDTH = 600
HEIGHT = 700
PLAYER_W = 58
PLAYER_H = 24
CELL = 24

DEFAULT_SETTINGS = {
    "player_speed": 0.75,
    "friction": 0.88,
    "difficulty": 1.0
}

THEMES = {
    "Neon Blue": {
        "bg": "#10131c", "panel": "#191e2b",
        "panel_light": "#232b3b", "accent": "#57e6ff",
        "danger": "#ff5263", "text": "#f1f5ff",
        "muted": "#929bb0", "grid": "#171c29"
    },
    "Purple": {
        "bg": "#120d1c", "panel": "#21152f",
        "panel_light": "#352046", "accent": "#c084fc",
        "danger": "#fb7185", "text": "#f5edff",
        "muted": "#b4a2c9", "grid": "#1b1228"
    },
    "Red": {
        "bg": "#190d11", "panel": "#2a151c",
        "panel_light": "#41202a", "accent": "#ff667a",
        "danger": "#ff354f", "text": "#fff0f2",
        "muted": "#c6a0a7", "grid": "#241117"
    },
    "Green": {
        "bg": "#0b1512", "panel": "#14241e",
        "panel_light": "#20382e", "accent": "#70f0a0",
        "danger": "#ff667a", "text": "#edfff4",
        "muted": "#9db8a8", "grid": "#122019"
    }
}

PLAYER_COLORS = {
    "Cyan": "#57e6ff",
    "Purple": "#c084fc",
    "White": "#f1f5ff",
    "Orange": "#ffad5c",
    "Pink": "#ff70c5",
    "Green": "#70f0a0",
    "Yellow": "#ffe66d",
    "Red": "#ff5263"
}

# Standard Tetris tetrominoes.
# Coordinates are grid cells, not arbitrary angles.
SHAPES = {
    "I": [(0, 0), (1, 0), (2, 0), (3, 0)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "T": [(0, 0), (1, 0), (2, 0), (1, 1)],
    "S": [(1, 0), (2, 0), (0, 1), (1, 1)],
    "Z": [(0, 0), (1, 0), (1, 1), (2, 1)],
    "J": [(0, 0), (0, 1), (1, 1), (2, 1)],
    "L": [(2, 0), (0, 1), (1, 1), (2, 1)]
}

# Classic Tetris colors, assigned randomly to falling pieces.
PIECE_COLORS = {
    "I": "#00e5ff",
    "O": "#ffe500",
    "T": "#b44cff",
    "S": "#46e85a",
    "Z": "#ff4057",
    "J": "#4287ff",
    "L": "#ff9d32"
}

SAVE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
SAVE_DIR = SAVE_DIR / "DodgeTheBlocks"
SAVE_FILE = SAVE_DIR / "record.dat"


class DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte))
    ]


def protect_data(data, decrypt=False):
    if os.name != "nt":
        raise OSError("Windows encryption is required.")

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    if decrypt:
        func = crypt.CryptUnprotectData
        func.argtypes = [
            ctypes.POINTER(DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(DataBlob)
        ]
    else:
        func = crypt.CryptProtectData
        func.argtypes = [
            ctypes.POINTER(DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(DataBlob)
        ]

    func.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p

    buffer = ctypes.create_string_buffer(data)
    input_blob = DataBlob(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    )
    output_blob = DataBlob()

    if decrypt:
        success = func(
            ctypes.byref(input_blob), None, None,
            None, None, 0, ctypes.byref(output_blob)
        )
    else:
        success = func(
            ctypes.byref(input_blob),
            "DodgeTheBlocks High Score",
            None, None, None, 0,
            ctypes.byref(output_blob)
        )

    if not success:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        return ctypes.string_at(
            output_blob.pbData, output_blob.cbData
        )
    finally:
        kernel.LocalFree(
            ctypes.cast(output_blob.pbData, ctypes.c_void_p)
        )


class HighScoreStore:
    def load(self):
        try:
            encrypted = SAVE_FILE.read_bytes()
            raw = protect_data(encrypted, decrypt=True)
            data = json.loads(raw.decode("utf-8"))
            score = data["high_score"]

            if type(score) is not int or not 0 <= score <= 100000000:
                return 0

            return score
        except Exception:
            return 0

    def save(self, score):
        SAVE_DIR.mkdir(parents=True, exist_ok=True)

        raw = json.dumps({
            "high_score": int(score)
        }).encode("utf-8")

        encrypted = protect_data(raw)
        temp_file = SAVE_FILE.with_suffix(".tmp")
        temp_file.write_bytes(encrypted)
        os.replace(temp_file, SAVE_FILE)


def rotate_shape(cells, turns):
    """Rotate a tetromino by exact 90-degree increments."""
    result = list(cells)

    for _ in range(turns % 4):
        # Rotate clockwise and normalize back to origin.
        result = [(y, -x) for x, y in result]
        min_x = min(x for x, y in result)
        min_y = min(y for x, y in result)
        result = [
            (x - min_x, y - min_y)
            for x, y in result
        ]

    return result


class DodgeGame:
    def __init__(self, root):
        self.root = root
        self.root.title("Dodge the Blocks")
        self.root.resizable(False, False)

        self.settings = DEFAULT_SETTINGS.copy()
        self.theme_name = "Neon Blue"
        self.theme = THEMES[self.theme_name]

        self.player_color_name = "Cyan"
        self.player_color = PLAYER_COLORS[self.player_color_name]

        self.store = HighScoreStore()
        self.high_score = self.store.load()

        self.keys = set()
        self.paused = False
        self.game_over = False
        self.pause_widgets = []

        self.root.configure(bg=self.theme["bg"])

        self.header = tk.Frame(
            root, bg=self.theme["panel"], padx=18, pady=12
        )
        self.header.pack(fill="x")

        self.title_label = tk.Label(
            self.header, text="DODGE THE BLOCKS",
            bg=self.theme["panel"], fg=self.theme["accent"],
            font=("Segoe UI", 16, "bold")
        )
        self.title_label.pack(side="left")

        score_frame = tk.Frame(
            self.header, bg=self.theme["panel"]
        )
        score_frame.pack(side="right")

        self.score_label = tk.Label(
            score_frame, text="SCORE  0",
            bg=self.theme["panel"], fg=self.theme["text"],
            font=("Segoe UI", 11, "bold")
        )
        self.score_label.pack(anchor="e")

        self.best_label = tk.Label(
            score_frame, text=f"BEST  {self.high_score}",
            bg=self.theme["panel"], fg=self.theme["accent"],
            font=("Segoe UI", 10, "bold")
        )
        self.best_label.pack(anchor="e")

        self.canvas = tk.Canvas(
            root, width=WIDTH, height=HEIGHT,
            bg=self.theme["bg"], highlightthickness=0
        )
        self.canvas.pack()

        self.footer = tk.Frame(
            root, bg=self.theme["panel"], padx=18, pady=10
        )
        self.footer.pack(fill="x")

        self.footer_left = tk.Label(
            self.footer, text="MOVE: A / D OR ARROW KEYS",
            bg=self.theme["panel"], fg=self.theme["muted"],
            font=("Segoe UI", 10, "bold")
        )
        self.footer_left.pack(side="left")

        self.footer_right = tk.Label(
            self.footer, text="SPACE: PAUSE",
            bg=self.theme["panel"], fg=self.theme["accent"],
            font=("Segoe UI", 10, "bold")
        )
        self.footer_right.pack(side="right")

        self.root.bind("<KeyPress>", self.key_down)
        self.root.bind("<KeyRelease>", self.key_up)
        self.root.bind("<FocusOut>", self.clear_keys)

        self.reset()
        self.tick()

    def reset(self):
        self.canvas.delete("all")

        self.player_x = WIDTH / 2
        self.player_y = HEIGHT - 70
        self.player_vx = 0.0

        self.score = 0
        self.blocks = []
        self.frame = 0
        self.paused = False
        self.game_over = False
        self.keys.clear()

        self.draw_background()

        self.player = self.canvas.create_rectangle(
            self.player_x - PLAYER_W / 2,
            self.player_y - PLAYER_H / 2,
            self.player_x + PLAYER_W / 2,
            self.player_y + PLAYER_H / 2,
            fill=self.player_color, outline=""
        )

        self.canvas.create_text(
            14, 14, anchor="nw",
            text="SURVIVE",
            fill=self.theme["muted"],
            font=("Segoe UI", 10, "bold")
        )

        self.score_label.config(text="SCORE  0")
        self.best_label.config(text=f"BEST  {self.high_score}")

    def draw_background(self):
        self.canvas.configure(bg=self.theme["bg"])

        for x in range(0, WIDTH, 40):
            self.canvas.create_line(
                x, 0, x, HEIGHT,
                fill=self.theme["grid"], tags="grid"
            )

        for y in range(0, HEIGHT, 40):
            self.canvas.create_line(
                0, y, WIDTH, y,
                fill=self.theme["grid"], tags="grid"
            )

    def key_down(self, event):
        key = event.keysym.lower()

        if key == "space":
            if "space" not in self.keys:
                self.keys.add("space")
                if not self.game_over:
                    self.toggle_pause()
            return

        if self.game_over and key == "r":
            self.reset()
            return

        if not self.paused:
            self.keys.add(key)

    def key_up(self, event):
        self.keys.discard(event.keysym.lower())

    def clear_keys(self, event=None):
        self.keys.clear()

    def toggle_pause(self):
        if self.game_over:
            return

        self.paused = not self.paused
        self.keys.clear()

        if self.paused:
            self.show_pause_menu()
        else:
            self.close_pause_menu()

    def close_pause_menu(self):
        self.canvas.delete("pause_ui")

        for widget in self.pause_widgets:
            try:
                widget.destroy()
            except tk.TclError:
                pass

        self.pause_widgets.clear()

    def show_pause_menu(self):
        self.close_pause_menu()

        self.canvas.create_rectangle(
            35, 30, WIDTH - 35, HEIGHT - 25,
            fill=self.theme["panel"],
            outline=self.theme["accent"],
            width=2,
            tags="pause_ui"
        )

        self.canvas.create_text(
            WIDTH / 2, 58, text="PAUSED",
            fill=self.theme["accent"],
            font=("Segoe UI", 24, "bold"),
            tags="pause_ui"
        )

        self.canvas.create_text(
            WIDTH / 2, 88, text="Press SPACE to resume",
            fill=self.theme["muted"],
            font=("Segoe UI", 10),
            tags="pause_ui"
        )

        self.canvas.create_text(
            WIDTH / 2, 120, text="GAMEPLAY SETTINGS",
            fill=self.theme["text"],
            font=("Segoe UI", 12, "bold"),
            tags="pause_ui"
        )

        self.settings_frame = tk.Frame(
            self.canvas, bg=self.theme["panel"]
        )
        self.pause_widgets.append(self.settings_frame)

        self.canvas.create_window(
            WIDTH / 2, 235,
            window=self.settings_frame,
            width=430, height=205,
            tags="pause_ui"
        )

        self.add_setting(
            "Movement acceleration",
            "player_speed", 0.2, 1.5, 0.05
        )
        self.add_setting(
            "Sliding friction",
            "friction", 0.70, 0.98, 0.01
        )
        self.add_setting(
            "Block difficulty",
            "difficulty", 0.5, 2.0, 0.1
        )

        self.make_button(
            "RESET TUNES", self.reset_tunes,
            355, 180, self.theme["panel_light"], self.theme["text"]
        )

        self.canvas.create_text(
            WIDTH / 2, 393, text="PLAYER COLOR",
            fill=self.theme["text"],
            font=("Segoe UI", 12, "bold"),
            tags="pause_ui"
        )

        self.player_color_var = tk.StringVar(
            value=self.player_color_name
        )

        self.color_menu = tk.OptionMenu(
            self.canvas,
            self.player_color_var,
            *PLAYER_COLORS.keys(),
            command=self.change_player_color
        )
        self.style_menu(self.color_menu)
        self.pause_widgets.append(self.color_menu)

        self.canvas.create_window(
            WIDTH / 2, 425,
            window=self.color_menu,
            width=190, height=29,
            tags="pause_ui"
        )

        self.canvas.create_text(
            WIDTH / 2, 466, text="APPEARANCE THEME",
            fill=self.theme["text"],
            font=("Segoe UI", 12, "bold"),
            tags="pause_ui"
        )

        self.theme_var = tk.StringVar(value=self.theme_name)

        self.theme_menu = tk.OptionMenu(
            self.canvas,
            self.theme_var,
            *THEMES.keys(),
            command=self.change_theme
        )
        self.style_menu(self.theme_menu)
        self.pause_widgets.append(self.theme_menu)

        self.canvas.create_window(
            WIDTH / 2, 498,
            window=self.theme_menu,
            width=190, height=29,
            tags="pause_ui"
        )

        self.make_button(
            "RESUME GAME", self.toggle_pause,
            548, 190, self.theme["accent"], self.theme["bg"]
        )

    def style_menu(self, menu):
        menu.config(
            bg=self.theme["panel_light"],
            fg=self.theme["text"],
            activebackground=self.theme["accent"],
            activeforeground=self.theme["bg"],
            highlightthickness=0,
            relief="flat",
            font=("Segoe UI", 10)
        )
        menu["menu"].config(
            bg=self.theme["panel"],
            fg=self.theme["text"],
            activebackground=self.theme["accent"],
            activeforeground=self.theme["bg"]
        )

    def make_button(self, label, command, y, width, bg, fg):
        button = tk.Button(
            self.canvas,
            text=label,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=self.theme["text"],
            activeforeground=self.theme["bg"],
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2"
        )
        self.pause_widgets.append(button)

        self.canvas.create_window(
            WIDTH / 2, y,
            window=button, width=width, height=30,
            tags="pause_ui"
        )

    def add_setting(self, label, key, minimum, maximum, step):
        row = tk.Frame(self.settings_frame, bg=self.theme["panel"])
        row.pack(fill="x", pady=3)

        tk.Label(
            row, text=label,
            bg=self.theme["panel"], fg=self.theme["text"],
            font=("Segoe UI", 9)
        ).pack(anchor="w")

        slider = tk.Scale(
            row,
            from_=minimum, to=maximum,
            resolution=step,
            orient="horizontal",
            showvalue=True,
            command=lambda value, k=key: self.update_setting(k, value),
            bg=self.theme["panel"],
            fg=self.theme["accent"],
            troughcolor=self.theme["panel_light"],
            highlightthickness=0, bd=0,
            activebackground=self.theme["accent"],
            length=390
        )
        slider.set(self.settings[key])
        slider.pack(fill="x")

    def update_setting(self, key, value):
        self.settings[key] = float(value)

    def reset_tunes(self):
        self.settings = DEFAULT_SETTINGS.copy()
        self.show_pause_menu()

    def change_player_color(self, selected):
        if selected not in PLAYER_COLORS:
            return

        self.player_color_name = selected
        self.player_color = PLAYER_COLORS[selected]

        if hasattr(self, "player"):
            self.canvas.itemconfigure(
                self.player, fill=self.player_color
            )

    def change_theme(self, selected):
        if selected not in THEMES:
            return

        self.theme_name = selected
        self.theme = THEMES[selected]

        self.root.configure(bg=self.theme["bg"])
        self.header.configure(bg=self.theme["panel"])
        self.title_label.configure(
            bg=self.theme["panel"], fg=self.theme["accent"]
        )
        self.score_label.configure(
            bg=self.theme["panel"], fg=self.theme["text"]
        )
        self.best_label.configure(
            bg=self.theme["panel"], fg=self.theme["accent"]
        )
        self.footer.configure(bg=self.theme["panel"])
        self.footer_left.configure(
            bg=self.theme["panel"], fg=self.theme["muted"]
        )
        self.footer_right.configure(
            bg=self.theme["panel"], fg=self.theme["accent"]
        )

        if self.paused:
            self.show_pause_menu()
        else:
            self.redraw_game()

    def redraw_game(self):
        self.draw_background()

        self.canvas.itemconfigure(
            self.player, fill=self.player_color
        )

        for block in self.blocks:
            for item in block["items"]:
                self.canvas.itemconfigure(
                    item, fill=block["color"]
                )

    def spawn_block(self):
        # Pick a standard tetromino, then rotate it in 90-degree steps.
        name = random.choice(list(SHAPES.keys()))
        turns = random.randint(0, 3)
        cells = rotate_shape(SHAPES[name], turns)

        color = PIECE_COLORS[name]

        min_x = min(x for x, y in cells)
        max_x = max(x for x, y in cells)
        min_y = min(y for x, y in cells)

        shape_width = max_x - min_x + 1
        shape_height = max(y for x, y in cells) - min_y + 1

        left = random.randint(
            0, max(0, WIDTH // CELL - shape_width)
        ) * CELL

        # Begin just above the top of the play area.
        top = -shape_height * CELL

        items = []

        for cx, cy in cells:
            x = left + cx * CELL
            y = top + cy * CELL

            item = self.canvas.create_rectangle(
                x + 1, y + 1,
                x + CELL - 1, y + CELL - 1,
                fill=color,
                outline="#10131c",
                width=1
            )
            items.append(item)

        speed = random.uniform(2.5, 4.0)
        speed += min(self.score * 0.02, 4)
        speed *= self.settings["difficulty"]

        self.blocks.append({
            "items": items,
            "cells": cells,
            "x": left,
            "y": top,
            "width": shape_width,
            "height": shape_height,
            "color": color,
            "speed": speed,
            "scored": False
        })

    def tick(self):
        if not self.paused and not self.game_over:
            self.frame += 1

            # Smooth movement with acceleration and friction.
            acceleration = self.settings["player_speed"]

            if "left" in self.keys or "a" in self.keys:
                self.player_vx -= acceleration

            if "right" in self.keys or "d" in self.keys:
                self.player_vx += acceleration

            self.player_vx = max(-10, min(10, self.player_vx))
            self.player_vx *= self.settings["friction"]

            if abs(self.player_vx) < 0.08:
                self.player_vx = 0

            self.player_x += self.player_vx

            half = PLAYER_W / 2

            if self.player_x < half:
                self.player_x = half
                self.player_vx = 0

            if self.player_x > WIDTH - half:
                self.player_x = WIDTH - half
                self.player_vx = 0

            self.canvas.coords(
                self.player,
                self.player_x - half,
                self.player_y - PLAYER_H / 2,
                self.player_x + half,
                self.player_y + PLAYER_H / 2
            )

            spawn_every = max(
                18,
                int((38 - self.score // 5) /
                    self.settings["difficulty"])
            )

            if self.frame % spawn_every == 0:
                self.spawn_block()

            player_box = (
                self.player_x - PLAYER_W / 2 + 4,
                self.player_y - PLAYER_H / 2 + 3,
                self.player_x + PLAYER_W / 2 - 4,
                self.player_y + PLAYER_H / 2 - 3
            )

            remaining = []

            for block in self.blocks:
                block["y"] += block["speed"]

                for index, (cx, cy) in enumerate(block["cells"]):
                    x = block["x"] + cx * CELL
                    y = block["y"] + cy * CELL

                    self.canvas.coords(
                        block["items"][index],
                        x + 1, y + 1,
                        x + CELL - 1, y + CELL - 1
                    )

                    collision = (
                        player_box[0] < x + CELL - 1
                        and player_box[2] > x + 1
                        and player_box[1] < y + CELL - 1
                        and player_box[3] > y + 1
                    )

                    if collision:
                        self.end_game()
                        break

                if self.game_over:
                    break

                # Award a point when every cell of the piece clears
                # the bottom of the play area.
                if block["y"] > HEIGHT:
                    if not block["scored"]:
                        self.score += 1
                        block["scored"] = True

                    for item in block["items"]:
                        self.canvas.delete(item)
                else:
                    remaining.append(block)

            self.blocks = remaining

            if not self.game_over:
                self.score_label.config(
                    text=f"SCORE  {self.score}"
                )

        self.root.after(16, self.tick)

    def end_game(self):
        self.game_over = True
        self.keys.clear()

        if self.score > self.high_score:
            try:
                self.store.save(self.score)
                self.high_score = self.score
                self.best_label.config(
                    text=f"BEST  {self.high_score}"
                )
            except Exception as error:
                print(f"Could not save high score: {error}")

        self.canvas.create_rectangle(
            65, 245, WIDTH - 65, 455,
            fill=self.theme["panel"],
            outline=self.theme["accent"],
            width=2
        )

        self.canvas.create_text(
            WIDTH / 2, 285,
            text="GAME OVER",
            fill=self.theme["danger"],
            font=("Segoe UI", 26, "bold")
        )

        self.canvas.create_text(
            WIDTH / 2, 330,
            text=f"Score: {self.score}",
            fill=self.theme["text"],
            font=("Segoe UI", 16)
        )

        self.canvas.create_text(
            WIDTH / 2, 365,
            text=f"All-time best: {self.high_score}",
            fill=self.theme["accent"],
            font=("Segoe UI", 13, "bold")
        )

        self.canvas.create_text(
            WIDTH / 2, 415,
            text="Press R to play again",
            fill=self.theme["accent"],
            font=("Segoe UI", 12, "bold")
        )


if __name__ == "__main__":
    root = tk.Tk()
    game = DodgeGame(root)
    root.mainloop()