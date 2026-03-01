# (前略：STOCK_NAMES 字典保持不變)

if submit_btn:
    raw_tk = re.findall(r'\d{4}', ticker_input)
    user_tk = sorted(list(dict.fromkeys(raw_tk)))
    st.session_state["stocks"] = ", ".join(user_tk)
    sheet = init_sheet()
    if sheet:
        try:
            # 💡 尋找您的 Email 所在行
            cell = sheet.find(email_in)
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 💡 同步更新清單與時間 (假設清單在 col+1, 時間在 col+2)
            sheet.update_cell(cell.row, cell.col + 1, ", ".join(user_tk))
            sheet.update_cell(cell.row, cell.col + 2, now_str) 
            st.success(f"✅ 雲端同步成功！時間：{now_str}")
        except: 
            st.warning("⚠️ 找不到 Email，無法自動更新雲端時間")

        # (後略：analyze_strategy 執行邏輯...)
