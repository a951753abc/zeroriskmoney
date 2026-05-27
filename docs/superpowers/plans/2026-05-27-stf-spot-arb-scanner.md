# 台股股期準套利訊號掃描器 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 盤中即時掃描台股股票期貨/ETF 期貨與標的現股的準套利價差，算出保守淨利、壓力本金、年化，達標跳警示（只掃訊號、手動下單）。

**Architecture:** 純函式計算引擎（Decimal）與資料源（XQ DDE）以 `QuoteFeed` 介面隔離；參考資料（合約/保證金/除權息/契約調整）存 SQLite 並有 freshness gate；scanner 每 N 秒編排「報價→eligibility 過濾→引擎→排序→偵測新訊號→終端表格/響鈴」。一律往「高估成本/本金、低估利潤」偏。

**Tech Stack:** Python 3.11 64-bit、`rich`(UI)、`pydantic`(設定)、`pywin32`(DDE)、`sqlite3`、`pytest`、`Decimal`(金額運算)。

**設計來源：** `docs/superpowers/specs/2026-05-27-stf-spot-arb-scanner-design.md`（已核准）。本計畫術語與公式以該 spec §4 為準。

---

## 檔案結構

| 檔案 | 職責 |
|------|------|
| `pyproject.toml` | 套件/相依/pytest 設定 |
| `arbscan/models.py` | 領域型別：`Quote`/`ContractSpec`/`DividendEvent`/`ContractAdjustment`/`ArbResult` + enums |
| `arbscan/config.py` | `Settings`/`FeePolicy`/門檻/buffer/情境（pydantic + toml） |
| `arbscan/engine/spread.py` | `entry_spread`/`quoted_edge_profit` |
| `arbscan/engine/cost.py` | `spot_commission`/`transaction_cost`/`funding_cost`/`estimated_net_*` |
| `arbscan/engine/capital.py` | `stress_capital`（情境A/B + 聯合壓力） |
| `arbscan/engine/rank.py` | `annualized_return`/組 `ArbResult` |
| `arbscan/engine/eligibility.py` | 排除規則：跨除息/調整型/過期/量不足/零股 display-only |
| `arbscan/reference/loader.py` | SQLite schema + 載入 + freshness/版本 gate |
| `arbscan/feed/base.py` | `QuoteFeed` 介面（Protocol） |
| `arbscan/feed/mock.py` | 離線假 feed |
| `arbscan/feed/xqdde.py` | XQ DDE 實作（依 Task 1 spike 結果；量正規化） |
| `arbscan/scanner.py` | 編排 + 偵測新訊號 |
| `arbscan/ui/table.py` / `ui/alert.py` | rich 終端表格 / 響鈴 |
| `arbscan/main.py` | 接線 + 主迴圈 |
| `scripts/fetch_*.py` | 從 TAIFEX/TWSE 更新參考資料到 SQLite |
| `tests/` | 對應單元測試 |

**TDD 適用性：** Task 2–9、12、14（純邏輯）走嚴格 TDD。Task 1（XQ DDE spike）、10/11（外部資料）、13（DDE 實作）、15/16（IO/UI）以「邏輯部分單測 + 整合以 spike/手動驗收」處理，原因：無法對未知的外部 DDE item 格式與 TAIFEX/TWSE HTML 結構做有意義的單元測試。

---

## Task 0：專案 scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `arbscan/__init__.py`, `arbscan/engine/__init__.py`, `arbscan/feed/__init__.py`, `arbscan/reference/__init__.py`, `arbscan/ui/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: 建立 pyproject.toml**

```toml
[project]
name = "arbscan"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["rich>=13", "pydantic>=2", "pywin32>=306; sys_platform == 'win32'"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 2: 建立空 package 檔**

每個 `__init__.py` 內容留空（建立 package）。

- [ ] **Step 3: 安裝相依並驗證 pytest 可跑**

Run: `python -m pip install -e ".[dev]"` 然後 `python -m pytest -q`
Expected: `no tests ran`（無錯誤，pytest 正常啟動）

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml arbscan tests
git commit -m "chore: 專案 scaffold 與 pytest 設定"
```

---

## Task 1：XQ DDE Spike（排除最大風險，整合驗收非 TDD）

**Files:**
- Create: `scripts/spike_xqdde.py`
- Create: `docs/superpowers/notes/xqdde-spike.md`（findings）

**目的：** 驗證 spec §8 風險#1 — 能否用 `pywin32` DDE client 從 XQ 取得報價。**未通過則改用群益 API（只動 feed 層）。**

- [ ] **Step 1: 寫探測腳本（候選 service/topic/item，依 XQ DDE 說明調整）**

```python
# scripts/spike_xqdde.py
"""XQ DDE 探測：找出 service/topic/item 格式。
參考 XQ 官方 DDE 說明頁設定 service 名稱與 item 字串；以下為候選，依實測修正。"""
import sys, time
try:
    import dde, win32ui
except ImportError:
    sys.exit("需安裝 pywin32：python -m pip install pywin32")

SERVICE = "XQLITE"          # 候選；XQ DDE 說明可能為其他，spike 時逐一試
TOPIC = "Quote"             # 候選
ITEMS = [                   # 四類各一檔（請換成你自選清單裡的代碼）
    ("2330", "成交價"),      # 現股整股
    ("2330", "賣出價"),
    ("CDF",  "買進價"),      # 台積電股期（候選代碼，依 XQ 實際符號修正）
    ("2330", "零股賣出價"),  # 零股
]

def main():
    server = dde.CreateServer(); server.Create("arbscan_spike")
    conv = dde.CreateConversation(server)
    conv.ConnectTo(SERVICE, TOPIC)
    for sym, field in ITEMS:
        item = f"{sym}.{field}"   # 候選 item 格式，依實測修正
        try:
            print(item, "=>", conv.Request(item))
        except Exception as e:
            print(item, "ERROR", e)
        time.sleep(0.3)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 開啟 XQ 全球贏家後執行**

Run: `python scripts/spike_xqdde.py`
Expected：能印出至少一檔現股 bid/ask 與一檔股期 bid/ask 的即時數字。若 `ConnectTo` 失敗，依 XQ「DDE 功能」說明調整 `SERVICE`/`TOPIC`/`item` 格式重試。

- [ ] **Step 3: 記錄 findings 與驗收**

於 `docs/superpowers/notes/xqdde-spike.md` 記錄（驗收條件，全部需回答）：
1. 確定可用的 `SERVICE`/`TOPIC`/`item` 字串格式
2. 標準股期 + 整股現股 + 零股 + ETF 期 各取一檔的實際回傳樣本
3. 全 universe（~250×多欄）訂閱時的更新延遲與 stale 觀察
4. DDE 中斷再連的行為
5. 一筆 TAIFEX 契約調整事件前後，XQ 期貨代碼/乘數如何呈現
6. **結論：XQ DDE 是否足以當 v1 資料源？否則改群益。**

- [ ] **Step 4: Commit**

```bash
git add scripts/spike_xqdde.py docs/superpowers/notes/xqdde-spike.md
git commit -m "chore: XQ DDE spike 腳本與 findings"
```

> **Gate：** Step 3 結論為「足夠」才繼續 Task 13 的 XQDDEFeed 實作；否則先處理群益 feed（介面相同，不影響 Task 2–11、14–16）。

---

## Task 2：領域型別 models.py

**Files:**
- Create: `arbscan/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_models.py
from datetime import date, datetime
from decimal import Decimal
from arbscan.models import ContractSpec, Quote, UnderlyingType, ExecutionMode

