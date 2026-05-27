"""XQ 全球贏家 DDE 探測腳本（計畫 Task 1 spike）。

目的：確認能否用 pywin32 DDE client 從 XQ 取得「現股 + 股票期貨 + 零股 + ETF 期貨」的即時報價，
並找出可用的 service / topic / item 字串格式。這是整個資料層成立與否的關鍵未知。

用法：
  1. 先開啟 XQ 全球贏家並登入（行情要在跑）。
  2. 把下面 SYMBOLS 換成你自選清單裡實際的代碼（尤其股期/ETF期/零股的代碼格式）。
  3. 執行：  python scripts/spike_xqdde.py
  4. 把畫面輸出（哪組 service/topic 連得上、哪種 item 格式取得到數字）回報，
     我就能據此實作 arbscan/feed/xqdde.py。

備註：XQ 的 DDE 在 Excel 內通常長這樣： =XQ|Quote!'2330.成交價'
  → application(service) 可能是 "XQ"，topic 可能是 "Quote"，item 可能是 "代碼.欄位"。
  下面把幾個常見候選都試一遍；若全失敗，請打開 XQ「工具→DDE 功能 / 線上說明的 DDE 條目」
  對照實際的 service/topic/item 格式後修改本檔再跑。
"""
import sys
import time

try:
    import dde
    import win32ui  # noqa: F401  (pywin32 的 dde 需要 win32ui 一起在環境中)
except ImportError:
    sys.exit("缺 pywin32：請先 `python -m pip install pywin32` 再跑。")

# --- 候選連線參數（會逐一嘗試 ConnectTo，回報哪一組成功）-------------------
CANDIDATE_SERVICES = ["XQ", "XQLITE", "XQ全球贏家", "DDESERVER"]
CANDIDATE_TOPICS = ["Quote", "即時報價", "RealTime"]

# --- 測試標的（請改成你實際要監控的代碼）-----------------------------------
# 格式不確定的就多放幾個變體，看哪個取得到。
SYMBOLS = {
    "現股整股 台積電": "2330",
    "股票期貨 台積電期(候選代碼,請確認)": "CDF",     # XQ 的股期代碼格式未知，依實際修改
    "零股 台積電(候選)": "2330.TW-OD",               # 零股代碼格式未知，依實際修改
    "ETF期 元大台灣50期(候選)": "NYF",               # ETF 期代碼未知，依實際修改
}

# --- 候選欄位與 item 組法（會對每檔逐一嘗試）-------------------------------
CANDIDATE_FIELDS = ["成交價", "買進價", "賣出價", "買量", "賣量"]
ITEM_FORMATS = ["{sym}.{field}", "{sym}-{field}", "{sym}_{field}"]


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
                    print(f"  [OK] {item:<24} => {val!r}")
                    got_any = True
                except Exception as e:
                    print(f"  [--] {item:<24} ({e})")
                time.sleep(0.15)
        if not got_any:
            print("  ⚠ 這檔沒有任何 item 取得到 → 代碼格式可能不對，請對照 XQ 報價列表的實際代碼。")


def main():
    print("=== XQ DDE 探測開始（請確認 XQ 已開啟且行情在跑）===\n")
    result = try_connect()
    if not result:
        print("\n✗ 所有候選 service/topic 都連不上。")
        print("  請打開 XQ 的 DDE 說明，確認正確的 service/topic 名稱後，修改本檔 CANDIDATE_* 再跑。")
        return
    _svc, _topic, conv = result
    probe(conv)
    print("\n=== 探測結束 ===")
    print("請回報：① 哪組 service/topic 成功 ② 哪種 item 格式(代碼.欄位)取得到數字")
    print("        ③ 股期/零股/ETF期 的實際代碼長怎樣 ④ 數字更新有沒有延遲。")


if __name__ == "__main__":
    main()
