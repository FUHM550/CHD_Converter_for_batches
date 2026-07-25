#!/usr/bin/env python3
import os
import sys
import re
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

class ApeToFlacApp:
    def __init__(self, root):
        self.root = root
        self.root.title("APE to FLAC Preprocessor (Native File Manager)")
        self.root.geometry("680x450")

        self.selected_folder = ""
        self._build_ui()

    def _build_ui(self):
        frame = ttk.LabelFrame(self.root, text=" Directory Selection ", padding=15)
        frame.pack(fill="x", padx=10, pady=10)

        btn_browse = ttk.Button(frame, text="Select ROM Folder...", command=self._select_folder)
        btn_browse.pack(side="left", padx=5)

        self.lbl_folder = ttk.Label(frame, text="No folder selected.", font=("sans-serif", 9, "italic"))
        self.lbl_folder.pack(side="left", padx=10)

        frame_action = ttk.Frame(self.root, padding=10)
        frame_action.pack(fill="x", padx=10)

        self.btn_start = ttk.Button(frame_action, text="Convert All APE to FLAC", command=self._start_processing)
        self.btn_start.pack(side="right")

        frame_log = ttk.LabelFrame(self.root, text=" Log Output ", padding=10)
        frame_log.pack(fill="both", expand=True, padx=10, pady=10)

        self.txt_log = tk.Text(frame_log, wrap="word", height=10, state="disabled")
        self.txt_log.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame_log, command=self.txt_log.yview)
        scrollbar.pack(side="right", fill="y")
        self.txt_log['yscrollcommand'] = scrollbar.set

    def _log(self, text):
        self.txt_log.config(state="normal")
        self.txt_log.insert(tk.END, text + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")

    def _select_folder(self):
        folder = ""

        # Try KDE Plasma native dialog
        if shutil.which("kdialog"):
            try:
                res = subprocess.run(
                    ["kdialog", "--getexistingdirectory", "."],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
                )
                if res.returncode == 0:
                    folder = res.stdout.strip()
            except Exception:
                pass

        # Try GNOME native dialog
        if not folder and shutil.which("zenity"):
            try:
                res = subprocess.run(
                    ["zenity", "--file-selection", "--directory"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
                )
                if res.returncode == 0:
                    folder = res.stdout.strip()
            except Exception:
                pass

        # Fallback to Tkinter dialog
        if not folder:
            folder = filedialog.askdirectory(title="Select Folder Containing .cue / .ape Files")

        if folder:
            self.selected_folder = folder
            self.lbl_folder.config(text=folder)
            self._log(f"Selected: {folder}")

    def _start_processing(self):
        if not self.selected_folder or not os.path.exists(self.selected_folder):
            messagebox.showwarning("No Folder", "Please select a valid folder first.")
            return

        if not shutil.which("ffmpeg"):
            messagebox.showerror("Error", "ffmpeg was not found on your system.\nPlease install ffmpeg (e.g., sudo apt install ffmpeg).")
            return

        self.btn_start.config(state="disabled")
        self._log("\n--- Starting APE -> FLAC Conversion ---")

        threading.Thread(target=self._process_folder, daemon=True).start()

    def _process_folder(self):
        converted_count = 0
        for root_dir, _, files in os.walk(self.selected_folder):
            for file in files:
                if file.endswith(".cue"):
                    cue_path = os.path.join(root_dir, file)
                    with open(cue_path, "r", errors="ignore") as f:
                        content = f.read()

                    if ".ape" in content.lower():
                        self._log(f"Found APE references in CUE: {file}")
                        ape_matches = re.findall(r'FILE\s+"([^"]+\.ape)"', content, re.IGNORECASE)

                        new_content = content
                        for ape_file in ape_matches:
                            src_ape = os.path.join(root_dir, ape_file)
                            base_name = os.path.splitext(ape_file)[0]
                            flac_file = f"{base_name}.flac"
                            dst_flac = os.path.join(root_dir, flac_file)

                            if os.path.exists(src_ape):
                                self._log(f"  └─ Transcoding: {ape_file} -> {flac_file}")
                                # -threads 1 prevents CPU/RAM saturation during transcoding
                                cmd = ["ffmpeg", "-threads", "1", "-i", src_ape, "-c:a", "flac", dst_flac, "-y"]
                                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                                if res.returncode == 0:
                                    new_content = re.sub(re.escape(ape_file), flac_file, new_content, flags=re.IGNORECASE)
                                    os.remove(src_ape)  # Clean up original APE
                                    converted_count += 1
                                else:
                                    self._log(f"  └─ [ERROR] Failed to convert: {ape_file}")

                        with open(cue_path, "w") as f:
                            f.write(new_content)
                        self._log(f"Updated CUE sheet: {file}\n")

        self._log(f"--- Complete! Processed {converted_count} APE file(s). ---")
        self.btn_start.config(state="normal")
        messagebox.showinfo("Done", "APE tracks successfully converted to FLAC and CUE sheets updated!")

if __name__ == "__main__":
    root = tk.Tk()
    app = ApeToFlacApp(root)
    root.mainloop()
