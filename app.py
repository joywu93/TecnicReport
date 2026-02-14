import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time

# --- 1. 中文名稱對照表 (擴充版) ---
STOCK_NAMES = {
    "2330": "台積電", "2317": "鴻海", "6203": "海韻電", 
    "3570": "大塚", "4766": "南寶", "NVDA": "輝達",
    "2313": "華通", "2454": "聯發科", "2303": "聯電",
    "2603": "長榮", "2609": "陽明", "2615": "萬海",
    "2323": "中環", "2451": "創見", "6229": "研通",
    "4763": "材料-KY", "1522": "堤維西", "2404": "漢唐",
    "6788": "華景電", "2344": "華邦電", "1519": "華城",
    "1513": "中興電", "3231": "緯創", "3035": "智原"
}

# --- 2. Email 發送函數 ---
def send_email_batch(sender, pwd, receivers, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"股市監控小幫手 <{sender}>"
        msg['To'] = ", ".join(receivers)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, pwd)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

st.set_page_config(page_title="專業股市趨勢判讀系統", layout="wide")
st.title("📈 股市專業趨勢判讀 & 智能通知系統")

# 後台 Secrets 讀取
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

st.sidebar.header("👤 使用者設定")
friend_email = st.sidebar.text_input("接收通知信箱", placeholder="請輸入您的 Email")
ticker_input = st.sidebar.text_area("自選股清單", "2330, 2317, 2323, 2451, 6229, 4763, 1522, 2404, 6788, 2344")
run_button = st.sidebar.button("立即執行判讀")

# --- 3. 核心判讀邏輯函數 ---
def check_market_status(curr_price, prev_price, sma, prev_sma, curr_vol, prev_vol):
    # 解包均線數據
    s5, s10, s20, s60, s240 = sma[5], sma[10], sma[20], sma[60], sma[240]
    
    # 計算均線趨勢 (True為向下)
    trend_down = {
        5: sma[5] < prev_sma[5],
        10: sma[10] < prev_sma[10],
        20: sma[20] < prev_sma[20],
        60: sma[60] < prev_sma[60]
    }
    
    # 計算 5/10/20 下彎的數量
    short_down_count = sum([trend_down[5], trend_down[10], trend_down[20]])
    # 計算 5/10/20/60 下彎的數量
    all_down_count = short_down_count + (1 if trend_down[60] else 0)

    status = "趨勢不明/盤整中"
    need_notify = False
    
    # 距離 60SMA 的差距百分比
    dist_60 = abs(curr_price - s60) / s60
    # 距離 20SMA 的差距百分比
    dist_20 = abs(curr_price - s20) / s20

    # === 判斷多方市場 (收盤 > 240SMA) ===
    if curr_price > s240:
        
        # --- 優先判斷：特殊修正條件 (User Request 1, 2, 3) ---
        
        # 1.) 股價回測 60SMA (差距<3%) 且 5/10/20 有2條以上趨勢向下
        if dist_60 < 0.03 and short_down_count >= 2:
            if curr_price < sma[5]: # 且股價在5日線下
                 status = "⚠️ 修正壓力大，均線下彎，回測季線(60SMA)支撐"
            else:
                 status = "⚠️ 修正壓力漸增，留意季線(60SMA)支撐"
            need_notify = True
            return status, need_notify

        # 2.) 股價雖大於均線，但多數均線(3條以上)趨勢向下，且量能無爆發 (量 < 1.5倍)
        # (如 6229, 4763, 1522)
        if (curr_price > s5 or curr_price > s10) and all_down_count >= 3 and curr_vol < prev_vol * 1.5:
            status = "☁️ 空方趨勢不明/盤整中 (均線多數下彎)"
            return status, need_notify # 不一定要通知，視盤整而定

        # 3.a) 股價近 60SMA 且 2條以上均線向下 -> 中多整理 (如 2404, 6788)
        if dist_60 < 0.05 and short_down_count >= 2:
            status = "☕ 中多整理 (均線糾結/下彎)"
            return status, need_notify

        # 3.b) 股價近 20SMA 且 20>60>240 -> 中多高檔整理 (如 2344)
        if dist_20 < 0.05 and s20 > s60 > s240:
            status = "☕ 中多高檔整理 (均線糾結)"
            return status, need_notify

        # --- 以下為原有的標準多方邏輯 ---

        # 多頭排列
        if s5 > s10 > s20 > s60 > s240:
            if curr_price > s5:
                if curr_price >= s60 * 1.3:
                    status = "⚠️ 中多持續但短線乖離過大 (>60SMA 30%)"
                    need_notify = True
                else:
                    status = "📈 中多持續趨勢向上"
            else: # 破5日線
                if curr_vol > prev_vol * 1.5:
                    status = "⚠️ 中多高檔震盪，短線注意"
                    need_notify = True
                elif curr_vol > prev_vol * 1.4:
                    status = "📉 中多短空，量價背離，測試10SMA支撐"
                    need_notify = True
                else:
                    status = "☕ 中多高檔整理"

        # 短線轉弱
        elif s5 < s10 and s10 > s20 > s60 > s240:
            status = "📉 中多短空，測試20SMA支撐"
            if curr_price < s5 and curr_vol > prev_vol * 1.4:
                need_notify = True

        # 回測季線
        elif s5 < s10 < s20 and s20 > s60 > s240:
             status = "📉 中多短中空，測試60SMA支撐"
             if curr_price < s5 and curr_vol > prev_vol * 1.4:
                 status += " (量價背離)"
                 need_notify = True

        # 探底
        elif s5 < s10 < s20 < s60 and s60 > s240:
            if curr_vol > prev_vol * 1.4 and curr_price > prev_price:
                status = "✨ 短中空量價配合有亮點，測試240SMA支撐"
                need_notify = True
            else:
                status = "📉 短中空測試240SMA支撐 (繼續探底)"

    # === 判斷空方市場 (收盤 < 240SMA) ===
    else:
        # 空頭排列
        if s5 < s10 < s20 < s60 < s240:
            if curr_price > sma[3] and curr_vol > prev_vol * 1.5: # 修正: 這裡用 sma[3] 需在外面傳入，暫用 sma[5] 替代或在 analyze 補算
                 status = "✨ 空方探底有亮點 (爆量)"
                 need_notify = True
            else:
                 status = "❄️ 空方持續探底"
        
        # 反彈判斷
        elif curr_price > s5:
            if s10 > s20 > s60 > s240:
                status = "📈 空方短線反彈，10/20/60/240SMA有壓"
            elif s20 < s60 and s60 > s240:
                status = "📈 空方短線反彈，60/240SMA有壓"
                if curr_price >= s20:
                    status = "📈 空方短線反彈至近月線，60/240SMA有壓"
                    need_notify = True
            else:
                status = "📈 空方反彈整理中"

    return status, need_notify

