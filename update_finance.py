# ==========================================
# 📂 檔案名稱： update_finance.py (V191 精準鎖定版)
# 💡 策略： 配合最新表頭，精準鎖定 Y欄、Z欄、T欄！
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
    if v is None or str(v).strip() == "": return 0.0
    s = str(v).strip().replace(',', '')
    if s.startswith('(') and s.endswith(')'): s = '-' + s[1:-1]
    try: return float(s)
    except: return 0.0

def fetch_and_update():
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    url_twse = "https://openapi.twse.com.tw/v1/opendata/t187ap14_L"
    url_tpex = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O"
    
    try:
        print("📡 下載最新【綜合損益表】...")
        res_twse = requests.get(url_twse, headers=headers, verify=False, timeout=30).json()
        res_tpex = requests.get(url_tpex, headers=headers, verify=False, timeout=30).json()
        all_detail = res_twse + res_tpex
    except Exception as e: 
        print(f"❌ API 抓取失敗: {e}")
        return

    stats = {}
    for item in all_detail:
        code = str(item.get('公司代號')).strip()
        y = str(item.get('年度'))
        q = str(item.get('季別'))
        
        # 鎖定 114 年 第 4 季
        if y == "114" and q == "4":
            revenue = force_float(item.get('營業收入'))
            op_profit = force_float(item.get('營業利益（損失）'))
            annual_eps = force_float(item.get('基本每股盈餘（元）'))
            stats[code] = {
                "annual_eps": annual_eps, 
                "revenue": revenue,
                "op_profit": op_profit
            }

    print(f"✅ 成功獲取 114年 Q4 資料，共 {len(stats)} 檔股票準備寫入！\n")

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        if not data: continue
        
        h = data[0]
        i_c = next((i for i, x in enumerate(h) if "代號" in x), -1)
        
        # 🌟 V191 關鍵：依照最新截圖重新設定關鍵字！ 🌟
        # 1. 找前三季EPS來扣
        i_q1 = next((i for i, x in enumerate(h) if "25Q1" in str(x).upper()), -1)
        i_q2 = next((i for i, x in enumerate(h) if "25Q2" in str(x).upper()), -1)
        i_q3 = next((i for i, x in enumerate(h) if "25Q3" in str(x).upper()), -1)
        
        # 2. 找目標欄位：Y欄 (Q4)、Z欄 (累計)、T欄 (營益率)
        i_q4_target = next((i for i, x in enumerate(h) if "25Q4" in str(x).upper() and "單季" in str(x)), -1)
        i_accum_eps_target = next((i for i, x in enumerate(h) if "最新累季每股盈餘" in str(x)), -1)
        i_op_m_target = next((i for i, x in enumerate(h) if "營益率" in str(x) and "%" in str(x)), -1)
        
        if i_c == -1: continue

        print(f"🔍 {ws.title} 定位狀態：25Q4單季(Y)={i_q4_target}, 最新累季(Z)={i_accum_eps_target}, 營益率(T)={i_op_m_target}")

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            
            if code in stats:
                d = stats[code]
                
                # 1. 填入 Z欄：全年累計 EPS (直接拿官方資料)
                if i_accum_eps_target != -1:
                    cells.append(gspread.Cell(row=r_idx, col=i_accum_eps_target+1, value=d["annual_eps"]))

                # 2. 填入 Y欄：算出 Q4 EPS (累計 - 前三季)
                if i_q4_target != -1:
                    q1_eps = force_float(row[i_q1]) if i_q1 != -1 and i_q1 < len(row) else 0.0
                    q2_eps = force_float(row[i_q2]) if i_q2 != -1 and i_q2 < len(row) else 0.0
                    q3_eps = force_float(row[i_q3]) if i_q3 != -1 and i_q3 < len(row) else 0.0
                    q4_eps_calculated = round(d["annual_eps"] - q1_eps - q2_eps - q3_eps, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_q4_target+1, value=q4_eps_calculated))
                
                # 3. 填入 T欄：營益率%
                if d["revenue"] != 0 and i_op_m_target != -1:
                    op_margin = round((d["op_profit"] / d["revenue"]) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_op_m_target+1, value=op_margin))
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"📊 {ws.title} 更新完成。寫入了 {len(cells)} 個儲存格。")
        else:
            print(f"⚠️ {ws.title} 沒有寫入。可能是找不到對應的表頭名稱。")

if __name__ == "__main__":
    fetch_and_update()