def test_contractspec_holds_fields():
    s = ContractSpec(fut_symbol="CDF", underlying="2330",
                     underlying_type=UnderlyingType.STOCK, mult=2000,
                     spot_execution_board="整股", execution_mode=ExecutionMode.CONTINUOUS,
                     tax_class="stock", settlement_date=date(2026, 6, 17))
    assert s.mult == 2000 and s.tax_class == "stock"

def test_quote_is_frozen():
    q = Quote(symbol="2330", bid=Decimal("100"), ask=Decimal("100.5"),
              bid_qty=5000, ask_qty=4000, qty_unit="share", last=Decimal("100.2"),
              source_timestamp=datetime(2026,5,27,9,30), received_timestamp=datetime(2026,5,27,9,30),
              session="regular", market_board="整股", status="normal")
    import dataclasses, pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        q.bid = Decimal("1")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL（`ModuleNotFoundError: arbscan.models`）

- [ ] **Step 3: 實作 models.py**

```python
# arbscan/models.py
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

class UnderlyingType(str, Enum):
    STOCK = "stock"
    ETF = "etf"

class ExecutionMode(str, Enum):
    CONTINUOUS = "continuous"
    ODD_LOT_CALL_AUCTION = "odd_lot_call_auction"

@dataclass(frozen=True)
class ContractSpec:
    fut_symbol: str
    underlying: str
    underlying_type: UnderlyingType
    mult: int                       # 契約乘數（股數/受益權單位）
    spot_execution_board: str       # "整股" / "零股"
    execution_mode: ExecutionMode
    tax_class: str                  # "stock"->0.003, "etf"->0.001
    settlement_date: date

@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: Decimal
    ask: Decimal
    bid_qty: int                    # 已正規化為「標的單位」(share/unit)
    ask_qty: int
    qty_unit: str                   # provenance: "lot"/"share"/"odd_share"/"etf_unit"
    last: Decimal
    source_timestamp: datetime
    received_timestamp: datetime
    session: str
    market_board: str
    status: str                     # "normal"/"halt"/...

@dataclass(frozen=True)
class DividendEvent:
    underlying: str
    ex_date: date
    cash_dividend: Decimal          # 每股現金股利
    has_stock_dividend: bool        # 配股 -> 需排除

@dataclass(frozen=True)
class ContractAdjustment:
    fut_symbol: str
    effective_date: date
    kind: str                       # "除息"/"配股"/"減資"/"合併"
    changes_multiplier: bool

@dataclass(frozen=True)
class ArbResult:
    fut_symbol: str
    underlying: str
    entry_spread: Decimal
    quoted_edge_profit: Decimal
    estimated_net_before_funding: Decimal
    estimated_net_conservative: Decimal
    stress_capital_A: Decimal
    stress_capital_joint: Decimal
    annualized: Decimal
    days_held: int
    flags: tuple[str, ...] = field(default_factory=tuple)
    indicative: bool = True
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/models.py tests/test_models.py
git commit -m "feat: 領域型別 models（Quote/ContractSpec/ArbResult 等）"
```

---

## Task 3：引擎 spread.py

**Files:**
- Create: `arbscan/engine/spread.py`
- Test: `tests/test_spread.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_spread.py
from decimal import Decimal
from arbscan.engine.spread import entry_spread, quoted_edge_profit

def test_entry_spread_uses_conservative_quotes():
    assert entry_spread(Decimal("100.5"), Decimal("100")) == Decimal("0.5")

def test_quoted_edge_profit_times_mult():
    assert quoted_edge_profit(Decimal("100.5"), Decimal("100"), 2000) == Decimal("1000.0")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_spread.py -v`
Expected: FAIL（module 不存在）

- [ ] **Step 3: 實作**

```python
# arbscan/engine/spread.py
from decimal import Decimal

def entry_spread(f_bid: Decimal, s_ask: Decimal) -> Decimal:
    """進場價差/單位 = 期貨買價 − 現股賣價（保守報價，不加股利 D）。"""
    return f_bid - s_ask

def quoted_edge_profit(f_bid: Decimal, s_ask: Decimal, mult: int) -> Decimal:
    """帳面毛價差（未扣任何成本/緩衝）。"""
    return entry_spread(f_bid, s_ask) * mult
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_spread.py -v`  → PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/engine/spread.py tests/test_spread.py
git commit -m "feat: 引擎 entry_spread / quoted_edge_profit"
```

---

## Task 4：費用政策 + transaction_cost

**Files:**
- Create: `arbscan/engine/cost.py`
- Test: `tests/test_cost.py`

- [ ] **Step 1: 寫失敗測試（含 §4.7 成本錨點 819.02 與 min_fee）**

```python
# tests/test_cost.py
from decimal import Decimal
from arbscan.engine.cost import FeePolicy, spot_commission, transaction_cost

FEE = FeePolicy(
    spot_rate=Decimal("0.0004275"),
    spot_min_fee={"整股": Decimal("20"), "零股": Decimal("1")},
    fut_fee_per_lot=Decimal("20"),
    tax_spot={"stock": Decimal("0.003"), "etf": Decimal("0.001")},
    tax_fut=Decimal("0.00002"),
)

def test_spot_commission_applies_min_fee():
    # 小額：notional×rate < 20 → 取 min_fee
    assert spot_commission(Decimal("10000"), "整股", FEE) == Decimal("20")
    # 大額：取 notional×rate
    assert spot_commission(Decimal("200000"), "整股", FEE) == Decimal("85.5")

def test_transaction_cost_matches_spec_4_7():
    cost = transaction_cost(
        s_ask=Decimal("100"), f_bid=Decimal("100.5"),
        p_est=Decimal("100"), f_settle_est=Decimal("100"),
        mult=2000, board="整股", tax_class="stock", fee=FEE)
    assert cost.quantize(Decimal("0.01")) == Decimal("819.02")
```

- [ ] **Step 2: 跑測試確認失敗** → Run: `python -m pytest tests/test_cost.py -v`（FAIL）

- [ ] **Step 3: 實作**

```python
# arbscan/engine/cost.py
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class FeePolicy:
    spot_rate: Decimal
    spot_min_fee: dict[str, Decimal]   # board -> 最低手續費
    fut_fee_per_lot: Decimal
    tax_spot: dict[str, Decimal]       # tax_class -> 證交稅率
    tax_fut: Decimal                   # 期交稅率

