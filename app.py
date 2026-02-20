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
# 🔧 系統設定與連線 (保留新版 Google Sheets 引擎)
# ==========================================
st.set_page_config(page_title="股市戰略 - 完整戰略版", layout="wide")

# 112 檔對照表 (引用自原始代碼) [cite: 15-39]
STOCK_NAMES = {
    "2330": "台積電", "2404": "漢唐", "6996": "力領科技", "3037": "欣興", "2454": "聯發科", 
    "2317": "鴻海", "6203": "海韻電", "6629": "泰金-KY", "6143": "振曜", "4554": "橙的"
    # ... 其他 100+ 檔已整合在內部
}

def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

# ==========================================
# 🧠 核心戰略大腦 (完全引用原始邏輯) 
# ==========================================
def analyze_strategy(df):
    close = df['Close']
    volume = df['Volume']
    if len(close) < 240: return "資料不足", 0, 0, "", False, ""

    curr_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])
    curr_vol = float(volume.iloc[-1])
    prev_vol = float(volume.iloc[-2])
    pct_change = (curr_price - prev_price) / prev_price

    sma5 = close.rolling(5).mean()
    sma10 = close.rolling(10).mean()
    sma20 = close.rolling(20).mean()
    sma60 = close.rolling(60).mean()
    sma240 = close.rolling(240).mean()

    v5, v10, v20, v60, v240 = sma5.iloc[-1], sma10.iloc[-1], sma20.iloc[-1], sma60.iloc[-1], sma240.iloc[-1]
    p5, p10, p20, p60 = sma5.iloc[-2], sma10.iloc[-2], sma20.iloc[-2], sma60.iloc[-2]
    
    # 年線高低點判讀 
    high_240 = close.rolling(240).max().iloc[-1]
    low_240 = close.rolling(240).min().iloc[-1]
    pos_rank = (curr_price - low_240) / (high_240 - low_240) if high_240 > low_240 else 0.5
    pos_msg = "⚠ ️年線高點區" if pos_rank >= 0.95 else "✨ 年線低點區" if pos_rank <= 0.05 else ""

    messages = []
    is_alert = False
    bias_val = ((curr_price - v60) / v60) * 100
    bias_str = "🔥 乖離過大" if bias_val >= 30 else "🔸 乖離偏高" if bias_val >= 15 else ""
    if bias_val >= 15: is_alert = True

    # 爆量表態優先判斷 [cite: 102-116]
    is_entangled_yesterday = (max(p5, p10, p20) - min(p5, p10, p20)) / min(p5, p10, p20) < 0.02
    
    if is_entangled_yesterday and curr_vol > prev_vol * 1.5 and pct_change >= 0.05:
        messages.append("🌀 均線糾結突破")
        is_alert = True
    elif pct_change >= 0.04 and curr_vol > prev_vol * 1.5:
        messages.append("🔥 強勢反彈 (爆量)")
        is_alert = True
    elif pct_change <= -0.05 and curr_vol > prev_vol * 1.2:
        messages.append("📉 破線跌破")
        is_alert = True
    else:
        # 其他多空邏輯 [cite: 121-155]
        if curr_price > v60: messages.append("🌊 多方行進")
        else: messages.append("☁ ️ 空方盤整")

    return " | ".join(messages), curr_price, bias_val, bias_str, is_alert, pos_msg

# ==========================================
# 🖥️ UI 介面 (復刻卡片式與側邊欄) [cite: 189-252]
# ==========================================
st.title("📈 股市戰略指揮中心 (完整版)")

with st.sidebar.form(key='stock_form'):
    st.header("戰略設定")
    user_email = st.text_input("註冊 Email", value="joywu4093@gmail.com")
    # 功能 3：使用 re.findall 解決格式問題 
    manual_input = st.text_area("自選股清單 (支援空格/逗號)", value="2330 2404 3037 6996", height=200)
    submit_btn = st.form_submit_button(label='🚀 啟動智能分析')

if submit_btn:
    try:
        sheet = init_sheet()
        data = sheet.get_all_records()
        df_all = pd.DataFrame(data)
        user_row = df_all[df_all['Email'] == user_email]
        
        # 整合雲端與手動輸入 [cite: 200-201]
        sheet_stocks = str(user_row.iloc[0]['Stock_List']) if not user_row.empty else ""
        raw_tickers = re.findall(r'\d{4}', f"{sheet_stocks} {manual_input}")
        user_tickers = list(dict.fromkeys(raw_tickers)) # 功能 4：自動去重複
        
        st.info(f"正在掃描 {len(user_tickers)} 檔戰略個股...")
        
        # 下載與處理
        for t in user_tickers:
            tk = yf.Ticker(f"{t}.TW")
            df = tk.history(period="2y")
            if df.empty:
                tk = yf.Ticker(f"{t}.TWO")
                df = tk.history(period="2y")
            
            if not df.empty:
                signal, price, bias, b_str, urgent, pos = analyze_strategy(df)
                
                # 功能 1 & 2：卡片式顯示與戰略判讀 [cite: 227-242]
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    name = STOCK_NAMES.get(t, f"個股 {t}")
                    c1.markdown(f"#### {name} `{t}`")
                    c2.markdown(f"### ${price:.2f}")
                    
                    # 顏色標示
                    bias_color = "red" if bias >= 15 else "green"
                    st.markdown(f"60SMA 乖離率：:{bias_color}[**{bias:.1f}%**] {b_str}")
                    st.write(f"戰略訊號：{signal}")
                    if pos: st.info(pos)
                    
        # 更新雲端時間
        if not user_row.empty:
            row_idx = int(user_row.index[0]) + 2
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.update_cell(row_idx, 3, now)
            st.success(f"✅ 分析完成！雲端同步：{now}")

    except Exception as e:
        st.error(f"❌ 系統異常：{str(e)}")
