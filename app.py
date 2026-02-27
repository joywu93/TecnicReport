# --- 增加趨勢線掃描功能 ---
def detect_trendline(df):
    try:
        # 抓取最近 60 天的最低價
        lows = df['Low'].tail(60).astype(float)
        
        # 尋找兩個局部轉折低點 (Pivot Lows)
        # 第一個低點 (區間內最低)
        l1_val = float(lows.min())
        l1_idx = lows.idxmin()
        
        # 第二個低點 (L1之後，且比L1高的局部低)
        post_l1 = lows.loc[l1_idx:]
        if len(post_l1) < 5: return None
        
        l2_val = float(post_l1.iloc[1:].min())
        l2_idx = post_l1.iloc[1:].idxmin()
        
        # 計算斜率 m = (y2-y1) / (x2-x1)
        # 利用 index 差距當作 x 軸
        dist = (df.index.get_loc(l2_idx) - df.index.get_loc(l1_idx))
        if dist == 0: return None
        slope = (l2_val - l1_val) / dist
        
        # 換算出今天的預計支撐價 (今日與 L2 的距離)
        today_dist = len(df) - 1 - df.index.get_loc(l2_idx)
        support_price = l2_val + (slope * today_dist)
        
        curr_p = float(df['Close'].iloc[-1])
        gap = ((curr_p - support_price) / support_price) * 100
        
        # 如果股價靠近這條線 (正負 3% 內)，就顯示警報
        if abs(gap) <= 3.0:
            return f"🛡️ 趨勢線支撐：{support_price:.2f} (距 {gap:.1f}%)"
        return None
    except:
        return None
