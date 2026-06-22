"""
MediaMixin mixin class.
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageGrab
import os
import re
import subprocess
import platform
from pathlib import Path
from constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from bootstrap import dnd_available, DND_FILES

class MediaMixin:
    # Drag and Drop Implementation

    def _setup_dnd(self):
        """
        Registers drop bindings for the media zone if the tkinterdnd library is loaded.
        """
        global dnd_available
        if dnd_available:
            try:
                self.drop_frame.drop_target_register(DND_FILES)
                self.drop_frame.dnd_bind('<<Drop>>', self._on_drop)
            except Exception as e:
                print(f"[WARNING] Failed to register drop target: {e}")
                self.drop_label.configure(text="Drag & Drop not available\n(Use Browse or Paste instead)")
                dnd_available = False
        else:
            self.drop_label.configure(text="Drag & Drop not available\n(Use Browse or Paste instead)")

    def _on_drop(self, event):
        """
        Processes file paths dropped into the drag-and-drop area.
        Parses raw dropped string data to handle spaces in paths, which are typical 
        on macOS/Windows environments and usually wrapped in curly braces by the Tcl handler.
        It then filters the resolved paths and registers eligible image/video media.
        """
        raw = event.data.strip()
        paths = []
        
        # Regex separates paths, handling space characters enclosed in braces
        for match in re.finditer(r'\{([^{}]+)\}|(\S+)', raw):
            p = match.group(1) or match.group(2)
            if p:
                paths.append(p.strip())

        # Distribute file paths based on extension matches
        added = 0
        for p in paths:
            path = Path(p)
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                self._add_image_from_path(path)
                added += 1
            elif path.suffix.lower() in VIDEO_EXTENSIONS:
                self._add_video_from_path(path)
                added += 1
                
        if added == 0:
            messagebox.showwarning("Invalid File", "Please drop image or video files only.")

    def _browse_media(self):
        """
        Triggers a native file browser dialog configured with extensions for images and videos.
        Dispatches selected items to their respective image or video handler functions.
        """
        ftypes = [
            ("All Media", " ".join(f"*{e}" for e in IMAGE_EXTENSIONS + VIDEO_EXTENSIONS)),
            ("Image files", " ".join(f"*{e}" for e in IMAGE_EXTENSIONS)),
            ("Video files", " ".join(f"*{e}" for e in VIDEO_EXTENSIONS))
        ]
        paths = filedialog.askopenfilenames(title="Select Media", filetypes=ftypes)
        for path in paths:
            p = Path(path)
            if p.suffix.lower() in IMAGE_EXTENSIONS:
                self._add_image_from_path(p)
            elif p.suffix.lower() in VIDEO_EXTENSIONS:
                self._add_video_from_path(p)

    def _paste_image(self):
        """
        Retrieves clipboard contents. Supports both raw raster screenshots (as PIL Image objects)
        and file lists (where files are copied directly in Explorer or Finder).
        Displays a notification if no compatible content is discovered.
        """
        try:
            img = ImageGrab.grabclipboard()
            if img is None:
                messagebox.showinfo("No Image", "No image found in clipboard.")
                return
            if isinstance(img, list):
                # User copied file paths directly
                added = False
                for f in img:
                    if Path(f).suffix.lower() in IMAGE_EXTENSIONS:
                        self._add_image_from_path(Path(f))
                        added = True
                if not added:
                    messagebox.showinfo("No Image", "No image file found in clipboard.")
                return
            # Raw clipboard raster data
            self.image_list.append((None, img))
            self._refresh_previews()
            self.status_label.configure(text="Image pasted from clipboard", text_color="#2ecc71")
        except Exception as e:
            messagebox.showerror("Error", f"Could not paste image: {e}")

    def _add_image_from_path(self, path: Path):
        """
        Performs structural checks on image files from path. Verifies that the file suffix
        matches eligible types and confirms the file is readable by attempting to initialize PIL.
        Stores path as a reference tuple and triggers preview updates.
        """
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            messagebox.showwarning("Invalid File", "Please select an image file only.")
            return
        try:
            Image.open(path)  
            self.image_list.append((path, None))
            self._refresh_previews()
            self.status_label.configure(text=f"Image added: {path.name}", text_color="#2ecc71")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image: {e}")

    def _add_video_from_path(self, path: Path):
        """
        Validates and registers a video file. Only one video may be attached to a dataset record.
        """
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            messagebox.showwarning("Invalid File", "Please select a video file only.")
            return
        if self.video_path is not None:
            messagebox.showwarning("Limit Reached", "Only one video can be inserted per entry.")
            return
        self.video_path = path
        self._refresh_previews()
        self.status_label.configure(text=f"Video added: {path.name}", text_color="#2ecc71")

    def _refresh_previews(self):
        """
        Redraws the layout container for the drop frame.
        When empty, displays drag instruction instructions.
        When populated, compiles a horizontal grid listing all images, video attachments,
        and unresolved missing-file cards (referenced in CSV but absent locally).
        Stores references to CTkImage properties in self.preview_photos to shield objects from GC.
        """
        for widget in self.drop_frame.winfo_children():
            widget.destroy()
        self.preview_photos.clear()

        count = len(self.image_list) + (1 if self.video_path else 0)
        missing_count = len(self.missing_media) if hasattr(self, 'missing_media') else 0
        total_display = count + missing_count

        if total_display == 0:
            self.drop_frame.configure(height=100)
            self.drop_label = ctk.CTkLabel(self.drop_frame,
                                            text="📥 Drag & Drop image(s) here\nor use Browse / Paste buttons above",
                                            font=ctk.CTkFont(size=14), text_color="#888")
            self.drop_label.pack(expand=True, fill="both", pady=20)
            return

        self.drop_frame.configure(height=0)

        count_text = f"{count} media item(s) selected"
        if missing_count > 0:
            count_text += f"  •  ⚠️ {missing_count} file(s) missing"
        count_color = "#e74c3c" if missing_count > 0 and count == 0 else "#2ecc71"
        ctk.CTkLabel(self.drop_frame,
                     text=count_text,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=count_color).pack(pady=(8, 4))

        grid_frame = ctk.CTkFrame(self.drop_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=8, pady=(0, 8))

        thumb_size = (100, 80)
        cols = 5

        # Render preview thumbnails for attached images
        for i, (path, pil_img) in enumerate(self.image_list):
            try:
                if path:
                    img = Image.open(path)
                else:
                    img = pil_img.copy()
                img.thumbnail(thumb_size)
                ctk_photo = ctk.CTkImage(light_image=img, dark_image=img,
                                         size=(img.width, img.height))
                self.preview_photos.append(ctk_photo)  

                frame = ctk.CTkFrame(grid_frame, fg_color="#222240",
                                      corner_radius=6)
                frame.grid(row=i // cols, column=i % cols, padx=4, pady=4)

                lbl = ctk.CTkLabel(frame, image=ctk_photo, text="", cursor="hand2")
                lbl.pack(padx=4, pady=(4, 0))
                lbl.bind("<Button-1>", lambda e, idx=i: self._show_image_popup(idx))

                name = path.name if path else f"clipboard_{i+1}.png"
                ctk.CTkLabel(frame, text=name[:18], font=ctk.CTkFont(size=9),
                             text_color="#aaa").pack(pady=(0, 1))

                if self.current_mode in ("review", "relabel"):
                    ctk.CTkLabel(frame, text="🔍 Click to enlarge",
                                 font=ctk.CTkFont(size=9), text_color="#666").pack(pady=(0, 1))

                if self.current_mode != "relabel":
                    rm_btn = ctk.CTkButton(frame, text="x", width=26, height=20,
                                            font=ctk.CTkFont(size=10),
                                            fg_color="#e74c3c", hover_color="#c0392b",
                                            command=lambda idx=i: self._remove_image(idx))
                    rm_btn.pack(pady=(0, 4))
            except Exception:
                pass

        # Render video icon card if present
        if self.video_path:
            i = len(self.image_list)
            frame = ctk.CTkFrame(grid_frame, fg_color="#402222", corner_radius=6)
            frame.grid(row=i // cols, column=i % cols, padx=4, pady=4)
            
            lbl = ctk.CTkLabel(frame, text="🎬\nVideo", font=ctk.CTkFont(size=24), width=100, height=80, cursor="hand2")
            lbl.pack(padx=4, pady=(4, 0))
            lbl.bind("<Button-1>", lambda e: self._play_video())
            
            name = self.video_path.name
            ctk.CTkLabel(frame, text=name[:18], font=ctk.CTkFont(size=9), text_color="#aaa").pack(pady=(0, 1))
            
            if self.current_mode in ("review", "relabel"):
                ctk.CTkLabel(frame, text="🔍 Click to play", font=ctk.CTkFont(size=9), text_color="#666").pack(pady=(0, 1))
                
            if self.current_mode != "relabel":
                rm_btn = ctk.CTkButton(frame, text="x", width=26, height=20, font=ctk.CTkFont(size=10),
                                        fg_color="#e74c3c", hover_color="#c0392b", command=self._remove_video)
                rm_btn.pack(pady=(0, 4))

        # Render warning panels for missing media references
        if hasattr(self, 'missing_media') and self.missing_media:
            next_idx = len(self.image_list) + (1 if self.video_path else 0)
            for j, (media_type, rel_path) in enumerate(self.missing_media):
                idx = next_idx + j
                frame = ctk.CTkFrame(grid_frame, fg_color="#3a1a1a",
                                      corner_radius=6, border_width=2,
                                      border_color="#e74c3c")
                frame.grid(row=idx // cols, column=idx % cols, padx=4, pady=4)

                icon = "🖼️" if media_type == "image" else "🎬"
                ctk.CTkLabel(frame, text=f"⚠️ {icon}",
                             font=ctk.CTkFont(size=20),
                             width=100, height=50).pack(padx=4, pady=(4, 0))

                ctk.CTkLabel(frame, text="FILE MISSING",
                             font=ctk.CTkFont(size=9, weight="bold"),
                             text_color="#e74c3c").pack(pady=(0, 1))

                filename = Path(rel_path).name if rel_path else "unknown"
                ctk.CTkLabel(frame, text=filename[:20],
                             font=ctk.CTkFont(size=8),
                             text_color="#999").pack(pady=(0, 4))

    def _show_image_popup(self, index):
        """
        Creates a dedicated modal-style window to show a high-resolution display of the selected image.
        Resizes the target image proportionally to fit inside a maximum threshold of 80% screen dimensions.
        """
        if index < 0 or index >= len(self.image_list):
            return

        path, pil_img = self.image_list[index]
        try:
            if path:
                img = Image.open(path)
            else:
                img = pil_img.copy()
        except Exception:
            return

        popup = ctk.CTkToplevel(self)
        popup.title("Image Viewer")
        popup.configure(fg_color="#111")
        popup.attributes("-topmost", True)

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        max_w = int(screen_w * 0.8)
        max_h = int(screen_h * 0.8)
        img.thumbnail((max_w, max_h), Image.LANCZOS)

        popup.geometry(f"{img.width + 40}x{img.height + 100}")

        ctk_photo = ctk.CTkImage(light_image=img, dark_image=img,
                                  size=(img.width, img.height))
        popup._photo_ref = ctk_photo

        lbl = ctk.CTkLabel(popup, image=ctk_photo, text="")
        lbl.pack(expand=True, fill="both", padx=10, pady=(10, 5))

        name = path.name if path else f"clipboard_{index+1}.png"
        ctk.CTkLabel(popup, text=name, font=ctk.CTkFont(size=12),
                     text_color="#aaa").pack(pady=(0, 5))

        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=(0, 10))
        
        if path:
            ctk.CTkButton(btn_frame, text="📂 Open File Location", width=140, height=30,
                          fg_color="#2d6a4f", hover_color="#40916c",
                          command=lambda: [self._open_file_location(path), popup.destroy()]).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_frame, text="Close", width=100, height=30,
                      command=popup.destroy).pack(side="left")

    def _play_video(self):
        if not self.video_path: return
        path_str = str(self.video_path)
        try:
            if platform.system() == "Darwin":
                subprocess.call(('open', path_str))
            elif platform.system() == "Windows":
                os.startfile(path_str)
            else:
                subprocess.call(('xdg-open', path_str))
        except Exception as e:
            messagebox.showerror("Error", f"Could not play video: {e}")

    def _remove_image(self, index):
        """Remove a single image from the image list by its index.
        
        After removal, refreshes the preview grid to update the display.
        
        Args:
            index: Zero-based index of the image to remove.
        """
        if 0 <= index < len(self.image_list):
            self.image_list.pop(index)
            self._refresh_previews()
            self.status_label.configure(text="Image removed", text_color="#888")

    def _remove_video(self):
        self.video_path = None
        self._refresh_previews()
        self.status_label.configure(text="Video removed", text_color="#888")

    def _remove_all_images(self):
        """Remove all images and video from the entry."""
        self.image_list.clear()
        self.video_path = None
        self._refresh_previews()
        self.status_label.configure(text="All media removed", text_color="#888")

