"""
UpdateMixin mixin class.
"""

import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk
import sys
import os
import requests
import threading
import platform
import re
import shlex
import subprocess
import json
import time
import shutil
from pathlib import Path
from app_paths import VERSION_FILE, UPDATE_API_URL, UPDATE_DOWNLOAD_BASE_URL, UPDATE_CHUNK_SIZE, SCRIPT_DIR
from constants import UpdateCancelled

class UpdateMixin:
    def _get_resource_path(self, relative_path):
        """
        Resolves paths to internal static resources, supporting both development and production.
        
        This utility resolves file references when running in python environments or packaged
        inside PyInstaller single-file executables (referencing the _MEIPASS extraction root).
        
        Args:
            relative_path: Relative path string to the desired resource file.
            
        Returns:
            str: Resolved absolute path.
        """
        try:
            # When packaged with PyInstaller, assets are unpacked to a temporary folder
            # whose path is stored in the sys._MEIPASS system attribute.
            base_path = Path(sys._MEIPASS)
        except Exception:
            # During local development, resolve the file relative to the script directory
            base_path = Path(__file__).parent.resolve()
        
        return str(base_path / relative_path)

    def _parse_version_parts(self, version):
        """
        Converts a version tag like v9.1.0 into a comparable integer tuple.
        """
        parts = [int(part) for part in re.findall(r"\d+", version or "")]
        return tuple((parts + [0, 0, 0])[:3])

    def _remote_version_is_newer(self, latest_version, current_version):
        """
        Returns True only when the remote release version is newer than the local version.
        Falls back to string comparison if either version cannot be parsed.
        """
        latest_parts = self._parse_version_parts(latest_version)
        current_parts = self._parse_version_parts(current_version)
        if any(latest_parts) or any(current_parts):
            return latest_parts > current_parts
        return (latest_version or "").strip().lower() != (current_version or "").strip().lower()

    def _build_update_info(self, release_data):
        """
        Selects the correct release asset for the current platform.
        """
        system = platform.system()
        machine = platform.machine().lower()

        if system == "Darwin":
            if "arm" in machine or "aarch" in machine:
                asset_name = "FakeNewsAnnotator-macOS-AppleSilicon.zip"
            else:
                asset_name = "FakeNewsAnnotator-macOS-Intel.zip"
            package_type = "mac_zip"
        elif system == "Windows":
            asset_name = "FakeNewsAnnotator-Windows.exe"
            package_type = "windows_exe"
        else:
            asset_name = "FakeNewsAnnotator-Linux"
            package_type = "linux_binary"

        download_url = f"{UPDATE_DOWNLOAD_BASE_URL}/{asset_name}"
        for asset in release_data.get("assets", []):
            if asset.get("name") == asset_name and asset.get("browser_download_url"):
                download_url = asset["browser_download_url"]
                break

        return {
            "version": release_data.get("tag_name", "latest"),
            "asset_name": asset_name,
            "download_url": download_url,
            "package_type": package_type,
            "system": system,
        }

    def _get_current_app_path(self):
        """
        Returns the executable or .app bundle path that should be replaced by an update.
        """
        if getattr(sys, "frozen", False):
            exe_path = Path(sys.executable).resolve()
            if platform.system() == "Darwin" and ".app/Contents/MacOS" in exe_path.as_posix():
                return exe_path.parents[2]
            return exe_path
        return Path(__file__).resolve()

    def _get_update_download_path(self, update_info):
        """
        Returns a temporary path next to the app for the downloaded release asset.
        """
        updates_dir = SCRIPT_DIR / ".updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".new" if update_info["package_type"] in {"windows_exe", "linux_binary"} else ".tmp"
        return updates_dir / f"{update_info['asset_name']}{suffix}"

    def _format_download_size(self, byte_count):
        """
        Formats bytes for compact updater status text.
        """
        mb_count = byte_count / (1024 * 1024)
        return f"{mb_count:.1f} MB"

    def _queue_update_ui(self, popup, callback):
        """
        Schedules a small UI mutation from the updater worker thread.
        """
        def run_callback():
            try:
                if popup.winfo_exists():
                    callback()
            except tk.TclError:
                pass

        try:
            self.after(0, run_callback)
        except tk.TclError:
            pass

    def _check_for_updates(self):
        """
        Checks for a new release of the tool on GitHub in a background thread.

        Reads version.json to parse the local version string, performs a GET request
        to the GitHub releases API endpoint, and triggers the update alert window if
        a newer release tag is detected.
        """
        try:
            version_file = VERSION_FILE
            if not version_file.exists():
                return

            with open(version_file, "r") as f:
                data = json.load(f)
                current_version = data.get("version", "v1.0.0").strip()

            response = requests.get(UPDATE_API_URL, timeout=5)
            if response.status_code == 200:
                release_data = response.json()
                latest_tag = release_data.get("tag_name")
                if latest_tag and self._remote_version_is_newer(latest_tag, current_version):
                    update_info = self._build_update_info(release_data)
                    self.after(2000, lambda info=update_info: self._show_update_popup(info))
        except Exception as e:
            # Silently log update check errors since updates checking is non-critical for basic operation
            print(f"Update check failed (this is non-fatal): {e}")

    def _show_update_popup(self, update_info):
        """
        Renders the in-app updater popup with download progress and cancel support.
        """
        popup = ctk.CTkToplevel(self)
        popup.title("Update Available")
        popup.geometry("560x320")
        popup.attributes("-topmost", True)

        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 280
        y = self.winfo_y() + (self.winfo_height() // 2) - 160
        popup.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            popup,
            text=f"🎉 A new version ({update_info['version']}) is available!",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(22, 10))

        ctk.CTkLabel(
            popup,
            text="A product developed by Faysal Ahmmed.",
            font=ctk.CTkFont(size=14)
        ).pack(pady=(0, 8))
        
        ctk.CTkLabel(
            popup,
            text=f"Package: {update_info['asset_name']}",
            font=ctk.CTkFont(size=12),
            text_color="#a6adc8"
        ).pack(pady=(0, 8))

        progress_frame = ctk.CTkFrame(popup, fg_color="transparent")
        progress_bar = ctk.CTkProgressBar(progress_frame, height=14)
        progress_bar.set(0)
        progress_bar.pack(fill="x", padx=4, pady=(4, 8))

        status_label = ctk.CTkLabel(
            progress_frame,
            text="Ready to download.",
            font=ctk.CTkFont(size=13),
            text_color="#a6adc8"
        )
        status_label.pack()

        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=20)

        def start_update():
            if self._update_download_thread and self._update_download_thread.is_alive():
                return

            progress_frame.pack(fill="x", padx=24, pady=(8, 0))
            progress_bar.set(0)
            status_label.configure(text="Starting download...")
            update_btn.configure(state="disabled", text="Downloading...")
            close_btn.configure(state="disabled")
            cancel_btn.configure(state="normal")

            self._update_download_cancel = threading.Event()
            self._update_download_thread = threading.Thread(
                target=self._download_update_worker,
                args=(update_info, popup, progress_bar, status_label, update_btn, cancel_btn, close_btn),
                daemon=True
            )
            self._update_download_thread.start()

        def cancel_update():
            if self._update_download_cancel:
                self._update_download_cancel.set()
                status_label.configure(text="Canceling download...")
                cancel_btn.configure(state="disabled")

        def close_popup():
            if self._update_download_thread and self._update_download_thread.is_alive():
                cancel_update()
                return
            popup.destroy()

        update_btn = ctk.CTkButton(btn_frame, text="Update Now", command=start_update)
        update_btn.pack(side="left", padx=8)

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            state="disabled",
            command=cancel_update
        )
        cancel_btn.pack(side="left", padx=8)

        close_btn = ctk.CTkButton(
            btn_frame,
            text="Later",
            fg_color="transparent",
            border_width=1,
            command=close_popup
        )
        close_btn.pack(side="left", padx=8)

        popup.protocol("WM_DELETE_WINDOW", close_popup)

    def _download_update_worker(self, update_info, popup, progress_bar, status_label, update_btn, cancel_btn, close_btn):
        """
        Downloads the update in the background, then launches the platform installer script.
        """
        download_path = None
        try:
            download_path = self._get_update_download_path(update_info)
            self._download_update_file(update_info["download_url"], download_path, popup, progress_bar, status_label)

            self._queue_update_ui(
                popup,
                lambda: (
                    progress_bar.set(1),
                    status_label.configure(text="Download complete. Installing and restarting...")
                )
            )
            self._install_downloaded_update(update_info, download_path)
        except UpdateCancelled:
            if download_path:
                try:
                    download_path.unlink()
                except FileNotFoundError:
                    pass
                except Exception as e:
                    print(f"[WARNING] Could not remove canceled update download: {e}")

            self._queue_update_ui(
                popup,
                lambda: (
                    progress_bar.set(0),
                    status_label.configure(text="Download canceled."),
                    update_btn.configure(state="normal", text="Update Now"),
                    cancel_btn.configure(state="disabled"),
                    close_btn.configure(state="normal")
                )
            )
        except Exception as e:
            if download_path and download_path.exists():
                try:
                    download_path.unlink()
                except Exception:
                    pass

            error_text = f"Update failed: {e}"
            print(error_text)
            self._queue_update_ui(
                popup,
                lambda: (
                    status_label.configure(text=error_text),
                    update_btn.configure(state="normal", text="Try Again"),
                    cancel_btn.configure(state="disabled"),
                    close_btn.configure(state="normal")
                )
            )
        finally:
            self._update_download_thread = None
            self._update_download_cancel = None

    def _download_update_file(self, download_url, download_path, popup, progress_bar, status_label):
        """
        Streams a release asset to disk while updating the progress bar.
        """
        if download_path.exists():
            download_path.unlink()

        downloaded = 0
        last_ui_update = 0

        with requests.get(download_url, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("content-length") or 0)

            with open(download_path, "wb") as file_obj:
                for chunk in response.iter_content(chunk_size=UPDATE_CHUNK_SIZE):
                    if self._update_download_cancel and self._update_download_cancel.is_set():
                        raise UpdateCancelled()
                    if not chunk:
                        continue

                    file_obj.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_ui_update < 0.1:
                        continue

                    last_ui_update = now
                    if total_size:
                        progress = min(downloaded / total_size, 1)
                        percent = int(progress * 100)
                        status_text = (
                            f"Downloading... {percent}% "
                            f"({self._format_download_size(downloaded)} / {self._format_download_size(total_size)})"
                        )
                    else:
                        progress = 0
                        status_text = f"Downloading... {self._format_download_size(downloaded)}"

                    self._queue_update_ui(
                        popup,
                        lambda value=progress, text=status_text: (
                            progress_bar.set(value),
                            status_label.configure(text=text)
                        )
                    )

        self._queue_update_ui(
            popup,
            lambda: (
                progress_bar.set(1),
                status_label.configure(text="Download complete.")
            )
        )

    def _install_downloaded_update(self, update_info, download_path):
        """
        Creates the platform-specific updater script and exits the current app.
        """
        if not getattr(sys, "frozen", False):
            raise RuntimeError("Automatic installation is available only in the packaged app.")

        if update_info["package_type"] == "windows_exe":
            self._write_and_launch_windows_updater(download_path)
        elif update_info["package_type"] == "mac_zip":
            extract_dir = download_path.parent / "extracted"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir(parents=True, exist_ok=True)

            unzip_cmd = "/usr/bin/unzip" if Path("/usr/bin/unzip").exists() else "unzip"
            subprocess.run(
                [unzip_cmd, "-q", "-o", str(download_path), "-d", str(extract_dir)],
                check=True
            )

            new_app_path = self._find_extracted_macos_app(extract_dir)
            if not new_app_path:
                raise RuntimeError("The downloaded macOS archive did not contain a .app bundle.")

            self._ensure_macos_app_executable(new_app_path)
            self._write_and_launch_posix_updater(new_app_path, download_path.parent)
        else:
            os.chmod(download_path, os.stat(download_path).st_mode | 0o755)
            self._write_and_launch_posix_updater(download_path, download_path.parent)

    def _find_extracted_macos_app(self, extract_dir):
        """
        Locates the .app bundle inside a downloaded macOS release zip.
        """
        expected_app = extract_dir / "FakeNewsAnnotator.app"
        if expected_app.exists():
            return expected_app

        for app_path in extract_dir.rglob("*.app"):
            if "__MACOSX" not in app_path.parts:
                return app_path

        return None

    def _ensure_macos_app_executable(self, app_path):
        """
        Ensures the executable files inside a macOS .app bundle keep launch permissions.
        """
        macos_dir = app_path / "Contents" / "MacOS"
        if not macos_dir.exists():
            return

        for item in macos_dir.iterdir():
            if item.is_file():
                os.chmod(item, os.stat(item).st_mode | 0o755)

    def _write_and_launch_windows_updater(self, new_file_path):
        """
        Writes a batch updater that swaps the Windows executable after this process exits.
        """
        target_path = self._get_current_app_path()
        script_path = new_file_path.parent / "updater.bat"
        backup_path = target_path.with_suffix(target_path.suffix + ".old")

        # Handle existing hidden updater script to avoid PermissionError on Windows
        if script_path.exists():
            try:
                if platform.system() == "Windows":
                    subprocess.run(["attrib", "-h", "-r", "-s", str(script_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                script_path.unlink()
            except Exception:
                pass

        script = f"""@echo off
setlocal enabledelayedexpansion
set "TARGET={target_path}"
set "NEWFILE={new_file_path}"
set "BACKUP={backup_path}"
set RETRIES=0
timeout /t 2 /nobreak >nul
if exist "%BACKUP%" del /f /q "%BACKUP%" >nul 2>&1
:wait_for_exit
if exist "%TARGET%" (
    move /y "%TARGET%" "%BACKUP%" >nul 2>&1
    if errorlevel 1 (
        set /a RETRIES+=1
        if !RETRIES! GEQ 30 exit /b 1
        timeout /t 1 /nobreak >nul
        goto wait_for_exit
    )
)
move /y "%NEWFILE%" "%TARGET%" >nul
if errorlevel 1 (
    if exist "%BACKUP%" move /y "%BACKUP%" "%TARGET%" >nul
    exit /b 1
)
if exist "%BACKUP%" del /f /q "%BACKUP%" >nul 2>&1
start "" "%TARGET%"
del "%~f0"
"""
        script_path.write_text(script, encoding="utf-8")

        try:
            subprocess.run(["attrib", "+h", str(script_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:
            pass

        creation_flags = 0
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

        subprocess.Popen(["cmd", "/c", str(script_path)], close_fds=True, creationflags=creation_flags)
        self._schedule_exit_for_update()

    def _write_and_launch_posix_updater(self, new_item_path, cleanup_dir):
        """
        Writes a shell updater that swaps the macOS app bundle or Linux binary.
        """
        target_path = self._get_current_app_path()
        script_path = cleanup_dir / "updater.sh"

        script = f"""#!/bin/sh
TARGET={shlex.quote(str(target_path))}
NEW_ITEM={shlex.quote(str(new_item_path))}
CLEANUP_DIR={shlex.quote(str(cleanup_dir))}
BACKUP="${{TARGET}}.update-backup"
TRIES=0
sleep 2
rm -rf "$BACKUP"
if [ -e "$TARGET" ]; then
    while ! mv "$TARGET" "$BACKUP" 2>/dev/null; do
        TRIES=$((TRIES + 1))
        if [ "$TRIES" -ge 30 ]; then
            exit 1
        fi
        sleep 1
    done
fi
if mv "$NEW_ITEM" "$TARGET"; then
    rm -rf "$BACKUP"
    if [ -d "$TARGET" ]; then
        xattr -dr com.apple.quarantine "$TARGET" >/dev/null 2>&1
        /usr/bin/open "$TARGET"
    else
        chmod +x "$TARGET" >/dev/null 2>&1
        "$TARGET" >/dev/null 2>&1 &
    fi
    rm -rf "$CLEANUP_DIR"
else
    if [ -e "$BACKUP" ]; then
        mv "$BACKUP" "$TARGET" 2>/dev/null
    fi
fi
"""
        script_path.write_text(script, encoding="utf-8")
        os.chmod(script_path, 0o755)
        subprocess.Popen(["/bin/sh", str(script_path)], close_fds=True)
        self._schedule_exit_for_update()

    def _schedule_exit_for_update(self):
        """
        Gives the updater script a moment to start, then exits the running app.
        """
        try:
            self.after(500, self._exit_for_update)
        except tk.TclError:
            os._exit(0)

    def _exit_for_update(self):
        """
        Terminates the current process so the updater script can replace it.
        """
        try:
            self.destroy()
        finally:
            os._exit(0)

