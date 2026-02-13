import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText

# --- 1. 中文名稱對照表 (可自行增加常用代號) ---
STOCK_NAMES = {
    "2330": "台積電", "2317": "鴻海", "6203": "海韻電", 
    "3570": "大塚", "4766": "南寶", "NVDA": "輝達",
    "2313": "華通", "2454": "聯發科"
}

# --- 2. Email 發送函數 ---
def send_dual_email(sender, pwd, receivers, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"股市監控小幫手 <{sender}>"
        msg['To'] = ", ".join(receivers)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, pwd)
            server.send_message(msg)
        return True
    except:
        return False

st.set_page_config(page_title="親友專屬股市監控 Pro", layout="wide")
st.title("📈 股市多指標監控 & 自動通知系統")

# 後台 Secrets 讀取 (請確保 Streamlit 後台已設定 GMAIL_USER 與 GMAIL_PASSWORD)
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

st.sidebar.header("👤 使用者設定")
friend_email = st.sidebar.text_input("接收通知信箱", placeholder="請輸入您的 Email")
ticker_input = st.sidebar.text_area("自選股清單 (輸入數字即可)", "2330, 2317, 6203, 3570, 4766")
run_button = st.sidebar.button("立即執行掃描")

def analyze_stock(symbol):
    try:
        # 1. 自動補齊台灣股票後綴
        pure_code = symbol.strip().upper()
        target_symbol = pure_code
        if pure_code.isdigit():
            temp_stock = yf.download(f"{pure_code}.TW", period="5d", progress=False)
            target_symbol = f"{pure_code}.TW" if not temp_stock.empty else f"{pure_code}.TWO"

        stock = yf.Ticker(target_symbol)
        df = stock.history(period="1y")
        if df.empty or len(df) < 60: return None
        
        # --- 修正為中文公司名稱 ---
        # 優先從對照表抓，抓不到才用 yfinance 的英文名
        ch_name = STOCK_NAMES.get(pure_code, stock.info.get('shortName', target_symbol))
        
        close = df['Close']
        volume = df['Volume']
        high = df['High']
        
        # 指標計算 (均價稱為 SMA, 均量稱為 MA)
        sma3, sma5, sma10 = close.rolling(3).mean(), close.rolling(5).mean(), close.rolling(10).mean()
        sma20, sma60 = close.rolling(20).mean(), close.rolling(60).mean()
        ma3, ma5 = volume.rolling(3).mean(), volume.rolling(5).mean()
        high5 = high.rolling(5).max()
        
        curr_price = close.iloc[-1]
        curr_vol = volume.iloc[-1]
        
        # 條件 A (當日量 > 3日均量 1.5 倍) & B (收盤 > 5SMA)
        cond_A = (curr_vol > ma3.iloc[-1] * 1.5) and (ma3.iloc[-1] > ma5.iloc[-1])
        cond_B = curr_price > sma5.iloc[-1]
        
        status = "觀察中"
        email_content = ""
        if cond_A and cond_B:
            status = "🚀 突破成功"
            # 修正原因文字描述
            email_content = (f"【突破通知】\n"
                             f"標的：{ch_name} ({target_symbol})\n"
                             f"價格：{curr_price:.2f}\n"
                             f"原因：量能達標(>1.5倍)且價突破5SMA，但注意未來3日的收盤價 > 5SMA。")
            
        warning = "✅ 正常"
        if curr_price < high5.iloc[-1]:
            warning = "⚠️ 警示 (未過5日高)"

        return {
            "代號": target_symbol,
            "公司名稱": ch_name,
            "現價": round(curr_price, 2),
            "SMA 3/5/10": f"{sma3.iloc[-1]:.1f}/{sma5.iloc[-1]:.1f}/{sma10.iloc[-1]:.1f}",
            "SMA 20/60": f"{sma20.iloc[-1]:.1f}/{sma60.iloc[-1]:.1f}",
            "MA 3/5(萬)": f"{ma3.iloc[-1]/10000:.1f}/{ma5.iloc[-1]/10000:.1f}",
            "狀態": status,
            "風險檢查": warning,
            "通知內容": email_content
        }
    except:
        return None

if run_button:
    if not MY_GMAIL or not MY_PWD:
        st.error("後台 Secrets 未正確設定發信帳號！")
    elif not friend_email:
        st.warning("請填寫接收通知的 Email。")
    else:
        tickers = [t.strip() for t in ticker_input.split(',')]
        results = []
        sent_count = 0
        receiver_list = [MY_GMAIL, friend_email] # 同步寄給您與指定親友
        
        for t in tickers:
            res = analyze_stock(t)
            if res:
                results.append(res)
                # 只有符合「突破成功」才發送 Email
                if res["通知內容"]:
                    if send_dual_email(MY_GMAIL, MY_PWD, receiver_list, f"突破通知: {res['代號']}", res["通知內容"]):
                        sent_count += 1
        
        if results:
            # 顯示表格並移除隱藏欄位
            st.dataframe(pd.DataFrame(results).drop(columns=['通知內容']), use_container_width=True)
            if sent_count > 0:
                st.success(f"掃描完成！已發送 {sent_count} 封突破通知信。")
            else:
                st.info("目前無符合條件之標的，未發送郵件。")
