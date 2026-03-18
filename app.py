# ==========================================
# 📂 檔案名稱： update_finance.py (V193 終極完美版)
# 💡 策略： 鎖定四大標準表頭 + 暴力破解政府財報欄位名稱
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
            revenue = 0.0
            op_profit = 0.0
            non_op_income = 0.0
            annual_eps = 0.0
            
            # 🌟 V193 關鍵 1：用關鍵字掃描，無視政府全形半形括號陷阱！不怕讀不到數字！
            for k, v in item.items():
                if '營業收入' in k: revenue = force_float(v)
                elif '營業利益' in k: op_profit = force_float(v)
                elif '營業外收入' in k: non_op_income = force_float(v)
                elif '每股盈餘' in k: annual_eps = force_float(v)

            stats[code] = {
                "annual_eps": annual_eps, 
                "revenue": revenue,
                "op_profit": op_profit,
                "non_op_income": non_op_income
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
        
        # 尋找計算用的前三季
        i_q1 = next((i for i, x in enumerate(h) if "25Q1" in str(x).upper()), -1)
        i_q2 = next((i for i, x in enumerate(h) if "25Q2" in str(x).upper()), -1)
        i_q3 = next((i for i, x in enumerate(h) if "25Q3" in str(x).upper()), -1)
        
        # 🌟 V193 關鍵 2：完全依照您的「四大標準表頭」精準定位！
        i_op_m_target = next((i for i, x in enumerate(h) if "最新單季營益率" in str(x)), -1)
        i_q4_target = next((i for i, x in enumerate(h) if "25Q4單季每股盈餘" in str(x)), -1)
        i_accum_eps_target = next((i for i, x in enumerate(h) if "最新累季每股盈餘" in str(x)), -1)
        i_nop_target = next((i for i, x in enumerate(h) if "最新單季業外損益佔稅前淨利" in str(x)), -1)
        
        if i_c == -1: continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            
            # 只針對有資料的股票進行計算
            if code in stats:
                d = stats[code]
                
                # 1. 填入 累計 EPS
                if i_accum_eps_target != -1:
                    cells.append(gspread.Cell(row=r_idx, col=i_accum_eps_target+1, value=d["annual_eps"]))

                # 2. 填入 Q4 EPS (累計 - 前三季)
                if i_q4_target != -1:
                    q1_eps = force_float(row[i_q1]) if i_q1 != -1 and i_q1 < len(row) else 0.0
                    q2_eps = force_float(row[i_q2]) if i_q2 != -1 and i_q2 < len(row) else 0.0
                    q3_eps = force_float(row[i_q3]) if i_q3 != -1 and i_q3 < len(row) else 0.0
                    q4_eps_calculated = round(d["annual_eps"] - q1_eps - q2_eps - q3_eps, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_q4_target+1, value=q4_eps_calculated))
                
                # 3. 填入 單季營益率%
                if d["revenue"] != 0 and i_op_m_target != -1:
                    op_margin = round((d["op_profit"] / d["revenue"]) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_op_m_target+1, value=op_margin))
                    
                # 4. 填入 業外損益佔稅前淨利% 
                # (稅前淨利 = 營業利益 + 業外收入及支出)
                pre_tax_profit = d["non_op_income"] + d["op_profit"]
                if pre_tax_profit != 0 and i_nop_target != -1:
                    non_op_ratio = round((d["non_op_income"] / pre_tax_profit) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_nop_target+1, value=non_op_ratio))
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"📊 {ws.title} 更新完成。寫入了 {len(cells)} 個儲存格。")

if __name__ == "__main__":
    fetch_and_update()
