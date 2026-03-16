# ==========================================
# 📂 檔案名稱： update_finance.py (V190 全自動導航版)
# 💡 策略： 解決寫入空值的問題！讓程式自動尋找表單裡的精準欄位！
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
            non_op_income = force_float(item.get('營業外收入及支出'))
            annual_eps = force_float(item.get('基本每股盈餘（元）'))
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
        
        # 🌟 V190 關鍵：自動導航找位子，不管欄位怎麼移動都不怕！
        i_q1 = next((i for i, x in enumerate(h) if x.strip().upper() == "Q1"), -1)
        i_q2 = next((i for i, x in enumerate(h) if x.strip().upper() == "Q2"), -1)
        i_q3 = next((i for i, x in enumerate(h) if x.strip().upper() == "Q3"), -1)
        i_q4 = next((i for i, x in enumerate(h) if x.strip().upper() == "Q4"), -1) # 自動找 Q4
        
        # 寬鬆比對：只要標題裡有「業外」就算數，不強求要有「%」
        i_nop = next((i for i, x in enumerate(h) if "業外" in str(x)), -1)
        # 寬鬆比對：只要標題裡有「營利率」就算數
        i_op_m = next((i for i, x in enumerate(h) if "營利率" in str(x)), -1)
        
        if i_c == -1: 
            print(f"⚠️ 在 {ws.title} 找不到代號欄位。")
            continue

        print(f"🔍 {ws.title} 定位狀態：Q4={i_q4}, 業外={i_nop}, 營利率={i_op_m}")

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            
            if code in stats:
                d = stats[code]
                
                # 1. 演算 Q4 EPS (如果找不到 Q4 欄位就不寫)
                if i_q4 != -1:
                    q1_eps = force_float(row[i_q1]) if i_q1 != -1 and i_q1 < len(row) else 0.0
                    q2_eps = force_float(row[i_q2]) if i_q2 != -1 and i_q2 < len(row) else 0.0
                    q3_eps = force_float(row[i_q3]) if i_q3 != -1 and i_q3 < len(row) else 0.0
                    q4_eps_calculated = round(d["annual_eps"] - q1_eps - q2_eps - q3_eps, 2)
                    # 自動填到 i_q4 那一欄！
                    cells.append(gspread.Cell(row=r_idx, col=i_q4+1, value=q4_eps_calculated))
                
                # 2. 演算 業外收入%
                denominator_non_op = d["non_op_income"] + d["op_profit"]
                if denominator_non_op != 0 and i_nop != -1:
                    non_op_ratio = round((d["non_op_income"] / denominator_non_op) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_nop+1, value=non_op_ratio))
                    
                # 3. 演算 營利率%
                if d["revenue"] != 0 and i_op_m != -1:
                    op_margin = round((d["op_profit"] / d["revenue"]) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_op_m+1, value=op_margin))
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"📊 {ws.title} 更新完成。寫入了 {len(cells)} 個儲存格。")
        else:
            print(f"⚠️ {ws.title} 沒有寫入任何資料。可能是定位失敗，請檢查欄位標題。")

if __name__ == "__main__":
    fetch_and_update()
