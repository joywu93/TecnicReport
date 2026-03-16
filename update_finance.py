# ==========================================
# 📂 檔案名稱： update_finance.py (V189 財報真理版)
# 💡 策略： 接上正確的「綜合損益表」API，套用指揮官的精準公式！
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
    
    # 🌟 真正正確的綜合損益表 API (14 結尾)
    url_twse = "https://openapi.twse.com.tw/v1/opendata/t187ap14_L"
    url_tpex = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O"
    
    try:
        print("📡 正在向官方 Open Data 下載最新【綜合損益表】...")
        res_twse = requests.get(url_twse, headers=headers, verify=False, timeout=30).json()
        res_tpex = requests.get(url_tpex, headers=headers, verify=False, timeout=30).json()
        all_detail = res_twse + res_tpex
    except Exception as e: 
        print(f"❌ API 抓取失敗: {e}")
        return

    stats = {}
    radar_log = {} 
    
    for item in all_detail:
        code = str(item.get('公司代號')).strip()
        y = str(item.get('年度'))
        q = str(item.get('季別'))
        
        # 🔍 真相雷達紀錄：官方資料庫現在到底放了什麼季度
        if code in ['3023', '3030']:
            if code not in radar_log: radar_log[code] = []
            radar_log[code].append(f"{y}年Q{q}")

        # 鎖定 114 年 第 4 季 (目前官方可能還沒放，程式會靜靜等待)
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

    # 🖨️ 印出搜查報告給您看
    print("\n" + "="*40)
    print("🕵️ 官方 API 財報更新進度雷達 (重點關注 3023, 3030)")
    for code in ['3023', '3030']:
        if code in radar_log:
            available_qs = sorted(list(set(radar_log[code])))
            print(f"👉 [{code}] 官方目前最新財報進度：{available_qs}")
            if code not in stats:
                print(f"   ❌ 等待中：官方尚未釋出 {code} 的 114年 Q4 財報！")
            else:
                print(f"   ✅ 讚啦：已抓到 {code} 的 114年 Q4 財報，準備寫入表單！")
        else:
            print(f"👉 找不到 {code} 的任何資料。")
    print("="*40 + "\n")

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        if not data: continue
        
        h = data[0]
        i_c = next((i for i, x in enumerate(h) if "代號" in x), -1)
        
        # 自動定位您的各個欄位
        i_q1 = next((i for i, x in enumerate(h) if "Q1" in str(x).upper()), -1)
        i_q2 = next((i for i, x in enumerate(h) if "Q2" in str(x).upper()), -1)
        i_q3 = next((i for i, x in enumerate(h) if "Q3" in str(x).upper()), -1)
        i_nop = next((i for i, x in enumerate(h) if "業外" in str(x) and "%" in str(x)), -1)
        i_op_m = next((i for i, x in enumerate(h) if "營利率" in str(x) and "%" in str(x)), -1)
        
        if i_c == -1: continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            
            if code in stats:
                d = stats[code]
                
                # 1. 演算 Q4 EPS = 全年累計 - 前三季
                q1_eps = force_float(row[i_q1]) if i_q1 != -1 and i_q1 < len(row) else 0.0
                q2_eps = force_float(row[i_q2]) if i_q2 != -1 and i_q2 < len(row) else 0.0
                q3_eps = force_float(row[i_q3]) if i_q3 != -1 and i_q3 < len(row) else 0.0
                q4_eps_calculated = round(d["annual_eps"] - q1_eps - q2_eps - q3_eps, 2)
                
                # 將算好的 Q4 填入 AO 欄 (col=41)
                cells.append(gspread.Cell(row=r_idx, col=41, value=q4_eps_calculated))
                
                # 2. 演算 業外收入% = 營業外 / (營業外 + 營業利益)
                denominator_non_op = d["non_op_income"] + d["op_profit"]
                if denominator_non_op != 0 and i_nop != -1:
                    non_op_ratio = round((d["non_op_income"] / denominator_non_op) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_nop+1, value=non_op_ratio))
                    
                # 3. 演算 營利率% = 營業利益 / 營業收入
                if d["revenue"] != 0 and i_op_m != -1:
                    op_margin = round((d["op_profit"] / d["revenue"]) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_op_m+1, value=op_margin))
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"📊 {ws.title}：Q4 EPS、營利率、業外佔比 更新寫入完成。")

if __name__ == "__main__":
    fetch_and_update()
