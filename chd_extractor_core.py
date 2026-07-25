#!/usr/bin/env python3
import os
import sys
import re
import time
import shutil
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

def format_size(bytes_val):
    try:
        bytes_val = float(bytes_val)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if abs(bytes_val) < 1024.0:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} PB"
    except Exception:
        return "Unknown Size"

def get_cpu_usage_proc():
    """Reads /proc/stat to calculate CPU percentage."""
    try:
        with open('/proc/stat', 'r') as f:
            line = f.readline()
        fields = [float(x) for x in line.split()[1:]]
        idle = fields[3] + fields[4]
        total = sum(fields)
        return total, idle
    except Exception:
        return 0, 0

class ActiveJobRow:
    """Manages an active progress UI row for an ongoing extraction."""
    def __init__(self, parent, job_id):
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x", padx=5, pady=2)
        
        self.lbl_title = ttk.Label(self.frame, text=f"Job #{job_id}: Waiting...", width=38, anchor="w")
        self.lbl_title.pack(side="left", padx=5)
        
        self.progress = ttk.Progressbar(self.frame, orient="horizontal", mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=5)
        
        self.lbl_status = ttk.Label(self.frame, text="Extracting...", width=12)
        self.lbl_status.pack(side="right", padx=5)

    def update(self, filename):
        display_name = (filename[:33] + '..') if len(filename) > 35 else filename
        self.lbl_title.config(text=display_name)

    def destroy(self):
        try:
            self.frame.destroy()
        except Exception:
            pass

class SelectiveExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Selective Archive ROM Extractor")
        self.root.geometry("800x680")
        self.root.minsize(700, 550)

        self.files_to_process = []
        self.is_running = False
        self.queue = queue.Queue()
        self.active_rows = {}
        
        self.start_time = 0
        self.prev_cpu_total = 0
        self.prev_cpu_idle = 0

        self.tool_7z = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")

        self._build_ui()
        self.root.after(100, self._process_queue)
        self.root.after(1000, self._update_system_stats)

    def _build_ui(self):
        # 1. Inputs & Outputs
        frame_top = ttk.LabelFrame(self.root, text=" Paths & Targets ", padding=10)
        frame_top.pack(fill="x", padx=10, pady=5)

        btn_files = ttk.Button(frame_top, text="Select Archives...", command=self._select_files)
        btn_files.grid(row=0, column=0, padx=5, pady=2, sticky="w")

        btn_folder = ttk.Button(frame_top, text="Select Folder...", command=self._select_folder)
        btn_folder.grid(row=0, column=1, padx=5, pady=2, sticky="w")

        self.lbl_selected_count = ttk.Label(frame_top, text="No archives selected.")
        self.lbl_selected_count.grid(row=0, column=2, padx=10, pady=2, sticky="w")

        ttk.Label(frame_top, text="Extract Dir:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.entry_out_dir = ttk.Entry(frame_top)
        self.entry_out_dir.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

        btn_out_dir = ttk.Button(frame_top, text="Browse...", command=self._select_out_dir)
        btn_out_dir.grid(row=1, column=3, padx=5, pady=5)

        frame_top.columnconfigure(2, weight=1)

        # 2. Settings & Monitoring
        frame_sys = ttk.LabelFrame(self.root, text=" Performance & Filter Settings ", padding=10)
        frame_sys.pack(fill="x", padx=10, pady=5)

        frame_threads = ttk.Frame(frame_sys)
        frame_threads.pack(fill="x", pady=2)

        ttk.Label(frame_threads, text="Parallel Jobs:").pack(side="left", padx=5)
        cpu_count = os.cpu_count() or 4
        
        self.spin_threads = ttk.Spinbox(frame_threads, from_=1, to=cpu_count, width=5)
        self.spin_threads.set(1)
        self.spin_threads.pack(side="left", padx=5)

        ttk.Label(
            frame_threads, 
            text="Filter Exts: .iso, .bin, .cue, .gdi, .ccd, .ape, .flac, .wav, .chd",
            font=("sans-serif", 9, "italic")
        ).pack(side="left", padx=15)

        self.lbl_timer = ttk.Label(frame_threads, text="Elapsed: 00:00:00")
        self.lbl_timer.pack(side="right", padx=10)

        self.lbl_cpu = ttk.Label(frame_threads, text="CPU: 0.0%")
        self.lbl_cpu.pack(side="right", padx=10)

        # 3. Overall Status Line
        frame_batch_status = ttk.Frame(self.root, padding=5)
        frame_batch_status.pack(fill="x", padx=10)

        self.lbl_status_summary = ttk.Label(
            frame_batch_status, 
            text="Jobs Done: 0 / 0 | Last Completed: None", 
            font=("sans-serif", 10, "bold")
        )
        self.lbl_status_summary.pack(side="left")

        self.btn_start = ttk.Button(frame_batch_status, text="Start Extraction", command=self._start_extraction)
        self.btn_start.pack(side="right", padx=5)

        # 4. Active Progress Rows
        self.frame_active = ttk.LabelFrame(self.root, text=" Active Extractions ", padding=5)
        self.frame_active.pack(fill="x", padx=10, pady=5)

        # 5. Console Log Window
        frame_log = ttk.LabelFrame(self.root, text=" Extraction Log ", padding=10)
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)

        self.txt_log = tk.Text(frame_log, wrap="word", height=10, state="disabled")
        self.txt_log.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame_log, command=self.txt_log.yview)
        scrollbar.pack(side="right", fill="y")
        self.txt_log['yscrollcommand'] = scrollbar.set

    def _select_files(self):
        files = []
        if shutil.which("kdialog"):
            try:
                res = subprocess.run(
                    ["kdialog", "--getopenfilename", "--multiple", ".", "Archives (*.7z *.zip *.rar *.tar *.gz)"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
                )
                if res.returncode == 0:
                    files = [f.strip() for f in res.stdout.split("\n") if f.strip()]
            except Exception:
                pass

        if not files and shutil.which("zenity"):
            try:
                res = subprocess.run(
                    ["zenity", "--file-selection", "--multiple", "--file-filter=Archives | *.7z *.zip *.rar *.tar *.gz"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
                )
                if res.returncode == 0:
                    files = [f.strip() for f in res.stdout.split("|") if f.strip()]
            except Exception:
                pass

        if not files:
            files = filedialog.askopenfilenames(
                title="Select Archives",
                filetypes=[("Archives", "*.7z *.zip *.rar *.tar *.gz"), ("All Files", "*.*")]
            )

        if files:
            self.files_to_process = files
            self.lbl_selected_count.config(text=f"{len(files)} archive(s) selected.")
            self._log(f"Selected {len(files)} archive(s).")

    def _select_folder(self):
        folder = ""
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

        if not folder:
            folder = filedialog.askdirectory(title="Select Archive Folder")

        if folder:
            valid = []
            valid_exts = {".7z", ".zip", ".rar", ".tar", ".gz"}
            for root_dir, _, files in os.walk(folder):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in valid_exts:
                        valid.append(os.path.join(root_dir, f))
            self.files_to_process = valid
            self.lbl_selected_count.config(text=f"{len(valid)} archive(s) found.")
            self._log(f"Found {len(valid)} archive(s) in: {folder}")

    def _select_out_dir(self):
        folder = ""
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

        if not folder:
            folder = filedialog.askdirectory(title="Select Extraction Output Directory")

        if folder:
            self.entry_out_dir.delete(0, tk.END)
            self.entry_out_dir.insert(0, folder)

    def _log(self, text):
        self.queue.put(("LOG", text))

    def _update_system_stats(self):
        if self.is_running and self.start_time > 0:
            elapsed = int(time.time() - self.start_time)
            hrs, rem = divmod(elapsed, 3600)
            mins, secs = divmod(rem, 60)
            self.lbl_timer.config(text=f"Elapsed: {hrs:02d}:{mins:02d}:{secs:02d}")

        tot, idle = get_cpu_usage_proc()
        if self.prev_cpu_total > 0:
            diff_tot = tot - self.prev_cpu_total
            diff_idle = idle - self.prev_cpu_idle
            if diff_tot > 0:
                usage = ((diff_tot - diff_idle) / diff_tot) * 100.0
                self.lbl_cpu.config(text=f"CPU: {usage:.1f}%")
        self.prev_cpu_total = tot
        self.prev_cpu_idle = idle

        self.root.after(1000, self._update_system_stats)

    def _start_extraction(self):
        if not self.files_to_process:
            messagebox.showwarning("No Files", "Please select archive files or a directory first.")
            return

        if not self.tool_7z:
            messagebox.showerror("Missing Dependency", "7z / p7zip was not found on your system.\nPlease install '7-zip' or 'p7zip'.")
            return

        out_dir = self.entry_out_dir.get().strip()
        if not out_dir:
            messagebox.showwarning("No Output Path", "Please select an extraction output directory.")
            return

        os.makedirs(out_dir, exist_ok=True)

        try:
            max_workers = int(self.spin_threads.get())
        except ValueError:
            max_workers = 1

        self.btn_start.config(state="disabled")
        self.is_running = True
        self.start_time = time.time()

        self.lbl_status_summary.config(text=f"Jobs Done: 0 / {len(self.files_to_process)} | Last Completed: None")
        self._log(f"\n--- Starting Selective Extraction ({max_workers} worker(s)) ---")

        threading.Thread(
            target=self._run_batch, 
            args=(self.files_to_process, out_dir, max_workers), 
            daemon=True
        ).start()

    def _run_batch(self, archives, target_out_dir, max_workers):
        semaphore = threading.Semaphore(max_workers)
        threads = []
        completed_count = 0
        total_files = len(archives)
        count_lock = threading.Lock()

        # Specific file extensions to extract
        target_extensions = [
            "*.iso", "*.bin", "*.cue", "*.gdi", "*.ccd", 
            "*.ape", "*.flac", "*.wav", "*.chd"
        ]

        def worker(job_id, archive_path):
            nonlocal completed_count
            filename = os.path.basename(archive_path)

            try:
                self.queue.put(("ROW_START", (job_id, filename)))
                self._log(f"[STARTING] Extracting from: {filename}")

                # Build 7z command extracting ONLY specified extensions directly to target
                cmd = [self.tool_7z, "e", archive_path, f"-o{target_out_dir}", "-y", "-r", "-bd"]
                
                # Append extension filters to command
                for ext in target_extensions:
                    cmd.append(ext)

                res = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                if res.returncode == 0:
                    self._log(f"[SUCCESS] Extracted disc images/audio from: {filename}")
                else:
                    self._log(f"[NOTICE] No matching ROMs/Audio found in: {filename}")

            except Exception as e:
                self._log(f"[ERROR] Exception processing {filename}: {e}")

            finally:
                self.queue.put(("ROW_END", job_id))
                semaphore.release()

                with count_lock:
                    completed_count += 1
                    self.queue.put(("STATUS_UPDATE", (completed_count, total_files, filename)))

        for idx, arch in enumerate(archives, start=1):
            semaphore.acquire()
            t = threading.Thread(target=worker, args=(idx, arch), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.queue.put(("FINISHED", None))

    def _process_queue(self):
        try:
            for _ in range(20):
                msg_type, payload = self.queue.get_nowait()
                if msg_type == "LOG":
                    self.txt_log.config(state="normal")
                    self.txt_log.insert(tk.END, payload + "\n")
                    self.txt_log.see(tk.END)
                    self.txt_log.config(state="disabled")

                elif msg_type == "ROW_START":
                    job_id, fname = payload
                    row = ActiveJobRow(self.frame_active, job_id)
                    row.update(fname)
                    row.progress.start(10)
                    self.active_rows[job_id] = row

                elif msg_type == "ROW_END":
                    job_id = payload
                    if job_id in self.active_rows:
                        self.active_rows[job_id].progress.stop()
                        self.active_rows[job_id].destroy()
                        del self.active_rows[job_id]

                elif msg_type == "STATUS_UPDATE":
                    done, total, last_file = payload
                    self.lbl_status_summary.config(
                        text=f"Jobs Done: {done} / {total} | Last Completed: {last_file}"
                    )

                elif msg_type == "FINISHED":
                    self.btn_start.config(state="normal")
                    self.is_running = False
                    self._log("\n--- Archive Extraction Complete! ---")
                    self.root.bell()
                    messagebox.showinfo("Done", "Selected ROMs and audio tracks have been extracted successfully!")

        except queue.Empty:
            pass

        self.root.after(50, self._process_queue)

if __name__ == "__main__":
    root = tk.Tk()
    app = SelectiveExtractorApp(root)
    root.mainloop()
