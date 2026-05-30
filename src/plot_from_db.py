"""
從 PostgreSQL 資料庫繪製黃金市場情緒線圖
"""
import argparse
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patheffects as pe
import pandas as pd
import yfinance as yf

from src.db_manager import GoldSentimentDB


def get_gold_price(start_date: str, end_date: str) -> pd.DataFrame:
    """
    取得黃金價格的每日收盤價
    優先使用 XAUUSD=X（現貨），失敗則用 GC=F（期貨）
    """
    tickers = ["XAUUSD=X", "GC=F"]
    
    for ticker in tickers:
        try:
            gold = yf.Ticker(ticker)
            hist = gold.history(start=start_date, end=end_date)
            if not hist.empty:
                print(f"使用 {ticker} 取得金價數據")
                price_df = hist[['Close']].reset_index()
                price_df.columns = ['date', 'gold_price']
                price_df['date'] = pd.to_datetime(price_df['date']).dt.tz_localize(None).dt.normalize()
                return price_df
        except Exception as e:
            print(f"{ticker} 取得失敗: {e}")
            continue
    
    print("警告：無法取得黃金價格數據")
    return pd.DataFrame()


def plot_sentiment_from_db(days: int = 30, output_path: str = "gold_sentiment_from_db.png", show_price: bool = True):
    """
    從資料庫讀取每日情緒分數並繪製線圖，可選擇性加入黃金價格曲線
    金價和情緒分數各自獨立抓取，不強制日期對齊
    """
    db = GoldSentimentDB()
    
    # 取得每日情緒數據（過去 N 天內有的數據）
    daily_data = db.get_daily_sentiment(days=days)
    
    if not daily_data:
        print("資料庫中沒有足夠的數據")
        return None
    
    # 轉換為 DataFrame
    sentiment_df = pd.DataFrame(daily_data)
    sentiment_df['date'] = pd.to_datetime(sentiment_df['date']).dt.normalize()
    
    print(f"情緒數據：共 {len(sentiment_df)} 天")
    
    # 獨立取得黃金價格（過去 N 天的每日收盤價）
    gold_price_df = None
    if show_price:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        gold_price_df = get_gold_price(start_date, end_date)
        
        if not gold_price_df.empty:
            print(f"金價數據：共 {len(gold_price_df)} 個交易日")
        else:
            print("警告：無法取得金價數據")
    
    # 設定中文字體
    plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'SimHei', 'Arial']
    plt.rcParams['axes.unicode_minus'] = False
    
    # 創建圖表
    fig, ax1 = plt.subplots(figsize=(14, 7))
    
    # 情緒分數線（左Y軸）- 使用情緒數據自己的日期
    color_sentiment = '#FF6B6B'  # 紅色
    ax1.set_xlabel('日期', fontsize=12)
    ax1.set_ylabel('情緒分數', color=color_sentiment, fontsize=12)
    ax1.plot(sentiment_df['date'], sentiment_df['avg_score'], color=color_sentiment, linewidth=2.5, 
             marker='o', markersize=6, label='情緒分數')
    ax1.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    ax1.set_ylim(-1.1, 1.1)
    ax1.tick_params(axis='y', labelcolor=color_sentiment)
    
    # 情緒分數數值標籤
    for x, y in zip(sentiment_df['date'], sentiment_df['avg_score']):
        ax1.annotate(f'{y:+.2f}', (x, y), textcoords='offset points', 
                     xytext=(0, 10), ha='center', fontsize=9, fontweight='bold', color=color_sentiment,
                     zorder=5, path_effects=[pe.withStroke(linewidth=2, foreground='white')])
    
    # 填充正負區域
    scores = sentiment_df['avg_score'].tolist()
    ax1.fill_between(sentiment_df['date'], scores, 0, where=[s > 0 for s in scores], 
                     alpha=0.2, color='green', label='利多區')
    ax1.fill_between(sentiment_df['date'], scores, 0, where=[s < 0 for s in scores], 
                     alpha=0.2, color='red', label='利空區')
    
    # 黃金價格線（右Y軸）- 使用金價數據自己的日期
    ax2 = None
    if show_price and gold_price_df is not None and not gold_price_df.empty:
        ax2 = ax1.twinx()
        color_price = '#FFD700'  # 金色
        ax2.set_ylabel('黃金價格 (USD)', color=color_price, fontsize=12)
        ax2.plot(gold_price_df['date'], gold_price_df['gold_price'], color=color_price, linewidth=2, 
                 linestyle='-', marker='s', markersize=4, label='XAUUSD 收盤價')
        ax2.tick_params(axis='y', labelcolor=color_price)
        
        # 金價數值標籤（放在點的下方避免遮擋情緒分數）
        for x, y in zip(gold_price_df['date'], gold_price_df['gold_price']):
            ax2.annotate(f'{y:.0f}', (x, y), textcoords='offset points', 
                         xytext=(0, -15), ha='center', fontsize=9, fontweight='bold', color=color_price,
                         zorder=5, path_effects=[pe.withStroke(linewidth=2, foreground='white')])
        
        # 設定價格軸範圍（留更多邊距給標籤）
        price_min = gold_price_df['gold_price'].min() * 0.99
        price_max = gold_price_df['gold_price'].max() * 1.02
        ax2.set_ylim(price_min, price_max)
    
    # 格式化 X 軸
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    ax1.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, days//10)))
    plt.xticks(rotation=45)
    
    # 標題
    title = f'黃金市場情緒指數 vs 金價 - 過去 {days} 天' if show_price else f'黃金市場情緒指數 - 過去 {days} 天'
    plt.title(title, fontsize=16, fontweight='bold', pad=20)
    
    # 合併圖例（放在右上角並縮小）
    lines1, labels1 = ax1.get_legend_handles_labels()
    if ax2:
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=9, framealpha=0.9)
    else:
        ax1.legend(lines1, labels1, loc='upper right', fontsize=9, framealpha=0.9)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.show()
    
    print(f"圖表已儲存至: {output_path}")
    
    db.close()
    return sentiment_df


def export_to_csv(days: int = 30, output_path: str = "data/sentiment_export.csv"):
    """
    匯出資料庫中的每日情緒數據到 CSV
    """
    db = GoldSentimentDB()
    daily_data = db.get_daily_sentiment(days=days)
    
    if not daily_data:
        print("沒有數據可匯出")
        return
    
    df = pd.DataFrame(daily_data)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"已匯出 {len(df)} 天的數據至: {output_path}")
    
    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="從資料庫繪製情緒線圖")
    parser.add_argument("--days", type=int, default=30, help="顯示過去 N 天的數據")
    parser.add_argument("--output", type=str, default="gold_sentiment_from_db.png", 
                        help="輸出圖片路徑")
    parser.add_argument("--no-price", action="store_true", help="不顯示黃金價格曲線")
    parser.add_argument("--export-csv", action="store_true", help="同時匯出 CSV")
    
    args = parser.parse_args()
    
    df = plot_sentiment_from_db(days=args.days, output_path=args.output, show_price=not args.no_price)
    
    if args.export_csv and df is not None:
        export_to_csv(days=args.days)
