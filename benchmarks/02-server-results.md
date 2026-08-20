# 02 - Serve: load test + saturation reading

Host `Windows-AMD64` · llama.cpp `b10488` ·
`--parallel 4` · `ctx=2048` · `threads=12` ·
`ngl=99`

| Users | Reqs | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Eff. concurrency | Failures |
|:--|--:|--:|--:|--:|--:|--:|--:|
| 10 | 173 | 2.97 | 2300 | 3800 | 5100 | 7.3 | 0.0% |
| 50 | 172 | 2.91 | 15000 | 17000 | 17000 | 40.5 | 0.0% |

*Effective concurrency = RPS x average latency (Little's Law) -- how many requests were
really in flight, regardless of how many users locust simulated. It counts queued requests
too, so the occupancy/slot ratio can legitimately exceed 1.0; it is occupancy, not
utilisation. For true slot utilisation use the server's own gauges (`make metrics`).*

## What these two runs say

| Going from 10 to 50 users | |
|:--|--:|
| Offered load | 5x |
| Throughput actually delivered | **0.98x** (20% of linear) |
| P95 latency | **4.47x** |
| Effective concurrency at 50 users | 40.5 vs `--parallel 4` slots (occupancy/slot ratio 10.12) |

**Saturated.** Throughput delivered only 0.98x for 5x the offered load, and effective concurrency (40.5) is at or above all 4 decode slots. Saturation sets in somewhere at or below 50 users; the load you added beyond that point became queue time rather than throughput.

Throughput moved 0.98x while P95 moved 4.47x. That gap is the goodput argument: past saturation you buy throughput by spending latency, and if your SLO is a P95 target then the requests you added are no longer being served within it. (This lab does not fix an SLO number for you -- pick one in your write-up and state how much goodput you keep at it.)

## Your reading

Server đạt điểm bão hoà (saturation) ngay ở mức tải vượt quá 10 users và bão hoà hoàn toàn ở 50 users.

Bằng chứng thuyết phục:
1. Throughput plateau: Khi tăng tải mô phỏng 5x (từ 10 lên 50 users), RPS thực tế hoàn toàn không tăng mà giữ nguyên ở mức 2.91 - 2.97 req/s (đạt 0.98x).
2. P95 latency phồng lên 4.47x (từ 3.8s lên 17.0s), P50 tăng 6.52x (từ 2.3s lên 15.0s). Toàn bộ độ trễ tăng thêm này là queue time (thời gian nghẽn hàng đợi), được chứng thực bởi chỉ số requests_deferred = 45 trong khi requests_processing chạm trần 4/4 slots.
3. Effective concurrency tăng vọt lên 40.5, vượt gấp 10.12 lần số slot phục vụ (--parallel 4).

Giải pháp nâng Goodput@SLO:
Nếu đặt mục tiêu SLO P95 <= 5.0s, ở mức 50 users thì 0% request đạt SLO (goodput = 0). Để nâng Goodput@SLO, knob tôi sẽ ưu tiên thay đổi đầu tiên là tăng số lượng slot song song `--parallel` (ví dụ từ 4 lên 8 slots) kết hợp với bật KV cache quantization (`--ctk q8_0 --ctv q8_0`). Lý do chọn knob này thay vì tăng thread: Tăng slot giải quyết trực tiếp hiện tượng nghẽn hàng đợi (queue time bottleneck), cho phép GPU xử lý đồng thời nhiều luồng sinh token hơn trong mỗi bước tính toán GEMM, từ đó kéo giảm hàng đợi deferred và đưa P95 latency trở về dưới ngưỡng SLO.
