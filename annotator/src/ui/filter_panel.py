"""
FilterMixin mixin class.
"""

import struct
import threading
from pathlib import Path

import customtkinter as ctk
from constants import CATEGORIES, SOURCE_CATEGORIES, MULTI_CATEGORIES


def _format_seconds(value):
    """Formats a duration in seconds for display, dropping a redundant ``.0``."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if f == int(f):
        return str(int(f))
    return f"{f:g}"


def _parse_seconds(text):
    """
    Parses a user-entered duration in seconds into a non-negative float.

    Returns None for blank input (meaning "no bound") or unparseable/negative
    values, so a bad entry is treated as no constraint rather than an error.
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value >= 0 else None


def _mp4_container_duration(path):
    """
    Reads the total duration of an MP4/MOV/M4V file by parsing its ``mvhd`` atom.

    This is a fast, dependency-free path for the ISO base media file format
    (the container used by .mp4/.mov/.m4v). It walks the top-level atom tree
    into ``moov`` and reads the movie header's timescale and duration fields,
    supporting both 32-bit (version 0) and 64-bit (version 1) layouts as well
    as extended 64-bit atom sizes.

    Args:
        path: Filesystem path to the video file.

    Returns:
        Duration in seconds as a float, or None if it could not be determined
        (e.g. the file is not an ISO-BMFF container or the header is missing).
    """
    try:
        file_size = path.stat().st_size
        with open(path, "rb") as f:

            def _walk(end):
                # Iterate sibling atoms within [current position, end)
                while f.tell() + 8 <= end:
                    start = f.tell()
                    header = f.read(8)
                    if len(header) < 8:
                        return None
                    size, atom_type = struct.unpack(">I4s", header)
                    if size == 1:
                        # 64-bit extended size follows the standard header
                        ext = f.read(8)
                        if len(ext) < 8:
                            return None
                        size = struct.unpack(">Q", ext)[0]
                    elif size == 0:
                        # Atom extends to the end of the file
                        size = end - start
                    if size < 8 or start + size > end:
                        return None

                    if atom_type in (b"moov", b"trak", b"mdia"):
                        # Descend into container atoms that hold the movie header
                        found = _walk(start + size)
                        if found is not None:
                            return found
                    elif atom_type == b"mvhd":
                        version = f.read(4)  # 1 byte version + 3 bytes flags
                        if len(version) < 4:
                            return None
                        if version[0] == 1:
                            payload = f.read(28)  # 8+8 dates, 4 timescale, 8 duration
                            if len(payload) < 28:
                                return None
                            timescale = struct.unpack(">I", payload[16:20])[0]
                            duration = struct.unpack(">Q", payload[20:28])[0]
                        else:
                            payload = f.read(16)  # 4+4 dates, 4 timescale, 4 duration
                            if len(payload) < 16:
                                return None
                            timescale = struct.unpack(">I", payload[8:12])[0]
                            duration = struct.unpack(">I", payload[12:16])[0]
                        # A zero movie-header duration means the real length lives in
                        # the track headers or in fragments; report it as unknown so
                        # the caller falls back to the OpenCV probe.
                        if timescale and duration:
                            return duration / timescale
                        return None

                    f.seek(start + size)
                return None

            return _walk(file_size)
    except Exception:
        return None


def _cv2_duration(path):
    """
    Reads a video's duration using OpenCV's FFmpeg backend.

    This is the general-purpose fallback that handles every container FFmpeg
    understands (mkv, avi, webm, flv, ts, wmv, ...), computing duration from the
    reported frame count divided by frame rate. OpenCV is imported lazily so the
    application still launches when the optional dependency is unavailable.

    Args:
        path: Filesystem path to the video file.

    Returns:
        Duration in seconds as a float, or None if it could not be determined.
    """
    try:
        import cv2
    except Exception:
        return None
    cap = None
    try:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps and fps > 0 and frames and frames > 0:
            return frames / fps
    except Exception:
        pass
    finally:
        if cap is not None:
            cap.release()
    return None


