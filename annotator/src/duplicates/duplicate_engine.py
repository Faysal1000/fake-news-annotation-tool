"""
DuplicateEngineMixin mixin class.
"""

import customtkinter as ctk
import threading
import csv
import json
import os
import concurrent.futures
from pathlib import Path
from tkinter import messagebox
from app_paths import CSV_PATH, CONFIG_PATH, SCRIPT_DIR
from constants import CSV_COLUMNS
from analysis.text_similarity import calculate_heading_similarity, calculate_jaccard_similarity, calculate_containment_similarity, clean_text
from data.config_manager import get_full_config, save_full_config

import difflib

_worker_records = None
_worker_index = None

def _init_worker(records, index):
    global _worker_records, _worker_index
    _worker_records = records
    _worker_index = index

def _evaluate_duplicate_chunk(args):
    if len(args) == 5:
        start_idx, end_idx, global_records_data, global_inverted_index, threshold = args
    else:
        start_idx, end_idx, threshold = args
        global_records_data = _worker_records
        global_inverted_index = _worker_index
        
    pairs_cache = []
    
    for i in range(start_idx, end_idx):
        data_i = global_records_data[i]
        words_i_comb = data_i["words_combined"]
        if not words_i_comb:
            continue
            
        # Find candidates sharing at least one word
        candidates = {}
        for word in words_i_comb:
            if word in global_inverted_index:
                for j in global_inverted_index[word]:
                    if j > i:
                        candidates[j] = candidates.get(j, 0) + 1
                        
        # Evaluate candidates
        for j, intersection_len in candidates.items():
            data_j = global_records_data[j]
            words_j_comb = data_j["words_combined"]
            
            union_len = len(words_i_comb) + len(words_j_comb) - intersection_len
            combined_jaccard = intersection_len / union_len if union_len > 0 else 0.0
            
            combined_containment = 0.0
            if len(words_i_comb) >= 30 and len(words_j_comb) >= 30:
                containment_i_j = intersection_len / len(words_i_comb) if len(words_i_comb) > 0 else 0.0
                containment_j_i = intersection_len / len(words_j_comb) if len(words_j_comb) > 0 else 0.0
                combined_containment = max(containment_i_j, containment_j_i)
                
            combined_sim = max(combined_jaccard, combined_containment)
            
            heading_sim = 0.0
            h_i = data_i["heading"]
            h_j = data_j["heading"]
            if h_i and h_j:
                words_i_h = data_i["words_heading"]
                words_j_h = data_j["words_heading"]
                if len(words_i_h.intersection(words_j_h)) > 0 or len(h_i) < 20 or len(h_j) < 20:
                    ratio = difflib.SequenceMatcher(None, h_i.lower(), h_j.lower()).ratio()
                    u_h = len(words_i_h.union(words_j_h))
                    jacc_h = len(words_i_h.intersection(words_j_h)) / u_h if u_h > 0 else 0.0
                    heading_sim = max(ratio, jacc_h)
                    
            text_sim = 0.0
            words_i_t = data_i["words_text"]
            words_j_t = data_j["words_text"]
            if words_i_t and words_j_t:
                intersection_t = len(words_i_t.intersection(words_j_t))
                union_t = len(words_i_t.union(words_j_t))
                text_jaccard = intersection_t / union_t if union_t > 0 else 0.0
                text_containment = intersection_t / len(words_i_t) if len(words_i_t) > 0 else 0.0
                text_sim = max(text_jaccard, text_containment)
                
            max_sim = max(combined_sim, heading_sim, text_sim)
            if max_sim >= threshold:
                pairs_cache.append({
                    "idx_a": i,
                    "idx_b": j,
                    "record_a": data_i["record"],
                    "record_b": data_j["record"],
                    "similarity": max_sim,
                    "combined_sim": combined_sim,
                    "heading_sim": heading_sim,
                    "text_sim": text_sim
                })
                
    return pairs_cache

