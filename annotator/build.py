"""
Build Script for Fake News Dataset Annotator

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
import os
from pathlib import Path

def build():
    """Run PyInstaller to create a standalone executable."""
    # Ensure command runs from the script's directory
    script_dir = Path(__file__).parent.resolve()
    os.chdir(script_dir)

    # Determine packaging mode based on OS
    # macOS Gatekeeper blocks --onefile + --windowed, so we MUST use --onedir
    mode = "--onedir" if platform.system() == "Darwin" else "--onefile"
    
    # Use appropriate separator for --add-data
    sep = ";" if platform.system() == "Windows" else ":"
    icon_ext = "icns" if platform.system() == "Darwin" else "ico"

    # Absolute paths for bundling
    version_path = str(script_dir / "src" / "version.json")
    assets_path = str(script_dir / "src" / "assets")
    icon_path = str(script_dir / "src" / "assets" / f"app_icon.{icon_ext}")
    dist_path = str(script_dir / "dist")
    work_path = str(script_dir / "build")
    spec_path = str(script_dir)
    main_path = str(script_dir / "main.py")

    # Base PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "FakeNewsAnnotator",     # Name of the output executable
        "--windowed",                       # No console window (GUI app)
        mode,                               # --onedir for Mac, --onefile for Win/Linux
        f"--icon={icon_path}",              # App icon
        f"--add-data={version_path}{sep}.",   # Include version.json in bundle
        f"--add-data={assets_path}{sep}assets",    # Include assets directory (icons, badges) in bundle
        f"--paths={script_dir / 'src'}",            # Add src to PyInstaller path
        f"--distpath={dist_path}",                  # Output dist directory
        f"--workpath={work_path}",                 # Output build directory
        f"--specpath={spec_path}",                       # Output spec directory
        "--noconfirm",                      # Overwrite previous build without asking
        "--clean",                          # Clean cache before building
    ]

    # OpenCV powers the video-duration filter for non-mp4 containers. It is an
    # optional dependency: only bundle it when it is installed in the build env,
    # so a machine without opencv can still produce a working build (mp4/mov
    # durations are read without it).
    try:
        import cv2  # noqa: F401
        cmd += ["--collect-all", "cv2"]
    except Exception:
        print("[INFO] opencv not found in build env; non-mp4 duration probing "
              "will be unavailable in this build.")

    cmd.append(main_path)  # The entry point script to bundle

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
