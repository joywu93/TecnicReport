# ==========================================
# 📂 檔案名稱： update_payout.py (絕對精準鎖定版)
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
    
    # --- 1. 上市 (TWSE) ---
    try:
        url_twse = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        res_twse = requests.get(url_twse, headers=headers, verify=False, timeout=30).json()
        for item in res_twse:
            code = str(item.get('Code', '')).strip()
            pe, dy = 0.0, 0.0
            # 暴力掃描所有欄位，無視大小寫，確保絕對不會漏接官方 API 數據
            for k, v in item.items():
                k_low = k.lower()
                if 'pe' in k_low and 'ratio' in k_low:
                    try: pe = float(str(v).replace(',', ''))
                    except: pass
                if 'dividend' in k_low and 'yield' in k_low:
                    try: dy = float(str(v).replace(',', ''))
                    except: pass
            if pe > 0 and dy > 0:
                magic_payout_dict[code] = round(pe * dy, 2)
    except Exception as e: 
        print(f"❌ 上市 API 抓取失敗: {e}")

    # --- 2. 上櫃 (TPEx) ---
    try:
        url_tpex = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_perwd_quotes"
        res_tpex = requests.get(url_tpex, headers=headers, verify=False, timeout=30).json()
        for item in res_tpex:
            code = str(item.get('SecuritiesCompanyCode', '')).strip()
            pe, dy = 0.0, 0.0
            for k, v in item.items():
                k_low = k.lower()
                if 'pe' in k_low and 'ratio' in k_low:
                    try: pe = float(str(v).replace(',', ''))
                    except: pass
                if 'dividend' in k_low and 'yield' in k_low:
                    try: dy = float(str(v).replace(',', ''))
                    except: pass
            if pe > 0 and dy > 0:
                magic_payout_dict[code] = round(pe * dy, 2)
    except Exception as e: 
        print(f"❌ 上櫃 API 抓取失敗: {e}")

    if not magic_payout_dict:
        print("⚠️ 無法取得資料，程式終止。")
        return

    print(f"✅ 成功反推計算出 {len(magic_payout_dict)} 檔股票的盈餘分配率！\n")

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        if not data: continue
        
        h = data[0]
        
        # 🌟 絕對精準定位 1：只認名字完全等於「代號」的欄位 (避開產業代號)
        i_c = -1
        for i, x in enumerate(h):
            clean_name = str(x).replace('\n', '').strip()
            if clean_name in ["代號", "股票代號", "證券代號"]:
                i_c = i
                break
                
        # 🌟 絕對精準定位 2：找出真正的盈餘總分配率 (AB欄)
        i_payout_target = -1
        for i, x in enumerate(h):
            if "盈餘總分配率" in str(x):
                i_payout_target = i
                break
        
        if i_c == -1:
            print(f"⚠️ 分頁 [{ws.title}] 找不到名為「代號」的欄位，跳過。")
            continue
        if i_payout_target == -1:
            print(f"⚠️ 分頁 [{ws.title}] 找不到「盈餘總分配率」的欄位，跳過。")
            continue

        print(f"🔍 [{ws.title}] 鎖定成功！代號在第 {i_c+1} 欄，目標在第 {i_payout_target+1} 欄 (28 為 AB 欄)")

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            if i_c >= len(row): continue
            code = str(row[i_c]).split('.')[0].strip()
            
            if code in magic_payout_dict:
                val = str(magic_payout_dict[code])
                # 直接將計算出的數值覆蓋掉原本的公式
                cells.append(gspread.Cell(row=r_idx, col=i_payout_target+1, value=val))
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"📊 {ws.title} 更新完成。成功覆蓋了 {len(cells)} 檔股票的資料！")

if __name__ == "__main__":
    fetch_and_update_payout()
