"""
FilterMixin mixin class.
"""

import customtkinter as ctk
from constants import CATEGORIES, SOURCE_CATEGORIES, MULTI_CATEGORIES

class FilterMixin:
    def _apply_advanced_filter(self, keep_index=False):
        """
        Filters the full dataset based on advanced criteria selected in the filter popup.
        
        This method processes the in-memory master list of records (all_dataset_records)
        and applies active filter parameters such as labels, sub-types, categories, source platforms,
        annotator names, content types (text/image/video combinations), the presence of notes,
        and confidence intervals.
        
        Args:
            keep_index: If True, preserves the current record review index. If False, or if
                        the current index is out of bounds after filtering, resets the index to 0.
        """
        if self.current_mode != "review":
            return

        filt = self.advanced_filter

        # If no filter criteria are active, restore the full dataset list
        if not filt:
            self.dataset_records = list(self.all_dataset_records)
        else:
            filtered = list(self.all_dataset_records)

            # Filter records by active authenticity labels (Fake / Real)
            sel_labels = filt.get("labels")
            if sel_labels:
                filtered = [r for r in filtered if (r.get("label") or "") in sel_labels]

            # Filter records by fake news classification sub-types
            sel_types = filt.get("types")
            if sel_types:
                filtered = [r for r in filtered if (r.get("multi_category") or "") in sel_types]

            # Filter records by topic categories (e.g. Politics, Sports)
            sel_cats = filt.get("categories")
            if sel_cats:
                filtered = [r for r in filtered if (r.get("category") or "") in sel_cats]

            # Filter records by news source categories (e.g. newspaper, social media)
            sel_src_cats = filt.get("source_categories")
            if sel_src_cats:
                filtered = [r for r in filtered if (r.get("source_category") or "") in sel_src_cats]

            # Filter records by the name of the annotator who saved them
            sel_annotators = filt.get("annotators")
            if sel_annotators:
                filtered = [r for r in filtered if (r.get("annotator") or "") in sel_annotators]

            # Filter records by their structural content type (e.g. text only, text & media)
            sel_content_types = filt.get("content_types")
            if sel_content_types:
                def _content_type(r):
                    has_text = bool((r.get("text") or "").strip())
                    has_image = bool((r.get("image_path") or "").strip())
                    has_video = bool((r.get("video_path") or "").strip())
                    has_media = has_image or has_video
                    if has_text and has_media:
                        return "Text & Image"
                    elif has_media:
                        return "Image Only"
                    elif has_text:
                        return "Text Only"
                    return ""
                
                # Check for video attachments separately from standard text/image breakdowns
                check_has_video = "Has Video" in sel_content_types
                other_types = sel_content_types - {"Has Video"}
                if other_types and check_has_video:
                    filtered = [r for r in filtered if _content_type(r) in other_types or bool((r.get("video_path") or "").strip())]
                elif check_has_video:
                    filtered = [r for r in filtered if bool((r.get("video_path") or "").strip())]
                else:
                    filtered = [r for r in filtered if _content_type(r) in other_types]

            # Filter records to only show those containing internal annotator notes
            if filt.get("has_notes"):
                filtered = [r for r in filtered if (r.get("additional_notes") or "").strip()]

            # Filter records by annotation confidence interval limits
            min_conf = filt.get("min_conf")
            max_conf = filt.get("max_conf")
            if min_conf is not None or max_conf is not None:
                lo = min_conf if min_conf is not None else 0
                hi = max_conf if max_conf is not None else 100
                def _conf_in_range(r):
                    try:
                        c = int(r.get("annotation_confidence") or "100")
                    except ValueError:
                        c = 100
                    return lo <= c <= hi
                filtered = [r for r in filtered if _conf_in_range(r)]

            self.dataset_records = filtered

        # Resolve index indexing boundaries for review navigation
        if not keep_index:
            self.current_review_index = 0
        elif self.current_review_index >= len(self.dataset_records):
            self.current_review_index = max(0, len(self.dataset_records) - 1)

        # Refresh the stats dashboard badges and active filter text
        self._update_stats()
        self._update_filter_indicator()

        # Update the form UI to display the current record, or clear fields if empty
        if self.dataset_records:
            self.record_index_entry.configure(state="normal")
            self._display_record(self.current_review_index)
        else:
            self._clear_fields()
            self.record_index_entry.configure(state="normal")
            self.record_index_entry.delete(0, "end")
            self.record_index_entry.insert(0, "0")
            self.record_index_entry.configure(state="disabled")
            self.record_total_label.configure(text="of 0")
            self.prev_btn.configure(state="disabled")
            self.next_btn.configure(state="disabled")

    def _update_filter_indicator(self):
        """
        Updates the UI filter status label and button styling.
        
        Reflects the count of active filter parameters on the label next to the
        filter button. If filters are active, highlights the button with a yellow warning color.
        """
        if self.advanced_filter:
            count = 0
            f = self.advanced_filter
            if f.get("labels"): count += 1
            if f.get("types"): count += 1
            if f.get("categories"): count += 1
            if f.get("source_categories"): count += 1
            if f.get("annotators"): count += 1
            if f.get("content_types"): count += 1
            if f.get("has_notes"): count += 1
            if f.get("min_conf") is not None or f.get("max_conf") is not None: count += 1
            self.filter_indicator.configure(text=f"⚡ {count} filter(s)")
            self.filter_btn.configure(fg_color="#4a3f00", border_color="#f39c12")
            if self.filter_btn.winfo_manager():
                self.filter_indicator.pack(side="right", padx=(4, 0), after=self.filter_btn)
        else:
            self.filter_indicator.pack_forget()
            self.filter_btn.configure(fg_color="#2d2d5e", border_color="#555")

    def _collect_unique_values(self, field):
        """
        Collects all unique, non-empty values for a specified column from all loaded records.
        
        This helper is used to dynamically construct selection options inside the filter dialog
        based on actual values present in the CSV database (such as unique annotator names).
        
        Args:
            field: The column name in the dataset records to extract values from.
            
        Returns:
            A sorted list of unique non-empty string values.
        """
        values = set()
        for r in self.all_dataset_records:
            v = (r.get(field) or "").strip()
            if v:
                values.add(v)
        return sorted(values)

    def _show_filter_popup(self):
        """
        Opens a modal window containing advanced filter controls for Review mode.
        
        Constructs checklists for labels, sub-types, categories, platforms,
        annotators, and content types. Includes entry fields for setting the
        minimum and maximum confidence interval boundaries.
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Filter Records")
        popup.configure(fg_color="#1a1a2e")
        popup.attributes("-topmost", True)
        popup.resizable(True, True)

        # Center the popup window on the screen relative to the main app coordinates
        pw, ph = 600, 580
        popup.geometry(f"{pw}x{ph}")
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (pw // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (ph // 2)
        popup.geometry(f"+{x}+{y}")

        # Section Header Title Frame with Icon
        header_frame = ctk.CTkFrame(popup, fg_color="transparent")
        header_frame.pack(pady=(12, 6))
        
        filter_icon = getattr(self, "filter_icon", None)
        if filter_icon:
            ctk.CTkLabel(header_frame, text="", image=filter_icon).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(header_frame, text="Filter Settings", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        else:
            ctk.CTkLabel(header_frame, text="🔽 Filter Settings", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        # Scrollable container supporting vertical layout overflows
        scroll = ctk.CTkScrollableFrame(popup, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        # Load active filter selections to pre-populate checkbox variables
        cur = self.advanced_filter or {}

        def _checkbox_section(parent, title, options, pre_selected):
            """
            Builds a card frame containing checklists for a categorical filter section.
            
            Returns a list of (option_value, BooleanVar) tuples to read selection states.
            """
            frame = ctk.CTkFrame(parent, fg_color="#222244", corner_radius=8,
                                  border_width=1, border_color="#444")
            frame.pack(fill="x", pady=(6, 2))

            ctk.CTkLabel(frame, text=title,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#ccc").pack(anchor="w", padx=10, pady=(6, 2))

            vars_list = []
            row_frame = ctk.CTkFrame(frame, fg_color="transparent")
            row_frame.pack(fill="x", padx=10, pady=(0, 6))

            # Render checkboxes in a 4-column grid layout
            for i, opt in enumerate(options):
                var = ctk.BooleanVar(value=(opt in pre_selected) if pre_selected else False)
                cb = ctk.CTkCheckBox(row_frame, text=opt, variable=var,
                                      font=ctk.CTkFont(size=12),
                                      height=24, checkbox_width=18, checkbox_height=18)
                cb.grid(row=i // 4, column=i % 4, sticky="w", padx=(0, 12), pady=2)
                vars_list.append((opt, var))
            return vars_list

        # Authenticity labels (Fake / Real)
        label_vars = _checkbox_section(scroll, "Label",
                                       ["Fake", "Real"],
                                       cur.get("labels", set()))

        # Fake News Sub-classification Types
        type_vars = _checkbox_section(scroll, "Fake News Type",
                                      MULTI_CATEGORIES,
                                      cur.get("types", set()))

        # Topic Categories (politics, science, etc.) compiled dynamically from data
        all_categories = self._collect_unique_values("category")
        cat_vars = _checkbox_section(scroll, "News Category",
                                     all_categories if all_categories else ["(no data)"],
                                     cur.get("categories", set()))

        # Platform medium categories compiled dynamically from data
        all_src_cats = self._collect_unique_values("source_category")
        src_cat_vars = _checkbox_section(scroll, "Source Category",
                                         all_src_cats if all_src_cats else ["(no data)"],
                                         cur.get("source_categories", set()))

        # Annotators names compiled dynamically from data
        all_annotators = self._collect_unique_values("annotator")
        ann_vars = _checkbox_section(scroll, "Annotator",
                                     all_annotators if all_annotators else ["(no data)"],
                                     cur.get("annotators", set()))

        # Media and Text content structure categories
        content_type_vars = _checkbox_section(scroll, "Content Type",
                                              ["Image Only", "Text & Image", "Text Only", "Has Video"],
                                              cur.get("content_types", set()))

        # Filter checkbox to toggle showing only records that contain non-empty annotator notes/comments.
        # This BooleanVar tracks the checkbox state and is pre-filled from the current filter settings.
        has_notes_var = ctk.BooleanVar(value=cur.get("has_notes", False))
        notes_filter_frame = ctk.CTkFrame(scroll, fg_color="#222244", corner_radius=8,
                                           border_width=1, border_color="#444")
        notes_filter_frame.pack(fill="x", pady=(6, 2))
        
        # Section title label for the additional notes filter block
        ctk.CTkLabel(notes_filter_frame, text="Additional Notes",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#ccc").pack(anchor="w", padx=10, pady=(6, 2))
        
        # Checklist checkbox container frame
        notes_cb_frame = ctk.CTkFrame(notes_filter_frame, fg_color="transparent")
        notes_cb_frame.pack(fill="x", padx=10, pady=(0, 6))
        
        # Checkbox controlling whether we restrict results to entries with user notes
        ctk.CTkCheckBox(notes_cb_frame, text="Only show entries with additional notes",
                        variable=has_notes_var, font=ctk.CTkFont(size=12),
                        height=24, checkbox_width=18, checkbox_height=18).pack(anchor="w")

        # Confidence Interval Range Selector
        # This frame groups controls that restrict the loaded subset to records within a specific confidence interval (0 to 100).
        conf_frame = ctk.CTkFrame(scroll, fg_color="#222244", corner_radius=8,
                                   border_width=1, border_color="#444")
        conf_frame.pack(fill="x", pady=(6, 2))

        # Title for the confidence interval settings section
        ctk.CTkLabel(conf_frame, text="Confidence Interval",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#ccc").pack(anchor="w", padx=10, pady=(6, 2))

        # Horizontal alignment row frame containing labels and text entries for min and max bounds
        conf_row = ctk.CTkFrame(conf_frame, fg_color="transparent")
        conf_row.pack(fill="x", padx=10, pady=(0, 8))

        # Input field for the minimum confidence value (default is 0)
        ctk.CTkLabel(conf_row, text="Min:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        min_conf_entry = ctk.CTkEntry(conf_row, width=60, height=26,
                                       font=ctk.CTkFont(size=12), justify="center")
        min_conf_entry.pack(side="left", padx=(0, 16))
        min_conf_entry.insert(0, str(cur.get("min_conf", 0)))

        # Input field for the maximum confidence value (default is 100)
        ctk.CTkLabel(conf_row, text="Max:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        max_conf_entry = ctk.CTkEntry(conf_row, width=60, height=26,
                                       font=ctk.CTkFont(size=12), justify="center")
        max_conf_entry.pack(side="left")
        max_conf_entry.insert(0, str(cur.get("max_conf", 100)))

        # Action control buttons container frame positioned at the bottom of the modal
        btn_container = ctk.CTkFrame(popup, fg_color="transparent")
        btn_container.pack(fill="x", padx=12, pady=(4, 12))

        # Combine all checkbox selection variables into a single flat list to simplify bulk resets
        all_checkbox_vars = label_vars + type_vars + cat_vars + src_cat_vars + ann_vars + content_type_vars

        def _clear_selections():
            """
            Resets all checkboxes in the popup and reverts the confidence interval 
            entries to the standard 0 to 100 range. Does not close the window.
            """
            # Reset all categories and filters in the checkboxes
            for _, var in all_checkbox_vars:
                var.set(False)
            has_notes_var.set(False)
            
            # Revert confidence entry fields back to absolute defaults
            min_conf_entry.delete(0, "end")
            min_conf_entry.insert(0, "0")
            max_conf_entry.delete(0, "end")
            max_conf_entry.insert(0, "100")

        def _apply():
            """
            Gathers the selected filters from the dialog checklist variables and confidence fields.
            Updates the application state's advanced_filter dictionary and triggers database updates.
            """
            # Pull selected list values from checkboxes
            sel_labels = {v for v, var in label_vars if var.get()}
            sel_types = {v for v, var in type_vars if var.get()}
            sel_cats = {v for v, var in cat_vars if var.get() and v != "(no data)"}
            sel_src_cats = {v for v, var in src_cat_vars if var.get() and v != "(no data)"}
            sel_annotators = {v for v, var in ann_vars if var.get() and v != "(no data)"}
            sel_content_types = {v for v, var in content_type_vars if var.get()}

            # Parse minimum confidence threshold value, reverting to 0 on string parsing errors
            try:
                mn = int(min_conf_entry.get().strip())
            except ValueError:
                mn = 0
            
            # Parse maximum confidence threshold value, reverting to 100 on string parsing errors
            try:
                mx = int(max_conf_entry.get().strip())
            except ValueError:
                mx = 100
            
            # Clamp thresholds to allowable percentages (0 to 100)
            mn = max(0, min(100, mn))
            mx = max(0, min(100, mx))
            
            # Swap values if user inadvertently input them backwards
            if mn > mx:
                mn, mx = mx, mn

            # Determine whether any active filter rules have been configured by checking selections
            notes_checked = has_notes_var.get()
            has_filter = (
                bool(sel_labels) or bool(sel_types) or bool(sel_cats) or
                bool(sel_src_cats) or bool(sel_annotators) or bool(sel_content_types) or
                notes_checked or mn > 0 or mx < 100
            )

            # Build or clear the advanced filter model dictionary accordingly
            if has_filter:
                self.advanced_filter = {
                    "labels": sel_labels if sel_labels else None,
                    "types": sel_types if sel_types else None,
                    "categories": sel_cats if sel_cats else None,
                    "source_categories": sel_src_cats if sel_src_cats else None,
                    "annotators": sel_annotators if sel_annotators else None,
                    "content_types": sel_content_types if sel_content_types else None,
                    "has_notes": notes_checked,
                    "min_conf": mn if mn > 0 else None,
                    "max_conf": mx if mx < 100 else None,
                }
            else:
                self.advanced_filter = None

            # Apply the selected criteria to reload the active list, then close popup
            self._apply_advanced_filter()
            popup.destroy()

        def _clear_and_apply():
            """
            Deactivates all filter parameters and closes the window immediately,
            restoring access to all records in the review queue.
            """
            self.advanced_filter = None
            self._apply_advanced_filter()
            popup.destroy()

        # Row 1 layout: Apply Filter + Clear All Selections buttons placed side-by-side
        row1 = ctk.CTkFrame(btn_container, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 6))

        # Button to confirm selections and update list view
        ctk.CTkButton(row1, text="✅ Apply Filter", command=_apply,
                       height=36, font=ctk.CTkFont(size=14, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black").pack(side="left", expand=True, fill="x", padx=(0, 6))

        # Button to clear checkboxes without submitting/applying or closing the popup
        ctk.CTkButton(row1, text="↺ Clear All", command=_clear_selections,
                       height=36, font=ctk.CTkFont(size=13),
                       fg_color="#555", hover_color="#777",
                       width=130).pack(side="left")

        # Row 2 layout: Clear Filter (disabling active settings) + Cancel buttons
        row2 = ctk.CTkFrame(btn_container, fg_color="transparent")
        row2.pack(fill="x")

        # Button to immediately wipe all active filter constraints from the review page
        ctk.CTkButton(row2, text="🗑️ Clear Filter", command=_clear_and_apply,
                       height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color="#e74c3c", hover_color="#c0392b").pack(side="left", expand=True, fill="x", padx=(0, 6))

        # Button to exit modal layout without saving any changes
        ctk.CTkButton(row2, text="Cancel", command=popup.destroy,
                       height=36, font=ctk.CTkFont(size=13),
                       fg_color="transparent", border_width=1,
                       border_color="#555", width=130).pack(side="left")

