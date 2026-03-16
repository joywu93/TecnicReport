# ==========================================
# 📂 檔案名稱： update_finance.py (V187 聰明反推 Q4 恢復版)
# 💡 策略： 恢復「累計盈餘扣除前三季得 Q4」的演算邏輯！財報不全時照樣先填 EPS。
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
    
    # 抓取官方綜合損益表 API
    try:
        res_detail = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap11_L", headers=headers, verify=False, timeout=30).json()
        res_detail_o = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap11_O", headers=headers, verify=False, timeout=30).json()
        all_detail = res_detail + res_detail_o
    except Exception as e: 
        print(f"API 抓取失敗: {e}")
        return

    stats = {}
    for item in all_detail:
        # 鎖定 114 年 第 4 季 (即最新全年度)
        if str(item.get('年度')) == "114" and str(item.get('季別')) == "4":
            code = str(item.get('公司代號')).strip()
            op = force_float(item.get('營業利益（損失）'))
            pre_t = force_float(item.get('繼續營業單位稅前淨利（淨損）'))
            annual_eps = force_float(item.get('基本每股盈餘（元）')) # 這是全年度的累計 EPS
            
            # 只要有抓到 EPS 就先存起來，不管 op 是不是 0
            stats[code] = {"annual_eps": annual_eps, "op": op, "pre_t": pre_t}

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        if not data: continue
        
        h = data[0]
        i_c = next((i for i, x in enumerate(h) if "代號" in x), -1)
        i_nop = next((i for i, x in enumerate(h) if "業外" in x and "%" in x), -1)
        
        # 🔍 自動尋找表單中的 Q1, Q2, Q3 欄位位置，準備用來做數學扣除
        i_q1 = next((i for i, x in enumerate(h) if "Q1" in str(x).upper()), -1)
        i_q2 = next((i for i, x in enumerate(h) if "Q2" in str(x).upper()), -1)
        i_q3 = next((i for i, x in enumerate(h) if "Q3" in str(x).upper()), -1)
        
        if i_c == -1: continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            
            if code in stats:
                d = stats[code]
                
                # 讀取表單上已有的前三季 EPS
                q1_eps = force_float(row[i_q1]) if i_q1 != -1 and i_q1 < len(row) else 0.0
                q2_eps = force_float(row[i_q2]) if i_q2 != -1 and i_q2 < len(row) else 0.0
                q3_eps = force_float(row[i_q3]) if i_q3 != -1 and i_q3 < len(row) else 0.0
                
                # 🌟 恢復您的精準邏輯：Q4 單季 = 全年累計 - (Q1+Q2+Q3)
                q4_eps_calculated = round(d["annual_eps"] - q1_eps - q2_eps - q3_eps, 2)
                
                # 先把算好的 Q4 EPS 填入 AO 欄 (col=41)！不管損益表齊不齊全都會填！
                cells.append(gspread.Cell(row=r_idx, col=41, value=q4_eps_calculated))
                
                # 接下來檢查損益表明細。如果有營業利益，才計算並更新業外佔比
                if d["pre_t"] != 0 and d["op"] != 0:
                    non_op_ratio = round(((d["pre_t"] - d["op"]) / d["pre_t"]) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_nop+1, value=non_op_ratio))
                    
                    # 更新 AP、AQ 證據欄
                    cells.append(gspread.Cell(row=r_idx, col=42, value=d["op"]))
                    cells.append(gspread.Cell(row=r_idx, col=43, value=d["pre_t"]))
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"📊 {ws.title} 掃描與 Q4 演算填寫完成。")

if __name__ == "__main__":
    fetch_and_update()
