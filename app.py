import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time

# --- 1. 中文名稱對照表 ---
STOCK_NAMES = {
    "2330": "台積電", "2317": "鴻海", "6203": "海韻電", 
    "3570": "大塚", "4766": "南寶", "NVDA": "輝達",
    "2313": "華通", "2454": "聯發科", "2303": "聯電",
    "2603": "長榮", "2609": "陽明", "2615": "萬海",
    "2323": "中環", "2451": "創見", "6229": "研通",
    "4763": "材料-KY", "1522": "堤維西", "2404": "漢唐",
    "6788": "華景電", "2344": "華邦電", "1519": "華城",
    "1513": "中興電", "3231": "緯創", "3035": "智原",
    "2408": "南亞科"
}

# --- 2. Email 發送函數 (分批發送) ---
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

st.set_page_config(page_title="股市技術指標戰略系統", layout="wide")
st.title("📈 股市多空轉換 & 戰略判讀系統")

# 後台 Secrets 讀取
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

st.sidebar.header("👤 使用者設定")
friend_email = st.sidebar.text_input("接收通知信箱", placeholder="請輸入您的 Email")
ticker_input = st.sidebar.text_area("自選股清單", "2330, 2317, 2454, 6203, 4766")
run_button = st.sidebar.button("立即執行判讀")

# --- 3. 核心判讀邏輯 ---
def check_strategy(df, symbol):
    # 提取數據
    close = df['Close']
    volume = df['Volume']
    
    # 當日與前一日數據
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    
    # 計算近3日高低點 (不含今日，用於判斷突破/跌破)
    last_3_days_high = close.iloc[-4:-1].max()
    last_3_days_low = close.iloc[-4:-1].min()

    # 計算均線 (Value)
    s5 = close.rolling(5).mean()
    s10 = close.rolling(10).mean()
    s20 = close.rolling(20).mean()
    s60 = close.rolling(60).mean()
    s240 = close.rolling(240).mean()

    # 取得今日均線數值
    v5, v10, v20, v60, v240 = s5.iloc[-1], s10.iloc[-1], s20.iloc[-1], s60.iloc[-1], s240.iloc[-1]
    
    # 取得前一日均線數值 (用於判斷斜率/趨勢)
    p5, p10, p20, p60 = s5.iloc[-2], s10.iloc[-2], s20.iloc[-2], s60.iloc[-2]

    # 判斷均線趨勢 (True=向上, False=向下)
    trend_up = {
        5: v5 > p5, 10: v10 > p10, 20: v20 > p20, 60: v60 > p60
    }
    
    # 統計趨勢數量
    up_count = sum([trend_up[5], trend_up[10], trend_up[20], trend_up[60]])
    down_count = 4 - up_count
    
    status = []
    need_notify = False
    
    # === 基礎判斷：年線多空 ===
    market_trend = "多方" if curr_price > v240 else "空方"
    
    # === A. 中場多方延續 (根據向上均線數量) ===
    if up_count >= 3:
        status.append("✅ 多方持續 (均線多頭)")
    elif up_count == 2:
        status.append("👀 多方觀察")

    # === B. 多方向下修正調整 (基準：股價在 60SMA 之上) ===
    if curr_price > v60:
        # B.2 短線乖離率過高/過低
        if curr_price > v60 * 1.27:
            status.append("⚠️ 短線乖離率過高")
        elif curr_price < v60 * 0.85: # 假設低乖離
            status.append("⚠️ 短線乖離率過低")

        # B.3 高檔轉折訊號
        # a) 10SMA下彎且股價 < 10SMA
        if not trend_up[10] and curr_price < v10:
            msg = "📉 高檔中長多短空：10SMA下彎，20SMA為支撐"
            status.append(msg)
            need_notify = True
            if curr_vol > prev_vol * 1.3: status.append("⚠️ (量價背離)")

        # b) 20SMA下彎且股價 < 20SMA
        elif not trend_up[20] and curr_price < v20:
            msg = "📉 高檔中長多轉中空：20SMA下彎，60SMA為支撐"
            status.append(msg)
            need_notify = True
            if curr_vol > prev_vol * 1.3: status.append("⚠️ (量價背離)")

        # c) 60SMA下彎且股價 < 60SMA
        elif not trend_up[60] and curr_price < v60:
            msg = "📉 高檔中長多轉中長空：60SMA下彎，需時間調整"
            status.append(msg)
            need_notify = True
            if curr_vol > prev_vol * 1.3: status.append("⚠️ (量價背離)")

        # d) 當日長黑(跌>5%) 且 跌破近3日最低
        pct_change = (curr_price - prev_price) / prev_price
        if pct_change <= -0.05 and curr_price < last_3_days_low:
            status.append("⚠️ 警訊：長黑跌破近3日低點")
            need_notify = True
            if curr_vol > prev_vol * 1.3: status.append("⚠️ (量價背離)")

    # === C. 空方延續 (基準：均線向下) ===
    # C.0 空方持續判斷
    if down_count >= 3:
        status.append("❄️ 空方持續")
    elif down_count <= 2:
        status.append("✨ 空方底部有亮點")
    
    # C.1 底部亮點 (漲幅>5% & 收盤>近3日高 & 量>1.5倍)
    pct_change = (curr_price - prev_price) / prev_price
    if pct_change >= 0.05 and curr_price > last_3_days_high and curr_vol > prev_vol * 1.5:
        status.append("🚀 底部亮點 + 量價配合 (漲幅>5%且過前高)")
        need_notify = True

    # C.2~C.6 反彈壓力測試 (根據均線排列與價格位置)
    # 為了簡化邏輯，我們檢查價格與均線的相對位置
    
    # C.2: 5 < 10 < 20 < 60 (標準空頭排列) 但價格 > 5日線
    if v5 < v10 < v20 < v60 and curr_price > v5:
        msg = "📈 底部有亮點，10/20/60日線有壓"
        status.append(msg)
        if curr_vol > prev_vol * 1.5:
            status.append("✅ (量價配合)")
            need_notify = True
    
    # 檢查跌幅是否 > 5% (用於 C.3 ~ C.6 的通知觸發)
    is_heavy_drop = pct_change <= -0.05
    
    # C.3: 5 > 10 < 20 < 60 (5日線已金叉10日線，但上方有壓)
    if v5 > v10 and v10 < v20 < v60:
        msg = "📈 底部有亮點，20/60日線有壓"
        status.append(msg)
        if is_heavy_drop: need_notify = True

    # C.4: 5 > 10 > 20 < 60 (短多成形，測季線)
    if v5 > v10 > v20 and v20 < v60:
        msg = "📈 短期反彈，10/20日線支撐，60日線有壓"
        status.append(msg)
        if is_heavy_drop: need_notify = True

    # C.5: 5 > 10, 20與60關係不明確 (簡化為 20 < 60 但非標準排列)
    # 這裡捕捉 "5>10" 且 "20<60" 的中間狀態
    if v5 > v10 and v20 < v60 and not (v5 > v10 > v20):
        msg = "📈 短期反彈，觀察20日支撐，60日線有壓"
        status.append(msg)
        if is_heavy_drop: need_notify = True

    # C.6: 5 > 10, 20 > 60 (中短期翻多)
    if v5 > v10 and v20 > v60:
        msg = "📈 中短期反彈翻多，觀察60日支撐，240日線有壓"
        status.append(msg)
        if is_heavy_drop: 
            status.append("⚠️ 中短期反彈有壓")
            need_notify = True

    return status, need_notify, market_trend, v60, v240

