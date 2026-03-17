# ==========================================
# 📂 檔案名稱： update_finance.py (後台自動更新大師 - Streamlit 雲端版)
# 💡 目的： 抓取官方本益比與殖利率，計算配息率後，精準寫入「盈餘總分配率」
# 🛠️ 修正： 將寫入表單的數字強制轉為字串 (str)，解決 Google API 格式報錯
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
            # 鎖定包含目標字眼的分頁
            target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]

            # ----------------------------------------
            # 3. 寫入資料 (絕對精準比對 + 強制轉字串防呆)
            # ----------------------------------------
            status.update(label="[3/3] 開始寫入各分頁配息率...")
            total_updated = 0
            
            for ws in target_sheets:
                data = ws.get_all_values()
                if not data: continue
                
                headers_row = data[0]
                
                # 🎯 尋找目標欄位：嚴格鎖定「代號」與「盈餘總分配率」
                c_idx = next((i for i, x in enumerate(headers_row) if "代號" in str(x)), -1)
                p_idx = next((i for i, x in enumerate(headers_row) if str(x).strip() == "盈餘總分配率"), -1)
                
                if c_idx != -1 and p_idx != -1:
                    cells_to_update = []
                    for r, row in enumerate(data):
                        if r == 0: continue # 跳過表頭
                        code = str(row[c_idx]).split('.')[0].strip()
                        
                        # 如果代號有在我們算好的名單裡，就更新它
                        if code in magic_payout_dict:
                            # 💡 這裡就是關鍵修正：加上 str() 把它變成文字，Google 就不會生氣了！
                            cells_to_update.append(gspread.Cell(row=r+1, col=p_idx+1, value=str(magic_payout_dict[code])))
                    
                    # 批次大量更新 Google Sheet
                    if cells_to_update:
                        ws.update_cells(cells_to_update, value_input_option='USER_ENTERED')
                        total_updated += len(cells_to_update)
                        st.write(f"📝 分頁 **[{ws.title}]** 成功更新了 {len(cells_to_update)} 檔！")
                else:
                    st.warning(f"⚠️ 分頁 **[{ws.title}]** 找不到名為「盈餘總分配率」的欄位，已跳過。")

            status.update(label=f"🎉 任務圓滿完成！總共更新了 {total_updated} 檔股票的配息率！", state="complete")
            st.balloons() # 噴發慶祝氣球

        except Exception as e:
            status.update(label="發生錯誤", state="error")
            st.error(f"系統錯誤: {e}")

st.divider()
st.caption("🚀 2026 戰略指揮 - 專屬財務後台更新系統")
