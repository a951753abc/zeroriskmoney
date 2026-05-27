# 台股股票期貨 vs 現股 準套利訊號掃描器 — 設計文件

> 日期：2026-05-27 ／ 狀態：設計 v2（已納入 Codex 兩輪審查 + TAIFEX 規則查證）
> v1 嚴謹度方針：**防假訊號的安全項全做**；資金成本／壓力本金／年化採**保守近似閉式**（不建完整逐日 T+2 現金流帳本），一律往「高估成本/本金、低估利潤」偏。

## 0. 定性（重要：非無風險套利）
掃描的是**相對價差/準套利訊號**，非無風險套利。股票期貨現金結算，最後結算價為標的證券**到期日收盤前 60 分鐘成交價之算術平均**，現股那腿無法保證以該均價出場 → 有**殘留基差風險**。一切數字命名為 `estimated_*`、訊號標 `indicative`，**下單前自行覆核**。

## 1. 目標
盤中即時掃描台股**股票期貨/ETF 期貨**與標的**現股**價差：當**保守淨利打贏所有成本與緩衝**時，放空 1 口期貨 + 買進等量現股，持有到結算收斂。即時算出每標的：進場價差、保守淨利、到結算需備妥之**壓力本金**、占用資金年化。只掃訊號、跳警示，**下單手動**（v1 不含自動執行）。

## 2. 已確認決策
| # | 決策 | 選定 |
|---|------|------|
| 1 | 執行範圍 | 只掃訊號（不自動下單） |
| 2 | 資料來源 | XQ DDE/RTD → Python；群益 Capital API 為未來升級 |
| 3 | 前端 | 終端機表格（rich，即時刷新 + 達標響鈴） |
| 4 | 除權息 | **預設排除/醒目標記**：跨現金股利除息日標的不發警示（§4.3） |
| 5 | 掃描範圍 | 可篩選的全掃（依量/保守淨利門檻篩） |
| 6 | 壓力本金 | 兩情境可調 + **聯合壓力**（天天漲停 ∧ 保證金調高）為保守 headline |
| 7 | 契約調整事件 | v1 **只掃非調整型契約**；配股/減資/合併 → 排除 |
| 8 | 借券費 | **N/A**（放空期貨非借券放空） |
| 9 | 有價證券抵繳保證金 | 可選情境、**預設關閉** |
| 10 | v1 嚴謹度 | **務實近似**：成本/本金/年化用保守近似閉式，不建逐日 T+2 帳本 |
| 11 | 保證金建模 | v1 用 `initial_margin_rate × 壓力倍數 + 券商加收`；不另拆維持/結算（全程用原始保證金即保守） |
| 12 | 小型/零股腿 | 盤中零股為**集合競價**；v1 **只顯示、不發警示** |

## 3. 領域背景（已查證）
- 契約乘數非定值：股期標準 2,000 股/小型 100 股；ETF 期標準 10,000 受益權單位/小型 1,000。`mult` per-contract。
- 小型股期對沖須用**盤中零股市場**（集合競價：9:10 首次撮合、其後每 3 分鐘一次），與期貨即時連續成交不同步 → v1 小型只顯示不警示。
- 最後交易日 = 第三個星期三（遇假日依官方行事曆）；最後結算價 = 標的收盤前 60 分鐘算術平均（現金結算）。
- 漲跌幅 ±10%/日；國外成分 ETF 期 ±15%；契約調整者另訂 → `price_limit_rule` per-contract、可逐日。
- 保證金 = 契約價值 × 保證金率（風險價格係數分級、會調整）；處置時可調高 1.5/2/3 倍。
- 期交稅/證交稅/手續費/資金利率/各 buffer **全部可調參數**。

## 4. 計算模型

### 4.1 一組
放空 1 口期貨（`mult` 單位）+ 買進 `mult` 單位現股，delta 對沖。`mult`/執行板別（整股/零股）/稅別（股 0.3%/ETF 0.1%）由 `ContractSpec` 決定。

### 4.2 進場價差（保守報價）
放空期貨用**期貨買價 `F_bid`**、買現股用**現股賣價 `S_ask`**（小型用零股賣價）。
```
entry_spread = F_bid − S_ask              # 訊號基礎，不加 D
quoted_edge_profit = entry_spread × mult  # 帳面毛價差，未扣任何成本/緩衝
```

