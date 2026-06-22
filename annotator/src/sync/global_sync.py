"""
GlobalSyncMixin mixin class.
"""

import customtkinter as ctk
import threading
import time
import requests
import json
from data.config_manager import get_machine_id, load_config, get_full_config, save_full_config
from data.stats_engine import get_label_counts

class GlobalSyncMixin:
    def _sync_global_metrics_loop(self):
        """
        Runs every 5 minutes in a background thread to sync metrics.
        """
        threading.Thread(target=self._sync_global_metrics_worker, daemon=True).start()
        # Schedule the next run in 5 minutes (300,000 ms)
        self.after(300000, self._sync_global_metrics_loop)

    def _sync_global_metrics_worker(self):
        if not self._sync_lock.acquire(blocking=False):
            return

        sync_succeeded = False
        self.last_sync_error = ""
        try:
            cfg = get_full_config()
            gist_id = cfg.get("gist_id")
            github_token = cfg.get("github_token")

            if not gist_id or not github_token:
                self.last_sync_error = "Missing GitHub Gist ID or Token"
                self.is_global_syncing = False
                self._queue_detailed_stats_redraw()
                return

            self.is_global_syncing = True
            self._queue_detailed_stats_redraw()

            machine_id = get_machine_id()
            current_local_stats = self._calculate_grouped_local_stats()
            needs_upload = self.last_uploaded_counts != current_local_stats

            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }

            # 1. Fetch current Gist
            resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=headers, timeout=10)
            if resp.status_code != 200:
                self.last_sync_error = f"Fetch failed: HTTP {resp.status_code}"
                print(f"[SYNC ERROR] Failed to fetch Gist: {resp.status_code}")
                return
                
            gist_data = resp.json()
            files = gist_data.get("files", {})
            if "metrics.json" not in files:
                global_data = {}
            else:
                try:
                    global_data = json.loads(files["metrics.json"]["content"])
                except Exception:
                    global_data = {}

            latest_cfg = get_full_config()
            if (latest_cfg.get("gist_id") != gist_id or
                    latest_cfg.get("github_token") != github_token):
                return
            
            # 2. Update local tracking variable for UI rendering
            self.global_metrics_data = dict(global_data)
            sync_succeeded = True
            
            if needs_upload:
                # 3. Merge our local stats into the global data
                global_data[machine_id] = current_local_stats
                
                # 4. Upload back to Gist
                payload = {
                    "files": {
                        "metrics.json": {
                            "content": json.dumps(global_data, indent=2)
                        }
                    }
                }
                patch_resp = requests.patch(f"https://api.github.com/gists/{gist_id}", json=payload, headers=headers, timeout=10)
                if patch_resp.status_code == 200:
                    self.last_uploaded_counts = current_local_stats
                    # Update local tracking again
                    self.global_metrics_data = dict(global_data)
                else:
                    self.last_sync_error = f"Upload failed: HTTP {patch_resp.status_code}"
                    print(f"[SYNC ERROR] Failed to update Gist: {patch_resp.status_code}")
                
        except Exception as e:
            self.last_sync_error = f"Network Error: {type(e).__name__}"
            print(f"[SYNC ERROR] Exception during sync: {e}")
        finally:
            self.is_global_syncing = False
            if sync_succeeded:
                self.last_global_sync_time = time.time()
            self._queue_detailed_stats_redraw()
            self._sync_lock.release()

    def _show_team_sync_popup(self):
        """
        Popup for configuring the GitHub Gist token.
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Team Sync Setup")
        popup.configure(fg_color="#1a1a2e")
        if hasattr(self, 'active_detailed_popup') and self.active_detailed_popup.winfo_exists():
            popup.transient(self.active_detailed_popup)
        else:
            popup.transient(self)
        popup.grab_set()
        popup.resizable(False, False)
        
        pw, ph = 450, 380
        popup.geometry(f"{pw}x{ph}")
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (pw // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (ph // 2)
        popup.geometry(f"+{x}+{y}")

        ctk.CTkLabel(popup, text="🌐 Team Global Metrics Sync", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 10))
        ctk.CTkLabel(popup, text="Enter your Team's GitHub Gist ID and Access Token to sync\nyour metrics globally and view your teammates' progress.",
                     text_color="#aaa", font=ctk.CTkFont(size=12)).pack(pady=(0, 15))

        cfg = get_full_config()
        
        form_frame = ctk.CTkFrame(popup, fg_color="transparent")
        form_frame.pack(fill="x", padx=30, pady=10)
        
        ctk.CTkLabel(form_frame, text="GitHub Gist ID:", anchor="w").pack(fill="x")
        gist_entry = ctk.CTkEntry(form_frame, height=35)
        gist_entry.pack(fill="x", pady=(2, 12))
        if "gist_id" in cfg:
            gist_entry.insert(0, cfg["gist_id"])
            
        ctk.CTkLabel(form_frame, text="GitHub Access Token (PAT):", anchor="w").pack(fill="x")
        token_entry = ctk.CTkEntry(form_frame, height=35, show="*")
        token_entry.pack(fill="x", pady=(2, 5))
        if "github_token" in cfg:
            token_entry.insert(0, cfg["github_token"])
            
        error_label = ctk.CTkLabel(popup, text="", text_color="#e74c3c")
        error_label.pack(pady=5)
        
        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(fill="x", padx=30, pady=10)
        
        def save_creds():
            g_id = gist_entry.get().strip()
            tkn = token_entry.get().strip()
            if not g_id or not tkn:
                error_label.configure(text="Please fill in both fields.")
                return
                
            error_label.configure(text="Validating...", text_color="#f39c12")
            popup.update()
            
            # Validate with GitHub
            headers = {"Authorization": f"token {tkn}", "Accept": "application/vnd.github.v3+json"}
            try:
                resp = requests.get(f"https://api.github.com/gists/{g_id}", headers=headers, timeout=10)
                if resp.status_code == 200:
                    cfg["gist_id"] = g_id
                    cfg["github_token"] = tkn
                    save_full_config(cfg)
                    error_label.configure(text="Success! Sync enabled.", text_color="#2ecc71")
                    # Force an immediate sync
                    threading.Thread(target=self._sync_global_metrics_worker, daemon=True).start()
                    popup.after(1500, popup.destroy)
                else:
                    error_label.configure(text=f"Validation Failed (Code {resp.status_code}). Check your credentials.", text_color="#e74c3c")
            except Exception as e:
                error_label.configure(text=f"Network Error: {e}", text_color="#e74c3c")
                
        def delete_creds():
            g_id = cfg.get("gist_id")
            tkn = cfg.get("github_token")
            machine_uuid = cfg.get("machine_id")

            if g_id and tkn and machine_uuid:
                error_label.configure(text="Removing data from cloud...", text_color="#f39c12")
                popup.update()
                try:
                    headers = {"Authorization": f"token {tkn}", "Accept": "application/vnd.github.v3+json"}
                    resp = requests.get(f"https://api.github.com/gists/{g_id}", headers=headers, timeout=10)
                    if resp.status_code == 200:
                        gist_data = resp.json()
                        metrics_file = gist_data.get("files", {}).get("metrics.json")
                        if metrics_file:
                            try:
                                cloud_data = json.loads(metrics_file.get("content", "{}"))
                                if machine_uuid in cloud_data:
                                    del cloud_data[machine_uuid]
                                    patch_data = {"files": {"metrics.json": {"content": json.dumps(cloud_data, indent=2)}}}
                                    requests.patch(f"https://api.github.com/gists/{g_id}", headers=headers, json=patch_data, timeout=10)
                            except Exception:
                                pass
                except Exception:
                    pass

            if "gist_id" in cfg: del cfg["gist_id"]
            if "github_token" in cfg: del cfg["github_token"]
            save_full_config(cfg)
            self.global_metrics_data = {}
            self.last_global_sync_time = None
            self.last_uploaded_counts = {}
            self.global_metrics_enabled.set(False)
            
            self._queue_detailed_stats_redraw()
                
            popup.destroy()
        save_btn = ctk.CTkButton(btn_frame, text="💾 Save & Sync", command=save_creds, height=35, fg_color="#2ecc71", hover_color="#27ae60", text_color="black")
        save_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        del_btn = ctk.CTkButton(btn_frame, text="Disconnect", command=delete_creds, height=35, fg_color="#e74c3c", hover_color="#c0392b")
        del_btn.pack(side="left", fill="x", expand=True)

