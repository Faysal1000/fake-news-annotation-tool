"""
ReviewModeMixin mixin class.
"""

import customtkinter as ctk
from tkinter import messagebox
import csv
import os
import shutil
from datetime import datetime
from pathlib import Path
from app_paths import CSV_PATH, IMAGES_DIR, VIDEOS_DIR, SCRIPT_DIR
from constants import CSV_COLUMNS, MULTI_CATEGORIES
from data.csv_manager import generate_id
from data.config_manager import sanitize_name
from data.stats_engine import get_image_count, get_video_count

class ReviewModeMixin:
    def _load_dataset(self):
        """
        Loads all records from the dataset CSV file into memory for review.
        
        Reads rows from dataset.csv, converting them into dictionaries, and then 
        applies the advanced checklist/filter criteria to populate the active subset.
        """
        # Optimization: check if CSV file has not changed on disk to avoid redundant loading & thread stutters
        try:
            if CSV_PATH.exists():
                mtime = CSV_PATH.stat().st_mtime
                size = CSV_PATH.stat().st_size
                if (self.all_dataset_records and 
                    getattr(self, 'dataset_records', None) and 
                    mtime == getattr(self, '_last_loaded_csv_mtime', None) and 
                    size == getattr(self, '_last_loaded_csv_size', None)):
                    # No changes on disk; just apply active filters and skip clearing cache/starting threads
                    self._apply_advanced_filter()
                    return
        except Exception:
            pass

        # Reset duplicate scan cache and cancel background computations
        self._cancel_duplicate_computing = True
        if hasattr(self, '_duplicate_computing'):
            self._duplicate_computing = False
        self._duplicate_pairs_cache = None
        self._cached_records_data = None
        self.after(200, lambda: self._compute_global_duplicates(force_restart=True))

        # Reset the master records container list
        self.all_dataset_records = []

        
        # If the dataset CSV does not exist or is empty, initialize empty lists and return
        if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
            self.dataset_records = []
            return
        
        # Read the file contents as dictionaries and append them to the master list
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.all_dataset_records.append(row)
                
        # Update last loaded details
        try:
            self._last_loaded_csv_mtime = CSV_PATH.stat().st_mtime
            self._last_loaded_csv_size = CSV_PATH.stat().st_size
        except Exception:
            pass
            
        # Apply the active advanced filter settings to construct the subset list (dataset_records)
        self._apply_advanced_filter()

    def _display_record(self, index):
        """
        Populates all UI input and display fields with data from a specific record.
        
        Handles:
        - Enabling/disabling Prev/Next navigation buttons according to record bounds.
        - Updating the record counter indicator entry box.
        - Populating text fields, category select menus, confidence metrics, and notes.
        - Extracting and loading image arrays (verifying file paths relative to script).
        - Handling attached video playbacks or noting missing assets.
        
        Args:
            index: Zero-based integer index of the record inside dataset_records.
        """
        # Bounds check: do nothing if index is out of range or list is empty
        if not self.dataset_records or index < 0 or index >= len(self.dataset_records):
            return

        # Fetch the active record dictionary from the loaded subset
        record = self.dataset_records[index]
        self._current_uuid_str = record.get("id") or "N/A"
        if hasattr(self, "uuid_lbl"):
            self.uuid_lbl.configure(text=f"ID: {self._current_uuid_str}")

        # Get total records size for display configuration
        total = len(self.dataset_records)
        
        # Enable the index field to update the record counter text
        self.record_index_entry.configure(state="normal")
        self.record_index_entry.delete(0, "end")
        self.record_index_entry.insert(0, str(index + 1))
        self.record_total_label.configure(text=f"of {total}")
        
        # Disable navigation buttons at the boundaries of the list to prevent out-of-bounds errors
        self.after(10, lambda: self.prev_btn.configure(state="normal" if index > 0 else "disabled"))
        self.after(10, lambda: self.next_btn.configure(state="normal" if index < total - 1 else "disabled"))

        # Wipe all existing inputs in the workspace to prepare for the new record's properties
        self._clear_fields()

        # Insert the annotator name associated with this record
        self.annotator_entry.delete(0, "end")
        self.annotator_entry.insert(0, record.get("annotator") or "")

        # Set the Real/Fake classification label dropdown
        label = record.get("label") or ""
        if label:
            self.label_var.set(label)
            # Trigger the label change event handler to load/hide subcategory options
            self._on_label_change()

        # If labeled as Fake, set the subcategory news type selector dropdown
        multi_cat = record.get("multi_category") or ""
        if label == "Fake" and multi_cat in MULTI_CATEGORIES:
            self.multi_cat_var.set(multi_cat)

        # Set news category and platform source dropdown variables
        self.category_var.set(record.get("category") or "")
        self.source_cat_var.set(record.get("source_category") or "")

        # Insert the reference URL link or source description
        self.source_entry.delete(0, "end")
        self.source_entry.insert(0, record.get("source") or "")

        # Populate the additional annotator notes box
        self.notes_entry.delete("0.0", "end")
        notes = record.get("additional_notes") or ""
        if notes:
            self.notes_entry.insert("0.0", notes)

        # Populate the article headline title box
        self.heading_entry.delete("1.0", "end")
        heading = record.get("heading") or ""
        if heading:
            self.heading_entry.insert("1.0", heading)
        self._update_heading_search_visibility()

        # Populate the core news body text box
        self.text_box.delete("1.0", "end")
        text = record.get("text") or ""
        if text:
            self.text_box.insert("1.0", text)

        # Insert the confidence percentage metric value
        self.confidence_entry.delete(0, "end")
        self.confidence_entry.insert(0, record.get("annotation_confidence") or "100")

        # Reset media lists and missing asset references
        self.image_list.clear()
        self.video_path = None
        self.missing_media = []
        
        # Load and verify the attached video path if registered
        video_path_str = record.get("video_path") or ""
        if video_path_str:
            full_vid_path = SCRIPT_DIR / video_path_str
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
                    full_path = SCRIPT_DIR / rel_path
                    if full_path.exists():
                        # Store verified path with a None placeholder for the PIL Image object
                        self.image_list.append((full_path, None))
                    else:
                        # Keep track of missing file references to notify the user
                        self.missing_media.append(("image", rel_path))
                        
        # Render the image previews and trigger placeholder graphics for missing files
        self._refresh_previews()

        # Update the inline duplicate count warning
        if self.current_mode == "review":
            self._update_inline_duplicate_count()

    def _check_unsaved_annotate_changes(self):
        """
        Checks for any unsaved changes when leaving Annotate mode.
        
        Reviews all input fields, text areas, dropdowns, and media slots. If any 
        contain values, prompts the user to save as a record, discard the current
        entries, or cancel the mode switch entirely.
        
        Returns:
            bool: True if safe to leave (confirmed save/discard or empty fields),
                  False if the user chose to cancel/stay.
        """
        # Flag indicating whether the workspace has modified unsaved elements
        changed = False
        
        # Sequentially check every input field to see if the user has entered any data.
        # If any element has a non-default value, we set the changed flag to True.
        if self.label_var.get() != "": changed = True
        elif self.heading_entry.get("1.0", "end-1c").strip() != "": changed = True
        elif self.text_box.get("1.0", "end-1c").strip() != "": changed = True
        elif self.source_entry.get().strip() != "": changed = True
        elif self.source_cat_var.get() != "": changed = True
        elif self.category_var.get() != "": changed = True
        elif self.multi_cat_var.get() != "": changed = True
        # A confidence score of "100" or empty string counts as default, other values denote edits
        elif self.confidence_entry.get().strip() not in ("", "100"): changed = True
        elif self.notes_entry.get("0.0", "end-1c").strip() != "": changed = True
        # Check if the user has loaded images or videos into the media bins
        elif len(self.image_list) > 0: changed = True
        elif self.video_path is not None: changed = True

        # If changes are detected, prompt the user with a decision dialog box
        if changed:
            ans = self._custom_ask_yes_no_cancel(
                "Unsaved Entry",
                "You have started an annotation but haven't saved it.\n\n"
                "Do you want to save it now?"
            )
            
            # Action A: User clicked 'Cancel' (stay on the current page and abort mode toggle)
            if ans is None:
                return False
            
            # Action B: User clicked 'Yes' (commit the new annotation first)
            elif ans is True:
                # Attempt to save the entry. If validation checks fail, prevent leaving the mode.
                if not self._save_entry():
                    return False
            
            # Action C: User clicked 'No' (explicitly discard changes and clean the workspaces)
            else:
                self._clear_fields()
                
        # Safe to navigate
        return True

    def _check_unsaved_changes(self):
        """
        Checks for unsaved changes in the current review record before navigating away.
        
        Compares all UI input states against the original values stored in dataset_records.
        Inspects textual fields, category dropdowns, confidence levels, additional notes,
        image attachments, and video directories.
        
        Returns:
            bool: True if navigation can proceed (no changes or confirmed save/discard),
                  False if the navigation should be aborted.
        """
        # If there are no records in memory, we can navigate freely
        if not self.dataset_records or self.current_review_index < 0:
            return True
            
        # Retrieve the original database record dictionary for direct value comparison
        record = self.dataset_records[self.current_review_index]
        
        # Read the current values of all workspace fields in the UI
        annotator = self.annotator_entry.get().strip()
        label = self.label_var.get()
        heading = self.heading_entry.get("1.0", "end-1c").strip()
        text = self.text_box.get("1.0", "end-1c").strip()
        source = self.source_entry.get().strip()
        source_category = self.source_cat_var.get()
        category = self.category_var.get()
        # Set the subcategory classification conditionally based on label (Fake vs Real)
        multi_cat = self.multi_cat_var.get() if label == "Fake" else ("Real" if label == "Real" else "")
        confidence = self.confidence_entry.get().strip()
        notes = self.notes_entry.get("0.0", "end-1c").strip()
        
        # Track changes indicator
        changed = False
        # Helper function to normalize strings and newlines for safe comparison across OSes
        def safe_get(key, default=""):
            val = record.get(key)
            if val is None:
                val = default
            return str(val).replace("\\r\\n", "\\n").replace("\\r", "\\n").strip()

        # Check standard textual fields and combobox select values against original values
        if annotator != safe_get("annotator"): changed = True
        elif label != safe_get("label"): changed = True
        elif heading != safe_get("heading"): changed = True
        elif text != safe_get("text"): changed = True
        elif source != safe_get("source"): changed = True
        elif source_category != safe_get("source_category"): changed = True
        elif category != safe_get("category"): changed = True
        elif multi_cat != safe_get("multi_category"): changed = True
        elif confidence != safe_get("annotation_confidence", "100"): changed = True
        elif notes != safe_get("additional_notes"): changed = True
        
        # Check image selection list for differences if text comparison did not flag changes
        if not changed:
            # Parse saved image paths from CSV (splitting by semicolon and replacing backslashes for path normalization)
            orig_images = [p.strip().replace("\\", "/") for p in (record.get("image_path") or "").split(";") if p.strip()]
            
            # An altered list length immediately denotes modified assets lists
            if len(self.image_list) != len(orig_images):
                changed = True
            else:
                # Zip lists together and inspect path strings element by element
                for (path, pil_img), orig_rel_path in zip(self.image_list, orig_images):
                    # If path is None, it is a newly pasted screenshot image in memory, denoting changes
                    if path is None:
                        changed = True
                        break
                    try:
                        # Extract path relative to script directory to check against CSV storage pattern
                        rel = path.relative_to(SCRIPT_DIR)
                        if str(rel).replace("\\", "/") != orig_rel_path:
                            changed = True
                            break
                    except ValueError:
                        changed = True
                        break
                
            # Check video references for changes
            if not changed:
                orig_video = (record.get("video_path") or "").strip().replace("\\", "/")
                current_video = ""
                if self.video_path:
                    try:
                        current_video = str(self.video_path.relative_to(SCRIPT_DIR)).replace("\\", "/")
                    except ValueError:
                        # Video path outside the local folder workspace signals a new upload change
                        changed = True
                
                # Check for updates to the video path reference
                if not changed and orig_video != current_video:
                    changed = True

        # If no edits are detected, proceed with navigation
        if not changed:
            return True
            
        # Prompt user with an action selection dialog for unsaved review edits
        response = self._custom_ask_yes_no_cancel(
            "Unsaved Changes",
            "You have unsaved changes in this record.\n\n"
            "Do you want to save them before moving?"
        )
        
        # User choice Yes: attempt to save the active record edits
        if response is True:
            # Update the CSV database silently (without showing the generic confirmation alert)
            save_ok = self._update_entry(show_success=False)
            if not save_ok:
                # If save fails due to validation errors, offer a fallback to discard changes
                # to prevent the user from being trapped in an infinite error loop.
                discard = self._custom_ask_yes_no(
                    "Save Failed",
                    "Could not save due to validation errors.\n\n"
                    "Do you want to discard your changes and continue?"
                )
                return discard
            return True
            
        # User choice No: discard modifications and allow navigation
        elif response is False:
            return True
            
        # User choice Cancel: remain on the current record
        else:
            return False

    def _next_record(self):
        """
        Navigates to the next record in the dataset subset.
        
        If currently in Re-label mode, delegates the navigation step to the kappa
        next record handler. Otherwise, verifies for unsaved edits in the active
        record. If safe, increments the review index pointer and displays the record.
        """
        # Route to the Kappa reliability navigation handler if the application is in Re-label mode
        if self.current_mode == "relabel":
            self._kappa_next_record()
            return
            
        # Ensure we are not already at the end of the loaded review subset
        if self.current_review_index < len(self.dataset_records) - 1:
            # Prompt user to resolve any unsaved changes before moving to the next record
            if not self._check_unsaved_changes():
                return
            # Increment index pointer and refresh UI layout fields with the next record
            self.current_review_index += 1
            self._display_record(self.current_review_index)

    def _prev_record(self):
        """
        Navigates to the previous record in the dataset subset.
        
        If currently in Re-label mode, delegates the navigation step to the kappa
        prev record handler. Otherwise, verifies index limits and checks for unsaved
        changes before decrementing the review index pointer and displaying the record.
        """
        # Route to the Kappa reliability navigation handler if the application is in Re-label mode
        if self.current_mode == "relabel":
            self._kappa_prev_record()
            return
            
        # Ensure we are not already at the beginning of the loaded review subset
        if self.current_review_index > 0:
            # Prompt user to resolve any unsaved changes before moving to the previous record
            if not self._check_unsaved_changes():
                return
            # Decrement index pointer and refresh UI layout fields with the previous record
            self.current_review_index -= 1
            self._display_record(self.current_review_index)

    def _jump_to_record(self, event=None):
        """
        Navigates directly to a record specified by the integer input in the navigation box.
        
        Converts the 1-based user input into a 0-based index. Validates the index bounds,
        verifies for unsaved edits, updates the review pointer, and displays the record.
        Reverts the navigation input box to the current index if invalid.
        """
        # Route to the Kappa reliability jump handler if the application is in Re-label mode
        if self.current_mode == "relabel":
            self._kappa_jump_to_record(event)
            return
            
        try:
            # Parse the user entry value as a 1-based record number
            val = int(self.record_index_entry.get().strip())
            # Convert to zero-based array index
            idx = val - 1
            
            # Ensure the targeted index lies within the boundaries of the active review list
            if 0 <= idx < len(self.dataset_records):
                # Only execute jump operations if the target index differs from the active one
                if self.current_review_index != idx:
                    # Check for unsaved changes before executing the index jump
                    if not self._check_unsaved_changes():
                        # Revert input entry text back to the active record number on navigation cancel
                        self.record_index_entry.delete(0, "end")
                        self.record_index_entry.insert(0, str(self.current_review_index + 1))
                        self.focus_set()
                        return
                    # Update index pointer and draw record data
                    self.current_review_index = idx
                    self._display_record(self.current_review_index)
                # Release keyboard focus from the input field to prevent cursor navigation conflicts
                self.focus_set()
            else:
                # Revert to current record indicator if user inputs an out-of-range index
                self.record_index_entry.delete(0, "end")
                self.record_index_entry.insert(0, str(self.current_review_index + 1))
                messagebox.showwarning("Invalid Record", f"Please enter a number between 1 and {len(self.dataset_records)}.")
        except ValueError:
            # Revert to current record indicator if user inputs a non-integer string
            self.record_index_entry.delete(0, "end")
            self.record_index_entry.insert(0, str(self.current_review_index + 1))

    def _update_entry(self, show_success=True):
        """
        Validates the UI input fields and commits changes to the current database record.
        
        Performs field requirement checks (e.g. category, source, non-empty media/text content).
        Copies any new external files (images or video clips) into local project storage sub-folders,
        generating unique filenames containing labels, counts, entry UUIDs, and annotator names.
        Saves new screenshots directly as PNGs.
        Rewrites the main database CSV file, updates dynamic filters, and updates the stats bar.
        
        Args:
            show_success: If True, displays a completion alert popup window.
            
        Returns:
            bool: True if validation and disk saving succeeded, False otherwise.
        """
        # Abort if there are no loaded review records in memory
        if not self.dataset_records:
            return False

        # Gather current string values from workspace widgets
        annotator = self.annotator_entry.get().strip()
        label = self.label_var.get()
        heading = self.heading_entry.get("1.0", "end-1c").strip()
        text = self.text_box.get("1.0", "end-1c").strip()
        source = self.source_entry.get().strip()
        source_category = self.source_cat_var.get()
        category = self.category_var.get()
        multi_cat = self.multi_cat_var.get()
        confidence_str = self.confidence_entry.get().strip()
        
        # Check for media attachments presence
        has_image = len(self.image_list) > 0
        has_media = has_image or (self.video_path is not None)

        # Enforce validation checks on mandatory inputs
        errors = []
        if not annotator:
            errors.append("Annotator name is required.")
        if not label:
            errors.append("Label (Fake/Real) must be selected.")
        if label == "Fake" and not multi_cat:
            errors.append("Fake News Type must be selected.")
        if not category:
            errors.append("News Category is required.")
        if not source_category:
            errors.append("Source Category is required.")
        # Ensure there is at least one modal source (text description or file attachments)
        if not text and not has_media:
            errors.append("At least one of Text, Image, or Video must be provided.")

        # Parse and validate the confidence score field
        confidence = 100
        if confidence_str:
            try:
                confidence = int(confidence_str)
                # Bounded percentage value checks
                if not (0 <= confidence <= 100):
                    errors.append("Annotation Confidence must be between 0 and 100.")
            except ValueError:
                errors.append("Annotation Confidence must be a valid integer.")

        # Show verification errors to the user and abort transaction if validation failed
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return False

        # Map Fake News Type subclass value to Real if the authenticity label is set to Real
        if label == "Real":
            multi_cat = "Real"

        # Retrieve entry ID and sanitize the annotator name for safe filename conversions
        record = self.dataset_records[self.current_review_index]
        entry_id = record.get("id") or generate_id()
        sanitized_annotator = sanitize_name(annotator)

        # Process image attachments list (keeping local paths, copying new uploads, writing screen captures)
        try:
            image_rel_paths = []
            for path, pil_img in self.image_list:
                if path:
                    try:
                        # If the path is already inside the local script folder, retain relative path format
                        rel = path.relative_to(SCRIPT_DIR)
                        image_rel_paths.append(str(rel).replace("\\", "/"))
                    except ValueError:
                        # Copy new external image files into the images sub-folder
                        img_count = get_image_count() + 1
                        ext = path.suffix.lower()
                        # Construct a unique, standard filename
                        img_filename = f"{label}_{img_count:05d}_{entry_id}_{sanitized_annotator}{ext}"
                        img_dest = IMAGES_DIR / img_filename
                        shutil.copy2(path, img_dest)
                        image_rel_paths.append(f"images/{img_filename}")
                else:
                    # Write pasted screenshot image objects directly to local disk as PNGs
                    img_count = get_image_count() + 1
                    img_filename = f"{label}_{img_count:05d}_{entry_id}_{sanitized_annotator}.png"
                    img_dest = IMAGES_DIR / img_filename
                    src_img = pil_img
                    # Ensure compatibility with RGB formatting
                    if src_img.mode == "RGBA":
                        src_img = src_img.convert("RGB")
                    src_img.save(img_dest)
                    image_rel_paths.append(f"images/{img_filename}")
    
            # Process video files attachments (copying external files if applicable)
            video_rel_path = ""
            if self.video_path:
                try:
                    # Retain relative path format if video is already located inside the project folders
                    rel = self.video_path.relative_to(SCRIPT_DIR)
                    video_rel_path = str(rel).replace("\\", "/")
                except ValueError:
                    # Copy external video file into the videos directory
                    vid_count = get_video_count() + 1
                    ext = self.video_path.suffix.lower()
                    # Construct a unique standard video filename
                    vid_filename = f"{label}_{vid_count:05d}_{entry_id}_{sanitized_annotator}{ext}"
                    vid_dest = VIDEOS_DIR / vid_filename
                    shutil.copy2(self.video_path, vid_dest)
                    video_rel_path = f"videos/{vid_filename}"
    
            # Assign modified UI values back to the active record dictionary
            record["annotator"] = annotator
            record["label"] = label
            record["heading"] = heading
            record["text"] = text
            record["source"] = source
            record["source_category"] = source_category
            record["category"] = category
            record["multi_category"] = multi_cat
            record["annotation_confidence"] = str(confidence)
            record["additional_notes"] = self.notes_entry.get("0.0", "end-1c").strip()
            record["image_path"] = ";".join(image_rel_paths)
            record["video_path"] = video_rel_path
            
            # Maintain original save timestamp or populate if missing
            if "timestamp" not in record or not record.get("timestamp"):
                record["timestamp"] = datetime.now().isoformat()
    
            # Commit the updated list values to dataset.csv
            self._rewrite_csv()
        except Exception as e:
            # Notify on OS-level errors (like files locked by external editors)
            messagebox.showerror("Update Error", f"Failed to update entry. Please make sure the dataset CSV file is not open in Excel or another program.\n\nError: {e}")
            return False

        # Re-apply filters to refresh the active records list (and automatically filter out records that no longer match)
        self._apply_advanced_filter(keep_index=True)
        
        # Display completion alert window if requested
        if show_success:
            messagebox.showinfo("Update Complete",
                f"Record {self.current_review_index + 1} updated successfully!")
        return True

    def _delete_entry(self):
        """
        Deletes the currently displayed record from the database after confirmation.
        
        Pops the record from the active subset and general list, rewrites the dataset CSV, 
        and updates active indices. Returns to Annotate mode if no entries remain.
        """
        # Abort if there are no loaded review records in memory
        if not self.dataset_records:
            return

        # Double check delete intent by prompting a warning dialog window
        confirm = self._custom_ask_yes_no("Confirm Delete",
            f"Are you sure you want to delete Record {self.current_review_index + 1}?\n\n"
            "This action cannot be undone.")
        if not confirm:
            return

        # Pop the target record from the active review subset list
        deleted_record = self.dataset_records.pop(self.current_review_index)
        
        # Locate the record's index in the master dataset tracking array by matching unique entry IDs
        all_idx = next((i for i, r in enumerate(self.all_dataset_records) if (r.get("id") or "") == (deleted_record.get("id") or "")), -1)
        if all_idx >= 0:
            # Pop the record from the master tracking list in memory
            self.all_dataset_records.pop(all_idx)

        # Attempt to save the deletion modification to disk
        try:
            self._rewrite_csv()
        except Exception as e:
            # Rollback layout lists in memory if the save operation fails (e.g. permission lock errors)
            # to protect data integrity and avoid sync discrepancies.
            self.dataset_records.insert(self.current_review_index, deleted_record)
            if all_idx >= 0:
                self.all_dataset_records.insert(all_idx, deleted_record)
            messagebox.showerror("Delete Error", f"Failed to delete entry. Please make sure the dataset CSV file is not open in Excel or another program.\n\nError: {e}")
            return

        # Re-apply filter settings to refresh review index pointers and layout lists
        self._apply_advanced_filter(keep_index=True)

        # Revert view back to Annotate Mode if no records remain in the database
        if not self.all_dataset_records:
            messagebox.showinfo("No Records", "All records have been deleted.")
            self.mode_switcher.set("📝 Annotate")
            self._toggle_mode("📝 Annotate")
            return

    def _rewrite_csv(self):
        """
        Rewrites the entire dataset CSV file from the general records database list.
        """
        # Invalidate global duplicates cache since the dataset content has changed
        self._cancel_duplicate_computing = True
        if hasattr(self, '_duplicate_computing'):
            self._duplicate_computing = False
        self._duplicate_pairs_cache = None
        self._cached_records_data = None
        self.after(200, lambda: self._compute_global_duplicates(force_restart=True))

        # Open CSV file with standard settings: newline protection and utf-8 encoding support

        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            # Construct standard writer, ignoring extra unexpected keys in record dictionaries
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            # Write column headers row first
            writer.writeheader()
            # Serialize each record dictionary to file rows sequentially
            for record in self.all_dataset_records:
                writer.writerow(record)
                
        # Update last loaded details
        try:
            self._last_loaded_csv_mtime = CSV_PATH.stat().st_mtime
            self._last_loaded_csv_size = CSV_PATH.stat().st_size
        except Exception:
            pass

