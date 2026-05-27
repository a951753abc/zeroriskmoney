import time
from datetime import datetime
from rich.console import Console
from rich.live import Live
from arbscan.scanner import Scanner
from arbscan.ui.table import build_table
from arbscan.ui.alert import beep

def run_once(scanner: Scanner, now: datetime, as_of: str, data_version: str, render: bool = True) -> int:
    results = scanner.scan(now)
    new = scanner.detect_new_signals(results)
    if new:
        beep(len(new))
    if render:
        Console().print(build_table(results, as_of, data_version, scanner.min_net_threshold))
    return len(results)

def run_loop(scanner: Scanner, refresh_seconds: int, data_version: str) -> None:
    if not scanner.feed.is_connected():
        raise RuntimeError("資料源未連線（XQ 是否開啟？）")
    with Live(auto_refresh=False) as live:
        while True:
            now = datetime.now()
            results = scanner.scan(now)
            new = scanner.detect_new_signals(results)
            if new:
                beep(len(new))
            live.update(build_table(results, now.strftime("%H:%M:%S"), data_version, scanner.min_net_threshold), refresh=True)
            time.sleep(refresh_seconds)
