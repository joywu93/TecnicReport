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
    "2603": "長榮", "2609": "陽明", "2615": "萬海"
}

# --- 2. Email 發送函數 (支援分批發送) ---
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
ticker_input = st.sidebar.text_area("自選股清單 (輸入數字即可)", "2330, 2317, 6203, 3570, 4766")
run_button = st.sidebar.button("立即執行判讀")

# --- 3. 核心判讀邏輯函數 ---
def check_market_status(curr_price, prev_price, sma, curr_vol, prev_vol):
    # 解包均線數據
    s3, s5, s10, s20, s60, s240 = sma[3], sma[5], sma[10], sma[20], sma[60], sma[240]
    
    status = "趨勢不明/盤整中"
    need_notify = False # 是否需要發信
    
    # 判斷多方市場 (收盤 > 240SMA)
    if curr_price > s240:
        # 1.a & 1.b & 1.c & 1.d: 多頭排列 (5>10>20>60>240)
        if s5 > s10 > s20 > s60 > s240:
            if curr_price > s5:
                # 1.b: 乖離過大
                if curr_price >= s60 * 1.3:
                    status = "⚠️ 中多持續但短線乖離過大 (>60SMA 30%)"
                    need_notify = True
                else:
                    # 1.a
                    status = "📈 中多持續趨勢向上"
            else: # curr_price < s5
                # 1.c: 高檔震盪 (量增 1.5倍)
                if curr_vol > prev_vol * 1.5:
                    status = "⚠️ 中多高檔震盪，短線注意"
                    need_notify = True
                else:
                    # 1.d (包含 Logic 3 的部分情境)
                    if curr_vol > prev_vol * 1.4:
                        status = "📉 中多短空，量價背離，測試10SMA支撐"
                        need_notify = True
                    else:
                        status = "☕ 中多高檔整理"

        # 2. 高檔整理 (價格在 5SMA +-3% 或 10SMA +-5% 之間)
        elif (abs(curr_price - s5)/s5 <= 0.03 or abs(curr_price - s10)/s10 <= 0.05) and s20 > s60 > s240:
             status = "☕ 中多高檔整理 (均線糾結)"

        # 4. 短線轉弱 (5 < 10, 10 > 20)
        elif s5 < s10 and s10 > s20 > s60 > s240:
            if curr_price < s5 and curr_vol > prev_vol * 1.4:
                status = "📉 中多短空，量價背離，測試20SMA支撐"
                need_notify = True
            else:
                status = "📉 中多短空，測試20SMA支撐"

        # 5. 回測季線 (5 < 10 < 20, 20 > 60)
        elif s5 < s10 < s20 and s20 > s60 > s240:
            if curr_price < s5 and curr_vol > prev_vol * 1.4:
                status = "📉 中多短中空，量價背離，測試60SMA支撐"
                need_notify = True
            elif curr_price > s5: # 5.b 反彈
                if curr_vol > prev_vol * 1.4:
                    status = "📈 中多短線反彈，20SMA有壓，測試60SMA支撐"
                    need_notify = True
                else:
                    status = "📈 中多短線反彈，60SMA有壓"
            else:
                status = "📉 中多短中空，測試60SMA支撐"

        # 6. 探底 (5 < 10 < 20 < 60, 60 > 240)
        elif s5 < s10 < s20 < s60 and s60 > s240:
            if curr_vol > prev_vol * 1.4:
                if curr_price > prev_price: # 亮點 (紅K)
                    status = "✨ 短中空量價配合有亮點，測試240SMA支撐"
                    need_notify = True
                else: # 殺盤 (黑K)
                    status = "📉 短中空量價背離，測試240SMA支撐 (繼續探底)"
                    need_notify = True
            else:
                status = "📉 短中空測試240SMA支撐 (繼續探底)"

    # 判斷空方市場 (收盤 < 240SMA)
    else:
        # 1. 空頭排列 (5<10<20<60<240)
        if s5 < s10 < s20 < s60 < s240:
            # 修正: 3SMA 判定 (如果收盤站上 3SMA 且量增)
            if curr_price > s3 and curr_vol > prev_vol * 1.5:
                status = "✨ 空方探底有亮點 (站上3SMA+爆量)"
                need_notify = True
            else:
                status = "❄️ 空方持續探底"
        
        # 反彈判斷
        elif curr_price > s5:
            if s10 > s20 > s60 > s240: # 接近 10SMA
                status = "📈 空方短線反彈，10/20/60/240SMA有壓"
            elif s10 < s20 and s20 > s60: # 站上 10, 測 20
                status = "📈 空方短線反彈，20/60/240SMA有壓"
            elif s20 < s60 and s60 > s240: # 站上 20, 測 60
                status = "📈 空方短線反彈，60/240SMA有壓"
                if curr_price >= s20: # 接近月線
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
        # 抓取 2 年數據以確保 240SMA 有值
        df = stock.history(period="2y")
        if len(df) < 240: return None
        
        ch_name = STOCK_NAMES.get(pure_code, stock.info.get('shortName', target_symbol))
        
        close = df['Close']
        volume = df['Volume']
        
        # 計算所需均線
        sma = {
            3: close.rolling(3).mean().iloc[-1],
            5: close.rolling(5).mean().iloc[-1],
            10: close.rolling(10).mean().iloc[-1],
            20: close.rolling(20).mean().iloc[-1],
            60: close.rolling(60).mean().iloc[-1],
            240: close.rolling(240).mean().iloc[-1]
        }
        
        # 取得今日與昨日數據
        curr_price = close.iloc[-1]
        prev_price = close.iloc[-2]
        curr_vol = volume.iloc[-1]
        prev_vol = volume.iloc[-2]

        # 呼叫判讀邏輯
        status_text, need_notify = check_market_status(curr_price, prev_price, sma, curr_vol, prev_vol)
        
        # 準備 Email 文字
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
            "量能變化": f"今{int(curr_vol/1000)}K / 昨{int(prev_vol/1000)}K",
            "系統判讀": status_text,
            "需要通知": need_notify,
            "回報文字": report_text
        }
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        return None

