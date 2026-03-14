# ==========================================
# 📂 檔案名稱： test_moneydj.py (純測試，不寫入 Sheet)
# 💡 目的： 測試是否能成功抓取 MoneyDJ 的「營業利益」與「稅前淨利」
# ==========================================

import requests
import pandas as pd
from io import StringIO
import warnings

# 忽略 pandas 的 HTML 解析警告
warnings.filterwarnings("ignore", category=FutureWarning)

def test_moneydj_fetch():
    # 這是您提供的 MoneyDJ 電子零組件產業損益表網址
    url = "https://www.moneydj.com/z/ze/zez/zezn/zezn_EB013000_0_0_TB.djhtm"
    
    # 偽裝成正常的瀏覽器，避免被 MoneyDJ 阻擋
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    print(f"📡 嘗試連線 MoneyDJ: {url}")
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8' # 確保中文不會變成亂碼
        
        # 使用 pandas 強大的網頁表格解析功能
        dfs = pd.read_html(StringIO(response.text))
        
        # MoneyDJ 的網頁裡有很多表格(版面排版用的)，我們要找出包含「營業利益」的那一張
        target_df = None
        for df in dfs:
            # 將表格轉成文字，檢查有沒有我們要的關鍵字
            if '營業利益' in df.to_string():
                target_df = df
                break
        
        if target_df is not None:
            print("✅ 成功抓到核心財務表格！\n")
            
            # 尋找我們關心的個股 (信邦 3023)
            # 因為我們不知道 MoneyDJ 表格確切的欄位索引，所以直接掃描每一列
            found = False
            for index, row in target_df.iterrows():
                row_data = [str(x) for x in row.values]
                row_text = " | ".join(row_data)
                
                # 如果這一列包含 3023 或 信邦
                if '3023' in row_text or '信邦' in row_text:
                    print(f"🎯 發現【3023 信邦】的原始抓取資料：")
                    print("-" * 50)
                    print(row_text)
                    print("-" * 50)
                    found = True
                    break
            
            if not found:
                print("⚠️ 網頁抓取成功，但在這張表裡沒看到 3023 (可能在別的產業分類網頁中)。")
                
            # 為了研究，我們也印出表格的前 3 行，看看它的標題長怎樣
            print("\n👀 表格前 3 行結構預覽：")
            print(target_df.head(3).to_string())
            
        else:
            print("❌ 網頁讀取成功，但找不到包含財務數據的表格。")
            
    except Exception as e:
        print(f"💥 發生錯誤: {e}")

if __name__ == "__main__":
    test_moneydj_fetch()
