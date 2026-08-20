# Bonus - GPU offload sweep

Host Windows-AMD64 · backend(s) 
vidia_cuda, vulkan ·
llama.cpp 10488 · 	hreads=12 · metric 	g128

| -ngl | tg128 (tok/s) | vs -ngl 0 | vs best |
|:--|--:|--:|--:|
| 0 | 5.7 | 1.00x | 7% |
| 8 | 19.3 | 3.41x | 25% |
| 16 | 24.4 | 4.32x | 32% |
| 24 | 41.4 | 7.32x | 54% |
| 32 | 56.4 | 9.96x | 73% |
| 99 | 77.3 | 13.66x | 100% |

Best: -ngl 99 at 77.3 tok/s
-- 13.66x faster than CPU-only.

Where the curve flattens tells you the model ran out of layers to move. Where it
*peaks below* full offload tells you something did not fit and the accelerator
started paying to fetch weights it could not hold.

## Your finding

Thực nghiệm sweep qua các mức offload chứng minh rằng Full GPU Offload (-ngl 99) mang lại hiệu năng cao nhất tuyệt đối trên máy tính này (đạt 77.3 tok/s, tăng tốc 13.66x so với CPU-only ở 5.7 tok/s).

Cơ chế phân tích đường cong tăng tốc:
1. Kiến trúc Model: Gemma 4 E2B sở hữu 35 transformer layers và dung lượng weight 2.97 GB.
2. Quá trình Partial Offload (-ngl 8 -> 32): Tốc độ sinh token tăng dần đều và tuyến tính từ 19.3 tok/s lên 56.4 tok/s. Cứ mỗi layer được chuyển từ CPU sang GPU, lượng dữ liệu weight cần phải đọc qua bus bộ nhớ RAM hệ thống giảm xuống, giảm bớt chi phí nghẽn băng thông PCIe giữa host và device.
3. Điểm bứt phá ở Full Offload (-ngl 99): Khi offload toàn bộ 35/35 layers vào 4GB VRAM của card rời NVIDIA RTX 3050 Ti, toàn bộ chu trình tính toán ma trận (GEMV/GEMM) được xử lý khép kín trong GPU VRAM với băng thông bộ nhớ lên tới ~192 GB/s, loại bỏ hoàn toàn chi phí truyền nhận dữ liệu qua CPU host.

Kết luận: Card đồ hoạ RTX 3050 Ti 4GB VRAM đủ dung lượng chứa 100% weights của model 4-bit, do đó full offload (-ngl 99) là cấu hình tối ưu nhất mà không gặp phải giới hạn VRAM OOM hay nghẽn PCIe bus.
