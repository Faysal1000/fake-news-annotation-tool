"""
Reusable GUI widget definitions.

Contains the FlowFrame custom container and re-exports UpdateCancelled.
"""

import customtkinter as ctk
from constants import UpdateCancelled

class FlowFrame(ctk.CTkFrame):
    """
    A custom frame container that automatically wraps child widgets to the next line
    when they exceed the available horizontal width of the frame.
    """
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.bind("<Configure>", self._on_configure)

    def _arrange(self):
        width = self.winfo_width()
        if width <= 10:  # Skip layout calculation if frame is not fully initialized/drawn yet
            return
            
        rows = []
        current_row = []
        x = 0
        max_height = 0
        
        # Group child widgets into rows based on their required widths
        for child in self.winfo_children():
            cw = child.winfo_reqwidth()
            ch = child.winfo_reqheight()
            
            # Wrap to next row if this child overflows the current width
            if x + cw > width and current_row:
                rows.append((current_row, x - 10, max_height))  # Subtract 10 to account for trailing space
                current_row = []
                x = 0
                max_height = 0
                
            current_row.append((child, cw, ch))
            x += cw + 10  # Horizontal spacing between elements
            max_height = max(max_height, ch)
            
        if current_row:
            rows.append((current_row, x - 10, max_height))
            
        # Draw and position the rows and elements dynamically
        y = 0
        total_height = 0
        for row_items, row_width, row_height in rows:
            start_x = (width - row_width) // 2
            start_x = max(0, start_x)  # Prevent negative alignment coordinates
            
            x_offset = start_x
            for child, cw, ch in row_items:
                child.place(x=x_offset, y=y)
                x_offset += cw + 10
                
            y += row_height + 5  # Vertical spacing between rows
            total_height += row_height + 5
            
        if total_height > 0:
            total_height -= 5  # Remove trailing vertical spacing
            
        if total_height != self.winfo_reqheight() and total_height > 0:
            self.configure(height=total_height)

    def _on_configure(self, event=None):
        self._arrange()