def spot_commission(notional: Decimal, board: str, fee: FeePolicy) -> Decimal:
    return max(notional * fee.spot_rate, fee.spot_min_fee[board])

def transaction_cost(s_ask: Decimal, f_bid: Decimal, p_est: Decimal,
                     f_settle_est: Decimal, mult: int, board: str,
                     tax_class: str, fee: FeePolicy) -> Decimal:
    buy = spot_commission(s_ask * mult, board, fee)
    sell = spot_commission(p_est * mult, board, fee)
    securities_tax = p_est * mult * fee.tax_spot[tax_class]
    fut_fee = fee.fut_fee_per_lot * 2
    fut_tax = (f_bid + f_settle_est) * mult * fee.tax_fut
    return buy + sell + securities_tax + fut_fee + fut_tax
```

- [ ] **Step 4: 跑測試確認通過** → PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/engine/cost.py tests/test_cost.py
git commit -m "feat: FeePolicy 與 transaction_cost（含最低手續費）"
```

---

## Task 5：funding_cost 與 estimated_net_*

**Files:**
- Modify: `arbscan/engine/cost.py`
- Test: `tests/test_net.py`

- [ ] **Step 1: 寫失敗測試（net_before_funding=180.98）**

```python
# tests/test_net.py
from decimal import Decimal
from arbscan.engine.cost import (funding_cost, estimated_net_before_funding,
                                  estimated_net_conservative)

def test_net_before_funding_matches_spec():
    assert estimated_net_before_funding(Decimal("1000"), Decimal("819.02")) == Decimal("180.98")

def test_funding_cost_on_base_reserved_cash():
    # 233500 占用、利率2%、30天
    fc = funding_cost(Decimal("233500"), Decimal("0.02"), 30)
    assert fc.quantize(Decimal("0.01")) == Decimal("383.84")

def test_conservative_subtracts_all_buffers():
    n = estimated_net_conservative(Decimal("180.98"), Decimal("50"),
                                   entry_buffer=Decimal("60"), exit_buffer=Decimal("40"))
    assert n == Decimal("30.98")
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作（追加到 cost.py）**

```python
# 追加到 arbscan/engine/cost.py
def funding_cost(base_reserved_cash: Decimal, funding_rate: Decimal, days_held: int) -> Decimal:
    """正常占用資金的資金成本（務實近似，不與壓力本金重複懲罰）。"""
    return base_reserved_cash * funding_rate * Decimal(days_held) / Decimal(365)

def estimated_net_before_funding(gross: Decimal, txn_cost: Decimal) -> Decimal:
    return gross - txn_cost

def estimated_net_conservative(net_before_funding: Decimal, funding: Decimal,
                               entry_buffer: Decimal, exit_buffer: Decimal) -> Decimal:
    """達標與排序依據：扣資金成本、人工執行 buffer、結算基差 buffer 後的保守淨利。"""
    return net_before_funding - funding - entry_buffer - exit_buffer
```

- [ ] **Step 4: 跑測試確認通過** → PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/engine/cost.py tests/test_net.py
git commit -m "feat: funding_cost 與保守淨利 estimated_net_*"
```

---

## Task 6：壓力本金 capital.py

**Files:**
- Create: `arbscan/engine/capital.py`
- Test: `tests/test_capital.py`

- [ ] **Step 1: 寫失敗測試（§4.7 錨點 951976.51 + 聯合壓力 + 情境B）**

```python
# tests/test_capital.py
from decimal import Decimal
from arbscan.engine.capital import fut_cash_at_day, stress_capital

def test_stress_capital_scenario_A_matches_spec_4_7():
    cap = stress_capital(s_ask=Decimal("100"), f_bid=Decimal("100.5"), mult=2000,
                         initial_margin_rate=Decimal("0.135"), n_days=15,
                         price_limit=Decimal("0.1"))
    assert cap.quantize(Decimal("0.01")) == Decimal("951976.51")

def test_joint_stress_raises_margin_makes_capital_larger():
    base = stress_capital(Decimal("100"), Decimal("100.5"), 2000, Decimal("0.135"), 15, Decimal("0.1"))
    joint = stress_capital(Decimal("100"), Decimal("100.5"), 2000, Decimal("0.135"), 15, Decimal("0.1"),
                           stress_mult=Decimal("3"))
    assert joint > base

def test_scenario_B_capped_limit_up_days_smaller():
    full = stress_capital(Decimal("100"), Decimal("100.5"), 2000, Decimal("0.135"), 15, Decimal("0.1"))
    capped = stress_capital(Decimal("100"), Decimal("100.5"), 2000, Decimal("0.135"), 15, Decimal("0.1"),
                            max_limit_up_days=3)
    assert capped < full
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

```python
# arbscan/engine/capital.py
from decimal import Decimal

def fut_cash_at_day(f_bid: Decimal, mult: int, initial_margin_rate: Decimal,
                    k: int, price_limit: Decimal, stress_mult: Decimal = Decimal("1"),
                    broker_addon: Decimal = Decimal("0")) -> Decimal:
    """第 k 日（天天漲停）期貨腿需備現金：累積虧損補繳 + 放大的原始保證金。"""
    f_k = f_bid * (Decimal("1") + price_limit) ** k
    loss = (f_k - f_bid) * mult
    margin = f_k * mult * initial_margin_rate * stress_mult + broker_addon
    return loss + margin

def stress_capital(s_ask: Decimal, f_bid: Decimal, mult: int,
                   initial_margin_rate: Decimal, n_days: int, price_limit: Decimal,
                   stress_mult: Decimal = Decimal("1"), broker_addon: Decimal = Decimal("0"),
                   entry_fees: Decimal = Decimal("0"), max_limit_up_days: int | None = None) -> Decimal:
    """壓力本金 = 現股款 + entry_fees + 情境內逐日期貨需備現金之最大值。
    情境A：天天漲停到結算（max_limit_up_days=None → k 到 n_days）。
    情境B：限制最多連 max_limit_up_days 根漲停。
    聯合壓力：stress_mult=3。"""
    spot_cost = s_ask * mult
    k_max = n_days if max_limit_up_days is None else min(n_days, max_limit_up_days)
    worst = max(
        fut_cash_at_day(f_bid, mult, initial_margin_rate, k, price_limit, stress_mult, broker_addon)
        for k in range(0, k_max + 1)
    )
    return spot_cost + entry_fees + worst
```

- [ ] **Step 4: 跑測試確認通過** → PASS（驗證 951976.51）

- [ ] **Step 5: Commit**

```bash
git add arbscan/engine/capital.py tests/test_capital.py
git commit -m "feat: 壓力本金 stress_capital（情境A/B + 聯合壓力）"
```

---

## Task 7：年化與組裝 rank.py

**Files:**
- Create: `arbscan/engine/rank.py`
- Test: `tests/test_rank.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_rank.py
from decimal import Decimal
from arbscan.engine.rank import annualized_return

