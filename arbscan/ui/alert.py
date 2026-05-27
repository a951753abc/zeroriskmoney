def beep(times: int = 1) -> None:
    """達標響鈴（Windows）。非 Windows 環境改印 BEL。"""
    try:
        import winsound
        for _ in range(times):
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        print("\a", end="", flush=True)
