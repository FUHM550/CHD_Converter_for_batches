#!/usr/bin/env python3
import os
import sys
import re
import time
import shutil
import subprocess
import threading
import queue
import tempfile
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
        self.frame.destroy()

class CHDConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced CHD Batch Converter")
        self.root.geometry("780x750")
        self.root.minsize(700, 600)

        self.files_to_process = []
        self.is_running = False
        self.queue = queue.Queue()
        self.active_rows = {}

        self.start_time = 0
        self.prev_cpu_total = 0
        self.prev_cpu_idle = 0
        self.sound_alarm_path = ""

        self._build_ui()
        self.root.after(100, self._process_queue)
        self.root.after(1000, self._update_system_stats)

    def _build_ui(self):
        # 1. Inputs & Outputs
        frame_top = ttk.LabelFrame(self.root, text=" Paths & Options ", padding=10)
        frame_top.pack(fill="x", padx=10, pady=5)

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

        ttk.Label(frame_top, text="Completion Sound:").grid(row=2, column=0, padx=5, pady=2, sticky="w")
        self.lbl_alarm = ttk.Label(frame_top, text="System Default Bell", font=("sans-serif", 9, "italic"))
        self.lbl_alarm.grid(row=2, column=1, columnspan=2, padx=5, pady=2, sticky="w")

        btn_alarm = ttk.Button(frame_top, text="Pick Sound...", command=self._select_alarm)
        btn_alarm.grid(row=2, column=3, padx=5, pady=2)

        frame_top.columnconfigure(2, weight=1)

        # 2. Performance & System Status
        frame_sys = ttk.LabelFrame(self.root, text=" Threads & Performance ", padding=10)
        frame_sys.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_sys, text="Parallel Jobs:").pack(side="left", padx=5)
        cpu_count = os.cpu_count() or 4
        default_workers = min(2, max(1, cpu_count // 2))

        self.spin_threads = ttk.Spinbox(frame_sys, from_=1, to=cpu_count, width=5)
        self.spin_threads.set(default_workers)
        self.spin_threads.pack(side="left", padx=5)

        self.lbl_timer = ttk.Label(frame_sys, text="Elapsed: 00:00:00")
        self.lbl_timer.pack(side="right", padx=15)

        self.lbl_cpu = ttk.Label(frame_sys, text="CPU: 0.0%")
        self.lbl_cpu.pack(side="right", padx=15)

        # 3. Overall Batch Status Line
        frame_batch_status = ttk.Frame(self.root, padding=5)
        frame_batch_status.pack(fill="x", padx=10)

        self.lbl_status_summary = ttk.Label(
            frame_batch_status,
            text="Jobs Done: 0 / 0 | Last Completed: None",
            font=("sans-serif", 10, "bold")
        )
        self.lbl_status_summary.pack(side="left")

        # Start Button
        self.btn_start = ttk.Button(frame_batch_status, text="Start Batch Conversion", command=self._start_conversion)
        self.btn_start.pack(side="right", padx=5)

        # 4. Active Parallel Progress Rows Frame
        self.frame_active = ttk.LabelFrame(self.root, text=" Active Conversions ", padding=5)
        self.frame_active.pack(fill="x", padx=10, pady=5)

        # 5. Console Log Window
        frame_log = ttk.LabelFrame(self.root, text=" Conversion History Log ", padding=10)
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)

        self.txt_log = tk.Text(frame_log, wrap="word", height=10, state="disabled")
        self.txt_log.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame_log, command=self.txt_log.yview)
        scrollbar.pack(side="right", fill="y")
        self.txt_log['yscrollcommand'] = scrollbar.set

    def _select_files(self):
        files = filedialog.askopenfilenames(
            title="Select Disc Images",
            filetypes=[("Disc Images", "*.cue *.iso *.gdi"), ("All Files", "*.*")]
        )
        if files:
            valid = [f for f in files if "(Track " not in f]
            self.files_to_process = valid
            self.lbl_selected_count.config(text=f"{len(valid)} file(s) selected.")
            self._log(f"Selected {len(valid)} file(s).")

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Select Input Folder")
        if folder:
            valid = []
            for root_dir, _, files in os.walk(folder):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in {".cue", ".iso", ".gdi"} and "(Track " not in f:
                        valid.append(os.path.join(root_dir, f))
            self.files_to_process = valid
            self.lbl_selected_count.config(text=f"{len(valid)} file(s) found.")
            self._log(f"Found {len(valid)} file(s) in: {folder}")

    def _select_out_dir(self):
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
            self.lbl_alarm.config(text=os.path.basename(sound))

    def _log(self, text):
        self.queue.put(("LOG", text))

    def _update_system_stats(self):
        # Update Timer
        if self.is_running and self.start_time > 0:
            elapsed = int(time.time() - self.start_time)
            hrs, rem = divmod(elapsed, 3600)
            mins, secs = divmod(rem, 60)
            self.lbl_timer.config(text=f"Elapsed: {hrs:02d}:{mins:02d}:{secs:02d}")

        # Update CPU Usage via /proc/stat
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
                    subprocess.Popen([player, self.sound_alarm_path], stderr=subprocess.DEVNULL)
                    return
        # Fallback system bell
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
            max_workers = 2

        self.btn_start.config(state="disabled")
        self.is_running = True
        self.start_time = time.time()

        self.lbl_status_summary.config(text=f"Jobs Done: 0 / {len(self.files_to_process)} | Last Completed: None")
        self._log(f"\n--- Starting Batch Conversion ({max_workers} max threads) ---")

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

        def worker(job_id, file_path):
            nonlocal completed_count
            filename = os.path.basename(file_path)
            base_name, ext = os.path.splitext(filename)

            target_dir = custom_out_dir if custom_out_dir else os.path.dirname(file_path)
            chd_path = os.path.join(target_dir, f"{base_name}.chd")

            self.queue.put(("ROW_START", (job_id, filename)))

            if os.path.exists(chd_path):
                self._log(f"[SKIP] CHD already exists: {base_name}.chd")
            else:
                self._log(f"[START] Converting: {filename}")
                cmd_type = "createdvd" if ext.lower() == ".iso" else "createcd"
                cmd = ["chdman", cmd_type, "-i", file_path, "-o", chd_path, "--force"]

                # Run chdman and capture progress
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
                )

                for line in iter(process.stdout.readline, ''):
                    # Extract percentage from chdman output lines like "Compressing, 45.2% complete..."
                    match = re.search(r'(\d+\.\d+)%', line)
                    if match:
                        pct = float(match.group(1))
                        self.queue.put(("ROW_PROGRESS", (job_id, filename, pct)))

                process.wait()

                if process.returncode == 0:
                    # 1. Calculate compression ratio & saved size
                    orig_bytes = self._get_input_total_size(file_path)
                    chd_bytes = os.path.getsize(chd_path) if os.path.exists(chd_path) else 0

                    if orig_bytes > 0 and chd_bytes > 0:
                        ratio = (chd_bytes / orig_bytes) * 100
                        saved = orig_bytes - chd_bytes
                        self._log(
                            f"[SUCCESS] {base_name}.chd\n"
                            f"  └─ Compression ratio {ratio:.1f}% | Saved {format_size(saved)}"
                        )
                    else:
                        self._log(f"[SUCCESS] Converted: {base_name}.chd")

                    # 2. Verify Output File Integrity
                    self._log(f"  └─ Verifying integrity of {base_name}.chd...")
                    v_cmd = ["chdman", "verify", "-i", chd_path]
                    v_res = subprocess.run(v_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if v_res.returncode == 0 and "raw sha1" in v_res.stdout.lower():
                        self._log(f"  └─ Integrity Check: PASSED ✓")
                    else:
                        self._log(f"  └─ Integrity Check: FAILED ✗")
                else:
                    self._log(f"[ERROR] Conversion failed for: {filename}")

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

                elif msg_type == "FINISHED":
                    self.btn_start.config(state="normal")
                    self.is_running = False
                    self._log("\n--- Batch Conversion Complete! ---")
                    self._play_alarm()
                    messagebox.showinfo("Done", "All conversions and integrity checks completed!")

        except queue.Empty:
            pass

        self.root.after(100, self._process_queue)

if __name__ == "__main__":
    root = tk.Tk()
    app = CHDConverterApp(root)
    root.mainloop()
