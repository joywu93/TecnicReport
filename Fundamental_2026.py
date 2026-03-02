def calculate_2026_strategic_model(
    rev_24q1, rev_24q2, rev_24q3, rev_24q4,  # 2024 各季營收
    rev_25q1, rev_25q2, rev_25q3, rev_25q4,  # 2025 各季營收
    avg_op_margin,        # 近兩年平均營業利益率 (%)
    shares_outstanding,   # 發行股數 (億股)
    recent_payout_ratio,  # 最近一年度配息率 (%)
    current_price         # 最新股價
):
    # 1. 計算近兩年各季與全年總和
    total_24_25 = sum([rev_24q1, rev_24q2, rev_24q3, rev_24q4, rev_25q1, rev_25q2, rev_25q3, rev_25q4])
    q1_24_25_total = rev_24q1 + rev_25q1
    q2_24_25_total = rev_24q2 + rev_25q2
    q3_24_25_total = rev_24q3 + rev_25q3
    q4_24_25_total = rev_24q4 + rev_25q4

    # 2. 您的專屬公式：精算預估 26Q1 營收 (平滑化 Q4 基期)
    avg_q4 = (rev_24q4 + rev_25q4) / 2
    est_26q1_rev = rev_25q4 * rev_25q1 / avg_q4 if avg_q4 > 0 else 0

    # 3. 季節性權重還原：計算預估 2026 全年營收
    seasonality_multiplier = total_24_25 / q1_24_25_total if q1_24_25_total > 0 else 0
    est_2026_total_rev = est_26q1_rev * seasonality_multiplier

    # 4. 各季雷達追蹤：推算 2026 各季預估營收目標 (供未來與實際值比對)
    est_26q2_rev = est_2026_total_rev * (q2_24_25_total / total_24_25)
    est_26q3_rev = est_2026_total_rev * (q3_24_25_total / total_24_25)
    est_26q4_rev = est_2026_total_rev * (q4_24_25_total / total_24_25)

    # 5. 推算 2026 EPS (本業營收 * 營益率 * 0.8 / 股本)
    est_2026_op_profit = est_2026_total_rev * (avg_op_margin / 100)
    est_2026_net_profit = est_2026_op_profit * 0.8  # 扣除20%營所稅估算
    est_2026_eps = est_2026_net_profit / shares_outstanding if shares_outstanding > 0 else 0

    # 6. 配息防呆與前瞻殖利率
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio == 0 else recent_payout_ratio)
    forward_yield = (est_2026_eps * (calc_payout_ratio / 100)) / current_price * 100 if current_price > 0 else 0

    return {
        "預估26Q1營收": est_26q1_rev,
        "預估26Q2營收": est_26q2_rev,  # 未來可用於追蹤落差
        "預估26全年營收": est_2026_total_rev,
        "預估今年EPS(元)": est_2026_eps,
        "運算配息率(%)": calc_payout_ratio,
        "前瞻殖利率(%)": forward_yield
    }
