"""
Fake News Dataset Annotator Entry Point.

Ensures dependencies are checked and installed before loading any external library,
then initializes and launches the AnnotatorTool GUI application.
"""

from bootstrap import _check_and_install
_check_and_install()

from ui.main_window import AnnotatorTool

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    app = AnnotatorTool()
    app.mainloop()
