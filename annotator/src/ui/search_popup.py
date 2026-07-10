"""
SearchUIMixin mixin class.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
from analysis.text_similarity import calculate_jaccard_similarity, calculate_containment_similarity, calculate_heading_similarity, clean_text

class SearchUIMixin:
    def _show_search_popup(self):
        """
        Opens a popup dialog allowing users to search the active filtered dataset
        by exact UUID or by heading/body text similarity.
        """
        if self.current_mode != "review" or not self.dataset_records:
            messagebox.showinfo("Search", "No records available to search.")
            return

        popup = ctk.CTkToplevel(self)
        popup.title("Search Filtered Dataset")
        popup.configure(fg_color="#1a1a2e")
        popup.transient(self)

        # Helper to dynamically resize the popup window
        def resize_popup(height):
            popup.geometry(f"600x{height}")

        # Initial compact sizing (UUID mode on startup)
        resize_popup(260)
        popup.resizable(False, True)

        # Center on screen after geometry calculation
        popup.update_idletasks()
        sx = (popup.winfo_screenwidth() - 600) // 2
        sy = (popup.winfo_screenheight() - 260) // 2
        popup.geometry(f"600x260+{sx}+{sy}")

        # Main Header
        header_frame = ctk.CTkFrame(popup, fg_color="#2b2b36", height=45, corner_radius=0)
        header_frame.pack(side="top", fill="x")
        header_frame.pack_propagate(False)

        ctk.CTkLabel(
            header_frame, text="🔍 Search Active Records",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#ffffff"
        ).pack(pady=8)

        # Bottom Bar for Close Button
        bottom_bar = ctk.CTkFrame(popup, fg_color="transparent")
        bottom_bar.pack(side="bottom", fill="x", pady=(5, 10), padx=20)
        
        close_btn = ctk.CTkButton(
            bottom_bar, text="Close", command=popup.destroy,
            width=80, height=28, font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#34495e", hover_color="#2c3e50"
        )
        close_btn.pack(anchor="center")

        # Search Controls Frame
        ctrl_frame = ctk.CTkFrame(popup, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=20, pady=(10, 5))

        # Input Query Container for UUID
        uuid_input_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        ctk.CTkLabel(uuid_input_frame, text="Exact ID (UUID):", font=ctk.CTkFont(size=11, weight="bold"), text_color="#ccc").pack(anchor="w", pady=(0, 1))
        uuid_entry = ctk.CTkEntry(uuid_input_frame, placeholder_text="Enter exact UUID...", height=28)
        uuid_entry.pack(fill="x")

        # Input Query Container for Text Similarity
        text_input_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        
        ctk.CTkLabel(text_input_frame, text="Heading Query:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#ccc").pack(anchor="w", pady=(0, 1))
        heading_entry = ctk.CTkEntry(text_input_frame, placeholder_text="Enter heading text keywords...", height=28)
        heading_entry.pack(fill="x", pady=(0, 6))
        
        ctk.CTkLabel(text_input_frame, text="Body Text Query:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#ccc").pack(anchor="w", pady=(0, 1))
        text_entry = ctk.CTkTextbox(text_input_frame, height=45, font=ctk.CTkFont(size=12), border_width=1, border_color="#555", undo=True)
        text_entry.pack(fill="x")

        # Toggle UI frames based on selection
        search_type_var = ctk.StringVar(value="uuid")
        scroll_frame = None
        result_cards = {}  # Tracks visual row widgets to highlight selections

        def toggle_inputs():
            nonlocal scroll_frame, result_cards
            result_cards.clear()
            if scroll_frame:
                scroll_frame.destroy()
                scroll_frame = None
            
            if search_type_var.get() == "uuid":
                text_input_frame.pack_forget()
                uuid_input_frame.pack(fill="x", pady=(0, 8))
                resize_popup(270)
            else:
                uuid_input_frame.pack_forget()
                text_input_frame.pack(fill="x", pady=(0, 8))
                resize_popup(360)

        # Mode Selection Radio Buttons
        mode_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        mode_frame.pack(fill="x", pady=(0, 6))
        
        ctk.CTkRadioButton(
            mode_frame, text="Exact UUID", variable=search_type_var,
            value="uuid", command=toggle_inputs, font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="left", padx=(0, 15))
        
        ctk.CTkRadioButton(
            mode_frame, text="Heading / Text Similarity", variable=search_type_var,
            value="text", command=toggle_inputs, font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="left")

        # Initialize the inputs layout
        toggle_inputs()

        # Info disclaimer
        ctk.CTkLabel(
            ctrl_frame, text="ℹ️ Search is restricted to the currently filtered dataset.",
            font=ctk.CTkFont(size=11, slant="italic"), text_color="#3498db"
        ).pack(anchor="w", pady=(2, 6))

        # Results area
        results_container = ctk.CTkFrame(popup, fg_color="transparent")
        results_container.pack(fill="both", expand=True, padx=20, pady=(0, 5))

        def perform_search():
            nonlocal scroll_frame, result_cards
            search_type = search_type_var.get()
            result_cards.clear()

            # Clear previous results scroll frame if any
            if scroll_frame:
                scroll_frame.destroy()
                scroll_frame = None

            # 1. Exact UUID Search
            if search_type == "uuid":
                query = uuid_entry.get().strip()
                if not query:
                    messagebox.showwarning("Search Error", "Please enter a UUID query.", parent=popup)
                    return
                
                found_idx = -1
                for idx, record in enumerate(self.dataset_records):
                    if (record.get("id") or "").strip() == query:
                        found_idx = idx
                        break

                if found_idx != -1:
                    popup.destroy()
                    self.current_review_index = found_idx
                    self._display_record(found_idx)
                else:
                    # Create results panel to display warning
                    scroll_frame = ctk.CTkScrollableFrame(results_container, fg_color="#1a1a2e")
                    scroll_frame.pack(fill="both", expand=True)
                    resize_popup(370)

                    # Check unfiltered dataset
                    exists_unfiltered = False
                    for record in self.all_dataset_records:
                        if (record.get("id") or "").strip() == query:
                            exists_unfiltered = True
                            break
                    
                    if exists_unfiltered:
                        msg = "⚠️ ID exists in database, but is excluded by active filters."
                    else:
                        msg = "❌ No record found with that exact ID."

                    ctk.CTkLabel(
                        scroll_frame, text=msg,
                        font=ctk.CTkFont(size=12, weight="bold"), text_color="#e74c3c"
                    ).pack(pady=20)
            
            # 2. Text Similarity Search
            else:
                heading_q = heading_entry.get().strip()
                text_q = text_entry.get("1.0", "end-1c").strip()
                
                if not heading_q and not text_q:
                    messagebox.showwarning("Search Error", "Please fill in either Heading or Body Text query (or both).", parent=popup)
                    return

                scroll_frame = ctk.CTkScrollableFrame(results_container, fg_color="#1a1a2e")
                scroll_frame.pack(fill="both", expand=True)

                threshold = self._get_duplicate_threshold() / 100.0
                results = []

                for idx, record in enumerate(self.dataset_records):
                    h_rec = record.get("heading") or ""
                    t_rec = record.get("text") or ""
                    
                    heading_sim = 0.0
                    if heading_q and h_rec:
                        heading_sim = calculate_heading_similarity(heading_q, h_rec)
                        
                    text_sim = 0.0
                    if text_q and t_rec:
                        jaccard = calculate_jaccard_similarity(text_q, t_rec)
                        words_q = set(clean_text(text_q))
                        words_rec = set(clean_text(t_rec))
                        intersection = len(words_q.intersection(words_rec))
                        min_len = min(len(words_q), len(words_rec))
                        containment = intersection / min_len if min_len > 0 else 0.0
                        text_sim = max(jaccard, containment)
                    
                    scores = []
                    if heading_q:
                        scores.append(heading_sim)
                    if text_q:
                        scores.append(text_sim)
                        
                    max_sim = max(scores) if scores else 0.0
                    if max_sim >= threshold:
                        results.append((idx, record, max_sim))

                # Sort by similarity score descending
                results.sort(key=lambda x: x[2], reverse=True)

                # Behavior: If exactly 1 match is found, close the popup and display it immediately
                if len(results) == 1:
                    target_idx = results[0][0]
                    popup.destroy()
                    self.current_review_index = target_idx
                    self._display_record(target_idx)
                    return

                # If multiple matches, expand the popup and render results
                if results:
                    resize_popup(550)
                    
                    # Render matches in scroll frame
                    for r_idx, r_data, score in results:
                        row_frame = ctk.CTkFrame(scroll_frame, fg_color="#2b2b36", corner_radius=6, border_width=1, border_color="#444")
                        row_frame.pack(fill="x", pady=3, padx=2, ipady=3)
                        result_cards[r_idx] = row_frame

                        text_info = r_data.get("heading") or r_data.get("text") or "No textual content"
                        if len(text_info) > 60:
                            text_info = text_info[:60] + "..."

                        # Score badge
                        badge_color = "#e74c3c" if score >= 0.8 else ("#f39c12" if score >= 0.6 else "#3498db")
                        score_badge = ctk.CTkLabel(
                            row_frame, text=f" {int(score * 100)}% ",
                            font=ctk.CTkFont(size=11, weight="bold"),
                            fg_color=badge_color, corner_radius=4, text_color="white"
                        )
                        score_badge.pack(side="left", padx=8, pady=3)

                        # Snippet
                        info_lbl = ctk.CTkLabel(
                            row_frame, text=f"#{r_idx + 1} - {text_info}",
                            font=ctk.CTkFont(size=11), text_color="#eee", anchor="w"
                        )
                        info_lbl.pack(side="left", fill="x", expand=True, padx=4)

                        # Jump Command (updates main review UI but DOES NOT close popup)
                        def jump_to_target(target=r_idx):
                            # Reset previous highlights
                            for card in result_cards.values():
                                card.configure(fg_color="#2b2b36", border_color="#444")
                            # Highlight selected card
                            result_cards[target].configure(fg_color="#1f6aa5", border_color="#3498db")
                            
                            self.current_review_index = target
                            self._display_record(target)

                        # Inline trigger button
                        jump_btn = ctk.CTkButton(
                            row_frame, text="View ➜", width=55, height=22,
                            font=ctk.CTkFont(size=10, weight="bold"),
                            fg_color="#27ae60", hover_color="#2ecc71", text_color="black",
                            command=jump_to_target
                        )
                        jump_btn.pack(side="right", padx=8, pady=3)
                else:
                    # If 0 matches, show warning label
                    resize_popup(420)
                    ctk.CTkLabel(
                        scroll_frame, text="❌ No matching records found.",
                        font=ctk.CTkFont(size=12, weight="bold"), text_color="#e74c3c"
                    ).pack(pady=20)

        # Trigger search button
        search_btn = ctk.CTkButton(
            ctrl_frame, text="🔍 Search", height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#27ae60", hover_color="#2ecc71", text_color="black",
            command=perform_search
        )
        search_btn.pack(fill="x", pady=4)
        
        # Binds Return keys to entry variables
        uuid_entry.bind("<Return>", lambda e: perform_search())
        heading_entry.bind("<Return>", lambda e: perform_search())
        text_entry.bind("<Control-Return>", lambda e: perform_search())
        text_entry.bind("<Command-Return>", lambda e: perform_search())
