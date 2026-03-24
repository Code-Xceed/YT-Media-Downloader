import json
import subprocess

from core.runtime import build_startupinfo, resolve_tool_paths


class MediaProbeError(Exception):
    pass


class MediaProbe:
    def __init__(self):
        self.ytdlp_path, self.ffmpeg_path = resolve_tool_paths()

    def probe(self, url):
        cmd = [
            self.ytdlp_path,
            "--ffmpeg-location",
            self.ffmpeg_path,
            "--dump-single-json",
            "--skip-download",
            "--quiet",
            "--no-warnings",
            url,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                startupinfo=build_startupinfo(),
            )
        except FileNotFoundError as exc:
            raise MediaProbeError(f"Cannot find yt-dlp at {self.ytdlp_path}") from exc
        except Exception as exc:
            raise MediaProbeError(f"Failed to analyze URL: {exc}") from exc

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip() or "yt-dlp returned an unknown error."
            raise MediaProbeError(message)

        payload = (result.stdout or "").strip()
        if not payload:
            raise MediaProbeError("yt-dlp returned no metadata for this URL.")

        try:
            info = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise MediaProbeError("yt-dlp returned invalid metadata output.") from exc

        return self._normalize_info(info)

    def _normalize_info(self, info):
        is_playlist = info.get("_type") == "playlist" or bool(info.get("entries"))
        playlist_count = info.get("playlist_count")
        if not playlist_count and is_playlist:
            entries = info.get("entries") or []
            playlist_count = len(entries) or None

        uploader = info.get("uploader") or info.get("channel") or info.get("creator") or "Unknown uploader"
        title = info.get("title") or info.get("playlist_title") or "Untitled"
        duration = self._format_duration(info.get("duration"))
        webpage_url = info.get("webpage_url") or info.get("original_url")

        formats = info.get("formats") or []
        video_heights = sorted(
            {
                int(fmt["height"])
                for fmt in formats
                if fmt.get("height") and fmt.get("vcodec") not in (None, "none")
            },
            reverse=True,
        )
        audio_only = bool(formats) and not video_heights

        if is_playlist:
            suggested_mode = "Playlist"
        elif audio_only:
            suggested_mode = "Audio"
        else:
            suggested_mode = "Video"

        return {
            "title": title,
            "uploader": uploader,
            "duration": duration,
            "thumbnail": info.get("thumbnail"),
            "webpage_url": webpage_url,
            "suggested_mode": suggested_mode,
            "is_playlist": is_playlist,
            "playlist_count": playlist_count,
            "extractor": info.get("extractor_key") or info.get("extractor") or "Unknown source",
            "qualities": [f"{height}p" for height in video_heights[:6]],
        }

    def _format_duration(self, seconds):
        if seconds is None:
            return "Unknown duration"

        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            return "Unknown duration"

        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
