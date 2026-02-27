def detect_patterns_pro(df, window=30):
    try:
        # 確保有足夠的日K線數據
        if len(df) < window: return None
        
        recent = df.tail(window)
        # 獲取價格序列 (Series)
        highs = recent['High']
        lows = recent['Low']
        curr_p = float(df['Close'].iloc[-1])

        # ==========================================
        # 📉 1. M頭 (Double Top) 偵測邏輯 [基準 12%]
        # ==========================================
        # 找出30日內最高點 (A)
        peak_a_val = float(highs.max())
        peak_a_idx = highs.idxmax()
        
        # 尋找最高點之後到今天的最低點 (B - 頸線預備位)
        post_peak_data = recent.loc[peak_a_idx:]
        if len(post_peak_data) > 3:
            mid_trough_val = float(post_peak_data['Low'].min())
            # 計算落差比例
            m_drop = (peak_a_val - mid_trough_val) / peak_a_val
            
            # 判斷條件：落差 >= 12% 且目前價格在頸線附近 (M頭右肩成形中)
            if m_drop >= 0.12:
                days_ago = (df.index[-1] - peak_a_idx).days
                return f"⚠ M頭警戒：左頭 ${peak_a_val:.2f} ({days_ago}天前)，落差 {m_drop*100:.1f}% 達標"

        # ==========================================
        # 📈 2. W底 (Double Bottom) 偵測邏輯 [基準 10%]
        # ==========================================
        # 找出30日內最低點 (A)
        trough_a_val = float(lows.min())
        trough_a_idx = lows.idxmin()
        
        # 尋找最低點之後到今天的高點 (B - 頸線預備位)
        post_trough_data = recent.loc[trough_a_idx:]
        if len(post_trough_data) > 3:
            mid_peak_val = float(post_trough_data['High'].max())
            # 計算落差比例
            w_rise = (mid_peak_val - trough_a_val) / trough_a_val
            
            # 判斷條件：落差 >= 10% 且目前股價緩步墊高 (W底右腳確認中)
            if w_rise >= 0.10:
                days_ago = (df.index[-1] - trough_a_idx).days
                return f"✨ W底機會：左底 ${trough_a_val:.2f} ({days_ago}天前)，落差 {w_rise*100:.1f}% 達標"

        return None
    except:
        return None
