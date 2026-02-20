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
        ticker = f"{stock.strip()}.TW"
        df = yf.download(ticker, period="6mo", progress=False)
        if df.empty:
            df = yf.download(f"{stock.strip()}.TWO", period="6mo", progress=False)
            
        if not df.empty:
            try:
                # 💡 關鍵修正：強制轉為 float 避免 TypeError
                current_price = float(df['Close'].iloc[-1])
                ma60 = float(df['Close'].rolling(window=60).mean().iloc[-1])
                
                # 計算 60SMA 乖離率
                bias = ((current_price - ma60) / ma60) * 100
                
                results.append({
                    "代號": stock.strip(),
                    "現價": f"{current_price:.2f}",
                    "60SMA乖離": f"{bias:.2f}%"
                })
            except:
                continue
    
    # 顯示分析結果表格
    if results:
        st.subheader("📊 智能分析結果")
        st.table(pd.DataFrame(results))
        
        # 💡 寫回 Update_Time 到試算表第 3 欄 (C 欄)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.update_cell(row_index, 3, now_str) 
        st.success(f"✅ 分析完成！已同步更新雲端 Update_Time：{now_str}")
    else:
        st.warning("⚠️ 無法獲取個股資料，請檢查代號是否正確。")

# 3. UI 介面
st.set_page_config(page_title="股市戰略指揮中心", layout="wide")
st.title("📈 股市戰略指揮中心")

user_email = st.text_input("請輸入您的註冊 Email：", value="joywu4093@gmail.com").strip()

if st.button("檢索資料並啟動分析"):
    try:
        sheet = init_sheet()
        data = sheet.get_all_records()
        df_all = pd.DataFrame(data)
        
        # 檢索帳號
        user_data = df_all[df_all['Email'] == user_email]
        
        if not user_data.empty:
            # 撈出 Stock_List
            stock_str = str(user_data.iloc[0]['Stock_List'])
            st.info(f"📋 偵測到您的關注清單：{stock_str}")
            
            # 處理清單並執行
            stock_list = stock_str.split(',')
            # 計算 Excel 行索引 (包含標題列且從 1 開始)
            row_idx = int(user_data.index[0]) + 2 
            
            run_analysis(user_email, stock_list, row_idx, sheet)
        else:
            st.error("❌ 找不到此帳號，請確認 Email 是否已註冊於試算表中。")
    except Exception as e:
        st.error(f"🔌 連線異常：{str(e)}")
