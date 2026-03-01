import streamlit as st
import yfinance as yf
import pandas as pd
import gspread, re, smtplib, json
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. 112 檔完整名單 ---
STOCK_NAMES = {"1464":"得力","1517":"利奇","1522":"堤維西","1597":"直得","1616":"億泰","2228":"劍麟","2313":"華通","2317":"鴻海","2327":"國巨","2330":"台積電","2344":"華邦電","2368":"金像電","2376":"技嘉","2377":"微星","2379":"瑞昱","2382":"廣達","2383":"台光電","2397":"友通","2404":"漢唐","2408":"南亞科","2439":"美律","2441":"超豐","2449":"京元電子","2454":"聯發科","2493":"揚博","2615":"萬海","3005":"神基","3014":"聯陽","3017":"奇鋐","3023":"信邦","3030":"德律","3037":"欣興","3042":"晶技","3078":"僑威","3163":"波若威","3167":"大量","3217":"優群","3219":"倚強科","3227":"原相","3231":"緯創","3264":"欣銓","3265":"台星科","3303":"岱稜","3357":"臺慶科","3402":"漢科","3406":"玉晶光","3416":"融程電","3441":"聯一光","3450":"聯鈞","3455":"由田","3479":"安勤","3483":"力致","3484":"崧騰","3515":"華擎","3526":"凡甲","3548":"兆利","3570":"大塚","3596":"智易","3679":"新至陞","3711":"日月光投控","3712":"永崴投控","4554":"橙的","4760":"勤凱","4763":"材料*-KY","4766":"南寶","4915":"致伸","4953":"緯軟","4961":"天鈺","4979":"華星光","5225":"東科-KY","5236":"力領科技","5284":"jpp-KY","5388":"中磊","5439":"高技","5871":"中租-KY","6104":"創惟","6121":"新普","6139":"亞翔","6143":"振曜","6158":"禾昌","6176":"瑞儀","6187":"萬潤","6197":"佳必琪","6203":"海韻電","6221":"晉泰","6227":"茂崙","6257":"矽格","6261":"久元","6274":"台燿","6278":"台表科","6285":"啟碁","6290":"良維","6538":"倉和","6579":"研揚","6605":"帝寶","6613":"朋億*","6629":"泰金-KY","6651":"全宇昕","6667":"信紘科","6768":"志強-KY","6788":"華景電","6894":"衛司特","6951":"靑新-創","6967":"汎瑋材料","6996":"力領科技","8081":"致新","8358":"金居","8432":"東生華","8473":"山林水","8938":"明安","9914":"美利達","9939":"宏全"}

