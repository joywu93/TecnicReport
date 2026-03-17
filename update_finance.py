# ==========================================
# 📂 檔案名稱： update_finance.py (V194 股利整合最終版)
# 💡 策略： 雙雷達啟動！同時抓取「Q4財報」與「最新公告股利」，精準鎖定表頭！
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
    
    # --- 雷達 1：綜合損益表 (抓 EPS、營益率、業外) ---
    url_twse_fin = "https://openapi.twse.com.tw/v1/opendata/t187ap14_L"
    url_tpex_fin = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O"
    
    # --- 雷達 2：董事會決議股利分派 (抓 現金+股票股利) ---
    url_twse_div = "https://openapi.twse.com.tw/v1/opendata/t187ap08_L"
    url_tpex_div = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap08_O"
    
    try:
        print("📡 下載最新【綜合損益表】與【股利分派】...")
        res_fin = requests.get(url_twse_fin, headers=headers, verify=False, timeout=30).json() + \
                  requests.get(url_tpex_fin, headers=headers, verify=False, timeout=30).json()
                  
        res_div = requests.get(url_twse_div, headers=headers, verify=False, timeout=30).json() + \
                  requests.get(url_tpex_div, headers=headers, verify=False, timeout=30).json()
    except Exception as e: 
        print(f"❌ API 抓取失敗: {e}")
        return

    # 彙整財報數據
    stats = {}
    for item in res_fin:
        code = str(item.get('公司代號')).strip()
        y = str(item.get('年度'))
        q = str(item.get('季別'))
        
        # 鎖定 114 年 第 4 季
        if y == "114" and q == "4":
            revenue = op_profit = non_op_income = annual_eps = 0.0
            
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

    # 彙整股利數據
    div_stats = {}
    for item in res_div:
        code = str(item.get('公司代號')).strip()
        # 現金股利 (盈餘分配 + 公積發放)
        cash_1 = force_float(item.get('盈餘分配之現金股利(元/股)'))
        cash_2 = force_float(item.get('法定盈餘公積、資本公積發放之現金(元/股)'))
        # 股票股利 (盈餘轉增資 + 公積轉增資)
        stock_1 = force_float(item.get('盈餘轉增資配股(元/股)'))
        stock_2 = force_float(item.get('法定盈餘公積、資本公積轉增資配股(元/股)'))
        
        total_div = cash_1 + cash_2 + stock_1 + stock_2
        if code not in div_stats: div_stats[code] = 0.0
        div_stats[code] += total_div # 加總合計股利

    print(f"✅ 獲取 114年 Q4 財報：{len(stats)} 檔，最新公告股利：{len(div_stats)} 檔！\n")

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        if not data: continue
        
        h = data[0]
        i_c = next((i for i, x in enumerate(h) if "代號" in x), -1)
        
        # 財報計算用的前三季
        i_q1 = next((i for i, x in enumerate(h) if "25Q1" in str(x).upper()), -1)
        i_q2 = next((i for i, x in enumerate(h) if "25Q2" in str(x).upper()), -1)
        i_q3 = next((i for i, x in enumerate(h) if "25Q3" in str(x).upper()), -1)
        
        # 🌟 四大財報標準表頭 + 全新股利表頭
        i_op_m_target = next((i for i, x in enumerate(h) if "最新單季營益率" in str(x)), -1)
        i_q4_target = next((i for i, x in enumerate(h) if "25Q4單季每股盈餘" in str(x)), -1)
        i_accum_eps_target = next((i for i, x in enumerate(h) if "最新累季每股盈餘" in str(x)), -1)
        i_nop_target = next((i for i, x in enumerate(h) if "最新單季業外損益佔稅前淨利" in str(x)), -1)
        i_div_target = next((i for i, x in enumerate(h) if "2026合計股利" in str(x)), -1) # 🎯 股利目標欄位
        
        if i_c == -1: continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            
            # 處理財報寫入
            if code in stats:
                d = stats[code]
                if i_accum_eps_target != -1:
                    cells.append(gspread.Cell(row=r_idx, col=i_accum_eps_target+1, value=d["annual_eps"]))
                if i_q4_target != -1:
                    q1_eps = force_float(row[i_q1]) if i_q1 != -1 and i_q1 < len(row) else 0.0
                    q2_eps = force_float(row[i_q2]) if i_q2 != -1 and i_q2 < len(row) else 0.0
                    q3_eps = force_float(row[i_q3]) if i_q3 != -1 and i_q3 < len(row) else 0.0
                    q4_eps_calculated = round(d["annual_eps"] - q1_eps - q2_eps - q3_eps, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_q4_target+1, value=q4_eps_calculated))
                if d["revenue"] != 0 and i_op_m_target != -1:
                    op_margin = round((d["op_profit"] / d["revenue"]) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_op_m_target+1, value=op_margin))
                pre_tax_profit = d["non_op_income"] + d["op_profit"]
                if pre_tax_profit != 0 and i_nop_target != -1:
                    non_op_ratio = round((d["non_op_income"] / pre_tax_profit) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_nop_target+1, value=non_op_ratio))

            # 處理股利寫入 🎯
            if code in div_stats and i_div_target != -1:
                # 只填寫有公告股利的公司
                if div_stats[code] > 0:
                    cells.append(gspread.Cell(row=r_idx, col=i_div_target+1, value=round(div_stats[code], 2)))
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"📊 {ws.title} 更新完成。寫入了 {len(cells)} 個儲存格（含財報與股利）。")

if __name__ == "__main__":
    fetch_and_update()
