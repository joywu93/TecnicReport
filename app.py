import streamlit as st
import yfinance as yf
import pandas as pd
import gspread
import re
import smtplib
import json
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# 💡 112 檔名單 (解決名稱缺失)
STOCK_NAMES = {"2330":"台積電","3014":"聯陽","2344":"華邦電","6996":"力領科技","2317":"鴻海"} # 此處可補完其餘名單

def analyze_strategy(df):
    try:
        if df.empty or len(df) < 60: return "資料不足", 0, 0, 0, False
        df.columns = df.columns.get_level_values(0)
        close = df['Close'].astype(float).dropna()
        lows, highs = df['Low'].astype(float).dropna(), df['High'].astype(float).dropna()
        curr_p = float(close.iloc[-1])
        ma60 = float(close.rolling(60).mean().iloc[-1])
        bias = ((curr_p - ma60) / ma60) * 100
        msg, is_mail = [], False
        # W底簡易判讀
        if curr_p > ma60 and bias < 5: 
            msg.append("🌊 多方行進")
            is_mail = True
        if not msg: msg.append("☁ 盤整中")
        return " | ".join(msg), curr_p, ma60, bias, is_mail
    except: return "分析錯誤", 0, 0, 0, False

st.title("📈 股市戰略指揮中心")
with st.sidebar:
    email_in = st.text_input("通知 Email", value="joywu4093@gmail.com")
    ticker_input = st.text_area("自選股清單", height=300)
    # 💡 修正：先定義按鈕！
    submit_btn = st.button("🚀 執行全戰略分析")

if submit_btn:
    tickers = re.findall(r'\d{4}', ticker_input)
    for t in tickers:
        df = yf.download(f"{t}.TW", period="1y", progress=False)
        if not df.empty:
            sig, p, s60, b, im = analyze_strategy(df)
            st.write(f"【{STOCK_NAMES.get(t, t)}】${p:.2f} | {sig}")
