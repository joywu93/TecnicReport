# ==========================================
# 📂 檔案名稱： update_payout.py (年度專屬一次性更新版)
# 💡 策略： 完全沿用 update_finance.py0317 的極簡精準架構
# ==========================================
import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

def get_gspread_client():
    key_data = os.environ.get("GOOGLE_KEY_JSON")
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def fetch_and_update_payout():
    headers = {'User-Agent': 'Mozilla/5.0'}
    magic_payout_dict = {}

    print("📡 下載最新【每日收盤行情】計算盈餘分配率...")
    
    # 1. 上市 (TWSE)
    try:
        url_twse = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        res_twse = requests.get(url_twse, headers=headers, verify=False, timeout=30).json()
        for item in res_twse:
            code = str(item.get('Code', '')).strip()
            try:
                pe = float(str(item.get('PeRatio', '0')).replace(',', ''))
                dy = float(str(item.get('DividendYield', '0')).replace(',', ''))
                if pe > 0 and dy > 0: 
                    magic_payout_dict[code] = round(pe * dy, 2)
            except: pass
    except Exception as e: 
        print(f"❌ 上市 API 抓取失敗: {e}")

    # 2. 上櫃 (TPEx)
    try:
        url_tpex = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_perwd_quotes"
        res_tpex = requests.get(url_tpex, headers=headers, verify=False, timeout=30).json()
        for item in res_tpex:
            code = str(item.get('SecuritiesCompanyCode', '')).strip()
            try:
                pe = float(str(item.get('PERatio', '0')).replace(',', ''))
                dy = float(str(item.get('Dividendyield', '0')).replace(',', ''))
                if pe > 0 and dy > 0: 
                    magic_payout_dict[code] = round(pe * dy, 2)
            except: pass
    except Exception as e: 
        print(f"❌ 上櫃 API 抓取失敗: {e}")

    if not magic_payout_dict:
        print("⚠️ 無法取得資料，程式終止。")
        return

    print(f"✅ 成功計算出 {len(magic_payout_dict)} 檔股票的盈餘分配率！準備寫入！\n")

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        # 鎖定目標分頁
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        if not data: continue
        
        h = data[0]
        i_c = next((i for i, x in enumerate(h) if "代號" in str(x)), -1)
        
        # 🌟 完全依照 0317 版的精準定位邏輯
        i_payout_target = next((i for i, x in enumerate(h) if "盈餘總分配率" in str(x)), -1)
        
        if i_c == -1 or i_payout_target == -1: 
            continue

        cells = []
        # 從第二行開始處理資料 (start=2 確保 gspread 的 row index 正確)
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            
            # 只針對有資料的股票進行計算寫入
            if code in magic_payout_dict:
                # 依據 0317 寫法，直接將計算好的數值塞入 Cell
                val = str(magic_payout_dict[code]) # 加上 str 保險，避免 Google API 報錯
                cells.append(gspread.Cell(row=r_idx, col=i_payout_target+1, value=val))
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"📊 {ws.title} 更新完成。寫入了 {len(cells)} 個儲存格。")

if __name__ == "__main__":
    fetch_and_update_payout()