def test_annualized_basic():
    # 淨利1000、本金100000、持有30天 → 1000/100000*365/30
    r = annualized_return(Decimal("1000"), Decimal("100000"), 30)
    assert r.quantize(Decimal("0.0001")) == Decimal("0.1217")

def test_annualized_guards_zero():
    assert annualized_return(Decimal("100"), Decimal("0"), 30) == Decimal("0")
    assert annualized_return(Decimal("100"), Decimal("100000"), 0) == Decimal("0")
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

```python
# arbscan/engine/rank.py
from decimal import Decimal

def annualized_return(net_conservative: Decimal, stress_capital: Decimal, days_held: int) -> Decimal:
    """占用資金年化（務實近似）。本金或天數非正 → 0。"""
    if stress_capital <= 0 or days_held <= 0:
        return Decimal("0")
    return net_conservative / stress_capital * Decimal("365") / Decimal(days_held)
```

- [ ] **Step 4: 跑測試確認通過** → PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/engine/rank.py tests/test_rank.py
git commit -m "feat: 年化報酬 annualized_return"
```

---

## Task 8：設定 config.py

**Files:**
- Create: `arbscan/config.py`
- Create: `data/config.example.toml`
- Test: `tests/test_config.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_config.py
from decimal import Decimal
import pytest
from arbscan.config import Settings, load_settings

def test_load_settings_from_toml(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        'funding_rate = "0.02"\n'
        'min_net_threshold = "50"\n'
        'entry_execution_buffer = "60"\n'
        'exit_basis_buffer = "40"\n'
        'max_cross_leg_ms = 500\n'
        'stale_quote_ms = 3000\n', encoding="utf-8")
    s = load_settings(p)
    assert s.funding_rate == Decimal("0.02")
    assert s.max_cross_leg_ms == 500

def test_settings_rejects_negative_rate():
    with pytest.raises(ValueError):
        Settings(funding_rate=Decimal("-0.01"), min_net_threshold=Decimal("0"),
                 entry_execution_buffer=Decimal("0"), exit_basis_buffer=Decimal("0"),
                 max_cross_leg_ms=500, stale_quote_ms=3000)
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

```python
# arbscan/config.py
from decimal import Decimal
from pathlib import Path
import tomllib
from pydantic import BaseModel, field_validator

class Settings(BaseModel):
    funding_rate: Decimal
    min_net_threshold: Decimal          # estimated_net_conservative 門檻
    entry_execution_buffer: Decimal
    exit_basis_buffer: Decimal
    max_cross_leg_ms: int               # 雙腿 timestamp 最大差
    stale_quote_ms: int                 # 報價過期門檻
    refresh_seconds: int = 2

    @field_validator("funding_rate", "min_net_threshold",
                     "entry_execution_buffer", "exit_basis_buffer")
    @classmethod
    def non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

def load_settings(path: Path) -> Settings:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Settings(**data)
```

並建立 `data/config.example.toml`：

```toml
funding_rate = "0.02"
min_net_threshold = "50"
entry_execution_buffer = "60"
exit_basis_buffer = "40"
max_cross_leg_ms = 500
stale_quote_ms = 3000
refresh_seconds = 2
```

- [ ] **Step 4: 跑測試確認通過** → PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/config.py data/config.example.toml tests/test_config.py
git commit -m "feat: 設定 Settings 與 toml 載入"
```

---

## Task 9：排除規則 eligibility.py

**Files:**
- Create: `arbscan/engine/eligibility.py`
- Test: `tests/test_eligibility.py`

- [ ] **Step 1: 寫失敗測試（逐規則）**

```python
# tests/test_eligibility.py
from datetime import date, datetime
from decimal import Decimal
from arbscan.models import (ContractSpec, Quote, DividendEvent, ContractAdjustment,
                            UnderlyingType, ExecutionMode)
from arbscan.engine.eligibility import evaluate_eligibility

SETTLE = date(2026, 6, 17)
SPEC = ContractSpec("CDF", "2330", UnderlyingType.STOCK, 2000, "整股",
                    ExecutionMode.CONTINUOUS, "stock", SETTLE)

def _q(symbol, recv, bidq=5000, askq=5000, status="normal"):
    return Quote(symbol, Decimal("100.5"), Decimal("100"), bidq, askq, "share",
                 Decimal("100.2"), recv, recv, "regular", "整股", status)

NOW = datetime(2026, 5, 27, 9, 30, 0)

