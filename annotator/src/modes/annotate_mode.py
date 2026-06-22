"""
AnnotateModeMixin mixin class.
"""

import customtkinter as ctk
from tkinter import messagebox
import json
import csv
from datetime import datetime
import shutil
from pathlib import Path
from app_paths import CSV_PATH, IMAGES_DIR, VIDEOS_DIR, SCRIPT_DIR
from constants import CSV_COLUMNS, CATEGORIES, SOURCE_CATEGORIES, MULTI_CATEGORIES
from data.config_manager import save_config, sanitize_name
from data.csv_manager import generate_id
from data.stats_engine import get_image_count, get_video_count

class AnnotateModeMixin:
    def _set_label(self, value):
        """
        Sets the active label variable (Fake / Real) and updates button highlighting.
        """
        self.label_var.set(value)
        self._update_label_toggles()
        self._on_label_change()

    def _update_label_toggles(self):
        """
        Dynamically applies color themes to authenticity select toggles when selected.
        Red highlighting is used for Fake authenticity, green for Real authenticity.
        """
        selected = self.label_var.get()
        if selected == "Fake":
            self.fake_toggle_btn.configure(
                fg_color="#4a1a1a", border_color="#e74c3c",
                text_color="#e74c3c"
            )
            self.real_toggle_btn.configure(
                fg_color="transparent", border_color="#555",
                text_color="#888"
            )
        elif selected == "Real":
            self.real_toggle_btn.configure(
                fg_color="#1a4a1a", border_color="#2ecc71",
                text_color="#2ecc71"
            )
            self.fake_toggle_btn.configure(
                fg_color="transparent", border_color="#555",
                text_color="#888"
            )
        else:
            self.fake_toggle_btn.configure(
                fg_color="transparent", border_color="#555",
                text_color="#888"
            )
            self.real_toggle_btn.configure(
                fg_color="transparent", border_color="#555",
                text_color="#888"
            )

    def _on_label_change(self):
        """
        Displays the multi-category type selector frame if Fake is selected.
        Hides the category type frame and resets options if Real is selected.
        """
        if self.label_var.get() == "Fake":
            if self.current_mode == "relabel":
                self.multi_cat_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8),
                                           after=self.fake_toggle_btn.master)
            else:
                self.multi_cat_frame.pack(fill="x", expand=False, padx=12, pady=(0, 8),
                                           after=self.fake_toggle_btn.master)
        else:
            self.multi_cat_frame.pack_forget()
            self.multi_cat_var.set("")
        self._update_label_toggles()

    def _on_annotator_name_change(self):
        """
        Saves user credentials to local settings files and refreshes dashboard statistics when modified.
        """
        name = self.annotator_entry.get().strip()
        if self.current_mode == "annotate":
            save_config(name)
        elif self.current_mode == "relabel":
            save_config(name)
            self._update_kappa_stats()

    def _save_entry(self):
        """
        Validates input fields, processes attached media files, and appends the annotated record
        to the local CSV dataset.
        
        The save workflow consists of:
        1. Extracting values from input entries.
        2. Enforcing structural validations (checking for name, category, source category, 
           label selection, and requiring either text or media).
        3. Warning users about short text inputs (under 10 words).
        4. Storing attachments inside images/ and videos/ subfolders using structured filenames 
           conforming to naming templates.
        5. Appending a standardized row to dataset.csv, writing the header first if the file is new.
        6. Preserving the annotator's name in configuration files and resetting fields.
        """
        annotator = self.annotator_entry.get().strip()
        label = self.label_var.get()
        heading = self.heading_entry.get("1.0", "end-1c").strip()  
        text = self.text_box.get("1.0", "end-1c").strip()  
        source = self.source_entry.get().strip()
        source_category = self.source_cat_var.get()  
        category = self.category_var.get()
        multi_cat = self.multi_cat_var.get()  
        confidence_str = self.confidence_entry.get().strip()
        has_image = len(self.image_list) > 0
        has_media = has_image or (self.video_path is not None)

        # Enforce validation rules
        errors = []
        if not annotator:
            errors.append("Annotator name is required.")
        if not label:
            errors.append("Label (Fake/Real) must be selected.")
        if label == "Fake" and not multi_cat:
            errors.append("Fake News Type (Misinformation/Satire/Clickbait) must be selected.")
        if not category:
            errors.append("News Category is required.")
        if not source_category:
            errors.append("Source Category is required.")
        if not text and not has_media:
            errors.append("At least one of Text, Image, or Video must be provided.")

        # Ensure confidence ratings represent valid integer values between 0 and 100
        confidence = 100
        if not confidence_str:
            confidence = 100
        else:
            try:
                confidence = int(confidence_str)
                if not (0 <= confidence <= 100):
                    errors.append("Annotation Confidence must be an integer between 0 and 100.")
            except ValueError:
                errors.append("Annotation Confidence must be a valid integer between 0 and 100.")

        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return

        # Check duplicates in Annotate Mode on Save
        if self.current_mode == "annotate":
            matches = self._check_duplicates_for_saving(heading, text)
            if matches:
                self._show_duplicate_save_warning(
                    matches,
                    lambda: self._proceed_with_save(
                        annotator, label, heading, text, source, source_category,
                        category, multi_cat, confidence, has_image, has_media
                    )
                )
                return

        self._proceed_with_save(
            annotator, label, heading, text, source, source_category,
            category, multi_cat, confidence, has_image, has_media
        )

    def _proceed_with_save(self, annotator, label, heading, text, source, source_category, category, multi_cat, confidence, has_image, has_media):
        # Automatically map Real news classification subtype to Real
        if label == "Real":
            multi_cat = "Real"

        # Present warning confirmation if textual content is short
        if text and len(text.split()) < 10:
            proceed = messagebox.askyesno(
                "Short Text Warning",
                f"The text has only {len(text.split())} word(s). Are you sure you want to save?"
            )
            if not proceed:
                return

        # Generate unique database entry ID
        entry_id = generate_id()
        sanitized_annotator = sanitize_name(annotator)
        image_rel_paths = []

        try:
            # Transfer images to images directory using template patterns
            if has_image:
                for path, pil_img in self.image_list:
                    img_count = get_image_count() + 1
    
                    if path:
                        ext = path.suffix.lower()
                    else:
                        ext = ".png"
    
                    img_filename = f"{label}_{img_count:05d}_{entry_id}_{sanitized_annotator}{ext}"
                    img_dest = IMAGES_DIR / img_filename
    
                    if path:
                        shutil.copy2(path, img_dest)
                    else:
                        src_img = pil_img
                        # JPEGs do not support transparency layers; drop alpha if copying to JPEG
                        if src_img.mode == "RGBA" and ext in (".jpg", ".jpeg"):
                            src_img = src_img.convert("RGB")
                        src_img.save(img_dest)
    
                    image_rel_paths.append(f"images/{img_filename}")
    
            image_path_str = ";".join(image_rel_paths)
            
            # Transfer video files if registered
            video_rel_path = ""
            if self.video_path:
                vid_count = get_video_count() + 1
                ext = self.video_path.suffix.lower()
                vid_filename = f"{label}_{vid_count:05d}_{entry_id}_{sanitized_annotator}{ext}"
                vid_dest = VIDEOS_DIR / vid_filename
                shutil.copy2(self.video_path, vid_dest)
                video_rel_path = f"videos/{vid_filename}"
    
            # Open the CSV file and write data, initializing headers if file is empty
            file_has_content = CSV_PATH.exists() and CSV_PATH.stat().st_size > 0
            with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
                if not file_has_content:
                    writer.writeheader()
                writer.writerow({
                    "id": entry_id,
                    "heading": heading,
                    "text": text,
                    "image_path": image_path_str,
                    "video_path": video_rel_path,
                    "label": label,
                    "multi_category": multi_cat,
                    "source": source,
                    "source_category": source_category,
                    "category": category,
                    "annotator": annotator,
                    "annotation_confidence": str(confidence),
                    "additional_notes": self.notes_entry.get("0.0", "end-1c").strip(),
                    "timestamp": datetime.now().isoformat(),
                })
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save data. Please check if the dataset file is currently locked.\n\nError: {e}")
            return

        save_config(annotator)
        self.status_label.configure(text=f"Entry saved successfully!", text_color="#2ecc71")
        
        # Add the new record to the in-memory list so duplicate checks include it
        new_record = {
            "id": entry_id,
            "heading": heading,
            "text": text,
            "image_path": image_path_str,
            "video_path": video_rel_path,
            "label": label,
            "multi_category": multi_cat,
            "source": source,
            "source_category": source_category,
            "category": category,
            "annotator": annotator,
            "annotation_confidence": str(confidence),
            "additional_notes": self.notes_entry.get("0.0", "end-1c").strip(),
            "timestamp": datetime.now().isoformat(),
        }
        self.all_dataset_records.append(new_record)
        
        # Invalidate duplicate cache so it recomputes with the new record
        self._cancel_duplicate_computing = True
        self._duplicate_pairs_cache = None
        
        self._update_stats()
        self._clear_fields()
        messagebox.showinfo("Save Complete", f"Entry saved successfully!\nID: {entry_id}")

    def _clear_fields(self):
        """
        Resets input controllers to their default values, skipping the annotator name.
        Hides context-dependent panels and clears attachments from preview frames.
        """
        self.text_box.delete("1.0", "end")       
        self.heading_entry.delete("1.0", "end")       
        self.source_entry.delete(0, "end")         
        self.notes_entry.delete("0.0", "end")      
        self.label_var.set("")                      
        self._update_label_toggles()                 
        self.category_var.set("")                   
        self.source_cat_var.set("")                  
        self.multi_cat_var.set("")                   
        self.multi_cat_frame.pack_forget()           
        self._remove_all_images()                   
        self.confidence_entry.delete(0, "end")      
        self.confidence_entry.insert(0, "100")      
        self._update_heading_search_visibility()
        self._hide_duplicate_warnings()

    def _clear_all(self):
        """
        Clears workspace fields. Maintains annotator identifiers for productivity.
        """
        self._clear_fields()
        self.status_label.configure(text="All fields cleared", text_color="#888")

    def _has_unsaved_annotate_work(self):
        """
        Verifies if input controls in Annotate mode contain modifications relative to
        an empty form.
        """
        if self.current_mode != "annotate":
            return False
        
        if self.label_var.get() != "": return True
        if self.heading_entry.get("1.0", "end-1c").strip() != "": return True
        if self.text_box.get("1.0", "end-1c").strip() != "": return True
        if self.source_entry.get().strip() != "": return True
        if self.source_cat_var.get() != "": return True
        if self.category_var.get() != "": return True
        if self.multi_cat_var.get() != "": return True
        if self.confidence_entry.get().strip() not in ("", "100"): return True
        if self.notes_entry.get("0.0", "end-1c").strip() != "": return True
        if len(self.image_list) > 0: return True
        if self.video_path is not None: return True
        
        return False

    def _on_closing(self):
        """
        Intercepts closure signals. Prompts validation alerts depending on active work modes
        to shield annotators from unsaved changes.
        """
        if self.current_mode == "review":
            if not self._check_unsaved_changes():
                return
        elif self.current_mode == "relabel":
            if not self._check_unsaved_kappa_changes():
                return
        elif self.current_mode == "annotate":
            if self._has_unsaved_annotate_work():
                confirm = messagebox.askyesno(
                    "Unsaved Work",
                    "You have unsaved annotation work. Are you sure you want to exit without saving?"
                )
                if not confirm:
                    return
        self.destroy()

    def _save_draft(self):
        """
        Saves the current values of all annotation fields to a temporary draft cache.
        
        This cache prevents the annotator from losing in-progress work when toggling
        between Annotate mode and Review/Re-label modes.
        """
        # Take a snapshot of the workspace inputs and save them in memory
        self.draft_annotation = {
            "annotator": self.annotator_entry.get().strip(),
            "label": self.label_var.get(),
            "multi_cat": self.multi_cat_var.get(),
            "category": self.category_var.get(),
            "source_category": self.source_cat_var.get(),
            "source": self.source_entry.get().strip(),
            "heading": self.heading_entry.get("1.0", "end-1c").strip(),
            "text": self.text_box.get("1.0", "end-1c").strip(),
            "confidence": self.confidence_entry.get().strip(),
            "additional_notes": self.notes_entry.get("0.0", "end-1c").strip(),
            # Copy image_list reference to preserve pasted screenshots in memory
            "images": list(self.image_list),
            "video": self.video_path,
        }

    def _restore_draft(self):
        """
        Restores the cached draft annotation values to the UI input fields.
        
        This is called when returning to Annotate mode. If no draft has been cached,
        it resets all input fields to their defaults.
        """
        # If no draft is cached, just clear fields to their defaults and return
        if self.draft_annotation is None:
            self._clear_fields()
            return

        # Load draft and reset internal draft cache reference to release memory
        draft = self.draft_annotation
        self.draft_annotation = None

        # Wipe workspace controls first
        self._clear_fields()
        
        # Populate annotator name entry field
        self.annotator_entry.delete(0, "end")
        self.annotator_entry.insert(0, draft["annotator"])

        # Populate label fields and trigger updates
        if draft["label"]:
            self.label_var.set(draft["label"])
            self._on_label_change()

        # Populate subtype dropdown menu options if applicable
        if draft["multi_cat"]:
            self.multi_cat_var.set(draft["multi_cat"])

        # Set category and source drop-down variables
        self.category_var.set(draft["category"])
        self.source_cat_var.set(draft["source_category"])

        # Populate source description input
        self.source_entry.delete(0, "end")
        self.source_entry.insert(0, draft["source"])

        # Restore heading title text content
        self.heading_entry.delete("1.0", "end")
        if draft["heading"]:
            self.heading_entry.insert("1.0", draft["heading"])

        # Restore body text description content
        self.text_box.delete("1.0", "end")
        if draft["text"]:
            self.text_box.insert("1.0", draft["text"])

        # Restore confidence rating value
        self.confidence_entry.delete(0, "end")
        self.confidence_entry.insert(0, draft["confidence"] or "100")

        # Restore additional notes text area content
        self.notes_entry.delete("0.0", "end")
        notes = draft.get("additional_notes", "")
        if notes:
            self.notes_entry.insert("0.0", notes)

        # Restore attachments lists and refresh UI previews
        self.image_list = draft["images"]
        self.video_path = draft.get("video")
        self._refresh_previews()
        self._update_heading_search_visibility()

