"""One command for the demo video: capture -> TTS -> assemble.

    PLAYWRIGHT_BROWSERS_PATH=/Volumes/Crucial1TB/.cache/ms-playwright \
    .venv/bin/python scripts/video/make_video.py [--skip-capture] [--skip-tts]

Output: out/video/smoke-or-vog-demo.mp4 (git-ignored). Needs OPENAI_API_KEY in .env.local
(for TTS only) and the pins in requirements-video.txt.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable

if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--skip-capture" not in args:
        subprocess.run([PY, str(HERE / "capture.py")], check=True)
    if "--skip-tts" not in args:
        subprocess.run([PY, str(HERE / "tts.py")], check=True)
    subprocess.run([PY, str(HERE / "assemble.py")], check=True)
