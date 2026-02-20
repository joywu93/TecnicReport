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
# 🔧 1. 系統設定與 112 檔完整對照表
# ==========================================
st.set_page_config(page_title="股市戰略 - 最終實戰版", layout="wide")

# 補全 112 檔公司名稱 (源自 App.py.docx)
STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2228": "劍麟", "2313": "華通", "2317": "鴻海", "2327": "國巨", "2330": "台積電",
    "2344": "華邦電", "2368": "金像電", "2376": "技嘉", "2377": "微星", "2379": "瑞昱",
    "2382": "廣達", "2383": "台光電", "2397": "友通", "2404": "漢唐", "2408": "南亞科",
    "2439": "美律", "2441": "超豐", "2449": "京元電子", "2454": "聯發科", "2493": "揚博",
    "2615": "萬海", "3005": "神基", "3014": "聯陽", "3017": "奇鋐", "3023": "信邦",
    "3030": "德律", "3037": "欣興", "3042": "晶技", "3078": "僑威", "3163": "波若威",
    "3167": "大量", "3217": "優群", "3219": "倚強科", "3227": "原相", "3231": "緯創",
    "3264": "欣銓", "3265": "台星科", "3303": "岱稜", "3357": "臺慶科", "3402": "漢科",
    "3406": "玉晶光", "3416": "融程電", "3441": "聯一光", "3450": "聯鈞", "3455": "由田",
    "3479": "安勤", "3483": "力致", "3484": "崧騰", "3515": "華擎", "3526": "凡甲",
    "3548": "兆利", "3570": "大塚", "3596": "智易", "3679": "新至陞", "3711": "日月光投控",
    "3712": "永崴投控", "4554": "橙的", "4760": "勤凱", "4763": "材料*-KY", "4766": "南寶",
    "4915": "致伸", "4953": "緯軟", "4961": "天鈺", "4979": "華星光", "5225": "東科-KY",
    "5236": "凌陽創新", "5284": "jpp-KY", "5388": "中磊", "5439": "高技", "5871": "中租-KY",
    "6104": "創惟", "6121": "新普", "6139": "亞翔", "6143": "振曜", "6158": "禾昌",
    "6176": "瑞儀", "6187": "萬潤", "6197": "佳必琪", "6203": "海韻電", "6221": "晉泰",
    "6227": "茂崙", "6257": "矽格", "6261": "久元", "6274": "台燿", "6278": "台表科",
    "6285": "啟碁", "6290": "良維", "6538": "倉和", "6579": "研揚", "6605": "帝寶",
    "6613": "朋億*", "6629": "泰金-KY", "6651": "全宇昕", "6667": "信紘科", "6768": "志強-KY",
    "6788": "華景電", "6894": "衛司特", "6951": "靑新-創", "6967": "汎瑋材料", "6996": "力領科技",
    "8081": "致新", "8358": "金居", "8432": "東生華", "8473": "山林水", "8938": "明安",
    "9914": "美利達", "9939": "宏全"
}

def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

def send_email_batch(sender, pwd, receivers, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"股市戰略中心 <{sender}>"
        msg['To'] = ", ".join(receivers)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, pwd)
            server.send_message(msg)
        return True
    except: return False

# ==========================================
# 🧠 2. 核心戰略判讀 (復刻 App.py.docx 邏輯)
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

    sma60 = close.rolling(60).mean().iloc[-1]
    bias_val = ((curr_price - sma60) / sma60) * 100
    
    high_240, low_240 = close.rolling(240).max().iloc[-1], close.rolling(240).min().iloc[-1]
    pos_rank = (curr_price - low_240) / (high_240 - low_240) if high_240 > low_240 else 0.5
    pos_msg = "⚠️ 年線高點 (M頭風險)" if pos_rank >= 0.95 else "✨ 年線低點 (W底機會)" if pos_rank <= 0.05 else ""

    messages, is_alert = [], False
    b_str = "🔥 乖離過大" if bias_val >= 30 else "🔸 乖離偏高" if bias_val >= 15 else ""

    if curr_vol > prev_vol * 1.5 and pct_change >= 0.04:
        messages.append("🌀 均線糾結突破 (爆量)")
        is_alert = True
    elif bias_val >= 15:
        messages.append(b_str)
        is_alert = True
    
    if not messages:
        messages.append("🌊 多方行進" if curr_price > sma60 else "☁️ 空方盤整")

    return " | ".join(messages), curr_price, bias_val, b_str, is_alert, pos_msg

