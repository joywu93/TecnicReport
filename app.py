import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText

# Email 發送函數
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

# 後台 Secrets 讀取
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

st.sidebar.header("👤 使用者設定")
friend_email = st.sidebar.text_input("接收通知信箱", placeholder="請輸入您的 Email")
ticker_input = st.sidebar.text_area("自選股清單 (輸入數字即可)", "2330, 2317, 6203, 3570, 4766, NVDA")
run_button = st.sidebar.button("立即執行掃描")

def analyze_stock(symbol):
    try:
        # 1. 自動補齊台灣股票後綴
        target_symbol = symbol.strip().upper()
        if target_symbol.isdigit(): # 如果全是數字
            # 先試上市 (.TW)
            temp_stock = yf.download(f"{target_symbol}.TW", period="5d", progress=False)
            if not temp_stock.empty:
                target_symbol = f"{target_symbol}.TW"
            else:
                # 不行就試上櫃 (.TWO)
                target_symbol = f"{target_symbol}.TWO"

        stock = yf.Ticker(target_symbol)
        df = stock.history(period="1y")
        if df.empty or len(df) < 60: return None
        
        name = stock.info.get('shortName', target_symbol)
        
        close = df['Close']
        volume = df['Volume']
        high = df['High']
        
        # 指標計算
        ma3, mv3 = close.rolling(3).mean(), volume.rolling(3).mean()
        ma5, mv5 = close.rolling(5).mean(), volume.rolling(5).mean()
        ma10, mv10 = close.rolling(10).mean(), volume.rolling(10).mean()
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        high5 = high.rolling(5).max()
        
        curr_price = close.iloc[-1]
        curr_vol = volume.iloc[-1]
        
        # 條件 A (量能 > 3日均量 1.2 倍) & B (收盤 > 5日均價)
        cond_A = (curr_vol > mv3.iloc[-1] * 1.5) and (mv3.iloc[-1] > mv5.iloc[-1])
        cond_B = curr_price > ma5.iloc[-1]
        
        status = "觀察中"
        email_content = ""
        if cond_A and cond_B:
            status = "🚀 突破成功"
            email_content = f"【突破通知】\n標的：{name} ({target_symbol})\n價格：{curr_price:.2f}\n原因：量能達標(>1.2倍)且站在均線上。"
            
        warning = "✅ 正常"
        if curr_price < high5.iloc[-1]:
            warning = "⚠️ 警示 (未過5日高)"

        return {
            "代號": target_symbol,
            "名稱": name[:10],
            "現價": round(curr_price, 2),
            "MA3/5/10": f"{ma3.iloc[-1]:.1f}/{ma5.iloc[-1]:.1f}/{ma10.iloc[-1]:.1f}",
            "MA20/60": f"{ma20.iloc[-1]:.1f}/{ma60.iloc[-1]:.1f}",
            "MV3/5/10(萬)": f"{mv3.iloc[-1]/10000:.1f}/{mv5.iloc[-1]/10000:.1f}/{mv10.iloc[-1]/10000:.1f}",
            "狀態": status,
            "風險檢查": warning,
            "通知內容": email_content
        }
    except:
        return None

if run_button:
    if not MY_GMAIL or not MY_PWD:
        st.error("後台 Secrets 未正確設定！")
    elif not friend_email:
        st.warning("請填寫接收通知的 Email。")
    else:
        tickers = [t.strip() for t in ticker_input.split(',')]
        results = []
        sent_count = 0
        receiver_list = [MY_GMAIL, friend_email]
        
        for t in tickers:
            res = analyze_stock(t)
            if res:
                results.append(res)
                if res["通知內容"]:
                    if send_dual_email(MY_GMAIL, MY_PWD, receiver_list, f"突破通知: {res['代號']}", res["通知內容"]):
                        sent_count += 1
        
        if results:
            st.dataframe(pd.DataFrame(results).drop(columns=['通知內容']), use_container_width=True)
            if sent_count > 0:
                st.success(f"已發送 {sent_count} 封突破通知。")
            else:
                st.info("目前無符合條件之標的。")