if run_button:
    if not MY_GMAIL or not MY_PWD:
        st.error("後台 Secrets 未正確設定發信帳號！")
    elif not friend_email:
        st.warning("請填寫接收通知的 Email。")
    else:
        with st.spinner('正在進行專業趨勢運算...'):
            tickers = [t.strip() for t in ticker_input.split(',')]
            results = []
            notify_list = [] # 收集所有需要通知的文字
            
            for t in tickers:
                res = analyze_stock(t)
                if res:
                    results.append(res)
                    if res["需要通知"]:
                        notify_list.append(res["回報文字"])
            
            if results:
                # 顯示網頁表格
                df_show = pd.DataFrame(results).drop(columns=['需要通知', '回報文字'])
                st.dataframe(df_show, use_container_width=True)
                
                # --- Email 分批發送邏輯 (每5封一件) ---
                if notify_list:
                    receiver_list = [MY_GMAIL, friend_email]
                    chunk_size = 5 # 設定每封信包含幾支股票
                    
                    # 將列表切割成多個小塊
                    chunks = [notify_list[i:i + chunk_size] for i in range(0, len(notify_list), chunk_size)]
                    
                    success_count = 0
                    for i, chunk in enumerate(chunks):
                        mail_body = f"【股市趨勢判讀報告 - Part {i+1}】\n\n" + "".join(chunk)
                        mail_body += "\n系統提示：本報告依據多空市場量價與均線位階自動生成。"
                        
                        subject = f"股市重要訊號通知 ({i+1}/{len(chunks)})"
                        
                        if send_email_batch(MY_GMAIL, MY_PWD, receiver_list, subject, mail_body):
                            success_count += 1
                        time.sleep(1) # 避免發送太快被擋
                        
                    st.success(f"判讀完成！共發現 {len(notify_list)} 支標的需留意，已拆分為 {success_count} 封郵件發送。")
                else:
                    st.info("掃描完成，目前所有持股走勢穩健，無須發送特殊警示通知。")
