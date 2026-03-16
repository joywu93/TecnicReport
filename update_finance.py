# ==========================================
# 📂 檔案名稱： update_finance.py (V188 真相雷達版)
# 💡 策略： 執行 Q4 演算，並在日誌中強制印出官方 API 的真實進度！
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

def force_float(v):
    if v is None or v == "": return 0.0
    s = str(v).strip().replace(',', '')
    if s.startswith('(') and s.endswith(')'): s = '-' + s[1:-1]
    try: return float(s)
    except: return 0.0

def fetch_and_update():
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        print("📡 正在向官方 Open Data 下載最新損益表...")
        res_detail = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap11_L", headers=headers, verify=False, timeout=30).json()
        res_detail_o = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap11_O", headers=headers, verify=False, timeout=30).json()
        all_detail = res_detail + res_detail_o
    except Exception as e: 
        print(f"❌ API 抓取失敗: {e}")
        return

    stats = {}
    radar_log = {} # 🔍 用來記錄官方到底有幾季的資料
    
    for item in all_detail:
        code = str(item.get('公司代號')).strip()
        y = str(item.get('年度'))
        q = str(item.get('季別'))
        
        # 🔍 真相雷達：記錄 3023 和 3030 目前在官方資料庫裡到底有哪些季度
        if code in ['3023', '3030']:
            if code not in radar_log:
                radar_log[code] = []
            radar_log[code].append(f"{y}年Q{q}")

        # 鎖定 114 年 第 4 季
        if y == "114" and q == "4":
            op = force_float(item.get('營業利益（損失）'))
            pre_t = force_float(item.get('繼續營業單位稅前淨利（淨損）'))
            annual_eps = force_float(item.get('基本每股盈餘（元）'))
            stats[code] = {"annual_eps": annual_eps, "op": op, "pre_t": pre_t}

    # 🖨️ 印出搜查報告給您看！
    print("\n" + "="*40)
    print("🕵️ 官方 API 資料庫搜查報告 (重點關注 3023, 3030)")
    for code in ['3023', '3030']:
        if code in radar_log:
            # 整理並印出官方目前擁有的季度
            available_qs = sorted(list(set(radar_log[code])))
            print(f"👉 [{code}] 官方目前有：{available_qs}")
            if code not in stats:
                print(f"   ❌ 結論：官方資料庫裡【沒有】{code} 的 114年 Q4 資料，所以程式無法填寫！")
            else:
                print(f"   ✅ 結論：已抓到 {code} 的 114年 Q4 資料，準備寫入！")
        else:
            print(f"👉 找不到 {code} 的任何資料。")
    print("="*40 + "\n")

    # --- 以下是寫入 Google Sheet 的邏輯 (與 V187 完全相同) ---
    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        if not data: continue
        
        h = data[0]
        i_c = next((i for i, x in enumerate(h) if "代號" in x), -1)
        i_nop = next((i for i, x in enumerate(h) if "業外" in x and "%" in x), -1)
        i_q1 = next((i for i, x in enumerate(h) if "Q1" in str(x).upper()), -1)
        i_q2 = next((i for i, x in enumerate(h) if "Q2" in str(x).upper()), -1)
        i_q3 = next((i for i, x in enumerate(h) if "Q3" in str(x).upper()), -1)
        
        if i_c == -1: continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            
            if code in stats:
                d = stats[code]
                q1_eps = force_float(row[i_q1]) if i_q1 != -1 and i_q1 < len(row) else 0.0
                q2_eps = force_float(row[i_q2]) if i_q2 != -1 and i_q2 < len(row) else 0.0
                q3_eps = force_float(row[i_q3]) if i_q3 != -1 and i_q3 < len(row) else 0.0
                
                # Q4 演算
                q4_eps_calculated = round(d["annual_eps"] - q1_eps - q2_eps - q3_eps, 2)
                cells.append(gspread.Cell(row=r_idx, col=41, value=q4_eps_calculated)) # AO欄
                
                # 業外佔比演算
                if d["pre_t"] != 0 and d["op"] != 0:
                    non_op_ratio = round(((d["pre_t"] - d["op"]) / d["pre_t"]) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_nop+1, value=non_op_ratio))
                    cells.append(gspread.Cell(row=r_idx, col=42, value=d["op"]))
                    cells.append(gspread.Cell(row=r_idx, col=43, value=d["pre_t"]))
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"📊 {ws.title} 掃描與 Q4 演算填寫完成。")

if __name__ == "__main__":
    fetch_and_update()
