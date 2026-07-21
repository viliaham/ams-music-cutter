# DMS / AMS Music Cutter

Source code for the audio-cutting tool bundled with the
"Another Musical System / Battle Music Mod" for Mount & Blade II: Bannerlord.

`batch_loops.py` turns raw mp3 files into ready loop sets (intro / loop / outro):
it detects loop points with the pymusiclooper library and cuts them with ffmpeg.

## What the .exe is

The distributed `DMS_MusicCutter.exe` is exactly this `batch_loops.py`, packaged
with PyInstaller:

    pyinstaller --onefile --console --name DMS_MusicCutter --collect-all pymusiclooper --collect-all librosa --collect-all numba --collect-all soundfile --collect-all audioread batch_loops.py

PyInstaller one-file builds are a common cause of false-positive antivirus flags,
because they unpack to a temp folder at runtime. The source here is the full,
unobfuscated script — nothing else is in the exe.

## Third-party binaries

`ffmpeg.exe` and `ffprobe.exe` shipped next to the tool are the official FFmpeg
Windows builds from gyan.dev (https://www.gyan.dev/ffmpeg/builds/,
release-essentials). They are unmodified, licensed under LGPL/GPL, and are not part
of this code.

## Run from source

- Python 3.10+
- `pip install pymusiclooper`
- ffmpeg + ffprobe on PATH (or next to the script)
- `python batch_loops.py`

## License

Script by Viellar. Free to use and modify with credit. FFmpeg belongs to the
FFmpeg project.
