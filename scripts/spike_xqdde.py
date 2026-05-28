"""XQ 全球贏家 DDE 探測腳本（計畫 Task 1 spike）。

目的：確認能否用 pywin32 DDE client 從 XQ 取得「現股 + 股票期貨」即時報價，
並確認 service / topic / item 字串格式。這是整個資料層成立與否的關鍵未知。

★重要：請在「你自己開著 XQ 的那台機器、自己的終端機(cmd/PowerShell)」執行本檔。
  DDE 靠 Windows 視窗訊息，跨 session/桌面看不到對方；由代理(Claude)代跑可能連不上。

已查證：XQ DDE 在 Excel 的公式是  =XQLITE|Quote!'2330.TW-Close'
  → service=XQLITE, topic=Quote, 股票 item = 代碼.TW-欄位（欄位用英文，如 Close/Bid/Ask）。

用法：
  1. 開啟 XQ 全球贏家並登入（行情在跑）。若不確定 DDE 是否啟用，先在 Excel 某格貼上
     =XQLITE|Quote!'2330.TW-Close'  看會不會跳出價格（會跳＝DDE 正常）。
  2. 執行：  python scripts/spike_xqdde.py
  3. 把畫面輸出回報，我就能據此實作 arbscan/feed/xqdde.py。
"""
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # 避免 cp950 終端中文亂碼
except Exception:
    pass

try:
    import win32ui  # noqa: F401  必須先 import win32ui（dde 依賴其 MFC 初始化，順序不可顛倒）
    import dde
except ImportError as e:
    sys.exit(f"pywin32/dde 載入失敗：{e}\n請先 `python -m pip install pywin32`。")

# --- 連線參數（XQLITE|Quote 已由 Excel 公式查證；保留 XQ 作備援）-----------
CANDIDATE_SERVICES = ["XQLITE", "XQ"]
CANDIDATE_TOPICS = ["Quote"]

# --- 測試標的（你已填入真實代碼）-------------------------------------------
SYMBOLS = {
    "現股整股 台積電": "2330",
    "股票期貨 台積電期近月": "FICDFN*1",
    "現股整股 群創": "3481",
    "股票期貨 群創期近月": "FIDQF*1",
}

# --- 欄位與 item 組法（已查證 by XQ「複製 DDE 公式」實際輸出）--------------
# 股票 item = 代碼.TW-欄位（例 2330.TW-Bid）；期貨 item = 代碼.TF-欄位（例 FIDQF*1.TF-Bid）
# 一個 item 可以逗號串多欄位一次拿（生產 feed 會這樣用；spike 先單欄位驗證）。
CANDIDATE_FIELDS = ["Bid", "Ask", "Price", "Name"]
ITEM_FORMATS = ["{sym}.TW-{field}", "{sym}.TF-{field}"]


def try_connect():
    """回傳第一組連得上的 (service, topic, conversation)，全失敗回 None。"""
    server = dde.CreateServer()
    server.Create("arbscan_spike")
    for svc in CANDIDATE_SERVICES:
        for topic in CANDIDATE_TOPICS:
            conv = dde.CreateConversation(server)
            try:
                conv.ConnectTo(svc, topic)
                print(f"[OK] 連線成功：service={svc!r} topic={topic!r}")
                return svc, topic, conv
            except Exception as e:
                print(f"[--] ConnectTo 失敗：service={svc!r} topic={topic!r} ({e})")
    return None


def probe(conv):
    """對每檔標的、用每種 item 格式試 Request，印出取得到的值。"""
    for label, sym in SYMBOLS.items():
        print(f"\n=== {label}  代碼={sym} ===")
        got_any = False
        for field in CANDIDATE_FIELDS:
            for fmt in ITEM_FORMATS:
                item = fmt.format(sym=sym, field=field)
                try:
                    val = conv.Request(item)
                    print(f"  [OK] {item:<26} => {val!r}")
                    got_any = True
                except Exception as e:
                    print(f"  [--] {item:<26} ({e})")
                time.sleep(0.15)
        if not got_any:
            print("  ⚠ 這檔沒有任何 item 取得到 → 代碼或欄位格式可能不對。")


def main():
    print("=== XQ DDE 探測開始（請在開著 XQ 的本機終端執行）===\n")
    result = try_connect()
    if not result:
        print("\n✗ ConnectTo 全部失敗。可能原因：")
        print("  1) XQ 未開/未登入（行情沒在跑）。")
        print("  2) XQ 內未啟用 DDE → 先用 Excel 貼 =XQLITE|Quote!'2330.TW-Close' 測試。")
        print("  3) 此終端與 XQ 不在同一桌面 session（例如由代理代跑）→ 請在你自己的終端跑。")
        return
    _svc, _topic, conv = result
    probe(conv)
    print("\n=== 探測結束 ===")
    print("請回報：① 哪種 item 格式(股票/期貨各自)取得到數字 ② Bid/Ask/Close 等欄位名是否正確")
    print("        ③ 期貨 FICDFN*1 用哪種組法取得到 ④ 數字有無延遲。")


if __name__ == "__main__":
    main()
