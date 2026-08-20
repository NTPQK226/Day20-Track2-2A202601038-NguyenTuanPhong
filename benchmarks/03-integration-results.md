# 03 - Integrate: RAG pipeline run

Host Windows-AMD64 · llama.cpp 10488 ·
retrieval backend: **keyword overlap** · 3 queries

| Query | Contexts retrieved | embed (ms) | retrieve (ms) | llm (ms) | total (ms) |
|:--|--:|--:|--:|--:|--:|
| Why is goodput more useful than raw throughp... | goodput, paged, radix | 0.0 | 0.3 | 3056.3 | 3056.5 |
| What problem does PagedAttention actually so... | paged, radix, disagg | 0.0 | 0.0 | 2759.4 | 2759.5 |
| When does splitting prefill and decode help?... | disagg, radix, batching | 0.0 | 0.0 | 2686.7 | 2686.8 |

Mean per stage (ms): embed **0.0** · retrieve **0.1** ·
llm **2834.1** · total **2834.3**
Dominant stage: **llm** (100% of total)

## Answers returned

**Why is goodput more useful than raw throughput?**

> Goodput@SLO counts only the requests per second that met the TTFT and TPOT targets. Throughput at saturation ignores SLOs.

**What problem does PagedAttention actually solve?**

> PagedAttention stores the KV cache in non-contiguous pages, removing the internal fragmentation that wasted most GPU memory.

**When does splitting prefill and decode help?**

> Splitting prefill and decode helps because prefill is compute-bound and decode is memory-bandwidth-bound.


## Which N16-N19 pieces are real

Khai báo trạng thái thành phần tích hợp:
- N16 Cloud/IaC: stub
- N17 Data pipeline: stub
- N18 Lakehouse: stub
- N19 Vector + features: stub (sử dụng thuật toán keyword overlap fallback trong bộ nhớ)
- N20 Model Serving: real (llama-server chạy cục bộ trên GPU NVIDIA RTX 3050 Ti qua OpenAI-compatible API)

Phân tích Bottleneck & Tối ưu hoá:
- Phân rã độ trễ hoàn toàn khớp với kỳ vọng lý thuyết: Stage llm chiếm trọn 100% tổng thời gian xử lý (~2834.1 ms trên tổng số 2834.3 ms). Khâu retrieve và embed dạng stub thực thi trong bộ nhớ siêu nhanh (< 0.5 ms), trong khi LLM phải thực hiện prefill prompt dài và decode tuần tự từng token qua mạng nơ-ron sâu.
- Để giảm độ trễ toàn bộ pipeline đi 2x (từ ~2.8s xuống ~1.4s), bắt buộc phải tối ưu trực tiếp vào stage **LLM Generation**:
  1. Áp dụng **Prompt Caching / Prefix Caching**: Tái sử dụng KV cache của system prompt và các văn bản context đã truy xuất để đưa thời gian prefill về ~0ms.
  2. Áp dụng **Speculative Decoding** (sử dụng MTP head mtp-gemma-4-E2B-it.gguf hoặc draft model nhỏ hơn) để dự đoán trước 2-3 tokens trong một lượt forward pass của GPU, giúp tăng tốc độ decode lên 1.5x - 2.0x.