def analyze_stock(symbol):
    try:
        # 自動補齊台灣股票後綴
        pure_code = symbol.strip().upper()
        target_symbol = pure_code
        if pure_code.isdigit():
            temp_stock = yf.download(f"{pure_code}.TW", period="5d", progress=False)
            target_symbol = f"{pure_code}.TW" if not temp_stock.empty else f"{pure_code}.TWO"

        stock = yf.Ticker(target_symbol)
        df = stock.history(period="2y")
        if len(df) < 240: return None
        
        # 中文名稱對照 (若無則顯示英文)
        ch_name = STOCK_NAMES.get(pure_code, stock.info.get('shortName', target_symbol))
        
        close = df['Close']
        volume = df['Volume']
        
        # 計算今日均線
        sma = {
            3: close.rolling(3).mean().iloc[-1],
            5: close.rolling(5).mean().iloc[-1],
            10: close.rolling(10).mean().iloc[-1],
            20: close.rolling(20).mean().iloc[-1],
            60: close.rolling(60).mean().iloc[-1],
            240: close.rolling(240).mean().iloc[-1]
        }
        
        # 計算昨日均線 (用於判斷趨勢)
        prev_sma = {
            5: close.rolling(5).mean().iloc[-2],
            10: close.rolling(10).mean().iloc[-2],
            20: close.rolling(20).mean().iloc[-2],
            60: close.rolling(60).mean().iloc[-2]
        }
        
        curr_price = close.iloc[-1]
        prev_price = close.iloc[-2]
        curr_vol = volume.iloc[-1]
        prev_vol = volume.iloc[-2]

        # 呼叫判讀邏輯
        status_text, need_notify = check_market_status(curr_price, prev_price, sma, prev_sma, curr_vol, prev_vol)
        
        report_text = ""
        if need_notify:
            report_text = (f"【{ch_name} ({target_symbol})】\n"
                           f"現價: {curr_price:.2f} | 狀態: {status_text}\n"
                           f"------------------------------\n")

        return {
            "代號": target_symbol,
            "公司名稱": ch_name,
            "現價": round(curr_price, 2),
            "SMA 5/10/20": f"{sma[5]:.1f}/{sma[10]:.1f}/{sma[20]:.1f}",
            "SMA 60/240": f"{sma[60]:.1f}/{sma[240]:.1f}",
            "系統判讀": status_text,
            "需要通知": need_notify,
            "回報文字": report_text
        }
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        return None

if run_button:
    if not MY_GMAIL or not MY_PWD:
        st.error("後台 Secrets 未正確設定！")
    elif not friend_email:
        st.warning("請填寫接收通知的 Email。")
    else:
        with st.spinner('進行均線趨勢與乖離率判讀中...'):
            tickers = [t.strip() for t in ticker_input.split(',')]
            results = []
            notify_list = []
            
            for t in tickers:
                res = analyze_stock(t)
                if res:
                    results.append(res)
                    if res["需要通知"]:
                        notify_list.append(res["回報文字"])
            
            if results:
                df_show = pd.DataFrame(results).drop(columns=['需要通知', '回報文字'])
                st.dataframe(df_show, use_container_width=True)
                
                # 分批發送 Email
                if notify_list:
                    receiver_list = [MY_GMAIL, friend_email]
                    chunk_size = 5
                    chunks = [notify_list[i:i + chunk_size] for i in range(0, len(notify_list), chunk_size)]
                    
                    success_count = 0
                    for i, chunk in enumerate(chunks):
                        mail_body = f"【股市趨勢判讀報告 - Part {i+1}】\n\n" + "".join(chunk)
                        mail_body += "\n系統提示：本報告依據均線趨勢與量價關係自動生成。"
                        subject = f"股市重要訊號 ({i+1}/{len(chunks)})"
                        if send_email_batch(MY_GMAIL, MY_PWD, receiver_list, subject, mail_body):
                            success_count += 1
                        time.sleep(1)
                        
                    st.success(f"已發送 {success_count} 封郵件，共包含 {len(notify_list)} 支警示標的。")
                else:
                    st.info("目前所有標的走勢平穩，無須發送警示。")
