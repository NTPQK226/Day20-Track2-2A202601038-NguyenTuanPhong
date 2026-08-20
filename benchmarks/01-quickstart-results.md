# 01 - Measure: latency baseline

Model Gemma 4 E2B · host Windows-AMD64 · llama.cpp 10488
Settings: 	hreads=12 
gl=99 ctx=2048
max_tokens=64 · warm-up discarded
Completed requests: UD-Q4_K_XL 10/10 · UD-Q2_K_XL 10/10

| Quantization | Size (GB) | Load (ms) | TTFT P50/P95 (ms) | TPOT P50/P95 (ms) | E2E P50/P95/P99 (ms) | Decode (tok/s) |
|:--|--:|--:|--:|--:|--:|--:|
| UD-Q4_K_XL | 2.97 | 9713 | 327 / 760 | 12.9 / 13.3 | 1136 / 1584 / 1584 | 77.2 |
| UD-Q2_K_XL | 2.24 | 7635 | 321 / 633 | 12.2 / 12.4 | 1092 / 1411 / 1411 | 81.7 |

- **TTFT** = prefill. Short prompts keep it small; long-context RAG is where it explodes.
- **TPOT** = per-output-token decode cost, bounded by memory bandwidth. decode tok/s = 1000 / TPOT_p50.
- UD-Q2_K_XL decodes **1.06x faster** than UD-Q4_K_XL here, for 0.73 GB less on disk.

## Your observation

Thực nghiệm đo đạc cho thấy bản 2-bit UD-Q2_K_XL (2.24 GB) nhẹ hơn 0.73 GB dung lượng và có tốc độ decode nhanh hơn khoảng 1.06x (81.7 tok/s so với 77.2 tok/s, TPOT giảm từ 12.9ms xuống 12.2ms) do kích thước weight nhỏ hơn giúp tiết kiệm băng thông bộ nhớ (memory bandwidth).

Để đánh giá chất lượng câu trả lời thực tế, em đã khởi động đồng thời cả hai server ở port 8080 (bản 4-bit) và port 8090 (bản 2-bit với cờ --compare) rồi gửi cùng một câu hỏi yêu cầu phân biệt prefill và decode phase. Kết quả thực nghiệm:
- Bản 4-bit UD-Q4_K_XL trả lời rất chặt chẽ và chuẩn xác về mặt thuật ngữ hệ thống (nhấn mạnh prefill là batch operation tính toán toàn bộ context, decode là autoregressive token generation từng bước một).
- Bản 2-bit UD-Q2_K_XL vẫn giữ được cấu trúc đọc hiểu tốt nhờ định dạng Unsloth Dynamic (UD), nhưng nội dung diễn đạt bị đơn giản hoá và lặp ý, thiếu các thuật ngữ kỹ thuật quan trọng.

Kết luận: Trên phần cứng laptop Intel Core i5-12500H và card rời NVIDIA RTX 3050 Ti (4GB VRAM), cả hai model đều được offload hoàn toàn vào GPU (ngl=99). Mức tăng tốc 5.8% của bản 2-bit là không đáng kể khi phải đánh đổi độ chính xác và khả năng suy luận của model Gemma 4 E2B. Do đó, bản 4-bit UD-Q4_K_XL là lựa chọn tối ưu và phù hợp nhất cho production serving trên máy này.
