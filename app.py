import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText

# Email 發送函數：支援同時發給多人
def send_dual_email(sender, pwd, receivers, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"股市監控小幫手 <{sender}>"
        msg['To'] = ", ".join(receivers) # 將多個收件者串接起來
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, pwd)
            server.send_message(msg)
        return True
    except:
        return False

st.set_page_config(page_title="親友專屬股市監控", layout="wide")
st.title("📈 股市短線突破監控系統 (親友專用版)")

# 從後台 Secrets 自動讀取您的資訊
# 請確保 Secrets 中有 GMAIL_USER 和 GMAIL_PASSWORD
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

# 側邊欄：親友只需填寫這兩項
st.sidebar.header("👤 使用者設定")
friend_email = st.sidebar.text_input("接收通知信箱", placeholder="請輸入您的 Email")
ticker_input = st.sidebar.text_area("自選股清單", "2330.TW, 2317.TW, NVDA")
run_button = st.sidebar.button("立即執行掃描")

def analyze_stock(symbol):
    try:
        df = yf.download(symbol, period="1y", progress=False)
        if df.empty: return None
        
        # 數據清理與計算
        close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        volume = df['Volume'].iloc[:, 0] if isinstance(df['Volume'], pd.DataFrame) else df['Volume']
        high = df['High'].iloc[:, 0] if isinstance(df['High'], pd.DataFrame) else df['High']

        # 技術指標計算
        ma5 = close.rolling(5).mean()
        mv3 = volume.rolling(3).mean()
        mv5 = volume.rolling(5).mean()
        high5 = high.rolling(5).max()
        
        curr_price = close.iloc[-1]
        curr_vol = volume.iloc[-1]
        
        # 判斷邏輯 A & B
        cond_A = (curr_vol > mv3.iloc[-1] * 1.3) and (mv3.iloc[-1] > mv5.iloc[-1])
        cond_B = curr_price > ma5.iloc[-1]
        
        status = "觀察中"
        email_content = ""
        if cond_A and cond_B:
            status = "🚀 突破成功"
            email_content = f"【突破通知】\n標的：{symbol}\n現價：{curr_price:.2f}\n原因：成交量爆發且站上均線，符合短線突破條件。"
            
        warning = "✅ 正常"
        if curr_price < high5.iloc[-1]:
            warning = "⚠️ 警示 (未過5日高)"

        return {"代號": symbol, "現價": round(curr_price, 2), "狀態": status, "風險檢查": warning, "通知內容": email_content}
    except:
        return None

if run_button:
    if not MY_GMAIL or not MY_PWD:
        st.error("系統後台未設定發信帳號，請聯絡管理員。")
    elif not friend_email:
        st.warning("請輸入您的 Email，以便接收通知。")
    else:
        tickers = [t.strip() for t in ticker_input.split(',')]
        results = []
        sent_count = 0
        
        # 設定雙收件者：您自己 + 親友
        receiver_list = [MY_GMAIL, friend_email]
        
        for t in tickers:
            res = analyze_stock(t)
            if res:
                results.append(res)
                if res["通知內容"]:
                    # 發送給兩者
                    if send_dual_email(MY_GMAIL, MY_PWD, receiver_list, f"股市突破通知: {res['代號']}", res["通知內容"]):
                        sent_count += 1
        
        if results:
            st.table(pd.DataFrame(results).drop(columns=['通知內容']))
            if sent_count > 0:
                st.success(f"掃判完成！已同步發送通知信至您與管理員的信箱。")
            else:
                st.info("目前無標的符合突破條件，未發送郵件。")

