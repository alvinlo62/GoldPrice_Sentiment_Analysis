# 黃金市場情緒分析系統

> Gold Price Sentiment Analysis System

自動化黃金市場新聞情緒分析工具，透過 Google Gemini LLM 評估新聞對黃金價格的潛在影響，結果存入 PostgreSQL 並視覺化呈現。

---

## 目錄

- [專案簡介](#專案簡介)
- [系統架構](#系統架構)
- [檔案結構](#檔案結構)
- [技術棧](#技術棧)
- [資料庫設計](#資料庫設計)
- [安裝與設定](#安裝與設定)
- [使用方式](#使用方式)
- [輸出格式](#輸出格式)
- [版本演進](#版本演進)

---

## 專案簡介

黃金作為重要的避險資產，其價格受到全球經濟、地緣政治、貨幣政策等多重因素影響。本專案提供：

1. **自動化新聞收集**：從 Yahoo Finance 抓取黃金期貨 (GC=F) 相關新聞
2. **AI 情緒分析**：使用 Google Gemini LLM 評估新聞對金價的影響（黃金市場視角）
3. **數據持久化**：結果存入 PostgreSQL，同時輸出 CSV，支援長期追蹤
4. **視覺化呈現**：繪製情緒指數 + 新聞數量雙軸圖表
5. **排程自動化**：設計供 Windows Task Scheduler / Linux cron 每日自動執行

### 情緒分數說明

LLM 分析時採用黃金市場視角，個股漲跌不納入考量：

| 分數範圍 | 意義 | 示例情境 |
|----------|------|----------|
| +0.5 ~ +1.0 | 極度利多 | 地緣衝突升溫、美元大跌、風險規避上升 |
| +0.1 ~ +0.5 | 偏多 | 通膨數據高於預期、央行擴大黃金儲備 |
| -0.1 ~ +0.1 | 中性 | 例行經濟數據、無明顯金價影響 |
| -0.5 ~ -0.1 | 偏空 | 聯準會釋放鷹派訊號、美元走強 |
| -1.0 ~ -0.5 | 極度利空 | 風險偏好大幅回升、加速升息預期 |

---

## 系統架構

```
資料來源層
─────────────────────────────────────────────────────
  Yahoo Finance API (yfinance)
  - 黃金期貨新聞列表 (GC=F)
  - 即時金價報價

  Finnhub API (僅 historical 模式)
  - 歷史新聞補充（最長 ~7 天）
─────────────────────────────────────────────────────
                         │
                         ▼
資料處理層
─────────────────────────────────────────────────────
  新聞內文爬取 (requests + BeautifulSoup)
  - 多重 CSS Selector 容錯
    (.caas-body → .article-body → .body-copy → article)
  - 全文不足 100 字時回退：標題 + 摘要
─────────────────────────────────────────────────────
                         │
                         ▼
AI 分析層
─────────────────────────────────────────────────────
  Google Gemini API (gemini-3-flash-preview)
  - 輸入：新聞標題 + 摘要 + 全文
  - 輸出：情緒分數 (-1.0 ~ +1.0) + 分析原因 (20字內)
  - Prompt 強調黃金市場邏輯（通膨/地緣政治利多）
─────────────────────────────────────────────────────
                         │
                         ▼
儲存層
─────────────────────────────────────────────────────
  PostgreSQL                │  CSV 檔案
  - gold_news 表            │  - 每日分析報告
  - daily_sentiment 表      │  - 可直接用 Excel 開啟
─────────────────────────────────────────────────────
                         │
                         ▼
視覺化層
─────────────────────────────────────────────────────
  Matplotlib
  - 情緒分數折線（雙 Y 軸）
  - 利多 / 利空區域填充
  - 新聞數量柱狀圖
─────────────────────────────────────────────────────
```

---

## 檔案結構

```
GoldPrice_Sentiment_Analysis/
│
├── src/                             # 核心模組（目前使用）
│   ├── goldSentimentAnalyzerV3.py   # 主程式：Yahoo Finance + Gemini + PostgreSQL
│   ├── db_manager.py                # PostgreSQL CRUD 管理層
│   ├── daily_collector.py           # 排程執行入口（每日自動化）
│   ├── plot_from_db.py              # 從資料庫繪製情緒圖表
│   └── historical_sentiment_finnhub.py  # 歷史資料補充（Finnhub API）
│
├── data/                            # 資料輸出目錄
│   ├── Gold_Market_LLM_Analysis_YYYY-MM-DD.csv  # 每日分析結果
│   ├── historical_news_detailed.csv             # Finnhub 歷史新聞
│   └── historical_sentiment.csv                 # 每日彙總（Finnhub）
│
├── prev_version/                    # 舊版本（保留參考）
│   ├── goldSentimentAnalyzer.py     # V1：Selenium + FinBERT + Investing.com
│   ├── goldSentimentAnalyzerV2.py   # V2：requests + FinBERT + Yahoo Finance
│   ├── goldNews_crawler.py          # 純爬蟲，無分析功能
│   └── goldPrice_catcher.ipynb      # Jupyter 實驗
│
├── .env                             # API Keys 與 DB 連線設定（不納入 git）
├── .gitignore
└── README.md
```

---

## 技術棧

### 程式語言
- Python 3.10+

### 資料抓取
| 套件 | 用途 |
|------|------|
| `yfinance` | Yahoo Finance 新聞列表與金價報價 |
| `requests` | HTTP 爬取新聞全文 |
| `beautifulsoup4` | HTML 解析 |
| `finnhub-python` | Finnhub API（歷史模式） |

### AI / LLM
| 套件 | 用途 |
|------|------|
| `google-generativeai` | Gemini API 客戶端（模型：gemini-3-flash-preview） |

### 資料庫
| 技術 | 用途 |
|------|------|
| PostgreSQL | 關聯式資料庫 |
| `psycopg2-binary` | Python PostgreSQL 驅動 |

### 資料處理與視覺化
| 套件 | 用途 |
|------|------|
| `pandas` | 資料整理與 CSV 輸出 |
| `matplotlib` | 圖表繪製 |
| `python-dotenv` | 環境變數管理 |

---

## 資料庫設計

### 資料庫名稱：`gold_sentiment`

### Table: `gold_news`（新聞詳細資料）

| 欄位 | 型別 | 說明 |
|------|------|------|
| id | SERIAL PRIMARY KEY | 自動遞增主鍵 |
| date | DATE NOT NULL | 收集日期（YYYY-MM-DD） |
| datetime | TIMESTAMP | 新聞發布時間 |
| title | TEXT NOT NULL | 新聞標題 |
| summary | TEXT | Yahoo Finance 摘要 |
| link | TEXT UNIQUE | 原文網址（去重依據） |
| source | TEXT | 來源（固定為 "Yahoo Finance"） |
| full_content | TEXT | 爬取的全文內容 |
| final_text_for_ai | TEXT | 實際送給 LLM 的文字 |
| llm_score | REAL | LLM 情緒分數（-1.0 ~ +1.0） |
| llm_reason | TEXT | LLM 分析原因（20字內） |
| created_at | TIMESTAMP | 記錄建立時間 |

索引：`idx_gold_news_date`（date）、`idx_gold_news_link`（link）

去重機制：`ON CONFLICT (link) DO NOTHING`，同一則新聞不會重複插入。

### Table: `daily_sentiment`（每日彙總）

| 欄位 | 型別 | 說明 |
|------|------|------|
| date | DATE PRIMARY KEY | 日期 |
| avg_score | REAL | 當日平均情緒分數（四捨五入至小數第 2 位） |
| news_count | INTEGER | 當日分析新聞則數 |
| updated_at | TIMESTAMP | 最後更新時間 |

---

## 安裝與設定

### 1. 複製專案

```bash
git clone <repository-url>
cd GoldPrice_Sentiment_Analysis
```

### 2. 建立虛擬環境

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. 安裝相依套件

```bash
pip install yfinance pandas requests beautifulsoup4
pip install google-generativeai python-dotenv
pip install psycopg2-binary matplotlib
pip install finnhub-python  # 僅使用歷史補充功能時需要
```

### 4. 建立 PostgreSQL 資料庫

```sql
CREATE DATABASE gold_sentiment;
```

### 5. 設定環境變數

建立 `.env` 檔案（參考以下格式）：

```env
# Google Gemini API（必要）
GEMINI_API_KEY=your_gemini_api_key

# Finnhub API（僅 historical_sentiment_finnhub.py 需要）
FINNHUB_API_KEY=your_finnhub_api_key

# PostgreSQL 連線
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=gold_sentiment
PG_USER=postgres
PG_PASSWORD=your_password
```

---

## 使用方式

### 一次性分析（手動執行）

```bash
python src/goldSentimentAnalyzerV3.py
```

輸出：
- 終端機顯示逐則分析進度
- `data/Gold_Market_LLM_Analysis_YYYY-MM-DD.csv`
- PostgreSQL：自動寫入 `gold_news` 與 `daily_sentiment` 資料表

### 每日收集（手動或排程）

```bash
python src/daily_collector.py
```

分析完成後自動顯示當日情緒摘要（利多 / 中性 / 利空）。

### 設定 Windows 每日排程

```batch
schtasks /create /tn "GoldSentimentDaily" ^
  /tr "python C:\path\to\src\daily_collector.py" ^
  /sc daily /st 09:00
```

### 繪製歷史情緒圖表

```bash
# 過去 30 天
python src/plot_from_db.py --days 30

# 過去 7 天並匯出每日彙總 CSV
python src/plot_from_db.py --days 7 --export-csv
```

輸出：`gold_sentiment_from_db.png`

### 補充歷史資料（Finnhub）

```bash
python src/historical_sentiment_finnhub.py
```

> 注意：Finnhub 免費版僅保留約 7 天歷史新聞，`days` 參數超過 7 天幾乎無法取得舊資料。

---

## 輸出格式

### CSV 欄位（`Gold_Market_LLM_Analysis_YYYY-MM-DD.csv`）

| 欄位 | 說明 |
|------|------|
| Title | 新聞標題 |
| Summary | Yahoo Finance 摘要 |
| Link | 新聞原文網址 |
| Date | 發布時間（含時區） |
| Full_Content | 爬取的完整新聞內文 |
| Final_Text_For_AI | 實際送給 LLM 的文字 |
| LLM_Score | 情緒分數（-1.0 ~ +1.0） |
| LLM_Reason | 情緒分析原因（中文，20字內） |

### 終端機輸出範例

```
初始化系統...
資料庫連線成功
正在從 Yahoo Finance 獲取黃金新聞列表...
正在抓取 10 則新聞內文...
正在呼叫 LLM 進行深度情緒分析...
正在存入 PostgreSQL 資料庫...
--- 資料庫存入完成！新增 10 則新聞 ---
--- CSV 存檔完成：Gold_Market_LLM_Analysis_2026-05-30.csv ---

   Title                                    LLM_Score  LLM_Reason
0  Gold hits record above $3,500...         +0.70     金價創歷史新高
1  Central banks slow gold purchases...     -0.20     央行買盤減少
2  Inflation data boosts safe-haven...      +0.50     通膨推升避險需求

今日平均情緒分數: +0.33 (利多)
```

---

## 版本演進

| 版本 | 檔案 | 新聞來源 | 分析引擎 | 儲存方式 | 狀態 |
|------|------|----------|----------|----------|------|
| V1 | `goldSentimentAnalyzer.py` | Investing.com（Selenium） | FinBERT | CSV | 已棄用 |
| V2 | `goldSentimentAnalyzerV2.py` | Yahoo Finance（requests） | FinBERT | CSV | 已棄用 |
| V3 | `goldSentimentAnalyzerV3.py` | Yahoo Finance（requests） | Gemini LLM | PostgreSQL + CSV | 目前使用 |

---

## 注意事項

- **LLM Prompt 格式**：解析依賴正則表達式 `分數:\s*([-+]?\d*\.?\d+)` 與 `原因:\s(.*)`，修改 Prompt 格式須同步修改解析邏輯
- **資料庫降級機制**：PostgreSQL 連線失敗時自動降級為純 CSV 模式，程式不會中斷
- **中文字體**：`plot_from_db.py` 在 Windows 使用 `Microsoft JhengHei`，Linux 回退 `SimHei`，非中文環境需確認字體存在
- **爬取頻率**：內文抓取設有 1.5 秒延遲，避免對來源網站造成過大負擔

---

## 授權

MIT License
