import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
import os
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv
from src.db_manager import GoldSentimentDB

load_dotenv()

class GoldSentimentAnalyzerV3:
    def __init__(self, use_db=True):
        print("初始化系統...")
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("錯誤：找不到 GEMINI_API_KEY，請檢查 .env 檔案！")
        
        genai.configure(api_key=api_key)
        self.llm_model = genai.GenerativeModel('gemini-3-flash-preview')
        
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        
        # 資料庫初始化
        self.use_db = use_db
        if use_db:
            try:
                self.db = GoldSentimentDB()
                self.db.init_db()
                print("資料庫連線成功")
            except Exception as e:
                print(f"資料庫連線失敗: {e}，將僅使用 CSV 儲存")
                self.use_db = False
                self.db = None
        else:
            self.db = None

    # 1. 直接從 yfinance 獲取新聞列表
    def get_news_list(self):
        print("正在從 Yahoo Finance 獲取黃金新聞列表...")
        gold = yf.Ticker("GC=F")
        raw_news = gold.news
        
        if not raw_news:
            print("警告：未抓取到任何新聞")
            return pd.DataFrame()

        processed_news = []
        
        for item in raw_news:
            # 取得 nested 的 content 部分 (yfinance 新格式)
            content = item.get('content', {})
            
            # 如果 item 本身就是攤平的，則直接取值；否則從 content 取值
            title = content.get('title', item.get('title', 'No Title'))
            summary = content.get('summary', item.get('summary', ''))
            
            # 取得正確的連結 (通常在 canonicalUrl 裡面)
            link_info = content.get('canonicalUrl', {})
            link = link_info.get('url', item.get('link', ''))
            
            # 取得時間
            pub_date = content.get('pubDate', item.get('providerPublishTime', ''))
            
            processed_news.append({
                "Title": title,
                "Summary": summary,
                "Link": link,
                "Date": pub_date
            })
        
        df = pd.DataFrame(processed_news)
        
        # 轉換日期格式
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            
        return df

    # 2. 抓取 Yahoo 新聞內文
    def fetch_content(self, url):
        if not url or "video" in url: return "Video Content (Skipped)"
        try:
            time.sleep(1.5) # 稍微增加延遲，避免被 Yahoo 偵測
            res = requests.get(url, headers=self.headers, timeout=10)
            if res.status_code != 200: return f"HTTP {res.status_code}"
            
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # --- 強化版：嘗試多種可能的內文容器 ---
            content_selectors = [
                '.caas-body',           # Yahoo 原生
                '.article-body',        # Reuters 轉載
                '.body-copy',           # 一般新聞
                'article',              # 通用標籤
                '.main-content'         # 通用標籤
            ]
            
            body = None
            for selector in content_selectors:
                body = soup.select_one(selector)
                if body: break
            
            if body:
                # 抓取 p 標籤，並過濾掉太短的句子（通常是廣告或選單）
                paragraphs = body.find_all('p')
                text = " ".join([p.get_text() for p in paragraphs if len(p.get_text()) > 30])
                return text if len(text) > 50 else "Content too short"
            
            return "Selector Failed"
        except Exception as e:
            return f"Error: {str(e)}"

    # 3. LLM 情緒分析引擎 (-1 to +1)
    def analyze_with_llm(self, text, link):
        # 截取前 1000 字避免 token 過長
        full_text = text[:1000]
        
        prompt = f"""
        你是一位專業的黃金市場分析師。請根據以下新聞內容，如果資訊不足，可自行存取新聞連結，查看更完整的資訊，評估其對「黃金價格 (XAU/USD)」的短期影響：
        
        1. 分數範圍：-1.0 (極度利空) 到 1.0 (極度利多)。
        2. 0.0 代表完全中性。
        3. 請考慮經濟邏輯（例如：通膨升溫、地緣政治緊張、美元走弱 通常利多黃金、某公司的投資組合跑贏大盤 通常跟黃金價格無關）。
        
        請嚴格按照此格式回覆：
        分數: [數值]
        原因: [20字內簡述]

        新聞內容：
        {full_text}
        連結：
        {link}
        """
        
        try:
            response = self.llm_model.generate_content(prompt)
            res_text = response.text
            
            # 提取分數與原因
            score_match = re.search(r"分數:\s*([-+]?\d*\.\d+|\d+)", res_text)
            reason_match = re.search(r"原因:\s*(.*)", res_text)
            
            score = float(score_match.group(1)) if score_match else 0.0
            reason = reason_match.group(1).strip() if reason_match else "分析完成"
            return score, reason
        except Exception as e:
            return 0.0, f"LLM Error: {str(e)}"

    def run(self, save_csv=True):
            # A. 抓新聞
            df = self.get_news_list()
            if df.empty: return "No News Found"

            # B. 抓內文
            print(f"正在抓取 {len(df)} 則新聞內文...")
            df['Full_Content'] = df['Link'].apply(self.fetch_content)

            def merge_text(row):
                if len(row['Full_Content']) < 100:
                    return f"{row['Title']}. {row['Summary']}"
                return row['Full_Content']
        
            df['Final_Text_For_AI'] = df.apply(merge_text, axis=1)
            
            # C. LLM 評分
            print("正在呼叫 LLM 進行深度情緒分析...")
            llm_results = []
            for _, row in df.iterrows():
                score, reason = self.analyze_with_llm(row['Final_Text_For_AI'], row['Link'])
                llm_results.append({'LLM_Score': score, 'LLM_Reason': reason})
                time.sleep(1) # Gemini API 的頻率限制
            
            # 合併結果
            res_df = pd.DataFrame(llm_results)
            final_df = pd.concat([df, res_df], axis=1)
            
            # D. 存入資料庫
            if self.use_db and self.db:
                print("正在存入 PostgreSQL 資料庫...")
                inserted_count = 0
                today = datetime.now().strftime("%Y-%m-%d")
                
                for _, row in final_df.iterrows():
                    news_data = {
                        "date": today,
                        "datetime": row.get('Date') if pd.notna(row.get('Date')) else datetime.now(),
                        "title": row.get('Title'),
                        "summary": row.get('Summary'),
                        "link": row.get('Link'),
                        "source": "Yahoo Finance",
                        "full_content": row.get('Full_Content'),
                        "final_text_for_ai": row.get('Final_Text_For_AI'),
                        "llm_score": row.get('LLM_Score'),
                        "llm_reason": row.get('LLM_Reason')
                    }
                    if self.db.insert_news(news_data):
                        inserted_count += 1
                
                # 更新每日情緒分數
                self.db.update_daily_sentiment(today)
                print(f"--- 資料庫存入完成！新增 {inserted_count} 則新聞 ---")
            
            # E. 存 CSV（保留原有功能）
            if save_csv:
                final_df.to_csv(f"Gold_Market_LLM_Analysis_{today}.csv", index=False, encoding="utf-8-sig")
                print(f"--- CSV 存檔完成：Gold_Market_LLM_Analysis_{today}.csv ---")
            
            print("--- 專案執行完成！---")
            return final_df

# --- 啟動程序 ---
if __name__ == "__main__":
    analyzer = GoldSentimentAnalyzerV3()
    result_df = analyzer.run()
    print(result_df[['Title', 'LLM_Score', 'LLM_Reason']].head())