class DuplicateEngineMixin:
    def _on_heading_key_release(self, event=None):
        self._update_heading_search_visibility(event)
        if self.current_mode == "review":
            self._schedule_inline_dup_check(event)

    def _on_text_key_release(self, event=None):
        if self.current_mode == "review":
            self._schedule_inline_dup_check(event)

    def _schedule_inline_dup_check(self, event=None):
        """
        Schedules a duplicate count update in Review Mode.
        """
        if self.current_mode != "review":
            return
        if hasattr(self, "_inline_dup_timer") and self._inline_dup_timer:
            self.after_cancel(self._inline_dup_timer)
        self._inline_dup_timer = self.after(400, self._update_inline_duplicate_count)

    def _hide_duplicate_warnings(self):
        """
        Hides any duplicate warnings / hyperlink text in the UI.
        """
        if hasattr(self, "heading_dup_badge") and self.heading_dup_badge:
            self._update_heading_dup_badge_ui("hidden")

    def _get_precomputed_data(self):
        """
        Ensures the cleaned records and inverted index are precomputed and cached.
        Returns (global_records_data, global_inverted_index).
        """
        records = self._get_all_records_for_dup_check()
        
        # Return cached copy if available and matches records size
        if (hasattr(self, '_cached_records_data') and 
            self._cached_records_data is not None and 
            len(self._cached_records_data) == len(records)):
            return self._cached_records_data, self._cached_inverted_index
            
        # Re-index all records
        global_records_data = []
        for idx, rec in enumerate(records):
            h = rec.get("heading", "") or ""
            t = rec.get("text", "") or ""
            comb = f"{h} {t}".strip()
            
            words_comb = set(clean_text(comb))
            words_h = set(clean_text(h))
            words_t = set(clean_text(t))
            
            global_records_data.append({
                "idx": idx,
                "record": rec,
                "heading": h,
                "text": t,
                "combined": comb,
                "words_combined": words_comb,
                "words_heading": words_h,
                "words_text": words_t
            })
            
        global_inverted_index = {}
        for idx, data in enumerate(global_records_data):
            for word in data["words_combined"]:
                if word not in global_inverted_index:
                    global_inverted_index[word] = []
                global_inverted_index[word].append(idx)
                
        self._cached_records_data = global_records_data
        self._cached_inverted_index = global_inverted_index
        return global_records_data, global_inverted_index

    def _get_all_records_for_dup_check(self):
        """
        Retrieves all records from dataset.csv for duplicate verification.
        Uses in-memory records if already loaded, otherwise reads from file.
        """
        if self.all_dataset_records:
            return self.all_dataset_records
            
        records = []
        if CSV_PATH.exists() and CSV_PATH.stat().st_size > 0:
            try:
                with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        records.append(row)
                self.all_dataset_records = records
                try:
                    self._last_loaded_csv_mtime = CSV_PATH.stat().st_mtime
                    self._last_loaded_csv_size = CSV_PATH.stat().st_size
                except Exception:
                    pass
            except Exception as e:
                print(f"[WARNING] Failed to read dataset.csv for duplicate check: {e}")
        return records

    def _check_duplicates_for_saving(self, current_heading, current_text, exclude_id=None):
        """
        Compares heading/text against all existing database records to find duplicates.
        Combines heading + text into a single blob so cross-field matches are caught
        (e.g. heading content appearing in the other record's text).
        Returns a sorted list of matches with similarity scores >= 0.50 (50%).
        """
        records = self._get_all_records_for_dup_check()
        if not records:
            return []
        
        # Build combined blob for the current entry
        current_combined = f"{current_heading or ''} {current_text or ''}".strip()
        if not current_combined:
            return []
            
        matches = []
        for idx, rec in enumerate(records):
            rec_id = rec.get("id")
            if exclude_id and rec_id == exclude_id:
                continue
                
            rec_heading = rec.get("heading", "")
            rec_text = rec.get("text", "")
            rec_combined = f"{rec_heading} {rec_text}".strip()
            
            if not rec_combined:
                continue
            
            # Heading similarity (heading-to-heading)
            heading_sim = 0.0
            if current_heading and rec_heading:
                heading_sim = calculate_heading_similarity(current_heading, rec_heading)
                
            # Text similarity (text-to-text)
            text_sim = 0.0
            if current_text and rec_text:
                text_jaccard = calculate_jaccard_similarity(current_text, rec_text)
                text_containment = calculate_containment_similarity(current_text, rec_text)
                text_sim = max(text_jaccard, text_containment)
                
            # Combined similarity (head+body with head+body)
            combined_jaccard = calculate_jaccard_similarity(current_combined, rec_combined)
            combined_containment = 0.0
            words_i_comb = set(clean_text(current_combined))
            words_j_comb = set(clean_text(rec_combined))
            if len(words_i_comb) >= 30 and len(words_j_comb) >= 30:
                combined_containment = calculate_containment_similarity(current_combined, rec_combined)
            combined_sim = max(combined_jaccard, combined_containment)
            max_sim = max(combined_sim, heading_sim, text_sim)
            
            # The duplicate threshold is triggered if overall similarity (max of combined, heading, text) is >= dynamic threshold
            threshold = self._get_duplicate_threshold() / 100.0
            if max_sim >= threshold:
                matches.append({
                    "row_num": idx + 1,
                    "record": rec,
                    "similarity": max_sim,
                    "combined_sim": combined_sim,
                    "heading_sim": heading_sim,
                    "text_sim": text_sim,
                    "new_heading_ref": current_heading,
                    "new_text_ref": current_text
                })
                
        matches.sort(key=lambda x: x["similarity"], reverse=True)
        return matches

    def _update_inline_duplicate_count(self):
        """
        Audits the current record in Review Mode against other records for duplicates.
        If duplicates exist, shows the clickable warning text next to the heading label.
        Calculates in the background using a thread to avoid freezing the UI.
        """
        if self.current_mode != "review":
            self._hide_duplicate_warnings()
            return
            
        # Pause if an update is downloading/installing
        if getattr(self, '_update_download_thread', None) and self._update_download_thread.is_alive():
            self._hide_duplicate_warnings()
            return
            
        current_id = None
        if self.current_mode == "review" and self.dataset_records:
            record = self.dataset_records[self.current_review_index]
            current_id = record.get("id")
        current_heading = self._get_heading_text()
        current_text = self.text_box.get("1.0", "end-1c").strip()
        
        # We only check if heading or text is populated
        if not current_heading.strip() and not current_text.strip():
            self._hide_duplicate_warnings()
            return

        # Show calculating state immediately
        self._update_heading_dup_badge_ui("calculating")
        
        # Reset current record matches
        self._current_record_matches = []
        
        # Set up check ID to track this specific request
        self._current_inline_dup_check_id = getattr(self, '_current_inline_dup_check_id', 0) + 1
        check_id = self._current_inline_dup_check_id
        
        # Run query asynchronously
        thread = threading.Thread(target=self._inline_dup_thread_worker, args=(check_id, current_heading, current_text, current_id), daemon=True)
        thread.start()

    def _inline_dup_thread_worker(self, check_id, current_heading, current_text, current_id):
        if getattr(self, '_current_inline_dup_check_id', 0) != check_id:
            return
            
        try:
            # Load cached dataset representation
            global_records_data, global_inverted_index = self._get_precomputed_data()
            
            words_i_h = set(clean_text(current_heading))
            words_i_text = set(clean_text(current_text))
            words_i_comb = words_i_h.union(words_i_text)
            
            matches = []
            threshold = self._get_duplicate_threshold() / 100.0
            
            # Find candidates with word overlaps
            candidates = {}
            for word in words_i_comb:
                if word in global_inverted_index:
                    for j in global_inverted_index[word]:
                        candidates[j] = candidates.get(j, 0) + 1
                        
            # Evaluate candidates
            for j, intersection_len in candidates.items():
                if getattr(self, '_current_inline_dup_check_id', 0) != check_id:
                    return
                    
                data_j = global_records_data[j]
                rec_id = data_j["record"].get("id")
                if current_id and rec_id == current_id:
                    continue
                    
                words_j_comb = data_j["words_combined"]
                union_len = len(words_i_comb) + len(words_j_comb) - intersection_len
                combined_jaccard = intersection_len / union_len if union_len > 0 else 0.0
                
                combined_containment = 0.0
                if len(words_i_comb) >= 30 and len(words_j_comb) >= 30:
                    containment_i_j = intersection_len / len(words_i_comb) if len(words_i_comb) > 0 else 0.0
                    containment_j_i = intersection_len / len(words_j_comb) if len(words_j_comb) > 0 else 0.0
                    combined_containment = max(containment_i_j, containment_j_i)
                    
                combined_sim = max(combined_jaccard, combined_containment)
                
                heading_sim = 0.0
                h_j = data_j["heading"]
                if current_heading and h_j:
                    words_j_h = data_j["words_heading"]
                    if len(words_i_h.intersection(words_j_h)) > 0 or len(current_heading) < 20 or len(h_j) < 20:
                        ratio = difflib.SequenceMatcher(None, current_heading.lower(), h_j.lower()).ratio()
                        u_h = len(words_i_h.union(words_j_h))
                        jacc_h = len(words_i_h.intersection(words_j_h)) / u_h if u_h > 0 else 0.0
                        heading_sim = max(ratio, jacc_h)
                        
                text_sim = 0.0
                if current_text and data_j["text"]:
                    words_j_t = data_j["words_text"]
                    if words_i_text and words_j_t:
                        intersection_t = len(words_i_text.intersection(words_j_t))
                        union_t = len(words_i_text.union(words_j_t))
                        text_jaccard = intersection_t / union_t if union_t > 0 else 0.0
                        text_containment = intersection_t / len(words_i_text) if len(words_i_text) > 0 else 0.0
                        text_sim = max(text_jaccard, text_containment)
                        
                max_sim = max(combined_sim, heading_sim, text_sim)
                if max_sim >= threshold:
                    matches.append({
                        "row_num": j + 1,
                        "record": data_j["record"],
                        "similarity": max_sim,
                        "combined_sim": combined_sim,
                        "heading_sim": heading_sim,
                        "text_sim": text_sim,
                        "new_heading_ref": current_heading,
                        "new_text_ref": current_text
                    })
                    
            matches.sort(key=lambda x: x["similarity"], reverse=True)
            
        except Exception as e:
            print(f"Error in inline dup thread: {e}")
            matches = []
            
        # Notify main window of completion
        if getattr(self, '_current_inline_dup_check_id', 0) == check_id:
            self.after(0, lambda: self._on_inline_dup_done(check_id, matches))

    def _on_inline_dup_done(self, check_id, matches):
        if getattr(self, '_current_inline_dup_check_id', 0) != check_id:
            return
        
        self._current_record_matches = matches
        count = len(matches)
        if count > 0:
            self._update_heading_dup_badge_ui("duplicates_found", count=count)
        else:
            self._update_heading_dup_badge_ui("no_duplicates")

    def _update_heading_dup_badge_ui(self, state, count=0):
        """
        Updates the styling and contents of the inline heading duplicate warning badge.
        """
        self._heading_dup_state = state
        
        if not hasattr(self, "heading_dup_badge") or not self.heading_dup_badge:
            return
            
        if state == "hidden":
            self.heading_dup_badge.pack_forget()
        else:
            if not self.heading_dup_badge.winfo_manager():
                self.heading_dup_badge.pack(side="left", padx=(8, 0))
            self.heading_dup_badge.configure(width=165, height=26)
            self.heading_dup_badge.pack_propagate(False)
            
            if state == "calculating":
                self.heading_dup_badge.configure(
                    fg_color="#2b2b36",
                    border_color="#555555",
                    border_width=1,
                    cursor="arrow"
                )
                self.heading_dup_text.configure(
                    text="⏳ Calculating...",
                    text_color="#aaaaaa"
                )
            elif state == "duplicates_found":
                self.heading_dup_badge.configure(
                    fg_color="#3d2b0f",
                    border_color="#f39c12",
                    border_width=1,
                    cursor="hand2"
                )
                self.heading_dup_text.configure(
                    text=f"⚠️ {count} Duplicate{'s' if count > 1 else ''} · View ▸",
                    text_color="#f39c12"
                )
            elif state == "no_duplicates":
                self.heading_dup_badge.configure(
                    fg_color="#1a3322",
                    border_color="#2ecc71",
                    border_width=1,
                    cursor="arrow"
                )
                self.heading_dup_text.configure(
                    text="✅ No Duplicate",
                    text_color="#2ecc71"
                )

    def _on_heading_dup_click(self):
        """
        Handles clicks on the heading duplicate badge.
        """
        if getattr(self, "_heading_dup_state", "hidden") == "duplicates_found":
            self._show_review_duplicates()

    def _compute_global_duplicates(self, force_restart=False):
        """
        Computes all duplicate pairs in the dataset in a true background thread.
        Stores results in self._duplicate_pairs_cache and safely updates UI when done.
        """
        # Pause background calculation if an update is downloading/installing
        if getattr(self, '_update_download_thread', None) and self._update_download_thread.is_alive():
            return

        if hasattr(self, '_duplicate_computing') and self._duplicate_computing:
            if not force_restart:
                return
            
        self._duplicate_computing = True
        self._cancel_duplicate_computing = False
        
        if not hasattr(self, '_duplicate_thread_generation'):
            self._duplicate_thread_generation = 0
        self._duplicate_thread_generation += 1
        
        current_gen = self._duplicate_thread_generation
        
        # Run the heavy duplicate processing in a separate thread to prevent UI freezing
        thread = threading.Thread(target=self._duplicate_thread_worker, args=(current_gen,), daemon=True)
        thread.start()

    def _duplicate_thread_worker(self, generation):
        try:
            # Load cached dataset representation
            global_records_data, global_inverted_index = self._get_precomputed_data()
            n_records = len(global_records_data)
            
            # Process all records using chunks
            pairs_cache = []
            threshold = self._get_duplicate_threshold() / 100.0
            use_mp = self._get_duplicate_multiprocessing()
            
            if use_mp:
                num_cores = os.cpu_count() or 4
                # Split tasks into chunks
                num_chunks = 100
                chunk_size = max(1, n_records // num_chunks)
                
                tasks = []
                for start_idx in range(0, n_records, chunk_size):
                    end_idx = min(start_idx + chunk_size, n_records)
                    tasks.append((start_idx, end_idx, threshold))
                
                self.after(0, lambda g=generation: self._update_duplicate_progress(0.0, g))
                with concurrent.futures.ProcessPoolExecutor(max_workers=num_cores, initializer=_init_worker, initargs=(global_records_data, global_inverted_index)) as executor:
                    futures = [executor.submit(_evaluate_duplicate_chunk, t) for t in tasks]
                    pending = set(futures)
                    
                    completed_chunks = 0
                    while pending:
                        if getattr(self, '_duplicate_thread_generation', 0) != generation or getattr(self, '_cancel_duplicate_computing', False):
                            executor.shutdown(wait=False, cancel_futures=True)
                            self.after(0, lambda: self._on_duplicate_thread_done([], generation, cancelled=True))
                            return
                        done, pending = concurrent.futures.wait(pending, timeout=0.2, return_when=concurrent.futures.FIRST_COMPLETED)
                        for future in done:
                            pairs_cache.extend(future.result())
                            completed_chunks += 1
                            progress = completed_chunks / len(tasks)
                            self.after(0, lambda p=progress, g=generation: self._update_duplicate_progress(p, g))
            else:
                num_chunks = max(1, min(100, n_records))
                chunk_size = max(1, n_records // num_chunks)
                
                tasks = []
                for start_idx in range(0, n_records, chunk_size):
                    end_idx = min(start_idx + chunk_size, n_records)
                    tasks.append((start_idx, end_idx, threshold))
                
                # Process sequentially using a single worker
                self.after(0, lambda g=generation: self._update_duplicate_progress(0.0, g))
                with concurrent.futures.ProcessPoolExecutor(max_workers=1, initializer=_init_worker, initargs=(global_records_data, global_inverted_index)) as executor:
                    futures = [executor.submit(_evaluate_duplicate_chunk, t) for t in tasks]
                    pending = set(futures)
                    
                    completed_chunks = 0
                    while pending:
                        if getattr(self, '_duplicate_thread_generation', 0) != generation or getattr(self, '_cancel_duplicate_computing', False):
                            executor.shutdown(wait=False, cancel_futures=True)
                            self.after(0, lambda: self._on_duplicate_thread_done([], generation, cancelled=True))
                            return
                        done, pending = concurrent.futures.wait(pending, timeout=0.2, return_when=concurrent.futures.FIRST_COMPLETED)
                        for future in done:
                            pairs_cache.extend(future.result())
                            completed_chunks += 1
                            progress = completed_chunks / len(tasks)
                            self.after(0, lambda p=progress, g=generation: self._update_duplicate_progress(p, g))
            
            # Use after() to safely update the GUI thread
            self.after(0, lambda: self._on_duplicate_thread_done(pairs_cache, generation))
            
        except Exception as e:
            print(f"Error in background duplicate check: {e}")
            self.after(0, lambda: self._on_duplicate_thread_done([], generation))

    def _update_duplicate_progress(self, progress, generation):
        if getattr(self, '_duplicate_thread_generation', 0) != generation:
            return
            
        if hasattr(self, '_duplicate_popup_pb') and self._duplicate_popup_pb.winfo_exists():
            self._duplicate_popup_pb.set(progress)
            
        if hasattr(self, '_duplicate_popup_lbl') and self._duplicate_popup_lbl.winfo_exists():
            pct = int(progress * 100)
            text = f"🔄 Recalculating duplicates... {pct}%\nPlease wait."
            self._duplicate_popup_lbl.configure(text=text)

    def _on_duplicate_thread_done(self, computed_cache, generation, cancelled=False):
        # If a new thread has been started, ignore this old thread's result
        if getattr(self, '_duplicate_thread_generation', 0) != generation:
            return
            
        self._duplicate_computing = False
        
        if cancelled:
            # When cancelled, keep existing cache if any, but stop the popup
            if hasattr(self, '_duplicate_popup_lbl') and self._duplicate_popup_lbl.winfo_exists():
                # We can't destroy the whole popup directly without a ref, but it usually gets overwritten 
                # or destroyed when the user re-opens it. We just reset the calculating state.
                self._duplicate_popup_lbl.configure(text="❌ Calculation Cancelled")
            return
            
        self._raw_duplicate_pairs_cache = computed_cache
        self._duplicate_pairs_cache = computed_cache
        # Load non duplicates
        non_dups = self._load_non_duplicates()
        if non_dups:
            self._apply_non_duplicates_filter()
        self._update_stats()

    def _get_non_duplicates_file_path(self):
        import os
        return SCRIPT_DIR / "non_duplicates.json"

    def _load_non_duplicates(self):
        import json
        path = self._get_non_duplicates_file_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception as e:
                print(f"Error loading non_duplicates.json: {e}")
        return set()

    def _save_non_duplicates(self, non_dups_set):
        import json
        path = self._get_non_duplicates_file_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(list(non_dups_set), f)
        except Exception as e:
            print(f"Error saving non_duplicates.json: {e}")

    def _get_duplicate_threshold(self):
        cfg = get_full_config()
        return cfg.get("duplicate_threshold", 60)

    def _save_duplicate_threshold(self, threshold):
        cfg = get_full_config()
        cfg["duplicate_threshold"] = threshold
        save_full_config(cfg)

    def _get_duplicate_multiprocessing(self):
        cfg = get_full_config()
        return cfg.get("duplicate_multiprocessing", False)

    def _save_duplicate_multiprocessing(self, enabled):
        cfg = get_full_config()
        cfg["duplicate_multiprocessing"] = enabled
        save_full_config(cfg)

    def _apply_non_duplicates_filter(self):
        if not hasattr(self, '_raw_duplicate_pairs_cache') or not self._raw_duplicate_pairs_cache:
            return
            
        non_dups = self._load_non_duplicates()
        if not non_dups:
            self._duplicate_pairs_cache = list(self._raw_duplicate_pairs_cache)
            return
            
        filtered_cache = []
        for pair in self._raw_duplicate_pairs_cache:
            id_a = str(pair["record_a"].get("id", ""))
            id_b = str(pair["record_b"].get("id", ""))
            
            # Create a consistent pair key regardless of order
            pair_key = f"{min(id_a, id_b)}_{max(id_a, id_b)}"
            if pair_key not in non_dups:
                filtered_cache.append(pair)
                
        self._duplicate_pairs_cache = filtered_cache

    def _mark_as_non_duplicate(self, record_a, record_b):
        id_a = str(record_a.get("id", ""))
        id_b = str(record_b.get("id", ""))
        if not id_a or not id_b:
            messagebox.showwarning("Warning", "Cannot mark as non-duplicate: Missing IDs.")
            return
            
        pair_key = f"{min(id_a, id_b)}_{max(id_a, id_b)}"
        non_dups = self._load_non_duplicates()
        non_dups.add(pair_key)
        self._save_non_duplicates(non_dups)
        
        # Remove from current cache
        self._apply_non_duplicates_filter()
        self._update_stats()

    def _unmark_as_non_duplicate(self, record_a, record_b):
        id_a = str(record_a.get("id", ""))
        id_b = str(record_b.get("id", ""))
        if not id_a or not id_b:
            return
            
        pair_key = f"{min(id_a, id_b)}_{max(id_a, id_b)}"
        non_dups = self._load_non_duplicates()
        if pair_key in non_dups:
            non_dups.remove(pair_key)
            self._save_non_duplicates(non_dups)
        
        self._apply_non_duplicates_filter()
        self._update_stats()

    def _unmark_all_non_duplicates(self):
        import json
        path = self._get_non_duplicates_file_path()
        if path.exists():
            try:
                path.unlink()
            except Exception as e:
                print(f"Error deleting non_duplicates.json: {e}")
        
        # Since we just cleared the local filters, simply re-apply them to restore the cache
        self._apply_non_duplicates_filter()
        self._update_stats()

