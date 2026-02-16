import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import re
import time
import random

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 穩健分批版", layout="wide")

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
        return False

# --- 3. 核心判讀邏輯 ---
def check_strategy(df):
    try:
        # 簡單化處理，避免多層索引錯誤
        if isinstance(df, pd.DataFrame):
             # 嘗試取得 Close 和 Volume，若無則抓前兩欄
            close = df['Close'] if 'Close' in df.columns else df.iloc[:, 0]
            volume = df['Volume'] if 'Volume' in df.columns else df.iloc[:, 1]
        else:
            return [], False, 0, 0, 0, 0

        # 移除 NaN
        close = close.dropna()
        volume = volume.dropna()
        
        if len(close) < 60: return [], False, 0, 0, 0, 0

        curr_price = close.iloc[-1]
        prev_price = close.iloc[-2]
        curr_vol = volume.iloc[-1]
        prev_vol = volume.iloc[-2]
        pct_change = (curr_price - prev_price) / prev_price if prev_price != 0 else 0
        
        price_4_days_ago = close.iloc[-5] 
        s3 = close.rolling(3).mean()
        s5 = close.rolling(5).mean()
        s10 = close.rolling(10).mean()
        s20 = close.rolling(20).mean()
        s60 = close.rolling(60).mean() 
        
        v60 = s60.iloc[-1]
        p60 = s60.iloc[-2]
        v5, v3 = s5.iloc[-1], s3.iloc[-1]

        trend_up = {5: v5 > s5.iloc[-2], 10: s10.iloc[-1] > s10.iloc[-2], 20: s20.iloc[-1] > s20.iloc[-2], 60: v60 > p60}
        up_count = sum(trend_up.values())
        down_count = 4 - up_count
        
        status = []
        need_notify = False
        
        # === 乖離率警示 ===
        if curr_price >= v60 * 1.3:
            status.append("⚠️ 乖離過大：慎防拉回 (距季線>30%)")
            need_notify = True

        # === 策略訊號 ===
        if prev_price > p60 and curr_price < v60:
            status.append("📉 轉空警示：跌破季線")
            need_notify = True
        elif prev_price < p60 and curr_price > v60:
            status.append("🚀 轉多訊號：站上季線")
            need_notify = True
        if pct_change >= 0.04 and curr_vol > prev_vol * 1.5 and curr_price > v3:
            status.append("🔥 強勢反彈 (漲>4%, 爆量, 站上3SMA)")
            need_notify = True
        if up_count >= 2 and curr_price <= v60 * 1.1:
            status.append(f"✨ 底部轉折：{up_count}條均線翻揚")
            need_notify = True
        cond_sell_a = (curr_vol > prev_vol * 1.3 and pct_change < 0)
        cond_sell_b = (curr_price < price_4_days_ago)
        if cond_sell_a or cond_sell_b:
            reasons = []
            if cond_sell_a: reasons.append("爆量收黑")
            if cond_sell_b: reasons.append("跌破4日價")
            status.append(f"⚠️ 出貨警訊 ({'+'.join(reasons)})")
            need_notify = True
        if curr_vol > prev_vol * 1.2 and curr_price < v5 and pct_change < 0:
            status.append("⚠️ 量價背離 (量增價弱，破5SMA)")
            need_notify = True
            
        dist_240 = abs(curr_price - s60.iloc[-1]) / s60.iloc[-1]
        if dist_240 < 0.05 and down_count >= 3:
            status.append("⚠️ 年線保衛戰：均線偏弱")
            need_notify = True 
        elif curr_price < v60 and down_count >= 3:
            status.append("❄️ 空方弱勢整理：均線蓋頭")
        
        if not status:
            if curr_price > v60: status.append("🌊 多方行進 (觀察)")
            else: status.append("☁️ 空方盤整 (觀望)")

        return status, need_notify, curr_price, up_count, down_count, v60
    except Exception as e:
        return [f"計算錯誤"], False, 0, 0, 0, 0

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 穩健分批版")

# 手機版切換
use_mobile_view = st.toggle("📱 手機卡片模式", value=True)

