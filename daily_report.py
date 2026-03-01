import os, gspread, json, re, smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. 112 檔完整名單 (確保名稱對位，不再顯示「個股」) ---
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
    "5236": "力領科技", "5284": "jpp-KY", "5388": "中磊", "5439": "高技", "5871": "中租-KY",
    "6104": "創惟", "6121": "新普", "6139": "亞翔", "6143": "振曜", "6158": "禾昌",
    "6176": "瑞儀", "6187": "萬潤", "6197": "佳必琪", "6203": "海韻電", "6221": "晉泰",
    "6227": "茂崙", "6257": "矽格", "6261": "久元", "6274": "台燿", "6278": "台表科",
    "6285": "啟碁", "6290": "良維", "6538": "倉和", "6579": "研揚", "6605": "帝寶",
    "6613": "朋億*", "6629": "泰金-KY", "6651": "全宇昕", "6667": "信紘科", "6768": "志強-KY",
    "6788": "華景電", "6894": "衛司特", "6951": "靑新-創", "6967": "汎瑋材料", "6996": "力領科技",
    "8081": "致新", "8358": "金居", "8432": "東生華", "8473": "山林水", "8938": "明安",
    "9914": "美利達", "9939": "宏全"
}

# --- 2. 核心大腦 (解決 slice indexing 與 $0.00 問題) ---
def analyze_strategy(df):
    try:
        if df.empty or len(df) < 240: return None, False
        # 💡 解決 image_194cfa.png 的關鍵：強制拍平標籤
        df.columns = df.columns.get_level_values(0)
        close = df['Close'].astype(float).dropna()
        highs = df['High'].astype(float).dropna()
        lows = df['Low'].astype(float).dropna()
        volume = df['Volume'].astype(float).dropna()
        
        curr_p, prev_p = float(close.iloc[-1]), float(close.iloc[-2])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        p3_close = float(close.iloc[-4])
        
        ma5 = close.rolling(5).mean(); v5 = float(ma5.iloc[-1])
        ma60 = close.rolling(60).mean(); v60 = float(ma60.iloc[-1])
        ma240 = close.rolling(240).mean(); v240 = float(ma240.iloc[-1])
        
        msg, is_mail = [], False

        # W底偵測 (60日)
        r_l, r_h = lows.tail(60), highs.tail(60)
        t_a_v = float(r_l.min()); t_a_i = r_l.idxmin()
        post_a = r_h.loc[t_a_i:]
        if len(post_a) > 5:
            w_p_v = float(post_a.max()); w_p_i = post_a.idxmax()
            post_b = lows.loc[w_p_i:]
            if len(post_b) > 3:
                t_c_v = float(post_b.min())
                # 💡 右底不低於左底 3%
                if t_c_v >= (t_a_v * 0.97) and (w_p_v - t_a_v)/t_a_v >= 0.10:
                    status = "✨ W底突破" if curr_p > w_p_v else "✨ W底機會"
                    msg.append(f"{status}: 領口距 {((w_p_v-curr_p)/w_p_v)*100:.1f}%")
                    is_mail = True

        # 7 大戰略
        if prev_p < v60 and curr_p > v60: msg.append("🚀 轉多：站上季線"); is_mail = True
        if (curr_p - prev_p)/prev_p >= 0.05 and curr_v > prev_v * 1.5: msg.append("🔥 強勢反彈"); is_mail = True
        if curr_v > prev_v * 1.2 and curr_p < v5 and curr_p < prev_p: msg.append("⚠️ 量價背離"); is_mail = True

        return " | ".join(msg), is_mail
    except: return None, False

def run_batch():
    try:
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
        if not creds_json or not sender: return
        
        creds = Credentials.from_service_account_info(json.loads(creds_json), 
                 scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
        
        for row in sheet.get_all_records():
            email, stocks = row.get('Email'), str(row.get('Stock_List', ''))
            tickers = re.findall(r'\d{4}', stocks)
            if not email or not tickers: continue
            
            notify_list = []
            for t in tickers:
                df = yf.download(f"{t}.TW", period="2y", progress=False)
                if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
                
                sig, im = analyze_strategy(df)
                if im:
                    name = STOCK_NAMES.get(t, f"個股 {t}")
                    notify_list.append(f"【{name} {t}】${df['Close'].iloc[-1].values[0]:.2f} | {sig}")
            
            if notify_list:
                msg = MIMEText("\n\n".join(notify_list))
                msg['Subject'] = f"📈 戰略警報 - {datetime.now().strftime('%m/%d %H:%M')}"
                msg['From'], msg['To'] = sender, email
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(sender, pwd); server.send_message(msg)
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    run_batch()
