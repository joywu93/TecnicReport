# ==========================================
# 📂 檔案名稱： update_finance.py (V193 雙效全能完美版)
# 💡 策略： 股價同步更新 + 鎖定四大標準表頭 + 暴力破解政府財報欄位名稱
# ==========================================

import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# V193 專屬的 Google Sheet 網址
MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

def get_gspread_client():
    # 🌟 防呆設計：不管您在 GitHub 設定的金鑰叫什麼名字，都抓得到！
    key_data = os.environ.get("GOOGLE_CREDENTIALS") or os.environ.get("GOOGLE_KEY_JSON")
    if not key_data: raise ValueError("找不到 Google 金鑰，請檢查 GitHub Secrets 設定！")
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def force_float(v):
    if v is None or str(v).strip() == "": return 0.0
    s = str(v).strip().replace(',', '')
    if s.startswith('(') and s.endswith(')'): s = '-' + s[1:-1]
    try: return float(s)
    except: return 0.0

def safe_parse_price(val):
    try:
        s = str(val).replace(',', '').strip()
        if not s or s == '-' or s == '--' or s == '---': return None
        return float(s)
    except: return None

def fetch_and_update():
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # ---------------------------------------------------------
    # 任務一：抓取 EPS 與 四大財報指標
    # ---------------------------------------------------------
    url_twse = "https://openapi.twse.com.tw/v1/opendata/t187ap14_L"
    url_tpex = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O"
    
    try:
        print("📡 任務一：下載最新【綜合損益表】...")
        res_twse = requests.get(url_twse, headers=headers, verify=False, timeout=30).json()
        res_tpex = requests.get(url_tpex, headers=headers, verify=False, timeout=30).json()
        all_detail = res_twse + res_tpex
    except Exception as e: 
        print(f"❌ API 抓取失敗: {e}")
        all_detail = []

    stats = {}
    for item in all_detail:
        code = str(item.get('公司代號', item.get('co_id', ''))).strip()
        if not code: continue
        y = str(item.get('年度'))
        q = str(item.get('季別'))
        
        # 鎖定 114 年 第 4 季
        if y == "114" and q == "4":
            revenue = 0.0
            op_profit = 0.0
            non_op_income = 0.0
            annual_eps = 0.0
            
            # 🌟 V193 關鍵 1：用關鍵字掃描，無視政府全形半形括號陷阱！
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

    print(f"✅ 成功獲取 114年 Q4 資料，共 {len(stats)} 檔財報準備寫入！")

    # ---------------------------------------------------------
    # 任務二：抓取盤後股價
    # ---------------------------------------------------------
    print("\n📡 任務二：下載最新【盤後收盤價】...")
    price_dict = {}
    try:
        res_twse_price = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=headers, verify=False, timeout=30).json()
        if isinstance(res_twse_price, list):
            for i in res_twse_price:
                cp = safe_parse_price(i.get('ClosingPrice'))
                if cp is not None: price_dict[str(i.get('Code', '')).strip()] = cp
    except Exception as e: print(f"⚠️ 台灣證交所股價抓取失敗: {e}")

    try:
        res_tpex_price = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers=headers, verify=False, timeout=30).json()
        if isinstance(res_tpex_price, list):
            for i in res_tpex_price:
                cp = safe_parse_price(i.get('Close'))
                if cp is not None: price_dict[str(i.get('SecuritiesCompanyCode', '')).strip()] = cp
    except Exception as e: print(f"⚠️ 櫃買中心股價抓取失敗: {e}")
    
    print(f"✅ 成功抓取 {len(price_dict)} 檔股價報價。")

    # ---------------------------------------------------------
    # 任務三：開始寫入 Google 表單
    # ---------------------------------------------------------
    print("\n📝 任務三：開始寫入 Google 表單...")
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    except Exception as e:
        print(f"❌ Google 表單連線失敗: {e}")
        return
    
    # 鎖定目標分頁
    target_sheets = [ws for ws in spreadsheet.worksheets() if any(n in ws.title for n in ["當年度表", "個股總表", "總表", "金融股"])]
    
    for ws in target_sheets:
        data = ws.get_all_values()
        if not data: continue
        
        h = data[0]
        i_c = next((i for i, x in enumerate(h) if str(x).strip() in ["代號", "股票代號", "證券代號"]), -1)
        p_idx = next((i for i, x in enumerate(h) if str(x).strip() in ["成交", "股價", "最新股價", "收盤價"]), -1)
        
        # 尋找計算用的前三季
        i_q1 = next((i for i, x in enumerate(h) if "25Q1" in str(x).upper()), -1)
        i_q2 = next((i for i, x in enumerate(h) if "25Q2" in str(x).upper()), -1)
        i_q3 = next((i for i, x in enumerate(h) if "25Q3" in str(x).upper()), -1)
        
        # 🌟 V193 關鍵 2：四大標準表頭精準定位
        i_op_m_target = next((i for i, x in enumerate(h) if "最新單季營益率" in str(x)), -1)
        i_q4_target = next((i for i, x in enumerate(h) if "25Q4單季每股盈餘" in str(x)), -1)
        i_accum_eps_target = next((i for i, x in enumerate(h) if "最新累季每股盈餘" in str(x)), -1)
        i_nop_target = next((i for i, x in enumerate(h) if "最新單季業外損益佔稅前淨利" in str(x)), -1)
        
        if i_c == -1: continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            if i_c >= len(row): continue
            code = str(row[i_c]).split('.')[0].strip()
            
            # 【寫入股價】
            if p_idx != -1 and code in price_dict:
                cells.append(gspread.Cell(row=r_idx, col=p_idx+1, value=price_dict[code]))
            
            # 【寫入財報四大數據】
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
            print(f"📊 {ws.title} 更新完成。共寫入了 {len(cells)} 個儲存格 (含股價與財報)。")

if __name__ == "__main__":
    fetch_and_update()