### 4.3 除權息（方向已修正）
TAIFEX 對現金股利做契約調整：調整生效日**買方權益數 +（股利×乘數）、賣方（空方）−（股利×乘數）**，參考價降 `(S−D)/(1+無償配股率)`，帳戶權益總值不變 → 股利被中性化、期貨不為股利折價、空方拿不到除息跌價利益。原 `+D` 已刪。
**精確語意**：跨現金股利除息時，**現股取得之現金股利與股期空方權益數減項，僅就股利事件本身在稅前互抵**；進場價差、交易成本、資金成本、稅負、結算基差**並不歸零**。又現股股利要課股利所得稅＋二代健保補充保費 → 跨除息是淨成本。
**v1 行為**：持有期內遇現金股利除息日 → **排除/醒目標記、不發警示**；會改乘數/代號之事件 → 排除。

### 4.4 保守淨利（達標與排序依據）
```
transaction_cost =
    spot_commission(S_ask×mult, board)            # 買，= max(notional×c_b, min_fee[board])
  + spot_commission(P_est×mult, board)            # 賣
  + P_est × mult × tax_spot                        # 證交稅（股0.3%/ETF0.1%，依 tax_class；留倉不享當沖減半）
  + fee_fut_per_lot × 2                             # 期貨手續費（開+平/結算）
  + (F_bid + F_settle_est) × mult × tax_fut         # 期交稅（開倉、結算各課；STF 率以現行公告為準）

base_reserved_cash = S_ask×mult + F_bid×mult×initial_margin_rate       # 正常占用資金（非壓力峰值）
funding_cost ≈ base_reserved_cash × funding_rate × days_held / 365     # 務實近似；用正常占用、不與壓力本金重複懲罰；保守不提前計 T+2 入帳
entry_execution_buffer = (期貨tick×n_f + 現股tick×n_s)×mult + manual_delay_slippage   # 可調
exit_basis_buffer      = 可調（結算基差保守折扣，後續用歷史校準）

estimated_net_before_funding = quoted_edge_profit − transaction_cost          # 參考
estimated_net_conservative   = estimated_net_before_funding − funding_cost
                               − entry_execution_buffer − exit_basis_buffer
```
- `P_est`/`F_settle_est`：每個情境用該情境估計價重算稅費，**不固定取 S_ask**。
- **達標與排序一律以 `estimated_net_conservative > threshold` 為準**，不可用 `quoted_edge_profit` 或單點 net 當訊號。
- 證交稅 0.3% 通常最大宗成本；借券費 N/A。

### 4.5 壓力本金（configured_stress_capital，非數學上界）
**觀念**：期間要備妥的**最高現金水位**，非虧損。期貨虧損每日現金補繳；現股未實現獲利賣出前不能補（除非啟用抵繳）。
```
entry_cash = S_ask×mult + spot_buy_fee + fee_fut_per_lot + fut_open_tax
           + F_bid×mult×initial_margin_rate                     # 進場即占用
F_k        = F_bid × Π_{t=1..k}(1 + price_limit_t)              # 逐日漲停（limit 依 price_limit_rule）
margin_k   = F_k × mult × initial_margin_rate × stress_mult + broker_addon
fut_cash(k)= (F_k − F_bid)×mult + margin_k                       # 累積虧損補繳 + (放大的) 原始保證金
stress_capital = (S_ask×mult + entry_fees) + max_{k∈情境} fut_cash(k)
```
- **保守 headline = 聯合情境**：天天漲停到結算（k=N）∧ 保證金被調高（`stress_mult=3`）。
- 另列：情境A（天天漲停、base margin）、情境B（可設 `maxLimitUpDays` 或不利上限 `F_bid×(1+X)`）供比較。
- v1 全程用**原始保證金**估算（不拆維持/結算，較高即保守）；現股 T+2 入帳**不提前計入**（資金占用偏長＝保守）。
- （可選、預設關）有價證券抵繳：可減少所需現金 ≤ min(現股折扣後評價, 0.5×所需結算保證金)，需期貨商確認。
- 明示：天天漲停只是情境，**非真正數學上界**。

### 4.6 年化（務實近似）
```
annualized = estimated_net_conservative / stress_capital × 365 / days_held
days_held = 建倉日 → 最後現金回收日（含期貨結算與現股賣出 T+2）之日曆天數
```
XIRR／逐日現金流帳本 **v1 不做**（務實近似），列為未來增強。終端表格各欄（進場價差、保守淨利、年化、壓力本金、結算倒數、可成交量、flags）皆可排序。

