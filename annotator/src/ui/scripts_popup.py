"""
ScriptsMixin mixin class.
"""

import os
from pathlib import Path
import customtkinter as ctk
from tkinter import messagebox, filedialog
from app_paths import CSV_PATH, SCRIPT_DIR
from analysis.aggregator import aggregate_datasets, generate_kappa_sample
from analysis.kappa import calculate_kappa
import threading

class ScriptsMixin:
    def _show_scripts_popup(self):
        """
        Opens a popup window with three columns for running utility scripts.
        All logic is inlined so it works in the bundled app without separate files.
        Column 1: Aggregate Datasets
        Column 2: Generate Kappa Sample
        Column 3: Calculate Kappa (Cohen's or Fleiss')
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Scripts")
        popup.configure(fg_color="#1a1a2e")
        popup.attributes("-topmost", True)
        popup.resizable(True, True)

        pw, ph = 1100, 720
        popup.geometry(f"{pw}x{ph}")
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (pw // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (ph // 2)
        popup.geometry(f"+{x}+{y}")

        # Three-column container
        columns_frame = ctk.CTkFrame(popup, fg_color="transparent")
        columns_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        columns_frame.columnconfigure(0, weight=2, uniform="cols")
        columns_frame.columnconfigure(1, weight=3, uniform="cols")
        columns_frame.columnconfigure(2, weight=2, uniform="cols")
        columns_frame.rowconfigure(0, weight=1)

        script_dir = str(SCRIPT_DIR)
        default_annotators_dir = str(SCRIPT_DIR / "all_annotators_dataset")
        default_output_csv = str(SCRIPT_DIR / "dataset.csv")
        default_output_images = str(SCRIPT_DIR / "images")
        default_output_videos = str(SCRIPT_DIR / "videos")
        default_kappa_input = str(CSV_PATH)
        default_kappa_bundle = str(SCRIPT_DIR / "kappa_sample")

        # Helper to create input fields with label, default, browse, clear, and undo
        def _make_field(parent, label_text, default_value, row,
                        browse_dir=False, browse_file=False, browse_warning=None):
            ctk.CTkLabel(parent, text=label_text,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#ccc", anchor="w").grid(
                             row=row, column=0, sticky="w", padx=8, pady=(6, 0))

            field_frame = ctk.CTkFrame(parent, fg_color="transparent")
            field_frame.grid(row=row + 1, column=0, sticky="ew", padx=8, pady=(2, 4))
            field_frame.columnconfigure(0, weight=1)

            entry = ctk.CTkEntry(field_frame, height=30, font=ctk.CTkFont(size=11),
                                  placeholder_text=label_text)
            entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
            entry.insert(0, default_value)

            undo_stack = [default_value]

            def _on_key(event):
                current = entry.get()
                if not undo_stack or undo_stack[-1] != current:
                    undo_stack.append(current)

            def _undo(event):
                if len(undo_stack) > 1:
                    undo_stack.pop()
                    entry.delete(0, "end")
                    entry.insert(0, undo_stack[-1])
                return "break"

            entry.bind("<KeyRelease>", _on_key)
            entry.bind("<Control-z>", _undo)
            entry.bind("<Command-z>", _undo)

            col = 1

            if browse_dir:
                def _browse():
                    popup.attributes("-topmost", False)
                    path = filedialog.askdirectory(initialdir=script_dir)
                    popup.attributes("-topmost", True)
                    if path:
                        undo_stack.append(entry.get())
                        entry.delete(0, "end")
                        entry.insert(0, path)
                ctk.CTkButton(field_frame, text="📂", width=30, height=30,
                               command=_browse, fg_color="#444",
                               hover_color="#555").grid(row=0, column=col, padx=(0, 2))
                col += 1

            if browse_file:
                def _browse_file():
                    popup.attributes("-topmost", False)
                    path = filedialog.askopenfilename(
                        initialdir=script_dir,
                        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
                    popup.attributes("-topmost", True)
                    if path:
                        undo_stack.append(entry.get())
                        entry.delete(0, "end")
                        entry.insert(0, path)
                ctk.CTkButton(field_frame, text="📂", width=30, height=30,
                               command=_browse_file, fg_color="#444",
                               hover_color="#555").grid(row=0, column=col, padx=(0, 2))
                col += 1

            def _clear():
                undo_stack.append(entry.get())
                entry.delete(0, "end")
            ctk.CTkButton(field_frame, text="✕", width=26, height=30,
                           command=_clear, fg_color="#555",
                           hover_color="#777", text_color="#e74c3c",
                           font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=col)

            return entry

        # ---- COLUMN 1: Aggregate Datasets ----
        left_card = ctk.CTkFrame(columns_frame, fg_color="#222244", corner_radius=10,
                                  border_width=1, border_color="#444")
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=4)
        left_card.columnconfigure(0, weight=1)
        left_card.rowconfigure(20, weight=1)

        ctk.CTkLabel(left_card, text="📦 Aggregate Datasets",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
                         row=0, column=0, padx=8, pady=(10, 2), sticky="w")

        ctk.CTkLabel(left_card, text=(
            "• Merges all annotator datasets into one\n"
            "• Copies images & videos to output dirs\n"
            "• Each annotator folder must contain:\n"
            "   dataset.csv, images/, videos/\n"
            "• Place all folders inside one master dir"),
            font=ctk.CTkFont(size=11), text_color="#999",
            wraplength=300, justify="left", anchor="nw").grid(
                row=1, column=0, padx=10, pady=(2, 4), sticky="w")

        agg_master_entry = _make_field(left_card, "Master Folder",
                                        default_annotators_dir, row=2, browse_dir=True)
        agg_csv_entry = _make_field(left_card, "Output CSV",
                                     default_output_csv, row=4, browse_dir=True)
        agg_images_entry = _make_field(left_card, "Output Images Dir",
                                        default_output_images, row=6, browse_dir=True)
        agg_videos_entry = _make_field(left_card, "Output Videos Dir",
                                        default_output_videos, row=8, browse_dir=True)

        # Results popup helper: progress bar → scrollable result text
        def _show_result_popup(title, task_fn):
            """
            Opens a result popup with progress bar, runs task_fn in background,
            then shows the result/error in a scrollable text area.
            """
            rp = ctk.CTkToplevel(popup)
            rp.title(title)
            rp.configure(fg_color="#1a1a2e")
            rp.attributes("-topmost", True)
            rp.resizable(True, True)
            rp.geometry("560x420")
            rp.update_idletasks()
            rx = popup.winfo_x() + (popup.winfo_width() // 2) - 280
            ry = popup.winfo_y() + (popup.winfo_height() // 2) - 210
            rp.geometry(f"+{rx}+{ry}")

            # Header
            ctk.CTkLabel(rp, text=f"⏳ {title}",
                         font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(16, 8))

            # Status label
            status_label = ctk.CTkLabel(rp, text="Running...",
                                         font=ctk.CTkFont(size=12),
                                         text_color="#f39c12")
            status_label.pack(pady=(0, 8))

            # Progress bar (indeterminate)
            progress = ctk.CTkProgressBar(rp, mode="indeterminate",
                                           width=480, height=8)
            progress.pack(padx=30, pady=(0, 12))
            progress.start()

            # Scrollable text area (hidden initially, will fill middle)
            text_frame = ctk.CTkFrame(rp, fg_color="transparent")

            result_text = ctk.CTkTextbox(text_frame, font=ctk.CTkFont(family="Courier", size=12),
                                          fg_color="#111122", text_color="#ccc",
                                          wrap="word", activate_scrollbars=True,
                                          corner_radius=8)
            result_text.pack(fill="both", expand=True, padx=16, pady=(0, 8))

            # Close button (packed at bottom first so it stays anchored)
            close_btn = ctk.CTkButton(rp, text="Close", command=rp.destroy,
                                       height=36, font=ctk.CTkFont(size=13),
                                       fg_color="transparent", border_width=1,
                                       border_color="#555", width=130, state="disabled")
            close_btn.pack(side="bottom", pady=(0, 12))

            def _run():
                try:
                    result = task_fn()
                    def _show():
                        progress.stop()
                        progress.pack_forget()
                        status_label.configure(text="✅ Completed", text_color="#2ecc71")
                        text_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))
                        result_text.insert("1.0", result)
                        result_text.configure(state="disabled", text_color="#2ecc71")
                        close_btn.configure(state="normal")
                    self.after(0, _show)
                except Exception as e:
                    err_msg = str(e)
                    def _show_err():
                        progress.stop()
                        progress.pack_forget()
                        status_label.configure(text="❌ Error", text_color="#e74c3c")
                        text_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))
                        result_text.insert("1.0", err_msg)
                        result_text.configure(state="disabled", text_color="#e74c3c")
                        close_btn.configure(state="normal")
                    self.after(0, _show_err)
            threading.Thread(target=_run, daemon=True).start()

        def _run_aggregate():
            ann_dir = agg_master_entry.get().strip()
            out_csv = agg_csv_entry.get().strip() or default_output_csv
            out_img = agg_images_entry.get().strip() or default_output_images
            out_vid = agg_videos_entry.get().strip() or default_output_videos
            if not ann_dir:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Missing Input", "Provide the master folder path.", parent=popup)
                popup.attributes("-topmost", True)
                return
            existing = []
            if os.path.exists(out_csv):
                existing.append(f"dataset.csv")
            if os.path.exists(out_img) and os.listdir(out_img):
                existing.append(f"images/ directory")
            if os.path.exists(out_vid) and os.listdir(out_vid):
                existing.append(f"videos/ directory")
            if existing:
                warn = "These outputs already exist and will be overwritten:\n\n" + \
                       "\n".join(f"  - {p}" for p in existing) + "\n\nContinue?"
                popup.attributes("-topmost", False)
                if not messagebox.askyesno("Overwrite Warning", warn, parent=popup):
                    popup.attributes("-topmost", True)
                    return
                popup.attributes("-topmost", True)
            _show_result_popup("Aggregate Datasets",
                               lambda: aggregate_datasets(ann_dir, out_csv, out_img, out_vid))

        left_btn = ctk.CTkFrame(left_card, fg_color="transparent")
        left_btn.grid(row=20, column=0, padx=10, pady=(4, 10), sticky="sew")
        ctk.CTkButton(left_btn, text="▶ Run Aggregation", command=_run_aggregate,
                       height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black").pack(fill="x")

        # ---- COLUMN 2: Generate Kappa Sample ----
        mid_card = ctk.CTkFrame(columns_frame, fg_color="#222244", corner_radius=10,
                                 border_width=1, border_color="#444")
        mid_card.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        mid_card.columnconfigure(0, weight=1)
        mid_card.rowconfigure(30, weight=1)

        ctk.CTkLabel(mid_card, text="🎲 Generate Kappa Sample",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
                         row=0, column=0, padx=8, pady=(10, 2), sticky="w")

        ctk.CTkLabel(mid_card, text=(
            "• Balanced random sample for kappa testing\n"
            "• Customize Real/Fake split below\n"
            "• Fake sub-categories divide the Fake portion\n"
            "• Creates a portable folder with the sample\n"
            "   CSV + only its referenced images/videos\n"
            "• Output loads in Re-label mode"),
            font=ctk.CTkFont(size=11), text_color="#999",
            wraplength=300, justify="left", anchor="nw").grid(
                row=1, column=0, padx=10, pady=(2, 4), sticky="w")

        kappa_input_entry = _make_field(mid_card, "Input CSV (master dataset)",
                                         default_kappa_input, row=2, browse_file=True)
        kappa_n_entry = _make_field(mid_card, "Sample Size (N)", "500", row=4)

        # --- Distribution: Real % / Fake % (must sum to 100) ---
        ctk.CTkLabel(mid_card, text="Distribution (% of total sample)",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ccc", anchor="w").grid(
                         row=6, column=0, sticky="w", padx=8, pady=(6, 0))

        dist_frame = ctk.CTkFrame(mid_card, fg_color="transparent")
        dist_frame.grid(row=7, column=0, sticky="ew", padx=8, pady=(2, 4))
        dist_frame.columnconfigure(0, weight=1)
        dist_frame.columnconfigure(2, weight=1)

        real_sub = ctk.CTkFrame(dist_frame, fg_color="transparent")
        real_sub.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkLabel(real_sub, text="Real %", font=ctk.CTkFont(size=11),
                     text_color="#2ecc71").pack(anchor="w")
        real_pct_entry = ctk.CTkEntry(real_sub, height=28, font=ctk.CTkFont(size=11),
                                       placeholder_text="50.00")
        real_pct_entry.pack(fill="x")
        real_pct_entry.insert(0, "50.00")

        ctk.CTkLabel(dist_frame, text="+", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#888").grid(row=0, column=1, padx=4)

        fake_sub = ctk.CTkFrame(dist_frame, fg_color="transparent")
        fake_sub.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        ctk.CTkLabel(fake_sub, text="Fake %", font=ctk.CTkFont(size=11),
                     text_color="#e74c3c").pack(anchor="w")
        fake_pct_entry = ctk.CTkEntry(fake_sub, height=28, font=ctk.CTkFont(size=11),
                                       placeholder_text="50.00")
        fake_pct_entry.pack(fill="x")
        fake_pct_entry.insert(0, "50.00")

        dist_sum_label = ctk.CTkLabel(dist_frame, text="= 100.00%",
                                       font=ctk.CTkFont(size=11, weight="bold"),
                                       text_color="#2ecc71")
        dist_sum_label.grid(row=0, column=3, padx=(6, 0))

        # Auto-fill: editing Real auto-calculates Fake, and vice versa
        _dist_updating = [False]

        def _on_real_pct_change(*_):
            if _dist_updating[0]:
                return
            val = real_pct_entry.get().strip()
            try:
                r = round(float(val), 2)
                if 0 <= r <= 100:
                    _dist_updating[0] = True
                    f = round(100.0 - r, 2)
                    fake_pct_entry.delete(0, "end")
                    fake_pct_entry.insert(0, f"{f:.2f}")
                    dist_sum_label.configure(text="= 100.00%", text_color="#2ecc71")
                    _dist_updating[0] = False
                else:
                    dist_sum_label.configure(text="Out of range", text_color="#e74c3c")
            except ValueError:
                dist_sum_label.configure(text="= ???", text_color="#e74c3c")

        def _on_fake_pct_change(*_):
            if _dist_updating[0]:
                return
            val = fake_pct_entry.get().strip()
            try:
                f = round(float(val), 2)
                if 0 <= f <= 100:
                    _dist_updating[0] = True
                    r = round(100.0 - f, 2)
                    real_pct_entry.delete(0, "end")
                    real_pct_entry.insert(0, f"{r:.2f}")
                    dist_sum_label.configure(text="= 100.00%", text_color="#2ecc71")
                    _dist_updating[0] = False
                else:
                    dist_sum_label.configure(text="Out of range", text_color="#e74c3c")
            except ValueError:
                dist_sum_label.configure(text="= ???", text_color="#e74c3c")

        real_pct_entry.bind("<KeyRelease>", _on_real_pct_change)
        fake_pct_entry.bind("<KeyRelease>", _on_fake_pct_change)

        # --- Fake Sub-categories: Misinfo / Satire / Clickbait (% of Fake portion, must sum to 100) ---
        ctk.CTkLabel(mid_card, text="Fake Sub-categories (% of Fake portion)",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ccc", anchor="w").grid(
                         row=8, column=0, sticky="w", padx=8, pady=(6, 0))

        subcat_frame = ctk.CTkFrame(mid_card, fg_color="transparent")
        subcat_frame.grid(row=9, column=0, sticky="ew", padx=8, pady=(2, 4))
        subcat_frame.columnconfigure(0, weight=1)
        subcat_frame.columnconfigure(2, weight=1)
        subcat_frame.columnconfigure(4, weight=1)

        misinfo_sub = ctk.CTkFrame(subcat_frame, fg_color="transparent")
        misinfo_sub.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        ctk.CTkLabel(misinfo_sub, text="Misinfo %", font=ctk.CTkFont(size=10),
                     text_color="#f39c12").pack(anchor="w")
        misinfo_pct_entry = ctk.CTkEntry(misinfo_sub, height=28, font=ctk.CTkFont(size=11),
                                          placeholder_text="33.33")
        misinfo_pct_entry.pack(fill="x")
        misinfo_pct_entry.insert(0, "33.33")

        ctk.CTkLabel(subcat_frame, text="+", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#888").grid(row=0, column=1, padx=2)

        satire_sub = ctk.CTkFrame(subcat_frame, fg_color="transparent")
        satire_sub.grid(row=0, column=2, sticky="ew", padx=2)
        ctk.CTkLabel(satire_sub, text="Satire %", font=ctk.CTkFont(size=10),
                     text_color="#9b59b6").pack(anchor="w")
        satire_pct_entry = ctk.CTkEntry(satire_sub, height=28, font=ctk.CTkFont(size=11),
                                         placeholder_text="33.33")
        satire_pct_entry.pack(fill="x")
        satire_pct_entry.insert(0, "33.33")

        ctk.CTkLabel(subcat_frame, text="+", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#888").grid(row=0, column=3, padx=2)

        clickbait_sub = ctk.CTkFrame(subcat_frame, fg_color="transparent")
        clickbait_sub.grid(row=0, column=4, sticky="ew", padx=(2, 0))
        ctk.CTkLabel(clickbait_sub, text="Clickbait %", font=ctk.CTkFont(size=10),
                     text_color="#3498db").pack(anchor="w")
        clickbait_pct_entry = ctk.CTkEntry(clickbait_sub, height=28, font=ctk.CTkFont(size=11),
                                            placeholder_text="33.34")
        clickbait_pct_entry.pack(fill="x")
        clickbait_pct_entry.insert(0, "33.34")

        subcat_sum_label = ctk.CTkLabel(subcat_frame, text="= 100.00%",
                                         font=ctk.CTkFont(size=11, weight="bold"),
                                         text_color="#2ecc71")
        subcat_sum_label.grid(row=0, column=5, padx=(4, 0))

        # Auto-fill: first-to-last method
        # Editing Misinfo → splits remaining evenly to Satire & Clickbait
        # Editing Satire → auto-calculates Clickbait (100 - Misinfo - Satire)
        # Editing Clickbait → only updates sum label, no auto-fill
        _subcat_updating = [False]

        def _update_subcat_sum():
            """Update the sum label with current values."""
            try:
                m = float(misinfo_pct_entry.get().strip() or "0")
                s = float(satire_pct_entry.get().strip() or "0")
                c = float(clickbait_pct_entry.get().strip() or "0")
                total = round(m + s + c, 2)
                color = "#2ecc71" if abs(total - 100.0) < 0.02 else "#e74c3c"
                subcat_sum_label.configure(text=f"= {total:.2f}%", text_color=color)
            except ValueError:
                subcat_sum_label.configure(text="= ???", text_color="#e74c3c")

        def _on_misinfo_change(*_):
            if _subcat_updating[0]:
                return
            val = misinfo_pct_entry.get().strip()
            try:
                m = round(float(val), 2)
                if 0 <= m <= 100:
                    _subcat_updating[0] = True
                    remaining = round(100.0 - m, 2)
                    half = round(remaining / 2, 2)
                    other_half = round(remaining - half, 2)
                    satire_pct_entry.delete(0, "end")
                    satire_pct_entry.insert(0, f"{half:.2f}")
                    clickbait_pct_entry.delete(0, "end")
                    clickbait_pct_entry.insert(0, f"{other_half:.2f}")
                    _subcat_updating[0] = False
            except ValueError:
                pass
            _update_subcat_sum()

        def _on_satire_change(*_):
            if _subcat_updating[0]:
                return
            val_m = misinfo_pct_entry.get().strip()
            val_s = satire_pct_entry.get().strip()
            try:
                m = round(float(val_m or "0"), 2)
                s = round(float(val_s), 2)
                if 0 <= s <= 100:
                    _subcat_updating[0] = True
                    c = round(100.0 - m - s, 2)
                    clickbait_pct_entry.delete(0, "end")
                    clickbait_pct_entry.insert(0, f"{c:.2f}")
                    _subcat_updating[0] = False
            except ValueError:
                pass
            _update_subcat_sum()

        def _on_clickbait_change(*_):
            # Last field: no auto-fill, just update the sum label
            _update_subcat_sum()

        misinfo_pct_entry.bind("<KeyRelease>", _on_misinfo_change)
        satire_pct_entry.bind("<KeyRelease>", _on_satire_change)
        clickbait_pct_entry.bind("<KeyRelease>", _on_clickbait_change)

        kappa_output_folder_entry = _make_field(mid_card, "Output Folder",
                                                  default_kappa_bundle, row=10,
                                                  browse_dir=True)

        # Static note explaining the output folder
        ctk.CTkLabel(mid_card, text=(
            "ℹ The sample CSV, images/ and videos/ will all be\n"
            "   placed inside this folder. "),
            font=ctk.CTkFont(size=10), text_color="#3498db",
            wraplength=300, justify="left", anchor="nw").grid(
                row=12, column=0, padx=10, pady=(0, 2), sticky="w")

        def _run_kappa_gen():
            input_csv = kappa_input_entry.get().strip()
            n_str = kappa_n_entry.get().strip()
            output_folder = kappa_output_folder_entry.get().strip() or default_kappa_bundle
            if not input_csv:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Missing Input", "Provide the input CSV path.", parent=popup)
                popup.attributes("-topmost", True)
                return
            try:
                n = int(n_str) if n_str else 500
                if n <= 0:
                    raise ValueError("Must be positive")
            except ValueError as e:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Invalid", f"Bad sample size: {e}", parent=popup)
                popup.attributes("-topmost", True)
                return

            # Validate Real/Fake distribution
            try:
                r_pct = round(float(real_pct_entry.get().strip() or "50"), 2)
                f_pct = round(float(fake_pct_entry.get().strip() or "50"), 2)
                if abs(r_pct + f_pct - 100.0) > 0.01:
                    raise ValueError(f"Real ({r_pct}%) + Fake ({f_pct}%) = {r_pct + f_pct:.2f}%, must equal 100%")
                if r_pct < 0 or f_pct < 0:
                    raise ValueError("Percentages cannot be negative")
            except ValueError as e:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Invalid Distribution", str(e), parent=popup)
                popup.attributes("-topmost", True)
                return

            # Validate Fake sub-category distribution
            try:
                m_pct = round(float(misinfo_pct_entry.get().strip() or "33.33"), 2)
                s_pct = round(float(satire_pct_entry.get().strip() or "33.33"), 2)
                c_pct = round(float(clickbait_pct_entry.get().strip() or "33.34"), 2)
                sub_total = round(m_pct + s_pct + c_pct, 2)
                if abs(sub_total - 100.0) > 0.02:
                    raise ValueError(
                        f"Misinfo ({m_pct}%) + Satire ({s_pct}%) + Clickbait ({c_pct}%) = {sub_total:.2f}%\n"
                        f"Fake sub-categories must sum to 100%")
                if m_pct < 0 or s_pct < 0 or c_pct < 0:
                    raise ValueError("Percentages cannot be negative")
            except ValueError as e:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Invalid Sub-categories", str(e), parent=popup)
                popup.attributes("-topmost", True)
                return

            # Warn if the output folder already has content from a previous run
            bundle_csv = os.path.join(output_folder, "relabeling_for_kappa.csv")
            bundle_imgs = os.path.join(output_folder, "images")
            bundle_vids = os.path.join(output_folder, "videos")
            existing = []
            if os.path.exists(bundle_csv):
                existing.append("relabeling_for_kappa.csv")
            if os.path.isdir(bundle_imgs) and os.listdir(bundle_imgs):
                existing.append("images/")
            if os.path.isdir(bundle_vids) and os.listdir(bundle_vids):
                existing.append("videos/")
            if existing:
                popup.attributes("-topmost", False)
                if not messagebox.askyesno("Overwrite Warning",
                    f"Output folder already contains data from a previous run:\n"
                    f"  {output_folder}\n\n"
                    f"These will be overwritten:\n" +
                    "\n".join(f"  • {p}" for p in existing) +
                    "\n\nContinue?", parent=popup):
                    popup.attributes("-topmost", True)
                    return
                popup.attributes("-topmost", True)

            _show_result_popup("Generate Kappa Sample",
                               lambda: generate_kappa_sample(input_csv, n,
                                                              output_folder=output_folder,
                                                              real_pct=r_pct, misinfo_pct=m_pct,
                                                              satire_pct=s_pct, clickbait_pct=c_pct))

        mid_btn = ctk.CTkFrame(mid_card, fg_color="transparent")
        mid_btn.grid(row=30, column=0, padx=10, pady=(4, 10), sticky="sew")
        ctk.CTkButton(mid_btn, text="▶ Generate Sample", command=_run_kappa_gen,
                       height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black").pack(fill="x")

        # ---- COLUMN 3: Calculate Kappa ----
        right_card = ctk.CTkFrame(columns_frame, fg_color="#222244", corner_radius=10,
                                   border_width=1, border_color="#444")
        right_card.grid(row=0, column=2, sticky="nsew", padx=(4, 0), pady=4)
        right_card.columnconfigure(0, weight=1)
        right_card.rowconfigure(20, weight=1)

        ctk.CTkLabel(right_card, text="📊 Calculate Kappa",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
                         row=0, column=0, padx=8, pady=(10, 2), sticky="w")

        ctk.CTkLabel(right_card, text=(
            "• Calculates inter-rater agreement\n"
            "• Computes for both Label & Multi-Category\n"
            "• Cohen: pairwise (every pair of annotators)\n"
            "• Fleiss: all annotators at once\n"
            "• All records must be fully labeled first"),
            font=ctk.CTkFont(size=11), text_color="#999",
            wraplength=300, justify="left", anchor="nw").grid(
                row=1, column=0, padx=10, pady=(2, 4), sticky="w")

        kappa_calc_entry = _make_field(right_card, "Kappa CSV File",
                                        str(Path(default_kappa_bundle) / "relabeling_for_kappa.csv"),
                                        row=2, browse_file=True)

        ctk.CTkLabel(right_card, text="Kappa Mode",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ccc", anchor="w").grid(
                         row=4, column=0, sticky="w", padx=8, pady=(6, 0))

        kappa_mode_var = ctk.StringVar(value="Cohen's Kappa (pairwise)")
        ctk.CTkOptionMenu(
            right_card,
            values=["Cohen's Kappa (pairwise)", "Fleiss' Kappa (all raters)"],
            variable=kappa_mode_var,
            font=ctk.CTkFont(size=12),
            fg_color="#333", button_color="#444", height=30
        ).grid(row=5, column=0, sticky="ew", padx=8, pady=(2, 4))

        def _run_kappa_calc():
            csv_path = kappa_calc_entry.get().strip()
            if not csv_path:
                popup.attributes("-topmost", False)
                messagebox.showwarning("Missing Input", "Provide the kappa CSV path.", parent=popup)
                popup.attributes("-topmost", True)
                return
            mode = "cohen" if "Cohen" in kappa_mode_var.get() else "fleiss"
            _show_result_popup("Calculate Kappa",
                               lambda: calculate_kappa(csv_path, mode=mode))

        right_btn = ctk.CTkFrame(right_card, fg_color="transparent")
        right_btn.grid(row=20, column=0, padx=10, pady=(4, 10), sticky="sew")
        ctk.CTkButton(right_btn, text="▶ Calculate Kappa", command=_run_kappa_calc,
                       height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black").pack(fill="x")

        # Close button
        ctk.CTkButton(popup, text="Close", command=popup.destroy,
                       height=36, font=ctk.CTkFont(size=13),
                       fg_color="transparent", border_width=1,
                       border_color="#555", width=130).pack(pady=(4, 12))

