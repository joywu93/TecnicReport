# ==========================================
# 📂 檔案名稱： update_finance.py (後台自動更新大師 - Streamlit 雲端版)
# 💡 目的： 抓取官方本益比與殖利率，計算配息率後，精準寫入「盈餘總分配率」
# 🛠️ 修正： 改用「整欄區塊寫入 (ws.update)」，徹底解決 Google API 的 ListValue 報錯 Bug！
# ==========================================

import streamlit as st
import requests
import urllib3
import gspread
from google.oauth2.service_account import Credentials
import json

# 關閉煩人的「未加密警告」提示音
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 網頁與系統設定
# ==========================================
st.set_page_config(page_title="財務後台更新大師", layout="centered", page_icon="🤖")
st.title("🤖 雲端財務數據更新大師 (update_finance.py)")

# 您的 Google Sheet 網址
MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

def get_gspread_client():
    """使用 Streamlit 雲端的 Secrets 進行 Google 認證"""
    if "google_key" not in st.secrets: 
        st.error("❌ 找不到 Google 金鑰 (st.secrets)，請確認雲端環境設定。")
        st.stop()
    key_data = st.secrets["google_key"]
    creds = Credentials.from_service_account_info(
        json.loads(key_data) if isinstance(key_data, str) else dict(key_data), 
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return gspread.authorize(creds)

# ==========================================
# 🚀 核心功能：更新「盈餘總分配率」
# ==========================================
st.markdown("### 🎯 【盈餘總分配率】雲端清洗站")
st.info("💡 **運作原理**：潛入證交所與櫃買中心，抓取每日最新『本益比』與『殖利率』，利用反向公式計算出全市場的隱含配息率，並自動覆寫您的 Google Sheet。")

if st.button("🚀 執行全市場配息率更新", type="primary", use_container_width=True):
    with st.status("啟動雲端更新程序...", expanded=True) as status:
        try:
            # ----------------------------------------
            # 1. 抓取官方資料
            # ----------------------------------------
            status.update(label="[1/3] 潛入官方資料庫，獲取本益比與殖利率...")
            headers = {'User-Agent': 'Mozilla/5.0'}
            magic_payout_dict = {}

            # 上市 (TWSE)
            try:
                url_twse = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
                res_twse = requests.get(url_twse, headers=headers, verify=False, timeout=15).json()
                for item in res_twse:
                    code = str(item.get('Code', '')).strip()
                    try:
                        pe = float(str(item.get('PeRatio', '0')).replace(',', ''))
                        dy = float(str(item.get('DividendYield', '0')).replace(',', ''))
                        if pe > 0 and dy > 0: magic_payout_dict[code] = round(pe * dy, 2)
                    except: pass
            except Exception as e:
                st.warning(f"上市資料獲取失敗: {e}")

            # 上櫃 (TPEx)
            try:
                url_tpex = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_perwd_quotes"
                res_tpex = requests.get(url_tpex, headers=headers, verify=False, timeout=15).json()
                for item in res_tpex:
                    code = str(item.get('SecuritiesCompanyCode', '')).strip()
                    try:
                        pe = float(str(item.get('PERatio', '0')).replace(',', ''))
                        dy = float(str(item.get('Dividendyield', '0')).replace(',', ''))
                        if pe > 0 and dy > 0: magic_payout_dict[code] = round(pe * dy, 2)
                    except: pass
            except Exception as e:
                st.warning(f"上櫃資料獲取失敗: {e}")

            if not magic_payout_dict:
                status.update(label="⚠️ 無法取得官方資料，請稍後再試", state="error")
                st.stop()

            st.write(f"✅ 成功反推計算出 **{len(magic_payout_dict)}** 檔股票的配息率！")

            # ----------------------------------------
            # 2. 連線 Google Sheet
            # ----------------------------------------
            status.update(label="[2/3] 連線 Google Sheet 戰情室...")
            client = get_gspread_client()
            worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
            target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]

            # ----------------------------------------
            # 3. 寫入資料 (整欄區塊寫入法)
            # ----------------------------------------
            status.update(label="[3/3] 開始寫入各分頁配息率 (高速整欄模式)...")
            total_updated = 0
            
            for ws in target_sheets:
                data = ws.get_all_values()
                if not data or len(data) < 2: continue
                
                headers_row = data[0]
                
                # 🎯 尋找目標欄位：嚴格鎖定「代號」與「盈餘總分配率」
                c_idx = next((i for i, x in enumerate(headers_row) if "代號" in str(x)), -1)
                p_idx = next((i for i, x in enumerate(headers_row) if str(x).strip() == "盈餘總分配率"), -1)
                
                if c_idx != -1 and p_idx != -1:
                    # 準備一整直排的資料
                    col_values = []
                    cells_updated = 0
                    
                    for r in range(1, len(data)):
                        row = data[r]
                        code = str(row[c_idx]).split('.')[0].strip()
                        
                        if code in magic_payout_dict:
                            # 填入算好的新配息率
                            col_values.append([magic_payout_dict[code]])
                            cells_updated += 1
                        else:
                            # 保持原本的數值不變 (防呆處理)
                            old_val = row[p_idx] if p_idx < len(row) else ""
                            col_values.append([old_val])
                            
                    if cells_updated > 0:
                        # 找出該欄位的英文代號 (例如第7欄就是 G)
                        col_letter = gspread.utils.rowcol_to_a1(1, p_idx+1).replace('1', '')
                        # 框出整條欄位的範圍 (例如 G2:G1000)
                        range_str = f"{col_letter}2:{col_letter}{len(data)}"
                        
                        # 💡 終極解法：整排一次覆寫，絕對不會發生格式錯亂的 Bug！
                        ws.update(values=col_values, range_name=range_str)
                        
                        total_updated += cells_updated
                        st.write(f"📝 分頁 **[{ws.title}]** 成功更新了 {cells_updated} 檔！")
                else:
                    st.warning(f"⚠️ 分頁 **[{ws.title}]** 找不到名為「盈餘總分配率」的欄位，已跳過。")

            status.update(label=f"🎉 任務圓滿完成！總共更新了 {total_updated} 檔股票的配息率！", state="complete")
            st.balloons() 

        except Exception as e:
            status.update(label="發生錯誤", state="error")
            st.error(f"系統錯誤: {e}")

st.divider()
st.caption("🚀 2026 戰略指揮 - 專屬財務後台更新系統")
