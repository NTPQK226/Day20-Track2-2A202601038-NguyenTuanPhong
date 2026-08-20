# Bonus B1 - Prebuilt vs source build

Host Windows-AMD64 · CPU 12th Gen Intel(R) Core(TM) i5-12500H
Vector extensions detected: none
llama.cpp 10488 both sides · 	hreads=12 ·
**both pinned to 
gl=0** so this isolates the compiler ·
metric 	g128, 3 repetitions

> **Backend mismatch, handled.** The prebuilt binary sees
> ['CUDA0: NVIDIA GeForce RTX 3050 Ti Laptop GPU (4095 MiB, 3295 MiB free)'] and your source build sees (no devices).
> Left at -ngl 99 this comparison would have measured the accelerator and printed
> it under a compiler headline, so both sides were pinned to -ngl 0.

| Binary | Built for | tg128 (tok/s) | Relative |
|:--|--:|--:|--:|
| prebuilt release | runtime CPU dispatch | 18.9 | 1.00x |
| your source build | this CPU (-DGGML_NATIVE=ON) | 6.7 | 0.36x |

On this machine, the prebuilt binary is **2.81x faster**.

before: 18.9 tok/s (prebuilt release)
after:  6.7 tok/s (source build, -DGGML_NATIVE=ON)
speedup: 0.36x

Same source revision, same model, same backend, same -ngl -- the only difference
is what the compiler was allowed to assume about the CPU.

## Your explanation

Kết quả thực nghiệm cho thấy bản prebuilt binary chính thức đạt 18.9 tok/s, nhanh hơn 2.81x so với bản source build GCC native (6.7 tok/s) khi cùng chạy thuần trên CPU (-ngl 0).

Nguyên nhân kỹ thuật đằng sau hiện tượng này:
1. Toolchain Optimization: Bản prebuilt binary chính thức của llama.cpp trên Windows được biên dịch bằng Microsoft Visual C++ (MSVC) kết hợp với các assembly kernel intrinsics (AVX2/FMA) được viết tay và tối ưu hóa sâu cho memory alignment và threadpool của Windows OS.
2. Runtime Dynamic Dispatch: Bản prebuilt tích hợp cơ chế runtime CPU feature detection, tự động chọn các kernel GEMM tối ưu nhất cho tập lệnh của CPU Intel Core i5-12500H tại thời điểm thực thi.
3. GCC trên Windows MinGW: Bản build mã nguồn bằng GCC trên Windows gặp hạn chế về khả năng tự động vector hoá (auto-vectorization) và đồng bộ hoá OpenMP trên nền Windows thread scheduler, dẫn đến hiệu năng tính toán ma trận CPU thấp hơn.

Kết luận: Việc so sánh này chứng minh rằng bên cạnh cờ biên dịch (-march=native), chất lượng của compiler toolchain và các kernel SIMD viết tay đóng vai trò then chốt đối với hiệu năng tính toán CPU.
