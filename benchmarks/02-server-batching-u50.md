# 02 - Continuous batching under load (u50)

Hust `Windows-AMD64` · `--parallel 4` · 15 samples over
60s at 2.0s intervals · raw CSV: `02-server-metrics-u50.csv`

| Gauge | Peak observed |
|:--|--:|
| `n_busy_slots_per_decode` (avg/decode) | 3.88 of 4 slots (97%) |
| `requests_processing` | 4 |
| `requests_deferred` | 45 |
| `kv_cache_usage_ratio` | n/a · not exported by llama.cpp `b10488` |
| `tokens_predicted_total` (final) | 19011 |

Highest sampled value was **3.88 of 4** slots. Note this gauge is llama.cpp's *average* busy slots per decode step, so the number below is the highest average we sampled, not an instantaneous maximum batch width. A peak near 1 means
requests were served one at a time -- either the load was too light to overlap, or
they arrived too far apart. A peak approaching `--parallel` means the scheduler was
genuinely packing concurrent requests into shared decode steps.
`requests_deferred` went above zero: more requests arrived than there were slots, so some waited. That wait is the queue time in your P95.

## Your observation

Mức peak batch width đo được từ gauge nội bộ của llama-server đạt 3.88/4 slots (97% công suất thiất kế), chứng minh cơ chế continuous batching hoạt động hiệu quả khi gộp đồng thời các request vao cùng một lượt decode bước tính toán ma trận.

Về sự khác biệt giữa peak batch width (3.88) và effective concurrency (40.5) từ Little's Law:
- Peak batch width (3.88) đo số lượng request thực tế đang được GPU thực thi giải mã song song trong VRAM (tối đa bằng số slot = 4).
- Effective concurrency (40.5) phản ánh tổng số request đang tồn tại trong toàn bộ hệ thống serving (bao gồm 4 request đang xử lý và ~36-45 request đang nam chò trong hàng đợi deferred).

Cả hai con số này hoàn toàn nhất quán: Server đã hoạt động hết 97% công suất slot tính toán, và toàn bộ 5x tải tăng thêm đãchuyển hña thành hàng đợi chó đợi (requests_deferred = 45), giải thích trực tiếp nguyên nhân P95 latency tăng từ 3.8s lên 17.0s.
