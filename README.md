# arbscan — 台股股票期貨 vs 現股 準套利訊號掃描器

盤中即時掃描台股**股票期貨/ETF 期貨**與標的**現股**的價差：放空 1 口期貨 + 買進等量現股，持有到結算收斂。算出進場價差、保守淨利、到結算需備妥的壓力本金、占用資金年化，達標跳警示。**只掃訊號、手動下單。**

> ⚠️ **定性**：這是**相對價差/準套利訊號**，**非無風險套利**。股票期貨現金結算，最後結算價為標的收盤前 60 分鐘均價，現股無法保證以該價出場 → 有殘留基差風險。所有數字皆為 `indicative`，**下單前請自行覆核**。

## 現況

**已完成並測試綠（27 tests）：**
- 領域型別 `arbscan/models.py`
- 計算引擎（純函式）`arbscan/engine/`：價差、費稅、資金成本、保守淨利、壓力本金、年化、排除規則
- 編排 `arbscan/scanner.py`、設定 `arbscan/config.py`、Feed 介面 + MockFeed、終端 UI `arbscan/ui/`、主迴圈 `arbscan/main.py`

**待補（需本機開 XQ／連實站才能驗）：**
- XQ DDE spike（`scripts/spike_xqdde.py`）：確認可匯出股期/零股/ETF 期報價（計畫 Task 1）
- 參考資料抓取腳本 `scripts/fetch_*.py`：TAIFEX/TWSE → `data/reference.sqlite`（計畫 Task 11）
- `arbscan/feed/xqdde.py`：依 spike 結果實作 DDE 取值（計畫 Task 13）
- `arbscan/main.py` 的 `main()` 進入點：串接設定 + 參考資料 + XQDDEFeed（計畫 Task 17）

## 安裝

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q          # 應全綠
```

## 設定

```powershell
copy data\config.example.toml data\config.toml
```
編輯 `data\config.toml`：填你的手續費折數、門檻、buffer、資金利率。（`data\config.toml` 與 `data\*.sqlite` 已 gitignore，不會外洩個人設定。）

## 更新參考資料（待腳本實作後）

```powershell
python scripts\fetch_contracts.py
python scripts\fetch_margins.py
python scripts\fetch_dividends.py
python scripts\fetch_contract_adjustments.py
```

## 啟動（待 XQ DDE spike 與 main() 串接後）

先開啟 XQ 全球贏家，再：
```powershell
python -m arbscan.main
```

## 文件

- 設計 spec：`docs/superpowers/specs/2026-05-27-stf-spot-arb-scanner-design.md`
- 實作計畫：`docs/superpowers/plans/2026-05-27-stf-spot-arb-scanner.md`
