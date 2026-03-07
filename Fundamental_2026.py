# 1. 算出去年 11、12 月的單月平均值
static_q1_avg = (rev_last_11 + rev_last_12) / 2

# 2. 乘以 3 個月，還原成 Q1 的一整季總標竿 (這就是圖表上那根紅柱的高度！)
static_q1_est_total = static_q1_avg * 3

# 3. 系統在最後輸出時，把它放進圖表的變數中 (_total_est_qs 的第 0 個位置就是 Q1)
"_total_est_qs": [static_q1_est_total, est_q2_rev_total, est_q3_rev_total, est_q4_rev_total]
