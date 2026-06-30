"""
StatsMixin mixin class.
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog
import tkinter as tk
import csv
import time
import threading
from datetime import datetime
from app_paths import ASSETS_DIR, CSV_PATH
from constants import DETAILED_STATS_COLUMNS, DETAILED_STATS_METRICS, CATEGORIES, SOURCE_CATEGORIES, MIN_TEXT_LENGTH
from data.stats_engine import get_image_count, get_video_count, get_entry_count, get_label_counts
from data.config_manager import get_full_config

class StatsMixin:
    def _create_stat_badge(self, parent, label, count, dot_color="#888"):
        """
        Creates and packs a visually stylized metric badge/card inside the stats bar.
        
        Each badge card is enclosed in a dark, rounded container with a subtle border.
        It contains a colored circular dot indicating status/category, a large bold
        counter showing the numeric value, and a smaller descriptive label.
        
        Args:
            parent: The Tkinter container widget that will host this badge.
            label: Text descriptor for the metric (e.g., "Fake", "Real", "Images").
            count: Numeric value/count to display.
            dot_color: Hex color string for the status dot indicator.
        """
        # Create the outer container frame for the statistic badge card.
        # This frame establishes the card boundaries, using a dark background color
        # and rounded corners for a modern, dashboard-like style.
        badge = ctk.CTkFrame(parent, fg_color="#1e1e3a", corner_radius=8,
                              border_width=1, border_color="#333")
        
        # Create an inner widget wrapper that handles spacing and layout within the card.
        # Keeping this transparent lets the parent frame's background color show through.
        inner = ctk.CTkFrame(badge, fg_color="transparent")
        inner.pack(padx=10, pady=6)
        
        # Draw the status indicator dot. We configure a tiny frame with rounded corners
        # (corner_radius = half of width/height) to create a perfect circle.
        dot = ctk.CTkFrame(inner, width=10, height=10, corner_radius=5,
                            fg_color=dot_color)
        dot.pack(side="left", padx=(0, 6))
        
        # Disable pack propagation on the dot frame. This is critical because without it,
        # Tkinter would shrink this empty container to 0x0 size since it has no child widgets.
        dot.pack_propagate(False)
        
        # Render the count text. We use a larger, bold font to make the numeric statistic
        # stand out as the primary metric of the card.
        ctk.CTkLabel(inner, text=str(count),
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ffffff").pack(side="left", padx=(0, 6))
        
        # Render the helper label text to describe what the count represents.
        # This uses a smaller, secondary text color to keep the dashboard visual hierarchy clean.
        ctk.CTkLabel(inner, text=label,
                     font=ctk.CTkFont(size=11),
                     text_color="#aaa").pack(side="left")

    def _create_stat_label(self, parent, text, filter_key=None, is_separator=False):
        """
        Helper method to instantiate stat labels inside a FlowFrame parent.
        
        These labels do not define click actions. Instead, they serve as display
        items or textual separators (e.g. pipe characters) in the categories list.
        Because they are placed in a FlowFrame, they do not need explicit manual
        packing; the parent layout manager arranges them automatically.
        
        Args:
            parent: The FlowFrame hosting the label list.
            text: Text content of the label.
            filter_key: Optional identifier for category filtering.
            is_separator: If True, renders a neutral separator style.
        """
        # If this is a decorative divider element (like a pipe separator "|"),
        # render it using a default font style without key-based color themes.
        if is_separator:
            lbl = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=13))
            return

        # Determine label text color by checking the active Tkinter appearance mode (Dark vs Light).
        # This keeps text elements legible regardless of system-level styling preferences.
        color = "#ffffff" if ctk.get_appearance_mode() == "Dark" else "#000000"
        fnt = ctk.CTkFont(size=13)
        lbl = ctk.CTkLabel(parent, text=text, font=fnt, text_color=color)

    def _create_clickable_stat_badge(self, parent, label, count, dot_color="#888", command=None):
        """
        Creates a clickable visually stylized metric badge/card inside the stats bar.
        Supports hover styling, hand2 cursor, and bindings to click event.
        """
        badge = ctk.CTkFrame(parent, fg_color="#1e1e3a", corner_radius=8,
                              border_width=1, border_color="#333", cursor="hand2")
        
        inner = ctk.CTkFrame(badge, fg_color="transparent")
        inner.pack(padx=10, pady=6)
        
        dot = ctk.CTkFrame(inner, width=10, height=10, corner_radius=5,
                            fg_color=dot_color)
        dot.pack(side="left", padx=(0, 6))
        dot.pack_propagate(False)
        
        count_lbl = ctk.CTkLabel(inner, text=str(count),
                                 font=ctk.CTkFont(size=16, weight="bold"),
                                 text_color="#ffffff")
        count_lbl.pack(side="left", padx=(0, 6))
        
        text_lbl = ctk.CTkLabel(inner, text=label,
                                font=ctk.CTkFont(size=11),
                                text_color="#aaa")
        text_lbl.pack(side="left")
        
        # Hover effect
        def on_enter(e):
            badge.configure(fg_color="#2c2c54")
        def on_leave(e):
            badge.configure(fg_color="#1e1e3a")
            
        widgets = [badge, inner, dot, count_lbl, text_lbl]
        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            if command:
                w.bind("<Button-1>", lambda e: command())
                
        return badge

    def _update_stats(self):
        """
        Recalculates and refreshes the database statistics dashboard at the top of the UI.
        
        This method aggregates count data for articles, classification labels, fake news
        sub-categories, and media types. It supports two operational scopes:
        1. Filtered subset: If the user is in Review mode and has an active search filter, 
           statistics are calculated dynamically from the loaded/filtered records in memory.
        2. Global dataset: Otherwise, statistics are fetched directly from the database 
           using backend helper functions.
           
        After calculating counts, all existing badge widgets are destroyed and recreated
        to avoid layout stacking, followed by a manual FlowFrame layout trigger.
        """
        # Determine whether we should compile statistics from the active filter results.
        # This is active only if we are in review mode and an advanced filter query is loaded.
        use_filtered = (self.current_mode == "review" and self.advanced_filter
                         and hasattr(self, 'dataset_records'))

        if use_filtered:
            # Aggregate category stats directly from the filtered memory list.
            records = self.dataset_records
            total = len(records)
            
            # Tally primary target authenticity classes
            fake = sum(1 for r in records if (r.get("label") or "") == "Fake")
            real = sum(1 for r in records if (r.get("label") or "") == "Real")
            
            # Set up aggregation trackers for fake news subtypes, categories, and media
            sub = {"Misinformation": 0, "Satire": 0, "Clickbait": 0}
            news_cats = {}
            img_count = 0
            vid_count = 0
            only_image = 0
            only_text = 0
            both_text_image = 0
            
            # Iterate through active records and aggregate counts
            for r in records:
                # Increment counts for fake news classifications (Misinformation, Satire, Clickbait)
                mc = (r.get("multi_category") or "").strip()
                if mc in sub:
                    sub[mc] += 1
                
                # Increment counts for news categories (e.g. Politics, Sports, Health)
                cat = (r.get("category") or "").strip()
                if cat:
                    news_cats[cat] = news_cats.get(cat, 0) + 1
                
                # Parse semicolon-delimited image paths and count files
                ip = (r.get("image_path") or "").strip()
                img_list = [p for p in ip.split(";") if p.strip()]
                if ip:
                    img_count += len(img_list)
                
                # Check for video attachments
                vp = (r.get("video_path") or "").strip()
                if vp:
                    vid_count += 1
                
                # Categorize the article format based on the presence of text vs media files
                has_text = bool((r.get("text") or "").strip())
                has_image = bool(img_list)
                has_media = has_image or bool(vp)
                
                if has_text and has_media:
                    both_text_image += 1
                elif has_text and not has_media:
                    only_text += 1
                elif not has_text and has_media:
                    only_image += 1
            
            # Retain a reference to the global unfiltered total to display alongside the subset size
            global_total = len(self.all_dataset_records)
        else:
            # Query global database stats directly from the CSV parser backend module.
            # This is used when there are no active filters or we are in standard annotate mode.
            counts = get_label_counts()
            img_count = get_image_count()
            vid_count = get_video_count()
            total = counts["total"]
            fake = counts["fake"]
            real = counts["real"]
            sub = counts["fake_subcategories"]
            news_cats = counts["news_categories"]
            only_image = counts["only_image"]
            only_text = counts["only_text"]
            both_text_image = counts["both_text_image"]
            global_total = None

        # Temporarily freeze geometry propagation to prevent flickering/resizing during rebuild
        current_stats_h = self.stats_frame.winfo_height()
        current_cat_h = self.category_stats_frame.winfo_height()
        lock_stats_h = current_stats_h if current_stats_h > 1 else 52
        lock_cat_h = current_cat_h if current_cat_h > 1 else 24

        self.stats_frame.configure(height=lock_stats_h)
        self.stats_frame.pack_propagate(False)
        self.category_stats_frame.configure(height=lock_cat_h)
        self.category_stats_frame.pack_propagate(False)

        # Tear down all existing badge widgets from the main stats frame.
        # This prevents widgets from stacking on top of each other when redrawing.
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
            
        # Clean up existing category label displays from the bottom statistics strip.
        for widget in self.category_stats_frame.winfo_children():
            widget.destroy()

        # Build total entries dashboard cards
        if use_filtered:
            # Display active records relative to the database totals (e.g. "Filtered / 45")
            self._create_stat_badge(self.stats_frame, f"Filtered / {global_total}", total, "#3498db")
        else:
            self._create_stat_badge(self.stats_frame, "Total", total, "#3498db")
        
        # Render Fake/Real category status badges.
        # If using active filters, we hide badges that have zero counts to keep the UI clean.
        if not use_filtered or fake > 0:
            self._create_stat_badge(self.stats_frame, "Fake", fake, "#e74c3c")
        if not use_filtered or real > 0:
            self._create_stat_badge(self.stats_frame, "Real", real, "#2ecc71")
        
        # Render subclassification badges for fine-grained Fake News subtypes
        if not use_filtered or sub["Misinformation"] > 0:
            self._create_stat_badge(self.stats_frame, "Misinfo", sub["Misinformation"], "#e67e22")
        if not use_filtered or sub["Satire"] > 0:
            self._create_stat_badge(self.stats_frame, "Satire", sub["Satire"], "#9b59b6")
        if not use_filtered or sub["Clickbait"] > 0:
            self._create_stat_badge(self.stats_frame, "Clickbait", sub["Clickbait"], "#f39c12")
            
        # Duplicate audit badge (in Review and Annotate modes)
        if self.current_mode in ("review", "annotate"):
            if not hasattr(self, '_duplicate_pairs_cache') or self._duplicate_pairs_cache is None:
                self._compute_global_duplicates()
                
            if hasattr(self, '_duplicate_computing') and self._duplicate_computing:
                dup_count = "..."
            else:
                unique_records_with_dups = set()
                if self._duplicate_pairs_cache is not None:
                    for pair in self._duplicate_pairs_cache:
                        unique_records_with_dups.add(pair["idx_a"])
                        unique_records_with_dups.add(pair["idx_b"])
                dup_count = len(unique_records_with_dups)
                
            self._create_clickable_stat_badge(
                self.stats_frame, "Duplicates", dup_count, "#e67e22",
                command=self._show_global_duplicate_audit
            )

        
        # Create a "See More" badge-style button
        see_more_badge = ctk.CTkFrame(
            self.stats_frame, fg_color="#1e1e3a", corner_radius=8,
            border_width=1, border_color="#333", cursor="hand2"
        )
        
        inner = ctk.CTkFrame(see_more_badge, fg_color="transparent")
        inner.pack(padx=10, pady=6)
        
        dot = ctk.CTkFrame(inner, width=10, height=10, corner_radius=5, fg_color="#3498db")
        dot.pack(side="left", padx=(0, 6))
        dot.pack_propagate(False)
        
        lbl = ctk.CTkLabel(
            inner, text="See More ▸",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#3498db"
        )
        lbl.pack(side="left")
        
        # Add hover effects to the see more badge frame and its children
        def on_enter(e):
            see_more_badge.configure(fg_color="#2c2c54")
        def on_leave(e):
            see_more_badge.configure(fg_color="#1e1e3a")
            
        see_more_badge.bind("<Enter>", on_enter)
        see_more_badge.bind("<Leave>", on_leave)
        inner.bind("<Enter>", on_enter)
        inner.bind("<Leave>", on_leave)
        dot.bind("<Enter>", on_enter)
        dot.bind("<Leave>", on_leave)
        lbl.bind("<Enter>", on_enter)
        lbl.bind("<Leave>", on_leave)
        
        # Bind click events
        see_more_badge.bind("<Button-1>", lambda e: self._show_detailed_stats_popup())
        inner.bind("<Button-1>", lambda e: self._show_detailed_stats_popup())
        dot.bind("<Button-1>", lambda e: self._show_detailed_stats_popup())
        lbl.bind("<Button-1>", lambda e: self._show_detailed_stats_popup())

        # Compile and layout the horizontal categories text bar
        if news_cats:
            # Instantiate section header
            lbl = ctk.CTkLabel(self.category_stats_frame, text="News Categories  ▸  ", font=ctk.CTkFont(size=12), text_color="#aaa")
            lbl.pack(side="left", padx=(0, 6))
            
            # Sort category keys alphabetically to guarantee a stable, predictable layout order
            sorted_cats = sorted(news_cats.items())
            for i, (cat, count) in enumerate(sorted_cats):
                self._create_stat_label(self.category_stats_frame, f"{cat}: {count}", filter_key=cat)
                
                # Append pipe separators between adjacent items, skipping the last element
                if i < len(sorted_cats) - 1:
                    self._create_stat_label(self.category_stats_frame, "|", is_separator=True)
        else:
            # Fallback message displayed when no categories have been saved yet
            lbl = ctk.CTkLabel(self.category_stats_frame, text="News Categories  ▸  No entries yet", font=ctk.CTkFont(size=12), text_color="#aaa")
            lbl.pack(side="left", padx=(0, 6))

        # Re-enable pack propagation after creating all widgets
        self.stats_frame.pack_propagate(True)
        self.category_stats_frame.pack_propagate(True)

        # Force Tkinter layout engine update to process changes before arranging widget coordinate paths
        self.stats_frame.update_idletasks()
        self.category_stats_frame.update_idletasks()
        
        # Call the FlowFrame layout manager arrange algorithm to calculate reflow positions
        self.stats_frame._arrange()
        self.category_stats_frame._arrange()

    def _get_records_for_detailed_stats(self):
        """
        Retrieves the list of records to compute detailed statistics on.
        If the app is in Review mode and filtering is active, it returns
        self.dataset_records (the filtered subset). Otherwise, it reads all
        records dynamically from dataset.csv.
        """
        use_filtered = (self.current_mode == "review" and self.advanced_filter
                         and hasattr(self, 'dataset_records'))
        if use_filtered:
            return self.dataset_records
        
        records = []
        if CSV_PATH.exists() and CSV_PATH.stat().st_size > 0:
            try:
                with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        records.append(row)
            except Exception as e:
                print(f"[WARNING] Failed to read CSV for detailed stats: {e}")
        return records

    def _filter_detailed_stats_records(self, records, selected_category="All Categories",
                                       selected_annotator="All Annotators"):
        filtered_records = records
        if selected_category != "All Categories":
            filtered_records = [
                r for r in filtered_records
                if (r.get("category") or "").strip() == selected_category
            ]
        if selected_annotator != "All Annotators":
            filtered_records = [
                r for r in filtered_records
                if (r.get("annotator") or "").strip() == selected_annotator
            ]
        return filtered_records

    def _detailed_stats_export_rows(self, stats):
        headers = ["Modality / Metric", *DETAILED_STATS_COLUMNS]
        rows = [headers]
        for metric_name in DETAILED_STATS_METRICS:
            rows.append([
                metric_name,
                *[str(stats[col_key][metric_name]) for col_key in DETAILED_STATS_COLUMNS]
            ])
        return rows

    def _ask_detailed_stats_export_scope(self, parent):
        """
        Opens a small modal with explicit export-scope buttons.
        Returns "current", "all", or None when canceled.
        """
        choice = {"value": None}

        dialog = ctk.CTkToplevel(parent)
        dialog.title("Export Statistics")
        dialog.configure(fg_color="#1a1a2e")
        dialog.transient(parent)
        dialog.grab_set()
        dialog.resizable(False, False)

        pw, ph = 420, 175
        dialog.geometry(f"{pw}x{ph}")
        dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (pw // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (ph // 2)
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog,
            text="Choose Export Scope",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#cdd6f4"
        ).pack(pady=(20, 6))

        ctk.CTkLabel(
            dialog,
            text="Pick exactly what should be written to the CSV.",
            font=ctk.CTkFont(size=12),
            text_color="#a6adc8"
        ).pack(pady=(0, 18))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=22)

        def finish(value):
            choice["value"] = value
            dialog.destroy()

        ctk.CTkButton(
            btn_frame,
            text="Current Dashboard",
            command=lambda: finish("current"),
            height=36,
            fg_color="#4f46e5",
            hover_color="#5c5cff"
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="All Local Categories",
            command=lambda: finish("all"),
            height=36,
            fg_color="#313244",
            hover_color="#45475a"
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            command=lambda: finish(None),
            height=36,
            fg_color="transparent",
            border_width=1,
            border_color="#555"
        ).pack(side="left", fill="x", expand=True)

        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(None))
        parent.wait_window(dialog)
        return choice["value"]

    def _refresh_detailed_stats_filters(self, is_global, category_var, annotator_var,
                                        category_menu, annotator_menu, option_provider):
        """
        Keeps detailed dashboard filters aligned with the selected metrics scope.
        Uses cascading logic: selecting one filter narrows the other's options.
        """
        current_category = category_var.get()
        current_annotator = annotator_var.get()
        category_options, annotator_options = option_provider(
            is_global, selected_category=current_category, selected_annotator=current_annotator
        )

        category_values = category_options
        category_state = "normal"
        if category_var.get() not in category_values:
            category_var.set("All Categories")

        if annotator_var.get() not in annotator_options:
            annotator_var.set("All Annotators")

        if category_menu is not None:
            category_menu.configure(values=category_values, state=category_state)
            if not category_menu.winfo_manager():
                if annotator_menu is not None:
                    category_menu.pack(side="left", padx=(0, 10), before=annotator_menu)
                else:
                    category_menu.pack(side="left", padx=(0, 10))
        if annotator_menu is not None:
            annotator_menu.configure(values=annotator_options)

    def _show_detailed_stats_popup(self):
        """
        Displays a modal popup with a detailed dashboard breakdown of news modalities
        (Video, Image, Text combinations) across all authenticity categories.
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Detailed Statistics Dashboard")
        popup.configure(fg_color="#11111b")  # Darker premium background
        popup.transient(self)
        popup.grab_set()
        popup.resizable(True, True)

        pw, ph = 960, 680
        popup.geometry(f"{pw}x{ph}")
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (pw // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (ph // 2)
        popup.geometry(f"+{x}+{y}")

        all_records = self._get_records_for_detailed_stats()
        global_annotator_filter_map = {}
        def _dashboard_filter_options(is_global=False, selected_category="All Categories",
                                      selected_annotator="All Annotators"):
            """
            Builds cascading filter options. When one filter is set, the other
            dropdown is narrowed to only show relevant matching options.
            """
            if is_global:
                # --- Build raw data map: {(ann_label, machine_uuid): set of categories} ---
                annotator_cats_map = {}  # option_label -> set of category names
                cat_annotators_map = {}  # category_name -> set of option_labels
                
                entries = []
                name_counts = {}
                global_annotator_filter_map.clear()
                
                for machine_uuid, machine_data in self.global_metrics_data.items():
                    if not isinstance(machine_data, dict):
                        continue
                    for ann_name, ann_stats in machine_data.items():
                        if not isinstance(ann_stats, dict):
                            continue
                        ann_label = str(ann_name).strip()
                        if not ann_label:
                            continue
                        entries.append((ann_label, str(machine_uuid)))
                        name_counts[ann_label] = name_counts.get(ann_label, 0) + 1
                
                # Build option labels and the filter map
                option_labels_by_key = {}  # (ann_label, machine_uuid) -> option_label
                for ann_label, machine_uuid in sorted(entries):
                    if name_counts.get(ann_label, 0) > 1:
                        option_label = f"{ann_label}-{machine_uuid[-8:]}"
                    else:
                        option_label = ann_label
                    global_annotator_filter_map[option_label] = (ann_label, machine_uuid)
                    option_labels_by_key[(ann_label, machine_uuid)] = option_label
                
                # Now build the category <-> annotator mappings
                for machine_uuid, machine_data in self.global_metrics_data.items():
                    if not isinstance(machine_data, dict):
                        continue
                    for ann_name, ann_stats in machine_data.items():
                        if not isinstance(ann_stats, dict):
                            continue
                        ann_label = str(ann_name).strip()
                        if not ann_label:
                            continue
                        option_label = option_labels_by_key.get((ann_label, str(machine_uuid)))
                        if not option_label:
                            continue
                        
                        categories_data = ann_stats.get("_categories")
                        if isinstance(categories_data, dict):
                            cats_for_ann = set()
                            for cat_key in categories_data:
                                if cat_key != "_uncategorized":
                                    cats_for_ann.add(cat_key)
                                    if cat_key not in cat_annotators_map:
                                        cat_annotators_map[cat_key] = set()
                                    cat_annotators_map[cat_key].add(option_label)
                            annotator_cats_map[option_label] = cats_for_ann
                        else:
                            # Old format: this annotator has no category info
                            # They appear in all category filters (can't be narrowed)
                            annotator_cats_map[option_label] = None  # None = all categories
                
                # Build category dropdown (narrowed by selected annotator)
                all_global_cats = set()
                for cats in annotator_cats_map.values():
                    if cats is not None:
                        all_global_cats.update(cats)
                
                if selected_annotator != "All Annotators":
                    ann_cats = annotator_cats_map.get(selected_annotator)
                    if ann_cats is not None:
                        visible_cats = ann_cats
                    else:
                        # Old format annotator: show all categories
                        visible_cats = all_global_cats
                else:
                    visible_cats = all_global_cats
                
                preferred_categories = [c for c in CATEGORIES if c and c in visible_cats]
                extra_categories = sorted(visible_cats - set(preferred_categories))
                category_values = ["All Categories"] + preferred_categories + extra_categories
                
                # Build annotator dropdown (narrowed by selected category)
                if selected_category != "All Categories":
                    # Show annotators who have this category OR have no category data (old format)
                    visible_annotators = []
                    for opt_label in sorted(annotator_cats_map.keys()):
                        ann_cats = annotator_cats_map[opt_label]
                        if ann_cats is None or selected_category in ann_cats:
                            visible_annotators.append(opt_label)
                else:
                    visible_annotators = sorted(annotator_cats_map.keys())
                
                annotator_values = ["All Annotators"] + visible_annotators
            else:
                # --- LOCAL MODE: cascade using raw records ---
                # Narrow categories based on selected annotator
                if selected_annotator != "All Annotators":
                    scoped_records = [
                        r for r in all_records
                        if (r.get("annotator") or "").strip() == selected_annotator
                    ]
                else:
                    scoped_records = all_records
                
                local_categories = {
                    (r.get("category") or "").strip()
                    for r in scoped_records
                    if (r.get("category") or "").strip()
                }
                preferred_categories = [c for c in CATEGORIES if c and c in local_categories]
                extra_categories = sorted(local_categories - set(preferred_categories))
                category_values = ["All Categories"] + preferred_categories + extra_categories

                # Narrow annotators based on selected category
                if selected_category != "All Categories":
                    cat_records = [
                        r for r in all_records
                        if (r.get("category") or "").strip() == selected_category
                    ]
                else:
                    cat_records = all_records
                
                local_annotators = {
                    (r.get("annotator") or "").strip()
                    for r in cat_records
                    if (r.get("annotator") or "").strip()
                }
                annotator_values = ["All Annotators"] + sorted(local_annotators)
            return category_values, annotator_values

        # Top Controls Frame
        top_frame = ctk.CTkFrame(popup, fg_color="transparent")
        top_frame.pack(fill="x", padx=24, pady=(24, 10))
        
        ctk.CTkLabel(top_frame, text="Filter:", font=ctk.CTkFont(size=14, weight="bold"), text_color="#cdd6f4").pack(side="left", padx=(0, 10))
        
        category_options, annotator_options = _dashboard_filter_options(
            self.global_metrics_enabled.get(),
            selected_category="All Categories",
            selected_annotator="All Annotators"
        )
        category_var = ctk.StringVar(value="All Categories")
        annotator_var = ctk.StringVar(value="All Annotators")
        category_menu = None
        annotator_menu = None
        
        def show_info():
            info_text = (
                "Dashboard Calculation Metrics:\n\n"
                "1. Local Metrics: Calculated from your local dataset.csv and can be filtered by category and annotator.\n\n"
                "2. Global Metrics (Team): Calculated from synced aggregate counts in the team's GitHub Gist. No raw article text, notes, sources, or media files are uploaded.\n\n"
                "3. Duplicate Names: If two synced machines use the same annotator name, the Team filter shows Name-last8uuid to keep them separate.\n\n"
                "4. Hidden by Default: Percentages only appear when you click a row or column header.\n\n"
                "5. Column Clicks (Vertical %): Shows the distribution of modalities for that specific column.\n\n"
                "6. Row Clicks (Horizontal %): 'Real' & 'Fake' are percentages of the 'Total' column. 'Misinfo', 'Satire', & 'Clickbait' are percentages of the 'Fake' column.\n\n"
                "7. Raw Counts: The 'Total Items' row and 'Total' column always show raw instance counts."
            )
            messagebox.showinfo("Metrics Info", info_text, parent=popup)

        info_btn = ctk.CTkButton(top_frame, text="❓", width=28, height=28, fg_color="transparent", hover_color="#313244", font=ctk.CTkFont(size=14), command=show_info)
        info_btn.pack(side="right", padx=(10, 0))
        
        # Add Team Sync and Global Metrics Toggle
        self.team_sync_btn = ctk.CTkButton(top_frame, text="🌐 Team Sync", command=self._show_team_sync_popup,
                                          width=100, height=28,
                                          font=ctk.CTkFont(size=13),
                                          fg_color="#27ae60", hover_color="#2ecc71",
                                          border_width=1, border_color="#555",
                                          corner_radius=6)
        self.team_sync_btn.pack(side="right", padx=(10, 10))

        def on_global_toggle():
            # Update the dashboard whenever the toggle is clicked
            draw_dashboard()

        self.active_detailed_popup = popup

        self.global_toggle = ctk.CTkSwitch(top_frame, text="Global Metrics (Team)", 
                                           variable=self.global_metrics_enabled,
                                           command=on_global_toggle,
                                           font=ctk.CTkFont(size=13, weight="bold"))
        self.global_toggle.pack(side="right", padx=10)

        self.sync_time_label = ctk.CTkLabel(top_frame, text="", font=ctk.CTkFont(size=11), text_color="#a6adc8")
        self.sync_time_label.pack(side="right", padx=5)

        # Container for the dashboard (Cards + Grid)
        dash_container = ctk.CTkFrame(popup, fg_color="transparent")
        dash_container.pack(fill="both", expand=True)
        
        # Active subset data for CSV export
        active_export_data = []
        # Toggle for including teammates without category data
        include_uncategorized_var = ctk.BooleanVar(value=False)

        def draw_dashboard(*args):
            nonlocal active_export_data
            for widget in dash_container.winfo_children():
                widget.destroy()

            is_global = self.global_metrics_enabled.get()
            self._refresh_detailed_stats_filters(
                is_global, category_var, annotator_var, category_menu, annotator_menu,
                _dashboard_filter_options
            )

            selected_category = category_var.get()
            selected_annotator = annotator_var.get()

            # Update sync time label
            cfg = get_full_config()
            if not cfg.get("gist_id") or not cfg.get("github_token"):
                self.sync_time_label.configure(text="Not connected")
            elif hasattr(self, 'last_global_sync_time') and self.last_global_sync_time:
                mins = int((time.time() - self.last_global_sync_time) / 60)
                if mins == 0:
                    self.sync_time_label.configure(text="Synced just now")
                else:
                    self.sync_time_label.configure(text=f"Synced {mins} min ago")
            else:
                self.sync_time_label.configure(text="Not synced yet")

            if is_global:
                # --- GLOBAL METRICS MODE ---
                # Build stats by aggregating from self.global_metrics_data
                stats = self._empty_detailed_stats()
                found_any = False
                machines_without_categories = 0
                total_annotator_entries = 0
                selected_global_entry = global_annotator_filter_map.get(selected_annotator)
                filtering_by_category = selected_category != "All Categories"

                for machine_uuid, machine_data in self.global_metrics_data.items():
                    if not isinstance(machine_data, dict):
                        continue
                    for ann_name, ann_stats in machine_data.items():
                        if not isinstance(ann_stats, dict):
                            continue
                        ann_label = str(ann_name).strip()
                        if selected_annotator != "All Annotators":
                            if selected_global_entry is None:
                                continue
                            selected_name, selected_machine_uuid = selected_global_entry
                            if ann_label != selected_name or str(machine_uuid) != selected_machine_uuid:
                                continue

                        total_annotator_entries += 1
                        categories_data = ann_stats.get("_categories")
                        has_categories = isinstance(categories_data, dict) and len(categories_data) > 0

                        if filtering_by_category:
                            if has_categories:
                                # New format: extract specific category stats
                                cat_stats = categories_data.get(selected_category)
                                if cat_stats and self._merge_detailed_stats(stats, cat_stats):
                                    found_any = True
                            else:
                                # Old format: no category data — count them but exclude by default
                                machines_without_categories += 1
                                if include_uncategorized_var.get():
                                    # User opted in to include unfiltered stats
                                    if self._merge_detailed_stats(stats, ann_stats):
                                        found_any = True
                        else:
                            # All Categories: merge top-level stats as before
                            if self._merge_detailed_stats(stats, ann_stats):
                                found_any = True
                
                if not found_any:
                    empty_frame = ctk.CTkFrame(dash_container, fg_color="transparent")
                    empty_frame.pack(expand=True)
                    if getattr(self, 'is_global_syncing', False):
                        ctk.CTkLabel(empty_frame, text="⏳", font=ctk.CTkFont(size=60)).pack(pady=(0, 10))
                        ctk.CTkLabel(empty_frame, text="Syncing Team Data...", font=ctk.CTkFont(size=24, weight="bold"), text_color="#f39c12").pack(pady=(0, 5))
                        ctk.CTkLabel(empty_frame, text="Please wait while we fetch the latest metrics from GitHub.", font=ctk.CTkFont(size=14), text_color="#a6adc8").pack()
                    else:
                        ctk.CTkLabel(empty_frame, text="📭", font=ctk.CTkFont(size=60)).pack(pady=(0, 10))
                        ctk.CTkLabel(empty_frame, text="No Team Data Available", font=ctk.CTkFont(size=24, weight="bold"), text_color="#cdd6f4").pack(pady=(0, 5))
                        ctk.CTkLabel(empty_frame, text="Ensure Team Sync is configured, or choose an annotator with synced metrics.", font=ctk.CTkFont(size=14), text_color="#a6adc8").pack()
                        
                        last_err = getattr(self, 'last_sync_error', '')
                        if last_err:
                            ctk.CTkLabel(empty_frame, text=f"⚠️ Sync Failed: {last_err}", font=ctk.CTkFont(size=13, weight="bold"), text_color="#e74c3c").pack(pady=(10, 0))

                        def force_manual_sync():
                            self.last_sync_error = ""
                            self.is_global_syncing = True
                            self._queue_detailed_stats_redraw()
                            threading.Thread(target=self._sync_global_metrics_worker, daemon=True).start()
                            
                        sync_btn = ctk.CTkButton(empty_frame, text="↻ Manual Sync", command=force_manual_sync,
                                               width=120, height=32, font=ctk.CTkFont(size=13, weight="bold"),
                                               fg_color="#3498db", hover_color="#2980b9")
                        sync_btn.pack(pady=(15 if not last_err else 10, 0))
                    active_export_data = []
                    return
            else:
                # --- LOCAL METRICS MODE ---
                # Filter records
                filtered_records = self._filter_detailed_stats_records(
                    all_records, selected_category, selected_annotator
                )

                # --- EMPTY STATE ---
                if not filtered_records:
                    empty_frame = ctk.CTkFrame(dash_container, fg_color="transparent")
                    empty_frame.pack(expand=True)
                    ctk.CTkLabel(empty_frame, text="📭", font=ctk.CTkFont(size=60)).pack(pady=(0, 10))
                    ctk.CTkLabel(empty_frame, text="No Data Available", font=ctk.CTkFont(size=24, weight="bold"), text_color="#cdd6f4").pack(pady=(0, 5))
                    ctk.CTkLabel(empty_frame, text=f"No annotated items match the current filters.", font=ctk.CTkFont(size=14), text_color="#a6adc8").pack()
                    active_export_data = []
                    return

                stats = self._compute_detailed_stats_for_records(filtered_records)

            # --- PARTIAL DATA WARNING (global mode with category filter) ---
            if is_global and filtering_by_category and machines_without_categories > 0:
                warn_frame = ctk.CTkFrame(dash_container, fg_color="#3d2e1e", corner_radius=8,
                                          border_width=1, border_color="#e67e22")
                warn_frame.pack(fill="x", padx=24, pady=(10, 0))

                warn_inner = ctk.CTkFrame(warn_frame, fg_color="transparent")
                warn_inner.pack(fill="x", padx=12, pady=8)

                plural = "s" if machines_without_categories > 1 else ""
                excluded_text = "excluded" if not include_uncategorized_var.get() else "included (unfiltered)"
                ctk.CTkLabel(
                    warn_inner,
                    text=f"⚠️  {machines_without_categories} teammate{plural} don't have category data — {excluded_text}.",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#fab387"
                ).pack(side="left")

                def toggle_include_uncategorized():
                    include_uncategorized_var.set(not include_uncategorized_var.get())
                    draw_dashboard()

                btn_text = "Exclude Them" if include_uncategorized_var.get() else "Include Them"
                btn_color = "#e74c3c" if include_uncategorized_var.get() else "#4f46e5"
                btn_hover = "#c0392b" if include_uncategorized_var.get() else "#5c5cff"
                ctk.CTkButton(
                    warn_inner, text=btn_text, command=toggle_include_uncategorized,
                    width=120, height=26, font=ctk.CTkFont(size=12, weight="bold"),
                    fg_color=btn_color, hover_color=btn_hover, corner_radius=6
                ).pack(side="right", padx=(10, 0))

            # --- SUMMARY CARDS ---
            cards_frame = ctk.CTkFrame(dash_container, fg_color="transparent")
            cards_frame.pack(fill="x", padx=24, pady=(10, 20))
            cards_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="card")

            def create_card(parent, title, value, subtext, col, bg_color):
                c = ctk.CTkFrame(parent, fg_color=bg_color, corner_radius=12)
                c.grid(row=0, column=col, sticky="nsew", padx=8)
                ctk.CTkLabel(c, text=title, font=ctk.CTkFont(size=13, weight="bold"), text_color="#bac2de").pack(anchor="w", padx=16, pady=(10, 0))
                ctk.CTkLabel(c, text=str(value), font=ctk.CTkFont(size=28, weight="bold"), text_color="#ffffff").pack(anchor="w", padx=16, pady=(0, 0))
                ctk.CTkLabel(c, text=subtext, font=ctk.CTkFont(size=12), text_color="#a6adc8").pack(anchor="w", padx=16, pady=(0, 10))

            total_count = stats["Total"]["Total Items"]
            real_count = stats["Real"]["Total Items"]
            fake_count = stats["Fake"]["Total Items"]
            real_pct = int(real_count / total_count * 100) if total_count > 0 else 0
            fake_pct = int(fake_count / total_count * 100) if total_count > 0 else 0
            
            total_media = stats["Total"]["Total Images"] + stats["Total"]["Total Videos"]

            if is_global:
                create_card(cards_frame, "🌐 TEAM TOTAL ITEMS", total_count, "All annotators combined", 0, "#2c2c54")
                create_card(cards_frame, "Team Authenticity Split", f"{real_pct}% / {fake_pct}%", f"{real_count} Real, {fake_count} Fake", 1, "#2c2c54")
                create_card(cards_frame, "Team Total Media", total_media, f"{stats['Total']['Total Images']} Images, {stats['Total']['Total Videos']} Videos", 2, "#2c2c54")
            else:
                create_card(cards_frame, "Local Total Items", total_count, "Your annotated entries", 0, "#1e1e2e")
                create_card(cards_frame, "Local Authenticity Split", f"{real_pct}% / {fake_pct}%", f"{real_count} Real, {fake_count} Fake", 1, "#1e1e2e")
                create_card(cards_frame, "Local Total Media", total_media, f"{stats['Total']['Total Images']} Images, {stats['Total']['Total Videos']} Videos", 2, "#1e1e2e")

            # --- DETAILED GRID ---
            scroll = ctk.CTkScrollableFrame(dash_container, fg_color="#181825", corner_radius=16)
            scroll.pack(fill="both", expand=True, padx=24, pady=(0, 10))

            header_fg = "#181825"
            row_fg_even = "#1e1e2e"
            row_fg_odd = "#242436"
            hover_fg = "#313244"
            active_fg = "#4f46e5" 
            
            grid_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            grid_frame.pack(fill="x", expand=True, padx=2, pady=2)
            
            grid_frame.columnconfigure(0, weight=2, minsize=180)
            for c in range(1, 7):
                grid_frame.columnconfigure(c, weight=1, uniform="col_stat", minsize=100)
                
            headers = ["Modality / Metric", *DETAILED_STATS_COLUMNS]
            export_rows = self._detailed_stats_export_rows(stats)
            
            active_highlight_row = [None]
            active_highlight_col = [None]
            row_cells = {}
            row_labels = {}
            col_cells = {i: [] for i in range(7)}
            col_labels = {i: [] for i in range(7)}
            row_default_colors = {}
            label_default_colors = {}

            def clear_highlights():
                if active_highlight_row[0] is not None:
                    old_row = active_highlight_row[0]
                    for cell in row_cells[old_row]:
                        cell.configure(fg_color=row_default_colors[old_row])
                    for label in row_labels[old_row]:
                        if label_default_colors[label] == "HIDDEN_PCT":
                            label.configure(text="", text_color="#9399b2")
                        else:
                            label.configure(text_color=label_default_colors[label])
                    active_highlight_row[0] = None
                
                if active_highlight_col[0] is not None:
                    old_col = active_highlight_col[0]
                    for r_idx, cell in col_cells[old_col]:
                        cell.configure(fg_color=row_default_colors[r_idx])
                    for label in col_labels[old_col]:
                        if label_default_colors[label] == "HIDDEN_PCT":
                            label.configure(text="", text_color="#9399b2")
                        else:
                            label.configure(text_color=label_default_colors[label])
                    active_highlight_col[0] = None

            for col_idx, h_text in enumerate(headers):
                cell_frame = ctk.CTkFrame(grid_frame, fg_color=header_fg, corner_radius=0, border_width=0, cursor="hand2")
                cell_frame.grid(row=0, column=col_idx, sticky="nsew", pady=(0, 4))
                lbl = ctk.CTkLabel(cell_frame, text=h_text, font=ctk.CTkFont(size=13, weight="bold"), text_color="#cdd6f4")
                lbl.pack(padx=6, pady=12, expand=True)
                
                # Bind column click
                cell_frame.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))
                lbl.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))

            def on_enter(e, r):
                if active_highlight_row[0] != r and active_highlight_col[0] is None:
                    for cell in row_cells[r]:
                        cell.configure(fg_color=hover_fg)

            def on_leave(e, r):
                if active_highlight_row[0] != r and active_highlight_col[0] is None:
                    for cell in row_cells[r]:
                        cell.configure(fg_color=row_default_colors[r])

            def on_row_click(row_idx):
                if active_highlight_row[0] == row_idx:
                    clear_highlights()
                    for cell in row_cells[row_idx]:
                        cell.configure(fg_color=hover_fg)
                else:
                    clear_highlights()
                    for cell in row_cells[row_idx]:
                        cell.configure(fg_color=active_fg)
                    for label in row_labels[row_idx]:
                        if label_default_colors[label] == "HIDDEN_PCT":
                            h_text = getattr(label, '_stored_horizontal_text', '')
                            h_color = getattr(label, '_horizontal_highlight_color', '#bac2de')
                            label.configure(text=h_text, text_color=h_color)
                        elif label_default_colors[label] in ("#6c7086", "#9399b2"):
                            label.configure(text_color="#bac2de") 
                        else:
                            label.configure(text_color="#ffffff")
                    active_highlight_row[0] = row_idx
                    
            def on_col_click(col_idx):
                if active_highlight_col[0] == col_idx:
                    clear_highlights()
                else:
                    clear_highlights()
                    for r_idx, cell in col_cells[col_idx]:
                        cell.configure(fg_color=active_fg)
                    for label in col_labels[col_idx]:
                        if label_default_colors[label] == "HIDDEN_PCT":
                            v_text = getattr(label, '_stored_vertical_text', '')
                            v_color = getattr(label, '_vertical_highlight_color', '#bac2de')
                            label.configure(text=v_text, text_color=v_color)
                        elif label_default_colors[label] in ("#6c7086", "#9399b2"):
                            label.configure(text_color="#bac2de") 
                        else:
                            label.configure(text_color="#ffffff")
                    active_highlight_col[0] = col_idx
                
            metrics = [
                ("Total Items", "#89b4fa"),
                ("Text Only", "#f38ba8"),
                ("Image Only", "#fab387"),
                ("Video Only", "#fab387"),
                ("Text + Image", "#f9e2af"),
                ("Text + Video", "#f9e2af"),
                ("Image + Video", "#f9e2af"),
                ("Text + Image + Video", "#cba6f7")
            ]

            for row_idx, (metric_name, dot_color) in enumerate(metrics, start=1):
                bg_color = row_fg_even if row_idx % 2 == 0 else row_fg_odd
                row_cells[row_idx] = []
                row_labels[row_idx] = []
                row_default_colors[row_idx] = bg_color
                
                cell_frame = ctk.CTkFrame(grid_frame, fg_color=bg_color, corner_radius=6, border_width=0, cursor="hand2")
                cell_frame.grid(row=row_idx, column=0, sticky="nsew", padx=(0, 2), pady=1)
                row_cells[row_idx].append(cell_frame)
                col_cells[0].append((row_idx, cell_frame))
                
                inner = ctk.CTkFrame(cell_frame, fg_color="transparent")
                inner.pack(padx=16, pady=12, anchor="w")
                
                dot = ctk.CTkFrame(inner, width=10, height=10, corner_radius=5, fg_color=dot_color)
                dot.pack(side="left", padx=(0, 10))
                dot.pack_propagate(False)
                
                lbl_weight = "bold" if row_idx == 1 else "normal"
                lbl = ctk.CTkLabel(inner, text=metric_name, font=ctk.CTkFont(size=14, weight=lbl_weight), text_color="#f5e0dc")
                lbl.pack(side="left")
                row_labels[row_idx].append(lbl)
                col_labels[0].append(lbl)
                label_default_colors[lbl] = "#f5e0dc"

                for widget in (cell_frame, inner, dot, lbl):
                    widget.bind("<Button-1>", lambda e, r=row_idx: on_row_click(r))
                    widget.bind("<Enter>", lambda e, r=row_idx: on_enter(e, r))
                    widget.bind("<Leave>", lambda e, r=row_idx: on_leave(e, r))

                for col_idx, col_key in enumerate(["Total", "Real", "Fake", "Misinfo", "Satire", "Clickbait"], start=1):
                    is_last_col = (col_idx == 6)
                    val_cell_frame = ctk.CTkFrame(grid_frame, fg_color=bg_color, corner_radius=6 if is_last_col else 0, border_width=0, cursor="hand2")
                    val_cell_frame.grid(row=row_idx, column=col_idx, sticky="nsew", padx=(0, 0 if is_last_col else 2), pady=1)
                    row_cells[row_idx].append(val_cell_frame)
                    col_cells[col_idx].append((row_idx, val_cell_frame))
                    
                    val = stats[col_key][metric_name]
                    text_color = "#f5e0dc" if val > 0 else "#6c7086"
                    weight = "bold" if val > 0 or row_idx == 1 else "normal"
                    
                    inner_val_frame = ctk.CTkFrame(val_cell_frame, fg_color="transparent")
                    inner_val_frame.pack(expand=True, pady=12)
                    
                    v_lbl = ctk.CTkLabel(inner_val_frame, text=str(val), font=ctk.CTkFont(size=14, weight=weight), text_color=text_color)
                    v_lbl.pack(side="left")
                    row_labels[row_idx].append(v_lbl)
                    col_labels[col_idx].append(v_lbl)
                    label_default_colors[v_lbl] = text_color
                    
                    vertical_pct = None
                    horizontal_pct = None
                    if val > 0:
                        if row_idx > 1:
                            # --- Vertical Calculation (modality distribution) ---
                            v_denom = 0
                            
                            # Sum up all modality items for this column to ensure vertical percentages sum to 100%
                            # excluding items that have no text, image, or video.
                            modality_sum = sum(stats[col_key][m] for m in [
                                "Text Only", "Image Only", "Video Only", 
                                "Text + Image", "Text + Video", "Image + Video", 
                                "Text + Image + Video"
                            ])
                            
                            if col_key in ["Real", "Fake"]:
                                v_denom = modality_sum
                            elif col_key in ["Misinfo", "Satire", "Clickbait"]:
                                # For subclasses, we want their vertical sum to add up to 100% of their own modality sum
                                v_denom = modality_sum
                                
                            if v_denom > 0:
                                vertical_pct = int(round((val / v_denom) * 100))
                            
                        # --- Horizontal Calculation (runs for ALL rows including Total Items) ---
                        h_denom = 0
                        if col_key in ["Real", "Fake"]:
                            h_denom = stats["Total"][metric_name]
                        elif col_key in ["Misinfo", "Satire", "Clickbait"]:
                            h_denom = stats["Fake"][metric_name]
                            
                        if h_denom > 0:
                            horizontal_pct = int(round((val / h_denom) * 100))

                    pct_lbl = None
                    if vertical_pct is not None or horizontal_pct is not None:
                        v_text = f"({vertical_pct}%)" if vertical_pct is not None else ""
                        h_text = f"({horizontal_pct}%)" if horizontal_pct is not None else ""
                        # We initialize with text="" to hide it visually without crashing CTk
                        pct_lbl = ctk.CTkLabel(inner_val_frame, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="#9399b2")
                        pct_lbl._stored_vertical_text = v_text
                        pct_lbl._stored_horizontal_text = h_text
                        
                        pct_lbl._vertical_highlight_color = "#bac2de"
                        if col_key in ["Misinfo", "Satire", "Clickbait"]:
                            pct_lbl._horizontal_highlight_color = "#fab387" # Soft orange to differentiate
                        else:
                            pct_lbl._horizontal_highlight_color = "#bac2de"
                            
                        pct_lbl.pack(side="left", padx=(6, 0))
                        row_labels[row_idx].append(pct_lbl)
                        col_labels[col_idx].append(pct_lbl)
                        label_default_colors[pct_lbl] = "HIDDEN_PCT"

                    val_cell_frame.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))
                    val_cell_frame.bind("<Enter>", lambda e, r=row_idx: on_enter(e, r))
                    val_cell_frame.bind("<Leave>", lambda e, r=row_idx: on_leave(e, r))
                    inner_val_frame.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))
                    inner_val_frame.bind("<Enter>", lambda e, r=row_idx: on_enter(e, r))
                    inner_val_frame.bind("<Leave>", lambda e, r=row_idx: on_leave(e, r))
                    v_lbl.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))
                    v_lbl.bind("<Enter>", lambda e, r=row_idx: on_enter(e, r))
                    v_lbl.bind("<Leave>", lambda e, r=row_idx: on_leave(e, r))
                    if pct_lbl:
                        pct_lbl.bind("<Button-1>", lambda e, c=col_idx: on_col_click(c))
                        pct_lbl.bind("<Enter>", lambda e, r=row_idx: on_enter(e, r))
                        pct_lbl.bind("<Leave>", lambda e, r=row_idx: on_leave(e, r))
            
            active_export_data = export_rows

        def on_filter_change(*args):
            draw_dashboard()

        category_menu = ctk.CTkOptionMenu(top_frame, values=category_options, variable=category_var, command=on_filter_change, fg_color="#313244", button_color="#4f46e5", button_hover_color="#5c5cff", font=ctk.CTkFont(size=13, weight="bold"))
        category_menu.pack(side="left", padx=(0, 10))
        annotator_menu = ctk.CTkOptionMenu(top_frame, values=annotator_options, variable=annotator_var, command=on_filter_change, fg_color="#313244", button_color="#4f46e5", button_hover_color="#5c5cff", font=ctk.CTkFont(size=13, weight="bold"))
        annotator_menu.pack(side="left")

        def export_csv():
            is_global_export = self.global_metrics_enabled.get()
            export_all_categories = False

            if not is_global_export:
                export_choice = self._ask_detailed_stats_export_scope(popup)
                if export_choice is None:
                    return
                export_all_categories = (export_choice == "all")

            selected_annotator = annotator_var.get()

            if export_all_categories:
                scoped_records = self._filter_detailed_stats_records(
                    all_records, "All Categories", selected_annotator
                )
                if not scoped_records:
                    messagebox.showinfo("Export", "No local data to export.", parent=popup)
                    return

                present_categories = {
                    (r.get("category") or "").strip()
                    for r in scoped_records
                    if (r.get("category") or "").strip()
                }
                preferred_categories = [c for c in CATEGORIES if c in present_categories]
                extra_categories = sorted(present_categories - set(preferred_categories))
                categories_to_export = ["All Categories"] + preferred_categories + extra_categories
                initialfile = "detailed_statistics_all_categories.csv"
            else:
                if not active_export_data:
                    messagebox.showinfo("Export", "No data to export.", parent=popup)
                    return
                initialfile = "detailed_statistics_current.csv"
            
            filepath = filedialog.asksaveasfilename(
                parent=popup,
                defaultextension=".csv",
                initialfile=initialfile,
                title="Save Detailed Statistics as CSV",
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
            )
            if filepath:
                try:
                    with open(filepath, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Scope", "Team" if is_global_export else "Local"])
                        writer.writerow(["Export", "All Categories" if export_all_categories else "Current Dashboard"])
                        writer.writerow(["Category", "All Categories" if export_all_categories else category_var.get()])
                        writer.writerow(["Annotator", selected_annotator])
                        writer.writerow([])

                        if export_all_categories:
                            for cat in categories_to_export:
                                if cat == "All Categories":
                                    category_records = scoped_records
                                else:
                                    category_records = self._filter_detailed_stats_records(
                                        scoped_records, cat, "All Annotators"
                                    )
                                if not category_records:
                                    continue

                                category_stats = self._compute_detailed_stats_for_records(category_records)
                                writer.writerow([f"=== CATEGORY: {cat.upper()} ==="])
                                writer.writerows(self._detailed_stats_export_rows(category_stats))
                                writer.writerow([])
                        else:
                            writer.writerows(active_export_data)
                            
                    messagebox.showinfo("Success", f"Statistics successfully exported to:\n{filepath}", parent=popup)
                except Exception as e:
                    messagebox.showerror("Export Failed", f"An error occurred while saving:\n{e}", parent=popup)

        # Bottom Frame
        bottom_frame = ctk.CTkFrame(popup, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=24, pady=(0, 24))

        ctk.CTkButton(bottom_frame, text="Close", command=popup.destroy,
                       height=40, font=ctk.CTkFont(size=14, weight="bold"),
                       fg_color="transparent", border_width=1,
                       border_color="#555", width=120).pack(side="right", padx=(10, 0))
                       
        ctk.CTkButton(bottom_frame, text="📥 Export to CSV", command=export_csv,
                       height=40, font=ctk.CTkFont(size=14, weight="bold"),
                       fg_color="#313244", hover_color="#45475a", width=140).pack(side="right")

        # Initial draw
        popup.redraw_cmd = draw_dashboard
        draw_dashboard()

    def _on_global_toggle_change(self):
        # Refresh the stats view
        self._update_stats()

    def _compute_metrics_for_subset(self, records):
        total_items = 0
        total_images = 0
        total_videos = 0
        text_only = 0
        image_only = 0
        video_only = 0
        text_image = 0
        text_video = 0
        image_video = 0
        text_image_video = 0

        for r in records:
            total_items += 1
            ip = (r.get("image_path") or "").strip()
            img_list = [p for p in ip.split(";") if p.strip()]
            total_images += len(img_list)
            
            vp = (r.get("video_path") or "").strip()
            has_video = bool(vp)
            if has_video:
                total_videos += 1
                
            t_content = (r.get("text") or "").strip()
            h_content = (r.get("heading") or "").strip()
            has_text = (len(t_content) + len(h_content)) >= MIN_TEXT_LENGTH
            
            has_image = bool(img_list)
            
            if has_text and not has_image and not has_video:
                text_only += 1
            elif not has_text and has_image and not has_video:
                image_only += 1
            elif not has_text and not has_image and has_video:
                video_only += 1
            elif has_text and has_image and not has_video:
                text_image += 1
            elif has_text and not has_image and has_video:
                text_video += 1
            elif not has_text and has_image and has_video:
                image_video += 1
            elif has_text and has_image and has_video:
                text_image_video += 1

        return {
            "Total Items": total_items,
            "Total Images": total_images,
            "Total Videos": total_videos,
            "Text Only": text_only,
            "Image Only": image_only,
            "Video Only": video_only,
            "Text + Image": text_image,
            "Text + Video": text_video,
            "Image + Video": image_video,
            "Text + Image + Video": text_image_video
        }

    def _empty_detailed_stats(self):
        return {
            col_name: {metric_name: 0 for metric_name in DETAILED_STATS_METRICS}
            for col_name in DETAILED_STATS_COLUMNS
        }

    def _compute_detailed_stats_for_records(self, records):
        subsets = {
            "Total": records,
            "Real": [r for r in records if (r.get("label") or "").strip() == "Real"],
            "Fake": [r for r in records if (r.get("label") or "").strip() == "Fake"],
            "Misinfo": [r for r in records if (r.get("label") or "").strip() == "Fake" and (r.get("multi_category") or "").strip() == "Misinformation"],
            "Satire": [r for r in records if (r.get("label") or "").strip() == "Fake" and (r.get("multi_category") or "").strip() == "Satire"],
            "Clickbait": [r for r in records if (r.get("label") or "").strip() == "Fake" and (r.get("multi_category") or "").strip() == "Clickbait"]
        }
        return {
            col_name: self._compute_metrics_for_subset(subset)
            for col_name, subset in subsets.items()
        }

    def _merge_detailed_stats(self, target, source):
        if not isinstance(source, dict):
            return False

        recognized = False
        for col_name in DETAILED_STATS_COLUMNS:
            subset_metrics = source.get(col_name)
            if not isinstance(subset_metrics, dict):
                continue
            recognized = True
            for metric_name in DETAILED_STATS_METRICS:
                try:
                    target[col_name][metric_name] += int(subset_metrics.get(metric_name, 0) or 0)
                except (TypeError, ValueError):
                    continue
        # Note: _categories key is intentionally skipped here — it's a nested
        # dict of per-category stats, not a stats column to merge.
        return recognized

    def _redraw_active_detailed_popup(self):
        popup = getattr(self, "active_detailed_popup", None)
        if popup is None:
            return
        try:
            if popup.winfo_exists() and hasattr(popup, "redraw_cmd"):
                popup.redraw_cmd()
        except tk.TclError:
            pass

    def _queue_detailed_stats_redraw(self):
        try:
            self.after(0, self._redraw_active_detailed_popup)
        except tk.TclError:
            pass

    def _calculate_grouped_local_stats(self):
        """
        Reads dataset.csv and groups detailed metrics by annotator name.
        Also computes per-category breakdowns under a '_categories' key
        for each annotator, enabling category filtering in global metrics.
        """
        grouped_records = {}
        grouped_by_cat = {}  # (annotator, category) -> [rows]
        if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
            return {}
        
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ann = (row.get("annotator") or "").strip() or "Unknown"
                cat = (row.get("category") or "").strip() or "_uncategorized"
                
                if ann not in grouped_records:
                    grouped_records[ann] = []
                grouped_records[ann].append(row)
                
                key = (ann, cat)
                if key not in grouped_by_cat:
                    grouped_by_cat[key] = []
                grouped_by_cat[key].append(row)
                
        result = {}
        for ann, records in grouped_records.items():
            # Top-level stats (backward compatible — kept as-is)
            ann_stats = self._compute_detailed_stats_for_records(records)
            # Per-category breakdown
            categories_stats = {}
            for (a, cat), cat_records in grouped_by_cat.items():
                if a == ann:
                    categories_stats[cat] = self._compute_detailed_stats_for_records(cat_records)
            ann_stats["_categories"] = categories_stats
            result[ann] = ann_stats
        
        return result

