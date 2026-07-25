#!/usr/bin/env python3
import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

class MainLauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CHD & Media Processing Suite")
        self.root.geometry("480x320")
        self.root.resizable(False, False)

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self._build_ui()

    def _build_ui(self):
        frame_main = ttk.Frame(self.root, padding=20)
        frame_main.pack(fill="both", expand=True)

        lbl_title = ttk.Label(
            frame_main, 
            text="CHD & Media Processing Suite", 
            font=("sans-serif", 14, "bold")
        )
        lbl_title.pack(pady=(0, 5))

        lbl_sub = ttk.Label(
            frame_main, 
            text="Select a tool to launch:", 
            font=("sans-serif", 10, "italic")
        )
        lbl_sub.pack(pady=(0, 20))

        # Button 1: CHD Batch Converter
        btn_chd = ttk.Button(
            frame_main, 
            text="1. CHD Batch Converter", 
            command=self._launch_chd_converter
        )
        btn_chd.pack(fill="x", pady=6, ipady=4)

        # Button 2: APE to FLAC Preprocessor
        btn_ape = ttk.Button(
            frame_main, 
            text="2. APE to FLAC Preprocessor", 
            command=self._launch_ape_preprocessor
        )
        btn_ape.pack(fill="x", pady=6, ipady=4)

        # Button 3: CHD Extractor
        btn_extract = ttk.Button(
            frame_main, 
            text="3. CHD Extractor", 
            command=self._launch_chd_extractor
        )
        btn_extract.pack(fill="x", pady=6, ipady=4)

    def _spawn_script(self, script_name):
        script_path = os.path.join(self.base_dir, script_name)
        if not os.path.exists(script_path):
            messagebox.showerror("Error", f"Could not find script:\n{script_name}")
            return

        try:
            # Spawns child process using the Python environment
            subprocess.Popen([sys.executable, script_path])
        except Exception as e:
            messagebox.showerror("Execution Error", f"Failed to launch {script_name}:\n{e}")

    def _launch_chd_converter(self):
        # Target converter script
        target = "chd_gui_advanced.py" if os.path.exists(os.path.join(self.base_dir, "chd_gui_advanced.py")) else "chd_gui.py"
        self._spawn_script(target)

    def _launch_ape_preprocessor(self):
        self._spawn_script("ape_to_flac_preprocessor.py")

    def _launch_chd_extractor(self):
        self._spawn_script("chd_extractor_core.py")

if __name__ == "__main__":
    root = tk.Tk()
    app = MainLauncherApp(root)
    root.mainloop()
