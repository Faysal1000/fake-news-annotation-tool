"""
UIBuilderMixin mixin class.
"""

import customtkinter as ctk
import tkinter as tk
from PIL import Image, ImageTk
from app_paths import ASSETS_DIR, IMAGES_DIR, VIDEOS_DIR, CSV_PATH
from constants import CATEGORIES, SOURCE_CATEGORIES, MULTI_CATEGORIES
from ui.widgets import FlowFrame
from data.config_manager import load_config

class UIBuilderMixin:
    def _build_ui(self):
        """
        Creates and positions all widgets inside the application window.
        Uses a two-column desktop layout consisting of:
        - Top Bar: mode select buttons and filter indicators
        - Left Panel: heading, body text, and media upload zone
        - Right Panel: classification fields (authenticity, category, confidence, source)
        - Bottom Bar: navigation controls and action buttons
        """
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=18, pady=10)
        self._main_frame = main

        # Top Bar containing Mode Selector and main header label
        top_bar = ctk.CTkFrame(main, fg_color="transparent", height=38)
        top_bar.pack(fill="x", pady=(5, 2))
        top_bar.pack_propagate(False)

        self.mode_switcher = ctk.CTkSegmentedButton(
            top_bar, values=["📝 Annotate", "🔍 Review", "🔄 Re-label"],
            command=self._toggle_mode,
            font=ctk.CTkFont(size=12),
            selected_color="#1f6aa5", selected_hover_color="#144870",
            height=28, width=270
        )
        self.mode_switcher.set("📝 Annotate")
        self.mode_switcher.pack(side="left", padx=(0, 10))
        
        # Filter controls for Review mode
        self.filter_indicator = ctk.CTkLabel(top_bar, text="",
                                              font=ctk.CTkFont(size=12),
                                              text_color="#f39c12")
        
        # Load Filter icon
        self.filter_icon = None
        filter_icon_path = ASSETS_DIR / "filter_icon.png"
        if filter_icon_path.exists():
            try:
                f_img = Image.open(filter_icon_path)
                try:
                    resample_filter = Image.Resampling.LANCZOS
                except AttributeError:
                    try:
                        resample_filter = Image.LANCZOS
                    except AttributeError:
                        resample_filter = Image.ANTIALIAS
                f_img = f_img.resize((32, 32), resample_filter)
                self.filter_icon = ctk.CTkImage(light_image=f_img, dark_image=f_img, size=(16, 16))
            except Exception as e:
                print(f"[WARNING] Failed to load filter_icon.png: {e}")
                
        self.filter_btn = ctk.CTkButton(top_bar, text="Filter", command=self._show_filter_popup,
                                         image=self.filter_icon if self.filter_icon else None,
                                         width=70, height=32,
                                         font=ctk.CTkFont(size=12, weight="bold"),
                                         fg_color="#2d2d5e", hover_color="#3d3d7e",
                                         border_width=1, border_color="#555",
                                         corner_radius=6)
        self.filter_btn._image_label_spacing = 4

        # Search button next to filter (only shown in Review Mode)
        self.search_btn = ctk.CTkButton(top_bar, text="🔍 Search", command=self._show_search_popup,
                                         width=70, height=32,
                                         font=ctk.CTkFont(size=12, weight="bold"),
                                         fg_color="#2d2d5e", hover_color="#3d3d7e",
                                         border_width=1, border_color="#555",
                                         corner_radius=6)

        # Scripts button - always visible in all modes, opens the script runner popup
        self.scripts_btn = ctk.CTkButton(top_bar, text="🛠 Scripts", command=self._show_scripts_popup,
                                          width=90, height=32,
                                          font=ctk.CTkFont(size=13),
                                          fg_color="#2d2d5e", hover_color="#3d3d7e",
                                          border_width=1, border_color="#555",
                                          corner_radius=6)
        self.scripts_btn.pack(side="right", padx=(4, 0))

        # Load App Icon for Main Title
        self.app_title_icon = None
        app_icon_path = ASSETS_DIR / "app_icon.png"
        if app_icon_path.exists():
            try:
                a_img = Image.open(app_icon_path)
                try:
                    resample_filter = Image.Resampling.LANCZOS
                except AttributeError:
                    try:
                        resample_filter = Image.LANCZOS
                    except AttributeError:
                        resample_filter = Image.ANTIALIAS
                a_img = a_img.resize((22, 22), resample_filter)
                self.app_title_icon = ctk.CTkImage(light_image=a_img, dark_image=a_img, size=(22, 22))
            except Exception as e:
                print(f"[WARNING] Failed to load app_icon.png for title: {e}")

        self.title_label = ctk.CTkLabel(
            top_bar, 
            text=" Fake News Dataset Annotator",
            image=self.app_title_icon if self.app_title_icon else None,
            compound="left",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        self.title_label.place(relx=0.5, rely=0.5, anchor="center")

        # Top stats cards area
        self.stats_frame = FlowFrame(main, fg_color="transparent")
        self.stats_frame.pack(fill="x", pady=(4, 2))

        # Secondary categories stats cards
        self.category_stats_frame = FlowFrame(main, fg_color="transparent")
        self.category_stats_frame.pack(fill="x", pady=(0, 6))

        # UUID display container (alternative to News Categories stats in Review Mode)
        self.uuid_display_frame = ctk.CTkFrame(main, fg_color="transparent", height=24)
        
        self.uuid_lbl = ctk.CTkLabel(self.uuid_display_frame, text="ID: N/A", font=ctk.CTkFont(size=13, weight="bold"), text_color="#aaa")
        self.uuid_lbl.pack(side="left", padx=(10, 4), pady=2)
        
        def copy_uuid():
            uuid_str = getattr(self, "_current_uuid_str", "")
            if uuid_str:
                self.clipboard_clear()
                self.clipboard_append(uuid_str)
                self.update()
                orig = self.uuid_copy_btn.cget("text")
                self.uuid_copy_btn.configure(text="✅")
                self.after(1000, lambda: self.uuid_copy_btn.configure(text=orig))
                
        self.uuid_copy_btn = ctk.CTkButton(
            self.uuid_display_frame, text="📋", width=22, height=22,
            font=ctk.CTkFont(size=12), fg_color="transparent", hover_color="#2b2b36",
            text_color="#aaa", command=copy_uuid
        )
        self.uuid_copy_btn.pack(side="left", padx=(2, 10), pady=2)

        # Bottom controls container
        self.bottom_bar = ctk.CTkFrame(main, fg_color="#1a1a2e", corner_radius=8,
                                        border_width=1, border_color="#333")
        self.bottom_bar.pack(side="bottom", fill="x", pady=(6, 0))
        self.bottom_bar.columnconfigure(0, weight=1, uniform="btm")
        self.bottom_bar.columnconfigure(1, weight=1, uniform="btm")

        # Left controls (Navigation)
        self.nav_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")

        self.prev_btn = ctk.CTkButton(self.nav_frame, text="← Previous",
                                       command=self._prev_record, width=100, height=32,
                                       font=ctk.CTkFont(size=12),
                                       fg_color="transparent", border_width=1,
                                       border_color="#555", hover_color="#333")
        self.prev_btn.pack(side="left", padx=(0, 10))

        # Page index / total counter block
        self.record_center_frame = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        self.record_center_frame.pack(side="left", expand=True)
        
        self.record_index_entry = ctk.CTkEntry(self.record_center_frame, width=50, height=28,
                                                font=ctk.CTkFont(size=13, weight="bold"), justify="center")
        self.record_index_entry.pack(side="left")
        self.record_index_entry.bind("<Return>", self._jump_to_record)
        
        self.record_total_label = ctk.CTkLabel(self.record_center_frame, text="/ 0",
                                                font=ctk.CTkFont(size=13), text_color="#aaa")
        self.record_total_label.pack(side="left", padx=(4, 0))

        self.next_btn = ctk.CTkButton(self.nav_frame, text="Next →",
                                       command=self._next_record, width=100, height=32,
                                       font=ctk.CTkFont(size=12),
                                       fg_color="#1f6aa5", hover_color="#144870")
        self.next_btn.pack(side="left", padx=(10, 0))

        # Right controls (Save / Clear actions)
        self.action_btn_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        self.action_btn_frame.grid(row=0, column=1, sticky="ew", padx=(8, 8), pady=6)

        self.primary_btn = ctk.CTkButton(self.action_btn_frame, text="💾  Save Entry",
                       command=self._save_entry,
                       height=38, font=ctk.CTkFont(size=14, weight="bold"),
                       fg_color="#2ecc71", hover_color="#27ae60",
                       text_color="black")
        self.primary_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.secondary_btn = ctk.CTkButton(self.action_btn_frame, text="🗑  Clear All",
                       command=self._clear_all,
                       height=38, width=130, font=ctk.CTkFont(size=14),
                       fg_color="#444", hover_color="#555",
                       border_width=1, border_color="#666")
        self.secondary_btn.pack(side="left")

        # Two Column Main Area
        self.content_container = ctk.CTkFrame(main, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, pady=(4, 0))

        # Left Column containing input text area and drop targets
        self.left_col = ctk.CTkFrame(self.content_container, fg_color="transparent")

        # Heading entry field
        self.heading_header = self._section(self.left_col, "News Heading (optional)")
        self._heading_dup_state = "hidden"
        self.heading_dup_badge = ctk.CTkFrame(
            self.heading_header,
            fg_color="transparent",
            corner_radius=6,
            border_width=0,
            border_color="#555555",
            cursor="arrow"
        )
        self.heading_dup_text = ctk.CTkLabel(
            self.heading_dup_badge,
            text="",
            height=18,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#aaaaaa"
        )
        self.heading_dup_text.pack(expand=True, fill="both")
        
        # Hover effect bindings
        def on_enter_badge(e):
            if getattr(self, "_heading_dup_state", "hidden") == "duplicates_found":
                self.heading_dup_badge.configure(fg_color="#523a15")
        def on_leave_badge(e):
            if getattr(self, "_heading_dup_state", "hidden") == "duplicates_found":
                self.heading_dup_badge.configure(fg_color="#3d2b0f")
            
        self.heading_dup_badge.bind("<Enter>", on_enter_badge)
        self.heading_dup_badge.bind("<Leave>", on_leave_badge)
        self.heading_dup_text.bind("<Enter>", on_enter_badge)
        self.heading_dup_text.bind("<Leave>", on_leave_badge)
        
        # Click bindings to trigger review duplicates popup
        self.heading_dup_badge.bind("<Button-1>", lambda e: self._on_heading_dup_click())
        self.heading_dup_text.bind("<Button-1>", lambda e: self._on_heading_dup_click())

        
        # Load Google search icon
        self.google_search_icon = None
        google_icon_path = ASSETS_DIR / "google_icon.png"
        if google_icon_path.exists():
            try:
                g_img = Image.open(google_icon_path)
                try:
                    resample_filter = Image.Resampling.LANCZOS
                except AttributeError:
                    try:
                        resample_filter = Image.LANCZOS
                    except AttributeError:
                        resample_filter = Image.ANTIALIAS
                
                # Pre-resize to 32x32 using high-quality filter to prevent Tkinter downscale pixelation
                g_img = g_img.resize((32, 32), resample_filter)
                self.google_search_icon = ctk.CTkImage(light_image=g_img, dark_image=g_img, size=(16, 16))
            except Exception as e:
                print(f"[WARNING] Failed to load google_icon.png: {e}")

        self.heading_search_btn = ctk.CTkButton(
            self.heading_header,
            text="Search",
            image=self.google_search_icon if self.google_search_icon else None,
            command=self._open_heading_search,
            width=70,
            height=26,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2d2d5e",
            hover_color="#3d3d7e",
            border_width=1,
            border_color="#555",
            corner_radius=6
        )
        self.heading_search_btn._image_label_spacing = 4
        self.heading_entry = ctk.CTkTextbox(self.left_col, height=55, font=ctk.CTkFont(size=13),
                                            border_width=1, border_color="#555", undo=True)
        self.heading_entry.pack(fill="x", padx=10, pady=(0, 6))
        self.heading_entry.bind("<KeyRelease>", self._on_heading_key_release)

        # Article text entry field
        self._section(self.left_col, "📝 News Text (required if no image)")
        self.text_box = ctk.CTkTextbox(self.left_col, height=120, font=ctk.CTkFont(size=13),
                                        border_width=1, border_color="#555", undo=True)
        self.text_box.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.text_box.bind("<KeyRelease>", self._on_text_key_release)

        # Upload / Pasting controls
        self._section(self.left_col, "🖼️ Images & Video (required if no text)")
        img_btn_frame = ctk.CTkFrame(self.left_col, fg_color="transparent")
        img_btn_frame.pack(fill="x", padx=10, pady=(0, 4))

        ctk.CTkButton(img_btn_frame, text="📁 Browse", command=self._browse_media,
                       width=100, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(img_btn_frame, text="📋 Paste", command=self._paste_image,
                       width=100, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(img_btn_frame, text="❌ Remove All", command=self._remove_all_images,
                       width=110, height=26, font=ctk.CTkFont(size=12),
                       fg_color="#e74c3c", hover_color="#c0392b").pack(side="left")

        # Main drop target frame for Drag and Drop operations
        self.drop_frame = ctk.CTkFrame(self.left_col, height=80, border_width=2,
                                        border_color="#666", fg_color="#1a1a2e")
        self.drop_frame.pack(fill="both", padx=10, pady=(4, 6))

        self.drop_label = ctk.CTkLabel(self.drop_frame,
                                        text="📥 Drag & Drop image(s) / video here\nor use Browse / Paste buttons above",
                                        font=ctk.CTkFont(size=13), text_color="#888")
        self.drop_label.pack(expand=True, fill="both", pady=15)

        # Right Column containing categorical selectors and validation constraints
        self.right_col = ctk.CTkFrame(self.content_container, fg_color="#1a1a2e",
                                       corner_radius=10, border_width=1, border_color="#333")

        # Annotator Name
        self._section(self.right_col, "Annotator name *")
        self.annotator_entry = ctk.CTkEntry(self.right_col, placeholder_text="Your name", height=32)
        self.annotator_entry.pack(fill="x", padx=12, pady=(0, 8))

        saved_name = load_config()
        if saved_name:
            self.annotator_entry.insert(0, saved_name)

        # Authenticity Selectors
        self._section(self.right_col, "News Authenticity *")
        label_frame = ctk.CTkFrame(self.right_col, fg_color="transparent")
        label_frame.pack(fill="x", padx=12, pady=(0, 6))
        label_frame.grid_columnconfigure((0, 1), weight=1, uniform="toggles")

        self.label_var = ctk.StringVar(value="")

        # Fake authenticity option
        self.fake_toggle_btn = ctk.CTkButton(
            label_frame, text="❌  FAKE",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, corner_radius=8,
            fg_color="transparent", hover_color="#4a1a1a",
            border_width=2, border_color="#555",
            text_color="#888",
            command=lambda: self._set_label("Fake")
        )
        self.fake_toggle_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        # Real authenticity option
        self.real_toggle_btn = ctk.CTkButton(
            label_frame, text="✅  REAL",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, corner_radius=8,
            fg_color="transparent", hover_color="#1a4a1a",
            border_width=2, border_color="#555",
            text_color="#888",
            command=lambda: self._set_label("Real")
        )
        self.real_toggle_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Multi-category selection subframe (displayed for Fake news only)
        self.multi_cat_frame = ctk.CTkFrame(self.right_col, fg_color="#222244",
                                             corner_radius=8, border_width=1,
                                             border_color="#444")
        self.multi_cat_var = ctk.StringVar(value="")

        # Done review badge container for kappa mode
        self.done_indicator_frame = ctk.CTkFrame(self.right_col, fg_color="transparent")
        self.done_indicator_frame.bind("<Configure>", self._on_done_indicator_configure)
        
        # Preload the reviewed badge image for the Done popup
        self.reviewed_badge_img = None
        try:
            r_img = Image.open(ASSETS_DIR / "reviewed_badge.png")
            self.reviewed_badge_img = ctk.CTkImage(light_image=r_img, dark_image=r_img, size=(220, 220))
        except Exception: pass

        self.done_label = ctk.CTkLabel(self.done_indicator_frame, text="")
        self.done_label.pack(expand=True, fill="both", pady=10)

        mc_header = ctk.CTkFrame(self.multi_cat_frame, fg_color="transparent")
        mc_header.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(mc_header, text="⚠️ Fake News Type",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#f39c12").pack(side="left", padx=(0, 2))
        ctk.CTkLabel(mc_header, text="*",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#e74c3c").pack(side="left")

        mc_radios = ctk.CTkFrame(self.multi_cat_frame, fg_color="transparent")
        mc_radios.pack(fill="x", padx=10, pady=(0, 8))

        self.radio_misinfo = ctk.CTkRadioButton(
            mc_radios, text="Misinformation", variable=self.multi_cat_var,
            value="Misinformation", font=ctk.CTkFont(size=12),
            fg_color="#e67e22", hover_color="#d35400")
        self.radio_misinfo.pack(side="left", padx=(0, 12))
        
        self.radio_satire = ctk.CTkRadioButton(
            mc_radios, text="Satire", variable=self.multi_cat_var,
            value="Satire", font=ctk.CTkFont(size=12),
            fg_color="#9b59b6", hover_color="#8e44ad")
        self.radio_satire.pack(side="left", padx=(0, 12))
        
        self.radio_clickbait = ctk.CTkRadioButton(
            mc_radios, text="Clickbait", variable=self.multi_cat_var,
            value="Clickbait", font=ctk.CTkFont(size=12),
            fg_color="#e74c3c", hover_color="#c0392b")
        self.radio_clickbait.pack(side="left")

        # Main news and platform category selectors
        cat_row_header = ctk.CTkFrame(self.right_col, fg_color="transparent")
        cat_row_header.pack(fill="x", padx=10, pady=(10, 3))
        cat_row_header.columnconfigure(0, weight=1, uniform="catcol")
        cat_row_header.columnconfigure(1, weight=1, uniform="catcol")

        nc_lbl_frame = ctk.CTkFrame(cat_row_header, fg_color="transparent")
        nc_lbl_frame.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(nc_lbl_frame, text="News Category",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(nc_lbl_frame, text=" *",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color="#e74c3c").pack(side="left")

        sc_lbl_frame = ctk.CTkFrame(cat_row_header, fg_color="transparent")
        sc_lbl_frame.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ctk.CTkLabel(sc_lbl_frame, text="Source Category",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(sc_lbl_frame, text=" *",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color="#e74c3c").pack(side="left")

        cat_row = ctk.CTkFrame(self.right_col, fg_color="transparent")
        cat_row.pack(fill="x", padx=12, pady=(0, 8))
        cat_row.columnconfigure(0, weight=1, uniform="catdrop")
        cat_row.columnconfigure(1, weight=1, uniform="catdrop")

        self.category_var = ctk.StringVar(value="")
        self.category_menu = ctk.CTkOptionMenu(cat_row, variable=self.category_var,
                                                values=CATEGORIES, height=32,
                                                dynamic_resizing=False)
        self.category_menu.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.source_cat_var = ctk.StringVar(value="")
        self.source_cat_menu = ctk.CTkOptionMenu(cat_row, variable=self.source_cat_var,
                                                  values=SOURCE_CATEGORIES, height=32,
                                                  dynamic_resizing=False)
        self.source_cat_menu.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Confidence rating
        self._section(self.right_col, "Confidence (%)")
        self.confidence_entry = ctk.CTkEntry(self.right_col, placeholder_text="100", height=32, justify="center")
        self.confidence_entry.pack(fill="x", padx=12, pady=(0, 8))
        self.confidence_entry.insert(0, "100")

        # News Source link
        self._section(self.right_col, "Source Link")
        self.source_entry = ctk.CTkEntry(self.right_col, placeholder_text="Paste URL or link here", height=32)
        self.source_entry.pack(fill="x", padx=12, pady=(0, 8))

        # Internal Annotator notes textbox
        self._section(self.right_col, "Additional Notes")
        notes_hint = ctk.CTkLabel(self.right_col, text="For annotator use only — e.g., personal notes or remarks outside of classification",
                                   font=ctk.CTkFont(size=10, slant="italic"), text_color="#666")
        notes_hint.pack(fill="x", padx=12, pady=(0, 2))
        self.notes_entry = ctk.CTkTextbox(self.right_col, font=ctk.CTkFont(size=13),
                                           border_width=1, border_color="#555", undo=True)
        self.notes_entry.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Establish base columns
        self._arrange_columns()
        self.content_container.bind("<Configure>", self._on_content_resize)

        class DummyLabel:
            def configure(self, *args, **kwargs): pass
        self.status_label = DummyLabel()

    def _section(self, parent, text):
        """
        Creates a bold text header to separate sections inside the control panel.
        Displays trailing '*' symbols in standard red to denote required fields.
        """
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=(10, 3))
        
        if text.endswith("*"):
            main_text = text[:-1].rstrip()
            lbl = ctk.CTkLabel(frame, text=main_text, font=ctk.CTkFont(size=15, weight="bold"))
            lbl.pack(side="left")
            ast = ctk.CTkLabel(frame, text=" *", font=ctk.CTkFont(size=15, weight="bold"), text_color="#e74c3c")
            ast.pack(side="left")
        else:
            lbl = ctk.CTkLabel(frame, text=text, font=ctk.CTkFont(size=15, weight="bold"))
            lbl.pack(side="left")

        return frame

    def _inline_label(self, parent, text, width=140):
        """
        Helper to construct fixed-width label wrappers for horizontal layout alignment.
        """
        frame = ctk.CTkFrame(parent, width=width, height=36, fg_color="transparent")
        frame.pack_propagate(False)
        frame.pack(side="left", padx=(0, 10))
        
        if text.endswith("*"):
            main_text = text[:-1].rstrip()
            ctk.CTkLabel(frame, text=main_text, font=ctk.CTkFont(size=13)).pack(side="left")
            ctk.CTkLabel(frame, text=" *", font=ctk.CTkFont(size=13, weight="bold"), text_color="#e74c3c").pack(side="left")
        else:
            ctk.CTkLabel(frame, text=text, font=ctk.CTkFont(size=13)).pack(side="left")

    def _arrange_columns(self):
        """
        Fixes the content container to use a balanced two-column grid.
        """
        self.content_container.columnconfigure(0, weight=1, uniform="col")
        self.content_container.columnconfigure(1, weight=1, uniform="col")
        self.content_container.rowconfigure(0, weight=1)

        self.left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.right_col.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    def _on_content_resize(self, event=None):
        pass

    def _on_done_indicator_configure(self, event):
        """
        Handler to scale the reviewed check badge dynamically with window resizing constraints.
        """
        if not self.reviewed_badge_img:
            return
        w = event.width
        h = event.height
        size = min(w - 24, h - 30, 220)
        size = max(100, size)
        if self.reviewed_badge_img.cget("size") != (size, size):
            self.reviewed_badge_img.configure(size=(size, size))

    def _update_heading_search_visibility(self, event=None):
        """
        Shows the Google search button only in Review/Re-label modes when a heading exists.
        """
        if not hasattr(self, "heading_search_btn"):
            return

        should_show = self.current_mode in ("review", "relabel") and bool(self._get_heading_text())
        is_visible = bool(self.heading_search_btn.winfo_manager())

        if should_show and not is_visible:
            self.heading_search_btn.pack(side="right", padx=(8, 0))
        elif not should_show and is_visible:
            self.heading_search_btn.pack_forget()

