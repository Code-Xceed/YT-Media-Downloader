import os
import subprocess
import sys


def resolve_base_path():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def resolve_app_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return resolve_base_path()


def resolve_tool_paths():
    base_path = resolve_base_path()
    ytdlp_path = os.path.join(base_path, "bin", "yt-dlp.exe")
    ffmpeg_path = os.path.join(base_path, "bin", "ffmpeg", "bin")
    return ytdlp_path, ffmpeg_path


def resolve_data_dir():
    return os.path.join(resolve_app_root(), "data")


def build_startupinfo():
    if os.name != "nt":
        return None

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startupinfo
