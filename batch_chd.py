#!/usr/bin/env python3
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import filedialog

def convert_to_chd(file_path):
    directory, filename = os.path.split(file_path)
    base_name, ext = os.path.splitext(filename)
    chd_path = os.path.join(directory, f"{base_name}.chd")

    if os.path.exists(chd_path):
        print(f"[SKIP] CHD exists: {chd_path}")
        return

    ext_lower = ext.lower()
    cmd_type = "createdvd" if ext_lower == ".iso" else "createcd"
    
    cmd = ["chdman", cmd_type, "-i", file_path, "-o", chd_path, "--force"]
    
    print(f"[START] Converting: {filename}")
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[DONE] Converted: {base_name}.chd")
    except subprocess.CalledProcessError:
        print(f"[ERROR] Failed to convert: {filename}")

def main():
    # Hide root tkinter window and open directory selector
    root = tk.Tk()
    root.withdraw()
    target_dir = filedialog.askdirectory(title="Select ROM Folder for CHD Conversion")
    
    if not target_dir:
        print("No directory selected. Exiting.")
        return

    valid_extensions = {".cue", ".iso", ".gdi"}
    files_to_convert = []

    for root_dir, _, files in os.walk(target_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in valid_extensions and "(Track " not in file:
                files_to_convert.append(os.path.join(root_dir, file))

    print(f"Found {len(files_to_convert)} candidate files.")
    
    # Run conversions in parallel matching system CPU thread count
    max_workers = os.cpu_count() or 4
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(convert_to_chd, files_to_convert)

    print("\nAll tasks finished!")

if __name__ == "__main__":
    main()
