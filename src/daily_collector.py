"""
每日黃金新聞收集器
設計用於排程執行（如 Windows Task Scheduler 或 cron）
每天執行一次，自動抓取最新新聞並存入資料庫
"""
import sys
from datetime import datetime
from src.goldSentimentAnalyzerV3 import GoldSentimentAnalyzerV3


def main():
    print(f"\n{'='*50}")
    print(f"每日黃金新聞收集器 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")
    
    try:
        # 初始化分析器（啟用資料庫）
        analyzer = GoldSentimentAnalyzerV3(use_db=True)
        
        # 執行分析（同時存 DB 和 CSV）
        result = analyzer.run(save_csv=True)
        
        if isinstance(result, str) and result == "No News Found":
            print("警告：今日未找到任何新聞")
            return 1
        
        print(f"\n本次收集完成，共處理 {len(result)} 則新聞")
        
        # 從資料庫讀取今日正確的平均分數
        from src.db_manager import GoldSentimentDB
        db = GoldSentimentDB()
        daily_data = db.get_daily_sentiment(days=1)
        db.close()
        
        if daily_data:
            today_data = daily_data[-1]  # 取最新一天
            avg_score = today_data['avg_score']
            news_count = today_data['news_count']
            sentiment = "利多 📈" if avg_score > 0.1 else ("利空 📉" if avg_score < -0.1 else "中性 ➖")
            print(f"今日平均情緒分數: {avg_score:+.2f} (共 {news_count} 則) {sentiment}")
        
        return 0
        
    except Exception as e:
        print(f"執行錯誤: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
