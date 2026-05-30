"""
PostgreSQL 資料庫管理模組
用於黃金市場情緒分析數據的儲存與查詢
"""
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


class GoldSentimentDB:
    def __init__(self):
        """初始化資料庫連線"""
        self.conn_params = {
            "host": os.getenv("PG_HOST", "localhost"),
            "port": os.getenv("PG_PORT", "5432"),
            "database": os.getenv("PG_DATABASE", "gold_sentiment"),
            "user": os.getenv("PG_USER", "postgres"),
            "password": os.getenv("PG_PASSWORD", "")
        }
        self.conn = None
    
    def connect(self):
        """建立資料庫連線"""
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(**self.conn_params)
        return self.conn
    
    def close(self):
        """關閉連線"""
        if self.conn and not self.conn.closed:
            self.conn.close()
    
    def init_db(self):
        """初始化資料表"""
        conn = self.connect()
        cur = conn.cursor()
        
        # 建立新聞資料表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gold_news (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                datetime TIMESTAMP,
                title TEXT NOT NULL,
                summary TEXT,
                link TEXT UNIQUE,
                source TEXT,
                full_content TEXT,
                final_text_for_ai TEXT,
                llm_score REAL,
                llm_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_gold_news_date ON gold_news(date);
            CREATE INDEX IF NOT EXISTS idx_gold_news_link ON gold_news(link);
        """)
        
        # 建立每日情緒摘要表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_sentiment (
                date DATE PRIMARY KEY,
                avg_score REAL,
                news_count INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        conn.commit()
        cur.close()
        print("資料庫初始化完成")
    
    def insert_news(self, news_data: Dict[str, Any]) -> bool:
        """
        插入單則新聞（自動跳過重複連結）
        
        Args:
            news_data: 包含 title, summary, link, date 等欄位的字典
        
        Returns:
            True 如果插入成功，False 如果重複或失敗
        """
        conn = self.connect()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                INSERT INTO gold_news 
                (date, datetime, title, summary, link, source, full_content, 
                 final_text_for_ai, llm_score, llm_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (link) DO NOTHING
                RETURNING id
            """, (
                news_data.get("date"),
                news_data.get("datetime"),
                news_data.get("title"),
                news_data.get("summary"),
                news_data.get("link"),
                news_data.get("source"),
                news_data.get("full_content"),
                news_data.get("final_text_for_ai"),
                news_data.get("llm_score"),
                news_data.get("llm_reason")
            ))
            
            result = cur.fetchone()
            conn.commit()
            return result is not None
            
        except Exception as e:
            conn.rollback()
            print(f"插入新聞失敗: {e}")
            return False
        finally:
            cur.close()
    
    def insert_news_batch(self, news_list: List[Dict[str, Any]]) -> int:
        """
        批量插入新聞
        
        Returns:
            成功插入的數量
        """
        inserted = 0
        for news in news_list:
            if self.insert_news(news):
                inserted += 1
        return inserted
    
    def update_daily_sentiment(self, date: str):
        """更新指定日期的每日情緒分數"""
        conn = self.connect()
        cur = conn.cursor()
        
        try:
            # 計算該日平均分數
            cur.execute("""
                SELECT AVG(llm_score), COUNT(*)
                FROM gold_news
                WHERE date = %s AND llm_score IS NOT NULL
            """, (date,))
            
            result = cur.fetchone()
            avg_score, count = result[0], result[1]
            
            if count > 0:
                # 四捨五入到小數點後第二位
                avg_score_rounded = round(avg_score, 2)
                cur.execute("""
                    INSERT INTO daily_sentiment (date, avg_score, news_count, updated_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (date) DO UPDATE SET
                        avg_score = EXCLUDED.avg_score,
                        news_count = EXCLUDED.news_count,
                        updated_at = CURRENT_TIMESTAMP
                """, (date, avg_score_rounded, count))
                conn.commit()
            
        except Exception as e:
            conn.rollback()
            print(f"更新每日情緒失敗: {e}")
        finally:
            cur.close()
    
    def get_daily_sentiment(self, days: int = 30) -> List[Dict]:
        """
        取得過去 N 天的每日情緒分數
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cur.execute("""
                SELECT date, avg_score, news_count
                FROM daily_sentiment
                WHERE date >= CURRENT_DATE - INTERVAL '%s days'
                ORDER BY date ASC
            """, (days,))
            
            return [dict(row) for row in cur.fetchall()]
            
        finally:
            cur.close()
    
    def get_news_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """
        取得日期範圍內的所有新聞
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cur.execute("""
                SELECT * FROM gold_news
                WHERE date BETWEEN %s AND %s
                ORDER BY datetime DESC
            """, (start_date, end_date))
            
            return [dict(row) for row in cur.fetchall()]
            
        finally:
            cur.close()
    
    def get_news_count_by_date(self, date: str) -> int:
        """取得指定日期的新聞數量"""
        conn = self.connect()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                SELECT COUNT(*) FROM gold_news WHERE date = %s
            """, (date,))
            return cur.fetchone()[0]
        finally:
            cur.close()
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 測試用
if __name__ == "__main__":
    db = GoldSentimentDB()
    db.init_db()
    print("資料庫連線測試成功！")
    
    # 測試插入
    test_news = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "datetime": datetime.now(),
        "title": "Test Gold News",
        "summary": "This is a test summary",
        "link": f"https://test.com/news/{datetime.now().timestamp()}",
        "llm_score": 0.5,
        "llm_reason": "測試用"
    }
    
    if db.insert_news(test_news):
        print("測試新聞插入成功")
    else:
        print("測試新聞插入失敗（可能已存在）")
    
    db.close()
