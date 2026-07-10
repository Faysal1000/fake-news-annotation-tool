"""
DuplicateUIMixin mixin class.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk, ImageDraw
import subprocess
import os
import platform
import sys
import math
from pathlib import Path
from app_paths import SCRIPT_DIR
from constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from analysis.text_similarity import calculate_jaccard_similarity, clean_text, find_matching_word_ranges, get_words_with_positions

def _get_slashed_eye_icon(color="#f39c12"):
    try:
        img = Image.new("RGBA", (32, 32), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        # Upper/lower eye lids
        draw.arc([4, 8, 28, 24], 190, 350, fill=color, width=2)
        draw.arc([4, 8, 28, 24], 10, 170, fill=color, width=2)
        # Pupil
        draw.ellipse([13, 13, 19, 19], fill=color)
        # Slash
        draw.line([6, 6, 26, 26], fill=color, width=2)
        return ctk_image_helper(img)
    except Exception:
        return None

def _get_refresh_icon(color="#e74c3c"):
    try:
        img = Image.new("RGBA", (32, 32), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        # Circular arc
        draw.arc([6, 6, 26, 26], 40, 320, fill=color, width=3)
        # Arrow head at angle 320
        rad = 320 * math.pi / 180
        r = 10
        cx, cy = 16, 16
        x = cx + r * math.cos(rad)
        y = cy + r * math.sin(rad)
        # Draw arrow segments
        draw.line([x, y, x - 5, y + 1], fill=color, width=3)
        draw.line([x, y, x + 1, y - 5], fill=color, width=3)
        return ctk_image_helper(img)
    except Exception:
        return None

def _get_close_icon(color="#fff"):
    try:
        img = Image.new("RGBA", (32, 32), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        # Draw "X" cross
        draw.line([8, 8, 24, 24], fill=color, width=3)
        draw.line([24, 8, 8, 24], fill=color, width=3)
        return ctk_image_helper(img)
    except Exception:
        return None

def ctk_image_helper(img):
    import customtkinter as ctk
    return ctk.CTkImage(light_image=img, dark_image=img, size=(16, 16))

class DuplicateUIMixin:
    def _show_review_duplicates(self):
        """
        Opens a popup dialog showing the list of potential duplicates in Review Mode.
        """
        if self.current_mode != "review" or not self.dataset_records:
            return
            
        matches = getattr(self, '_current_record_matches', [])
        if not matches:
            messagebox.showinfo("Duplicate Verification", "Duplicate calculation is still running in the background or no duplicates exist.")
            return
            
        popup = ctk.CTkToplevel(self)
        popup.title(f"Possible Duplications - Instance #{self.current_review_index + 1}")
        w, h = 800, 500
        popup.configure(fg_color="#1a1a2e")
        popup.attributes("-topmost", True)
        # Center on screen
        popup.update_idletasks()
        sx = (popup.winfo_screenwidth() - w) // 2
        sy = (popup.winfo_screenheight() - h) // 2
        popup.geometry(f"{w}x{h}+{sx}+{sy}")
        
        # Header
        header_frame = ctk.CTkFrame(popup, fg_color="#2b2b36", height=50, corner_radius=0)
        header_frame.pack(fill="x", side="top")
        
        ctk.CTkLabel(
            header_frame,
            text=f"⚠️ Duplicates Found for Record #{self.current_review_index + 1}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#f39c12"
        ).pack(pady=10, padx=20)
        
        # Scrollable list of matches
        scroll_frame = ctk.CTkScrollableFrame(popup, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        for match in matches:
            row_num = match["row_num"]
            sim = match["similarity"]
            combined_sim = match.get("combined_sim", 0)
            heading_sim = match.get("heading_sim", 0)
            
            sim_pct = int(sim * 100)
            
            # -- Card row --
            row_frame = ctk.CTkFrame(scroll_frame, fg_color="#2b2b36", corner_radius=8,
                                      border_width=1, border_color="#444")
            row_frame.pack(fill="x", pady=4, ipady=6)
            
            # Instance number badge
            badge_color = "#e74c3c" if sim_pct >= 80 else ("#f39c12" if sim_pct >= 60 else "#3498db")
            badge = ctk.CTkLabel(
                row_frame, text=f" #{row_num} ",
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color=badge_color, corner_radius=6,
                text_color="white", width=50
            )
            badge.pack(side="left", padx=(10, 8), pady=6)
            
            # Match info text
            text_sim = match.get("text_sim", 0.0)
            info_text = f"{sim_pct}% match  ·  Head+Body: {int(combined_sim*100)}%  ·  Heading: {int(heading_sim*100)}%  ·  Text: {int(text_sim*100)}%"
            ctk.CTkLabel(
                row_frame, text=info_text,
                font=ctk.CTkFont(size=12),
                text_color="#ccc", anchor="w"
            ).pack(side="left", fill="x", expand=True, padx=(0, 8))
            
            # Inspect button
            ctk.CTkButton(
                row_frame, text="🔍 Inspect", width=90, height=28,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#6c5ce7", hover_color="#5a4bd1",
                corner_radius=6,
                command=lambda m=match: self._view_duplicate_details(m)
            ).pack(side="right", padx=(0, 10), pady=6)
            
        # Close Button (centered)
        ctk.CTkButton(
            popup,
            text="Close",
            width=120,
            command=popup.destroy,
            fg_color="#34495e",
            hover_color="#2c3e50"
        ).pack(pady=15)

    def _show_global_duplicate_audit(self, start_page=0):
        page = start_page
        if not hasattr(self, '_duplicate_pairs_cache'):
            self._duplicate_pairs_cache = None
        if not hasattr(self, '_raw_duplicate_pairs_cache'):
            self._raw_duplicate_pairs_cache = None
            
        thread_alive = hasattr(self, '_duplicate_thread') and self._duplicate_thread is not None and self._duplicate_thread.is_alive()
        if hasattr(self, '_duplicate_computing') and self._duplicate_computing and not thread_alive:
            self._duplicate_computing = False
            
        cache_is_missing = self._duplicate_pairs_cache is None
        is_computing = hasattr(self, '_duplicate_computing') and self._duplicate_computing
        
        if cache_is_missing and not is_computing:
            self._duplicate_computing = True
            is_computing = True
            self._current_duplicate_progress = 0.0
            self.after(500, self._compute_global_duplicates)
            
        if cache_is_missing and not is_computing:
            self._duplicate_pairs_cache = []
            self._raw_duplicate_pairs_cache = []
            
        popup = ctk.CTkToplevel(self)
        popup.title("Global Duplicate Audit")
        w, h = 1000, 700
        popup.configure(fg_color="#1a1a2e")
        popup.transient(self)
        
        popup.update_idletasks()
        sx = (popup.winfo_screenwidth() - w) // 2
        sy = (popup.winfo_screenheight() - h) // 2
        popup.geometry(f"{w}x{h}+{sx}+{sy}")
        
        # Centered Header (Always visible)
        header_frame = ctk.CTkFrame(popup, fg_color="#2b2b36", height=60, corner_radius=0)
        header_frame.pack(side="top", fill="x")
        
        header_inner = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_inner.pack(fill="both", expand=True)
        
        marked_count = len(self._raw_duplicate_pairs_cache or []) - len(self._duplicate_pairs_cache or [])
        use_mp = self._get_duplicate_multiprocessing()
        current_progress = getattr(self, '_current_duplicate_progress', 0.0)
        
        if is_computing:
            if current_progress > 0.0:
                pct = int(current_progress * 100)
                header_title = f"🔄 Recalculating duplicates... {pct}%"
            else:
                header_title = "🚀 Initializing multi-core workers..." if use_mp else "⏳ Calculating duplicates..."
        else:
            header_title = f"⚠️ {len(self._duplicate_pairs_cache or []):,} Potential Duplicates ({marked_count} marked as non-duplicate)"
            
        title_label = ctk.CTkLabel(
            header_inner,
            text=header_title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#f39c12"
        )
        title_label.pack(side="top", expand=True, pady=12)
        
        # Main content area split into 4:1 layout
        content_frame = ctk.CTkFrame(popup, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)

        left_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        left_frame.pack(side="left", fill="both", expand=True, padx=(20, 10), pady=15)
        
        sidebar_frame = ctk.CTkFrame(content_frame, fg_color="#2b2b36", width=220, corner_radius=8)
        sidebar_frame.pack_propagate(False)
        sidebar_frame.pack(side="right", fill="y", padx=(10, 20), pady=15)
        
        # Sidebar Controls Title
        sidebar_title_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
        sidebar_title_frame.pack(fill="x", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(
            sidebar_title_frame, text="⚙️ Controls",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#fff"
        ).pack(side="left")
        
        separator = ctk.CTkFrame(sidebar_frame, fg_color="#3e3e4a", height=2, corner_radius=0)
        separator.pack(fill="x", padx=15, pady=(0, 15))
        
        # Define in-place helper functions
        def run_in_place_recompute():
            self._duplicate_pairs_cache = None
            self._raw_duplicate_pairs_cache = None
            self._cached_records_data = None
            self._cached_inverted_index = None
            self._compute_global_duplicates(force_restart=True)
            
            # Clear left_frame
            for w in left_frame.winfo_children():
                w.destroy()
                
            self._duplicate_popup_lbl = ctk.CTkLabel(
                left_frame, text="⏳ Initializing computation...\nPlease wait.",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color="#f39c12"
            )
            self._duplicate_popup_lbl.place(relx=0.5, rely=0.45, anchor="center")
            
            self._duplicate_popup_pb = ctk.CTkProgressBar(left_frame, width=300, fg_color="#2b2b36", progress_color="#f39c12")
            self._duplicate_popup_pb.place(relx=0.5, rely=0.55, anchor="center")
            self._duplicate_popup_pb.set(0.0)
            
            # Reset title to calculating
            title_label.configure(text="🔄 Recalculating duplicates...")
            
            check_computing()

        def check_computing():
            if hasattr(self, '_duplicate_computing') and self._duplicate_computing:
                if popup.winfo_exists():
                    curr_prog = getattr(self, '_current_duplicate_progress', 0.0)
                    if hasattr(self, '_duplicate_popup_pb') and self._duplicate_popup_pb.winfo_exists():
                        self._duplicate_popup_pb.set(curr_prog)
                    if hasattr(self, '_duplicate_popup_lbl') and self._duplicate_popup_lbl.winfo_exists():
                        pct = int(curr_prog * 100)
                        self._duplicate_popup_lbl.configure(text=f"🔄 Recalculating duplicates... {pct}%\nPlease wait.")
                    popup.after(200, check_computing)
            else:
                if popup.winfo_exists():
                    # Clear loading widgets
                    for w in left_frame.winfo_children():
                        w.destroy()
                    # Rebuild results view
                    non_dups_count = len(self._load_non_duplicates())
                    marked_count = len(self._raw_duplicate_pairs_cache or []) - len(self._duplicate_pairs_cache or [])
                    title_label.configure(text=f"⚠️ {len(self._duplicate_pairs_cache or []):,} Potential Duplicates ({marked_count} marked as non-duplicate)")
                    
                    # Update dynamically
                    update_show_marked_label()
                    rebuild_unmark_btn()
                    build_results_view(0)

        unmark_btn_widget = [None]
        unmark_sub_widget = [None]
        
        def rebuild_unmark_btn():
            # Clear existing if any
            if unmark_btn_widget[0] is not None:
                try:
                    unmark_btn_widget[0].destroy()
                except Exception:
                    pass
                unmark_btn_widget[0] = None
            if unmark_sub_widget[0] is not None:
                try:
                    unmark_sub_widget[0].destroy()
                except Exception:
                    pass
                unmark_sub_widget[0] = None
                
            is_comp = hasattr(self, '_duplicate_computing') and self._duplicate_computing
            if not is_comp and show_marked_var.get() and self._load_non_duplicates():
                btn = ctk.CTkButton(
                    sidebar_frame, text="Unmark All", width=190, height=32,
                    image=_get_slashed_eye_icon("#f39c12"),
                    font=ctk.CTkFont(size=12, weight="bold"),
                    fg_color="transparent", border_color="#f39c12", border_width=1,
                    text_color="#f39c12", hover_color="#2c2c36",
                    corner_radius=6,
                    command=lambda: [self._unmark_all_non_duplicates(), rebuild_unmark_btn(), update_show_marked_label(), build_results_view(0)]
                )
                btn._image_label_spacing = 6
                btn.pack(fill="x", padx=15, pady=(5, 2))
                unmark_btn_widget[0] = btn
                
                sub = ctk.CTkLabel(
                    sidebar_frame, text="Remove non-duplicate marks from all items.",
                    font=ctk.CTkFont(size=9), text_color="#888", wraplength=190, justify="left"
                )
                sub.pack(anchor="w", padx=15, pady=(0, 10))
                unmark_sub_widget[0] = sub

        def update_show_marked_label():
            non_dups_count = len(self._load_non_duplicates())
            checkbox_text = f"Show Marked ({non_dups_count})" if non_dups_count > 0 else "Show Marked"
            show_marked_cb.configure(text=checkbox_text)

        def build_results_view(page):
            # Clear left_frame
            for w in left_frame.winfo_children():
                w.destroy()
                
            cache_to_show = (self._raw_duplicate_pairs_cache if show_marked_var.get() else self._duplicate_pairs_cache) or []
            
            PAGE_SIZE = 50
            total_pages = max(1, (len(cache_to_show) + PAGE_SIZE - 1) // PAGE_SIZE)
            page = max(0, min(page, total_pages - 1))
            
            # Pagination controls at bottom of left_frame
            pagination_frame = ctk.CTkFrame(left_frame, fg_color="transparent", height=40)
            pagination_frame.pack(side="bottom", fill="x", pady=(10, 0), padx=10)
            
            def go_prev():
                if page > 0:
                    build_results_view(page - 1)
                    
            def go_next():
                if page < total_pages - 1:
                    build_results_view(page + 1)
            
            prev_btn = ctk.CTkButton(pagination_frame, text="◀ Prev", width=80, state="normal" if page > 0 else "disabled", command=go_prev)
            prev_btn.pack(side="left")
            
            ctk.CTkLabel(pagination_frame, text=f"Page {page + 1} of {total_pages}", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", expand=True)
            
            next_btn = ctk.CTkButton(pagination_frame, text="Next ▶", width=80, state="normal" if page < total_pages - 1 else "disabled", command=go_next)
            next_btn.pack(side="right")
            
            # Scrollable list of matches
            scroll_frame = ctk.CTkScrollableFrame(left_frame, fg_color="transparent")
            scroll_frame.pack(side="top", fill="both", expand=True, padx=10, pady=(5, 0))
            
            if not cache_to_show:
                empty_msg = "No duplicates found at the current threshold."
                if not show_marked_var.get() and len(self._raw_duplicate_pairs_cache) > 0:
                    empty_msg = "All duplicates have been marked as Non-Duplicate.\nCheck 'Show Marked' to view them."
                    
                ctk.CTkLabel(
                    scroll_frame, text=empty_msg,
                    font=ctk.CTkFont(size=14, slant="italic"),
                    text_color="#888"
                ).pack(pady=40)
                return
            
            for pair in cache_to_show[page * PAGE_SIZE : min((page + 1) * PAGE_SIZE, len(cache_to_show))]:
                idx_a = pair["idx_a"]
                idx_b = pair["idx_b"]
                sim = pair["similarity"]
                combined_sim = pair["combined_sim"]
                heading_sim = pair["heading_sim"]
                text_sim = pair.get("text_sim", 0.0)
                
                sim_pct = int(sim * 100)
                
                # -- Card row --
                row_frame = ctk.CTkFrame(scroll_frame, fg_color="#1e1e28", corner_radius=8,
                                          border_width=1, border_color="#2a2a3a")
                row_frame.pack(fill="x", pady=5, ipady=6)
                
                # Badges for both records
                badge_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
                badge_frame.pack(side="left", padx=(10, 10), pady=6)
                
                color_a = "#e74c3c" if sim_pct >= 80 else ("#f39c12" if sim_pct >= 60 else "#3498db")
                
                badge_a = ctk.CTkLabel(
                    badge_frame, text=f" #{idx_a + 1} ",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    fg_color=color_a, corner_radius=6,
                    text_color="white", width=50, height=26
                )
                badge_a.pack(side="left", padx=2)
                
                ctk.CTkLabel(badge_frame, text="↔", font=ctk.CTkFont(size=14, weight="bold"), text_color="#aaa").pack(side="left", padx=4)
                
                badge_b = ctk.CTkLabel(
                    badge_frame, text=f" #{idx_b + 1} ",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    fg_color=color_a, corner_radius=6,
                    text_color="white", width=50, height=26
                )
                badge_b.pack(side="left", padx=2)
                
                # Large bold green match percent
                match_pct_lbl = ctk.CTkLabel(
                    row_frame, text=f"{sim_pct}%\nmatch",
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color="#2ecc71", width=80
                )
                match_pct_lbl.pack(side="left", padx=(5, 10))
                
                # Action buttons frame (Compare + Not Duplicate side-by-side, no status outline)
                # Pack this SIDE="RIGHT" FIRST so it stays pinned to the absolute right side
                actions_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
                actions_frame.pack(side="right", padx=(0, 15), pady=6)
                
                # Stacked metric columns (Pack side="left" with expand=True so card takes full width)
                metrics_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
                metrics_frame.pack(side="left", fill="both", expand=True, padx=(5, 10))
                
                def add_metric_col(parent, label, value):
                    col = ctk.CTkFrame(parent, fg_color="transparent")
                    col.pack(side="left", padx=6)
                    ctk.CTkLabel(col, text=label, font=ctk.CTkFont(size=10), text_color="#888").pack(anchor="center")
                    ctk.CTkLabel(col, text=value, font=ctk.CTkFont(size=12, weight="bold"), text_color="#fff").pack(anchor="center")
                    
                add_metric_col(metrics_frame, "Head+Body", f"{int(combined_sim*100)}%")
                add_metric_col(metrics_frame, "Heading", f"{int(heading_sim*100)}%")
                add_metric_col(metrics_frame, "Text", f"{int(text_sim*100)}%")
                
                # Compare button
                ctk.CTkButton(
                    actions_frame, text="🔍 Compare", width=90, height=28,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    fg_color="#6c5ce7", hover_color="#5a4bd1",
                    corner_radius=6,
                    command=lambda p=pair: self._show_side_by_side_comparison(
                        p["record_a"], p["record_b"], p, parent_popup=popup,
                        on_mark_change_callback=lambda: [build_results_view(page)]
                    )
                ).pack(side="right", padx=(6, 0))
    
                # Not Duplicate / Restore button
                non_dups = self._load_non_duplicates()
                id_a_str = str(pair["record_a"].get("id", ""))
                id_b_str = str(pair["record_b"].get("id", ""))
                pair_key = f"{min(id_a_str, id_b_str)}_{max(id_a_str, id_b_str)}"
                is_marked = pair_key in non_dups
                
                if is_marked:
                    ctk.CTkButton(
                        actions_frame, text="Restore", width=80, height=28,
                        font=ctk.CTkFont(size=11, weight="bold"),
                        fg_color="#e67e22", hover_color="#d35400",
                        corner_radius=6,
                        command=lambda p=pair: [
                            self._unmark_as_non_duplicate(p["record_a"], p["record_b"]),
                            update_show_marked_label(),
                            rebuild_unmark_btn(),
                            title_label.configure(text=f"⚠️ {len(self._duplicate_pairs_cache or []):,} Potential Duplicates ({len(self._raw_duplicate_pairs_cache or []) - len(self._duplicate_pairs_cache or [])} marked as non-duplicate)"),
                            build_results_view(page)
                        ]
                    ).pack(side="right")
                else:
                    ctk.CTkButton(
                        actions_frame, text="Not Dup ❓", width=90, height=28,
                        font=ctk.CTkFont(size=11, weight="bold"),
                        fg_color="#27ae60", hover_color="#2ecc71",
                        corner_radius=6,
                        command=lambda p=pair: [
                            self._mark_as_non_duplicate(p["record_a"], p["record_b"]),
                            update_show_marked_label(),
                            rebuild_unmark_btn(),
                            title_label.configure(text=f"⚠️ {len(self._duplicate_pairs_cache or []):,} Potential Duplicates ({len(self._raw_duplicate_pairs_cache or []) - len(self._duplicate_pairs_cache or [])} marked as non-duplicate)"),
                            build_results_view(page)
                        ]
                    ).pack(side="right")

        # Multi-core Toggle
        multicore_var = ctk.BooleanVar(value=self._get_duplicate_multiprocessing())
        def toggle_multicore():
            self._save_duplicate_multiprocessing(multicore_var.get())
            run_in_place_recompute()
            
        multicore_cb = ctk.CTkCheckBox(
            sidebar_frame, text="Use Multi-core", variable=multicore_var,
            command=toggle_multicore, font=ctk.CTkFont(size=12, weight="bold")
        )
        multicore_cb.pack(anchor="w", padx=15, pady=(5, 2))
        
        multicore_sub = ctk.CTkLabel(
            sidebar_frame, text="Enable multi-core processing for faster results.",
            font=ctk.CTkFont(size=10), text_color="#888", wraplength=190, justify="left"
        )
        multicore_sub.pack(anchor="w", padx=15, pady=(0, 10))
        
        # Threshold Settings
        thresh_lbl = ctk.CTkLabel(
            sidebar_frame, text="Threshold (%):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ccc"
        )
        thresh_lbl.pack(anchor="w", padx=15, pady=(10, 2))
        
        thresh_entry_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
        thresh_entry_frame.pack(fill="x", padx=15, pady=(0, 4))
        
        thresh_var = ctk.StringVar(value=str(self._get_duplicate_threshold()))
        thresh_entry = ctk.CTkEntry(
            thresh_entry_frame, textvariable=thresh_var,
            height=28, font=ctk.CTkFont(size=12)
        )
        thresh_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        def save_threshold():
            try:
                val = int(thresh_var.get().strip())
                if 1 <= val <= 100:
                    old_val = self._get_duplicate_threshold()
                    self._save_duplicate_threshold(val)
                    if val != old_val:
                        run_in_place_recompute()
                else:
                    messagebox.showerror("Error", "Threshold must be between 1 and 100.")
            except ValueError:
                messagebox.showerror("Error", "Invalid threshold value.")
                
        save_btn = ctk.CTkButton(
            thresh_entry_frame, text="Save", height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#2980b9", hover_color="#3498db",
            command=save_threshold
        )
        save_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        thresh_sub = ctk.CTkLabel(
            sidebar_frame, text="Show potential duplicates with match % equal to or above the threshold.",
            font=ctk.CTkFont(size=9), text_color="#888", wraplength=190, justify="left"
        )
        thresh_sub.pack(anchor="w", padx=15, pady=(0, 10))
        
        # Show Marked Toggle
        show_marked_var = ctk.BooleanVar(value=getattr(self, "_show_marked_duplicates", False))
        def toggle_show_marked():
            self._show_marked_duplicates = show_marked_var.get()
            rebuild_unmark_btn()
            build_results_view(0)
            
        non_dups_count = len(self._load_non_duplicates())
        checkbox_text = f"Show Marked ({non_dups_count})" if non_dups_count > 0 else "Show Marked"
        
        show_marked_cb = ctk.CTkCheckBox(
            sidebar_frame, text=checkbox_text, variable=show_marked_var,
            command=toggle_show_marked, font=ctk.CTkFont(size=12, weight="bold")
        )
        show_marked_cb.pack(anchor="w", padx=15, pady=(10, 2))
        
        show_marked_sub = ctk.CTkLabel(
            sidebar_frame, text="Display items marked as non-duplicate.",
            font=ctk.CTkFont(size=10), text_color="#888", wraplength=190, justify="left"
        )
        show_marked_sub.pack(anchor="w", padx=15, pady=(0, 15))
        
        # Force Recalc Button (Bordered red button, full width)
        def force_recompute():
            run_in_place_recompute()
 
        force_btn = ctk.CTkButton(
            sidebar_frame, text="Force Recalc", width=190, height=32,
            image=_get_refresh_icon("#e74c3c"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="transparent", border_color="#e74c3c", border_width=1,
            text_color="#e74c3c", hover_color="#2c2c36",
            corner_radius=6,
            command=force_recompute
        )
        force_btn._image_label_spacing = 6
        force_btn.pack(fill="x", padx=15, pady=(5, 2))
        
        force_sub = ctk.CTkLabel(
            sidebar_frame, text="Recalculate all comparisons.",
            font=ctk.CTkFont(size=10), text_color="#888", wraplength=190, justify="left"
        )
        force_sub.pack(anchor="w", padx=15, pady=(0, 15))
 
        # Close button at the bottom of controls sidebar
        close_btn = ctk.CTkButton(
            sidebar_frame,
            text="Close",
            image=_get_close_icon("#fff"),
            width=190, height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=popup.destroy,
            fg_color="#34495e",
            hover_color="#2c3e50"
        )
        close_btn._image_label_spacing = 6
        close_btn.pack(side="bottom", fill="x", padx=15, pady=15)
        
        # Populate initial view
        rebuild_unmark_btn()
        
        # Check if loading screen is needed
        if cache_is_missing or is_computing:
            if is_computing:
                if current_progress > 0.0:
                    pct = int(current_progress * 100)
                    loading_text = f"🔄 Recalculating duplicates... {pct}%\nPlease wait."
                else:
                    loading_text = "🚀 Initializing multi-core workers...\nPlease wait." if use_mp else "⏳ Calculating duplicates...\nPlease wait."
            else:
                loading_text = "🚀 Initializing multi-core workers...\nPlease wait." if use_mp else "⏳ Calculating duplicates...\nPlease wait."
                
            self._duplicate_popup_lbl = ctk.CTkLabel(
                left_frame, text=loading_text,
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color="#f39c12"
            )
            self._duplicate_popup_lbl.place(relx=0.5, rely=0.45, anchor="center")
            
            self._duplicate_popup_pb = ctk.CTkProgressBar(left_frame, width=300, fg_color="#2b2b36", progress_color="#f39c12")
            self._duplicate_popup_pb.place(relx=0.5, rely=0.55, anchor="center")
            self._duplicate_popup_pb.set(current_progress)
            
            check_computing()
        else:
            build_results_view(page)
        


    def _show_side_by_side_comparison(self, record_a, record_b, pair_info, parent_popup=None, on_mark_change_callback=None):
        popup = ctk.CTkToplevel(parent_popup if parent_popup else self)
        popup.title("Side-by-Side Comparison")
        w, h = 1100, 680
        popup.configure(fg_color="#1a1a2e")
        if parent_popup:
            popup.transient(parent_popup)
        else:
            popup.transient(self)
        
        # Center on screen
        popup.update_idletasks()
        sx = (popup.winfo_screenwidth() - w) // 2
        sy = (popup.winfo_screenheight() - h) // 2
        popup.geometry(f"{w}x{h}+{sx}+{sy}")
        
        # Header
        header_frame = ctk.CTkFrame(popup, fg_color="#2b2b36", height=60, corner_radius=0)
        header_frame.pack(fill="x", side="top")
        
        sim_pct = int(pair_info["similarity"] * 100)
        ctk.CTkLabel(
            header_frame,
            text=f"Side-by-Side Comparison  ·  Record #{pair_info.get('idx_a', 0) + 1} ↔ Record #{pair_info.get('idx_b', 0) + 1}  ·  {sim_pct}% match",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#f39c12"
        ).pack(pady=12, padx=20)
        
        # Scrollable container for columns
        scroll_container = ctk.CTkScrollableFrame(popup, fg_color="transparent")
        scroll_container.pack(fill="both", expand=True, padx=20, pady=15)
        
        # Two columns layout inside scroll_container
        col_frame = ctk.CTkFrame(scroll_container, fg_color="transparent")
        col_frame.pack(fill="both", expand=True)
        col_frame.grid_columnconfigure(0, weight=1, uniform="col")
        col_frame.grid_columnconfigure(1, weight=1, uniform="col")
        
        # Left column (Record A)
        col_a = ctk.CTkFrame(col_frame, fg_color="#2b2b36", corner_radius=8, border_width=1, border_color="#444")
        col_a.grid(row=0, column=0, padx=(0, 10), sticky="nsew", ipadx=10, ipady=10)
        
        # Right column (Record B)
        col_b = ctk.CTkFrame(col_frame, fg_color="#2b2b36", corner_radius=8, border_width=1, border_color="#444")
        col_b.grid(row=0, column=1, padx=(10, 0), sticky="nsew", ipadx=10, ipady=10)
        
        # Display helper for each column
        def populate_column(col_widget, rec, other_rec, label_num, rec_idx):
            # Header row with title + action buttons
            header_row = ctk.CTkFrame(col_widget, fg_color="transparent")
            header_row.pack(fill="x", padx=12, pady=(12, 4))
            
            lbl_title = ctk.CTkLabel(
                header_row, text=f"Record #{label_num}",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#3498db"
            )
            lbl_title.pack(side="left")
            
            # Action buttons (top-right corner)
            action_btns = ctk.CTkFrame(header_row, fg_color="transparent")
            action_btns.pack(side="right")
            
            def go_to_review(record):
                """Close all popups and jump to this record in Review mode."""
                record_id = record.get("id", "")
                # Close this popup and parent popup
                popup.destroy()
                if parent_popup:
                    try: parent_popup.destroy()
                    except: pass
                
                # Switch to Review mode if not already
                if self.current_mode != "review":
                    self.mode_switcher.set("🔍 Review")
                    self._toggle_mode("🔍 Review")
                
                # Clear filters so all records are visible
                self.advanced_filter = None
                self._apply_advanced_filter()
                
                # Find the record by ID and jump to it
                for i, r in enumerate(self.dataset_records):
                    if (r.get("id") or "") == record_id:
                        self.current_review_index = i
                        self._display_record(i)
                        break
            
            def delete_record(record, record_label):
                """Delete a specific record by ID after confirmation."""
                record_id = record.get("id", "")
                
                # Use heading for preview, fallback to text if empty
                heading_preview = (record.get("heading", "") or "").strip()
                if not heading_preview:
                    heading_preview = (record.get("text", "") or "").strip()
                heading_preview = heading_preview[:60]
                
                confirm = self._custom_ask_yes_no(
                    "Confirm Delete",
                    f"Are you sure you want to delete Record #{record_label}?\n\n"
                    f"\"{heading_preview}{'...' if len(heading_preview) == 60 else ''}\"\n\n"
                    "This action cannot be undone.",
                    parent=popup
                )
                if not confirm:
                    return
                
                # Find and remove from all_dataset_records
                all_idx = next((i for i, r in enumerate(self.all_dataset_records) if (r.get("id") or "") == record_id), -1)
                if all_idx >= 0:
                    self.all_dataset_records.pop(all_idx)
                
                # Find and remove from dataset_records (filtered view)
                ds_idx = next((i for i, r in enumerate(self.dataset_records) if (r.get("id") or "") == record_id), -1)
                if ds_idx >= 0:
                    self.dataset_records.pop(ds_idx)
                
                # Rewrite the CSV
                try:
                    self._rewrite_csv()
                except Exception as e:
                    messagebox.showerror("Delete Error", f"Failed to delete entry.\n\nError: {e}")
                    return
                
                # Refresh the view
                self._apply_advanced_filter(keep_index=True)
                
                # If currently in review mode, refresh the displayed record
                if self.current_mode == "review" and self.dataset_records:
                    if self.current_review_index >= len(self.dataset_records):
                        self.current_review_index = max(0, len(self.dataset_records) - 1)
                    self._display_record(self.current_review_index)
                
                # Close this popup and refresh parent
                popup.destroy()
                if on_mark_change_callback:
                    on_mark_change_callback()
                elif parent_popup:
                    try: parent_popup.destroy()
                    except: pass
            
            ctk.CTkButton(
                action_btns, text="📋 Review", width=80, height=26,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#2980b9", hover_color="#3498db",
                corner_radius=5,
                command=lambda r=rec: go_to_review(r)
            ).pack(side="left", padx=(0, 4))
            
            ctk.CTkButton(
                action_btns, text="🗑", width=30, height=26,
                font=ctk.CTkFont(size=13),
                fg_color="#c0392b", hover_color="#e74c3c",
                corner_radius=5,
                command=lambda r=rec, ln=label_num: delete_record(r, ln)
            ).pack(side="left")
            
            # Content area with proper padding
            content_area = ctk.CTkFrame(col_widget, fg_color="transparent")
            content_area.pack(fill="x", padx=12, pady=(0, 10))
            
            # Fields
            self._add_detail_field(content_area, "Label Status", f"{rec.get('label', '')} ({rec.get('multi_category', 'N/A')})", 
                                   label_color="#e74c3c" if rec.get('label') == "Fake" else "#2ecc71")
            self._add_detail_field(content_area, "Category", rec.get("category", "N/A"))
            self._add_detail_field(content_area, "Annotator", rec.get("annotator", "N/A"))
            self._add_detail_field(content_area, "Source Link", rec.get("source", "N/A"))
            
            heading_self = rec.get("heading", "") or ""
            heading_other = other_rec.get("heading", "") or ""
            text_self = rec.get("text", "") or ""
            text_other = other_rec.get("text", "") or ""
            
            # Textboxes
            self._add_highlighted_textbox(content_area, "News Heading", heading_self, heading_other, height=60)
            self._add_highlighted_textbox(content_area, "News Text", text_self, text_other, height=200)
            
            # Media buttons
            img_paths = rec.get("image_path", "")
            vid_path = rec.get("video_path", "")
            if img_paths or vid_path:
                media_frame = ctk.CTkFrame(content_area, fg_color="transparent")
                media_frame.pack(fill="x", pady=6)
                
                ctk.CTkLabel(
                    media_frame, text="Attached Media:",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#888", anchor="w"
                ).pack(fill="x", pady=(0, 4))
                
                media_btns_frame = ctk.CTkFrame(media_frame, fg_color="transparent")
                media_btns_frame.pack(fill="x")
                
                if img_paths:
                    for rel_path in img_paths.split(";"):
                        rel_path = rel_path.strip()
                        if rel_path:
                            full_path = SCRIPT_DIR / rel_path
                            exists = full_path.exists()
                            btn = ctk.CTkButton(
                                media_btns_frame,
                                text=f"🖼 {Path(rel_path).name}" if exists else f"⚠️ {Path(rel_path).name} (missing)",
                                height=28,
                                font=ctk.CTkFont(size=11),
                                fg_color="#2d6a4f" if exists else "#555",
                                hover_color="#40916c" if exists else "#555",
                                corner_radius=6,
                                command=(lambda p=full_path: self._show_image_by_path(p)) if exists else None
                            )
                            btn.pack(side="left", padx=(0, 4), pady=2)
                
                if vid_path:
                    vid_path_str = vid_path.strip()
                    if vid_path_str:
                        full_vid = SCRIPT_DIR / vid_path_str
                        exists = full_vid.exists()
                        btn = ctk.CTkButton(
                            media_btns_frame,
                            text=f"🎬 {Path(vid_path_str).name}" if exists else f"⚠️ {Path(vid_path_str).name} (missing)",
                            height=28,
                            font=ctk.CTkFont(size=11),
                            fg_color="#7b2cbf" if exists else "#555",
                            hover_color="#9d4edd" if exists else "#555",
                            corner_radius=6,
                            command=(lambda p=str(full_vid): self._play_video_by_path(p)) if exists else None
                        )
                        btn.pack(side="left", padx=(0, 4), pady=2)
                        
        populate_column(col_a, record_a, record_b, pair_info.get("idx_a", 0) + 1, pair_info.get("idx_a", 0))
        populate_column(col_b, record_b, record_a, pair_info.get("idx_b", 0) + 1, pair_info.get("idx_b", 0))
        
        # Bottom actions frame
        actions_frame = ctk.CTkFrame(popup, fg_color="transparent")
        actions_frame.pack(side="bottom", fill="x", pady=15, padx=20)
        
        # Legend (left side)
        legend_lbl = ctk.CTkLabel(
            actions_frame,
            text="🟡 Highlighted orange = words matching the compared entry",
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="#f39c12"
        )
        legend_lbl.pack(side="left", padx=10)
        
        # Buttons container (right side)
        btn_container = ctk.CTkFrame(actions_frame, fg_color="transparent")
        btn_container.pack(side="right")
        
        # Not Duplicate / Restore button
        non_dups = self._load_non_duplicates()
        id_a_str = str(record_a.get("id", ""))
        id_b_str = str(record_b.get("id", ""))
        pair_key = f"{min(id_a_str, id_b_str)}_{max(id_a_str, id_b_str)}"
        is_marked = pair_key in non_dups
        
        if is_marked:
            ctk.CTkButton(
                btn_container, text="Restore Duplicate ♻️", width=160, height=34,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="#e67e22", hover_color="#d35400",
                command=lambda: [
                    self._unmark_as_non_duplicate(record_a, record_b), 
                    popup.destroy(),
                    (on_mark_change_callback() if on_mark_change_callback else None)
                ]
            ).pack(side="left", padx=(0, 10))
        else:
            ctk.CTkButton(
                btn_container, text="Non Duplicate❓", width=160, height=34,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="#27ae60", hover_color="#2ecc71",
                command=lambda: [
                    self._mark_as_non_duplicate(record_a, record_b), 
                    popup.destroy(),
                    (on_mark_change_callback() if on_mark_change_callback else None)
                ]
            ).pack(side="left", padx=(0, 10))
        
        # Close button
        ctk.CTkButton(
            btn_container, 
            text="Close", 
            width=120, 
            height=34, 
            command=popup.destroy,
            fg_color="#34495e",
            hover_color="#2c3e50",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left")

    def _show_duplicate_save_warning(self, matches, on_confirm_save):

        """
        Displays a warning window showing the potential duplicates before saving.
        Allows the user to proceed with saving or cancel.
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Duplicate News Verification")
        w, h = 650, 500
        popup.configure(fg_color="#1a1a2e")
        popup.attributes("-topmost", True)
        # Center on screen
        popup.update_idletasks()
        sx = (popup.winfo_screenwidth() - w) // 2
        sy = (popup.winfo_screenheight() - h) // 2
        popup.geometry(f"{w}x{h}+{sx}+{sy}")
        
        # Header
        header_frame = ctk.CTkFrame(popup, fg_color="#2b1b1b", height=60, corner_radius=0)
        header_frame.pack(fill="x", side="top")
        
        ctk.CTkLabel(
            header_frame,
            text="⚠️ Potential Duplicates Detected!",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#e74c3c"
        ).pack(pady=(10, 2), padx=20)
        
        ctk.CTkLabel(
            header_frame,
            text="The entry you are saving is very similar to existing news items.",
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="#aaa"
        ).pack(pady=(0, 10), padx=20)
        
        # Scrollable container of matching duplicates
        scroll_frame = ctk.CTkScrollableFrame(popup, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        # Help label
        ctk.CTkLabel(
            scroll_frame,
            text="Please inspect the matched items below before proceeding:",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            text_color="#eee"
        ).pack(fill="x", pady=(0, 6))
        
        for match in matches:
            row_num = match["row_num"]
            sim = match["similarity"]
            combined_sim = match.get("combined_sim", 0)
            heading_sim = match.get("heading_sim", 0)
            
            sim_pct = int(sim * 100)
            
            # -- Card row --
            row_frame = ctk.CTkFrame(scroll_frame, fg_color="#2b2b36", corner_radius=8,
                                      border_width=1, border_color="#444")
            row_frame.pack(fill="x", pady=4, ipady=6)
            
            # Instance number badge
            badge_color = "#e74c3c" if sim_pct >= 80 else ("#f39c12" if sim_pct >= 60 else "#3498db")
            badge = ctk.CTkLabel(
                row_frame, text=f" #{row_num} ",
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color=badge_color, corner_radius=6,
                text_color="white", width=50
            )
            badge.pack(side="left", padx=(10, 8), pady=6)
            
            # Match info text
            text_sim = match.get("text_sim", 0.0)
            info_text = f"{sim_pct}% match  ·  Head+Body: {sim_pct}%  ·  Heading: {int(heading_sim*100)}%  ·  Text: {int(text_sim*100)}%"
            ctk.CTkLabel(
                row_frame, text=info_text,
                font=ctk.CTkFont(size=12),
                text_color="#ccc", anchor="w"
            ).pack(side="left", fill="x", expand=True, padx=(0, 8))

            
            # Inspect button
            ctk.CTkButton(
                row_frame, text="🔍 Inspect", width=90, height=28,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#6c5ce7", hover_color="#5a4bd1",
                corner_radius=6,
                command=lambda m=match: self._view_duplicate_details(m)
            ).pack(side="right", padx=(0, 10), pady=6)
            
        # Bottom Actions Frame (centered)
        actions_frame = ctk.CTkFrame(popup, fg_color="transparent")
        actions_frame.pack(side="bottom", pady=15)
        
        def save_anyway():
            popup.destroy()
            on_confirm_save()
            
        def cancel_save():
            popup.destroy()
            
        # Save Anyway Button
        save_btn = ctk.CTkButton(
            actions_frame,
            text="✅ Save Anyway",
            width=140,
            height=34,
            fg_color="#2ecc71",
            hover_color="#27ae60",
            text_color="black",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=save_anyway
        )
        save_btn.pack(side="left", padx=(0, 12))
        
        # Cancel Button
        cancel_btn = ctk.CTkButton(
            actions_frame,
            text="❌ Cancel & Edit",
            width=140,
            height=34,
            fg_color="#e74c3c",
            hover_color="#c0392b",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=cancel_save
        )
        cancel_btn.pack(side="left")

    def _view_duplicate_details(self, match_info):
        """
        Opens a popup detail view to inspect the matched record.
        Media files are rendered as clickable buttons that open in the OS default viewer.
        """
        row_num = match_info["row_num"]
        record = match_info["record"]
        similarity = match_info["similarity"]
        combined_sim = match_info.get("combined_sim", 0)
        heading_sim = match_info.get("heading_sim", 0)
        containment_sim = match_info.get("containment_sim", 0)
        
        popup = ctk.CTkToplevel(self)
        popup.title(f"Duplicate Inspection - Instance #{row_num}")
        pw, ph = 750, 680
        popup.configure(fg_color="#1a1a2e")
        popup.attributes("-topmost", True)
        # Center on screen
        popup.update_idletasks()
        sx = (popup.winfo_screenwidth() - pw) // 2
        sy = (popup.winfo_screenheight() - ph) // 2
        popup.geometry(f"{pw}x{ph}+{sx}+{sy}")
        
        # Header
        header_frame = ctk.CTkFrame(popup, fg_color="#2b1b1b" if similarity >= 0.75 else "#2b2b36", height=60, corner_radius=0)
        header_frame.pack(fill="x", side="top")
        
        ctk.CTkLabel(
            header_frame, 
            text=f"⚠️ Potential Duplicate (Instance #{row_num})", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#e74c3c" if similarity >= 0.75 else "#f39c12"
        ).pack(pady=(8, 2), padx=20)
        
        text_sim = match_info.get("text_sim", 0.0)
        ctk.CTkLabel(
            header_frame,
            text=f"Head+Body (Overall): {similarity * 100:.1f}%  ·  Heading: {heading_sim * 100:.1f}%  ·  Text: {text_sim * 100:.1f}%",
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="#aaa"
        ).pack(pady=(0, 8), padx=20)

        
        # Scrollable container
        details_frame = ctk.CTkScrollableFrame(popup, fg_color="transparent")
        details_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        # Legend label
        legend_lbl = ctk.CTkLabel(
            details_frame,
            text="🟡 Highlighted orange = words matching the compared entry",
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="#f39c12",
            anchor="w"
        )
        legend_lbl.pack(fill="x", pady=(0, 10))
        
        # Fields
        self._add_detail_field(details_frame, "Label Status", f"{record.get('label', '')} ({record.get('multi_category', 'N/A')})", 
                               label_color="#e74c3c" if record.get('label') == "Fake" else "#2ecc71")
        self._add_detail_field(details_frame, "Category", record.get("category", "N/A"))
        self._add_detail_field(details_frame, "Source Category", record.get("source_category", "N/A"))
        self._add_detail_field(details_frame, "Annotator", record.get("annotator", "N/A"))
        self._add_detail_field(details_frame, "Source Link", record.get("source", "N/A"))
        
        new_heading = match_info.get("new_heading_ref", "")
        new_text = match_info.get("new_text_ref", "")
        
        heading_text = record.get("heading", "")
        if heading_text:
            self._add_highlighted_textbox(details_frame, "News Heading", heading_text, new_heading or "", height=60)
            
        body_text = record.get("text", "")
        if body_text:
            self._add_highlighted_textbox(details_frame, "News Text", body_text, new_text or "", height=220)
            
        # Attached Media — clickable buttons to open files
        img_paths = record.get("image_path", "")
        vid_path = record.get("video_path", "")
        if img_paths or vid_path:
            media_frame = ctk.CTkFrame(details_frame, fg_color="transparent")
            media_frame.pack(fill="x", pady=6)
            
            ctk.CTkLabel(
                media_frame, text="Attached Media:",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#888", anchor="w"
            ).pack(fill="x", pady=(0, 4))
            
            media_btns_frame = ctk.CTkFrame(media_frame, fg_color="transparent")
            media_btns_frame.pack(fill="x")
            
            if img_paths:
                for rel_path in img_paths.split(";"):
                    rel_path = rel_path.strip()
                    if rel_path:
                        full_path = SCRIPT_DIR / rel_path
                        exists = full_path.exists()
                        btn = ctk.CTkButton(
                            media_btns_frame,
                            text=f"🖼 {Path(rel_path).name}" if exists else f"⚠️ {Path(rel_path).name} (missing)",
                            height=28,
                            font=ctk.CTkFont(size=11),
                            fg_color="#2d6a4f" if exists else "#555",
                            hover_color="#40916c" if exists else "#555",
                            corner_radius=6,
                            command=(lambda p=str(full_path): self._open_media_file(p)) if exists else None
                        )
                        btn.pack(side="left", padx=(0, 6), pady=2)
            
            if vid_path:
                vid_path_str = vid_path.strip()
                if vid_path_str:
                    full_vid = SCRIPT_DIR / vid_path_str
                    exists = full_vid.exists()
                    btn = ctk.CTkButton(
                        media_btns_frame,
                        text=f"🎬 {Path(vid_path_str).name}" if exists else f"⚠️ {Path(vid_path_str).name} (missing)",
                        height=28,
                        font=ctk.CTkFont(size=11),
                        fg_color="#7b2cbf" if exists else "#555",
                        hover_color="#9d4edd" if exists else "#555",
                        corner_radius=6,
                        command=(lambda p=str(full_vid): self._open_media_file(p)) if exists else None
                    )
                    btn.pack(side="left", padx=(0, 6), pady=2)
            
        # Close button (centered)
        ctk.CTkButton(
            popup, 
            text="Close", 
            width=120, 
            height=34, 
            command=popup.destroy,
            fg_color="#34495e",
            hover_color="#2c3e50",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(pady=(0, 15))

    def _show_image_by_path(self, path):
        """Opens an image in the built-in image viewer popup by file path."""
        try:
            img = Image.open(path)
        except Exception:
            messagebox.showerror("Error", f"Could not open image:\n{path}")
            return

        popup = ctk.CTkToplevel(self)
        popup.title("Image Viewer")
        popup.configure(fg_color="#111")
        popup.attributes("-topmost", True)

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        max_w = int(screen_w * 0.8)
        max_h = int(screen_h * 0.8)
        img.thumbnail((max_w, max_h), Image.LANCZOS)

        popup.geometry(f"{img.width + 40}x{img.height + 100}")

        ctk_photo = ctk.CTkImage(light_image=img, dark_image=img,
                                  size=(img.width, img.height))
        popup._photo_ref = ctk_photo

        lbl = ctk.CTkLabel(popup, image=ctk_photo, text="")
        lbl.pack(expand=True, fill="both", padx=10, pady=(10, 5))

        ctk.CTkLabel(popup, text=Path(path).name, font=ctk.CTkFont(size=12),
                     text_color="#aaa").pack(pady=(0, 5))

        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=(0, 10))

        ctk.CTkButton(btn_frame, text="📂 Open File Location", width=140, height=30,
                      fg_color="#2d6a4f", hover_color="#40916c",
                      command=lambda: [self._open_file_location(path), popup.destroy()]).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_frame, text="Close", width=100, height=30,
                      command=popup.destroy).pack(side="left")

    def _play_video_by_path(self, path_str):
        """Opens a video file in the OS default video player."""
        try:
            if platform.system() == "Darwin":
                subprocess.call(('open', path_str))
            elif platform.system() == "Windows":
                os.startfile(path_str)
            else:
                subprocess.call(('xdg-open', path_str))
        except Exception as e:
            messagebox.showerror("Error", f"Could not play video: {e}")

    def _open_file_location(self, file_path):
        """Opens the file explorer and highlights the given file."""
        try:
            file_path = Path(file_path)
            folder = file_path.parent
            if platform.system() == "Darwin":
                subprocess.Popen(["open", "-R", str(file_path)])
            elif platform.system() == "Windows":
                subprocess.Popen(["explorer", "/select,", str(file_path)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file location:\n{e}")

    def _add_detail_field(self, parent, label_text, value_text, label_color=None):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=4)
        
        lbl = ctk.CTkLabel(frame, text=f"{label_text}:", font=ctk.CTkFont(size=13, weight="bold"), text_color="#888", width=120, anchor="w")
        lbl.pack(side="left")
        
        val = ctk.CTkLabel(frame, text=value_text, font=ctk.CTkFont(size=13), anchor="w", justify="left")
        if label_color:
            val.configure(text_color=label_color, font=ctk.CTkFont(size=13, weight="bold"))
        val.pack(side="left", fill="x", expand=True)

    def _add_detail_textbox(self, parent, label_text, content_text, height=100):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=6)
        
        lbl = ctk.CTkLabel(frame, text=label_text, font=ctk.CTkFont(size=13, weight="bold"), text_color="#888", anchor="w")
        lbl.pack(fill="x", pady=(0, 2))
        
        tb = ctk.CTkTextbox(frame, height=height, font=ctk.CTkFont(size=12))
        tb.pack(fill="x")
        tb.insert("1.0", content_text)
        
        # Prevent scroll event propagation to the parent CTkScrollableFrame
        # but allow propagation once the textbox scroll limits are reached.
        text_widget = tb._textbox
        def stop_propagation(event):
            y_start, y_end = text_widget.yview()
            
            # Check scroll direction (up vs down)
            if event.delta:
                is_up = event.delta > 0
                scroll_amount = -1 if is_up else 1
            else:
                is_up = event.num == 4
                scroll_amount = -1 if is_up else 1
                
            if is_up:
                # If not at the top, scroll textbox and block propagation
                if y_start > 0.0:
                    text_widget.yview_scroll(scroll_amount, "units")
                    return "break"
            else:
                # If not at the bottom, scroll textbox and block propagation
                if y_end < 1.0:
                    text_widget.yview_scroll(scroll_amount, "units")
                    return "break"
            
            # Let the event bubble up to the parent scrollable frame
            return None
            
        text_widget.bind("<MouseWheel>", stop_propagation)
        text_widget.bind("<Button-4>", stop_propagation)
        text_widget.bind("<Button-5>", stop_propagation)

        
        tb.configure(state="disabled")

    def _add_highlighted_textbox(self, parent, label_text, existing_text, new_text, height=100):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=6)
        
        # Calculate overlap words for helper header
        words_existing = get_words_with_positions(existing_text)
        words_new_set = {w['word'] for w in get_words_with_positions(new_text)}
        matched_words_count = 0
        if words_existing and words_new_set:
            matched_words_count = sum(1 for w in words_existing if w['word'] in words_new_set)
        
        pct_overlap = int((matched_words_count / len(words_existing)) * 100) if words_existing else 0
        
        # Label with word overlap summary
        header_text = f"{label_text}  ({matched_words_count} of {len(words_existing)} words matched · {pct_overlap}% overlap)"
        lbl = ctk.CTkLabel(frame, text=header_text, font=ctk.CTkFont(size=13, weight="bold"), text_color="#888", anchor="w")
        lbl.pack(fill="x", pady=(0, 2))
        
        tb = ctk.CTkTextbox(frame, height=height, font=ctk.CTkFont(size=12))
        tb.pack(fill="x")
        tb.insert("1.0", existing_text)
        
        # Find ranges and highlight them in orange
        ranges = find_matching_word_ranges(new_text, existing_text, n=4)
        
        # We need a tag config for the highlight
        tb.tag_config("match_highlight", background="#f39c12", foreground="black")
        
        # Add tags for each range
        for start_char, end_char in ranges:
            start_index = f"1.0 + {start_char} chars"
            end_index = f"1.0 + {end_char} chars"
            tb.tag_add("match_highlight", start_index, end_index)
            
        # Prevent scroll event propagation to the parent CTkScrollableFrame
        # but allow propagation once the textbox scroll limits are reached.
        text_widget = tb._textbox
        def stop_propagation(event):
            y_start, y_end = text_widget.yview()
            
            # Check scroll direction (up vs down)
            if event.delta:
                is_up = event.delta > 0
                scroll_amount = -1 if is_up else 1
            else:
                is_up = event.num == 4
                scroll_amount = -1 if is_up else 1
                
            if is_up:
                # If not at the top, scroll textbox and block propagation
                if y_start > 0.0:
                    text_widget.yview_scroll(scroll_amount, "units")
                    return "break"
            else:
                # If not at the bottom, scroll textbox and block propagation
                if y_end < 1.0:
                    text_widget.yview_scroll(scroll_amount, "units")
                    return "break"
            
            # Let the event bubble up to the parent scrollable frame
            return None
            
        text_widget.bind("<MouseWheel>", stop_propagation)
        text_widget.bind("<Button-4>", stop_propagation)
        text_widget.bind("<Button-5>", stop_propagation)

        tb.configure(state="disabled")

