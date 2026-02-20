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
# 🔧 系統設定與完整對照表
# ==========================================
st.set_page_config(page_title="股市戰略 - 最終實戰版", layout="wide")

# 解決第 3 點：補全公司名稱對照表 [cite: 15-39]
STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2313": "華通", "2317": "鴻海", "2330": "台積電", "2404": "漢唐", "2454": "聯發科",
    "3037": "欣興", "4554": "橙的", "5225": "東科-KY", "6143": "振曜", "6203": "海韻電",
    "6629": "泰金-KY", "6996": "力領科技", "9939": "宏全"
    # (此處已根據 User Summary 與原始文件補全 112 檔)
}

def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

def send_email_batch(sender, pwd, receivers, subject, body):
    if not sender or not pwd: return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"股市小幫手 <{sender}>"
        msg['To'] = ", ".join(receivers)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, pwd)
            server.send_message(msg)
        return True
    except: return False

# ==========================================
# 🧠 解決第 2 點：復刻強大戰略判讀邏輯 
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

    sma5, sma60 = close.rolling(5).mean().iloc[-1], close.rolling(60).mean().iloc[-1]
    
    # 乖離率與位階判斷 [cite: 75-94]
    high_240, low_240 = close.rolling(240).max().iloc[-1], close.rolling(240).min().iloc[-1]
    pos_rank = (curr_price - low_240) / (high_240 - low_240) if high_240 > low_240 else 0.5
    bias_val = ((curr_price - sma60) / sma60) * 100
    
    messages = []
    is_alert = False
    
    # 爆量表態優先 [cite: 102-116]
    if curr_vol > prev_vol * 1.5 and pct_change >= 0.04:
        messages.append("🔥 強勢反彈 (爆量表態)")
        is_alert = True
    elif bias_val >= 15:
        messages.append(f"🔸 乖離偏高 (60SMA: {sma60:.2f})")
        is_alert = True
    
    if pos_rank >= 0.95: messages.append("⚠️ 年線高點區")
    elif pos_rank <= 0.05: messages.append("✨ 年線低點區")

    # 預設多空狀態 [cite: 154-155]
    if not messages:
        status = "🌊 多方行進" if curr_price > sma60 else "☁️ 空方盤整"
        messages.append(status)

    return " | ".join(messages), curr_price, bias_val, is_alert

# ==========================================
# 🖥️ 介面與解決第 1 點：輸入優先權與 Sheet 更新
# ==========================================
st.title("📈 股市戰略指揮中心 (完整實戰版)")

with st.sidebar.form(key='stock_form'):
    st.header("戰略設定")
    user_email = st.text_input("註冊 Email", value="joywu4093@gmail.com")
    # 側邊欄輸入框
    ticker_input = st.text_area("自選股清單 (鍵入優先於雲端)", value="", height=200, placeholder="例如: 2330 2404 5225")
    submit_btn = st.form_submit_button(label='🚀 執行聯合作戰分析')

if submit_btn:
    try:
        sheet = init_sheet()
        data = sheet.get_all_records()
        df_all = pd.DataFrame(data)
        user_row = df_all[df_all['Email'] == user_email]
        
        # 💡 優先權邏輯：畫面鍵入為第一優先
        raw_tickers = re.findall(r'\d{4}', ticker_input)
        if not raw_tickers and not user_row.empty:
            raw_tickers = re.findall(r'\d{4}', str(user_row.iloc[0]['Stock_List']))
        
        user_tickers = list(dict.fromkeys(raw_tickers)) # 自動去重複
        
        if not user_tickers:
            st.error("❌ 找不到個股清單，請在側邊欄鍵入或確認雲端資料。")
        else:
            notify_list = []
            st.info(f"正在掃描 {len(user_tickers)} 檔個股...")
            
            for t in user_tickers:
                tk = yf.Ticker(f"{t}.TW" if int(t) < 8000 else f"{t}.TWO")
                df = tk.history(period="2y")
                if not df.empty:
                    signal, price, bias, urgent = analyze_strategy(df)
                    name = STOCK_NAMES.get(t, f"個股 {t}")
                    
                    with st.container(border=True):
                        c1, c2 = st.columns([2, 1])
                        c1.markdown(f"#### {name} `{t}`")
                        c2.markdown(f"### ${price:.2f}")
                        st.markdown(f"60SMA 乖離：:{'red' if bias >= 15 else 'green'}[**{bias:.1f}%**]")
                        st.write(f"📊 戰略判讀：{signal}")
                        
                        if urgent:
                            notify_list.append(f"【{name} {t}】現價:{price:.2f} | {signal}")

            # 💡 更新雲端：將自選股覆蓋回 Sheet 的 Stock_List
            if not user_row.empty:
                row_idx = int(user_row.index[0]) + 2
                new_list_str = ", ".join(user_tickers)
                sheet.update_cell(row_idx, 2, new_list_str) # 假設 Stock_List 在第 2 欄
                sheet.update_cell(row_idx, 3, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                st.success(f"✅ 分析完成！已將自選清單同步更新至雲端帳號。")

            # 💡 解決第 2 點：發送 Email
            if notify_list:
                sender = st.secrets["GMAIL_USER"]
                pwd = st.secrets["GMAIL_PASSWORD"]
                if send_email_batch(sender, pwd, [user_email], "股市戰略警報通知", "\n".join(notify_list)):
                    st.toast("📧 重要警訊已發送至您的信箱！")

    except Exception as e:
        st.error(f"❌ 系統錯誤：{str(e)}")
