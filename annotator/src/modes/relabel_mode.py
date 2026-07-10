"""
RelabelModeMixin mixin class.
"""

import customtkinter as ctk
from tkinter import messagebox
import csv
from pathlib import Path
from app_paths import KAPPA_CSV_PATH
from constants import MULTI_CATEGORIES, CSV_COLUMNS
from data.config_manager import load_config, save_config, sanitize_name

class RelabelModeMixin:
    def _pack_radios_vertical(self):
        """
        Arranges fake news sub-classification radio buttons vertically.
        
        Used to stack buttons inside narrow columns (e.g. in Re-label mode).
        """
        # Detach radio button widgets from their horizontal positioning layouts first
        self.radio_misinfo.pack_forget()
        self.radio_satire.pack_forget()
        self.radio_clickbait.pack_forget()
        
        # Re-pack buttons vertically to fit inside the narrow sidebar during Re-label mode
        self.radio_misinfo.pack(anchor="w", pady=(10, 10))
        self.radio_satire.pack(anchor="w", pady=(0, 10))
        self.radio_clickbait.pack(anchor="w", pady=(0, 10))

    def _pack_radios_horizontal(self):
        """
        Arranges fake news sub-classification radio buttons horizontally.
        
        Used for regular, wide window layout distributions.
        """
        # Detach radio button widgets from their vertical alignment schemes first
        self.radio_misinfo.pack_forget()
        self.radio_satire.pack_forget()
        self.radio_clickbait.pack_forget()
        
        # Pack buttons side-by-side to distribute them horizontally across wide containers
        self.radio_misinfo.pack(side="left", padx=(0, 12))
        self.radio_satire.pack(side="left", padx=(0, 12))
        self.radio_clickbait.pack(side="left")

    def _enter_relabel_mode(self):
        """
        Initializes and sets up the Re-label mode for inter-rater agreement (Kappa) analysis.
        
        This workflow:
        - Ingests the secondary rating target database file (`relabeling_for_kappa.csv`).
        - Automatically hides input components that are only relevant for standard annotation 
          (e.g., categories, source descriptions, notes) to establish a clean interface.
        - Pre-fills the annotator entry field with the configuration-persisted rating name.
        - Deactivates heading title and core text fields to make article content read-only.
        - Automatically jumps to the first record that has not yet been rated by the active annotator.
        - Formats the left-hand text column wider and right-hand options column narrower.
        - Vertically stacks news type option buttons to fit the narrow control sidebar.
        - Refreshes reliability stats badges to reflect progress count.
        """
        # Load the inter-rater reliability database file.
        # Fall back to standard annotate mode if the target file cannot be processed or is empty.
        if not self._load_kappa_csv():
            self.mode_switcher.set("📝 Annotate")
            self.current_mode = "annotate"
            self._restore_draft()
            self._update_stats()
            return

        # Hide inputs and category controls not used in blind reviews to keep raters unbiased.
        self._hide_annotate_only_fields()

        # Clear active entry fields to remove any leftovers from previous records
        self._clear_fields()

        # Pre-populate reviewer/annotator name using the saved configuration file helper
        self.annotator_entry.delete(0, "end")
        saved_name = load_config()
        if saved_name:
            self.annotator_entry.insert(0, saved_name)

        # Draw review navigation panel bar and hide advanced search filtering buttons
        self.nav_frame.grid(row=0, column=0, sticky="ew", padx=(8, 8), pady=6)
        self.filter_btn.pack_forget()
        self.filter_indicator.pack_forget()
        self.search_btn.pack_forget()
        self.uuid_display_frame.pack_forget()

        # Set up primary button actions and hide secondary controls (like Delete or Clear All)
        self.primary_btn.configure(text="💾  Save Decision",
                                    command=self._save_kappa_decision)
        self.primary_btn.pack_configure(padx=(0, 0))
        self.secondary_btn.pack_forget()

        # Deactivate modification access to primary textual fields (heading and main body text)
        # to ensure raters cannot modify the news content.
        self.heading_entry.configure(state="disabled")
        self.text_box.configure(state="disabled")

        # Resume rating progress from the first uncompleted sample row associated with this reviewer name
        annotator = self.annotator_entry.get().strip()
        start_idx = self._find_first_unlabeled(annotator)
        self.current_kappa_index = start_idx

        # Restructure column grid weights to make the text reading column wider (weight 3)
        # and the right-hand options column narrower (weight 1).
        self.content_container.columnconfigure(0, weight=3)
        self.content_container.columnconfigure(1, weight=1)

        # Align bottom bar navigation column weights symmetrically with the columns above
        self.bottom_bar.columnconfigure(0, weight=3, uniform="btm")
        self.bottom_bar.columnconfigure(1, weight=1, uniform="btm")
        
        # Hide category frames to conserve sidebar space
        self.category_stats_frame.pack_forget()

        # Arrange Fake News subcategory radio buttons vertically to fit the narrow sidebar
        self._pack_radios_vertical()

        # Load reliability statistics and display target record
        self._update_kappa_stats()
        if self.kappa_records:
            self._display_kappa_record(self.current_kappa_index)

    def _exit_relabel_mode(self):
        """
        Cleans up layouts and re-enables standard workspace fields when leaving Re-label mode.
        
        This resets input text modifications states, restores normal equal column widths, 
        restores category lists visibilities, resets option buttons orientation to horizontal, 
        and resets navigation pointer frames states.
        """
        # Restore horizontal category list layout frame
        self.category_stats_frame.pack(fill="x", pady=(0, 6), after=self.stats_frame)

        # Restore normal editing access to headline and text fields
        self.heading_entry.configure(state="normal")
        self.text_box.configure(state="normal")

        # Hide review navigation layouts
        self.nav_frame.grid_forget()

        # Clear inter-rater variables in memory
        self.kappa_records = []
        self.kappa_csv_columns = []
        self.current_kappa_index = 0

        # Reset column layout weights to equal distribution (1:1 ratio)
        self.content_container.columnconfigure(0, weight=1, uniform="col")
        self.content_container.columnconfigure(1, weight=1, uniform="col")

        # Reset bottom bar layout weights to equal distribution
        self.bottom_bar.columnconfigure(0, weight=1, uniform="btm")
        self.bottom_bar.columnconfigure(1, weight=1, uniform="btm")

        # Restore horizontal radio button layout orientation
        self._pack_radios_horizontal()
        
        # Ensure the reviewed badge is hidden when leaving Re-label mode
        self.done_label.configure(image=None, text="")
        self.done_indicator_frame.pack_forget()

    def _restore_annotate_fields(self):
        """
        Restores all input frames that were hidden to support the Re-label layout.
        
        Iterates over the widget references cached during the layout switch and calls pack
        with their original geometry parameters.
        """
        # Iterate through cached widgets that were hidden during relabel mode setup
        if hasattr(self, '_hidden_relabel_widgets'):
            for widget, pack_info in self._hidden_relabel_widgets:
                try:
                    # Restore widget geometry using stored packing configurations
                    widget.pack(**pack_info)
                except Exception:
                    pass
            # Wipe cache list to clean up memory
            self._hidden_relabel_widgets = []

    def _hide_annotate_only_fields(self):
        """
        Hides UI widgets that are not relevant during blind inter-rater reliability rating.
        
        Iterates through the right-hand container components, identifying and packing-forgetting 
        widgets that do not match the annotator name entry or label toggles (such as topic categories, 
        source medium dropdowns, article URLs, confidence levels, or personal comments).
        Also hides media browse and paste options to enforce read-only viewing boundaries.
        """
        self._hidden_relabel_widgets = []
        keep_widgets = set()
        right_children = list(self.right_col.winfo_children())

        # Traverse right sidebar frames to isolate annotator and label inputs
        found_annotator = False
        found_label = False

        for i, child in enumerate(right_children):
            is_section_frame = False
            section_text = ""
            if isinstance(child, ctk.CTkFrame):
                # Search frames for title text matching key headers
                for sub in child.winfo_children():
                    if isinstance(sub, ctk.CTkLabel):
                        t = sub.cget("text")
                        if t:
                            section_text = t
                            is_section_frame = True
                            break

            if is_section_frame:
                # Retain the Annotator Name section frame
                if "Annotator" in section_text:
                    found_annotator = True
                    found_label = False
                    keep_widgets.add(child)
                    continue
                # Retain the Authenticity Label section frame
                elif "Authenticity" in section_text:
                    found_annotator = False
                    found_label = True
                    keep_widgets.add(child)
                    continue
                else:
                    found_annotator = False
                    found_label = False

            # Keep the annotator entry field
            if found_annotator and child == self.annotator_entry:
                keep_widgets.add(child)
                found_annotator = False
                continue

            # Keep the parent container holding the Fake/Real buttons
            if found_label and isinstance(child, ctk.CTkFrame):
                keep_widgets.add(child)
                found_label = False
                continue

            # Keep the fine-grained type frame and status indicator label
            if child in (self.multi_cat_frame, self.done_indicator_frame):
                keep_widgets.add(child)
                continue

        # Hide widgets not selected for retention, saving packing configurations for recovery
        for child in right_children:
            if child not in keep_widgets:
                pack_info = child.pack_info() if child.winfo_manager() == "pack" else None
                if pack_info:
                    restore_info = {
                        k: v for k, v in pack_info.items()
                        if k in ('side', 'fill', 'expand', 'padx', 'pady', 'anchor',
                                 'ipadx', 'ipady')
                    }
                    self._hidden_relabel_widgets.append((child, restore_info))
                    child.pack_forget()

        # Hide browse and copy buttons frame in the media attachments panel
        for child in self.left_col.winfo_children():
            if isinstance(child, ctk.CTkFrame):
                sub_children = child.winfo_children()
                # Detect the media actions frame by checking if it contains the browse buttons
                has_browse = any(
                    isinstance(sc, ctk.CTkButton) and "Browse" in (sc.cget("text") or "")
                    for sc in sub_children
                )
                if has_browse:
                    pack_info = child.pack_info() if child.winfo_manager() == "pack" else None
                    if pack_info:
                        restore_info = {
                            k: v for k, v in pack_info.items()
                            if k in ('side', 'fill', 'expand', 'padx', 'pady', 'anchor',
                                     'ipadx', 'ipady')
                        }
                        self._hidden_relabel_widgets.append((child, restore_info))
                        child.pack_forget()
                    break

    def _load_kappa_csv(self):
        """
        Ingests the secondary annotation database file into memory.
        
        Returns:
            bool: True if loaded successfully, False if missing/empty.
        """
        # Verify that the Kappa CSV target path exists on disk and is not empty
        if not KAPPA_CSV_PATH.exists() or KAPPA_CSV_PATH.stat().st_size == 0:
            messagebox.showinfo(
                "No Kappa Data",
                f"Kappa re-labeling CSV not found:\n{KAPPA_CSV_PATH}\n\n"
                "Use Scripts → Generate Kappa Sample to create it."
            )
            return False

        # Reset the memory records array
        self.kappa_records = []
        
        # Read the Kappa dataset records from file
        with open(KAPPA_CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Cache the current columns header list
            self.kappa_csv_columns = list(reader.fieldnames) if reader.fieldnames else []
            for row in reader:
                self.kappa_records.append(row)

        # Alert if the file contains only headers but no data rows
        if not self.kappa_records:
            messagebox.showinfo("No Kappa Data",
                "The kappa CSV file is empty.\n"
                "Use Scripts → Generate Kappa Sample to populate it.")
            return False

        return True

    def _find_first_unlabeled(self, annotator_name):
        """
        Finds the index of the first record in the list that has not been rated by this annotator.
        
        Args:
            annotator_name: String name identifying the annotator.
            
        Returns:
            int: Zero-based record index, or 0 if all have been rated or name is blank.
        """
        # Default to index 0 if the annotator name field is empty or no records are loaded
        if not annotator_name or not self.kappa_records:
            return 0

        # Sanitize the input name to form the correct reviewer column prefix
        sanitized = sanitize_name(annotator_name)
        label_col = f"{sanitized}_label"

        # Search rows sequentially for a blank entry in this annotator's label column
        for i, record in enumerate(self.kappa_records):
            value = (record.get(label_col) or "").strip()
            # The first empty string value represents the first unrated record location
            if not value:
                return i

        # Fallback to starting index 0 if the annotator has completed all records
        return 0

    def _display_kappa_record(self, index):
        """
        Populates UI display fields with data from a specific record in Re-label mode.
        
        Loads article headline and body text into read-only display fields, refreshes image
        and video media previews, and checks if the active annotator has already rated this
        item. If a rating is present, pre-loads the label and sub-category inputs and shows 
        the completed badge.
        
        Args:
            index: Zero-based integer index of the record inside kappa_records.
        """
        # Bounds check: do nothing if index is out of range or list is empty
        if not self.kappa_records or index < 0 or index >= len(self.kappa_records):
            return

        # Fetch the active record dictionary from the Kappa list
        record = self.kappa_records[index]
        total = len(self.kappa_records)

        # Update the index counter entry text field
        self.record_index_entry.configure(state="normal")
        self.record_index_entry.delete(0, "end")
        self.record_index_entry.insert(0, str(index + 1))
        self.record_total_label.configure(text=f"of {total}")
        
        # Disable navigation buttons at the boundaries of the list to prevent out-of-bounds errors
        self.prev_btn.configure(state="normal" if index > 0 else "disabled")
        self.next_btn.configure(state="normal" if index < total - 1 else "disabled")

        # Clear the label selector dropdown inputs
        self.label_var.set("")
        self._update_label_toggles()
        self.multi_cat_frame.pack_forget()
        self.multi_cat_var.set("")

        # Temporarily enable heading text box to insert content, then set to read-only
        self.heading_entry.configure(state="normal")
        self.heading_entry.delete("1.0", "end")
        heading = record.get("heading") or ""
        if heading:
            self.heading_entry.insert("1.0", heading)
        self.heading_entry.configure(state="disabled")
        self._update_heading_search_visibility()

        # Temporarily enable news text box to insert content, then set to read-only
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        text = record.get("text") or ""
        if text:
            self.text_box.insert("1.0", text)
        self.text_box.configure(state="disabled")

        # Reset media lists and missing asset references
        self.image_list.clear()
        self.video_path = None
        self.missing_media = []

        # Load and verify the attached video path if registered
        video_path_str = record.get("video_path") or ""
        if video_path_str:
            full_vid_path = KAPPA_CSV_PATH.parent / video_path_str
            if full_vid_path.exists():
                self.video_path = full_vid_path
            else:
                # Keep track of missing file references to notify the user
                self.missing_media.append(("video", video_path_str))

        # Parse and verify semicolon-delimited image paths
        image_paths = record.get("image_path") or ""
        if image_paths:
            for rel_path in image_paths.split(";"):
                rel_path = rel_path.strip()
                if rel_path:
                    full_path = KAPPA_CSV_PATH.parent / rel_path
                    if full_path.exists():
                        # Store verified path with a None placeholder for the PIL Image object
                        self.image_list.append((full_path, None))
                    else:
                        # Keep track of missing file references to notify the user
                        self.missing_media.append(("image", rel_path))
                        
        # Render the image previews and trigger placeholder graphics for missing files
        self._refresh_previews()

        # Check if the active annotator has already rated this item
        annotator = self.annotator_entry.get().strip()
        is_reviewed = False
        if annotator:
            sanitized = sanitize_name(annotator)
            label_col = f"{sanitized}_label"
            multi_col = f"{sanitized}_multi_category"

            existing_label = (record.get(label_col) or "").strip()
            existing_multi = (record.get(multi_col) or "").strip()

            # Pre-load the label and sub-category inputs if a rating is present
            if existing_label:
                is_reviewed = True
                self.label_var.set(existing_label)
                self._on_label_change()
                if existing_label == "Fake" and existing_multi in MULTI_CATEGORIES:
                    self.multi_cat_var.set(existing_multi)
                
        # Draw the visual completed badge if the record has been reviewed by the active user
        if is_reviewed:
            if self.reviewed_badge_img:
                self.done_label.configure(image=self.reviewed_badge_img, text="")
            else:
                self.done_label.configure(image=None, text="ALREADY REVIEWED", font=ctk.CTkFont(size=18, weight="bold"), text_color="#2ecc71")
            # Show the indicator frame
            self.done_indicator_frame.pack(side="bottom", expand=True, fill="both", padx=12, pady=(10, 20))
        else:
            self.done_label.configure(image=None, text="")
            # Hide the indicator frame completely if not reviewed
            self.done_indicator_frame.pack_forget()

        # Recalculate kappa rating stats
        self._update_kappa_stats()

    def _save_kappa_decision(self, auto_advance=True):
        """
        Saves the rating decision for the current record.
        
        Writes the ratings to `{annotator_name}_label` and `{annotator_name}_multi_category`
        columns inside `relabeling_for_kappa.csv`. Automatically adds columns to the header if new.
        
        Args:
            auto_advance: If True, moves to the next record in the queue after a successful save.
            
        Returns:
            bool: True if decision saved successfully, False if validation failed.
        """
        # Abort if no kappa records are loaded in memory
        if not self.kappa_records:
            return False

        # Gather inputs from workspace widgets
        annotator = self.annotator_entry.get().strip()
        label = self.label_var.get()
        multi_cat = self.multi_cat_var.get()

        # Validate entries
        errors = []
        if not annotator:
            errors.append("Annotator name is required.")
        if not label:
            errors.append("Label (Fake/Real) must be selected.")
        if label == "Fake" and not multi_cat:
            errors.append("Fake News Type (Misinformation/Satire/Clickbait) must be selected.")

        # Display errors window if validation checks failed
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return False

        # Set multi-category value to Real if the authenticity label is set to Real
        if label == "Real":
            multi_cat = "Real"

        # Cache active username in config persistence file
        save_config(annotator)

        # Sanitize name to build dynamic column headers
        sanitized = sanitize_name(annotator)
        label_col = f"{sanitized}_label"
        multi_col = f"{sanitized}_multi_category"

        # Add new column headers to list if this is the first item reviewed by this annotator
        if label_col not in self.kappa_csv_columns:
            self.kappa_csv_columns.append(label_col)
        if multi_col not in self.kappa_csv_columns:
            self.kappa_csv_columns.append(multi_col)

        # Update record row in memory
        record = self.kappa_records[self.current_kappa_index]
        record[label_col] = label
        record[multi_col] = multi_cat

        # Commit memory updates to disk file
        try:
            self._rewrite_kappa_csv()
        except Exception as e:
            messagebox.showerror(
                "Save Error",
                f"Failed to save decision. Please make sure the kappa CSV "
                f"is not open in another program.\n\nError: {e}"
            )
            return False

        # Refresh stats bar metrics
        self._update_kappa_stats()
        
        # Display completed rating indicator badge
        if self.reviewed_badge_img:
            self.done_label.configure(image=self.reviewed_badge_img, text="")
        else:
            self.done_label.configure(image=None, text="ALREADY REVIEWED", font=ctk.CTkFont(size=18, weight="bold"), text_color="#2ecc71")

        # Repack the indicator frame to refresh visuals
        if not auto_advance:
            self.done_indicator_frame.pack(side="bottom", expand=True, fill="both", padx=12, pady=(10, 20))

        # Handle auto advance navigation transitions
        if auto_advance:
            if self.current_kappa_index < len(self.kappa_records) - 1:
                self.current_kappa_index += 1
                self._display_kappa_record(self.current_kappa_index)
            else:
                # Notify user when the end of the reliability review queue is reached
                # Trigger a popup message informing the user that they have successfully annotated 
                # every sample in the kappa queue. This ensures clear closure for the rating session.
                messagebox.showinfo("Done",
                    "All items have been labeled!\n"
                    "You can navigate back to review your decisions.")
                    
        # Return True to indicate that the record saving operation was completed successfully
        return True

    def _rewrite_kappa_csv(self):
        """
        Rewrites the kappa CSV file to commit updated decisions from memory to disk.
        
        This method aggregates the dynamic annotator columns (ratings) registered during
        the session across all loaded records. It constructs an ordered list of headers,
        ensuring that standard dataset fields remain first in the column order, followed
        by individual reviewer rating columns sorted alphabetically. Finally, it uses
        csv.DictWriter to safely overwrite the target CSV file with the updated records.
        """
        # Collect all existing columns currently present across any of the kappa record dicts
        all_cols = set(self.kappa_csv_columns)
        for record in self.kappa_records:
            all_cols.update(record.keys())

        # Segregate the columns to maintain a clean layout: standard fields are placed first,
        # and extra reviewer annotations are grouped and sorted alphabetically at the end.
        base_cols = [c for c in CSV_COLUMNS if c in all_cols]
        extra_cols = sorted([c for c in all_cols if c not in CSV_COLUMNS])
        ordered_cols = base_cols + extra_cols

        # Update the application's column cache with the finalized sequence
        self.kappa_csv_columns = ordered_cols

        # Open the target reliability CSV file with write access and UTF-8 encoding
        with open(KAPPA_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            # Instantiate a DictWriter mapper configuration that ignores extraneous keys
            writer = csv.DictWriter(f, fieldnames=ordered_cols, extrasaction="ignore")
            
            # Write the column headers as the first line of the file
            writer.writeheader()
            
            # Iterate through the in-memory records and write each row to the file
            for record in self.kappa_records:
                row = {col: record.get(col, "") for col in ordered_cols}
                writer.writerow(row)

    def _update_kappa_stats(self):
        """
        Calculates and updates the stats panel specifically for the Re-label workspace.
        
        To prevent annotator bias during blind reliability checks, this method suppresses
        the distribution counts of Fake/Real labels and topic categories. Instead, it computes:
        - The total number of items loaded in the Kappa agreement queue.
        - The number of records already rated by the current active reviewer.
        - The number of pending records remaining for the active reviewer.
        It then clears existing stats badges and renders new cards for these metrics.
        """
        # Remove any existing stat widgets inside the container frames to prevent layout overlap
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
        for widget in self.category_stats_frame.winfo_children():
            widget.destroy()

        # Retrieve the current status bounds
        total = len(self.kappa_records)
        annotator = self.annotator_entry.get().strip()

        # If a valid annotator name has been entered, count completed labels for that reviewer
        if annotator:
            sanitized = sanitize_name(annotator)
            label_col = f"{sanitized}_label"
            labeled = sum(1 for r in self.kappa_records
                          if (r.get(label_col) or "").strip())
            remaining = total - labeled
        else:
            # Revert to defaults if the annotator entry field is blank
            labeled = 0
            remaining = total

        # Render modern styled badges for total, completed, and pending records
        self._create_stat_badge(self.stats_frame, "Total Items", total, "#3498db")
        self._create_stat_badge(self.stats_frame, "Labeled", labeled, "#2ecc71")
        self._create_stat_badge(self.stats_frame, "Remaining", remaining, "#e67e22")

        # Request tkinter to recalculate and refresh geometry containers
        self.stats_frame.update_idletasks()
        self.category_stats_frame.update_idletasks()
        
        # Trigger the flow layout arrangement logic on the frames
        self.stats_frame._arrange()
        self.category_stats_frame._arrange()

    def _check_unsaved_kappa_changes(self):
        """
        Verifies if there are unsaved rating decisions on the active Kappa record.
        
        This method compares the current selection values in the dropdown widgets (such
        as Label and Fake News Type) against the committed values stored in the record dict.
        If a mismatch is detected, it raises a confirmation popup dialog allowing the user
        to save changes, discard them, or cancel the navigation action entirely.
        
        Returns:
            bool: True if it is safe to proceed with navigation (changes saved or discarded),
                  False if the user chose to cancel the navigation.
        """
        # If no kappa records are loaded or the index is invalid, no unsaved work exists
        if not self.kappa_records or self.current_kappa_index < 0:
            return True

        # Fetch the active record dictionary and current annotator name
        record = self.kappa_records[self.current_kappa_index]
        annotator = self.annotator_entry.get().strip()

        # If no annotator name has been specified, no editing column can be mapped
        if not annotator:
            return True

        # Map username to its corresponding rating column fields
        sanitized = sanitize_name(annotator)
        label_col = f"{sanitized}_label"
        multi_col = f"{sanitized}_multi_category"

        # Read the current selection states from the UI widgets
        current_label = self.label_var.get()
        current_multi = self.multi_cat_var.get() if current_label == "Fake" else ("Real" if current_label == "Real" else "")

        # Read the previously saved states from the in-memory record dict
        saved_label = (record.get(label_col) or "").strip()
        saved_multi = (record.get(multi_col) or "").strip()
        if saved_label == "Real":
            saved_multi = "Real"

        # Check for discrepancies between the UI widgets and the cached memory record
        changed = False
        if current_label != saved_label:
            changed = True
        elif current_label == "Fake" and current_multi != saved_multi:
            changed = True

        # If no differences are found, it is safe to navigate away
        if not changed:
            return True

        # Prompt the user with a standard confirmation dialog
        response = self._custom_ask_yes_no_cancel(
            "Unsaved Changes",
            "You have unsaved changes in this record.\n\n"
            "Do you want to save them before moving?"
        )

        # Handle user choice: True = Save, False = Discard, None = Cancel
        if response is True:
            # Attempt to write choices to memory and disk
            save_ok = self._save_kappa_decision(auto_advance=False)
            if not save_ok:
                # If validation fails, ask the user if they wish to discard changes to proceed
                discard = self._custom_ask_yes_no(
                    "Save Failed",
                    "Could not save due to validation errors.\n\n"
                    "Do you want to discard your changes and continue?"
                )
                return discard
            return True
        elif response is False:
            # User explicitly chose to discard changes
            return True
        else:
            # User clicked Cancel, aborting navigation
            return False

    def _kappa_next_record(self):
        """
        Navigates forward to the next record in the Kappa reliability review queue.
        
        Performs dirty verification checks on the active item before moving. If verification
        passes and another record exists, increments the index counter and loads the new entry.
        """
        # Verify that we are not already at the final record in the list
        if self.current_kappa_index < len(self.kappa_records) - 1:
            # Run safety checks for unsaved changes before moving
            if not self._check_unsaved_kappa_changes():
                return
            
            # Increment index pointer and refresh UI field content
            self.current_kappa_index += 1
            self._display_kappa_record(self.current_kappa_index)

    def _kappa_prev_record(self):
        """
        Navigates backward to the previous record in the Kappa reliability review queue.
        
        Performs dirty verification checks on the active item before moving. If verification
        passes and another record exists, decrements the index counter and loads the new entry.
        """
        # Verify that we are not at the first record in the list
        if self.current_kappa_index > 0:
            # Run safety checks for unsaved changes before moving
            if not self._check_unsaved_kappa_changes():
                return
            
            # Decrement index pointer and refresh UI field content
            self.current_kappa_index -= 1
            self._display_kappa_record(self.current_kappa_index)

    def _kappa_jump_to_record(self, event=None):
        """
        Jumps directly to a user-entered record index in the reliability review list.
        
        Triggered by pressing Enter on the index input widget. Validates that the input is a
        valid integer within list boundaries, performs dirty checks, and displays the record.
        """
        try:
            # Retrieve and parse the numeric value entered in the text field
            val = int(self.record_index_entry.get().strip())
            idx = val - 1
            
            # Validate that the index is within the boundaries of loaded kappa records
            if 0 <= idx < len(self.kappa_records):
                if self.current_kappa_index != idx:
                    # Verify unsaved changes on the active record before leaping
                    if not self._check_unsaved_kappa_changes():
                        # Revert the index entry back to the active record number if cancelled
                        self.record_index_entry.delete(0, "end")
                        self.record_index_entry.insert(0, str(self.current_kappa_index + 1))
                        self.focus_set()
                        return
                    
                    # Update index and render the new record
                    self.current_kappa_index = idx
                    self._display_kappa_record(self.current_kappa_index)
                
                # Re-focus the main window
                self.focus_set()
            else:
                # Revert text input and show a warning popup if the value is out of range
                self.record_index_entry.delete(0, "end")
                self.record_index_entry.insert(0, str(self.current_kappa_index + 1))
                messagebox.showwarning("Invalid Record",
                    f"Please enter a number between 1 and {len(self.kappa_records)}.")
        except ValueError:
            # Revert text input to the active record number if parsing fails
            self.record_index_entry.delete(0, "end")
            self.record_index_entry.insert(0, str(self.current_kappa_index + 1))

