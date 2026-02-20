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
# 🔧 1. 系統初始化與名稱對照
# ==========================================
st.set_page_config(page_title="股市戰略 - 全自動實戰版", layout="wide")

# [cite_start]基礎對照表 (針對特定不規範名稱) [cite: 36]
STOCK_NAMES_FIXED = {
    "6996": "力領科技", "5225": "東科-KY", "4763": "材料*-KY", "6613": "朋億*"
}

def get_company_name(ticker_obj, symbol):
    """💡 解決第 1 點：自動抓取名稱"""
    if symbol in STOCK_NAMES_FIXED:
        return STOCK_NAMES_FIXED[symbol]
    try:
        # 優先從 yfinance info 抓取
        name = ticker_obj.info.get('shortName') or ticker_obj.info.get('longName')
        return name if name else f"個股 {symbol}"
    except:
        return f"個股 {symbol}"

def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

# ==========================================
# [cite_start]🧠 2. 戰略判讀大腦 (復刻 240 日高低點與爆量邏輯) [cite: 58-156]
# ==========================================
def analyze_strategy(df):
    close = df['Close']
    volume = df['Volume']
    if len(close) < 240: return "資料不足", 0, 0, False, ""

    curr_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])
    curr_vol = float(volume.iloc[-1])
    prev_vol = float(volume.iloc[-2])
    pct_change = (curr_price - prev_price) / prev_price

    sma5 = close.rolling(5).mean().iloc[-1]
    sma60 = close.rolling(60).mean().iloc[-1]
    
    # [cite_start]年線高低位階判斷 [cite: 75-84]
    high_240 = float(close.rolling(240).max().iloc[-1])
    low_240 = float(close.rolling(240).min().iloc[-1])
    pos_rank = (curr_price - low_240) / (high_240 - low_240) if high_240 > low_240 else 0.5
    pos_msg = "⚠️ 年線高點" if pos_rank >= 0.95 else "✨ 年線低點" if pos_rank <= 0.05 else ""

    messages = []
    bias_val = ((curr_price - sma60) / sma60) * 100
    is_alert = False

    # [cite_start]戰略條件判斷 [cite: 102-140]
    if curr_vol > prev_vol * 1.5 and pct_change >= 0.04:
        messages.append("🔥 強勢反彈 (爆量)")
        is_alert = True
    elif bias_val >= 15:
        messages.append("🔸 乖離偏高")
        is_alert = True
    
    if not messages:
        messages.append("🌊 多方行進" if curr_price > sma60 else "☁️ 空方盤整")

    return " | ".join(messages), curr_price, bias_val, is_alert, pos_msg

# ==========================================
# 🖥️ 3. UI 介面與資料同步
# ==========================================
st.title("📈 股市戰略指揮中心 (雲端同步版)")

with st.sidebar.form(key='stock_form'):
    st.header("戰略設定")
    user_email = st.text_input("註冊 Email", value="joywu4093@gmail.com").strip()
    # 💡 解決第 2 點：界面鍵入優先
    ticker_input = st.text_area("自選股清單 (鍵入優先)", height=200, placeholder="例如: 2330 2404 5225")
    submit_btn = st.form_submit_button(label='🚀 啟動聯合作戰')

if submit_btn:
    try:
        sheet = init_sheet()
        data = sheet.get_all_records()
        df_all = pd.DataFrame(data)
        user_row = df_all[df_all['Email'] == user_email]
        
        # 💡 優先權邏輯：畫面鍵入 > 雲端存檔
        raw_input = re.findall(r'\d{4}', ticker_input)
        if not raw_input and not user_row.empty:
            raw_input = re.findall(r'\d{4}', str(user_row.iloc[0].get('Stock_List', '')))
        
        user_tickers = list(dict.fromkeys(raw_input))
        
        if not user_tickers:
            st.warning("⚠️ 請輸入股票代號或確認雲端清單。")
        else:
            notify_list = []
            st.info(f"正在分析 {len(user_tickers)} 檔戰略個股...")
            
            for t in user_tickers:
                tk = yf.Ticker(f"{t}.TW" if int(t) < 8000 else f"{t}.TWO")
                df = tk.history(period="2y")
                
                if not df.empty:
                    signal, price, bias, urgent, pos = analyze_strategy(df)
                    # 💡 解決第 1 點：從 yfinance 抓取名稱
                    name = get_company_name(tk, t)
                    
                    with st.container(border=True):
                        c1, c2 = st.columns([2, 1])
                        c1.markdown(f"#### {name} `{t}`")
                        c2.markdown(f"### ${price:.2f}")
                        st.markdown(f"60SMA 乖離：:{'red' if bias >= 15 else 'green'}[**{bias:.1f}%**] | {pos}")
                        st.write(f"📊 戰略判讀：{signal}")
                        if urgent:
                            notify_list.append(f"【{name}】${price:.2f} | {signal}")

            # 💡 解決第 3 點：新帳號自動加入，舊帳號自動更新
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            stock_list_str = ", ".join(user_tickers)
            
            if user_row.empty:
                # 新帳號：執行 append_row (Email, Stock_List, Update_Time)
                sheet.append_row([user_email, stock_list_str, now_str])
                st.success(f"🎊 歡迎新戰友！已為您在雲端建立帳號並儲存清單。")
            else:
                # 舊帳號：覆蓋 Stock_List
                row_idx = int(user_row.index[0]) + 2
                sheet.update_cell(row_idx, 2, stock_list_str) # 更新第 2 欄 (B)
                sheet.update_cell(row_idx, 3, now_str)        # 更新第 3 欄 (C)
                st.success(f"✅ 同步成功！雲端清單已根據您的輸入更新。")

    except Exception as e:
        st.error(f"❌ 系統錯誤：{str(e)}")
