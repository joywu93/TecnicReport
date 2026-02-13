import streamlit as st
import yfinance as yf
import pandas as pd
import requests

# Line Notify 函數
def send_line(message, token):
    if not token: return
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": "Bearer " + token}
    data = {"message": message}
    requests.post(url, headers=headers)

st.set_page_config(page_title="股市監控 Pro", layout="wide")
st.title("📈 股市短線突破 & 自動通知系統")

# 側邊欄設定
st.sidebar.header("系統設定")
line_token = st.sidebar.text_input("輸入 Line Notify Token", type="password")
ticker_input = st.sidebar.text_area("自選股清單 (用逗號隔開)", "2330.TW, 2317.TW, 2454.TW")
run_button = st.sidebar.button("立即執行掃描")

def analyze_stock(symbol):
    try:
        df = yf.download(symbol, period="1y", progress=False)
        if df.empty: return None
        
        # 數值提取 (處理 yfinance 多層索引問題)
        close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        volume = df['Volume'].iloc[:, 0] if isinstance(df['Volume'], pd.DataFrame) else df['Volume']
        high = df['High'].iloc[:, 0] if isinstance(df['High'], pd.DataFrame) else df['High']

        # 1.) 計算均線與均量
        ma5 = close.rolling(5).mean()
        mv3 = volume.rolling(3).mean()
        mv5 = volume.rolling(5).mean()
        high5 = high.rolling(5).max() # 近5日高點
        
        curr_price = close.iloc[-1]
        curr_vol = volume.iloc[-1]
        
        # 2.) 判斷條件
        # A. 當日量 > 3日均量*1.5 & 3日均量 > 5日均量
        cond_A = (curr_vol > mv3.iloc[-1] * 1.5) and (mv3.iloc[-1] > mv5.iloc[-1])
        # B. 當日價 > 5日均價
        cond_B = curr_price > ma5.iloc[-1]
        
        status = "觀察中"
        msg = ""
        
        if cond_A and cond_B:
            status = "🚀 突破成功"
            msg = f"\n【突破通知】\n股票：{symbol}\n價格：{curr_price:.2f}\n成交量爆發中！"
            
        # 2-1-C.) 假突破檢查 (今日價 < 近5日最高價)
        warning = "✅ 正常"
        if curr_price < high5.iloc[-1]:
            warning = "⚠️ 警示 (未過前高)"

        return {
            "代號": symbol,
            "現價": round(curr_price, 2),
            "狀態": status,
            "風險檢查": warning,
            "通知訊息": msg
        }
    except Exception as e:
        return None

if run_button:
    tickers = [t.strip() for t in ticker_input.split(',')]
    results = []
    
    with st.spinner('掃描中...'):
        for t in tickers:
            res = analyze_stock(t)
            if res:
                results.append(res)
                # 如果有突破訊號，發送 Line
                if res["通知訊息"] and line_token:
                    send_line(res["通知訊息"], line_token)
    
    if results:
        st.table(pd.DataFrame(results).drop(columns=['通知訊息']))
        st.success("掃描完成！若符合條件已發送 Line 通知。")
    else:
        st.error("找不到相關數據，請檢查代號是否正確。")