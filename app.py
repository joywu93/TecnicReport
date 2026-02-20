import streamlit as st
import gspread
import pandas as pd
import yfinance as yf
import json
import re
from google.oauth2.service_account import Credentials
from datetime import datetime

# 1. 初始化 Google Sheets 連線
def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

# 2. 核心戰略引擎：引用前輩的投資條件
def strategic_analysis(stock_list):
    results = []
    # 自動去重複 (解決重複顯示問題)
    unique_stocks = list(dict.fromkeys([s.strip() for s in stock_list if s.strip()]))
    
    progress_bar = st.progress(0)
    for i, stock in enumerate(unique_stocks):
        ticker_symbol = f"{stock}.TW"
        tk = yf.Ticker(ticker_symbol)
        df = tk.history(period="6mo")
        
        # 若上市抓不到，改抓上櫃
        if df.empty:
            ticker_symbol = f"{stock}.TWO"
            tk = yf.Ticker(ticker_symbol)
            df = tk.history(period="6mo")
            
        if not df.empty:
            try:
                # 獲取數值 (強制轉換 float)
                price = float(df['Close'].iloc[-1])
                ma60 = float(df['Close'].rolling(window=60).mean().iloc[-1])
                # 60SMA 乖離率公式
                bias = ((price - ma60) / ma60) * 100
                
                # 獲取殖利率資訊
                info = tk.info
                yield_rate = info.get('dividendYield', 0)
                yield_pct = yield_rate * 100 if yield_rate else 0
                
                # 💡 引用前輩的戰略判斷條件
                tactics = []
                if yield_pct > 4: tactics.append("💰 高殖利率") #
                if bias > 10: tactics.append("🔴 過熱")
                elif bias < -10: tactics.append("🔵 超跌")
                if bias < 5 and yield_pct > 4: tactics.append("🎯 戰略買點")
                
                results.append({
                    "代號": stock,
                    "現價": round(price, 2),
                    "60SMA乖離": f"{bias:.2f}%",
                    "殖利率": f"{yield_pct:.2f}%",
                    "戰略提示": " | ".join(tactics) if tactics else "⚪ 觀察中"
                })
            except:
                continue
        progress_bar.progress((i + 1) / len(unique_stocks))
    return results

# 3. 介面設定
st.set_page_config(page_title="股市戰略指揮中心", layout="wide")
st.title("📈 股市戰略指揮中心")

# 使用者登入區
with st.sidebar:
    st.header("👤 權限驗證")
    user_email = st.text_input("註冊 Email：", value="joywu4093@gmail.com").strip()

# 💡 功能 1：手動輸入區 (支援空格、逗號、分號)
col1, col2 = st.columns([2, 1])
with col1:
    manual_input = st.text_area("➕ 手動新增個股 (代號間請用空格或逗號分開)：", placeholder="例如: 2330 2454 3037")

if st.button("🚀 執行智能戰略分析"):
    try:
        sheet = init_sheet()
        data = sheet.get_all_records()
        df_all = pd.DataFrame(data)
        user_row = df_all[df_all['Email'] == user_email]
        
        if not user_row.empty:
            # 💡 功能 3：強健解析雲端清單
            sheet_stocks_raw = str(user_row.iloc[0]['Stock_List'])
            sheet_stocks = [s.strip() for s in re.split(r'[,;，；\s]+', sheet_stocks_raw) if s.strip()]
            
            # 整合手動輸入
            manual_stocks = [s.strip() for s in re.split(r'[,;，；\s]+', manual_input) if s.strip()]
            final_list = sheet_stocks + manual_stocks
            
            st.info(f"📋 聯合作戰清單：已載入 {len(set(final_list))} 檔個股")
            
            # 執行分析
            analysis_data = strategic_analysis(final_list)
            
            if analysis_data:
                # 💡 功能 2：訊息通知與報表
                st.subheader("📊 戰略評估結果")
                st.table(pd.DataFrame(analysis_data))
                
                # 針對前輩 20% 獲利目標的提示
                st.write("---")
                st.markdown("💡 **戰略提醒**：若個股利潤已達 **20%**，請考慮分批獲利了結。")
                
                # 更新雲端時間
                row_idx = int(user_row.index[0]) + 2
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sheet.update_cell(row_idx, 3, now_str)
                st.success(f"✅ 更新成功！雲端同步時間：{now_str}")
        else:
            st.error("❌ 找不到此帳號，請確認 Email 是否正確。")
    except Exception as e:
        st.error(f"❌ 系統異常：{str(e)}")