# --- 2. 戰略分析邏輯 (遵照條件判讀.docx) ---
def analyze_strategy(df):
    try:
        if df.empty or len(df) < 240: return "資料不足", 0, 0, 0, False
        df.columns = df.columns.get_level_values(0)
        close, lows, highs, volume = df['Close'].astype(float).dropna(), df['Low'].astype(float).dropna(), df['High'].astype(float).dropna(), df['Volume'].astype(float).dropna()
        curr_p, prev_p, p3_close = float(close.iloc[-1]), float(close.iloc[-2]), float(close.iloc[-4])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        
        ma5, ma10, ma20, ma60, ma240 = close.rolling(5).mean(), close.rolling(10).mean(), close.rolling(20).mean(), close.rolling(60).mean(), close.rolling(240).mean()
        v5, v10, v20, v60, v240 = float(ma5.iloc[-1]), float(ma10.iloc[-1]), float(ma20.iloc[-1]), float(ma60.iloc[-1]), float(ma240.iloc[-1])
        bias = ((curr_p - v60) / v60) * 100
        msg, is_mail = [], False

        # 戰略 1：季線轉折
        if prev_p < v60 and curr_p > v60: msg.append(f"🚀 轉多訊號：站上季線({curr_p:.1f})"); is_mail = True
        elif prev_p > v60 and curr_p < v60: msg.append(f"📉 轉空警示：跌破季線({curr_p:.1f})"); is_mail = True
        
        # 戰略 2：強勢反彈
        if (curr_p - prev_p)/prev_p >= 0.05 and curr_v > prev_v * 1.5: 
            msg.append(f"🔥 強勢反彈，慎防破 {p3_close:.1f}"); is_mail = True

        # 戰略 3：底部/高檔轉折
        up_c = sum([ma5.diff().iloc[-1]>0, ma10.diff().iloc[-1]>0, ma20.diff().iloc[-1]>0])
        dn_c = sum([ma5.diff().iloc[-1]<0, ma10.diff().iloc[-1]<0, ma20.diff().iloc[-1]<0])
        if up_c >= 2 and curr_p < v60 and curr_p < v240: msg.append(f"✨ 底部轉折：{up_c}均線翻揚"); is_mail = True
        elif dn_c >= 2 and curr_p > v60 and curr_p > v240 and curr_p < v5: msg.append(f"✨ 高檔轉整理：{dn_c}均線翻下"); is_mail = True

        # 戰略 4：量價背離
        if curr_v > prev_v * 1.2 and curr_p < v5 and curr_p < prev_p:
            msg.append(f"⚠️ 量價背離 (基準 {p3_close:.1f})"); is_mail = True

        # 戰略 5：年線保衛戰
        if abs(curr_p - v240)/v240 < 0.05: msg.append("⚠️ 年線保衛戰"); is_mail = True

        # 🏆 W底偵測
        r_l, r_h = lows.tail(60), highs.tail(60)
        t_a_v, t_a_i = float(r_l.min()), r_l.idxmin()
        post_a = r_h.loc[t_a_i:]
        if len(post_a) > 5:
            w_p_v, w_p_i = float(post_a.max()), post_a.idxmax()
            post_b = lows.loc[w_p_i:]
            if len(post_b) > 3:
                t_c_v = float(post_b.min())
                if t_c_v >= (t_a_v * 0.97) and (w_p_v - t_a_v)/t_a_v >= 0.10:
                    status = "✨ W底突破" if curr_p > w_p_v else "✨ W底機會"
                    msg.append(f"{status}(距領口 {((w_p_v-curr_p)/w_p_v)*100:.1f}%)"); is_mail = True

        if not msg: msg.append("🌊 多方行進" if curr_p > v60 else "☁ 空方盤整")
        return " | ".join(msg), curr_p, v60, bias, is_mail
    except: return "分析錯誤", 0, 0, 0, False

# --- 3. UI 介面 ---
st.title("📈 股市戰略指揮中心")
with st.sidebar:
    st.header("權限驗證")
    email_in = st.text_input("通知 Email", value="joywu4093@gmail.com").strip()
    if st.button("🔄 讀取雲端清單"):
        try:
            scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            creds = Credentials.from_service_account_info(json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"]), scopes=scope)
            sheet = gspread.authorize(creds).open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
            user = next((r for r in sheet.get_all_records() if r['Email'] == email_in), None)
            if user: st.session_state["stocks"] = str(user['Stock_List'])
        except: st.error("雲端連線失敗")
    ticker_input = st.text_area("自選股清單", value=st.session_state.get("stocks", ""), height=300)
    submit_btn = st.button("🚀 執行分析並同步雲端")

if submit_btn:
    tickers = re.findall(r'\d{4}', ticker_input)
    st.session_state["stocks"] = ", ".join(tickers)
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"]), scopes=scope)
        sheet = gspread.authorize(creds).open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
        cell = sheet.find(email_in)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sheet.update_cell(cell.row, cell.col + 1, ", ".join(tickers))
        sheet.update_cell(cell.row, cell.col + 2, now_str)
        st.success(f"✅ 雲端同步成功 ({now_str})")
    except: st.warning("雲端同步失敗")

    for t in tickers:
        df = yf.download(f"{t}.TW", period="2y", progress=False)
        if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
        if not df.empty:
            sig, p, s60, b, im = analyze_strategy(df)
            with st.container(border=True):
                st.markdown(f"#### {STOCK_NAMES.get(t, t)} {t} - ${p:.2f} 乖離 {b:.1f}%")
                st.write(sig)
