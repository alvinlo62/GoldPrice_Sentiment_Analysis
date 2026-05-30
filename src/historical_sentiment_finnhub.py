"""
黃金市場歷史情緒分析 - 使用 Finnhub API
抓取過去 30 天的黃金相關新聞，計算每日情緒分數，並繪製線圖
"""
import os
import re
import time
from datetime import datetime, timedelta
from collections import defaultdict

import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


class HistoricalGoldSentimentAnalyzer:
    def __init__(self):
        print("初始化系統...")
        
        # Gemini API
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            raise ValueError("錯誤：找不到 GEMINI_API_KEY，請檢查 .env 檔案！")
        genai.configure(api_key=gemini_key)
        self.llm_model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Finnhub API
        self.finnhub_key = os.getenv("FINNHUB_API_KEY")
        if not self.finnhub_key:
            raise ValueError("錯誤：找不到 FINNHUB_API_KEY，請檢查 .env 檔案！")
        
        self.finnhub_base_url = "https://finnhub.io/api/v1"
    
    def fetch_market_news(self, category="general", min_id=0):
        """
        抓取 Finnhub 市場新聞
        category: general, forex, crypto, merger
        """
        url = f"{self.finnhub_base_url}/news"
        params = {
            "category": category,
            "token": self.finnhub_key,
            "minId": min_id
        }
        
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Finnhub API 錯誤: {e}")
            return []
    
    def filter_gold_news(self, news_list):
        """
        過濾出黃金相關新聞
        """
        gold_keywords = [
            "gold", "黃金", "xau", "precious metal", "bullion",
            "gold price", "gold futures", "gold market", "gold trading",
            "safe haven", "inflation hedge", 'metal', 'commodity', '黃金', '金價'
        ]
        
        filtered = []
        for news in news_list:
            headline = news.get("headline", "").lower()
            summary = news.get("summary", "").lower()
            combined = headline + " " + summary
            
            if any(kw in combined for kw in gold_keywords):
                filtered.append(news)
        
        return filtered
    
    def collect_historical_news(self, days=7, max_news_per_day=20):
        """
        收集過去 N 天的黃金新聞
        注意：Finnhub 免費版的 market-news 只保留最近約 1 週的新聞
        """
        print(f"正在收集過去 {days} 天的黃金相關新聞...")
        
        all_news = []
        seen_ids = set()  # 用於追蹤已見過的新聞 ID，避免重複
        min_id = 0
        
        # Finnhub market-news 會返回最新的新聞，我們需要多次呼叫來獲取更多
        # 免費版限制：每分鐘 60 次呼叫
        for i in range(10):  # 最多嘗試 10 次
            print(f"  抓取批次 {i+1}...")
            news_batch = self.fetch_market_news(category="general", min_id=min_id)
            
            if not news_batch:
                break
            
            # 過濾黃金相關
            gold_news = self.filter_gold_news(news_batch)
            
            # 去重：只加入未見過的新聞
            for news in gold_news:
                news_id = news.get("id")
                if news_id and news_id not in seen_ids:
                    seen_ids.add(news_id)
                    all_news.append(news)
            
            # 更新 min_id 以獲取更舊的新聞
            min_id = min(item.get("id", 0) for item in news_batch) - 1
            
            # 檢查是否已經超出日期範圍
            oldest_time = min(item.get("datetime", 0) for item in news_batch)
            oldest_date = datetime.fromtimestamp(oldest_time)
            cutoff_date = datetime.now() - timedelta(days=days)
            
            if oldest_date < cutoff_date:
                print(f"  已達到 {days} 天前的日期限制")
                break
            
            time.sleep(1)  # 避免超過 API 頻率限制
        
        print(f"共收集到 {len(all_news)} 則黃金相關新聞（已去重）")
        return all_news
    
    def group_news_by_date(self, news_list, max_per_day=20):
        """
        按日期分組新聞，每天最多取 max_per_day 則
        """
        grouped = defaultdict(list)
        
        for news in news_list:
            timestamp = news.get("datetime", 0)
            date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
            grouped[date_str].append(news)
        
        # 每天限制數量
        for date_str in grouped:
            if len(grouped[date_str]) > max_per_day:
                grouped[date_str] = grouped[date_str][:max_per_day]
        
        return dict(grouped)
    
    def analyze_with_llm(self, headline, summary):
        """
        使用 Gemini LLM 分析情緒，返回 (score, reason)
        """
        text = f"{headline}. {summary}"[:800]
        
        prompt = f"""
        你是一位專業的黃金市場分析師。請根據以下新聞標題與摘要，評估其對「黃金價格 (XAU/USD)」的短期影響：
        
        1. 分數範圍：-1.0 (極度利空) 到 1.0 (極度利多)
        2. 0.0 代表完全中性
        3. 請考慮經濟邏輯（通膨升溫、地緣政治緊張、美元走弱通常利多黃金、某公司的投資組合跑贏大盤 通常跟黃金價格無關）
        
        請嚴格按照此格式回覆（只需兩行）：
        分數: [數值]
        原因: [20字內簡述]

        新聞內容：
        {text}
        """
        
        try:
            response = self.llm_model.generate_content(prompt)
            res_text = response.text
            
            score_match = re.search(r"分數:\s*([-+]?\d*\.?\d+)", res_text)
            reason_match = re.search(r"原因:\s*(.*)", res_text)
            
            score = float(score_match.group(1)) if score_match else 0.0
            score = max(-1.0, min(1.0, score))  # 確保在範圍內
            reason = reason_match.group(1).strip() if reason_match else "分析完成"
            
            return score, reason
        except Exception as e:
            print(f"LLM 錯誤: {e}")
            return 0.0, f"LLM Error: {e}"
    
    def calculate_daily_sentiment(self, grouped_news):
        """
        計算每日平均情緒分數，並收集每則新聞的詳細資料
        返回: (daily_scores, all_news_details)
        """
        daily_scores = {}
        all_news_details = []  # 儲存每則新聞的詳細資料
        
        total_days = len(grouped_news)
        for idx, (date_str, news_list) in enumerate(sorted(grouped_news.items())):
            print(f"正在分析 {date_str} ({idx+1}/{total_days})...")
            
            scores = []
            for news in news_list:
                headline = news.get("headline", "")
                summary = news.get("summary", "")
                url = news.get("url", "")
                source = news.get("source", "")
                timestamp = news.get("datetime", 0)
                news_id = news.get("id", "")
                image = news.get("image", "")
                
                # LLM 分析
                score, reason = self.analyze_with_llm(headline, summary)
                scores.append(score)
                
                # 組合 Final_Text_For_AI
                final_text = f"{headline}. {summary}"[:800]
                
                # 儲存詳細資料
                all_news_details.append({
                    "Date": date_str,
                    "Datetime": datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "",
                    "Title": headline,
                    "Summary": summary,
                    "Link": url,
                    "Source": source,
                    "Final_Text_For_AI": final_text,
                    "LLM_Score": score,
                    "LLM_Reason": reason,
                    "News_ID": news_id,
                    "Image_URL": image
                })
                
                time.sleep(0.5)  # Gemini API 頻率限制
            
            avg_score = sum(scores) / len(scores) if scores else 0.0
            daily_scores[date_str] = {
                "avg_score": round(avg_score, 3),
                "news_count": len(scores),
                "scores": scores
            }
            print(f"  平均分數: {avg_score:.3f} (共 {len(scores)} 則)")
        
        return daily_scores, all_news_details
    
    def save_detailed_csv(self, news_details, output_path="data/historical_news_detailed.csv"):
        """
        儲存每則新聞的詳細資料到 CSV（類似 goldSentimentAnalyzerV3 的輸出格式）
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        df = pd.DataFrame(news_details)
        
        # 重新排列欄位順序
        column_order = [
            "Date", "Datetime", "Title", "Summary", "Link", "Source",
            "Final_Text_For_AI", "LLM_Score", "LLM_Reason", "News_ID", "Image_URL"
        ]
        df = df[[col for col in column_order if col in df.columns]]
        
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"詳細新聞 CSV 已儲存至: {output_path}")
        return df
    
    def plot_sentiment_chart(self, daily_scores, output_path="gold_sentiment_chart.png"):
        """
        繪製情緒指數線圖
        """
        if not daily_scores:
            print("無數據可繪製")
            return
        
        # 準備數據
        dates = [datetime.strptime(d, "%Y-%m-%d") for d in sorted(daily_scores.keys())]
        scores = [daily_scores[d.strftime("%Y-%m-%d")]["avg_score"] for d in dates]
        counts = [daily_scores[d.strftime("%Y-%m-%d")]["news_count"] for d in dates]
        
        # 設定中文字體
        plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'SimHei', 'Arial']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 創建圖表
        fig, ax1 = plt.subplots(figsize=(14, 7))
        
        # 情緒分數線
        color_line = '#FFD700'  # 金色
        ax1.set_xlabel('日期', fontsize=12)
        ax1.set_ylabel('情緒分數', color=color_line, fontsize=12)
        ax1.plot(dates, scores, color=color_line, linewidth=2.5, marker='o', 
                 markersize=6, label='情緒分數')
        ax1.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
        ax1.set_ylim(-1.1, 1.1)
        ax1.tick_params(axis='y', labelcolor=color_line)
        
        # 填充正負區域
        ax1.fill_between(dates, scores, 0, where=[s > 0 for s in scores], 
                         alpha=0.3, color='green', label='利多區')
        ax1.fill_between(dates, scores, 0, where=[s < 0 for s in scores], 
                         alpha=0.3, color='red', label='利空區')
        
        # 新聞數量柱狀圖（次要Y軸）
        ax2 = ax1.twinx()
        color_bar = '#4169E1'
        ax2.set_ylabel('新聞數量', color=color_bar, fontsize=12)
        ax2.bar(dates, counts, alpha=0.3, color=color_bar, width=0.8, label='新聞數量')
        ax2.tick_params(axis='y', labelcolor=color_bar)
        
        # 格式化 X 軸日期
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        ax1.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        plt.xticks(rotation=45)
        
        # 標題與圖例
        plt.title('黃金市場情緒指數 - 過去30天', fontsize=16, fontweight='bold', pad=20)
        
        # 合併圖例
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.show()
        
        print(f"圖表已儲存至: {output_path}")
    
    def save_to_csv(self, daily_scores, output_path="data/historical_sentiment.csv"):
        """
        儲存每日情緒分數到 CSV
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        rows = []
        for date_str, data in sorted(daily_scores.items()):
            rows.append({
                "日期": date_str,
                "平均情緒分數": data["avg_score"],
                "新聞數量": data["news_count"]
            })
        
        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"CSV 已儲存至: {output_path}")
        return df
    
    def run(self, days=30):
        """
        執行完整流程
        """
        # 1. 收集歷史新聞
        all_news = self.collect_historical_news(days=days)
        
        if not all_news:
            print("警告：未能收集到任何黃金相關新聞")
            return None
        
        # 2. 按日期分組
        grouped = self.group_news_by_date(all_news, max_per_day=20)
        print(f"共有 {len(grouped)} 天的數據")
        
        # 3. LLM 情緒分析
        daily_scores, news_details = self.calculate_daily_sentiment(grouped)
        
        # 4. 儲存 CSV
        self.save_to_csv(daily_scores)
        self.save_detailed_csv(news_details)  # 儲存詳細新聞資料
        
        # 5. 繪製圖表
        self.plot_sentiment_chart(daily_scores)
        
        return daily_scores


if __name__ == "__main__":
    analyzer = HistoricalGoldSentimentAnalyzer()
    results = analyzer.run(days=7)
    
    if results:
        print("\n=== 分析完成 ===")
        print("每日情緒分數摘要：")
        for date, data in sorted(results.items()):
            sentiment = "利多 📈" if data["avg_score"] > 0.1 else ("利空 📉" if data["avg_score"] < -0.1 else "中性 ➖")
            print(f"  {date}: {data['avg_score']:+.3f} ({data['news_count']}則) {sentiment}")