### 4.7 單元測試基準：無公司行為、無 buffer 簡化案例（精確值、用 Decimal）
`S_ask=100, F_bid=100.5, mult=2000, initial_margin_rate=13.5%, N=15交易日, c_b=c_s=0.0004275（且≥min_fee）, tax_spot=0.003, fee_fut=20/口, tax_fut=0.00002, P_est=F_settle_est=100, D=0, stress_mult=1, broker_addon=0`：
```
quoted_edge_profit = (100.5−100)×2000 = 1,000.00
transaction_cost   = 85.50 + 85.50 + 600.00 + 40.00 + 8.02 = 819.02
estimated_net_before_funding = 180.98
1.1^15 = 4.177248169...  →  F_15 = 419.8134410
fut_cash(15) = (419.8134410−100.5)×2000 + 419.8134410×2000×0.135 = 751,976.51
formula_stress_capital(情境A) = 100×2000 + 751,976.51 = 951,976.51
```
**測試斷言**：`estimated_net_before_funding = 180.98`、`formula_stress_capital = 951,976.51`（Decimal/完整浮點，不可截斷 F_15）。此為簡化基準；另須測：跨除息排除、結算基差 buffer、entry buffer、ETF 乘數、小型零股排除警示、聯合壓力(stress_mult=3)、min_fee 生效、qty 單位正規化。

## 5. 架構

### 5.1 模組（純計算與資料源切開）
```
arbscan/
  config.py          # 費率/門檻/情境/篩選/資金利率/稅率/buffer/min_fee/margin 設定 (pydantic+toml)
  models.py          # Quote / ContractSpec / DividendEvent / ContractAdjustment / ArbResult
  feed/
    base.py          # QuoteFeed 介面 ← 關鍵接縫（換群益/加下單只動這層）
    xqdde.py         # XQ DDE/RTD（整股+零股+期貨），輸出前正規化 qty 單位
    mock.py          # 離線假 feed（測試）
  reference/
    contracts.py            # ContractSpec：代碼↔標的、mult、tax_class、執行板別、結算日
    margins.py              # 逐檔逐日 initial_margin_rate、price_limit_rule、處置調高、broker_addon
    contract_adjustments.py # ★TAIFEX 契約調整為 canonical（除息/配股/減資/合併）
    dividends.py            # 現金股利除息行事曆（判斷跨除息）
    loader.py               # SQLite 載入 + 版本/freshness gate
  engine/            # ★純函式、可單測
    spread.py        # entry_spread、quoted_edge_profit
    cost.py          # transaction_cost(含min_fee)、funding_cost、buffers → estimated_net_*
    capital.py       # configured_stress_capital（情境A/B + 聯合壓力 + 可選抵繳）
    rank.py          # 年化、組 ArbResult
    eligibility.py   # 排除：跨除息、調整型契約、stale、量不足、小型零股不警示
  scanner.py         # 編排：universe→quotes→eligibility→engine→篩選/排序→偵測新訊號
  ui/table.py        # rich.Live（資料版本/as-of、indicative、display-only 標示）
  ui/alert.py        # 達標響鈴（僅 estimated_net_conservative>threshold 且可成交）
  main.py            # 接線 + 主迴圈（每 N 秒重算）
data/{reference.sqlite, config.toml}
scripts/{fetch_contracts, fetch_margins, fetch_contract_adjustments, fetch_dividends}
tests/
```
技術：Python 3.11 64-bit、`pywin32`(DDE)、`rich`、`sqlite3`、`pydantic`。

### 5.2 資料模型重點
- `Quote`：`bid, ask, bid_qty, ask_qty, qty_unit, last, source_timestamp, received_timestamp, session, market_board, status`。feed adapter 進 scanner 前把量正規化為 `underlying_units` / `contract_lots`。
- `ContractSpec`：`fut_symbol, underlying, underlying_type(stock/etf), mult, spot_execution_board(整股/零股), execution_mode(continuous/odd_lot_call_auction), tax_class, settlement_date`。
- `ArbResult`：`entry_spread, quoted_edge_profit, estimated_net_before_funding, estimated_net_conservative, stress_capital{A,B,joint}, annualized, flags[跨除息/調整型/量不足/過期/display_only], indicative=True`。
- fee policy：`spot_commission(notional, board)=max(notional×rate, min_fee[board])`、`futures_fee` 固定元。

### 5.3 資料流
XQ → `xqdde` 訂閱（整股+零股+期貨，正規化量）→ 記憶體報價快取 → `scanner` 每 N 秒：取 universe → `eligibility` 過濾（跨除息、調整型、stale、量不足、小型標 display_only）→ 配對 bid/ask → `engine` 算 `estimated_net_conservative`/壓力本金/年化 → 套門檻/排序 → 新達標觸發 `alert` → `table` 刷新（顯示資料版本/as-of）。參考資料啟動載入、盤前刷新、可手動 refresh。

