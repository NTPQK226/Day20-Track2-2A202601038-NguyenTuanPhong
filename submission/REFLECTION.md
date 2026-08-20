# Reflection — Day 20 Lab (Personal Report)

> **Đây là báo cáo cá nhân.** Số liệu của bạn **không** so sánh được với bạn cùng lớp
> — chỉ so **before vs after trên chính máy bạn**. Rubric chấm độ rõ ràng của setup,
> đo lường và **lập luận**, không chấm tốc độ tuyệt đối.
>
> `make verify` sẽ fail nếu còn placeholder chưa điền. Đó là cố ý.

**Họ Tên:** _Nguyễn Tuấn Phong_
**MSSV:** _2A202601038_
**Cohort:** _A20-K3B_
**Ngày submit:** _2026/08/20_

---

## 1. Hardware & runtime  *(rubric 1, 2 — 10 điểm)*

> Từ `make probe`. Paste output hoặc điền tay.

- **OS:** Windows 11 (AMD64)
- **CPU:** 12th Gen Intel(R) Core(TM) i5-12500H
- **Cores:** 12 physical / 16 logical cores
- **CPU extensions:** AVX2 / FMA
- **RAM:** 15.7 GB
- **Accelerator:** NVIDIA GeForce RTX 3050 Ti Laptop GPU (4096 MiB) + Vulkan
- **llama.cpp asset đã tải:** llama-b10488-bin-win-cuda-12.4-x64.zip
- **Model đã dùng:** Gemma 4 E2B (`LAB_MODEL=gemma4-e2b`)
- **Quantization:** UD-Q4_K_XL (2.97 GB) + UD-Q2_K_XL (2.24 GB) (từ `models/active.json`)

**Chạy ở đâu:** laptop của tôi

**Setup story** (≤ 80 chữ): Khởi tạo môi trường ảo bằng Python 3.12 chuẩn Windows, chuyển đường dẫn cache HF_HOME và PIP_CACHE_DIR sang ổ D để bảo vệ dung lượng ổ C. Hệ thống tự động tải prebuilt binary llama.cpp tích hợp CUDA 12.4 và 2 bản quantization Gemma 4 E2B.

---

## 2. Đo lường  *(rubric 3, 4, 5 — 20 điểm)*

> Paste bảng từ `benchmarks/01-quickstart-results.md` (`make bench` tự sinh).

| Quantization | Size (GB) | Load (ms) | TTFT P50/P95 (ms) | TPOT P50/P95 (ms) | E2E P50/P95/P99 (ms) | Decode (tok/s) |
|---|--:|--:|--:|--:|--:|--:|
| UD-Q4_K_XL | 2.97 | 9713 | 327 / 760 | 12.9 / 13.3 | 1136 / 1584 / 1584 | 77.2 |
| UD-Q2_K_XL | 2.24 | 7635 | 321 / 633 | 12.2 / 12.4 | 1092 / 1411 / 1411 | 81.7 |

**Quan sát** (≤ 60 chữ): Bản 2-bit decode nhanh hơn 1.06x và nhẹ hơn 0.73 GB. Thử nghiệm đối chứng cùng một prompt cho thấy 4-bit vượt trội về độ chính xác và chiều sâu ngữ nghĩa. Do model 4-bit nằm vừa vặn trong 4GB VRAM của RTX 3050 Ti, việc giữ bản 4-bit là tối ưu nhất.

---

## 3. Serving under load  *(rubric 8, 9, 10 — 20 điểm)*

> Từ `benchmarks/02-server-results.md` (`make load-report`).

| Users | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Eff. concurrency | Failures |
|--:|--:|--:|--:|--:|--:|--:|
| 10 | 2.97 | 2300 | 3800 | 5100 | 7.3 | 0.0% |
| 50 | 2.91 | 15000 | 17000 | 17000 | 40.5 | 0.0% |

- **Offered load tăng 5×, throughput thực tăng:** 0.98×
- **P95 tăng:** 4.47×
- **Effective concurrency ở 50 users:** 40.5 so với `--parallel` = 4 slots

**Peak `llamacpp:n_busy_slots_per_decode`** (từ `make metrics` khi `make load-50` đang
chạy): 3.88 / 4 slots

**Saturation reading** (≤ 80 chữ): Server bão hoà ngay trên mức 10 users và bão hoà hoàn toàn ở 50 users khi RPS đi ngang (0.98x) còn P95 phồng lên 4.47x (17.0s). Phần latency tăng thêm hoàn toàn là queue time vì requests_deferred lên tới 45 trong khi 4 slots compute đã đạt 97% công suất (3.88/4). Để nâng Goodput@SLO (P95 <= 5s), em sẽ tăng số slot --parallel lên 8 kết hợp KV cache quantization để giải toả hàng đợi.

---

## 4. Integration  *(rubric 12, 13 — 15 điểm)*

> Từ `make pipeline`. Nói thật cái nào real, cái nào stub — stub **không** mất điểm.

