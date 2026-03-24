
import os
import re
import sys
import threading
import urllib.request
from datetime import datetime
from io import BytesIO
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from core.downloader import Downloader
from core.media_probe import MediaProbe, MediaProbeError
from core.storage import AppStorage

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class SmoothScrollableFrame(ctk.CTkScrollableFrame):
    def __init__(self, *args, scroll_speed_getter=None, **kwargs):
        bg = kwargs.get("fg_color", "#0a0a0a")
        if bg == "transparent": bg = "#0a0a0a"
        kwargs.setdefault("scrollbar_button_color", bg)
        kwargs.setdefault("scrollbar_button_hover_color", bg)
        super().__init__(*args, **kwargs)
        self._wheel_residual_y = 0.0
        self._wheel_residual_x = 0.0
        self._scroll_speed_getter = scroll_speed_getter

    def _nearest_scroll_target(self, widget):
        import tkinter as tk
        current = widget
        while current:
            if isinstance(current, tk.Text):
                return "text"
            if isinstance(current, tk.Canvas):
                master = getattr(current, "master", None)
                if hasattr(master, "_parent_canvas") and getattr(master, "_parent_canvas") == current:
                    return current
            current = getattr(current, "master", None)
        return None

    def _mouse_wheel_all(self, event):
        target = self._nearest_scroll_target(event.widget)
        if target == "text":
            return
        if target != self._parent_canvas:
            return
        horizontal = self._shift_pressed
        view = self._parent_canvas.xview if horizontal else self._parent_canvas.yview
        if view() == (0.0, 1.0):
            return

        if sys.platform.startswith("win"):
            step = -event.delta / 24.0
        elif sys.platform == "darwin":
            step = -event.delta / 3.0
        else:
            step = -event.delta / 2.0
        speed = 1.0
        if callable(self._scroll_speed_getter):
            try:
                speed = max(0.4, min(2.2, float(self._scroll_speed_getter())))
            except Exception:
                speed = 1.0
        step *= speed

        residual_attr = "_wheel_residual_x" if horizontal else "_wheel_residual_y"
        residual = getattr(self, residual_attr) + step
        units = int(residual)
        if units != 0:
            axis = self._parent_canvas.xview if horizontal else self._parent_canvas.yview
            axis("scroll", units, "units")
            residual -= units
        setattr(self, residual_attr, residual)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("YT-MEDIA Downloader")
        self.min_window_width = 760
        self.min_window_height = 560
        self.geometry(f"{self.min_window_width}x{self.min_window_height}")
        self.minsize(self.min_window_width, self.min_window_height)
        self.palette = {
            "bg": "#0a0a0a",
            "panel": "#121212",
            "panel_soft": "#1e1e1e",
            "panel_alt": "#0f0f0f",
            "line": "#2c2c2c",
            "text_muted": "#888888",
            "accent": "#d32f2f",
            "accent_hover": "#ff5252",
            "danger": "#ff1744",
        }
        self.configure(fg_color=self.palette["bg"])

        self.modes = ["Video", "Audio", "Playlist", "Post", "Thumbnail"]
        self.nav_pages = ["Downloader", "Downloads", "Settings"]
        self.qualities = {
            "Video": ["Best", "4K", "1440p", "1080p", "720p", "480p", "360p"],
            "Audio": ["Best", "320kbps", "256kbps", "192kbps", "128kbps"],
            "PlaylistVideo": ["Best", "1080p", "720p"],
            "PlaylistAudio": ["Best", "320kbps", "128kbps"],
            "Post": ["Best"],
            "Thumbnail": ["Best"],
        }
        self.spacing_profiles = {
            "regular": {"outer_pad": 22, "card_pad": 18, "row_gap": 14, "small_gap": 8},
            "compact": {"outer_pad": 14, "card_pad": 12, "row_gap": 10, "small_gap": 6},
        }
        self.font_profiles = {
            "regular": {
                "brand_icon": 14,
                "brand_title": 18,
                "nav": 14,
                "section_title": 15,
                "h1": 22,
                "h2": 20,
                "button": 15,
                "button_lg": 16,
                "body": 13,
                "body_sm": 12,
                "meta": 11,
                "chip": 11,
                "code": 10,
                "footer": 12,
            },
            "compact": {
                "brand_icon": 13,
                "brand_title": 16,
                "nav": 12,
                "section_title": 14,
                "h1": 18,
                "h2": 18,
                "button": 14,
                "button_lg": 15,
                "body": 12,
                "body_sm": 11,
                "meta": 10,
                "chip": 10,
                "code": 9,
                "footer": 11,
            },
        }
        self.fonts = {}
        self._density = "regular"
        self._init_fonts()

        self.storage = AppStorage()
        self.settings = self.storage.load_settings()
        self.preferences = self._load_preferences()
        self.downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        pref_dir = self.preferences.get("default_output_dir", "")
        self.default_output_dir = pref_dir if pref_dir and os.path.isdir(pref_dir) else self.downloads_dir
        self._font_scale = float(self.preferences.get("font_scale", 1.0))
        self._scroll_speed = float(self.preferences.get("scroll_speed", 1.0))
        self.history_entries = self.storage.load_history()
        self.history_entries = self.history_entries[: int(self.preferences.get("history_limit", 30))]
        self.dl = Downloader(on_progress=self._on_progress, on_log=self._on_log, on_complete=self._on_complete)
        self.probe = MediaProbe()

        self.active_page = ctk.StringVar(value="Downloader")
        self.active_mode = ctk.StringVar(value="Video")
        self.pref_density_var = ctk.StringVar(value=str(self.preferences.get("ui_density_mode", "auto")).capitalize())
        self.pref_font_scale_var = ctk.DoubleVar(value=max(85.0, min(125.0, self._font_scale * 100.0)))
        self.pref_scroll_speed_var = ctk.DoubleVar(value=max(60.0, min(170.0, self._scroll_speed * 100.0)))
        self.pref_show_logs_var = ctk.BooleanVar(value=bool(self.preferences.get("show_logs", True)))
        self.pref_auto_analyze_var = ctk.BooleanVar(value=bool(self.preferences.get("auto_analyze", False)))
        self.pref_history_limit_var = ctk.StringVar(value=str(int(self.preferences.get("history_limit", 30))))
        self.pref_default_dir_var = ctk.StringVar(value=self.default_output_dir)
        self.current_job = None
        self.logs_visible = True
        self._save_job = None
        self._booting = True
        self._persistence_bound = False
        self._auto_analyze_job = None
        self.nav_buttons = {}
        self.history_rows = []
        self.history_folder_buttons = []
        self.queue_preview_rows = []
        self.states = {m: self._new_state() for m in self.modes}
        self.preview_placeholder = self._create_preview_placeholder()

        self._build_shell()
        self._apply_saved()
        self.after_idle(self._finish_initial_render)
        self.bind("<Configure>", self._on_resize)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_fonts(self):
        self.fonts = {
            "brand_icon": ctk.CTkFont(family="Segoe UI Symbol", size=self.font_profiles["regular"]["brand_icon"], weight="bold"),
            "brand_title": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["brand_title"], weight="bold"),
            "nav": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["nav"], weight="bold"),
            "section_title": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["section_title"], weight="bold"),
            "h1": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["h1"], weight="bold"),
            "h2": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["h2"], weight="bold"),
            "button": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["button"], weight="bold"),
            "button_lg": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["button_lg"], weight="bold"),
            "body": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["body"]),
            "body_sm": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["body_sm"]),
            "meta": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["meta"]),
            "chip": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["chip"], weight="bold"),
            "code": ctk.CTkFont(family="Consolas", size=self.font_profiles["regular"]["code"]),
            "footer": ctk.CTkFont(family="Segoe UI", size=self.font_profiles["regular"]["footer"]),
        }

    def _load_preferences(self):
        defaults = {
            "ui_density_mode": "auto",
            "font_scale": 1.0,
            "scroll_speed": 1.0,
            "show_logs": True,
            "auto_analyze": False,
            "history_limit": 30,
            "default_output_dir": "",
            "remember_window_size": False,
        }
        raw = self.settings.get("preferences", {})
        pref = dict(defaults)
        if isinstance(raw, dict):
            pref.update(raw)
        try:
            pref["font_scale"] = max(0.85, min(1.25, float(pref.get("font_scale", 1.0))))
        except Exception:
            pref["font_scale"] = 1.0
        try:
            pref["scroll_speed"] = max(0.6, min(1.7, float(pref.get("scroll_speed", 1.0))))
        except Exception:
            pref["scroll_speed"] = 1.0
        try:
            pref["history_limit"] = max(10, min(200, int(pref.get("history_limit", 30))))
        except Exception:
            pref["history_limit"] = 30
        pref["show_logs"] = bool(pref.get("show_logs", True))
        pref["auto_analyze"] = bool(pref.get("auto_analyze", False))
        pref["remember_window_size"] = False
        mode = str(pref.get("ui_density_mode", "auto")).lower().strip()
        pref["ui_density_mode"] = mode if mode in ("auto", "regular", "compact") else "auto"
        default_dir = str(pref.get("default_output_dir", "")).strip()
        pref["default_output_dir"] = default_dir if default_dir and os.path.isdir(default_dir) else ""
        return pref

    def _new_state(self):
        return {
            "url": ctk.StringVar(),
            "dir": ctk.StringVar(value=self.default_output_dir),
            "quality": ctk.StringVar(value="Best"),
            "subtitles": ctk.BooleanVar(value=False),
            "thumbnail": ctk.BooleanVar(value=False),
            "playlist_format": ctk.StringVar(value="Video"),
            "playlist_max": ctk.StringVar(value="All"),
            "probe_busy": False,
            "probe_ticket": 0,
            "probe_data": None,
            "preview_image": None,
            "last_auto_url": "",
        }

    def _finish_initial_render(self):
        self._refresh_mode()
        self._refresh_history()
        self._refresh_current()
        self._refresh_queue_preview()
        self._apply_logs_visibility(self.pref_show_logs_var.get())
        self._on_settings_font_scale()
        self._on_settings_scroll_speed()
        self._bind_persistence()
        self._booting = False
        self._sync_density_from_size(force=True)

    def _create_preview_placeholder(self):
        image = Image.new("RGB", (250, 140), "#0D1628")
        return ctk.CTkImage(light_image=image, dark_image=image, size=(250, 140))

    def _build_thumbnail_image(self, raw_bytes):
        image = Image.open(BytesIO(raw_bytes)).convert("RGB")
        image.thumbnail((250, 140), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (250, 140), "#0D1628")
        x = (250 - image.width) // 2
        y = (140 - image.height) // 2
        canvas.paste(image, (x, y))
        return ctk.CTkImage(light_image=canvas, dark_image=canvas, size=(250, 140))

    def _build_shell(self):
        gap = self.spacing_profiles["regular"]
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.top_bar = ctk.CTkFrame(self, fg_color=self.palette["panel_alt"], corner_radius=0, height=56)
        self.top_bar.grid(row=0, column=0, sticky="ew")
        self.top_bar.grid_propagate(False)
        self.top_bar.grid_columnconfigure(1, weight=1)
        brand = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        brand.grid(row=0, column=0, padx=(14, gap["outer_pad"]), pady=10, sticky="w")
        ctk.CTkLabel(
            brand,
            text="▶",
            width=28,
            height=28,
            text_color="#FFFFFF",
            fg_color="#DA3C3C",
            corner_radius=6,
            font=self.fonts["brand_icon"],
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkLabel(
            brand,
            text="YT-MEDIA DOWNLOADER",
            font=self.fonts["brand_title"],
            text_color="#FFFFFF",
        ).grid(row=0, column=1, sticky="w")

        self.nav_strip = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        self.nav_strip.grid(row=0, column=1, sticky="w")
        for i, p in enumerate(self.nav_pages):
            b = ctk.CTkButton(
                self.nav_strip,
                text=p,
                width=104,
                height=34,
                fg_color="transparent",
                hover_color=self.palette["panel_soft"],
                text_color="#9E9E9E",
                font=self.fonts["nav"],
                command=lambda x=p: self._show_page(x),
            )
            b.grid(row=0, column=i, padx=4, pady=8)
            self.nav_buttons[p] = b

        self.body = ctk.CTkFrame(self, fg_color=self.palette["bg"], corner_radius=0)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self._build_downloader_page()
        self._build_downloads_page()
        self._build_settings_page()

        self.footer_bar = ctk.CTkFrame(self, fg_color=self.palette["panel_alt"], corner_radius=0, height=34)
        self.footer_bar.grid(row=2, column=0, sticky="ew")
        self.footer_bar.grid_propagate(False)
        self.footer_bar.grid_columnconfigure(0, weight=1)
        self.footer_left = ctk.CTkLabel(self.footer_bar, text="Ready", text_color="#FFFFFF", font=self.fonts["footer"])
        self.footer_left.grid(row=0, column=0, padx=16, pady=6, sticky="w")
        self.footer_right = ctk.CTkLabel(self.footer_bar, text="0.0 MiB/s", text_color="#9E9E9E", font=self.fonts["footer"])
        self.footer_right.grid(row=0, column=1, padx=16, pady=6, sticky="e")
    def _build_downloader_page(self):
        gap = self.spacing_profiles["regular"]
        page = ctk.CTkFrame(self.body, fg_color=self.palette["bg"])
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(0, weight=1)

        self.downloader_scroll = SmoothScrollableFrame(page, fg_color=self.palette["bg"], corner_radius=0, scroll_speed_getter=lambda: self._scroll_speed)
        self.downloader_scroll.grid(row=0, column=0, sticky="nsew")
        self.downloader_scroll.grid_columnconfigure(0, weight=1)

        self.mode_card = ctk.CTkFrame(self.downloader_scroll, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        self.mode_card.grid(row=0, column=0, sticky="ew", padx=gap["outer_pad"], pady=(gap["outer_pad"], gap["row_gap"]))
        self.mode_card.grid_columnconfigure(0, weight=1)
        self.mode_label = ctk.CTkLabel(self.mode_card, text="Content Type", text_color="#FFFFFF", font=self.fonts["body_sm"])
        self.mode_label.grid(row=0, column=0, padx=gap["card_pad"], pady=(10, 4), sticky="w")
        self.mode_switch = ctk.CTkSegmentedButton(
            self.mode_card,
            values=self.modes,
            variable=self.active_mode,
            command=lambda _: self._on_mode_change(),
            selected_color=self.palette["accent"],
            selected_hover_color=self.palette["accent_hover"],
            unselected_color=self.palette["panel_soft"],
            unselected_hover_color=self.palette["panel_alt"],
            text_color="#FFFFFF",
            font=self.fonts["body_sm"],
            height=34,
        )
        self.mode_switch.grid(row=1, column=0, padx=gap["card_pad"], pady=(0, 12), sticky="ew")

        self.url_card = ctk.CTkFrame(self.downloader_scroll, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        self.url_card.grid(row=1, column=0, sticky="ew", padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.url_card.grid_columnconfigure(0, weight=1)
        self.url_entry = ctk.CTkEntry(
            self.url_card,
            height=42,
            corner_radius=8, border_width=1, border_color=self.palette["line"],
            fg_color=self.palette["panel_soft"],
            placeholder_text="Paste media URL (e.g., https://www.youtube.com/watch?v=...)",
            font=self.fonts["body_sm"],
        )
        self.url_entry.grid(row=0, column=0, padx=(gap["card_pad"], gap["small_gap"]), pady=gap["card_pad"], sticky="ew")
        self.fetch_btn = ctk.CTkButton(
            self.url_card,
            text="Analyze",
            width=112,
            height=42,
            corner_radius=8, border_width=1, border_color=self.palette["line"],
            fg_color=self.palette["accent"],
            hover_color=self.palette["accent_hover"],
            font=self.fonts["button"],
            command=self._analyze,
        )
        self.fetch_btn.grid(row=0, column=1, padx=(0, gap["card_pad"]), pady=gap["card_pad"])
        self.url_hint = ctk.CTkLabel(
            self.url_card,
            text="Supported sources: YouTube, Vimeo, Dailymotion, and other compatible platforms.",
            text_color="#9E9E9E",
            font=self.fonts["meta"],
        )
        self.url_hint.grid(row=1, column=0, columnspan=2, padx=gap["outer_pad"], pady=(0, 12), sticky="w")

        self.preview_card = ctk.CTkFrame(self.downloader_scroll, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        self.preview_card.grid(row=2, column=0, sticky="ew", padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.preview_card.grid_columnconfigure(1, weight=1)
        self.preview_thumb = ctk.CTkLabel(
            self.preview_card,
            text="Preview unavailable",
            image=self.preview_placeholder,
            width=250,
            height=140,
            corner_radius=8,
            fg_color=self.palette["panel_soft"],
            text_color="#9E9E9E",
            compound="center",
            font=self.fonts["meta"],
        )
        self.preview_thumb.grid(row=0, column=0, rowspan=4, padx=(gap["card_pad"], 14), pady=gap["card_pad"], sticky="nw")
        self.preview_title = ctk.CTkLabel(
            self.preview_card,
            text="Paste a media URL to load metadata.",
            anchor="w",
            justify="left",
            wraplength=650,
            text_color="#FFFFFF",
            font=self.fonts["h1"],
        )
        self.preview_title.grid(row=0, column=1, padx=(0, gap["card_pad"]), pady=(18, 6), sticky="ew")
        self.preview_mode_chip = ctk.CTkLabel(
            self.preview_card,
            text="VIDEO",
            text_color="#FFFFFF",
            fg_color=self.palette["panel_soft"],
            corner_radius=6,
            padx=10,
            pady=4,
            font=self.fonts["chip"],
        )
        self.preview_mode_chip.grid(row=0, column=2, padx=(0, gap["card_pad"]), pady=(18, 6), sticky="e")
        self.preview_meta = ctk.CTkLabel(
            self.preview_card,
            text="Title, source, duration, and quality metadata appear after analysis.",
            anchor="w",
            justify="left",
            wraplength=650,
            text_color="#9E9E9E",
            font=self.fonts["body_sm"],
        )
        self.preview_meta.grid(row=1, column=1, columnspan=2, padx=(0, gap["card_pad"]), pady=(0, 6), sticky="ew")
        self.preview_status = ctk.CTkLabel(
            self.preview_card,
            text="Run Analyze to load media information.",
            anchor="w",
            justify="left",
            wraplength=650,
            text_color="#FFFFFF",
            font=self.fonts["body_sm"],
        )
        self.preview_status.grid(row=2, column=1, columnspan=2, padx=(0, gap["card_pad"]), pady=(0, 8), sticky="ew")
        self.preview_details = ctk.CTkFrame(self.preview_card, fg_color=self.palette["panel_soft"], corner_radius=8, border_width=1, border_color=self.palette["line"],)
        self.preview_details.grid(row=3, column=1, columnspan=2, padx=(0, gap["card_pad"]), pady=(0, gap["card_pad"]), sticky="ew")
        self.preview_details.grid_columnconfigure((0, 1, 2), weight=1)
        self.preview_detail_left = ctk.CTkLabel(self.preview_details, text="Type: Video", anchor="w", text_color="#FFFFFF", font=self.fonts["meta"])
        self.preview_detail_left.grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.preview_detail_mid = ctk.CTkLabel(self.preview_details, text="Output: MP4", anchor="center", text_color="#9E9E9E", font=self.fonts["meta"])
        self.preview_detail_mid.grid(row=0, column=1, padx=10, pady=8)
        self.preview_detail_right = ctk.CTkLabel(self.preview_details, text="Best quality", anchor="e", text_color="#9E9E9E", font=self.fonts["meta"])
        self.preview_detail_right.grid(row=0, column=2, padx=10, pady=8, sticky="e")

        self.opts_card = ctk.CTkFrame(self.downloader_scroll, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        self.opts_card.grid(row=3, column=0, sticky="ew", padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.opts_card.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.lbl_quality = ctk.CTkLabel(self.opts_card, text="Quality", text_color="#FFFFFF", font=self.fonts["body_sm"])
        self.lbl_quality.grid(row=0, column=0, padx=12, pady=(14, 6), sticky="w")
        self.quality_menu = ctk.CTkOptionMenu(self.opts_card,fg_color=self.palette["panel_soft"], button_color=self.palette["panel_soft"], button_hover_color=self.palette["panel_alt"], dropdown_hover_color=self.palette["accent"],  height=36, font=self.fonts["body_sm"], dropdown_font=self.fonts["body_sm"])
        self.quality_menu.grid(row=1, column=0, padx=12, pady=(0, 14), sticky="ew")
        self.lbl_playlist_type = ctk.CTkLabel(self.opts_card, text="Playlist Type", text_color="#FFFFFF", font=self.fonts["body_sm"])
        self.lbl_playlist_type.grid(row=0, column=1, padx=12, pady=(14, 6), sticky="w")
        self.playlist_type = ctk.CTkOptionMenu(
            self.opts_card,
            values=["Video", "Audio"],fg_color=self.palette["panel_soft"], button_color=self.palette["panel_soft"], button_hover_color=self.palette["panel_alt"], dropdown_hover_color=self.palette["accent"], 
            height=36,
            command=lambda _: self._on_playlist_type(),
            font=self.fonts["body_sm"],
            dropdown_font=self.fonts["body_sm"],
        )
        self.playlist_type.grid(row=1, column=1, padx=12, pady=(0, 14), sticky="ew")
        self.lbl_max_items = ctk.CTkLabel(self.opts_card, text="Max Items", text_color="#FFFFFF", font=self.fonts["body_sm"])
        self.lbl_max_items.grid(row=0, column=2, padx=12, pady=(14, 6), sticky="w")
        self.max_items = ctk.CTkEntry(self.opts_card, height=36, placeholder_text="All", font=self.fonts["body_sm"])
        self.max_items.grid(row=1, column=2, padx=12, pady=(0, 14), sticky="ew")
        self.toggle_group = ctk.CTkFrame(self.opts_card, fg_color="transparent")
        self.toggle_group.grid(row=0, column=3, rowspan=2, padx=12, pady=10, sticky="ew")
        self.subs_switch = ctk.CTkSwitch(self.toggle_group, text="Subtitles", progress_color=self.palette["accent"], font=self.fonts["body_sm"])
        self.subs_switch.grid(row=0, column=0, sticky="w", pady=(4, 8))
        self.thumb_switch = ctk.CTkSwitch(self.toggle_group, text="Embed Thumbnail", progress_color=self.palette["accent"], font=self.fonts["body_sm"])
        self.thumb_switch.grid(row=1, column=0, sticky="w")
        self.options_hint = ctk.CTkLabel(
            self.opts_card,
            text="",
            text_color="#9E9E9E",
            font=self.fonts["meta"],
            anchor="w",
            justify="left",
        )

        self.output_card = ctk.CTkFrame(self.downloader_scroll, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        self.output_card.grid(row=4, column=0, sticky="ew", padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.output_card.grid_columnconfigure(0, weight=1)
        self.dir_entry = ctk.CTkEntry(self.output_card, height=38, state="readonly", fg_color=self.palette["panel_soft"], font=self.fonts["body_sm"])
        self.dir_entry.grid(row=0, column=0, padx=(gap["card_pad"], 10), pady=14, sticky="ew")
        self.change_dir_btn = ctk.CTkButton(
            self.output_card,
            text="Change",
            width=100,
            height=38,
            fg_color=self.palette["panel_soft"],
            hover_color=self.palette["panel_alt"], border_width=1, border_color=self.palette["line"],
            font=self.fonts["body_sm"],
            command=self._browse,
        )
        self.change_dir_btn.grid(row=0, column=1, padx=(0, gap["card_pad"]), pady=14)

        self.action_card = ctk.CTkFrame(self.downloader_scroll, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        self.action_card.grid(row=5, column=0, sticky="ew", padx=gap["outer_pad"], pady=(0, gap["outer_pad"]))
        self.action_card.grid_columnconfigure(0, weight=1)
        self.download_btn = ctk.CTkButton(
            self.action_card,
            text="Download",
            height=44,
            fg_color=self.palette["accent"],
            hover_color=self.palette["accent_hover"],
            font=self.fonts["button_lg"],
            command=self.trigger_action,
        )
        self.download_btn.grid(row=0, column=0, padx=gap["card_pad"], pady=(14, 10), sticky="ew")
        meta = ctk.CTkFrame(self.action_card, fg_color="transparent")
        meta.grid(row=1, column=0, padx=gap["card_pad"], pady=(0, 12), sticky="ew")
        meta.grid_columnconfigure((0, 1, 2), weight=1)
        self.prog_pct = ctk.CTkLabel(meta, text="0.0%", font=self.fonts["section_title"], text_color="#FFFFFF")
        self.prog_pct.grid(row=0, column=0, sticky="w")
        self.prog_speed = ctk.CTkLabel(meta, text="0.0 MiB/s", text_color="#9E9E9E", font=self.fonts["body_sm"])
        self.prog_speed.grid(row=0, column=1)
        self.prog_eta = ctk.CTkLabel(meta, text="ETA --:--", text_color="#9E9E9E", font=self.fonts["body_sm"])
        self.prog_eta.grid(row=0, column=2, sticky="e")
        self.prog_bar = ctk.CTkProgressBar(meta, height=8, progress_color=self.palette["accent"], fg_color=self.palette["panel_alt"])
        self.prog_bar.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 6))
        self.prog_bar.set(0)
        self.prog_title = ctk.CTkLabel(meta, text="Ready.", text_color="#FFFFFF", font=self.fonts["meta"])
        self.prog_title.grid(row=2, column=0, columnspan=3, sticky="w")

        self.queue_card = ctk.CTkFrame(self.downloader_scroll, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        self.queue_card.grid(row=6, column=0, sticky="ew", padx=gap["outer_pad"], pady=(0, gap["outer_pad"]))
        self.queue_card.grid_columnconfigure(0, weight=1)
        q_head = ctk.CTkFrame(self.queue_card, fg_color="transparent")
        q_head.grid(row=0, column=0, padx=12, pady=(10, 6), sticky="ew")
        q_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(q_head, text="Recent Activity", text_color="#FFFFFF", font=self.fonts["section_title"]).grid(row=0, column=0, sticky="w")
        self.open_downloads_btn = ctk.CTkButton(
            q_head,
            text="Open Downloads",
            width=120,
            height=28,
            fg_color=self.palette["panel_soft"],
            hover_color=self.palette["panel_alt"], border_width=1, border_color=self.palette["line"],
            font=self.fonts["body_sm"],
            command=lambda: self._show_page("Downloads"),
        )
        self.open_downloads_btn.grid(row=0, column=1, sticky="e")
        self.queue_preview = SmoothScrollableFrame(self.queue_card, fg_color=self.palette["panel_soft"], corner_radius=8, border_width=1, border_color=self.palette["line"], height=180, scroll_speed_getter=lambda: self._scroll_speed)
        self.queue_preview.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.queue_preview.grid_columnconfigure(0, weight=1)

        self.pages["Downloader"] = page

    def _build_downloads_page(self):
        gap = self.spacing_profiles["regular"]
        page = ctk.CTkFrame(self.body, fg_color=self.palette["bg"])
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(0, weight=1)
        self.downloads_scroll = SmoothScrollableFrame(page, fg_color=self.palette["bg"], corner_radius=0, scroll_speed_getter=lambda: self._scroll_speed)
        self.downloads_scroll.grid(row=0, column=0, sticky="nsew")
        self.downloads_scroll.grid_columnconfigure(0, weight=1)

        self.stats_card = ctk.CTkFrame(self.downloads_scroll, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        self.stats_card.grid(row=0, column=0, sticky="ew", padx=gap["outer_pad"], pady=(gap["outer_pad"], gap["row_gap"]))
        self.stats_card.grid_columnconfigure((0, 1, 2), weight=1)
        self.stats_completed = ctk.CTkLabel(self.stats_card, text="Completed: 0", text_color="#FFFFFF", font=self.fonts["section_title"])
        self.stats_completed.grid(row=0, column=0, padx=14, pady=12, sticky="w")
        self.stats_cancelled = ctk.CTkLabel(self.stats_card, text="Cancelled: 0", text_color="#FFFFFF", font=self.fonts["section_title"])
        self.stats_cancelled.grid(row=0, column=1, padx=14, pady=12)
        self.stats_failed = ctk.CTkLabel(self.stats_card, text="Failed: 0", text_color="#FFFFFF", font=self.fonts["section_title"])
        self.stats_failed.grid(row=0, column=2, padx=14, pady=12, sticky="e")

        self.current_card = ctk.CTkFrame(self.downloads_scroll, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        self.current_card.grid(row=1, column=0, sticky="ew", padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.current_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.current_card, text="Current Job", text_color="#FFFFFF", font=self.fonts["section_title"]).grid(row=0, column=0, padx=14, pady=(12, 6), sticky="w")
        self.current_badge = ctk.CTkLabel(self.current_card, text="IDLE", text_color="#FFFFFF", fg_color=self.palette["panel_soft"], corner_radius=6, padx=10, pady=4, font=self.fonts["chip"])
        self.current_badge.grid(row=0, column=1, padx=(0, 14), pady=(12, 6), sticky="e")
        self.current_title = ctk.CTkLabel(self.current_card, text="No active download.", anchor="w", text_color="#FFFFFF", font=self.fonts["body"])
        self.current_title.grid(row=1, column=0, padx=14, sticky="w")
        self.current_meta = ctk.CTkLabel(self.current_card, text="", anchor="w", text_color="#9E9E9E", font=self.fonts["body_sm"])
        self.current_meta.grid(row=2, column=0, padx=14, pady=(0, 8), sticky="w")
        self.current_progress = ctk.CTkProgressBar(self.current_card, height=8, progress_color=self.palette["accent"], fg_color=self.palette["panel_alt"])
        self.current_progress.grid(row=3, column=0, padx=14, pady=(0, 12), sticky="ew")
        self.current_progress.set(0)

        self.logs_card = ctk.CTkFrame(self.downloads_scroll, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        self.logs_card.grid(row=2, column=0, sticky="ew", padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.logs_card.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self.logs_card, fg_color="transparent")
        top.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Activity Log", text_color="#FFFFFF", font=self.fonts["section_title"]).grid(row=0, column=0, sticky="w")
        self.btn_logs = ctk.CTkButton(top, text="Hide Logs", width=90, height=28, fg_color=self.palette["panel_soft"], hover_color=self.palette["panel_alt"], font=self.fonts["body_sm"], command=self.toggle_logs)
        self.btn_logs.grid(row=0, column=1, sticky="e")
        self.log_box = ctk.CTkTextbox(self.logs_card, height=170, wrap="word", font=self.fonts["code"])
        self.log_box.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.log_box.configure(state="disabled")

        self.history_card = ctk.CTkFrame(self.downloads_scroll, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        self.history_card.grid(row=3, column=0, sticky="ew", padx=gap["outer_pad"], pady=(0, gap["outer_pad"]))
        self.history_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.history_card, text="History", text_color="#FFFFFF", font=self.fonts["section_title"]).grid(row=0, column=0, padx=14, pady=(12, 8), sticky="w")
        self.history_list = SmoothScrollableFrame(self.history_card, fg_color=self.palette["panel_soft"], corner_radius=8, border_width=1, border_color=self.palette["line"], height=260, scroll_speed_getter=lambda: self._scroll_speed)
        self.history_list.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.history_list.grid_columnconfigure(0, weight=1)

        self.pages["Downloads"] = page

    def _build_settings_page(self):
        gap = self.spacing_profiles["regular"]
        page = ctk.CTkFrame(self.body, fg_color=self.palette["bg"])
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(0, weight=1)
        s = SmoothScrollableFrame(page, fg_color=self.palette["bg"], corner_radius=0, scroll_speed_getter=lambda: self._scroll_speed)
        s.grid(row=0, column=0, sticky="nsew")
        s.grid_columnconfigure(0, weight=1)

        ui_card = ctk.CTkFrame(s, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        ui_card.grid(row=0, column=0, sticky="ew", padx=gap["outer_pad"], pady=(gap["outer_pad"], gap["row_gap"]))
        ui_card.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(ui_card, text="Interface", text_color="#FFFFFF", font=self.fonts["section_title"]).grid(row=0, column=0, columnspan=2, padx=14, pady=(12, 10), sticky="w")

        ctk.CTkLabel(ui_card, text="Density Mode", text_color="#FFFFFF", font=self.fonts["body_sm"]).grid(row=1, column=0, padx=14, pady=(0, 4), sticky="w")
        self.settings_density_menu = ctk.CTkOptionMenu(ui_card, values=["Auto", "Regular", "Compact"],fg_color=self.palette["panel_soft"], button_color=self.palette["panel_soft"], button_hover_color=self.palette["panel_alt"], dropdown_hover_color=self.palette["accent"],  variable=self.pref_density_var, command=lambda _: self._on_settings_density(), font=self.fonts["body_sm"], dropdown_font=self.fonts["body_sm"], height=34)
        self.settings_density_menu.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="ew")

        ctk.CTkLabel(ui_card, text="Log Panel", text_color="#FFFFFF", font=self.fonts["body_sm"]).grid(row=1, column=1, padx=14, pady=(0, 4), sticky="w")
        self.settings_show_logs_switch = ctk.CTkSwitch(ui_card, text="Show log panel in Downloads", variable=self.pref_show_logs_var, progress_color=self.palette["accent"], font=self.fonts["body_sm"], command=self._on_settings_show_logs)
        self.settings_show_logs_switch.grid(row=2, column=1, padx=14, pady=(0, 12), sticky="w")

        ctk.CTkLabel(ui_card, text="Font Scale", text_color="#FFFFFF", font=self.fonts["body_sm"]).grid(row=3, column=0, padx=14, pady=(0, 4), sticky="w")
        self.settings_font_slider = ctk.CTkSlider(ui_card,from_=85, to=125, variable=self.pref_font_scale_var, number_of_steps=40, progress_color=self.palette["accent"], button_color=self.palette["accent"], button_hover_color=self.palette["accent_hover"], command=lambda _: self._on_settings_font_scale())
        self.settings_font_slider.grid(row=4, column=0, padx=14, pady=(0, 6), sticky="ew")
        self.settings_font_label = ctk.CTkLabel(ui_card, text="100%", text_color="#9E9E9E", font=self.fonts["meta"])
        self.settings_font_label.grid(row=5, column=0, padx=14, pady=(0, 12), sticky="w")

        ctk.CTkLabel(ui_card, text="Scroll Smoothness", text_color="#FFFFFF", font=self.fonts["body_sm"]).grid(row=3, column=1, padx=14, pady=(0, 4), sticky="w")
        self.settings_scroll_slider = ctk.CTkSlider(ui_card,from_=60, to=170, variable=self.pref_scroll_speed_var, number_of_steps=55, progress_color=self.palette["accent"], button_color=self.palette["accent"], button_hover_color=self.palette["accent_hover"], command=lambda _: self._on_settings_scroll_speed())
        self.settings_scroll_slider.grid(row=4, column=1, padx=14, pady=(0, 6), sticky="ew")
        self.settings_scroll_label = ctk.CTkLabel(ui_card, text="100%", text_color="#9E9E9E", font=self.fonts["meta"])
        self.settings_scroll_label.grid(row=5, column=1, padx=14, pady=(0, 12), sticky="w")

        behavior_card = ctk.CTkFrame(s, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        behavior_card.grid(row=1, column=0, sticky="ew", padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        behavior_card.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(behavior_card, text="Behavior", text_color="#FFFFFF", font=self.fonts["section_title"]).grid(row=0, column=0, columnspan=2, padx=14, pady=(12, 10), sticky="w")

        self.settings_auto_analyze = ctk.CTkSwitch(behavior_card, text="Auto-analyze pasted URLs", variable=self.pref_auto_analyze_var, progress_color=self.palette["accent"], font=self.fonts["body_sm"], command=self._on_settings_auto_analyze)
        self.settings_auto_analyze.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="w")
        ctk.CTkLabel(behavior_card, text="Startup size: always minimum window size", text_color=self.palette["text_muted"], font=self.fonts["body_sm"]).grid(row=1, column=1, padx=14, pady=(0, 10), sticky="w")

        ctk.CTkLabel(behavior_card, text="Current Mode", text_color="#FFFFFF", font=self.fonts["body_sm"]).grid(row=2, column=0, padx=14, pady=(0, 4), sticky="w")
        self.settings_mode_menu = ctk.CTkOptionMenu(behavior_card, values=self.modes,fg_color=self.palette["panel_soft"], button_color=self.palette["panel_soft"], button_hover_color=self.palette["panel_alt"], dropdown_hover_color=self.palette["accent"],  variable=self.active_mode, command=lambda _: self._on_mode_change(), font=self.fonts["body_sm"], dropdown_font=self.fonts["body_sm"], height=34)
        self.settings_mode_menu.grid(row=3, column=0, padx=14, pady=(0, 12), sticky="ew")
        ctk.CTkButton(behavior_card, text="Open Downloader", height=34, fg_color=self.palette["panel_soft"], hover_color=self.palette["panel_alt"], border_width=1, border_color=self.palette["line"], font=self.fonts["body_sm"], command=lambda: self._show_page("Downloader")).grid(row=3, column=1, padx=14, pady=(0, 12), sticky="w")

        dl_card = ctk.CTkFrame(s, fg_color=self.palette["panel"], corner_radius=8, border_width=1, border_color=self.palette["line"])
        dl_card.grid(row=2, column=0, sticky="ew", padx=gap["outer_pad"], pady=(0, gap["outer_pad"]))
        dl_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(dl_card, text="Download Defaults", text_color="#FFFFFF", font=self.fonts["section_title"]).grid(row=0, column=0, padx=14, pady=(12, 10), sticky="w")

        ctk.CTkLabel(dl_card, text="Default Output Folder", text_color="#FFFFFF", font=self.fonts["body_sm"]).grid(row=1, column=0, padx=14, pady=(0, 4), sticky="w")
        folder_row = ctk.CTkFrame(dl_card, fg_color="transparent")
        folder_row.grid(row=2, column=0, padx=14, pady=(0, 10), sticky="ew")
        folder_row.grid_columnconfigure(0, weight=1)
        self.settings_default_dir_entry = ctk.CTkEntry(folder_row, textvariable=self.pref_default_dir_var, state="readonly", height=36, fg_color=self.palette["panel_soft"], font=self.fonts["body_sm"])
        self.settings_default_dir_entry.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkButton(folder_row, text="Browse", width=92, height=36, fg_color=self.palette["panel_soft"], hover_color=self.palette["panel_alt"], border_width=1, border_color=self.palette["line"], font=self.fonts["body_sm"], command=self._browse_default_output_dir).grid(row=0, column=1)

        bottom_row = ctk.CTkFrame(dl_card, fg_color="transparent")
        bottom_row.grid(row=3, column=0, padx=14, pady=(0, 12), sticky="ew")
        bottom_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bottom_row, text="History Limit", text_color="#FFFFFF", font=self.fonts["body_sm"]).grid(row=0, column=0, padx=(0, 8), sticky="w")
        self.settings_history_limit_menu = ctk.CTkOptionMenu(bottom_row, values=["20", "30", "50", "75", "100", "150", "200"],fg_color=self.palette["panel_soft"], button_color=self.palette["panel_soft"], button_hover_color=self.palette["panel_alt"], dropdown_hover_color=self.palette["accent"],  variable=self.pref_history_limit_var, command=lambda _: self._on_settings_history_limit(), font=self.fonts["body_sm"], dropdown_font=self.fonts["body_sm"], width=110, height=32)
        self.settings_history_limit_menu.grid(row=0, column=1, sticky="w")
        ctk.CTkButton(bottom_row, text="Apply Folder to All Modes", height=32, fg_color=self.palette["panel_soft"], hover_color=self.palette["panel_alt"], border_width=1, border_color=self.palette["line"], font=self.fonts["body_sm"], command=self._apply_default_output_dir_to_tabs).grid(row=0, column=2, padx=(12, 0), sticky="e")

        self.pages["Settings"] = page

    def _collect_preferences(self):
        try:
            history_limit = int(self.pref_history_limit_var.get())
        except Exception:
            history_limit = 30
        history_limit = max(10, min(200, history_limit))
        return {
            "ui_density_mode": self.pref_density_var.get().strip().lower(),
            "font_scale": round(self._font_scale, 3),
            "scroll_speed": round(self._scroll_speed, 3),
            "show_logs": bool(self.pref_show_logs_var.get()),
            "auto_analyze": bool(self.pref_auto_analyze_var.get()),
            "history_limit": history_limit,
            "default_output_dir": self.pref_default_dir_var.get().strip(),
            "remember_window_size": False,
        }

    def _apply_logs_visibility(self, visible):
        self.logs_visible = bool(visible)
        if hasattr(self, "btn_logs"):
            self.btn_logs.configure(text="Hide Logs" if self.logs_visible else "Show Logs")
        if hasattr(self, "log_box"):
            if self.logs_visible:
                self.log_box.grid()
            else:
                self.log_box.grid_remove()

    def _on_settings_density(self):
        self._sync_density_from_size(force=True)
        self._save_later()

    def _on_settings_font_scale(self):
        self._font_scale = max(0.85, min(1.25, float(self.pref_font_scale_var.get()) / 100.0))
        if hasattr(self, "settings_font_label"):
            self.settings_font_label.configure(text=f"{int(round(self._font_scale * 100))}%")
        self._apply_density(self._density)
        self._save_later()

    def _on_settings_scroll_speed(self):
        self._scroll_speed = max(0.6, min(1.7, float(self.pref_scroll_speed_var.get()) / 100.0))
        if hasattr(self, "settings_scroll_label"):
            self.settings_scroll_label.configure(text=f"{int(round(self._scroll_speed * 100))}%")
        self._save_later()

    def _on_settings_show_logs(self):
        self._apply_logs_visibility(self.pref_show_logs_var.get())
        self._save_later()

    def _on_settings_auto_analyze(self):
        if self.pref_auto_analyze_var.get():
            self._on_url_input_changed(self.active_mode.get())
        self._save_later()

    def _on_settings_history_limit(self):
        try:
            limit = int(self.pref_history_limit_var.get())
        except Exception:
            limit = 30
        limit = max(10, min(200, limit))
        self.pref_history_limit_var.set(str(limit))
        self.history_entries = self.history_entries[:limit]
        self.storage.save_history(self.history_entries, limit=limit)
        self._refresh_history()
        self._refresh_queue_preview()
        self._save_later()

    def _browse_default_output_dir(self):
        start = self.pref_default_dir_var.get() or self.downloads_dir
        d = filedialog.askdirectory(initialdir=start)
        if not d:
            return
        self.pref_default_dir_var.set(d)
        self.default_output_dir = d
        self._apply_default_output_dir_to_tabs()
        self._save_later()

    def _apply_default_output_dir_to_tabs(self):
        out = self.pref_default_dir_var.get().strip()
        if not out or not os.path.isdir(out):
            return
        self.default_output_dir = out
        for st in self.states.values():
            st["dir"].set(out)
        self._save_later()

    def _show_page(self, page):
        for n, f in self.pages.items():
            if n == page:
                f.grid(row=0, column=0, sticky="nsew")
            else:
                f.grid_forget()
        self.active_page.set(page)
        for n, b in self.nav_buttons.items():
            b.configure(
                fg_color=self.palette["panel_soft"] if n == page else "transparent",
                text_color="#FFFFFF" if n == page else self.palette["text_muted"], border_width=1 if n == page else 0,
                border_color=self.palette["accent"] if n == page else self.palette["panel_soft"],
            )
        self._save_later()

    def _state(self):
        return self.states[self.active_mode.get()]
    def _on_mode_change(self):
        st = self._state()
        self.fetch_btn.configure(state="disabled" if st["probe_busy"] else "normal", text="Analyzing..." if st["probe_busy"] else "Analyze")
        self._refresh_mode()
        self._save_later()

    def _on_playlist_type(self):
        if self.active_mode.get() == "Playlist":
            self._state()["quality"].set("Best")
            self._set_quality_values()
            self._save_later()

    def _set_quality_values(self):
        st = self._state()
        mode = self.active_mode.get()
        vals = self.qualities["Playlist" + st["playlist_format"].get()] if mode == "Playlist" else self.qualities[mode]
        self.quality_menu.configure(values=vals)
        if st["quality"].get() not in vals:
            st["quality"].set(vals[0])

    def _refresh_mode(self):
        st = self._state()
        self.url_entry.configure(textvariable=st["url"])
        self.dir_entry.configure(textvariable=st["dir"])
        self.quality_menu.configure(variable=st["quality"])
        self.playlist_type.configure(variable=st["playlist_format"])
        self.max_items.configure(textvariable=st["playlist_max"])
        self.subs_switch.configure(variable=st["subtitles"])
        self.thumb_switch.configure(variable=st["thumbnail"])
        self._set_quality_values()
        self._apply_options_layout(self._density == "compact")
        self._refresh_preview()

    def _refresh_preview(self):
        st = self._state()
        pd = st["probe_data"] or {}
        mode = self.active_mode.get()
        mode_label, output_label, extra_label = self._preview_profile(mode, pd)
        self.preview_mode_chip.configure(text=mode_label)
        if pd:
            self.preview_title.configure(text=pd.get("title", "Untitled"))
            meta = [f"Uploader: {pd.get('uploader', 'Unknown')}", f"Duration: {pd.get('duration', 'Unknown')}", f"Source: {pd.get('extractor', 'Unknown')}"]
            if pd.get("playlist_count"):
                meta.append(f"Playlist items: {pd['playlist_count']}")
            if pd.get("qualities"):
                meta.append(f"Qualities: {', '.join(pd['qualities'])}")
            self.preview_meta.configure(text=" | ".join(meta))
            msg = f"Suggested mode: {pd.get('suggested_mode', 'Video')}"
            if pd.get("suggested_mode") != self.active_mode.get():
                msg += f" | Current mode: {self.active_mode.get()}"
            self.preview_status.configure(text=msg)
        else:
            self.preview_title.configure(text=f"{mode} mode ready. Paste a URL and click Analyze.")
            self.preview_meta.configure(text="Media metadata appears here after analysis.")
            self.preview_status.configure(text=extra_label)
        preview_img = st["preview_image"] if st["preview_image"] is not None else self.preview_placeholder
        self.preview_thumb.configure(text="" if st["preview_image"] else "Preview unavailable", image=preview_img)
        self.preview_detail_left.configure(text=f"Type: {mode_label}")
        self.preview_detail_mid.configure(text=f"Output: {output_label}")
        self.preview_detail_right.configure(text=extra_label)

    def _preview_profile(self, mode, pd):
        if mode == "Video":
            quality_hint = ", ".join((pd.get("qualities") or [])[:3]) if pd else "Best, 1080p, 720p"
            return "VIDEO", "MP4 Video", f"Focus: {quality_hint}"
        if mode == "Audio":
            quality_hint = ", ".join((pd.get("qualities") or [])[:2]) if pd and pd.get("qualities") else "Best, 320kbps"
            return "AUDIO", "MP3 Audio", f"Audio profile: {quality_hint}"
        if mode == "Playlist":
            count = pd.get("playlist_count") if pd else None
            count_text = f"{count} items" if count else "Batch ready"
            fmt = self._state()["playlist_format"].get()
            return "PLAYLIST", f"{fmt} Collection", f"{count_text}"
        if mode == "Post":
            return "POST", "Best Available Media", "Single social post extraction"
        return "THUMBNAIL", "Image Only", "Highest-quality thumbnail download"

    def _apply_font_density(self, density):
        profile = self.font_profiles[density]
        for key, size in profile.items():
            if key in self.fonts:
                scaled_size = max(8, int(round(size * self._font_scale)))
                self.fonts[key].configure(size=scaled_size)

    def _apply_preview_layout(self, compact):
        card_pad = self.spacing_profiles[self._density]["card_pad"]
        if compact:
            self.preview_card.grid_columnconfigure(1, weight=1)
            self.preview_card.grid_columnconfigure(2, weight=1)
            self.preview_thumb.configure(width=210, height=118)
            self.preview_thumb.grid_configure(row=0, column=0, columnspan=3, rowspan=1, padx=card_pad, pady=(card_pad, 10), sticky="ew")
            self.preview_title.grid_configure(row=1, column=0, columnspan=3, padx=card_pad, pady=(0, 6), sticky="ew")
            self.preview_mode_chip.grid_configure(row=2, column=0, columnspan=1, padx=(card_pad, 8), pady=(0, 6), sticky="w")
            self.preview_meta.grid_configure(row=2, column=1, columnspan=2, padx=(0, card_pad), pady=(0, 6), sticky="ew")
            self.preview_status.grid_configure(row=3, column=0, columnspan=3, padx=card_pad, pady=(0, 8), sticky="ew")
            self.preview_details.grid_configure(row=4, column=0, columnspan=3, padx=card_pad, pady=(0, card_pad), sticky="ew")
        else:
            self.preview_thumb.configure(width=250, height=140)
            self.preview_thumb.grid_configure(row=0, column=0, columnspan=1, rowspan=4, padx=(card_pad, 14), pady=card_pad, sticky="nw")
            self.preview_title.grid_configure(row=0, column=1, columnspan=1, padx=(0, card_pad), pady=(18, 6), sticky="ew")
            self.preview_mode_chip.grid_configure(row=0, column=2, columnspan=1, padx=(0, card_pad), pady=(18, 6), sticky="e")
            self.preview_meta.grid_configure(row=1, column=1, columnspan=2, padx=(0, card_pad), pady=(0, 6), sticky="ew")
            self.preview_status.grid_configure(row=2, column=1, columnspan=2, padx=(0, card_pad), pady=(0, 8), sticky="ew")
            self.preview_details.grid_configure(row=3, column=1, columnspan=2, padx=(0, card_pad), pady=(0, card_pad), sticky="ew")

    def _apply_options_layout(self, compact):
        mode = self.active_mode.get()
        visibility = {
            "quality": mode in ("Video", "Audio", "Playlist"),
            "playlist_type": mode == "Playlist",
            "max_items": mode == "Playlist",
            "subs": mode in ("Video", "Playlist"),
            "thumb": mode in ("Video", "Audio", "Playlist"),
        }

        widgets = (
            self.lbl_quality,
            self.quality_menu,
            self.lbl_playlist_type,
            self.playlist_type,
            self.lbl_max_items,
            self.max_items,
            self.toggle_group,
            self.options_hint,
        )
        for widget in widgets:
            widget.grid_remove()

        self.subs_switch.grid_remove()
        self.thumb_switch.grid_remove()

        show_subs = visibility["subs"]
        show_thumb = visibility["thumb"]
        if show_subs:
            self.subs_switch.grid(row=0, column=0, sticky="w", pady=(2, 6) if show_thumb else (2, 2))
        if show_thumb:
            thumb_row = 1 if show_subs else 0
            self.thumb_switch.grid(row=thumb_row, column=0, sticky="w", pady=(0, 2))

        sections = []
        if visibility["quality"]:
            sections.append("quality")
        if visibility["playlist_type"]:
            sections.append("playlist_type")
        if visibility["max_items"]:
            sections.append("max_items")
        if show_subs or show_thumb:
            sections.append("toggles")

        for col in range(4):
            self.opts_card.grid_columnconfigure(col, weight=0)

        if not sections:
            hint_text = "No additional options are required for this mode."
            if mode == "Thumbnail":
                hint_text = "Thumbnail mode downloads the best available image automatically."
            if mode == "Post":
                hint_text = "Post mode automatically selects the best available media."
            self.options_hint.configure(text=hint_text)
            self.options_hint.grid(
                row=0,
                column=0,
                columnspan=2 if compact else 4,
                padx=12 if compact else 14,
                pady=(12, 12),
                sticky="w",
            )
            return

        if compact:
            self.opts_card.grid_columnconfigure((0, 1), weight=1)
            for idx, section in enumerate(sections):
                col = idx % 2
                row_base = (idx // 2) * 2
                if section == "quality":
                    self.lbl_quality.grid(row=row_base, column=col, padx=10, pady=(12, 4), sticky="w")
                    self.quality_menu.grid(row=row_base + 1, column=col, padx=10, pady=(0, 10), sticky="ew")
                elif section == "playlist_type":
                    self.lbl_playlist_type.grid(row=row_base, column=col, padx=10, pady=(12, 4), sticky="w")
                    self.playlist_type.grid(row=row_base + 1, column=col, padx=10, pady=(0, 10), sticky="ew")
                elif section == "max_items":
                    self.lbl_max_items.grid(row=row_base, column=col, padx=10, pady=(12, 4), sticky="w")
                    self.max_items.grid(row=row_base + 1, column=col, padx=10, pady=(0, 10), sticky="ew")
                elif section == "toggles":
                    self.toggle_group.grid(row=row_base, column=col, rowspan=2, padx=10, pady=(10, 8), sticky="w")
            return

        for idx, section in enumerate(sections):
            self.opts_card.grid_columnconfigure(idx, weight=1)
            if section == "quality":
                self.lbl_quality.grid(row=0, column=idx, padx=12, pady=(14, 6), sticky="w")
                self.quality_menu.grid(row=1, column=idx, padx=12, pady=(0, 14), sticky="ew")
            elif section == "playlist_type":
                self.lbl_playlist_type.grid(row=0, column=idx, padx=12, pady=(14, 6), sticky="w")
                self.playlist_type.grid(row=1, column=idx, padx=12, pady=(0, 14), sticky="ew")
            elif section == "max_items":
                self.lbl_max_items.grid(row=0, column=idx, padx=12, pady=(14, 6), sticky="w")
                self.max_items.grid(row=1, column=idx, padx=12, pady=(0, 14), sticky="ew")
            elif section == "toggles":
                self.toggle_group.grid(row=0, column=idx, rowspan=2, padx=12, pady=10, sticky="w")

    def _apply_density(self, density):
        if density not in self.spacing_profiles:
            return
        self._density = density
        gap = self.spacing_profiles[density]
        compact = density == "compact"
        self._apply_font_density(density)

        top_height = 50 if compact else 56
        footer_height = 30 if compact else 34
        self.top_bar.configure(height=top_height)
        self.footer_bar.configure(height=footer_height)
        self.footer_left.grid_configure(padx=gap["card_pad"], pady=6 if compact else 7)
        self.footer_right.grid_configure(padx=gap["card_pad"], pady=6 if compact else 7)

        for button in self.nav_buttons.values():
            button.configure(width=80 if compact else 104, height=30 if compact else 34)
            button.grid_configure(padx=3 if compact else 4, pady=6 if compact else 8)

        self.mode_card.grid_configure(padx=gap["outer_pad"], pady=(gap["outer_pad"], gap["row_gap"]))
        self.url_card.grid_configure(padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.preview_card.grid_configure(padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.opts_card.grid_configure(padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.output_card.grid_configure(padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.action_card.grid_configure(padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.queue_card.grid_configure(padx=gap["outer_pad"], pady=(0, gap["outer_pad"]))

        self.stats_card.grid_configure(padx=gap["outer_pad"], pady=(gap["outer_pad"], gap["row_gap"]))
        self.current_card.grid_configure(padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.logs_card.grid_configure(padx=gap["outer_pad"], pady=(0, gap["row_gap"]))
        self.history_card.grid_configure(padx=gap["outer_pad"], pady=(0, gap["outer_pad"]))

        self.mode_switch.configure(height=32 if compact else 34)
        self.url_entry.configure(height=38 if compact else 42)
        self.fetch_btn.configure(width=96 if compact else 112, height=38 if compact else 42)
        self.download_btn.configure(height=40 if compact else 44)
        self.change_dir_btn.configure(width=90 if compact else 100, height=36 if compact else 38)
        self.quality_menu.configure(height=34 if compact else 36)
        self.playlist_type.configure(height=34 if compact else 36)
        self.max_items.configure(height=34 if compact else 36)
        self.btn_logs.configure(width=82 if compact else 90, height=26 if compact else 28)
        self.open_downloads_btn.configure(width=108 if compact else 120, height=26 if compact else 28)
        if hasattr(self, "settings_density_menu"):
            self.settings_density_menu.configure(height=32 if compact else 34)
            self.settings_mode_menu.configure(height=32 if compact else 34)
            self.settings_default_dir_entry.configure(height=34 if compact else 36)
            self.settings_history_limit_menu.configure(height=30 if compact else 32)
            self.settings_show_logs_switch.configure(font=self.fonts["body_sm"])
            self.settings_auto_analyze.configure(font=self.fonts["body_sm"])
        for button in self.history_folder_buttons:
            button.configure(width=88 if compact else 96, height=26 if compact else 28)

        self._apply_preview_layout(compact)
        self._apply_options_layout(compact)
        if hasattr(self, "history_list"):
            self._refresh_history()
        if hasattr(self, "queue_preview"):
            self._refresh_queue_preview()

    def _sync_density_from_size(self, force=False):
        pref = self.pref_density_var.get().strip().lower()
        if pref in ("regular", "compact"):
            next_density = pref
        else:
            compact = self.winfo_width() < 1020 or self.winfo_height() < 710
            next_density = "compact" if compact else "regular"
        if force or next_density != self._density:
            self._apply_density(next_density)

    def _on_resize(self, event):
        if event.widget is not self:
            return
        self._sync_density_from_size()
        compact = self._density == "compact"
        width = max(300, self.winfo_width() - (320 if compact else 450))
        hint_width = max(220, self.winfo_width() - (230 if compact else 360))
        self.preview_title.configure(wraplength=width)
        self.preview_meta.configure(wraplength=width)
        self.preview_status.configure(wraplength=width)
        self.url_hint.configure(wraplength=hint_width)
        self._save_later()

    def _bind_persistence(self):
        if self._persistence_bound:
            return
        self._persistence_bound = True
        self.active_page.trace_add("write", lambda *_: self._save_later())
        self.active_mode.trace_add("write", lambda *_: self._save_later())
        for mode, st in self.states.items():
            for key in ("url", "dir", "quality", "subtitles", "thumbnail", "playlist_format", "playlist_max"):
                st[key].trace_add("write", lambda *_: self._save_later())
            st["url"].trace_add("write", lambda *_ , m=mode: self._on_url_input_changed(m))

    def _save_later(self):
        if self._booting:
            return
        if self._save_job is not None:
            self.after_cancel(self._save_job)
        self._save_job = self.after(250, self._persist)

    def _persist(self):
        self._save_job = None
        tabs = {}
        for mode, st in self.states.items():
            tabs[mode] = {
                "url": st["url"].get(),
                "dir": st["dir"].get(),
                "quality": st["quality"].get(),
                "subtitles": bool(st["subtitles"].get()),
                "thumbnail": bool(st["thumbnail"].get()),
                "playlist_format": st["playlist_format"].get(),
                "playlist_max": st["playlist_max"].get(),
            }
        geometry = f"{self.min_window_width}x{self.min_window_height}"
        settings_payload = {
            "window_geometry": geometry,
            "active_page": self.active_page.get(),
            "active_mode": self.active_mode.get(),
            "tabs": tabs,
            "preferences": self._collect_preferences(),
        }
        self.storage.save_settings(settings_payload)

    def _apply_saved(self):
        self.geometry(f"{self.min_window_width}x{self.min_window_height}")
        for mode in self.modes:
            saved = self.settings.get("tabs", {}).get(mode, {})
            if isinstance(saved, dict):
                st = self.states[mode]
                st["url"].set(saved.get("url", st["url"].get()))
                st["dir"].set(saved.get("dir", st["dir"].get()))
                st["quality"].set(saved.get("quality", st["quality"].get()))
                st["subtitles"].set(bool(saved.get("subtitles", st["subtitles"].get())))
                st["thumbnail"].set(bool(saved.get("thumbnail", st["thumbnail"].get())))
                st["playlist_format"].set(saved.get("playlist_format", st["playlist_format"].get()))
                st["playlist_max"].set(saved.get("playlist_max", st["playlist_max"].get()))

        mode = self.settings.get("active_mode") or self.settings.get("active_tab")
        if mode in self.modes:
            self.active_mode.set(mode)
        page = self.settings.get("active_page", "Downloader")
        self._show_page(page if page in self.nav_pages else "Downloader")

    def _on_close(self):
        if self._auto_analyze_job is not None:
            self.after_cancel(self._auto_analyze_job)
            self._auto_analyze_job = None
        self._persist()
        self.destroy()

    def _browse(self):
        st = self._state()
        d = filedialog.askdirectory(initialdir=st["dir"].get())
        if d:
            st["dir"].set(d)

    def _on_url_input_changed(self, mode):
        if self._booting or not self.pref_auto_analyze_var.get():
            return
        if mode != self.active_mode.get() or self.active_page.get() != "Downloader":
            return
        st = self.states[mode]
        url = st["url"].get().strip()
        if not url or not url.startswith(("http://", "https://")):
            return
        if st["probe_busy"] or st.get("last_auto_url") == url:
            return
        if self._auto_analyze_job is not None:
            self.after_cancel(self._auto_analyze_job)
        self._auto_analyze_job = self.after(700, lambda m=mode, u=url: self._run_auto_analyze(m, u))

    def _run_auto_analyze(self, mode, expected_url):
        self._auto_analyze_job = None
        if not self.pref_auto_analyze_var.get():
            return
        if mode != self.active_mode.get() or self.active_page.get() != "Downloader":
            return
        st = self.states[mode]
        current_url = st["url"].get().strip()
        if current_url != expected_url:
            return
        if st["probe_busy"] or not current_url.startswith(("http://", "https://")):
            return
        st["last_auto_url"] = current_url
        self._analyze()

    def _analyze(self):
        mode = self.active_mode.get()
        st = self._state()
        url = st["url"].get().strip()
        if not url:
            messagebox.showerror("Input Required", f"Enter a valid URL for {mode} mode.")
            return
        if st["probe_busy"]:
            return

        st["probe_ticket"] += 1
        ticket = st["probe_ticket"]
        st["probe_busy"] = True
        self.fetch_btn.configure(state="disabled", text="Analyzing...")
        self.preview_status.configure(text="Analyzing media metadata...")
        threading.Thread(target=self._probe_worker, args=(mode, url, ticket), daemon=True).start()

    def _probe_worker(self, mode, url, ticket):
        try:
            pd = self.probe.probe(url)
            img = None
            if pd.get("thumbnail"):
                req = urllib.request.Request(pd["thumbnail"], headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    img = self._build_thumbnail_image(r.read())
            self.after(0, lambda: self._apply_probe(mode, ticket, pd, img))
        except MediaProbeError as e:
            self.after(0, lambda: self._apply_probe_error(mode, ticket, str(e)))
        except Exception as e:
            self.after(0, lambda: self._apply_probe_error(mode, ticket, f"Unexpected probe failure: {e}"))

    def _apply_probe(self, mode, ticket, pd, img):
        st = self.states[mode]
        if ticket != st["probe_ticket"]:
            return
        st["probe_busy"] = False
        st["probe_data"] = pd
        st["preview_image"] = img
        st["last_auto_url"] = st["url"].get().strip()
        if mode == self.active_mode.get():
            self.fetch_btn.configure(state="normal", text="Analyze")
            self._refresh_preview()
        self._save_later()

    def _apply_probe_error(self, mode, ticket, msg):
        st = self.states[mode]
        if ticket != st["probe_ticket"]:
            return
        st["probe_busy"] = False
        st["probe_data"] = None
        st["preview_image"] = None
        st["last_auto_url"] = ""
        if mode == self.active_mode.get():
            self.fetch_btn.configure(state="normal", text="Analyze")
            self.preview_title.configure(text="Could not analyze this URL.")
            self.preview_meta.configure(text=msg)
            self.preview_status.configure(text="Verify URL format, binary paths, and source restrictions.")
            self.preview_thumb.configure(text="Preview unavailable", image=self.preview_placeholder)

    def toggle_logs(self):
        next_value = not self.logs_visible
        self.pref_show_logs_var.set(next_value)
        self._apply_logs_visibility(next_value)
        self._save_later()

    def _on_log(self, text):
        def ui():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
            if "Destination:" in text and self.current_job is not None:
                self.current_job["last_destination"] = text.split("Destination:", 1)[-1].strip()
                self._refresh_current()
        self.after(0, ui)

    def _on_progress(self, percent, line, playlist_idx=1, status_text=None):
        def ui():
            if status_text:
                self.prog_title.configure(text=status_text)
                self.footer_left.configure(text=status_text.replace("...", ""))
                if "Merging" in status_text or "Extracting" in status_text or "Converting" in status_text:
                    self.prog_bar.set(1.0)
                    self.prog_pct.configure(text="Processing...")
            else:
                self.prog_bar.set(percent / 100.0)
                self.prog_pct.configure(text=f"{percent:.1f}%")
                self.current_progress.set(percent / 100.0)
                self.prog_title.configure(text="Downloading...")
                self.footer_left.configure(text="Downloading...")

            sm = re.search(r'at\s+([\d\.]+(?:KiB|MiB|GiB)/s)', line)
            if sm:
                self.prog_speed.configure(text=sm.group(1))
                self.footer_right.configure(text=sm.group(1))
            em = re.search(r'ETA\s+([\d:]+)', line)
            if em:
                self.prog_eta.configure(text=f"ETA {em.group(1)}")
        self.after(0, ui)

    def _on_complete(self, code):
        def ui():
            self.download_btn.configure(state="normal", text="Download", fg_color=self.palette["accent"], hover_color=self.palette["accent_hover"])
            if code == 0:
                self.prog_bar.set(1.0)
                self.prog_pct.configure(text="100%")
                self.prog_title.configure(text="Download complete.")
                self.footer_left.configure(text="Completed")
            elif code == -2:
                self.prog_bar.set(0)
                self.prog_pct.configure(text="0.0%")
                self.prog_speed.configure(text="0.0 MiB/s")
                self.prog_eta.configure(text="ETA --:--")
                self.prog_title.configure(text="Download cancelled.")
                self.footer_left.configure(text="Cancelled")
            else:
                self.prog_title.configure(text="Download failed. Review Activity Log.")
                self.footer_left.configure(text="Failed")
            self._record_history(code)
            self.current_job = None
            self._refresh_current()
        self.after(0, ui)

    def _refresh_current(self):
        if not self.current_job:
            self.current_title.configure(text="No active download.")
            self.current_meta.configure(text="")
            self.current_progress.set(0)
            self.current_badge.configure(text="IDLE", fg_color=self.palette["panel_soft"])
            self._refresh_queue_preview()
            return
        pd = self.current_job.get("probe_data") or {}
        title = pd.get("title") or self.current_job.get("url")
        self.current_title.configure(text=f"{self.current_job.get('category')}: {title}")
        self.current_meta.configure(text=f"Output: {self.current_job.get('last_destination') or self.current_job.get('output_dir')}")
        self.current_badge.configure(text="ACTIVE", fg_color=self.palette["accent"])
        self._refresh_queue_preview()

    def _refresh_queue_preview(self):
        if not hasattr(self, "queue_preview"):
            return
        for row in self.queue_preview_rows:
            row.destroy()
        self.queue_preview_rows = []
        compact = self._density == "compact"
        row_pad_x = 6 if compact else 8
        row_pad_y = (6, 4) if compact else (8, 6)
        row_text_pad_x = 8 if compact else 10
        row_text_pad_top = 6 if compact else 8

        row_idx = 0
        if self.current_job:
            active = ctk.CTkFrame(self.queue_preview, fg_color=self.palette["panel_alt"], corner_radius=6)
            active.grid(row=row_idx, column=0, padx=row_pad_x, pady=row_pad_y, sticky="ew")
            active.grid_columnconfigure(0, weight=1)
            pd = self.current_job.get("probe_data") or {}
            title = pd.get("title") or self.current_job.get("url") or "Current download"
            ctk.CTkLabel(active, text=title, anchor="w", text_color="#FFFFFF", font=self.fonts["body_sm"]).grid(row=0, column=0, padx=row_text_pad_x, pady=(row_text_pad_top, 2), sticky="ew")
            ctk.CTkLabel(active, text="Downloading now", anchor="w", text_color="#FFFFFF", font=self.fonts["meta"]).grid(row=0, column=1, padx=(0, row_text_pad_x), pady=(row_text_pad_top, 2), sticky="e")
            ctk.CTkLabel(active, text=self.current_job.get("output_dir", ""), anchor="w", text_color="#9E9E9E", font=self.fonts["meta"]).grid(row=1, column=0, columnspan=2, padx=row_text_pad_x, pady=(0, row_text_pad_top), sticky="ew")
            self.queue_preview_rows.append(active)
            row_idx += 1

        for entry in self.history_entries[:4]:
            row = ctk.CTkFrame(self.queue_preview, fg_color=self.palette["panel_alt"], corner_radius=6)
            row.grid(row=row_idx, column=0, padx=row_pad_x, pady=(0, row_pad_y[1]), sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            status = entry.get("status", "unknown").upper()
            status_color = "#2EB67D" if status == "COMPLETED" else "#D5A847" if status == "CANCELLED" else "#D45E5E"
            title = entry.get("title") or entry.get("url") or "Unknown item"
            ctk.CTkLabel(row, text=title, anchor="w", text_color="#FFFFFF", font=self.fonts["body_sm"]).grid(row=0, column=0, padx=row_text_pad_x, pady=(row_text_pad_top, 2), sticky="ew")
            ctk.CTkLabel(row, text=status, text_color=status_color, font=self.fonts["meta"]).grid(row=0, column=1, padx=(0, row_text_pad_x), pady=(row_text_pad_top, 2), sticky="e")
            ctk.CTkLabel(row, text=f"{entry.get('category', 'Unknown')} | {entry.get('timestamp', 'Unknown')}", anchor="w", text_color="#9E9E9E", font=self.fonts["meta"]).grid(row=1, column=0, columnspan=2, padx=row_text_pad_x, pady=(0, row_text_pad_top), sticky="ew")
            self.queue_preview_rows.append(row)
            row_idx += 1

        if row_idx == 0:
            empty = ctk.CTkLabel(self.queue_preview, text="No recent activity.", text_color="#9E9E9E", anchor="w", font=self.fonts["body_sm"])
            empty.grid(row=0, column=0, padx=row_text_pad_x, pady=row_text_pad_x, sticky="ew")
            self.queue_preview_rows.append(empty)
        else:
            completed = len([h for h in self.history_entries if h.get("status") == "completed"])
            self.footer_left.configure(text=f"Ready | Completed jobs: {completed}")

    def _refresh_history(self):
        for row in self.history_rows:
            row.destroy()
        self.history_rows = []
        self.history_folder_buttons = []
        compact = self._density == "compact"
        row_pad_x = 6 if compact else 8
        row_pad_y = 4 if compact else 6
        folder_btn_w = 88 if compact else 96
        folder_btn_h = 26 if compact else 28
        if not self.history_entries:
            r = ctk.CTkLabel(self.history_list, text="No download history yet.", text_color="#9E9E9E", anchor="w", font=self.fonts["body_sm"])
            r.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
            self.history_rows.append(r)
            self.stats_completed.configure(text="Completed: 0")
            self.stats_cancelled.configure(text="Cancelled: 0")
            self.stats_failed.configure(text="Failed: 0")
            return
        completed = len([h for h in self.history_entries if h.get("status") == "completed"])
        cancelled = len([h for h in self.history_entries if h.get("status") == "cancelled"])
        failed = len([h for h in self.history_entries if h.get("status") == "failed"])
        self.stats_completed.configure(text=f"Completed: {completed}")
        self.stats_cancelled.configure(text=f"Cancelled: {cancelled}")
        self.stats_failed.configure(text=f"Failed: {failed}")
        try:
            limit = int(self.pref_history_limit_var.get())
        except Exception:
            limit = 30
        for i, e in enumerate(self.history_entries[:limit]):
            row = ctk.CTkFrame(self.history_list, fg_color=self.palette["panel_alt"], corner_radius=6)
            row.grid(row=i, column=0, padx=row_pad_x, pady=row_pad_y, sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            status = e.get("status", "unknown").upper()
            title = e.get("title") or e.get("url") or "Unknown item"
            status_color = "#2EB67D" if status == "COMPLETED" else "#D5A847" if status == "CANCELLED" else "#D45E5E"
            ctk.CTkLabel(row, text=title, anchor="w", text_color="#FFFFFF", font=self.fonts["body"]).grid(row=0, column=0, padx=10, pady=(8, 2), sticky="ew")
            ctk.CTkLabel(row, text=f"{e.get('timestamp', 'Unknown')} | {e.get('category', 'Unknown')}", anchor="w", text_color="#9E9E9E", font=self.fonts["meta"]).grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
            ctk.CTkLabel(row, text=status, text_color=status_color, font=self.fonts["meta"]).grid(row=0, column=1, padx=(0, 8), pady=(8, 2), sticky="e")
            folder = e.get("output_dir") or e.get("destination")
            folder_btn = ctk.CTkButton(
                row,
                text="Show Folder",
                width=folder_btn_w,
                height=folder_btn_h,
                fg_color=self.palette["panel_soft"],
                hover_color=self.palette["panel_alt"], border_width=1, border_color=self.palette["line"],
                font=self.fonts["meta"],
                command=lambda p=folder: self._open_folder(p),
            )
            folder_btn.grid(row=1, column=1, padx=(0, 8), pady=(0, 8), sticky="e")
            self.history_folder_buttons.append(folder_btn)
            self.history_rows.append(row)

    def _open_folder(self, path):
        try:
            if not path:
                return
            target = path
            if os.path.isfile(target):
                target = os.path.dirname(target)
            if os.path.isdir(target):
                os.startfile(target)
        except Exception:
            pass

    def _record_history(self, code):
        if not self.current_job:
            return
        status = "completed" if code == 0 else "cancelled" if code == -2 else "failed"
        pd = self.current_job.get("probe_data") or {}
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "status": status,
            "category": self.current_job.get("category"),
            "title": pd.get("title") or self.current_job.get("url"),
            "url": self.current_job.get("url"),
            "output_dir": self.current_job.get("output_dir"),
            "destination": self.current_job.get("last_destination") or self.current_job.get("output_dir"),
            "quality": self.current_job.get("options", {}).get("quality"),
        }
        try:
            limit = int(self.pref_history_limit_var.get())
        except Exception:
            limit = 30
        self.history_entries = self.storage.add_history_entry(entry, limit=max(10, min(200, limit)))
        self._refresh_history()
        self._save_later()

    def trigger_action(self):
        if self.dl.is_running:
            self.dl.cancel()
            self.download_btn.configure(state="disabled", text="Cancelling...")
            self.footer_left.configure(text="Cancelling...")
            return

        mode = self.active_mode.get()
        st = self._state()
        url = st["url"].get().strip()
        if not url:
            messagebox.showerror("Input Required", f"Enter a valid URL for {mode} mode.")
            return
        out = st["dir"].get()
        if not os.path.isdir(out):
            messagebox.showerror("Invalid Output Folder", f"Select a valid output folder for {mode} mode.")
            return

        self.log_box.configure(state="normal")
        self.log_box.delete("0.0", "end")
        self.log_box.configure(state="disabled")
        self.prog_bar.set(0)
        self.prog_pct.configure(text="0.0%")
        self.prog_speed.configure(text="0.0 MiB/s")
        self.prog_eta.configure(text="ETA --:--")
        self.prog_title.configure(text="Initializing download...")
        self.footer_left.configure(text="Downloading...")
        self.download_btn.configure(text="Cancel Download", fg_color=self.palette["danger"], hover_color="#D45858")

        opts = {
            "quality": st["quality"].get(),
            "subtitles": st["subtitles"].get(),
            "thumbnail": st["thumbnail"].get(),
            "max_items": st["playlist_max"].get(),
            "format": st["playlist_format"].get(),
        }
        self.current_job = {
            "category": mode,
            "url": url,
            "output_dir": out,
            "options": dict(opts),
            "probe_data": st.get("probe_data"),
            "last_destination": None,
        }
        self._refresh_current()
        self._save_later()
        self.dl.start(url, mode, opts, out)


if __name__ == "__main__":
    app = App()
    app.mainloop()
