"""Excel 橋接 spike：確認 Python 能透過 COM 讀到 Excel 裡的 XQ DDE 報價儲存格。

背景：XQ→DDE→Excel 已驗證可用（公式 =XQLITE|Quote!'...' 在 Excel 可取到值）。
但 Python→DDE→XQ（pywin32 dde）ConnectTo 失敗。
轉用「XQ↔DDE↔Excel↔COM↔Python」橋接，DDE 由 Excel 處理、Python 走較穩的 COM。

用法：
  1. XQ 全球贏家保持開著、行情在跑。
  2. Excel 開著、含 `=XQLITE|Quote!'...'` 公式的活頁簿在前景（例如你 XQ 匯出的那本）。
  3. 執行：  python scripts/spike_excel_bridge.py
  4. 把畫面輸出（找到幾個儲存格、公式與當下值）回報。

若沒找到任何 XQLITE 公式儲存格，腳本會告訴你怎麼快速加一格再跑。
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import win32com.client
except ImportError as e:
    sys.exit(f"pywin32 載入失敗：{e}\n請先 `python -m pip install pywin32`。")


def main():
    print("=== Excel COM 橋接探測開始 ===\n")
    try:
        xl = win32com.client.GetActiveObject("Excel.Application")
    except Exception as e:
        sys.exit(f"無法連到執行中的 Excel：{e}\n請確認 Excel 已開啟、含 XQ DDE 公式的活頁簿。")

    print(f"Excel 版本：{xl.Version}")
    print(f"開啟中的活頁簿數：{xl.Workbooks.Count}\n")

    total_found = 0
    for wb in xl.Workbooks:
        print(f"--- 活頁簿：{wb.Name} ---")
        for ws in wb.Worksheets:
            try:
                used = ws.UsedRange
                nrows = min(int(used.Rows.Count), 100)
                ncols = min(int(used.Columns.Count), 100)
            except Exception as e:
                print(f"  Sheet '{ws.Name}' 讀取 UsedRange 失敗：{e}")
                continue

            sheet_hits = 0
            for row in range(1, nrows + 1):
                for col in range(1, ncols + 1):
                    try:
                        cell = ws.Cells(row, col)
                        formula = str(cell.Formula or "")
                        if "XQLITE" in formula or "Quote!" in formula:
                            sheet_hits += 1
                            total_found += 1
                            if sheet_hits <= 10:
                                try:
                                    value = cell.Value
                                except Exception as ve:
                                    value = f"<read error: {ve}>"
                                print(f"  [{ws.Name} R{row}C{col}]")
                                print(f"    formula = {formula}")
                                print(f"    value   = {value!r}")
                    except Exception:
                        pass
            if sheet_hits > 10:
                print(f"  ...(此 sheet 共找到 {sheet_hits} 個 XQ DDE 儲存格，僅列前 10 個)")

    print()
    if total_found == 0:
        print("⚠ 沒找到任何含 XQLITE 公式的儲存格。請：")
        print("  1) 確認你那本 XQ 匯出的 Excel 是開著的、有報價跳動。")
        print("  2) 或在任一空白 Excel 的 A1 貼上：=XQLITE|Quote!'2330.TW-Bid'")
        print("     確認跳出價格後，重跑本腳本。")
    else:
        print(f"✓ 共找到 {total_found} 個 DDE 儲存格，Python 透過 COM 讀得到。")
        print("  → 確認 Excel 橋接方案可行；接下來會實作 arbscan/feed/excel_bridge.py：")
        print("    自動把所需 symbol×field 寫成公式到 Excel、再由 Python 輪詢讀回。")


if __name__ == "__main__":
    main()
