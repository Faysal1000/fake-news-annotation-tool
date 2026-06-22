"""
DialogMixin mixin class.
"""

import customtkinter as ctk

class DialogMixin:
    def _custom_ask_yes_no_cancel(self, title, message, parent=None):
        owner = parent or self
        popup = ctk.CTkToplevel(owner)
        popup.title(title)
        w, h = 480, 240
        popup.configure(fg_color="#1a1a2e")
        popup.transient(owner)
        
        popup.update_idletasks()
        sx = (popup.winfo_screenwidth() - w) // 2
        sy = (popup.winfo_screenheight() - h) // 2
        popup.geometry(f"{w}x{h}+{sx}+{sy}")
        
        popup.lift()
        popup.focus_force()
        popup.grab_set()
        
        result = [None]
        
        def set_res(val):
            result[0] = val
            popup.grab_release()
            popup.destroy()
            
        ctk.CTkLabel(
            popup, text=title,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#f39c12"
        ).pack(pady=(20, 10))
        
        ctk.CTkLabel(
            popup, text=message,
            font=ctk.CTkFont(size=14),
            text_color="#ecf0f1",
            justify="center",
            wraplength=420
        ).pack(pady=(0, 25), padx=20)
        
        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 20))
        
        btn_inner = ctk.CTkFrame(btn_frame, fg_color="transparent")
        btn_inner.pack(anchor="center")
        
        ctk.CTkButton(
            btn_inner, text="💾 Save", width=110, height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#27ae60", hover_color="#2ecc71",
            command=lambda: set_res(True)
        ).pack(side="left", padx=8)
        
        ctk.CTkButton(
            btn_inner, text="🗑️ Discard", width=110, height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#c0392b", hover_color="#e74c3c",
            command=lambda: set_res(False)
        ).pack(side="left", padx=8)
        
        ctk.CTkButton(
            btn_inner, text="❌ Cancel", width=110, height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#34495e", hover_color="#2c3e50",
            command=lambda: set_res(None)
        ).pack(side="left", padx=8)
        
        popup.protocol("WM_DELETE_WINDOW", lambda: set_res(None))
        self.wait_window(popup)
        return result[0]

    def _custom_ask_yes_no(self, title, message, parent=None):
        owner = parent or self
        popup = ctk.CTkToplevel(owner)
        popup.title(title)
        w, h = 480, 240
        popup.configure(fg_color="#1a1a2e")
        popup.transient(owner)
        
        popup.update_idletasks()
        sx = (popup.winfo_screenwidth() - w) // 2
        sy = (popup.winfo_screenheight() - h) // 2
        popup.geometry(f"{w}x{h}+{sx}+{sy}")
        
        popup.lift()
        popup.focus_force()
        popup.grab_set()
        
        result = [False]
        
        def set_res(val):
            result[0] = val
            popup.grab_release()
            popup.destroy()
            
        ctk.CTkLabel(
            popup, text=title,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#f39c12"
        ).pack(pady=(20, 10))
        
        ctk.CTkLabel(
            popup, text=message,
            font=ctk.CTkFont(size=14),
            text_color="#ecf0f1",
            justify="center",
            wraplength=420
        ).pack(pady=(0, 25), padx=20)
        
        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 20))
        
        btn_inner = ctk.CTkFrame(btn_frame, fg_color="transparent")
        btn_inner.pack(anchor="center")
        
        ctk.CTkButton(
            btn_inner, text="✅ Yes", width=130, height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#27ae60", hover_color="#2ecc71",
            command=lambda: set_res(True)
        ).pack(side="left", padx=15)
        
        ctk.CTkButton(
            btn_inner, text="❌ No", width=130, height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#c0392b", hover_color="#e74c3c",
            command=lambda: set_res(False)
        ).pack(side="left", padx=15)
        
        popup.protocol("WM_DELETE_WINDOW", lambda: set_res(False))
        self.wait_window(popup)
        return result[0]

