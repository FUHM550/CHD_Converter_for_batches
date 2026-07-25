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
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(bytes_val) < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PB"

def get_cpu_usage_proc():
    """Reads /proc/stat to calculate CPU percentage without requiring psutil."""
    try:
        with open('/proc/stat', 'r') as f:
            line = f.readline()
        fields = [float(x) for x in line.split()[1:]]
        idle = fields[3] + fields[4] # idle + iowait
        total = sum(fields)
        return total, idle
    except Exception:
        return 0, 0

class ActiveJobRow:
    """Manages an active progress bar UI row for a running conversion."""
    def __init__(self, parent, job_id):
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x", padx=5, pady=2)

        self.lbl_title = ttk.Label(self.frame, text=f"Job #{job_id}: Waiting...", width=40, anchor="w")
        self.lbl_title.pack(side="left", padx=5)

        self.progress = ttk.Progressbar(self.frame, orient="horizontal", mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=5)

        self.lbl_pct = ttk.Label(self.frame, text="0%", width=6)
        self.lbl_pct.pack(side="right", padx=5)

    def update(self, filename, percent):
        display_name = (filename[:35] + '..') if len(filename) > 37 else filename
        self.lbl_title.config(text=display_name)
        self.progress["value"] = percent
        self.lbl_pct.config(text=f"{int(percent)}%")

    def destroy(self):
        try:
            self.frame.destroy()
        except Exception:
            pass

class CHDConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced CHD Batch Converter")
        self.root.geometry("820x780")
        self.root.minsize(740, 640)

        self.files_to_process = []
        self.is_running = False
        self.queue = queue.Queue()
        self.active_rows = {}

        self.start_time = 0
        self.prev_cpu_total = 0
        self.prev_cpu_idle = 0

        # Options State
        self.sound_alarm_path = ""
        self.var_enable_sound = tk.BooleanVar(value=True)
        self.var_enable_popup = tk.BooleanVar(value=True)

        self._build_ui()
        self.root.after(100, self._process_queue)
        self.root.after(1000, self._update_system_stats)

    def _build_ui(self):
        # Create Tabbed Layout
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self.tab_main = ttk.Frame(self.notebook, padding=5)
        self.tab_options = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_main, text=" Conversion Manager ")
        self.notebook.add(self.tab_options, text=" Options & Notifications ")

        # ================= TAB 1: MAIN CONVERSION MANAGER =================
        # 1. Inputs & Outputs
        frame_top = ttk.LabelFrame(self.tab_main, text=" Paths & Options ", padding=10)
        frame_top.pack(fill="x", padx=5, pady=5)

        btn_files = ttk.Button(frame_top, text="Select Files...", command=self._select_files)
        btn_files.grid(row=0, column=0, padx=5, pady=2, sticky="w")

        btn_folder = ttk.Button(frame_top, text="Select Folder...", command=self._select_folder)
        btn_folder.grid(row=0, column=1, padx=5, pady=2, sticky="w")

        self.lbl_selected_count = ttk.Label(frame_top, text="No files selected.")
        self.lbl_selected_count.grid(row=0, column=2, padx=10, pady=2, sticky="w")

        ttk.Label(frame_top, text="Output Dir:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.entry_out_dir = ttk.Entry(frame_top)
        self.entry_out_dir.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

        btn_out_dir = ttk.Button(frame_top, text="Browse...", command=self._select_out_dir)
        btn_out_dir.grid(row=1, column=3, padx=5, pady=5)

        frame_top.columnconfigure(2, weight=1)

        # 2. Performance & System Status
        frame_sys = ttk.LabelFrame(self.tab_main, text=" Threads & Performance ", padding=10)
        frame_sys.pack(fill="x", padx=5, pady=5)

        # Row A: Parallel Jobs
        frame_jobs_row = ttk.Frame(frame_sys)
        frame_jobs_row.pack(fill="x", anchor="w", pady=2)

        ttk.Label(frame_jobs_row, text="Parallel Jobs:").pack(side="left", padx=5)
        cpu_count = os.cpu_count() or 4
        self.spin_threads = ttk.Spinbox(frame_jobs_row, from_=1, to=cpu_count, width=5)
        self.spin_threads.set(1)
        self.spin_threads.pack(side="left", padx=5)

        ttk.Label(
            frame_jobs_row,
            text="(Recommended: 1 for maximum ISO stability)",
            font=("sans-serif", 9, "italic")
        ).pack(side="left", padx=10)

        # Row B: Timer & CPU Monitor (Placed DIRECTLY under Parallel Jobs)
        frame_stats_row = ttk.Frame(frame_sys)
        frame_stats_row.pack(fill="x", anchor="w", pady=5)

        self.lbl_timer = ttk.Label(frame_stats_row, text="Elapsed: 00:00:00", font=("sans-serif", 9, "bold"))
        self.lbl_timer.pack(side="left", padx=5)

        ttk.Label(frame_stats_row, text="|").pack(side="left", padx=10)

        self.lbl_cpu = ttk.Label(frame_stats_row, text="CPU: 0.0%", font=("sans-serif", 9, "bold"))
        self.lbl_cpu.pack(side="left", padx=5)

        # 3. Overall Batch Status Line & Global Progress Bar
        frame_batch_status = ttk.LabelFrame(self.tab_main, text=" Overall Batch Progress ", padding=10)
        frame_batch_status.pack(fill="x", padx=5, pady=5)

        frame_status_info = ttk.Frame(frame_batch_status)
        frame_status_info.pack(fill="x", pady=2)

        self.lbl_status_summary = ttk.Label(
            frame_status_info,
            text="Jobs Done: 0 / 0 | Last Completed: None",
            font=("sans-serif", 10, "bold")
        )
        self.lbl_status_summary.pack(side="left")

        self.btn_start = ttk.Button(frame_status_info, text="Start Batch Conversion", command=self._start_conversion)
        self.btn_start.pack(side="right", padx=5)

        self.global_progress = ttk.Progressbar(frame_batch_status, orient="horizontal", mode="determinate")
        self.global_progress.pack(fill="x", expand=True, pady=5)

        # 4. Active Parallel Progress Rows Frame
        self.frame_active = ttk.LabelFrame(self.tab_main, text=" Active Conversions ", padding=5)
        self.frame_active.pack(fill="x", padx=5, pady=5)

        # 5. Console Log Window
        frame_log = ttk.LabelFrame(self.tab_main, text=" Conversion History Log ", padding=10)
        frame_log.pack(fill="both", expand=True, padx=5, pady=5)

        self.txt_log = tk.Text(frame_log, wrap="word", height=8, state="disabled")
        self.txt_log.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame_log, command=self.txt_log.yview)
        scrollbar.pack(side="right", fill="y")
        self.txt_log['yscrollcommand'] = scrollbar.set

        # ================= TAB 2: OPTIONS & NOTIFICATIONS =================
        frame_opts = ttk.LabelFrame(self.tab_options, text=" Completion Behavior ", padding=15)
        frame_opts.pack(fill="x", padx=10, pady=10)

        chk_popup = ttk.Checkbutton(
            frame_opts,
            text="Show pop-up notification box when batch completes",
            variable=self.var_enable_popup
        )
        chk_popup.pack(anchor="w", pady=5)

        chk_sound = ttk.Checkbutton(
            frame_opts,
            text="Play audio sound alarm when batch completes",
            variable=self.var_enable_sound
        )
        chk_sound.pack(anchor="w", pady=5)

        frame_alarm_pick = ttk.LabelFrame(self.tab_options, text=" Custom Alarm Sound ", padding=15)
        frame_alarm_pick.pack(fill="x", padx=10, pady=10)

        ttk.Label(frame_alarm_pick, text="Current Audio File:").pack(anchor="w")
        self.lbl_alarm_path = ttk.Label(
            frame_alarm_pick,
            text="System Default Bell",
            font=("sans-serif", 9, "italic")
        )
        self.lbl_alarm_path.pack(anchor="w", pady=2)

        frame_alarm_btns = ttk.Frame(frame_alarm_pick)
        frame_alarm_btns.pack(fill="x", pady=5)

        btn_alarm_select = ttk.Button(frame_alarm_btns, text="Pick Sound File...", command=self._select_alarm)
        btn_alarm_select.pack(side="left", padx=5)

        btn_alarm_test = ttk.Button(frame_alarm_btns, text="Test Alarm", command=self._play_alarm)
        btn_alarm_test.pack(side="left", padx=5)

    def _select_files(self):
        files = []
        if shutil.which("kdialog"):
            try:
                res = subprocess.run(
                    ["kdialog", "--getopenfilename", "--multiple", ".", "Disc Images (*.cue *.iso *.gdi *.ccd)"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
                )
                if res.returncode == 0:
                    files = [f.strip() for f in res.stdout.split("\n") if f.strip()]
            except Exception:
                pass

        if not files and shutil.which("zenity"):
            try:
                res = subprocess.run(
                    ["zenity", "--file-selection", "--multiple", "--file-filter=Disc Images | *.cue *.iso *.gdi *.ccd"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
                )
                if res.returncode == 0:
                    files = [f.strip() for f in res.stdout.split("|") if f.strip()]
            except Exception:
                pass

        if not files:
            files = filedialog.askopenfilenames(
                title="Select Disc Images",
                filetypes=[("Disc Images", "*.cue *.iso *.gdi *.ccd"), ("All Files", "*.*")]
            )

        if files:
            valid = [f for f in files if "(Track " not in f]
            self.files_to_process = valid
            self.lbl_selected_count.config(text=f"{len(valid)} file(s) selected.")
            self._log(f"Selected {len(valid)} file(s).")

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
            folder = filedialog.askdirectory(title="Select Input Folder")

        if folder:
            valid = []
            for root_dir, _, files in os.walk(folder):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in {".cue", ".iso", ".gdi", ".ccd"} and "(Track " not in f:
                        valid.append(os.path.join(root_dir, f))
            self.files_to_process = valid
            self.lbl_selected_count.config(text=f"{len(valid)} file(s) found.")
            self._log(f"Found {len(valid)} file(s) in: {folder}")

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
            folder = filedialog.askdirectory(title="Select Output Directory")

        if folder:
            self.entry_out_dir.delete(0, tk.END)
            self.entry_out_dir.insert(0, folder)

    def _select_alarm(self):
        sound = filedialog.askopenfilename(
            title="Select Alarm Sound File",
            filetypes=[("Audio Files", "*.wav *.ogg *.mp3"), ("All Files", "*.*")]
        )
        if sound:
            self.sound_alarm_path = sound
            self.lbl_alarm_path.config(text=sound)

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

    def _play_alarm(self):
        if self.sound_alarm_path and os.path.exists(self.sound_alarm_path):
            for player in ["paplay", "aplay", "canberra-gtk-play", "ffplay"]:
                if shutil.which(player):
                    try:
                        subprocess.Popen([player, self.sound_alarm_path], stderr=subprocess.DEVNULL)
                        return
                    except Exception:
                        pass
        self.root.bell()

    def _start_conversion(self):
        if not self.files_to_process:
            messagebox.showwarning("No Files", "Please select input files or a directory first.")
            return

        out_dir = self.entry_out_dir.get().strip()
        if out_dir and not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Error", f"Could not create output directory:\n{e}")
                return

        try:
            max_workers = int(self.spin_threads.get())
        except ValueError:
            max_workers = 1

        self.btn_start.config(state="disabled")
        self.is_running = True
        self.start_time = time.time()

        self.global_progress["value"] = 0
        self.lbl_status_summary.config(text=f"Jobs Done: 0 / {len(self.files_to_process)} | Last Completed: None")
        self._log(f"\n--- Starting Batch Conversion ({max_workers} parallel job(s)) ---")

        threading.Thread(
            target=self._run_batch,
            args=(self.files_to_process, out_dir, max_workers),
            daemon=True
        ).start()

    def _get_input_total_size(self, file_path):
        """Calculates total size including cue target bin files."""
        total = os.path.getsize(file_path)
        base_dir = os.path.dirname(file_path)
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".cue":
            try:
                with open(file_path, "r", errors="ignore") as f:
                    for line in f:
                        match = re.search(r'FILE\s+"([^"]+)"', line, re.IGNORECASE)
                        if match:
                            bin_path = os.path.join(base_dir, match.group(1))
                            if os.path.exists(bin_path) and bin_path != file_path:
                                total += os.path.getsize(bin_path)
            except Exception:
                pass
        return total

    def _run_batch(self, files, custom_out_dir, max_workers):
        semaphore = threading.Semaphore(max_workers)
        threads = []
        completed_count = 0
        total_files = len(files)
        count_lock = threading.Lock()

        successful_conversions = []
        successful_lock = threading.Lock()

        # PHASE 1: Pure Conversion Phase
        def worker(job_id, file_path):
            nonlocal completed_count
            filename = os.path.basename(file_path)
            base_name, ext = os.path.splitext(filename)

            target_dir = custom_out_dir if custom_out_dir else os.path.dirname(file_path)
            chd_path = os.path.join(target_dir, f"{base_name}.chd")

            self.queue.put(("ROW_START", (job_id, filename)))

            if os.path.exists(chd_path):
                self._log(f"[SKIP] CHD already exists: {base_name}.chd")
                with successful_lock:
                    successful_conversions.append((file_path, chd_path, base_name))
            else:
                self._log(f"[START] Converting: {filename}")

                cmd_type = "createdvd" if ext.lower() == ".iso" else "createcd"
                cmd = ["chdman", cmd_type, "-i", file_path, "-o", chd_path, "--force"]

                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
                )

                error_lines = []
                for line in iter(process.stdout.readline, ''):
                    match = re.search(r'(\d+\.\d+)%', line)
                    if match:
                        pct = float(match.group(1))
                        self.queue.put(("ROW_PROGRESS", (job_id, filename, pct)))
                    elif "error" in line.lower() or "fatal" in line.lower() or "failed" in line.lower():
                        error_lines.append(line.strip())

                process.wait()

                if process.returncode == 0:
                    self._log(f"[CONVERTED] Finished: {base_name}.chd")
                    with successful_lock:
                        successful_conversions.append((file_path, chd_path, base_name))
                else:
                    self._log(f"[ERROR] Conversion failed for: {filename}")
                    if error_lines:
                        self._log(f"  └─ Cause: {' | '.join(error_lines[:2])}")
                    if os.path.exists(chd_path):
                        try:
                            os.remove(chd_path)
                        except Exception:
                            pass

            self.queue.put(("ROW_END", job_id))
            semaphore.release()

            with count_lock:
                completed_count += 1
                self.queue.put(("STATUS_UPDATE", (completed_count, total_files, filename)))

        for idx, file_path in enumerate(files, start=1):
            semaphore.acquire()
            t = threading.Thread(target=worker, args=(idx, file_path), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # PHASE 2: Sequential Verification Phase
        if successful_conversions:
            self._log("\n--- Starting Sequential Verification Phase ---")
            for src_file, chd_path, base_name in successful_conversions:
                if os.path.exists(chd_path):
                    orig_bytes = self._get_input_total_size(src_file)
                    chd_bytes = os.path.getsize(chd_path)

                    if orig_bytes > 0 and chd_bytes > 0:
                        ratio = (chd_bytes / orig_bytes) * 100
                        saved = orig_bytes - chd_bytes
                        self._log(
                            f"[VERIFYING] {base_name}.chd\n"
                            f"  └─ Ratio {ratio:.1f}% | Saved {format_size(saved)}"
                        )

                    v_cmd = ["chdman", "verify", "-i", chd_path]
                    v_res = subprocess.run(v_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if v_res.returncode == 0 and "raw sha1" in v_res.stdout.lower():
                        self._log(f"  └─ Integrity Check: PASSED ✓")
                    else:
                        self._log(f"  └─ Integrity Check: FAILED ✗")

        self.queue.put(("FINISHED", None))

    def _process_queue(self):
        try:
            while True:
                msg_type, payload = self.queue.get_nowait()
                if msg_type == "LOG":
                    self.txt_log.config(state="normal")
                    self.txt_log.insert(tk.END, payload + "\n")
                    self.txt_log.see(tk.END)
                    self.txt_log.config(state="disabled")

                elif msg_type == "ROW_START":
                    job_id, fname = payload
                    row = ActiveJobRow(self.frame_active, job_id)
                    row.update(fname, 0)
                    self.active_rows[job_id] = row

                elif msg_type == "ROW_PROGRESS":
                    job_id, fname, pct = payload
                    if job_id in self.active_rows:
                        self.active_rows[job_id].update(fname, pct)

                elif msg_type == "ROW_END":
                    job_id = payload
                    if job_id in self.active_rows:
                        self.active_rows[job_id].destroy()
                        del self.active_rows[job_id]

                elif msg_type == "STATUS_UPDATE":
                    done, total, last_file = payload
                    self.lbl_status_summary.config(
                        text=f"Jobs Done: {done} / {total} | Last Completed: {last_file}"
                    )
                    if total > 0:
                        pct_complete = (done / total) * 100
                        self.global_progress["value"] = pct_complete

                elif msg_type == "FINISHED":
                    self.btn_start.config(state="normal")
                    self.is_running = False
                    self._log("\n--- Batch Conversion Complete! ---")

                    if self.var_enable_sound.get():
                        self._play_alarm()

                    if self.var_enable_popup.get():
                        messagebox.showinfo("Done", "All conversions and integrity checks completed!")

        except queue.Empty:
            pass

        self.root.after(100, self._process_queue)

if __name__ == "__main__":
    root = tk.Tk()
    app = CHDConverterApp(root)
    root.mainloop()
