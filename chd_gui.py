#!/usr/bin/env python3
import os
import sys
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

class CHDConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Batch CHD Converter")
        self.root.geometry("680x560")
        self.root.minsize(600, 500)

        self.files_to_process = []
        self.is_running = False
        self.queue = queue.Queue()

        self._build_ui()
        self.root.after(100, self._process_queue)

    def _build_ui(self):
        # Top Frame: Mode & Selection
        frame_input = ttk.LabelFrame(self.root, text=" 1. Input Selection ", padding=10)
        frame_input.pack(fill="x", padx=10, pady=5)

        btn_files = ttk.Button(frame_input, text="Select Files...", command=self._select_files)
        btn_files.pack(side="left", padx=5)

        btn_folder = ttk.Button(frame_input, text="Select Folder...", command=self._select_folder)
        btn_folder.pack(side="left", padx=5)

        self.lbl_selected_count = ttk.Label(frame_input, text="No files selected.")
        self.lbl_selected_count.pack(side="left", padx=10)

        # Output Directory Frame
        frame_output = ttk.LabelFrame(self.root, text=" 2. Output Location ", padding=10)
        frame_output.pack(fill="x", padx=10, pady=5)

        self.entry_out_dir = ttk.Entry(frame_output)
        self.entry_out_dir.pack(side="left", fill="x", expand=True, padx=5)

        btn_out_dir = ttk.Button(frame_output, text="Browse Output...", command=self._select_out_dir)
        btn_out_dir.pack(side="right", padx=5)

        # Performance / Threads Frame
        frame_settings = ttk.LabelFrame(self.root, text=" 3. Safety & Threads ", padding=10)
        frame_settings.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_settings, text="Max Parallel Jobs:").pack(side="left", padx=5)
        
        # Default to 2 workers to prevent thermal throttling / high wattage crashes
        cpu_count = os.cpu_count() or 4
        default_workers = min(2, max(1, cpu_count // 2))
        
        self.spin_threads = ttk.Spinbox(frame_settings, from_=1, to=cpu_count, width=5)
        self.spin_threads.set(default_workers)
        self.spin_threads.pack(side="left", padx=5)

        ttk.Label(
            frame_settings, 
            text=f"(System CPUs: {cpu_count}. Note: chdman compresses on multiple threads per job.)",
            font=("sans-serif", 9, "italic")
        ).pack(side="left", padx=5)

        # Action / Progress Frame
        frame_action = ttk.Frame(self.root, padding=10)
        frame_action.pack(fill="x", padx=10)

        self.btn_start = ttk.Button(frame_action, text="Start Conversion", command=self._start_conversion)
        self.btn_start.pack(side="left", padx=5)

        self.progress = ttk.Progressbar(frame_action, orient="horizontal", mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=10)

        # Log Window
        frame_log = ttk.LabelFrame(self.root, text=" Console Log ", padding=10)
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)

        self.txt_log = tk.Text(frame_log, wrap="word", height=10, state="disabled")
        self.txt_log.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame_log, command=self.txt_log.yview)
        scrollbar.pack(side="right", fill="y")
        self.txt_log['yscrollcommand'] = scrollbar.set

    def _log(self, text):
        self.queue.put(("LOG", text))

    def _select_files(self):
        files = filedialog.askopenfilenames(
            title="Select Disc Images",
            filetypes=[("Disc Images", "*.cue *.iso *.gdi"), ("All Files", "*.*")]
        )
        if files:
            # Filter out subtrack cue files
            valid = [f for f in files if "(Track " not in f]
            self.files_to_process = valid
            self.lbl_selected_count.config(text=f"{len(valid)} file(s) selected.")
            self._log(f"Selected {len(valid)} individual file(s).")

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Select Input Folder")
        if folder:
            valid = []
            for root, _, files in os.walk(folder):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in {".cue", ".iso", ".gdi"} and "(Track " not in f:
                        valid.append(os.path.join(root, f))
            self.files_to_process = valid
            self.lbl_selected_count.config(text=f"{len(valid)} file(s) found in directory.")
            self._log(f"Found {len(valid)} file(s) in: {folder}")

    def _select_out_dir(self):
        folder = filedialog.askdirectory(title="Select Output Directory")
        if folder:
            self.entry_out_dir.delete(0, tk.END)
            self.entry_out_dir.insert(0, folder)

    def _start_conversion(self):
        if not self.files_to_process:
            messagebox.showwarning("No Files", "Please select files or a folder to convert first.")
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
        self.progress["value"] = 0
        self.progress["maximum"] = len(self.files_to_process)

        self._log(f"\n--- Starting Conversion Batch (Max parallel jobs: {max_workers}) ---")

        # Run worker orchestration on a separate background thread
        threading.Thread(target=self._run_batch, args=(self.files_to_process, out_dir, max_workers), daemon=True).start()

    def _run_batch(self, files, custom_out_dir, max_workers):
        semaphore = threading.Semaphore(max_workers)
        threads = []
        completed_count = 0
        count_lock = threading.Lock()

        def worker(file_path):
            nonlocal completed_count
            filename = os.path.basename(file_path)
            base_name, ext = os.path.splitext(filename)

            # Determine output directory
            if custom_out_dir:
                target_dir = custom_out_dir
            else:
                target_dir = os.path.dirname(file_path)

            chd_path = os.path.join(target_dir, f"{base_name}.chd")

            if os.path.exists(chd_path):
                self._log(f"[SKIP] Exists: {base_name}.chd")
            else:
                self._log(f"[CONVERTING] {filename}")
                cmd_type = "createdvd" if ext.lower() == ".iso" else "createcd"
                cmd = ["chdman", cmd_type, "-i", file_path, "-o", chd_path, "--force"]

                try:
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if res.returncode == 0:
                        self._log(f"[SUCCESS] Converted: {base_name}.chd")
                    else:
                        self._log(f"[ERROR] Failed {filename}: {res.stderr.strip()}")
                except Exception as e:
                    self._log(f"[ERROR] {filename}: {str(e)}")

            semaphore.release()
            with count_lock:
                completed_count += 1
                self.queue.put(("PROGRESS", completed_count))

        for file_path in files:
            semaphore.acquire()
            t = threading.Thread(target=worker, args=(file_path,), daemon=True)
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
                elif msg_type == "PROGRESS":
                    self.progress["value"] = payload
                elif msg_type == "FINISHED":
                    self.btn_start.config(state="normal")
                    self.is_running = False
                    self._log("\n--- Batch Conversion Finished! ---")
                    messagebox.showinfo("Done", "All conversion tasks have completed.")
        except queue.Empty:
            pass

        self.root.after(100, self._process_queue)


if __name__ == "__main__":
    root = tk.Tk()
    app = CHDConverterApp(root)
    root.mainloop()
