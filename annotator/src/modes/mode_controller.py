"""
ModeControllerMixin mixin class.
"""

import customtkinter as ctk
from tkinter import messagebox

class ModeControllerMixin:
    def _toggle_mode(self, mode_name):
        """
        Manages transitions between Annotate, Review, and Re-label modes.
        
        This method acts as a router/coordinator when switching between application views.
        Before completing a switch, it checks for unsaved changes in the active mode
        and prompts the user appropriately. On successful confirmation, it performs
        the following setup steps:
        - Annotate mode: Restores the cached layout grid, switches primary buttons 
          to "Save Entry", recovers draft inputs, and updates statistics.
        - Review mode: Ingests the primary CSV database, updates primary buttons to 
          "Update Entry", reveals record navigation controls, and applies active filters.
        - Re-label mode: Ingests the kappa reliability dataset, makes primary article
          fields read-only, hides secondary inputs (like category or confidence), 
          adjusts container widths, and searches for the first unlabeled record.
        """
        # Save reference of the mode we are switching away from
        previous_mode = self.current_mode

        # Case 1: Switching to standard Annotate Mode
        if "Annotate" in mode_name:
            # If the application is already in annotate mode, do nothing
            if self.current_mode == "annotate":
                return
            
            # If leaving Review mode, check for unsaved edits on the active record first
            if self.current_mode == "review":
                if not self._check_unsaved_changes():
                    # Revert the dropdown selector if the user aborted the switch
                    self.mode_switcher.set("🔍 Review")
                    return
            
            # If leaving Re-label mode, check for unsaved decisions on the active reliability record
            if self.current_mode == "relabel":
                if not self._check_unsaved_kappa_changes():
                    # Revert the dropdown selector if the user aborted the switch
                    self.mode_switcher.set("🔄 Re-label")
                    return
                # Restore editing layouts modified specifically for Re-label mode
                self._exit_relabel_mode()
            
            # Set the internal state indicator to annotate mode
            self.current_mode = "annotate"
            
            # Hide navigation panels and filter/search settings widgets from the top bar
            self.nav_frame.grid_forget()
            self.filter_btn.pack_forget()
            self.filter_indicator.pack_forget()
            self.search_btn.pack_forget()
            
            # Hide UUID display and restore category stats in Annotate mode
            self.uuid_display_frame.pack_forget()
            self.category_stats_frame.pack(fill="x", pady=(0, 6), after=self.stats_frame)
            
            # Configure primary button to trigger entry save logic
            self.primary_btn.configure(text="💾  Save Entry", command=self._save_entry)
            self.primary_btn.pack_configure(padx=(0, 8))
            
            # Re-enable the secondary 'Clear All' button next to the save button
            self.secondary_btn.configure(text="🗑  Clear All", command=self._clear_all,
                                           fg_color="#444", hover_color="#555")
            self.secondary_btn.pack(side="left")
            
            # Restore regular annotation layouts, reload draft changes if cached, and refresh statistics
            self._restore_annotate_fields()
            self._restore_draft()
            self._update_stats()
            
        # Case 2: Switching to Review Mode (browsing previously saved records)
        elif "Review" in mode_name:
            # If the application is already in review mode, do nothing
            if self.current_mode == "review":
                return
            
            # Ensure any incomplete annotations in Annotate mode are saved or discarded
            if self.current_mode == "annotate":
                if not self._check_unsaved_annotate_changes():
                    self.mode_switcher.set("📝 Annotate")
                    return
            
            # Ensure any incomplete blind ratings in Re-label mode are resolved
            if self.current_mode == "relabel":
                if not self._check_unsaved_kappa_changes():
                    self.mode_switcher.set("🔄 Re-label")
                    return
                self._exit_relabel_mode()
            
            # Set the internal state indicator to review mode
            self.current_mode = "review"
            
            # Restore normal input fields that might have been hidden by Re-label mode
            self._restore_annotate_fields()
            
            # Load entries from the database file
            self._load_dataset()
            
            # If there are no saved records in dataset.csv, return to Annotate mode
            if not self.all_dataset_records:
                messagebox.showinfo("No Data",
                    "No entries found in dataset.csv.\nAnnotate some entries first!")
                self.mode_switcher.set("📝 Annotate")
                self.current_mode = "annotate"
                self._restore_draft()
                self._update_stats()
                return
                
            # Configure primary action button to trigger update modifications
            self.primary_btn.configure(text="💾  Update Entry", command=self._update_entry)
            self.primary_btn.pack_configure(padx=(0, 8))
            
            # Reconfigure secondary action button to serve as a delete button
            self.secondary_btn.configure(text="🗑  Delete", command=self._delete_entry,
                                          fg_color="#e74c3c", hover_color="#c0392b")
            self.secondary_btn.pack(side="left")
            
            # Make the record navigation bar, filter, and search widgets visible
            self.nav_frame.grid(row=0, column=0, sticky="ew", padx=(8, 8), pady=6)
            self.filter_btn.pack(side="right", padx=(4, 0))
            self.search_btn.pack(side="right", padx=(4, 0))
            self._update_filter_indicator()
            
            # Hide category stats and show UUID display in Review mode
            self.category_stats_frame.pack_forget()
            self.uuid_display_frame.pack(fill="x", pady=(0, 6), after=self.stats_frame)
            
        # Case 3: Switching to Re-label (Kappa reliability check) Mode
        elif "Re-label" in mode_name:
            # If the application is already in relabel mode, do nothing
            if self.current_mode == "relabel":
                return
            
            # Ensure any unsaved reviews are committed or discarded first
            if self.current_mode == "review":
                if not self._check_unsaved_changes():
                    self.mode_switcher.set("🔍 Review")
                    return
            
            # Ensure any incomplete workspace entries in Annotate mode are resolved
            if self.current_mode == "annotate":
                if not self._check_unsaved_annotate_changes():
                    self.mode_switcher.set("📝 Annotate")
                    return
            
            # Set the internal state indicator to relabel mode
            self.current_mode = "relabel"
            
            # Trigger layout transformations and load the Kappa CSV file
            self._enter_relabel_mode()