### 5.4 可成交性與雙腿同步
- scanner 設**最大跨腿時間差**（兩腿 `source_timestamp` 差上限）與**最低可成交量**（期貨 bid 量 ≥ 所需口數、現股 ask 量足）。
- 兩腿須同屬可交易 session、非暫停。過期 edge → 一律 `indicative`、不警示。
- **人工雙腿 legging/slippage** 與**結算基差**已分別由 `entry_execution_buffer`、`exit_basis_buffer` 從淨利扣除。
- **小型/零股腿（集合競價）**：v1 `execution_mode=odd_lot_call_auction`，**只顯示不警示**（不視為與期貨即時同步可成交）。

### 5.5 錯誤處理（fail-closed）
- XQ 未開/DDE 斷線：偵測、示警、自動重連，不整支崩。
- 報價缺失/過期：依 `received_timestamp` 標 stale，不硬算、跳過。
- **參考資料 stale 或版本不一致**：相關標的 **fail-closed**，不進排名與警示。
- 缺合約規格/結算日/保證金/契約調整資料：跳過並列警告。
- **每次 reference refresh 重新檢查**已警示/使用者標記持有之標的，若出現持有期內新公司行為事件 → 重新示警/排除。
- 費率/稅率/利率/buffer 設定錯：啟動時驗證 config。

### 5.6 測試
- `engine` 純函式 TDD：§4.7 簡化案例（Decimal 精確值）+ §4.7 列出之進階案例。
- `eligibility` 排除規則測試（跨除息、調整型、stale、量不足、小型 display_only）。
- `cost`：min_fee 生效、各 buffer、各稅別。`capital`：聯合壓力、情境A/B。
- reference 解析與 freshness gate；scanner 用 mock feed；XQ DDE 真接以 spike 手動驗。

## 6. 參考資料 canonical 來源
- **TAIFEX 契約調整事件**：除息/配股/減資/合併 → 排除/標記與乘數變更的權威來源。
- **TAIFEX 合約規格 + 保證金**：mult、tax_class、結算日、逐檔 `initial_margin_rate`、`price_limit_rule`、處置調高、`broker_addon`。
- **現金股利除息行事曆**（TWSE/公開資訊觀測站）：判斷跨除息。
- **設定**：手續費 rate 與 `min_fee[board]`、`fee_fut`、證交稅(0.3%/0.1%)、期交稅率、`funding_rate`、`entry_execution_buffer` 參數、`exit_basis_buffer`、`綜所稅邊際率(預設0)`、補充保費 2.11%。

## 7. 建構順序
1. **Spike（強化驗收）**：`pywin32` DDE 接 XQ，須同時驗 — 標準+小型股期、整股+零股、ETF 期報價；跑完整 universe 記錄 lag/stale 率；模擬斷線重連；核對至少一筆 TAIFEX 契約調整前後 symbol/mult 對映。**未通過不得視 DDE 為定案**。
2. **reference**：contracts/margins/contract_adjustments/dividends + 抓取腳本 + **freshness/版本 gate**。
3. **models + ContractSpec + eligibility**：公司行為 hard-reject、非調整型契約、stale fail-closed、小型 display-only。
4. **engine**（純函式）+ 單元測試：`estimated_net_conservative`（含 buffers）、`stress_capital`（聯合壓力）、年化。
5. **feed**：XQDDEFeed（接 `QuoteFeed`、量正規化）。
6. **scanner + ui + alert**：編排、可成交性/雙腿同步、表格、響鈴（門檻＝保守淨利、小型不警示）、資料版本顯示。
7. 篩選/排序/情境切換/收尾。

> 註：警示/排序/年化/壓力本金所依賴的「保守淨利公式（含 buffer）」在步驟 4 即就位，故開警示（步驟 6）前已具備 Codex 要求的前置條件。

## 8. 待驗證假設與風險
1. **【最高】XQ DDE 能否匯出股期/ETF期/零股報價及 item 格式** — 靠 `QuoteFeed` 介面隔離；不行換群益只動 `feed/`。Spike 驗收見 §7。
2. **STF 期交稅率** — 可能與指數期貨不同/有調降，以現行公告為準（可設）。
3. **保證金率/處置調高/漲跌幅規則** — 由 TAIFEX 載入、逐檔逐日；`broker_addon` 依期貨商。
4. **有價證券抵繳** — 需向期貨商確認；預設關。
5. **`exit_basis_buffer` 校準** — v1 先給保守預設值，未來用歷史到期日「可複製 VWAP vs 實際現股可成交價」校準。
6. **務實近似的偏差** — funding/壓力本金/年化非逐日帳本；設計上一律偏保守。XIRR、逐日 T+2 帳本列未來增強。
7. **股利所得稅模型** — `綜所稅邊際率` 因人而異（預設0、可設）；因 v1 排除跨除息，影響有限。
