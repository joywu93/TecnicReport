import os, gspread, json, re, smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. 112 檔名單 ---
STOCK_NAMES = {"1464":"得力","1517":"利奇","1522":"堤維西","1597":"直得","1616":"億泰","2228":"劍麟","2313":"華通","2317":"鴻海","2327":"國巨","2330":"台積電","2344":"華邦電","2368":"金像電","2376":"技嘉","2377":"微星","2379":"瑞昱","2382":"廣達","2383":"台光電","2397":"友通","2404":"漢唐","2408":"南亞科","2439":"美律","2441":"超豐","2449":"京元電子","2454":"聯發科","2493":"揚博","2615":"萬海","3005":"神基","3014":"聯陽","3017":"奇鋐","3023":"信邦","3030":"德律","3037":"欣興","3042":"晶技","3078":"僑威","3163":"波若威","3167":"大量","3217":"優群","3219":"倚強科","3227":"原相","3231":"緯創","3264":"欣銓","3265":"台星科","3303":"岱稜","3357":"臺慶科","3402":"漢科","3406":"玉晶光","3416":"融程電","3441":"聯一光","3450":"聯鈞","3455":"由田","3479":"安勤","3483":"力致","3484":"崧騰","3515":"華擎","3526":"凡甲","3548":"兆利","3570":"大塚","3596":"智易","3679":"新至陞","3711":"日月光投控","3712":"永崴投控","4554":"橙的","4760":"勤凱","4763":"材料*-KY","4766":"南寶","4915":"致伸","4953":"緯軟","4961":"天鈺","4979":"華星光","5225":"東科-KY","5236":"力領科技","5284":"jpp-KY","5388":"中磊","5439":"高技","5871":"中租-KY","6104":"創惟","6121":"新普","6139":"亞翔","6143":"振曜","6158":"禾昌","6176":"瑞儀","6187":"萬潤","6197":"佳必琪","6203":"海韻電","6221":"晉泰","6227":"茂崙","6257":"矽格","6261":"久元","6274":"台燿","6278":"台表科","6285":"啟碁","6290":"良維","6538":"倉和","6579":"研揚","6605":"帝寶","6613":"朋億*","6629":"泰金-KY","6651":"全宇昕","6667":"信紘科","6768":"志強-KY","6788":"華景電","6894":"衛司特","6951":"靑新-創","6967":"汎瑋材料","6996":"力領科技","8081":"致新","8358":"金居","8432":"東生華","8473":"山林水","8938":"明安","9914":"美利達","9939":"宏全"}

# --- 2. 戰略分析邏輯 (💡此處全選複製 app.py 的 analyze_strategy 函式) ---
def analyze_strategy(df):
    # (此處與 app.py 的 analyze_strategy 完全相同，為了代碼穩定，請前輩務必同步複製)
    # ... (略，請參考上方 app.py 之內容) ...

def run_batch():
    try:
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
        client = gspread.authorize(Credentials.from_service_account_info(json.loads(creds_json), 
                 scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))
        sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
        
        for row in sheet.get_all_records():
            email = row.get('Email')
            tickers = re.findall(r'\d{4}', str(row.get('Stock_List', '')))
            if not email: continue
            
            # 💡 強制測試行，確保休市時也能確認電路正常
            notify_list = [f"✅ 通訊測試成功！執行時間：{datetime.now().strftime('%H:%M:%S')}"]
            for t in tickers:
                df = yf.download(f"{t}.TW", period="2y", progress=False)
                if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
                if not df.empty:
                    sig, p, s60, b, im = analyze_strategy(df)
                    if im: notify_list.append(f"【{STOCK_NAMES.get(t, t)}】${p:.2f} | {sig}")

            msg = MIMEText("\n\n".join(notify_list))
            msg['Subject'] = f"📈 戰略巡航回報 - {datetime.now().strftime('%m/%d')}"
            msg['From'], msg['To'] = sender, email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(sender, pwd); server.send_message(msg)
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    run_batch()
