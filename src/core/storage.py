import json
import os
from datetime import datetime

from core.runtime import resolve_data_dir


DEFAULT_SETTINGS = {
    "window_geometry": "1180x780",
    "active_page": "Downloader",
    "active_mode": "Video",
    "active_tab": "Video",
    "preferences": {
        "ui_density_mode": "auto",
        "font_scale": 1.0,
        "scroll_speed": 1.0,
        "show_logs": True,
        "auto_analyze": False,
        "history_limit": 30,
        "default_output_dir": "",
        "remember_window_size": True,
    },
    "tabs": {},
}


class AppStorage:
    def __init__(self):
        self.data_dir = resolve_data_dir()
        self.settings_path = os.path.join(self.data_dir, "settings.json")
        self.history_path = os.path.join(self.data_dir, "history.json")
        os.makedirs(self.data_dir, exist_ok=True)

    def load_settings(self):
        settings = self._read_json(self.settings_path, DEFAULT_SETTINGS)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(settings if isinstance(settings, dict) else {})
        defaults_pref = DEFAULT_SETTINGS.get("preferences", {})
        prefs = merged.get("preferences")
        merged_pref = dict(defaults_pref)
        if isinstance(prefs, dict):
            merged_pref.update(prefs)
        merged["preferences"] = merged_pref
        tabs = merged.get("tabs")
        merged["tabs"] = tabs if isinstance(tabs, dict) else {}
        return merged

    def save_settings(self, settings):
        self._write_json(self.settings_path, settings)

    def load_history(self):
        history = self._read_json(self.history_path, [])
        return history if isinstance(history, list) else []

    def add_history_entry(self, entry, limit=30):
        history = self.load_history()
        stamped = dict(entry)
        stamped.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
        history.insert(0, stamped)
        self._write_json(self.history_path, history[:limit])
        return history[:limit]

    def save_history(self, entries, limit=30):
        history = entries if isinstance(entries, list) else []
        self._write_json(self.history_path, history[:limit])
        return history[:limit]

    def _read_json(self, path, fallback):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return fallback
        except Exception:
            return fallback

    def _write_json(self, path, payload):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True)
