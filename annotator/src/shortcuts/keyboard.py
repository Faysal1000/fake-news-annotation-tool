"""
ShortcutMixin mixin class.
"""

import customtkinter as ctk
import tkinter as tk
import webbrowser
from urllib.parse import quote_plus

class ShortcutMixin:
    def _setup_shortcuts(self):
        """
        Registers productivity shortcuts for Review and Re-label modes.
        """
        for sequence in ("<Control-s>", "<Control-S>", "<Command-s>", "<Command-S>"):
            self.bind_all(sequence, self._shortcut_save_and_next)

        for sequence in ("<Control-d>", "<Control-D>", "<Command-d>", "<Command-D>"):
            self.bind_all(sequence, self._shortcut_delete_record)

        self.bind_all("<Left>", self._shortcut_prev_record)
        self.bind_all("<Right>", self._shortcut_next_record)

    def _shortcut_event_is_for_main_window(self, event=None):
        """
        Returns False when focus is inside a child popup instead of the main app window.
        """
        try:
            if event is not None and hasattr(event, "widget"):
                return str(event.widget.winfo_toplevel()) == str(self)

            focused = self.focus_get()
            if focused is None:
                return True
            return str(focused.winfo_toplevel()) == str(self)
        except tk.TclError:
            return False

    def _focused_widget_is_text_input(self):
        """
        Detects focused text entry widgets so arrow shortcuts do not steal cursor movement.
        """
        try:
            focused = self.focus_get()
            if focused is None:
                return False
            widget_class = (focused.winfo_class() or "").lower()
            return "entry" in widget_class or "text" in widget_class or "spinbox" in widget_class
        except tk.TclError:
            return False

    def _shortcut_save_and_next(self, event=None):
        """
        Saves the current Review/Re-label decision and moves to the next record when possible.
        """
        if not self._shortcut_event_is_for_main_window(event):
            return None

        if self.current_mode == "review":
            record_id = ""
            if self.dataset_records and 0 <= self.current_review_index < len(self.dataset_records):
                record_id = self.dataset_records[self.current_review_index].get("id") or ""

            if self._update_entry(show_success=False):
                active_id = ""
                if self.dataset_records and 0 <= self.current_review_index < len(self.dataset_records):
                    active_id = self.dataset_records[self.current_review_index].get("id") or ""

                if record_id and active_id and active_id != record_id:
                    return "break"

                if self.current_review_index < len(self.dataset_records) - 1:
                    self._next_record()
                else:
                    self.status_label.configure(text="Record updated. You are at the last record.", text_color="#2ecc71")
            return "break"

        if self.current_mode == "relabel":
            self._save_kappa_decision(auto_advance=True)
            return "break"

        return None

    def _shortcut_prev_record(self, event=None):
        """
        Navigates to the previous record from the keyboard in Review/Re-label modes.
        """
        if not self._shortcut_event_is_for_main_window(event) or self._focused_widget_is_text_input():
            return None

        if self.current_mode in ("review", "relabel"):
            self._prev_record()
            return "break"

        return None

    def _shortcut_next_record(self, event=None):
        """
        Navigates to the next record from the keyboard in Review/Re-label modes.
        """
        if not self._shortcut_event_is_for_main_window(event) or self._focused_widget_is_text_input():
            return None

        if self.current_mode in ("review", "relabel"):
            self._next_record()
            return "break"

        return None

    def _shortcut_delete_record(self, event=None):
        """
        Deletes the active record from Review mode via Cmd/Ctrl+D.
        """
        if not self._shortcut_event_is_for_main_window(event):
            return None

        if self.current_mode == "review":
            self._delete_entry()
            return "break"

        return None

    def _get_heading_text(self):
        """
        Returns the current heading textbox content.
        """
        return self.heading_entry.get("1.0", "end-1c").strip()

    def _open_heading_search(self):
        """
        Opens a Google search for the current heading in the default system browser.
        """
        heading = self._get_heading_text()
        if not heading:
            self._update_heading_search_visibility()
            return

        webbrowser.open(f"https://www.google.com/search?q={quote_plus(heading)}", new=2)