def analyze_stock(symbol):
    try:
        pure_code = symbol.strip().upper()
        target_symbol = pure_code
        if pure_code.isdigit():
            temp_stock = yf.download(f"{pure_code}.TW", period="5d", progress=False)
            target_symbol = f"{pure_code}.TW" if not temp_stock.empty else f"{pure_code}.TWO"

        stock = yf.Ticker(target_symbol)
        df = stock.history(period="2y") # 需2年數據算240SMA
        if len(df) < 240: return None
        
        ch_name = STOCK_NAMES.get(pure_code, stock.info.get('shortName', target_symbol))
        
        curr_price = df['Close'].iloc[-1]
        
        # 呼叫新邏輯
        status_list, need_notify, market_trend, v60, v240 = check_strategy(df, target_symbol)
        
        # 組合顯示文字
        status_text = " | ".join(status_list) if status_list else "盤整無特殊訊號"
        
        report_text = ""
        if need_notify:
            report_text = (f"【{ch_name} ({target_symbol})】\n"
                           f"現價: {curr_price:.2f} ({market_trend}市場)\n"
                           f"訊號: {status_text}\n"
                           f"------------------------------\n")

        return {
            "代號": target_symbol,
            "公司名稱": ch_name,
            "現價": round(curr_price, 2),
            "多空市場(240SMA)": f"{market_trend} (> {v240:.1f})" if curr_price > v240 else f"{market_trend} (< {v240:.1f})",
            "季線(60SMA)": f"{v60:.1f}",
            "戰略判讀": status_text,
            "需要通知": need_notify,
            "回報文字": report_text
        }
    except Exception as e:
        print(f"Error: {e}")
        return None

if run_button:
    if not MY_GMAIL or not MY_PWD:
        st.error("後台 Secrets 未正確設定！")
    elif not friend_email:
        st.warning("請填寫接收通知的 Email。")
    else:
        with st.spinner('正在執行多空戰略判讀...'):
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
                st.dataframe(pd.DataFrame(results).drop(columns=['需要通知', '回報文字']), use_container_width=True)
                
                if notify_list:
                    receiver_list = [MY_GMAIL, friend_email]
                    chunk_size = 5
                    chunks = [notify_list[i:i + chunk_size] for i in range(0, len(notify_list), chunk_size)]
                    
                    for i, chunk in enumerate(chunks):
                        mail_body = f"【股市戰略報告 - Part {i+1}】\n\n" + "".join(chunk)
                        send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"股市重要戰略訊號 ({i+1})", mail_body)
                        time.sleep(1)
                        
                    st.success(f"判讀完成！已發送 {len(notify_list)} 則戰略警示。")
                else:
                    st.info("目前持股走勢穩健，無須發送警示。")
