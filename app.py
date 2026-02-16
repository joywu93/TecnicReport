import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time
import re
import os

# ==========================================
# 🔧 設定區
# ==========================================

# --- 1. 中文名稱對照表 ---
STOCK_NAMES = {
    "2330": "台積電", "2317": "鴻海", "6203": "海韻電", "3570": "大塚", "4766": "南寶", "NVDA": "輝達",
    "2313": "華通", "2454": "聯發科", "2303": "聯電", "2603": "長榮", "2609": "陽明", "2615": "萬海",
    "2323": "中環", "2451": "創見", "6229": "研通", "4763": "材料-KY", "1522": "堤維西", "2404": "漢唐",
    "6788": "華景電", "2344": "華邦電", "1519": "華城", "1513": "中興電", "3231": "緯創", "3035": "智原",
    "2408": "南亞科", "3406": "玉晶光", "2368": "金像電", "4979": "華星光", "3163": "波若威", "1326": "台化",
    "3491": "昇達科", "6143": "振曜", "2383": "台光電", "5225": "東科-KY", "3526": "凡甲", "6197": "佳必琪",
    "8299": "群聯", "8069": "元太", "3037": "欣興", "8046": "南電", "4977": "眾達-KY", "3455": "由田",
    "8271": "宇瞻", "5439": "高技"
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

# --- 3. 核心判讀邏輯 ---
def check_strategy(df):
    close = df['Close']
    volume = df['Volume']
    
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    pct_change = (curr_price - prev_price) / prev_price
    
    price_4_days_ago = close.iloc[-5] 
    
    s3 = close.rolling(3).mean()
    s5 = close.rolling(5).mean()
    s10 = close.rolling(10).mean()
    s20 = close.rolling(20).mean()
    s60 = close.rolling(60).mean() 
    s240 = close.rolling(240).mean()
    
    v240 = s240.iloc[-1] if len(close) >= 240 else s60.iloc[-1]
    v60 = s60.iloc[-1]
    p60 = s60.iloc[-2]
    v5, v10, v20 = s5.iloc[-1], s10.iloc[-1], s20.iloc[-1]
    p5, p10, p20 = s5.iloc[-2], s10.iloc[-2], s20.iloc[-2]
    v3 = s3.iloc[-1]

    trend_up = {5: v5 > p5, 10: v10 > p10, 20: v20 > p20, 60: v60 > p60}
    up_count = sum([trend_up[5], trend_up[10], trend_up[20], trend_up[60]])
    down_count = 4 - up_count
    
    status = []
    need_notify = False
    
    # 1. 重大轉折訊號
    if prev_price > p60 and curr_price < v60:
        status.append("📉 轉空警示：跌破季線(60SMA)")
        need_notify = True
    elif prev_price < p60 and curr_price > v60:
        status.append("🚀 轉多訊號：站上季線(60SMA)")
        need_notify = True
        
    # 2. 強勢反彈
    if pct_change >= 0.04 and curr_vol > prev_vol * 1.5 and curr_price > v3:
        status.append("🔥 強勢反彈 (漲>4%, 爆量1.5倍, 站上3SMA)")
        need_notify = True
        
    # 3. 底部轉折
    if up_count >= 2 and curr_price <= v60 * 1.1:
        status.append(f"✨ 底部轉折：{up_count}條均線翻揚")
        need_notify = True

    # 4. 出貨警訊
    cond_sell_a = (curr_vol > prev_vol * 1.3 and pct_change < 0)
    cond_sell_b = (curr_price < price_4_days_ago)
    
    if cond_sell_a or cond_sell_b:
        reasons = []
        if cond_sell_a: reasons.append("爆量收黑")
        if cond_sell_b: reasons.append("跌破4日價")
        status.append(f"⚠️ 出貨警訊 ({'+'.join(reasons)})")
        need_notify = True

    # 5. 量價背離
    if curr_vol > prev_vol * 1.2 and curr_price < v5 and pct_change < 0:
        status.append("⚠️ 量價背離 (量增價弱，破5SMA)")
        need_notify = True

    # 6. 關鍵位置
    dist_240 = abs(curr_price - v240) / v240
    if dist_240 < 0.05 and down_count >= 3:
        status.append("⚠️ 年線保衛戰：均線偏弱")
        need_notify = True 
    elif curr_price < v240 and down_count >= 3:
        status.append("❄️ 空方弱勢整理：均線蓋頭")
    
    avg_price = (v5 + v10 + v20) / 3
    if abs(v5-avg_price)/avg_price < 0.02 and abs(v20-avg_price)/avg_price < 0.02:
        status.append("🌀 均線糾結：變盤在即")
        
    if not status:
        if curr_price > v60: status.append("🌊 多方行進 (觀察)")
        else: status.append("☁️ 空方盤整 (觀望)")

    return status, need_notify, curr_price, up_count, down_count, v60

# --- 關鍵修正：加入快取機制 (Caching) ---
# ttl=900 代表資料會被記住 15 分鐘，期間內重複查詢不會再向 Yahoo 發請求
@st.cache_data(ttl=900)
def fetch_stock_data(symbol):
    pure_code = symbol.strip().upper()
    if not pure_code: return None, None, "空代號"

    # 先試 .TW
    target_symbol = f"{pure_code}.TW"
    # 使用 yf.download 替代 Ticker，並關閉進度條
    df = yf.download(target_symbol, period="1y", progress=False)
    
    # 如果抓不到或資料全空，改試 .TWO
    if df.empty:
        target_symbol = f"{pure_code}.TWO"
        df = yf.download(target_symbol, period="1y", progress=False)
    
    return df, target_symbol, pure_code

# 設定頁面與標題
st.set_page_config(page_title="全方位戰略監控系統", layout="wide")
st.title("📈 股市戰略轉折 & 自動提示分析")

try:
    # 後台 Secrets 讀取
    MY_GMAIL = st.secrets.get("GMAIL_USER", "")
    MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")
    MY_PRIVATE_LIST = st.secrets.get("MY_LIST", "2330, 2317") 

    st.sidebar.header("👤 使用者設定")
    friend_email = st.sidebar.text_input("接收通知信箱 (輸入 Email 以載入設定)", placeholder="請輸入您的 Email")

    # 判斷載入清單
    display_tickers = "2330"
    if friend_email.strip() == MY_GMAIL:
        display_tickers = MY_PRIVATE_LIST

    # 文字輸入區
    ticker_input = st.sidebar.text_area(
        "自選股清單 (支援中文/英文逗號、空白、分號)", 
        value=display_tickers, 
        height=300,
        key=f"area_{friend_email}", 
        help="輸入 Email 後會自動載入專屬清單"
    )

    run_button = st.sidebar.button("立即執行判讀")

    if run_button:
        if not MY_GMAIL or not MY_PWD:
            st.error("請檢查 Secrets 設定！無法讀取 GMAIL 帳號密碼。")
        elif not friend_email:
            st.warning("請填寫接收通知的 Email。")
        else:
            # 處理分隔符號
            raw_tickers = re.split(r'[,\s;，、]+', ticker_input)
            tickers = list(dict.fromkeys([t.strip() for t in raw_tickers if t.strip()]))
            
            results = []
            notify_list = []
            
            st.write(f"📊 成功辨識 {len(tickers)} 檔股票，正在抓取資料 (快取模式)...")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            total_tickers = len(tickers)
            for i, t in enumerate(tickers):
                status_text.text(f"分析進度 ({i+1}/{total_tickers}): {t} ...")
                
                # 呼叫有快取的下載函數
                df, target_symbol, pure_code = fetch_stock_data(t)
                
                if df is not None and not df.empty and len(df) >= 60:
                    try:
                        # 處理 MultiIndex Column 問題 (yf.download 會有這問題)
                        if isinstance(df.columns, pd.MultiIndex):
                            df.columns = df.columns.droplevel(1)
                            
                        # 取得名稱
                        ch_name = STOCK_NAMES.get(pure_code, target_symbol)
                        
                        # 執行策略
                        status_list, need_notify, price, up_cnt, down_cnt, v60 = check_strategy(df)
                        status_text_str = " | ".join(status_list)
                        
                        report_text = ""
                        if need_notify:
                            report_text = (f"【{ch_name} ({target_symbol})】\n"
                                           f"現價: {price:.2f} (季線: {v60:.1f})\n"
                                           f"訊號: {status_text_str}\n"
                                           f"------------------------------\n")

                        results.append({
                            "代號": target_symbol,
                            "公司名稱": ch_name,
                            "現價": round(price, 2),
                            "均線狀態": f"⬆️{up_cnt} / ⬇️{down_cnt}",
                            "戰略訊號": status_text_str,
                            "需要通知": need_notify,
                            "回報文字": report_text
                        })
                        if need_notify:
                            notify_list.append(report_text)
                            
                    except Exception as e:
                        print(f"Error processing {target_symbol}: {e}")
                
                progress_bar.progress((i + 1) / total_tickers)
                # 即使有快取，還是稍微休息一下比較保險，但可以縮短時間
                time.sleep(0.1)
                
            status_text.text("✅ 全部分析完成！")
            
            if results:
                st.dataframe(pd.DataFrame(results).drop(columns=['需要通知', '回報文字']), use_container_width=True)
                
                if notify_list:
                    receiver_list = [MY_GMAIL, friend_email]
                    chunk_size = 5
                    chunks = [notify_list[i:i + chunk_size] for i in range(0, len(notify_list), chunk_size)]
                    
                    for i, chunk in enumerate(chunks):
                        mail_body = f"【股市戰略報告 - Part {i+1}】\n\n" + "".join(chunk)
                        send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"關鍵戰略提示 ({i+1})", mail_body)
                        time.sleep(1)
                        
                    st.success(f"已發送 {len(notify_list)} 則重要訊號。")
                else:
                    st.info("目前持股走勢平穩，無特殊警示。")
            else:
                st.warning("未找到有效股票。請稍後再試，或檢查 Yahoo Finance 連線。")

except Exception as e:
    st.error(f"程式發生錯誤：{e}")
