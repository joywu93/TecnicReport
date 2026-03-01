import os, gspread, json, re, smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. 112 檔完整名單 (全數寫入，不再省略) ---
STOCK_NAMES = {"1464":"得力","1517":"利奇","1522":"堤維西","1597":"直得","1616":"億泰","2228":"劍麟","2313":"華通","2317":"鴻海","2327":"國巨","2330":"台積電","2344":"華邦電","2368":"金像電","2376":"技嘉","2377":"微星","2379":"瑞昱","2382":"廣達","2383":"台光電","2397":"友通","2404":"漢唐","2408":"南亞科","2439":"美律","2441":"超豐","2449":"京元電子","2454":"聯發科","2493":"揚博","2615":"萬海","3005":"神基","3014":"聯陽","3017":"奇鋐","3023":"信邦","3030":"德律","3037":"欣興","3042":"晶技","3078":"僑威","3163":"波若威","3167":"大量","3217":"優群","3219":"倚強科","3227":"原相","3231":"緯創","3264":"欣銓","3265":"台星科","3303":"岱稜","3357":"臺慶科","3402":"漢科","3406":"玉晶光","3416":"融程電","3441":"聯一光","3450":"聯鈞","3455":"由田","3479":"安勤","3483":"力致","3484":"崧騰","3515":"華擎","3526":"凡甲","3548":"兆利","3570":"大塚","3596":"智易","3679":"新至陞","3711":"日月光投控","3712":"永崴投控","4554":"橙的","4760":"勤凱","4763":"材料*-KY","4766":"南寶","4915":"致伸","4953":"緯軟","4961":"天鈺","4979":"華星光","5225":"東科-KY","5236":"力領科技","5284":"jpp-KY","5388":"中磊","5439":"高技","5871":"中租-KY","6104":"創惟","6121":"新普","6139":"亞翔","6143":"振曜","6158":"禾昌","6176":"瑞儀","6187":"萬潤","6197":"佳必琪","6203":"海韻電","6221":"晉泰","6227":"茂崙","6257":"矽格","6261":"久元","6274":"台燿","6278":"台表科","6285":"啟碁","6290":"良維","6538":"倉和","6579":"研揚","6605":"帝寶","6613":"朋億*","6629":"泰金-KY","6651":"全宇昕","6667":"信紘科","6768":"志強-KY","6788":"華景電","6894":"衛司特","6951":"靑新-創","6967":"汎瑋材料","6996":"力領科技","8081":"致新","8358":"金居","8432":"東生華","8473":"山林水","8938":"明安","9914":"美利達","9939":"宏全"}

