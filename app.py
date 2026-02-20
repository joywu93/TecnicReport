import streamlit as st
import gspread
import pandas as pd
import yfinance as yf
import json
import re
import smtplib
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==========================================
# 🔧 1. 系統設定與 112 檔完整對照表 [cite: 14-38]
# ==========================================
st.set_page_config(page_title="股市戰略指揮中心", layout="wide")

# (此處省略 112 檔名稱表，請保留您原本程式中那一長串名稱)

def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

# ==========================================
# 🧠 2. 核心戰略判讀大腦 (2026 修正版) [cite: 253-302]
# ==========================================
def analyze_strategy(df):
    close, volume = df['Close'], df['Volume']
    if len(close) < 240: return "資料不足", 0, 0, False
    
    # 基礎數值
    curr_price, prev_price = float(close.iloc[-1]), float(close.iloc[-2])
    curr_vol, prev_vol = float(volume.iloc[-1]), float(volume.iloc[-2])
    pct_change = (curr_price - prev_price) / prev_price
    
    # 均線計算 [cite: 66-71]
    sma5 = close.rolling(5).mean()
    sma10 = close.rolling(10).mean()
    sma20 = close.rolling(20).mean()
    sma60 = close.rolling(60).mean()
    sma240 = close.rolling(240).mean()
    
    v5, v10, v20, v60, v240 = sma5.iloc[-1], sma10.iloc[-1], sma20.iloc[-1], sma60.iloc[-1], sma240.iloc[-1]
    p5, p60 = sma5.iloc[-2], sma60.iloc[-2]
    
    # 均線趨勢 (計算今日與昨日差) [cite: 269-276]
    slope5 = v5 > p5
    slope10 = v10 > sma10.iloc[-2]
    slope20 = v20 > sma20.iloc[-2]
    up_count = sum([slope5, slope10, slope20])
    down_count = sum([not slope5, not slope10, not slope20])

    messages, is_alert = [], False

    # 1. 季線轉多/轉空 [cite: 257-262]
    if prev_price < p60 and curr_price > v60:
        messages.append(f"🚀 轉多訊號：站上季線(60SMA) ({v60:.2f})")
        is_alert = True
    elif prev_price > p60 and curr_price < v60:
        messages.append(f"📉 轉空警示：跌破季線(60SMA) ({v60:.2f})")
        is_alert = True

    # 2. 強勢反彈 [cite: 265-267]
    if pct_change >= 0.05 and curr_vol > prev_vol * 1.5:
        messages.append(f"🔥 強勢反彈 (漲>=5%且爆量1.5倍) 慎防未來3日跌破前3日收盤價({close.iloc[-4]:.2f})")
        is_alert = True

    # 3. 形態轉折 (底部與高檔) 
    if up_count >= 2 and curr_price < v60 and curr_price < v240:
        messages.append(f"✨ 底部轉折：{up_count}條均線翻揚 60SMA({v60:.2f}) / 240SMA({v240:.2f})")
        is_alert = True
    elif down_count >= 2 and curr_price > v60 and curr_price > v240 and curr_price < v5:
        messages.append(f"✨ 高檔轉整理：{down_count}條均線翻下 5SMA({v5:.2f}) / 60SMA({v60:.2f}) / 240SMA({v240:.2f})")
        is_alert = True

    # 4. 量價背離 [cite: 280-282]
    if curr_vol > prev_vol * 1.2 and curr_price < v5 and pct_change < 0:
        messages.append(f"⚠️ 量價背離：量增價跌破5SMA({v5:.2f}) 觀察未來3日收盤價是否>{close.iloc[-4]:.2f}")
        is_alert = True

    # 5. 年線保衛戰 [cite: 285-290]
    dist_240 = (curr_price - v240) / v240
    if 0 < dist_240 < 0.05 and down_count >= 3:
        messages.append("⚠️ 年線保衛戰：均線偏弱，提防長黑")
        is_alert = True
    elif curr_price < v240 and down_count >= 3:
        messages.append("❄️ 空方弱勢整理：均線蓋頭")
        is_alert = True

    # 6. 均線糾結 [cite: 292-294]
    ma_diff = (max(v5, v10, v20) - min(v5, v10, v20)) / min(v5, v10, v20)
    if ma_diff < 0.02:
        messages.append("🌀 均線糾結：變盤在即")
        is_alert = True

    # 7. 乖離率附加標籤 [cite: 296-298]
    bias_val = ((curr_price - v60) / v60) * 100
    if curr_price > v60 * 1.3:
        messages.append(f"🚨 乖離率過高 60SMA({v60:.2f})")
        is_alert = True

    # 預設狀態 [cite: 299-302]
    if not messages:
        res = "🌊 多方行進 (觀察)" if curr_price > v60 else "☁️ 空方盤整 (觀望)"
        messages.append(res)

    return " | ".join(messages), curr_price, bias_val, is_alert

# (其餘 UI 與連線邏輯維持不變)
