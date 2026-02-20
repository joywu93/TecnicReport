import streamlit as st
import gspread
import pandas as pd
import yfinance as yf
import json
from google.oauth2.service_account import Credentials
from datetime import datetime

# 1. 初始化 Google Sheets 連線
def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    # 這裡直接讀取您存在環境變數中的 JSON 鑰匙
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    # 使用您的試算表 ID
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

# 2. 核心功能：分析並更新時間
def run_analysis(email, stocks, row_index, sheet):
    st.write(f"🔍 正在為 {email} 分析個股...")
    results = []
    
    for stock in stocks:
        # 抓取資料計算 60SMA
        ticker = f"{stock}.TW"
        df = yf.download(ticker, period="6mo", progress=False)
        if df.empty:
            df = yf.download(f"{stock}.TWO", period="6mo", progress=False)
            
        if not df.empty:
            price = df['Close'].iloc[-1]
            ma60 = df['Close'].rolling(window=60).mean().iloc[-1]
            # 計算 60SMA 乖離率
            bias = ((price - ma60) / ma60) * 100
            results.append({"代號": stock, "現價": f"{price:.2f}", "60SMA乖離": f"{bias:.2f}%"})
    
    # 顯示結果
    st.table(pd.DataFrame(results))
    
    # 💡 關鍵步驟：寫回 Update_Time 到試算表 C 欄 (第 3 欄)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.update_cell(row_index, 3, now) 
    st.success(f"✅ 分析完成！已於試算表更新執行時間：{now}")

# 3. UI 介面
st.title("📈 股市戰略指揮中心")
user_email = st.text_input("請輸入您的註冊 Email：").strip()

if st.button("檢索資料並啟動分析"):
    sheet = init_sheet()
    data = sheet.get_all_records()
    df_all = pd.DataFrame(data)
    
    # 檢索帳號是否存在
    user_data = df_all[df_all['Email'] == user_email]
    
    if not user_data.empty:
        # 撈出 Stock_List 並處理成清單
        stock_str = str(user_data.iloc[0]['Stock_List'])
        stock_list = [s.strip() for s in stock_str.split(',')]
        row_index = user_data.index[0] + 2 # +2 是因為包含標題列且從 1 開始算
        
        st.info(f"📋 偵測到您的關注清單：{stock_str}")
        
        # 執行分析與資料回填
        run_analysis(user_email, stock_list, row_index, sheet)
    else:
        st.error("❌ 找不到此帳號，請確認 Email 是否正確。")
