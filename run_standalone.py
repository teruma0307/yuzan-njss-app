from __future__ import annotations

import sys
import threading
import time
import webbrowser
from pathlib import Path

_PORT = 8501


def _open_browser() -> None:
    time.sleep(2)
    webbrowser.open(f"http://localhost:{_PORT}")


def main() -> None:
    if getattr(sys, "frozen", False):
        bundle_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        bundle_dir = Path(__file__).parent

    app_path = str(bundle_dir / "app.py")

    threading.Thread(target=_open_browser, daemon=True).start()

    from streamlit.web import cli as stcli

    # PyInstallerでexe化した環境ではStreamlitが`global.developmentMode`を誤ってtrueと
    # 判定し、(1) server.portが効かなくなる、(2) 自動ブラウザオープンが開発用ポート3000番を
    # 開こうとする、という不具合が実機で確認されたため、明示的にfalseにする。
    # 自動ブラウザオープンもheadlessにしてこちらのスレッドで確実に行う。
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        f"--server.port={_PORT}",
        "--server.headless=true",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
