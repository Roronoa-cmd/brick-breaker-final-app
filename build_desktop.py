"""Builds the desktop version of the game (Windows .exe / Linux program) with PyInstaller.

Run it from the folder that contains main.py, audio_data.py and icon.png:

    python -m pip install "kivy[base]" pyinstaller pillow
    python build_desktop.py

Result:
    dist/BrickBreaker/                  the app folder (BrickBreaker.exe inside on Windows)
    out/BrickBreaker-windows.zip        (on Windows)
    out/BrickBreaker-linux.tar.gz       (on Linux)

Set the environment variable PYI_MODE to an empty value to get a build that shows a
console window with error messages (handy if the app does not open).
"""
import importlib.util
import os
import shutil
import sys

NAME = "BrickBreaker"


def module_exists(name):
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def make_icon():
    """Windows needs an .ico file for the .exe icon; make it from icon.png."""
    try:
        from PIL import Image
        Image.open("icon.png").convert("RGBA").save(
            "icon.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        return True
    except Exception as e:
        print("could not make icon.ico, building without it:", e)
        return False


def build_args(plat, mode, has_module, icon_ok):
    args = ["main.py", "--name", NAME, "--noconfirm", "--clean", "--onedir",
            "--hidden-import", "audio_data",
            "--hidden-import", "kivy.core.audio.audio_sdl2"]
    if os.path.exists("icon.png"):
        args += ["--add-data", "icon.png" + os.pathsep + "."]
    if mode:
        args.append(mode)
    if plat == "win32":
        if icon_ok:
            args += ["--icon", "icon.ico"]
        # Kivy's Windows graphics/audio libraries live in the kivy_deps packages
        for mod in ("kivy_deps.sdl2", "kivy_deps.glew", "kivy_deps.angle"):
            if has_module(mod):
                args += ["--collect-all", mod]
            else:
                print("not installed, skipped:", mod)
    return args


def main():
    if not os.path.exists("main.py"):
        sys.exit("Run this from the folder that contains main.py")
    import PyInstaller.__main__ as pyi

    mode = os.environ.get("PYI_MODE", "--windowed")
    icon_ok = make_icon() if sys.platform == "win32" else False
    args = build_args(sys.platform, mode, module_exists, icon_ok)
    print("PyInstaller arguments:", args)
    pyi.run(args)

    folder = os.path.join("dist", NAME)
    if not os.path.isdir(folder):
        sys.exit("Build failed: " + folder + " was not created")

    os.makedirs("out", exist_ok=True)
    if sys.platform == "win32":
        archive = shutil.make_archive(os.path.join("out", NAME + "-windows"), "zip", "dist", NAME)
    else:
        archive = shutil.make_archive(os.path.join("out", NAME + "-linux"), "gztar", "dist", NAME)
    print("DONE ->", archive)


if __name__ == "__main__":
    main()