# ==========================================
# 🖥️ 3. UI 介面與自動同步
# ==========================================
st.title("📈 股市戰略指揮中心")

# 初始化 session state 存放清單
if "stock_list_str" not in st.session_state:
    st.session_state["stock_list_str"] = ""

with st.sidebar:
    st.header("戰略帳號設定")
    email_in = st.text_input("註冊 Email", value="joywu4093@gmail.com").strip()
    
    # 💡 點擊「讀取雲端」按鈕先同步清單到框框
    if st.button("🔄 讀取雲端清單"):
        try:
            sheet = init_sheet()
            data = sheet.get_all_records()
            user_row = next((r for r in data if r['Email'] == email_in), None)
            if user_row:
                st.session_state["stock_list_str"] = str(user_row['Stock_List'])
                st.success("已從雲端載入清單！")
            else:
                st.warning("查無此 Email，請直接鍵入清單建立新帳號。")
        except Exception as e:
            st.error(f"連線失敗: {e}")

    # 顯示並允許編輯清單
    ticker_input = st.text_area("自選股清單", value=st.session_state["stock_list_str"], height=300)
    submit_btn = st.button("🚀 執行智能分析")

if submit_btn:
    try:
        sheet = init_sheet()
        raw_tickers = re.findall(r'\d{4}', ticker_input)
        user_tickers = list(dict.fromkeys(raw_tickers))
        
        if user_tickers:
            st.info(f"正在分析 {len(user_tickers)} 檔個股...")
            notify_list = []
            
            # 批次下載
            dl_list = [f"{t}.TW" for t in user_tickers] + [f"{t}.TWO" for t in user_tickers]
            all_data = yf.download(dl_list, period="2y", group_by='ticker', progress=False)

            for t in user_tickers:
                df = all_data[f"{t}.TW"] if f"{t}.TW" in all_data.columns.levels[0] else pd.DataFrame()
                if df.empty or df['Close'].dropna().empty:
                    df = all_data[f"{t}.TWO"] if f"{t}.TWO" in all_data.columns.levels[0] else pd.DataFrame()

                if not df.empty:
                    sig, price, bias, b_s, urgent, pos = analyze_strategy(df)
                    name = STOCK_NAMES.get(t, f"個股 {t}")
                    
                    with st.container(border=True):
                        c1, c2 = st.columns([2, 1])
                        c1.markdown(f"#### {name} `{t}`")
                        c2.markdown(f"### ${price:.2f}")
                        st.markdown(f"60SMA 乖離：:{'red' if bias >= 15 else 'green'}[**{bias:.1f}%**] | {pos}")
                        st.write(f"📊 戰略判讀：{sig}")
                        if urgent:
                            notify_list.append(f"【{name} {t}】${price:.2f} | {sig} {b_s}")

            # 💡 更新/註冊雲端
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            stock_list_str = ", ".join(user_tickers)
            data = sheet.get_all_records()
            user_idx = next((i for i, r in enumerate(data) if r['Email'] == email_in), -1)
            
            if user_idx == -1:
                sheet.append_row([email_in, stock_list_str, now_str])
                st.success("🎊 已建立新帳號並儲存清單。")
            else:
                sheet.update_cell(user_idx + 2, 2, stock_list_str)
                sheet.update_cell(user_idx + 2, 3, now_str)
                st.success("✅ 雲端清單同步完成。")

            # 💡 解決信件問題
            if notify_list:
                s, p = st.secrets["GMAIL_USER"], st.secrets["GMAIL_PASSWORD"]
                if send_email_batch(s, p, [email_in], "股市戰略警報", "\n\n".join(notify_list)):
                    st.toast("📧 重要警訊已寄出！")
                else:
                    st.error("信件寄送失敗，請檢查 Secrets 設定。")
        else:
            st.warning("請先輸入股票代號。")
    except Exception as e:
        st.error(f"系統錯誤: {e}")