# --- 2. 戰略分析大腦 (完整寫入，包含精確價位) ---
def analyze_strategy(df, t):
    try:
        if df.empty or len(df) < 240: return "資料不足", 0, 0, 0, False
        df.columns = df.columns.get_level_values(0)
        close = df['Close'].astype(float).dropna()
        highs = df['High'].astype(float).dropna()
        lows = df['Low'].astype(float).dropna()
        volume = df['Volume'].astype(float).dropna()
        
        curr_p, prev_p, p3_close = float(close.iloc[-1]), float(close.iloc[-2]), float(close.iloc[-4])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        ma5, ma10, ma20, ma60, ma240 = close.rolling(5).mean(), close.rolling(10).mean(), close.rolling(20).mean(), close.rolling(60).mean(), close.rolling(240).mean()
        v5, v10, v20, v60, v240 = float(ma5.iloc[-1]), float(ma10.iloc[-1]), float(ma20.iloc[-1]), float(ma60.iloc[-1]), float(ma240.iloc[-1])
        bias = ((curr_p - v60) / v60) * 100
        msg, is_mail = [], False

        # 季線與強勢戰略
        if prev_p < v60 and curr_p > v60: msg.append(f"🚀 轉多：站上季線({curr_p:.1f})"); is_mail = True
        elif prev_p > v60 and curr_p < v60: msg.append(f"📉 轉空：跌破季線({curr_p:.1f})"); is_mail = True
        if (curr_p - prev_p)/prev_p >= 0.05 and curr_v > prev_v * 1.5: 
            msg.append(f"🔥 強勢反彈：慎防跌破 {p3_close:.1f}"); is_mail = True
        
        # 底部轉折
        up_tags = []
        if ma5.diff().iloc[-1] > 0: up_tags.append(f"5SMA({v5:.1f})")
        if ma10.diff().iloc[-1] > 0: up_tags.append(f"10SMA({v10:.1f})")
        if len(up_tags) >= 2 and curr_p < v60: msg.append(f"✨ 底部轉折：{'/'.join(up_tags)}翻揚"); is_mail = True

        # W底中間峰值 與 M頭中間谷底 (精確位)
        r_l, r_h = lows.tail(60), highs.tail(60)
        t_a_v, t_a_i = float(r_l.min()), r_l.idxmin()
        post_a = r_h.loc[t_a_i:]
        if len(post_a) > 5:
            w_peak_v, w_peak_i = float(post_a.max()), post_a.idxmax()
            post_b = lows.loc[w_peak_i:]
            if len(post_b) > 3:
                t_c_v = float(post_b.min())
                if t_c_v >= (t_a_v * 0.97) and (w_peak_v - t_a_v)/t_a_v >= 0.10:
                    st_w = "✨ W底突破" if curr_p > w_peak_v else "✨ W底機會"
                    msg.append(f"{st_w}: 中間峰值({w_peak_v:.1f}) 距領口{((w_peak_v-curr_p)/w_peak_v)*100:.1f}%"); is_mail = True

        if t in ["2408", "2344"] and curr_p > v60:
            m_pk_a_v, m_pk_a_i = float(r_h.max()), r_h.idxmax()
            post_pk_a = r_l.loc[m_pk_a_i:]
            if len(post_pk_a) > 5:
                m_trough_v, m_trough_i = float(post_pk_a.min()), post_pk_a.idxmin()
                post_tr = r_h.loc[m_trough_i:]
                if len(post_tr) > 3:
                    m_pk_b_v = float(post_tr.max())
                    if abs(m_pk_a_v - m_pk_b_v)/m_pk_a_v < 0.05:
                        msg.append(f"⚠️ M頭警示: 中間谷底價({m_trough_v:.1f}) 提防跌破頸線"); is_mail = True

        # 壓力標記
        p_high_20 = float(highs.tail(20).max())
        if curr_p < v240:
            msg.append(f"❄️ 空方反彈中: 壓力240SMA({v240:.1f})")
        elif not any("底" in s or "頭" in s for s in msg):
            msg.append(f"🌊 多方行進: 近期壓力高點({p_high_20:.1f})")

        return " | ".join(msg), curr_p, v60, bias, is_mail
    except: return "分析錯誤", 0, 0, 0, False

# --- 3. 發報機主程式 ---
def run_batch():
    try:
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
        if not sender or not pwd: return
        
        client = gspread.authorize(Credentials.from_service_account_info(json.loads(creds_json), 
                 scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))
        sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
        
        for row in sheet.get_all_records():
            email = row.get('Email')
            tickers = re.findall(r'\d{4}', str(row.get('Stock_List', '')))
            if not email: continue
            
            # 強制連線報告：保證一定發信
            notify_list = [f"✅ 股市戰略偵察機連線成功！測試時間：{datetime.now().strftime('%H:%M:%S')}"]
            for t in tickers:
                df = yf.download(f"{t}.TW", period="2y", progress=False)
                if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
                if not df.empty:
                    sig, p, s60, b, im = analyze_strategy(df, t)
                    if im: notify_list.append(f"【{STOCK_NAMES.get(t, t)}】${p:.2f} | {sig}")

            msg = MIMEText("\n\n".join(notify_list))
            msg['Subject'] = f"📈 戰略巡航回報 - {datetime.now().strftime('%m/%d')}"
            msg['From'], msg['To'] = sender, email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(sender, pwd)
                server.send_message(msg)
                print(f"Mail sent to {email}")
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    run_batch()
