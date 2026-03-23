# YT-Downloader

A sleek, ultra-minimal, and lightning-fast desktop interface for downloading videos, audio, playlists, social media posts, and simple thumbnails. Built on top of Python's `customtkinter` explicitly to wrap the raw command-line power of `yt-dlp` into a professional app.

## Features
- **Compartmentalized Multi-Tab Interface:** Five completely independent tab sessions (Video, Audio, Playlist, Post, Thumbnail) that allow you to hold different URLs, output directories, and quality settings per tab without overriding each other.
- **Concurrent Fragment Downloading:** Instructs `yt-dlp` to extract media chunks across multiple simultaneous pipelines internally for massively accelerated transfer speeds.
- **Clean Drive Guarantee:** Features a raw sub-process "Cancel Download" switch. If a download is manually aborted mid-way, the application automatically sweeps your output folder to silently delete any fragmented `.part` or `.ytdl` scraping files left behind.
- **Dynamic Progress HUD:** A graphical overlay parsing out precise real-time Network Speeds (MiB/s), Percentages, and ETA cleanly, hiding the noisy developer logs by default.

## Usage
Simply double-click the `start.bat` initialization script. 
1. If this is your first time loading the application, the script will rapidly auto-verify your Python installation and silently fetch any missing GUI dependencies (`customtkinter`, `pillow`) natively. 
2. Upon successful compilation, it immediately collapses the background terminal into a detached detached process so that you are left flawlessly looking at pure Native UI.
    
**Backend Dependencies Required:** 
You must possess the executable binaries `yt-dlp.exe` and your extracted `ffmpeg` folder stored neatly inside the local `/bin/` directory.
