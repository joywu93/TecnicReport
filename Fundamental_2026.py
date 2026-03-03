import streamlit as st
import pandas as pd
import io

# ==========================================
# 網頁基本設定
# ==========================================
st.set_page_config(page_title="2026 股市戰略指揮中心", layout="wide")
st.title("🛠️ V18 終極照妖鏡版 (純診斷不運算)")
st.markdown("💡 **除錯模式啟動：** 先不跑任何公式，我們直接看看系統到底有沒有把檔案讀進來！")

# ==========================================
# 側邊欄：檔案上傳
# ==========================================
st.sidebar.header("📥 資料庫匯入區")
uploaded_file = st.sidebar.file_uploader("請上傳 Goodinfo 報表 (CSV/Excel)", type=["xlsx", "csv"])

# ==========================================
# 暴力解碼與顯示區
# ==========================================
if uploaded_file is not None:
    st.warning("🔄 檔案已接收，系統正在嘗試暴力解碼中...")
    try:
        file_name = uploaded_file.name.lower()
        uploaded_file.seek(0)
        
        # 如果是 Excel 格式
        if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
            df = pd.read_excel(uploaded_file)
            st.success("✅ 成功使用 Excel 引擎讀取！")
            
        # 如果是 CSV 格式 (進行多重編碼測試)
        else:
            file_bytes = uploaded_file.read()
            try:
                # 測試台灣常見的 CP950 編碼
                csv_str = file_bytes.decode('cp950')
                st.success("✅ 成功使用 CP950 (Big5) 繁體中文編碼讀取！")
            except:
                try:
                    # 測試 UTF-8 編碼
                    csv_str = file_bytes.decode('utf-8-sig')
                    st.success("✅ 成功使用 UTF-8 編碼讀取！")
                except:
                    # 暴力強制解碼 (忽略無法辨識的亂碼)
                    csv_str = file_bytes.decode('big5', errors='ignore')
                    st.warning("⚠️ 遭遇亂碼，已啟用強制忽略模式讀取！")
            
            df = pd.read_csv(io.StringIO(csv_str))
            
        # 💡 照妖鏡發威：把系統看到的資料直接印出來！
        st.subheader("🔍 步驟一：系統看到的「欄位名稱」")
        st.write(df.columns.tolist())
        
        st.subheader("🔍 步驟二：系統看到的「前 5 筆資料」")
        st.dataframe(df.head(5))
        
    except Exception as e:
        st.error(f"❌ 解析慘遭滑鐵盧！錯誤代碼：{e}")
        
else:
    st.info("👈 請把檔案丟進左側上傳區，讓我們看看它的真面目！")
