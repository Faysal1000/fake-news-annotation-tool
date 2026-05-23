"""
Build Script for Fake News Dataset Annotator
=============================================
Creates a standalone executable that includes Python and all dependencies.
Non-technical users can run the app without installing anything.

IMPORTANT: PyInstaller creates platform-specific executables.
  - Run this script on macOS to build a macOS .app
  - Run this script on Windows to build a Windows .exe

Usage:
    python build.py
"""

import subprocess
import sys
import platform

def build():
    """Run PyInstaller to create a standalone executable."""

    # Determine packaging mode based on OS
    # macOS Gatekeeper blocks --onefile + --windowed, so we MUST use --onedir
    mode = "--onedir" if platform.system() == "Darwin" else "--onefile"

    # Base PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "FakeNewsAnnotator",     # Name of the output executable
        "--windowed",                       # No console window (GUI app)
        mode,                               # --onedir for Mac, --onefile for Win/Linux
        "--noconfirm",                      # Overwrite previous build without asking
        "--clean",                          # Clean cache before building
        "annotator_tool.py",               # The main script to bundle
    ]

    print(f"Building for {platform.system()} ({platform.machine()})...")
    print(f"Command: {' '.join(cmd)}\n")

    subprocess.run(cmd, check=True)

    print("\n" + "=" * 60)
    print("BUILD COMPLETE!")
    print("=" * 60)
    if platform.system() == "Darwin":
        print("Output: dist/FakeNewsAnnotator.app")
        print("\nTo distribute: zip the dist/FakeNewsAnnotator.app folder")
        print("Users can double-click the .app to run it.")
    elif platform.system() == "Windows":
        print("Output: dist/FakeNewsAnnotator.exe")
        print("\nTo distribute: share the single file dist/FakeNewsAnnotator.exe")
        print("Users can double-click FakeNewsAnnotator.exe to run it.")
    else:
        print("Output: dist/FakeNewsAnnotator")
        print("\nTo distribute: share the single file dist/FakeNewsAnnotator")
    print("\nNOTE: The images/ folder and dataset.csv will be created")
    print("next to the executable when the user first saves an entry.")


if __name__ == "__main__":
    build()