class FilterMixin:
    def _probe_video_duration(self, rel_path):
        """
        Resolves a record's video path and returns its duration in seconds.

        Uses the fast, dependency-free MP4/MOV atom parser first and falls back
        to OpenCV for any other container. The result (including None for files
        that are missing or unreadable) is intended to be cached by the caller so
        each physical file is only probed once per session.

        Args:
            rel_path: The record's ``video_path`` value (relative to the app
                directory, e.g. ``videos/clip.mp4``, or an absolute path).

        Returns:
            Duration in seconds as a float, or None if it is unknown.
        """
        from app_paths import SCRIPT_DIR

        rel_path = (rel_path or "").strip()
        if not rel_path:
            return None

        path = Path(rel_path)
        if not path.is_absolute():
            path = SCRIPT_DIR / rel_path

        try:
            if not path.exists():
                return None
        except OSError:
            return None

        if path.suffix.lower() in (".mp4", ".mov", ".m4v"):
            duration = _mp4_container_duration(path)
            if duration is not None:
                return duration

        return _cv2_duration(path)

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

            # Filter records by their attached video's duration (in seconds).
            # Durations are read from the session cache, which the filter popup
            # populates on a background thread before this method runs. Records
            # without a video, or whose duration is unknown, are excluded while a
            # duration filter is active.
            min_dur = filt.get("min_dur")
            max_dur = filt.get("max_dur")
            if min_dur is not None or max_dur is not None:
                lo = min_dur if min_dur is not None else 0.0
                hi = max_dur if max_dur is not None else float("inf")
                cache = getattr(self, "_video_duration_cache", {})

                def _dur_in_range(r):
                    rel = (r.get("video_path") or "").strip()
                    if not rel:
                        return False
                    dur = cache.get(rel)
                    if dur is None:
                        return False
                    return lo <= dur <= hi
                filtered = [r for r in filtered if _dur_in_range(r)]

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
            if f.get("min_dur") is not None or f.get("max_dur") is not None: count += 1
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
        pw, ph = 600, 680
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

        # Video Duration Range Selector
        # Restricts results to records whose attached video runs for a length (in
        # seconds) within the given bounds. Leaving a field blank means that bound
        # is unbounded. Applying this filter probes each video file, so the Apply
        # step shows a live progress bar (see _apply below).
        dur_frame = ctk.CTkFrame(scroll, fg_color="#222244", corner_radius=8,
                                 border_width=1, border_color="#444")
        dur_frame.pack(fill="x", pady=(6, 2))

        ctk.CTkLabel(dur_frame, text="Video Duration (seconds)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#ccc").pack(anchor="w", padx=10, pady=(6, 2))

        # Horizontal row holding the min and max duration entry fields
        dur_row = ctk.CTkFrame(dur_frame, fg_color="transparent")
        dur_row.pack(fill="x", padx=10, pady=(0, 4))

        # Minimum duration in seconds (blank = no lower bound)
        ctk.CTkLabel(dur_row, text="Min:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        min_dur_entry = ctk.CTkEntry(dur_row, width=70, height=26,
                                     font=ctk.CTkFont(size=12), justify="center",
                                     placeholder_text="0")
        min_dur_entry.pack(side="left", padx=(0, 16))
        _cur_min_dur = cur.get("min_dur")
        if _cur_min_dur is not None:
            min_dur_entry.insert(0, _format_seconds(_cur_min_dur))

        # Maximum duration in seconds (blank = no upper bound)
        ctk.CTkLabel(dur_row, text="Max:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        max_dur_entry = ctk.CTkEntry(dur_row, width=70, height=26,
                                     font=ctk.CTkFont(size=12), justify="center",
                                     placeholder_text="∞")
        max_dur_entry.pack(side="left")
        _cur_max_dur = cur.get("max_dur")
        if _cur_max_dur is not None:
            max_dur_entry.insert(0, _format_seconds(_cur_max_dur))

        # Helper hint explaining blank-field semantics and the non-video exclusion
        ctk.CTkLabel(dur_frame,
                     text="Only records with a video in this length range are kept. "
                          "Leave a box empty for no limit.",
                     font=ctk.CTkFont(size=10), text_color="#888",
                     justify="left", wraplength=540).pack(anchor="w", padx=10, pady=(0, 8))

        # Action control buttons container frame positioned at the bottom of the modal
        btn_container = ctk.CTkFrame(popup, fg_color="transparent")
        btn_container.pack(fill="x", padx=12, pady=(4, 12))

        # Live progress area shown only while video durations are being probed on a
        # background thread. Created hidden; _apply packs it in during probing.
        progress_frame = ctk.CTkFrame(btn_container, fg_color="transparent")
        progress_label = ctk.CTkLabel(progress_frame, text="",
                                      font=ctk.CTkFont(size=12), text_color="#f39c12")
        progress_label.pack(anchor="w", pady=(0, 4))
        progress_bar = ctk.CTkProgressBar(progress_frame, height=14)
        progress_bar.pack(fill="x")
        progress_bar.set(0)

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

            # Clear the video duration bounds (blank = no limit)
            min_dur_entry.delete(0, "end")
            max_dur_entry.delete(0, "end")

        # Tracks the background probing thread's cancel request and busy state so
        # the popup cannot launch two probes at once or apply after being closed.
        probe_state = {"cancel": None, "busy": False}

        def _set_controls_enabled(enabled):
            """Enables or disables every action button during background probing."""
            state = "normal" if enabled else "disabled"
            for btn in (apply_btn, clear_all_btn, clear_filter_btn, cancel_btn):
                btn.configure(state=state)

        def _commit_filter():
            """Applies the already-built filter to the review list and closes the popup."""
            self._apply_advanced_filter()
            if popup.winfo_exists():
                popup.destroy()

        def _run_duration_probe(records_to_probe, on_complete):
            """
            Probes each pending video's duration on a background thread while a
            determinate progress bar reports live progress, keeping the UI
            responsive. Invokes on_complete() on the main thread when finished.
            """
            total = len(records_to_probe)
            cancel_event = threading.Event()
            probe_state["cancel"] = cancel_event
            probe_state["busy"] = True

            # Reveal the progress area and lock the action buttons for the run
            _set_controls_enabled(False)
            cancel_btn.configure(state="normal", text="Stop")
            progress_bar.set(0)
            progress_label.configure(
                text=f"Collecting video durations…  0 / {total}")
            progress_frame.pack(fill="x", pady=(0, 8), before=row1)

            def _report(done):
                # Marshalled onto the main thread to update the progress widgets
                if not progress_frame.winfo_exists():
                    return
                progress_bar.set(done / total if total else 1.0)
                progress_label.configure(
                    text=f"Collecting video durations…  {done} / {total}")

            def _finish(cancelled):
                # Runs on the main thread once probing ends or is cancelled
                probe_state["busy"] = False
                probe_state["cancel"] = None
                if cancelled:
                    if progress_frame.winfo_exists():
                        progress_frame.pack_forget()
                    if cancel_btn.winfo_exists():
                        cancel_btn.configure(text="Cancel")
                    _set_controls_enabled(True)
                    return
                if progress_label.winfo_exists():
                    progress_label.configure(text="Filtering…")
                if progress_bar.winfo_exists():
                    progress_bar.set(1.0)
                # Let the "Filtering…" frame paint before the (fast) apply runs
                self.after(60, on_complete)

            def _worker():
                for i, rec in enumerate(records_to_probe):
                    if cancel_event.is_set():
                        self.after(0, lambda: _finish(True))
                        return
                    rel = (rec.get("video_path") or "").strip()
                    duration = self._probe_video_duration(rel)
                    self._video_duration_cache[rel] = duration
                    done = i + 1
                    self.after(0, lambda d=done: _report(d))
                self.after(0, lambda: _finish(False))

            threading.Thread(target=_worker, daemon=True).start()

        def _apply():
            """
            Gathers the selected filters from the dialog checklist variables, confidence
            fields, and video-duration bounds, updates the application's advanced_filter,
            then applies it. When a duration filter is active, video files are probed on
            a background thread (with a live progress bar) before the filter is applied.
            """
            if probe_state["busy"]:
                return

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

            # Parse the video duration bounds (blank/invalid -> that side is unbounded)
            min_dur = _parse_seconds(min_dur_entry.get())
            max_dur = _parse_seconds(max_dur_entry.get())
            if min_dur is not None and max_dur is not None and min_dur > max_dur:
                min_dur, max_dur = max_dur, min_dur

            # Determine whether any active filter rules have been configured by checking selections
            notes_checked = has_notes_var.get()
            has_filter = (
                bool(sel_labels) or bool(sel_types) or bool(sel_cats) or
                bool(sel_src_cats) or bool(sel_annotators) or bool(sel_content_types) or
                notes_checked or mn > 0 or mx < 100 or
                min_dur is not None or max_dur is not None
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
                    "min_dur": min_dur,
                    "max_dur": max_dur,
                }
            else:
                self.advanced_filter = None

            # When a duration filter is set, probe any videos whose length we have
            # not measured yet (on a background thread) before applying.
            if min_dur is not None or max_dur is not None:
                pending = [
                    r for r in self.all_dataset_records
                    if (r.get("video_path") or "").strip()
                    and (r.get("video_path") or "").strip() not in self._video_duration_cache
                ]
                if pending:
                    _run_duration_probe(pending, _commit_filter)
                    return

            # No probing required: apply immediately and close
            _commit_filter()

        def _clear_and_apply():
            """
            Deactivates all filter parameters and closes the window immediately,
            restoring access to all records in the review queue.
            """
            if probe_state["busy"]:
                return
            self.advanced_filter = None
            _commit_filter()

        def _on_cancel():
            """
            Stops an in-progress duration probe if one is running, otherwise closes
            the popup without applying any changes.
            """
            cancel_event = probe_state.get("cancel")
            if probe_state["busy"] and cancel_event is not None:
                cancel_event.set()
                return
            popup.destroy()

        # Row 1 layout: Apply Filter + Clear All Selections buttons placed side-by-side
        row1 = ctk.CTkFrame(btn_container, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 6))

        # Button to confirm selections and update list view
        apply_btn = ctk.CTkButton(row1, text="✅ Apply Filter", command=_apply,
                       height=36, font=ctk.CTkFont(size=14, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black")
        apply_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        # Button to clear checkboxes without submitting/applying or closing the popup
        clear_all_btn = ctk.CTkButton(row1, text="↺ Clear All", command=_clear_selections,
                       height=36, font=ctk.CTkFont(size=13),
                       fg_color="#555", hover_color="#777",
                       width=130)
        clear_all_btn.pack(side="left")

        # Row 2 layout: Clear Filter (disabling active settings) + Cancel buttons
        row2 = ctk.CTkFrame(btn_container, fg_color="transparent")
        row2.pack(fill="x")

        # Button to immediately wipe all active filter constraints from the review page
        clear_filter_btn = ctk.CTkButton(row2, text="🗑️ Clear Filter", command=_clear_and_apply,
                       height=36, font=ctk.CTkFont(size=13, weight="bold"),
                       fg_color="#e74c3c", hover_color="#c0392b")
        clear_filter_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        # Button to exit the modal, or to stop an in-progress duration probe
        cancel_btn = ctk.CTkButton(row2, text="Cancel", command=_on_cancel,
                       height=36, font=ctk.CTkFont(size=13),
                       fg_color="transparent", border_width=1,
                       border_color="#555", width=130)
        cancel_btn.pack(side="left")

        # Cancelling the window (X button) also stops any running probe safely
        popup.protocol("WM_DELETE_WINDOW", _on_cancel)