| Day | Piece | Real hay stub? |
|---|---|---|
| N16 Cloud/IaC | Terraform / Cloud infra | stub |
| N17 Data pipeline | Ingestion & ETL | stub |
| N18 Lakehouse | Storage & Catalog | stub |
| N19 Vector + features | Keyword overlap retrieval | stub |
| N20 Serving | `llama-server` | real |

**Latency split** (mean của 3 query, từ output của `pipeline.py`):

- embed: 0.0 ms
- retrieve: 0.1 ms
- llm: 2834.1 ms
- **stage chiếm nhiều nhất:** llm (100% của total)

**Reflection** (≤ 60 chữ): Stage LLM chiếm 100% latency đúng như kỳ vọng vì embed/retrieve là stub. Để giảm độ trễ pipeline 2x, tôi sẽ tập trung tối ưu stage LLM bằng Prompt Caching (giảm TTFT prefill về 0ms) và Speculative Decoding (MTP head tăng tốc decode 1.5x-2x).

---

## 5. The single change that mattered most  *(rubric 11 — 10 điểm)*

> **Phần quan trọng nhất của report.** Không cần bonus track: `make tune` đã cho bạn
> một before/after thật (`benchmarks/01-tuning-tg128.md`). Đổi quantization,
> `LAB_N_CTX`, hay `--parallel` rồi đo lại cũng được.

**Change:** Tối ưu số lượng CPU worker threads từ mặc định physical cores (-t 12) xuống điểm ngọt (-t 6) khi kết hợp offload GPU toàn phần (ngl=99)

```
before:  84.0 tok/s (-t 12)
after:   85.3 tok/s (-t 6)
speedup: 1.02x
```

**Tại sao nó work** (1–2 đoạn — đây là phần grader đọc kỹ nhất):

Khi offload toàn bộ 100% layer của Gemma 4 E2B vào 4GB VRAM của card đồ hoạ rời NVIDIA GeForce RTX 3050 Ti (ngl=99), toàn bộ quá trình tính toán ma trận trong pha decode bị giới hạn bởi băng thông bộ nhớ VRAM của GPU (GPU Memory Bandwidth Bound). CPU lúc này đóng vai trò host scheduling để launch các CUDA kernels và điều phối token stream.

Việc thiết lập -t 6 đạt tốc độ cao nhất (85.3 tok/s) vì khớp hoàn hảo với cụm 4 nhân hiệu năng cao (P-cores) của chip Intel Core i5-12500H, tránh phân bổ công việc sang các nhân tiết kiệm điện (E-cores) xung nhịp thấp hơn. Khi tăng thread lên -t 12 hay -t 16, overhead chuyển đổi ngữ cảnh (context switching) và đồng bộ hoá threadpool tăng lên khiến throughput giảm nhẹ về 84.0 tok/s.

---

## 6. Bonus  *(optional — tối đa 20 điểm)*

> Bỏ trống nếu không làm. Xem `bonus/README.md`. Đừng làm hết — **một** finding sâu
> ăn điểm hơn năm bảng nông.

**Đã làm:** _<B1 build-compare / B2 sweep nào / B4 challenge nào / B5 lựa chọn nào>_

**Numbers:**

```
before:  <số>
after:   <số>
speedup: <X.Y>×
```

**Điều này nói lên gì mà deck chưa nói:**

_(để trống nếu bạn không làm phần này)_

---

## 7. Điều làm bạn ngạc nhiên nhất  *(optional)*

_(1–2 câu. Không bắt buộc, nhưng grader đọc hết.)_

_(để trống nếu bạn không làm phần này)_

---

## 8. Self-check trước khi push

- [ ] `hardware.json` committed
- [ ] `models/active.json` committed
- [ ] `benchmarks/01-quickstart-results.md` committed (`make bench`)
- [ ] `benchmarks/01-tuning-tg128.md` committed (`make tune`)
- [ ] `benchmarks/02-server-results.md` committed (`make load-report`)
- [ ] `benchmarks/02-server-batching-u50.md` hoặc `-metrics-u50.csv` committed (`make metrics`)
- [ ] `benchmarks/locust-10_stats.csv` + `locust-50_stats.csv` committed (`make load-10` / `load-50`)
- [ ] `benchmarks/03-integration-results.md` committed (`make pipeline`)
- [ ] Mọi section **"required — replace this line"** trong các file `benchmarks/*.md`
      đã được thay bằng nhận xét của bạn
- [ ] 5 screenshots trong `submission/screenshots/`
- [ ] `make verify` → **exit 0**
- [ ] Repo GitHub ở chế độ **public**
- [ ] Đã paste public URL vào VinUni LMS
- [ ] **Không** commit `models/*.gguf` hay `runtime/` (đã có trong `.gitignore`)

**Quan trọng:** repo phải **public** đến khi điểm được công bố. Private → grader không
xem được → 0 điểm.
