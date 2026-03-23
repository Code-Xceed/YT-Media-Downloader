import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
from core.downloader import Downloader
import re

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YT-Downloader V7")
        
        self.geometry("600x600")
        self.minsize(500, 600)
        
        self.dl = Downloader(
            on_progress=self._on_progress,
            on_log=self._on_log,
            on_complete=self._on_complete
        )
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        self.create_main_area()
        self.logs_visible = False
        
    def create_main_area(self):
        self.tabs = ctk.CTkTabview(self, corner_radius=10)
        self.tabs.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="nsew")
        
        cats = ["Video", "Audio", "Playlist", "Post", "Thumbnail"]
        self.tab_states = {}
        
        for c in cats:
            t = self.tabs.add(c)
            t.grid_columnconfigure(0, weight=1)
            t.grid_rowconfigure(1, weight=1)  # Enable expansion
            
            # Completely silo every variable locally to this tab category!
            self.tab_states[c] = {
                "url": ctk.StringVar(),
                "dir": ctk.StringVar(value=os.path.join(os.path.expanduser('~'), 'Downloads')),
                "quality": ctk.StringVar(value="Best"),
                "subtitles": ctk.BooleanVar(value=False),
                "thumbnail": ctk.BooleanVar(value=False),
                "playlist_format": ctk.StringVar(value="Video"),
                "playlist_max": ctk.StringVar(value="All")
            }
            
            self._build_tab_layout(c, t)

        dock = ctk.CTkFrame(self, fg_color="transparent")
        dock.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="ew")
        dock.grid_columnconfigure(0, weight=1)
        
        self.download_btn = ctk.CTkButton(dock, text="START DOWNLOAD", font=ctk.CTkFont(size=14, weight="bold"), height=40, command=self.trigger_action)
        self.download_btn.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        
        hud = ctk.CTkFrame(dock, fg_color=("gray85", "gray14"))
        hud.grid(row=1, column=0, columnspan=4, sticky="ew")
        hud.grid_columnconfigure((0,1,2), weight=1)
        
        self.prog_pct = ctk.CTkLabel(hud, text="0.0%", font=ctk.CTkFont(size=16, weight="bold"), width=60)
        self.prog_pct.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        self.prog_speed = ctk.CTkLabel(hud, text="0.0 MiB/s", font=ctk.CTkFont(size=12))
        self.prog_speed.grid(row=0, column=1, padx=10, pady=5)
        
        self.prog_eta = ctk.CTkLabel(hud, text="ETA: --:--", font=ctk.CTkFont(size=12))
        self.prog_eta.grid(row=0, column=2, padx=10, pady=5, sticky="e")
        
        self.prog_bar = ctk.CTkProgressBar(hud, height=8)
        self.prog_bar.grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="ew")
        self.prog_bar.set(0)
        
        self.prog_title = ctk.CTkLabel(hud, text="Ready.", font=ctk.CTkFont(size=11, slant="italic"))
        self.prog_title.grid(row=2, column=0, columnspan=3, padx=10, pady=(0, 5), sticky="w")

        self.btn_logs = ctk.CTkButton(hud, text="Show Logs", width=80, height=20, fg_color="transparent", border_width=1, command=self.toggle_logs)
        self.btn_logs.grid(row=3, column=0, columnspan=3, padx=10, pady=5)
        
        self.log_box = ctk.CTkTextbox(hud, height=100, wrap="word", font=ctk.CTkFont(family="Consolas", size=10))
        self.log_box.configure(state="disabled")

    def _build_tab_layout(self, cat, tab):
        tgt_frame = ctk.CTkFrame(tab, fg_color=("gray90", "gray16"))
        tgt_frame.grid(row=0, column=0, sticky="ew", pady=(5, 10))
        tgt_frame.grid_columnconfigure(1, weight=1)
        
        state = self.tab_states[cat]
        
        ctk.CTkLabel(tgt_frame, text="URL:").grid(row=0, column=0, padx=10, pady=5)
        ctk.CTkEntry(tgt_frame, textvariable=state["url"], height=30).grid(row=0, column=1, columnspan=2, padx=(0, 10), pady=8, sticky="ew")
        
        ctk.CTkLabel(tgt_frame, text="Dir:").grid(row=1, column=0, padx=10, pady=(0, 10))
        ctk.CTkEntry(tgt_frame, textvariable=state["dir"], height=30, state="readonly").grid(row=1, column=1, padx=(0, 10), pady=(0, 10), sticky="ew")
        
        # Unique callback for this specific category's browse button!
        ctk.CTkButton(tgt_frame, text="Browse", width=60, height=30, command=lambda c=cat: self.browse_dir(c)).grid(row=1, column=2, padx=(0, 10), pady=(0, 10))

        opt_frame = ctk.CTkFrame(tab, fg_color=("gray90", "gray16"))
        opt_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        opt_frame.grid_columnconfigure(0, weight=1)
        
        self._fill_options(cat, opt_frame, state)

    def _fill_options(self, cat, parent, state):
        lbl_font = ctk.CTkFont(size=12)

        if cat == "Video":
            ctk.CTkLabel(parent, text="Quality:", font=lbl_font).grid(row=0, column=0, padx=10, pady=10, sticky="w")
            ctk.CTkOptionMenu(parent, variable=state["quality"], values=["Best", "4K", "1440p", "1080p", "720p", "480p", "360p"]).grid(row=0, column=1, padx=10, pady=10, sticky="ew")
            ctk.CTkCheckBox(parent, text="Download Subtitles", variable=state["subtitles"]).grid(row=1, column=0, columnspan=2, padx=10, pady=(0,10), sticky="w")
            ctk.CTkCheckBox(parent, text="Embed Thumbnail", variable=state["thumbnail"]).grid(row=2, column=0, columnspan=2, padx=10, pady=(0,10), sticky="w")
            
        elif cat == "Audio":
            ctk.CTkLabel(parent, text="Quality:", font=lbl_font).grid(row=0, column=0, padx=10, pady=10, sticky="w")
            ctk.CTkOptionMenu(parent, variable=state["quality"], values=["Best", "320kbps", "256kbps", "192kbps", "128kbps"]).grid(row=0, column=1, padx=10, pady=10, sticky="ew")
            ctk.CTkCheckBox(parent, text="Embed Thumbnail", variable=state["thumbnail"]).grid(row=1, column=0, columnspan=2, padx=10, pady=(0,10), sticky="w")
            
        elif cat == "Playlist":
            ctk.CTkLabel(parent, text="Format:", font=lbl_font).grid(row=0, column=0, padx=10, pady=10, sticky="w")
            pl_q_menu = ctk.CTkOptionMenu(parent, variable=state["quality"], values=["Best", "1080p", "720p"])
            pm = ctk.CTkOptionMenu(parent, variable=state["playlist_format"], values=["Video", "Audio"], command=lambda v: self._playlist_fmt_change(v, pl_q_menu, state))
            pm.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
            pl_q_menu.grid(row=0, column=2, padx=10, pady=10, sticky="ew")
            
            ctk.CTkLabel(parent, text="Max Items:", font=lbl_font).grid(row=1, column=0, padx=10, pady=(0,10), sticky="w")
            ctk.CTkEntry(parent, textvariable=state["playlist_max"], width=60).grid(row=1, column=1, padx=10, pady=(0,10), sticky="w")
            
        elif cat in ["Post", "Thumbnail"]:
            desc = "Extracts generic media cleanly." if cat == "Post" else "Downloads only the highest quality thumbnail image."
            ctk.CTkLabel(parent, text=desc, font=ctk.CTkFont(size=12, slant="italic"), text_color="gray60").grid(row=0, column=0, padx=15, pady=15, sticky="w")

    def _playlist_fmt_change(self, v, quality_menu_widget, state):
        if v == "Audio":
            quality_menu_widget.configure(values=["Best", "320kbps", "128kbps"])
        else:
            quality_menu_widget.configure(values=["Best", "1080p", "720p"])
        state["quality"].set("Best")

    def toggle_logs(self):
        self.logs_visible = not self.logs_visible
        if self.logs_visible:
            self.btn_logs.configure(text="Hide Logs")
            self.log_box.grid(row=4, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew")
        else:
            self.btn_logs.configure(text="Show Logs")
            self.log_box.grid_forget()

    def browse_dir(self, cat):
        state = self.tab_states[cat]
        d = filedialog.askdirectory(initialdir=state["dir"].get())
        if d: state["dir"].set(d)

    def _on_log(self, text):
        def update():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
            
            if "Destination:" in text:
                fn = text.split("Destination:", 1)[-1].strip()
                self.prog_title.configure(text=f"Saving: {os.path.basename(fn)}")
        self.after(0, update)

    def _on_progress(self, percent, line, playlist_idx=1):
        def update():
            self.prog_bar.set(percent / 100.0)
            self.prog_pct.configure(text=f"{percent:.1f}%")
            
            sm = re.search(r'at\s+([\d\.]+(?:KiB|MiB|GiB)/s)', line)
            if sm: self.prog_speed.configure(text=sm.group(1))
            
            em = re.search(r'ETA\s+([\d:]+)', line)
            if em: self.prog_eta.configure(text=f"ETA: {em.group(1)}")
            
        self.after(0, update)

    def _on_complete(self, code):
        def update():
            self.download_btn.configure(state="normal", text="START DOWNLOAD", fg_color=["#3B8ED0", "#1F6AA5"], hover_color=["#36719F", "#144870"])
            
            if code == 0:
                self.prog_bar.set(1.0)
                self.prog_pct.configure(text="100%")
                self.prog_title.configure(text="Download Complete!")
            elif code == -2:
                # Cancelled!
                self.prog_title.configure(text="Download cancelled and leftovers cleaned.")
                self.prog_bar.set(0)
                self.prog_pct.configure(text="0.0%")
                self.prog_speed.configure(text="0.0 MiB/s")
                self.prog_eta.configure(text="ETA: --:--")
            else:
                self.prog_title.configure(text="Error occurred. Check advanced logs.")
        self.after(0, update)

    def trigger_action(self):
        if self.dl.is_running:
            self.dl.cancel()
            self.download_btn.configure(state="disabled", text="CANCELLING...")
            return

        cat = self.tabs.get()
        state = self.tab_states[cat]
        
        url = state["url"].get().strip()
        if not url:
            messagebox.showerror("Error", f"URL for {cat} is empty.")
            return

        out_dir = state["dir"].get()
        if not os.path.isdir(out_dir):
            messagebox.showerror("Error", f"Invalid output directory for {cat}.")
            return

        self.log_box.configure(state="normal")
        self.log_box.delete("0.0", "end")
        self.log_box.configure(state="disabled")
        
        self.prog_bar.set(0)
        self.prog_pct.configure(text="0.0%")
        self.prog_speed.configure(text="0.0 MiB/s")
        self.prog_eta.configure(text="ETA: --:--")
        self.prog_title.configure(text="Initializing Fast Download...")
        
        self.download_btn.configure(text="CANCEL DOWNLOAD", fg_color="#C0392B", hover_color="#922B21")

        opts = {
            "quality": state["quality"].get(),
            "subtitles": state["subtitles"].get(),
            "thumbnail": state["thumbnail"].get(),
            "max_items": state["playlist_max"].get(),
            "format": state["playlist_format"].get()
        }
        
        self.dl.start(url, cat, opts, out_dir)

if __name__ == "__main__":
    app = App()
    app.mainloop()
