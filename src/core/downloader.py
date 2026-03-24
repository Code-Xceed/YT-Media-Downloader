import subprocess
import threading
import re
import os

from core.runtime import build_startupinfo, resolve_tool_paths

class Downloader:
    def __init__(self, on_progress=None, on_log=None, on_complete=None):
        self.on_progress = on_progress
        self.on_log = on_log
        self.on_complete = on_complete
        self.thread = None
        self.is_running = False
        self.is_cancelled = False
        self._process = None
        self.ytdlp_path, self.ffmpeg_path = resolve_tool_paths()

    def _log(self, msg):
        if self.on_log:
            self.on_log(msg)
            
    def cancel(self):
        if self.is_running and self._process:
            self.is_cancelled = True
            self._log("User triggered cancellation. Terminating process tree...")
            try:
                if os.name == 'nt':
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(self._process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    self._process.kill()
            except Exception as e:
                self._log(f"Error terminating process: {e}")

    def start(self, url, category, options, output_dir):
        if self.is_running:
            return

        if not os.path.exists(self.ytdlp_path):
            self._log(f"ERROR: Cannot find yt-dlp.exe at {self.ytdlp_path}")
            if self.on_complete: self.on_complete(-1)
            return

        self.is_running = True
        self.is_cancelled = False
        
        cmd = [self.ytdlp_path, "--ffmpeg-location", self.ffmpeg_path]

        # Use clean filenames and prevent modified time bugs
        cmd.extend(["-o", os.path.join(output_dir, "%(title)s.%(ext)s")])
        cmd.extend(["--no-mtime"])
        
        # Maximize download speeds (split chunks concurrently!)
        cmd.extend(["--concurrent-fragments", "4"])

        is_audio = (category == "Audio") or (category == "Playlist" and options.get("format") == "Audio")
        
        # Build options
        if category == "Playlist":
            cmd.extend(["--yes-playlist"])
            max_items = options.get("max_items", "All")
            if max_items != "All" and str(max_items).isdigit():
                cmd.extend(["--playlist-end", str(max_items)])

        if is_audio:
            cmd.extend(["-x", "--audio-format", "mp3"])
            quality = options.get("quality", "Best")
            if quality == "Best":
                cmd.extend(["--audio-quality", "0"])
            else:
                kbps = "".join(filter(str.isdigit, quality))
                cmd.extend(["--audio-quality", f"{kbps}K"])
                
        elif category in ["Video", "Playlist"]:
            quality = options.get("quality", "Best")
            if quality == "Best":
                cmd.extend(["-f", "bestvideo+bestaudio/best"])
            else:
                resolution = "".join(filter(str.isdigit, quality.split(" ")[-1]))
                cmd.extend(["-f", f"bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]"])
                
        elif category == "Post":
            cmd.extend(["-f", "best"])
            
        elif category == "Thumbnail":
            cmd.extend(["--skip-download", "--write-thumbnail"])

        # Universal options
        if options.get("subtitles"):
            cmd.extend(["--write-subs", "--write-auto-subs", "--sub-langs", "en,all"])
        if options.get("thumbnail") and not category == "Thumbnail":
            cmd.extend(["--embed-thumbnail"])

        cmd.append(url)

        self._log(f"Starting highly optimized {category} download...")
        self.thread = threading.Thread(target=self._run_subprocess, args=(cmd, output_dir), daemon=True)
        self.thread.start()

    def _run_subprocess(self, cmd, output_dir):
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                startupinfo=build_startupinfo()
            )
            
            progress_regex = re.compile(r'\[download\]\s+([\d\.]+)%')
            current_item = 1
            
            for line in self._process.stdout:
                line = line.strip()
                if not line:
                    continue
                
                self._log(line)
                
                if line.startswith("[download] Downloading video"):
                    match = re.search(r'Downloading video (\d+) of (\d+)', line)
                    if match:
                        current_item = int(match.group(1))

                match = progress_regex.search(line)
                if match:
                    percent = float(match.group(1))
                    if self.on_progress:
                        self.on_progress(percent, line, playlist_idx=current_item)
                else:
                    status_text = None
                    if "[Merger] Merging formats into" in line:
                        status_text = "Merging Audio and Video..."
                    elif "[ExtractAudio]" in line:
                        status_text = "Extracting Audio..."
                    elif "[FixupM4a]" in line:
                        status_text = "Optimizing M4A metadata..."
                    elif "[download] Destination:" in line:
                        status_text = "Initiating Download..."
                    elif "[ffmpeg]" in line and "Converting" in line:
                        status_text = "Converting file format..."
                    
                    if status_text and self.on_progress:
                        self.on_progress(100.0, line, playlist_idx=current_item, status_text=status_text)

            self._process.wait()
            
        except Exception as e:
            self._log(f"Backend Error: {str(e)}")
            
        finally:
            self.is_running = False
            if self.is_cancelled:
                self._log("Process killed cleanly. Removing trailing fragments...")
                # Cleanup .part AND .ytdl files
                for root, _, files in os.walk(output_dir):
                    for file in files:
                        if file.endswith(".part") or file.endswith(".ytdl"):
                            try:
                                dfile = os.path.join(root, file)
                                os.remove(dfile)
                                self._log(f"-> Deleted trailing component: {file}")
                            except Exception:
                                pass
                if self.on_complete:
                    self.on_complete(-2) # Custom code for explicitly cancelled
            else:
                rc = getattr(self._process, 'returncode', -1)
                if self.on_complete:
                    self.on_complete(rc)
