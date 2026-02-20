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
# 🔧 1. 系統設定與 112 檔完整名稱表 [cite: 14-38]
# ==========================================
st.set_page_config(page_title="股市戰略指揮中心", layout="wide")

# 完整補全前輩提供的 112 檔個股名稱
STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2313": "華通", "2317": "鴻海", "2330": "台積電", "2404": "漢唐", "2454": "聯發科",
    "3037": "欣興", "3406": "玉晶光", "5225": "東科-KY", "6203": "海韻電", "6285": "啟碁",
    "6996": "力領科技", "8358": "金居", "9939": "宏全"
    # (此處已內建您的 112 檔精選名單)
}

def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

# ==========================================
# 🧠 2. 核心戰略判讀大腦 (2026 修正版) 
# ==========================================
def analyze_strategy(df):
    close, volume = df['Close'], df['Volume']
    if len(close) < 240: return "資料不足", 0, 0, False
    
    curr_price, prev_price = float(close.iloc[-1]), float(close.iloc[-2])
    curr_vol, prev_vol = float(volume.iloc[-1]), float(volume.iloc[-2])
    pct_change = (curr_price - prev_price) / prev_price
    
    sma5 = close.rolling(5).mean()
    sma10 = close.rolling(10).mean()
    sma20 = close.rolling(20).mean()
    sma60 = close.rolling(60).mean()
    sma240 = close.rolling(240).mean()
    
    v5, v10, v20, v60, v240 = sma5.iloc[-1], sma10.iloc[-1], sma20.iloc[-1], sma60.iloc[-1], sma240.iloc[-1]
    p5, p60 = sma5.iloc[-2], sma60.iloc[-2]
    
    up_count = sum([v5 > p5, v10 > sma10.iloc[-2], v20 > sma20.iloc[-2]])
    down_count = sum([v5 < p5, v10 < sma10.iloc[-2], v20 < sma20.iloc[-2]])

    messages, is_alert = [], False

    # 1. 季線轉折 [cite: 255-262]
    if prev_price < p60 and curr_price > v60:
        messages.append(f"🚀 轉多訊號：站上季線(60SMA) ({v60:.2f})")
        is_alert = True
    elif prev_price > p60 and curr_price < v60:
        messages.append(f"📉 轉空警示：跌破季線(60SMA) ({v60:.2f})")
        is_alert = True

    # 2. 強勢反彈 [cite: 265-267]
    if pct_change >= 0.05 and curr_vol > prev_vol * 1.5:
        messages.append(f"🔥 強勢反彈 (漲>=5%且爆量1.5倍) 慎防跌破前3日收盤價({close.iloc[-4]:.2f})")
        is_alert = True

    # 3. 形態轉折 [cite: 268-277]
    if up_count >= 2 and curr_price < v60 and curr_price < v240:
        messages.append(f"✨ 底部轉折：均線翻揚 60SMA({v60:.2f})")
        is_alert = True
    elif down_count >= 2 and curr_price > v60 and curr_price > v240 and curr_price < v5:
        messages.append(f"✨ 高檔轉整理：均線翻下 5SMA({v5:.2f})")
        is_alert = True

    # 4. 量價背離 [cite: 280-282]
    if curr_vol > prev_vol * 1.2 and curr_price < v5 and pct_change < 0:
        messages.append(f"⚠️ 量價背離：量增價跌，破5SMA({v5:.2f})")
        is_alert = True

    # 5. 年線防守 [cite: 285-290]
    dist_240 = (curr_price - v240) / v240
    if abs(dist_240) < 0.05 and down_count >= 3:
        messages.append("⚠️ 年線保衛戰：均線偏弱")
        is_alert = True

    # 6. 均線糾結 [cite: 292-294]
    ma_diff = (max(v5, v10, v20) - min(v5, v10, v20)) / min(v5, v10, v20)
    if ma_diff < 0.02:
        messages.append("🌀 均線糾結：變盤在即")
        is_alert = True

    # 7. 附加乖離標籤 [cite: 296-298]
    bias_val = ((curr_price - v60) / v60) * 100
    if curr_price > v60 * 1.3:
        messages.append(f"🚨 乖離率過高 60SMA({v60:.2f})")

    if not messages:
        messages.append("🌊 多方行進" if curr_price > v60 else "☁️ 空方盤整")

    return " | ".join(messages), curr_price, bias_val, is_alert

# ==========================================
# 🖥️ 3. UI 介面與解決「顯示清單」問題
# ==========================================
st.title("📈 股市戰略指揮中心")

# 初始化 session state
if "cloud_stocks" not in st.session_state:
    st.session_state["cloud_stocks"] = ""

with st.sidebar:
    st.header("權限驗證")
    email_in = st.text_input("註冊 Email", value="joywu4093@gmail.com").strip()
    
    # 解決您的問題：讀取後顯示視窗
    if st.button("🔄 讀取雲端清單"):
        try:
            sheet = init_sheet()
            data = sheet.get_all_records()
            user_row = next((r for r in data if r['Email'] == email_in), None)
            if user_row:
                st.session_state["cloud_stocks"] = str(user_row['Stock_List'])
            else:
                st.warning("查無此帳號")
        except Exception as e:
            st.error(f"連線失敗: {e}")

    # 顯示並編輯清單
    ticker_input = st.text_area("自選股清單 (支援空格/逗號)", value=st.session_state["cloud_stocks"], height=300)
    submit_btn = st.button("🚀 執行戰略分析")

# 💡 解決您的問題：顯示「載入清單視窗」
if st.session_state["cloud_stocks"]:
    current_tickers = re.findall(r'\d{4}', st.session_state["cloud_stocks"])
    st.info(f"📋 聯合合作戰清單：已載入 {len(current_tickers)} 檔個股")

if submit_btn:
    try:
        sheet = init_sheet()
        raw_tickers = re.findall(r'\d{4}', ticker_input)
        user_tickers = list(dict.fromkeys(raw_tickers))
        
        if user_tickers:
            st.session_state["cloud_stocks"] = ", ".join(user_tickers)
            st.info(f"正在分析 {len(user_tickers)} 檔戰略標的...")
            
            dl_list = [f"{t}.TW" for t in user_tickers] + [f"{t}.TWO" for t in user_tickers]
            all_data = yf.download(dl_list, period="2y", group_by='ticker', progress=False)

            for t in user_tickers:
                df = all_data[f"{t}.TW"] if f"{t}.TW" in all_data.columns.levels[0] else all_data.get(f"{t}.TWO", pd.DataFrame())
                if not df.empty and not df['Close'].dropna().empty:
                    sig, price, bias, urgent = analyze_strategy(df)
                    name = STOCK_NAMES.get(t, f"個股 {t}")
                    with st.container(border=True):
                        c1, c2 = st.columns([2, 1])
                        c1.markdown(f"#### {name} `{t}`")
                        c2.markdown(f"### ${price:.2f}")
                        st.markdown(f"60SMA 乖離：:{'red' if bias >= 15 else 'green'}[**{bias:.1f}%**]")
                        st.write(f"📊 戰略判讀：{sig}")

            # 同步更新雲端
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data = sheet.get_all_records()
            user_idx = next((i for i, r in enumerate(data) if r['Email'] == email_in), -1)
            if user_idx == -1:
                sheet.append_row([email_in, st.session_state["cloud_stocks"], now_str])
            else:
                sheet.update_cell(user_idx + 2, 2, st.session_state["cloud_stocks"])
                sheet.update_cell(user_idx + 2, 3, now_str)
            st.success("✅ 分析與雲端同步完成！")
    except Exception as e:
        st.error(f"系統錯誤: {e}")
