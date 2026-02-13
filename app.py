import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText

# Email 發送函數
def send_email(sender, pwd, receiver, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = receiver
        
        # 使用 Gmail SMTP 伺服器
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, pwd)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Email 發送失敗: {e}")
        return False

st.set_page_config(page_title="股市監控 Email 版", layout="wide")
st.title("📈 股市短線突破 & Email 通知系統")

# 側邊欄：通知設定
st.sidebar.header("📧 通知設定")
my_gmail = st.sidebar.text_input("您的 Gmail 帳號", value="joy****@gmail.com")
app_password = st.sidebar.text_input("應用程式密碼 (16位碼)", type="password")
target_email = st.sidebar.text_input("接收通知的信箱 (預設同自己)")

ticker_input = st.sidebar.text_area("自選股清單 (逗號隔開)", "2330.TW, 2317.TW, NVDA")
run_button = st.sidebar.button("立即執行掃描")

# 複用先前的分析邏輯
def analyze_stock(symbol):
    try:
        df = yf.download(symbol, period="1y", progress=False)
        if df.empty: return None
        
        close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        volume = df['Volume'].iloc[:, 0] if isinstance(df['Volume'], pd.DataFrame) else df['Volume']
        high = df['High'].iloc[:, 0] if isinstance(df['High'], pd.DataFrame) else df['High']

        ma5 = close.rolling(5).mean()
        mv3 = volume.rolling(3).mean()
        mv5 = volume.rolling(5).mean()
        high5 = high.rolling(5).max()
        
        curr_price = close.iloc[-1]
        curr_vol = volume.iloc[-1]
        
        # 條件 A & B
        cond_A = (curr_vol > mv3.iloc[-1] * 1.5) and (mv3.iloc[-1] > mv5.iloc[-1])
        cond_B = curr_price > ma5.iloc[-1]
        
        status = "觀察中"
        email_content = ""
        if cond_A and cond_B:
            status = "🚀 突破成功"
            email_content = f"股票：{symbol}\n價格：{curr_price:.2f}\n量能達標，符合短線突破條件！"
            
        warning = "✅ 正常"
        if curr_price < high5.iloc[-1]:
            warning = "⚠️ 警示 (未過5日高)"

        return {"代號": symbol, "現價": round(curr_price, 2), "狀態": status, "風險檢查": warning, "通知內容": email_content}
    except:
        return None

if run_button:
    if not app_password:
        st.warning("請輸入應用程式密碼後再執行。")
    else:
        tickers = [t.strip() for t in ticker_input.split(',')]
        results = []
        receiver = target_email if target_email else my_gmail
        
        for t in tickers:
            res = analyze_stock(t)
            if res:
                results.append(res)
                if res["通知內容"]:
                    send_email(my_gmail, app_password, receiver, f"股市突破通知: {res['代號']}", res["通知內容"])
        
        if results:
            st.table(pd.DataFrame(results).drop(columns=['通知內容']))
            st.success(f"掃描完成！符合條件的標的已發信至 {receiver}")

   