try:
    MY_GMAIL = st.secrets.get("GMAIL_USER", "")
    MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")
    MY_PRIVATE_LIST = st.secrets.get("MY_LIST", "2330")

    # 輸入表單
    with st.sidebar.form(key='stock_form'):
        st.header("設定")
        friend_email = st.text_input("Email (選填)", placeholder="輸入 Email 以接收通知")
        
        default_val = "2330"
        if friend_email == MY_GMAIL:
            default_val = MY_PRIVATE_LIST
            
        ticker_input = st.text_area("股票清單", value=default_val, height=250, help="支援逗號、空格、換行")
        submit_btn = st.form_submit_button(label='🚀 開始執行分析')

    if submit_btn:
        # 1. 解析輸入
        raw_tickers = re.findall(r'\d{4}', ticker_input)
        user_tickers = list(dict.fromkeys(raw_tickers)) # 去重但保留順序
        
        total_stocks = len(user_tickers)
        st.info(f"📊 偵測到 {total_stocks} 檔股票，開始分批掃描 (每批 5 支)...")
        
        all_results = []
        notify_list = []
        
        # 建立顯示容器
        progress_bar = st.progress(0)
        result_container = st.empty() # 用來即時更新表格
        
        # 2. 分批處理 (Chunking) - 核心修正
        chunk_size = 5
        
        for i in range(0, total_stocks, chunk_size):
            # 取得這一批的代號 (例如：第1-5支)
            batch = user_tickers[i : i + chunk_size]
            
            # 準備下載清單 (TW + TWO)
            download_list = []
            for t in batch:
                download_list.append(f"{t}.TW")
                download_list.append(f"{t}.TWO")
            
            # 下載這一批
            try:
                data = yf.download(download_list, period="3mo", group_by='ticker', progress=False)
            except Exception:
                data = pd.DataFrame() # 如果下載失敗，給空值，不要當機

            # 處理這一批的每一支
            for t in batch:
                full_tw = f"{t}.TW"
                full_two = f"{t}.TWO"
                
                df = pd.DataFrame()
                final_symbol = full_tw
                
                # 嘗試撈資料
                try:
                    # 情況A: 只有一支股票時，Yahoo回傳的結構不同
                    if len(download_list) <= 2: # TW+TWO=2
                        if not data.empty: df = data
                    # 情況B: 多支股票
                    else:
                        if full_tw in data:
                            temp = data[full_tw]
                            if not temp['Close'].isna().all(): df = temp
                        
                        if df.empty and full_two in data:
                            temp = data[full_two]
                            if not temp['Close'].isna().all(): 
                                df = temp
                                final_symbol = full_two
                except:
                    pass

                # 建立結果列
                row_data = {
                    "序號": len(all_results) + 1,
                    "代號": t,
                    "名稱": STOCK_NAMES.get(t, t),
                    "現價": 0,
                    "狀態": "❌",
                    "訊號": "❌ 查無資料"
                }

                if not df.empty:
                    try:
                        status_list, need_notify, price, up_cnt, down_cnt, v60 = check_strategy(df)
                        row_data["名稱"] = STOCK_NAMES.get(t, final_symbol)
                        row_data["現價"] = round(price, 2)
                        row_data["狀態"] = f"⬆️{up_cnt}⬇️{down_cnt}"
                        row_data["訊號"] = " | ".join(status_list)
                        
                        if need_notify:
                            notify_list.append(f"【{row_data['名稱']}】{price} | {row_data['訊號']}\n")
                    except:
                        pass
                
                all_results.append(row_data)

            # --- 關鍵：每處理完一批，馬上更新畫面 ---
            df_display = pd.DataFrame(all_results)
            
            if use_mobile_view:
                # 手機版不適合一直重繪整個很長的列表，改為最後顯示
                # 但為了進度感，我們可以顯示文字狀態
                pass 
            else:
                result_container.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # 更新進度條
            progress_bar.progress(min((i + chunk_size) / total_stocks, 1.0))
            
            # 休息一下，避免被擋
            time.sleep(1)

        st.success("✅ 全部掃描完成！")

        # 3. 最終顯示 (確保完整)
        df_final = pd.DataFrame(all_results)
        
        # 如果是手機版，這時候再渲染漂亮的卡片
        if use_mobile_view:
            result_container.empty() # 清空之前的表格
            for idx, row in df_final.iterrows():
                color = "grey"
                if "🚀" in row['訊號'] or "🔥" in row['訊號']: color = "green"
                elif "⚠️" in row['訊號'] or "📉" in row['訊號']: color = "red"
                
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    c1.markdown(f"**{row['序號']}. {row['名稱']}** ({row['代號']})")
                    c2.markdown(f"**${row['現價']}**")
                    st.caption(f"均線: {row['狀態']}")
                    
                    if "❌" not in row['訊號']:
                        if color == "red": st.error(row['訊號'])
                        elif color == "green": st.success(row['訊號'])
                        else: st.info(row['訊號'])
                    else:
                        st.write(row['訊號'])
        else:
            result_container.dataframe(df_final, use_container_width=True, hide_index=True)

        # 發信
        if notify_list and MY_GMAIL and friend_email:
            receiver_list = [MY_GMAIL, friend_email]
            chunks = [notify_list[i:i + 20] for i in range(0, len(notify_list), 20)]
            for i, chunk in enumerate(chunks):
                send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"戰略訊號 ({i+1})", "".join(chunk))
                time.sleep(1)
            st.success(f"已發送 {len(notify_list)} 則通知信。")

except Exception as e:
    st.error(f"系統錯誤: {e}")