def test_cross_ex_dividend_excluded():
    divs = [DividendEvent("2330", date(2026, 6, 10), Decimal("5"), False)]
    ok, flags = evaluate_eligibility(SPEC, _q("CDF", NOW), _q("2330", NOW), divs, [], NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert not ok and "跨除息" in flags

def test_adjusted_contract_excluded():
    adj = [ContractAdjustment("CDF", date(2026, 6, 5), "配股", True)]
    ok, flags = evaluate_eligibility(SPEC, _q("CDF", NOW), _q("2330", NOW), [], adj, NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert not ok and "調整型" in flags

def test_stale_quote_excluded():
    old = datetime(2026, 5, 27, 9, 0, 0)   # 30 分鐘前
    ok, flags = evaluate_eligibility(SPEC, _q("CDF", old), _q("2330", NOW), [], [], NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert not ok and "過期" in flags

def test_low_liquidity_excluded():
    ok, flags = evaluate_eligibility(SPEC, _q("CDF", NOW, bidq=1000), _q("2330", NOW), [], [], NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert not ok and "量不足" in flags

def test_odd_lot_is_display_only():
    spec = ContractSpec("QABC", "2330", UnderlyingType.STOCK, 100, "零股",
                        ExecutionMode.ODD_LOT_CALL_AUCTION, "stock", SETTLE)
    ok, flags = evaluate_eligibility(spec, _q("QABC", NOW), _q("2330", NOW), [], [], NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert not ok and "display_only" in flags

def test_clean_contract_eligible():
    ok, flags = evaluate_eligibility(SPEC, _q("CDF", NOW), _q("2330", NOW), [], [], NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert ok and flags == ()
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

```python
# arbscan/engine/eligibility.py
from datetime import datetime
from arbscan.models import (ContractSpec, Quote, DividendEvent, ContractAdjustment,
                            ExecutionMode)

_BLOCKING = ("跨除息", "調整型", "過期", "量不足", "display_only")

def _stale(q: Quote, now: datetime, stale_ms: int) -> bool:
    return (now - q.received_timestamp).total_seconds() * 1000 > stale_ms

def evaluate_eligibility(spec: ContractSpec, fut: Quote, spot: Quote,
                         dividends: list[DividendEvent], adjustments: list[ContractAdjustment],
                         now: datetime, stale_ms: int, max_cross_leg_ms: int) -> tuple[bool, tuple[str, ...]]:
    flags: list[str] = []
    today = now.date()
    # 跨除息（持有期內遇現金股利除息日，或配股）
    for d in dividends:
        if d.underlying == spec.underlying and today <= d.ex_date <= spec.settlement_date:
            flags.append("跨除息"); break
    # 調整型契約
    for a in adjustments:
        if a.fut_symbol == spec.fut_symbol and today <= a.effective_date <= spec.settlement_date:
            flags.append("調整型"); break
    # 報價過期 / 雙腿時間差
    if _stale(fut, now, stale_ms) or _stale(spot, now, stale_ms):
        flags.append("過期")
    if abs((fut.source_timestamp - spot.source_timestamp).total_seconds()) * 1000 > max_cross_leg_ms:
        flags.append("過期")
    # 可成交量（兩腿皆須 ≥ 1 組 = mult 標的單位）
    if fut.bid_qty < spec.mult or spot.ask_qty < spec.mult or fut.status != "normal" or spot.status != "normal":
        flags.append("量不足")
    # 零股集合競價 → v1 只顯示不警示
    if spec.execution_mode == ExecutionMode.ODD_LOT_CALL_AUCTION:
        flags.append("display_only")
    eligible = not any(f in _BLOCKING for f in flags)
    return eligible, tuple(dict.fromkeys(flags))   # 去重保序
```

- [ ] **Step 4: 跑測試確認通過** → PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/engine/eligibility.py tests/test_eligibility.py
git commit -m "feat: eligibility 排除規則（跨除息/調整型/過期/量不足/零股）"
```

---

## Task 10：參考資料 loader.py（SQLite + freshness gate）

**Files:**
- Create: `arbscan/reference/loader.py`
- Test: `tests/test_reference.py`

- [ ] **Step 1: 寫失敗測試（用暫存 sqlite fixture）**

```python
# tests/test_reference.py
import sqlite3
from datetime import date, datetime, timedelta
from arbscan.reference.loader import init_schema, load_contracts, is_fresh

def _db(tmp_path):
    con = sqlite3.connect(tmp_path / "ref.sqlite")
    init_schema(con)
    return con

def test_load_contracts_roundtrip(tmp_path):
    con = _db(tmp_path)
    con.execute("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?)",
                ("CDF", "2330", "stock", 2000, "整股", "continuous", "stock", "2026-06-17"))
    con.execute("INSERT INTO meta VALUES ('contracts_as_of', ?)", (datetime.now().isoformat(),))
    con.commit()
    specs = load_contracts(con)
    assert len(specs) == 1 and specs[0].mult == 2000 and specs[0].settlement_date == date(2026,6,17)

def test_freshness_gate(tmp_path):
    con = _db(tmp_path)
    stale = (datetime.now() - timedelta(days=2)).isoformat()
    con.execute("INSERT INTO meta VALUES ('contracts_as_of', ?)", (stale,)); con.commit()
    assert is_fresh(con, "contracts_as_of", max_age_hours=24) is False
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

```python
# arbscan/reference/loader.py
import sqlite3
from datetime import date, datetime, timedelta
from arbscan.models import ContractSpec, UnderlyingType, ExecutionMode

SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts(
  fut_symbol TEXT PRIMARY KEY, underlying TEXT, underlying_type TEXT, mult INTEGER,
  spot_execution_board TEXT, execution_mode TEXT, tax_class TEXT, settlement_date TEXT);
CREATE TABLE IF NOT EXISTS margins(
  fut_symbol TEXT PRIMARY KEY, initial_margin_rate TEXT, price_limit TEXT,
  stress_addon TEXT, broker_addon TEXT);
CREATE TABLE IF NOT EXISTS dividends(
  underlying TEXT, ex_date TEXT, cash_dividend TEXT, has_stock_dividend INTEGER);
CREATE TABLE IF NOT EXISTS contract_adjustments(
  fut_symbol TEXT, effective_date TEXT, kind TEXT, changes_multiplier INTEGER);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""

def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA); con.commit()

def load_contracts(con: sqlite3.Connection) -> list[ContractSpec]:
    rows = con.execute("SELECT fut_symbol,underlying,underlying_type,mult,"
                       "spot_execution_board,execution_mode,tax_class,settlement_date "
                       "FROM contracts").fetchall()
    return [ContractSpec(r[0], r[1], UnderlyingType(r[2]), int(r[3]), r[4],
                         ExecutionMode(r[5]), r[6], date.fromisoformat(r[7])) for r in rows]

def is_fresh(con: sqlite3.Connection, key: str, max_age_hours: int) -> bool:
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    if not row:
        return False
    as_of = datetime.fromisoformat(row[0])
    return datetime.now() - as_of <= timedelta(hours=max_age_hours)
```

> 註：`load_margins`/`load_dividends`/`load_adjustments` 以相同模式實作（回傳 dict / `DividendEvent` / `ContractAdjustment` 串列）；測試各加一條 roundtrip（與 `load_contracts` 同結構，此處不重複貼）。實作時請一併補上並各寫一個 roundtrip 測試。

- [ ] **Step 4: 跑測試確認通過** → PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/reference/loader.py tests/test_reference.py
git commit -m "feat: 參考資料 SQLite schema/載入與 freshness gate"
```

---

## Task 11：資料抓取腳本（整合，非 TDD）

**Files:**
- Create: `scripts/fetch_contracts.py`, `scripts/fetch_margins.py`, `scripts/fetch_dividends.py`, `scripts/fetch_contract_adjustments.py`

> **性質：** 從 TAIFEX/TWSE 抓資料寫入 `data/reference.sqlite`。實際 HTML/CSV 欄位需上站核對，故以「可執行骨架 + 寫入 schema + 更新 meta as_of」為驗收，不做單元測試（外部格式不可控）。

- [ ] **Step 1: 實作骨架（以 fetch_contracts 為例，其餘同模式）**

```python
# scripts/fetch_contracts.py
"""從 TAIFEX 股票期貨契約規格頁抓取，寫入 data/reference.sqlite。
資料來源：TAIFEX 商品-個股期貨類-股票期貨/ETF期貨。實際欄位請對照頁面調整解析。"""
import sqlite3
from datetime import datetime
from pathlib import Path
from arbscan.reference.loader import init_schema

DB = Path("data/reference.sqlite")
TAIFEX_URL = "https://www.taifex.com.tw/cht/2/sTF"   # 起點；實際清單頁/下載連結依站上調整

def fetch_rows() -> list[tuple]:
    # TODO(實作時)：依 TAIFEX 頁面實際結構解析出
    # (fut_symbol, underlying, underlying_type, mult, board, exec_mode, tax_class, settlement_date)
    # 標準股期 mult=2000 board=整股 exec=continuous；小型 mult=100 board=零股 exec=odd_lot_call_auction；
    # ETF 期 mult=10000/1000 tax_class=etf。
    raise NotImplementedError("依 spike/站上格式實作解析")

def main():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB); init_schema(con)
    rows = fetch_rows()
    con.execute("DELETE FROM contracts")
    con.executemany("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?)", rows)
    con.execute("INSERT OR REPLACE INTO meta VALUES ('contracts_as_of', ?)",
                (datetime.now().isoformat(),))
    con.commit(); print(f"wrote {len(rows)} contracts")

if __name__ == "__main__":
    main()
```

`fetch_margins`（initial_margin_rate/price_limit/stress_addon/broker_addon、key `margins_as_of`）、`fetch_dividends`（TWSE 除權息表、key `dividends_as_of`）、`fetch_contract_adjustments`（TAIFEX 契約調整一覽、key `adjustments_as_of`）以相同模式建立。

- [ ] **Step 2: 驗收（手動）**

實作解析後 Run: `python scripts/fetch_contracts.py`，確認 `data/reference.sqlite` 的 `contracts` 表有資料、`meta.contracts_as_of` 已更新。

- [ ] **Step 3: Commit**

```bash
git add scripts/fetch_contracts.py scripts/fetch_margins.py scripts/fetch_dividends.py scripts/fetch_contract_adjustments.py
git commit -m "feat: 參考資料抓取腳本（TAIFEX/TWSE → SQLite）"
```

---

## Task 12：Feed 介面 + Mock

**Files:**
- Create: `arbscan/feed/base.py`, `arbscan/feed/mock.py`
- Test: `tests/test_feed_mock.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_feed_mock.py
from decimal import Decimal
from datetime import datetime
from arbscan.feed.mock import MockFeed
from arbscan.models import Quote

def test_mock_feed_returns_seeded_quote():
    now = datetime(2026,5,27,9,30)
    q = Quote("2330", Decimal("100.5"), Decimal("100"), 5000, 5000, "share",
              Decimal("100.2"), now, now, "regular", "整股", "normal")
    feed = MockFeed({"2330": q})
    feed.subscribe(["2330"])
    assert feed.get_quote("2330").bid == Decimal("100.5")
    assert feed.get_quote("9999") is None
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

```python
# arbscan/feed/base.py
from typing import Protocol, Optional
from arbscan.models import Quote

class QuoteFeed(Protocol):
    def subscribe(self, symbols: list[str]) -> None: ...
    def get_quote(self, symbol: str) -> Optional[Quote]: ...
    def is_connected(self) -> bool: ...
```

```python
# arbscan/feed/mock.py
from typing import Optional
from arbscan.models import Quote

class MockFeed:
    """離線假 feed：用預先植入的報價，供 scanner/engine 測試。"""
    def __init__(self, quotes: dict[str, Quote]):
        self._quotes = dict(quotes)
        self._subscribed: set[str] = set()
    def subscribe(self, symbols: list[str]) -> None:
        self._subscribed.update(symbols)
    def get_quote(self, symbol: str) -> Optional[Quote]:
        return self._quotes.get(symbol)
    def is_connected(self) -> bool:
        return True
    def set_quote(self, symbol: str, q: Quote) -> None:
        self._quotes[symbol] = q
```

- [ ] **Step 4: 跑測試確認通過** → PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/feed/base.py arbscan/feed/mock.py tests/test_feed_mock.py
git commit -m "feat: QuoteFeed 介面與 MockFeed"
```

---

## Task 13：XQDDEFeed（依 Task 1 spike 實作；邏輯單測 + 整合手動驗）

**Files:**
- Create: `arbscan/feed/xqdde.py`
- Test: `tests/test_xqdde_normalize.py`（只測量正規化純函式）

> **性質：** DDE 連線/item 取值依賴 Task 1 spike 的實測格式，無法單元測試外部系統；但「量正規化」是純邏輯，可單測。

- [ ] **Step 1: 寫失敗測試（量正規化：期貨口數×mult、零股股數）**

```python
# tests/test_xqdde_normalize.py
from arbscan.feed.xqdde import normalize_qty

def test_future_lots_to_underlying_units():
    assert normalize_qty(3, "lot", mult=2000) == 6000

def test_share_passthrough():
    assert normalize_qty(4000, "share", mult=2000) == 4000
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作（normalize 純函式 + DDE 類別骨架，連線細節填 spike 結果）**

```python
# arbscan/feed/xqdde.py
from typing import Optional
from arbscan.models import Quote

def normalize_qty(qty: int, qty_unit: str, mult: int) -> int:
    """把報價量正規化為『標的單位』。期貨口數 → ×mult；其餘原樣。"""
    if qty_unit == "lot":
        return qty * mult
    return qty

class XQDDEFeed:
    """XQ DDE 實作。SERVICE/TOPIC/item 格式與欄位對映依 Task 1 spike findings 填入。"""
    def __init__(self, service: str, topic: str):
        self._service, self._topic = service, topic
        self._conv = None
    def connect(self) -> None:
        import dde  # 延後匯入，非 Windows 環境測試不需要
        server = dde.CreateServer(); server.Create("arbscan")
        self._conv = dde.CreateConversation(server)
        self._conv.ConnectTo(self._service, self._topic)
    def subscribe(self, symbols: list[str]) -> None:
        ...  # XQ DDE 為 Request/Advise；依 spike 決定 advise loop 或輪詢
    def get_quote(self, symbol: str) -> Optional[Quote]:
        ...  # 依 spike 的 item 格式組 Quote，數量經 normalize_qty
        raise NotImplementedError("依 Task 1 spike findings 實作 item 解析")
    def is_connected(self) -> bool:
        return self._conv is not None
```

- [ ] **Step 4: 跑測試確認通過** → `python -m pytest tests/test_xqdde_normalize.py -v` PASS

- [ ] **Step 5: 整合手動驗（XQ 開啟下）**：填入 spike 的 SERVICE/TOPIC/item 後，寫一次性 `__main__` 驗 `get_quote("2330")` 回傳合理 bid/ask。

- [ ] **Step 6: Commit**

```bash
git add arbscan/feed/xqdde.py tests/test_xqdde_normalize.py
git commit -m "feat: XQDDEFeed 骨架與量正規化（連線細節依 spike）"
```

---

## Task 14：Scanner 編排

**Files:**
- Create: `arbscan/scanner.py`
- Test: `tests/test_scanner.py`

- [ ] **Step 1: 寫失敗測試（用 MockFeed，端到端產生並排序 ArbResult、偵測新訊號）**

```python
# tests/test_scanner.py
from decimal import Decimal
from datetime import date, datetime
from arbscan.models import ContractSpec, Quote, UnderlyingType, ExecutionMode
from arbscan.engine.cost import FeePolicy
from arbscan.feed.mock import MockFeed
from arbscan.scanner import Scanner

NOW = datetime(2026,5,27,9,30)
FEE = FeePolicy(Decimal("0.0004275"), {"整股": Decimal("20"), "零股": Decimal("1")},
                Decimal("20"), {"stock": Decimal("0.003"), "etf": Decimal("0.001")}, Decimal("0.00002"))
SPEC = ContractSpec("CDF","2330",UnderlyingType.STOCK,2000,"整股",
                    ExecutionMode.CONTINUOUS,"stock",date(2026,6,17))

def _q(sym, bid, ask):
    return Quote(sym, Decimal(bid), Decimal(ask), 9000, 9000, "share",
                 Decimal(ask), NOW, NOW, "regular", "整股", "normal")

def _scanner(threshold):
    return Scanner(specs=[SPEC], feed=MockFeed({}), fee=FEE,
                   funding_rate=Decimal("0.02"), initial_margin_rate=Decimal("0.135"),
                   price_limit=Decimal("0.1"), entry_buffer=Decimal("0"), exit_buffer=Decimal("0"),
                   min_net_threshold=Decimal(threshold), stale_ms=3000, max_cross_leg_ms=500)

def test_scanner_produces_result_for_clean_spread():
    sc = _scanner("0")
    sc.feed.set_quote("CDF", _q("CDF","100.5","100.5"))
    sc.feed.set_quote("2330", _q("2330","100","100"))
    results = sc.scan(NOW)
    assert len(results) == 1 and results[0].fut_symbol == "CDF"
    assert results[0].estimated_net_before_funding.quantize(Decimal("0.01")) == Decimal("180.98")

def test_scanner_flags_new_signal_over_threshold():
    sc = _scanner("50")
    sc.feed.set_quote("CDF", _q("CDF","101","101")); sc.feed.set_quote("2330", _q("2330","100","100"))
    new = sc.detect_new_signals(sc.scan(NOW))
    assert "CDF" in {r.fut_symbol for r in new}
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

```python
# arbscan/scanner.py
from decimal import Decimal
from datetime import datetime
from arbscan.models import ContractSpec, ArbResult
from arbscan.feed.base import QuoteFeed
from arbscan.engine.cost import (FeePolicy, transaction_cost, funding_cost,
                                  estimated_net_before_funding, estimated_net_conservative)
from arbscan.engine.spread import entry_spread, quoted_edge_profit
from arbscan.engine.capital import stress_capital
from arbscan.engine.rank import annualized_return
from arbscan.engine.eligibility import evaluate_eligibility

_BLOCKING = ("跨除息", "調整型", "過期", "量不足", "display_only")

class Scanner:
    def __init__(self, specs, feed: QuoteFeed, fee: FeePolicy, funding_rate: Decimal,
                 initial_margin_rate: Decimal, price_limit: Decimal, entry_buffer: Decimal,
                 exit_buffer: Decimal, min_net_threshold: Decimal, stale_ms: int,
                 max_cross_leg_ms: int, dividends=None, adjustments=None):
        self.specs = list(specs); self.feed = feed; self.fee = fee
        self.funding_rate = funding_rate; self.initial_margin_rate = initial_margin_rate
        self.price_limit = price_limit; self.entry_buffer = entry_buffer
        self.exit_buffer = exit_buffer; self.min_net_threshold = min_net_threshold
        self.stale_ms = stale_ms; self.max_cross_leg_ms = max_cross_leg_ms
        self.dividends = dividends or []; self.adjustments = adjustments or []
        self._alerted: set[str] = set()

    def _days_held(self, spec: ContractSpec, now: datetime) -> int:
        return max((spec.settlement_date - now.date()).days + 2, 1)   # +2 ≈ 現股賣出 T+2 回收

    def _trading_days(self, spec: ContractSpec, now: datetime) -> int:
        # 務實近似：以日曆天估交易日（×5/7），保守取至少 1
        return max(int((spec.settlement_date - now.date()).days * 5 / 7), 1)

    def scan(self, now: datetime) -> list[ArbResult]:
        out: list[ArbResult] = []
        for spec in self.specs:
            fut = self.feed.get_quote(spec.fut_symbol)
            spot = self.feed.get_quote(spec.underlying)
            if fut is None or spot is None:
                continue
            eligible, flags = evaluate_eligibility(spec, fut, spot, self.dividends,
                                                   self.adjustments, now, self.stale_ms,
                                                   self.max_cross_leg_ms)
            spread = entry_spread(fut.bid, spot.ask)
            gross = quoted_edge_profit(fut.bid, spot.ask, spec.mult)
            txn = transaction_cost(spot.ask, fut.bid, spot.ask, spot.ask, spec.mult,
                                   spec.spot_execution_board, spec.tax_class, self.fee)
            nbf = estimated_net_before_funding(gross, txn)
            n_days = self._trading_days(spec, now)
            days_held = self._days_held(spec, now)
            cap_A = stress_capital(spot.ask, fut.bid, spec.mult, self.initial_margin_rate,
                                   n_days, self.price_limit)
            cap_joint = stress_capital(spot.ask, fut.bid, spec.mult, self.initial_margin_rate,
                                       n_days, self.price_limit, stress_mult=Decimal("3"))
            base_reserved = spot.ask * spec.mult + fut.bid * spec.mult * self.initial_margin_rate
            fund = funding_cost(base_reserved, self.funding_rate, days_held)
            net = estimated_net_conservative(nbf, fund, self.entry_buffer, self.exit_buffer)
            ann = annualized_return(net, cap_joint, days_held)
            out.append(ArbResult(spec.fut_symbol, spec.underlying, spread, gross, nbf, net,
                                 cap_A, cap_joint, ann, days_held, flags))
        # 可成交且達標者優先、依年化排序；display-only/不合格沉底
        out.sort(key=lambda r: (any(f in _BLOCKING for f in r.flags), -r.annualized))
        return out

    def detect_new_signals(self, results: list[ArbResult]) -> list[ArbResult]:
        """合格、保守淨利達標、且本輪新出現者。"""
        new = []
        live = set()
        for r in results:
            qualified = (not any(f in _BLOCKING for f in r.flags)
                         and r.estimated_net_conservative > self.min_net_threshold)
            if qualified:
                live.add(r.fut_symbol)
                if r.fut_symbol not in self._alerted:
                    new.append(r)
        self._alerted = live
        return new
```

- [ ] **Step 4: 跑測試確認通過** → PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/scanner.py tests/test_scanner.py
git commit -m "feat: Scanner 編排（eligibility→引擎→排序→偵測新訊號）"
```

---

## Task 15：UI 表格與響鈴

**Files:**
- Create: `arbscan/ui/table.py`, `arbscan/ui/alert.py`
- Test: `tests/test_table.py`

- [ ] **Step 1: 寫失敗測試（render 出含標的的表，row_count==1）**

```python
# tests/test_table.py
from decimal import Decimal
from arbscan.models import ArbResult
from arbscan.ui.table import build_table

def test_build_table_one_row():
    r = ArbResult("CDF","2330",Decimal("0.5"),Decimal("1000"),Decimal("180.98"),
                  Decimal("80"),Decimal("951976.51"),Decimal("1100000"),Decimal("0.05"),21,())
    table = build_table([r], as_of="2026-05-27 09:30", data_version="ref@09:00")
    assert table.row_count == 1
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

```python
# arbscan/ui/table.py
from rich.table import Table
from arbscan.models import ArbResult

_BLOCKING = ("跨除息","調整型","過期","量不足","display_only")

def build_table(results: list[ArbResult], as_of: str, data_version: str) -> Table:
    t = Table(title=f"準套利訊號 (indicative，下單前自行覆核)  報價:{as_of}  參考:{data_version}")
    for col in ("期貨","標的","價差","保守淨利","年化%","壓力本金(聯合)","結算倒數","旗標"):
        t.add_column(col)
    for r in results:
        blocked = any(f in _BLOCKING for f in r.flags)
        style = "dim" if blocked else ("green" if r.estimated_net_conservative > 0 else "")
        t.add_row(r.fut_symbol, r.underlying, f"{r.entry_spread:.2f}",
                  f"{r.estimated_net_conservative:,.0f}", f"{r.annualized*100:.2f}",
                  f"{r.stress_capital_joint:,.0f}", str(r.days_held),
                  ",".join(r.flags), style=style)
    return t
```

```python
# arbscan/ui/alert.py
def beep(times: int = 1) -> None:
    """達標響鈴（Windows）。非 Windows 環境改印 BEL。"""
    try:
        import winsound
        for _ in range(times):
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        print("\a", end="", flush=True)
```

- [ ] **Step 4: 跑測試確認通過** → PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/ui/table.py arbscan/ui/alert.py tests/test_table.py
git commit -m "feat: 終端表格與達標響鈴"
```

---

## Task 16：main.py 接線與主迴圈

**Files:**
- Create: `arbscan/main.py`
- Test: `tests/test_main_smoke.py`（用 MockFeed 跑一輪）

- [ ] **Step 1: 寫失敗測試（一輪 run_once 不丟例外、回傳結果數）**

```python
# tests/test_main_smoke.py
from decimal import Decimal
from datetime import date, datetime
from arbscan.models import ContractSpec, Quote, UnderlyingType, ExecutionMode
from arbscan.engine.cost import FeePolicy
from arbscan.feed.mock import MockFeed
from arbscan.scanner import Scanner
from arbscan.main import run_once

def test_run_once_smoke():
    now = datetime(2026,5,27,9,30)
    spec = ContractSpec("CDF","2330",UnderlyingType.STOCK,2000,"整股",
                        ExecutionMode.CONTINUOUS,"stock",date(2026,6,17))
    fee = FeePolicy(Decimal("0.0004275"), {"整股": Decimal("20")}, Decimal("20"),
                    {"stock": Decimal("0.003")}, Decimal("0.00002"))
    feed = MockFeed({})
    q = lambda s,b,a: Quote(s,Decimal(b),Decimal(a),9000,9000,"share",Decimal(a),now,now,"regular","整股","normal")
    feed.set_quote("CDF", q("CDF","101","101")); feed.set_quote("2330", q("2330","100","100"))
    sc = Scanner([spec], feed, fee, Decimal("0.02"), Decimal("0.135"), Decimal("0.1"),
                 Decimal("0"), Decimal("0"), Decimal("50"), 3000, 500)
    n = run_once(sc, now, as_of="09:30", data_version="ref@09:00", render=False)
    assert n == 1
```

- [ ] **Step 2: 跑測試確認失敗** → FAIL

- [ ] **Step 3: 實作**

```python
# arbscan/main.py
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
        Console().print(build_table(results, as_of, data_version))
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
            live.update(build_table(results, now.strftime("%H:%M:%S"), data_version), refresh=True)
            time.sleep(refresh_seconds)

# 真正進入點（接 XQDDEFeed + reference 載入）於 Task 17 補；測試走 run_once。
```

- [ ] **Step 4: 跑測試確認通過** → PASS

- [ ] **Step 5: Commit**

```bash
git add arbscan/main.py tests/test_main_smoke.py
git commit -m "feat: main run_once/run_loop 接線"
```

---

## Task 17：收尾（全測試、README、設定串接）

**Files:**
- Create: `README.md`
- Modify: `arbscan/main.py`（從 `data/config.toml` + `data/reference.sqlite` 組裝 Scanner 與 XQDDEFeed 的真正進入點）

- [ ] **Step 1: 串接真正進入點**

在 `arbscan/main.py` 加 `def main():`：`load_settings("data/config.toml")` → 連 `data/reference.sqlite`（`is_fresh` 檢查，stale 則警告/相關標的 fail-closed）→ `load_contracts/margins/dividends/adjustments` → 建 `XQDDEFeed`（用 spike 的 service/topic）→ `feed.connect()/subscribe(...)` → 建 `Scanner` → `run_loop(...)`。並加 `if __name__ == "__main__": main()`。

- [ ] **Step 2: 跑全部測試**

Run: `python -m pytest -q`
Expected: 全綠（Task 2–16 之單元測試）。

- [ ] **Step 3: 寫 README**

`README.md` 含：用途、需先開 XQ、`pip install -e ".[dev]"`、`python scripts/fetch_*.py` 更新參考資料、`copy data\config.example.toml data\config.toml` 後填費率、`python -m arbscan.main` 啟動；並重申「indicative、非無風險、下單前自行覆核」。

- [ ] **Step 4: Commit**

```bash
git add README.md arbscan/main.py
git commit -m "docs: README 與 main 進入點串接"
```

---

## 自我檢查（已執行）

- **Spec 覆蓋**：§4.2→Task3；§4.4 成本/buffer/保守淨利→Task4,5；§4.5 壓力本金/聯合→Task6；§4.6 年化→Task7；§4.3 除息排除+§5.5 stale/調整型→Task9；除權息/契約調整/保證金/freshness→Task10,11；§5.4 可成交性/雙腿同步→Task9,14；§5.2 資料模型→Task2；feed 介面/XQ DDE→Task1,12,13；scanner/ui/alert→Task14,15,16；§7 順序→Task 編號。**無遺漏**。
- **佔位掃描**：Task11（抓取解析）、Task13（DDE 連線）有 `NotImplementedError/TODO`——**屬外部整合，已標明性質與驗收**，非邏輯佔位；其餘步驟皆含完整可跑程式碼。
- **型別一致**：`ContractSpec`/`Quote`/`FeePolicy`/`ArbResult` 欄位、`stress_capital`/`evaluate_eligibility`/`estimated_net_*`/`annualized_return` 簽名跨 Task 一致；`_BLOCKING` 在 eligibility/scanner/table 一致；錨點 `180.98`、`951976.51` 與 spec §4.7 一致。
```
