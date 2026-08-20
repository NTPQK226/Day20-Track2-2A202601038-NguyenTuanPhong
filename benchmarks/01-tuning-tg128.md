# 01 - Tune: thread-count sweep

Model gemma-4-E2B-it-UD-Q4_K_XL.gguf · host Windows-AMD64 · llama.cpp 10488
CPU: **12 physical · 16 logical** cores · 
gl=99 · metric 	g128

| threads (-t) | tg128 (tok/s) | vs best |
|:--|--:|--:|
| 1 | 84.0 | 98% |
| 6 | 85.3 | 100% |
| 12 | 84.0 | 98% |
| 16 | 84.0 | 98% |
| 32 | 84.1 | 99% |

**Best**: -t 6 at 85.3 tok/s
**Slowest tested**: -t 1 at 84.0 tok/s (1.02x spread)
**Against the physical-core default** (-t 12, 84.0 tok/s): 1.02x

Use this in your run:

`ash
LAB_N_THREADS=6 make bench
`

## Your explanation

Đường cong thông lượng (throughput curve) thực tế đo được gần như phẳng (giao động rất hẹp từ 84.0 đến 85.3 tok/s, tỉ lệ chênh lệch chỉ 1.02x). Nguyên nhân và cơ chế hệ thống đằng sau hiện tượng này bao gồm:

1. Cơ chế GPU Offload (ngl=99): Do model Gemma 4 E2B (2.97 GB) nằm gọn hoàn toàn trong 4GB VRAM của card NVIDIA GeForce RTX 3050 Ti, toàn bộ tính toán ma trận trong quá trình token generation (tg128) được xử lý trực tiếp bởi các nhân CUDA và băng thông VRAM của GPU (GPU Memory Bandwidth Bound). CPU lúc này chỉ đóng vai trò host điều phối (kernel launch và context management), do đó việc tăng số lượng CPU worker threads không tác động nhiều đến tốc độ sinh token của GPU.

2. Điểm tối ưu ở -t 6: CPU Intel Core i5-12500H sở hữu kiến trúc lai (4 Performance-cores với Hyper-Threading và 8 Efficient-cores). Mức thiết lập -t 6 đạt đỉnh nhẹ (85.3 tok/s) do tận dụng tối ưu các P-cores hiệu năng cao để xử lý host scheduling mà không gặp hiện tượng nghẽn do phân bổ thread sang các E-cores xung nhịp thấp.

3. Hiện tượng Oversubscription ở thread cao (-t 12, 16, 32): Khi tăng vượt quá 6 threads lên 12, 16 hay 32 threads, chi phí chuyển đổi ngữ cảnh (context switching overhead) và đồng bộ hoá threadpool tăng lên, làm giảm nhẹ hiệu quả điều phối xuống 84.0 tok/s.

Kết luận: Đối với trường hợp offload toàn bộ model lên GPU, thiết lập -t 6 mang lại hiệu quả cân bằng nhất giữa chi phí CPU host và tốc độ kernel launch của GPU.
