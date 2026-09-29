# Load test of the HTTP surface (fixture warehouse, model simulated at 1800 ms)

Limits in force: max_concurrent_chats=32 chat_queue_max=64 chat_queue_wait_seconds=5.0 retry_after_seconds=3; rate limits raised out of the way for this run. Clients wait out Retry-After.

## Model answering

| clients | sent | ok | rate_limited_429 | busy_503 | other | served_per_s | ok_p50_ms | ok_p95_ms | refused_p95_ms | refusals_with_retry_after |
|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 200 | 200 | 0 | 0 | 0 | 4.4 | 1810.7 | 1818.9 | None | 0/0 |
| 32 | 200 | 200 | 0 | 0 | 0 | 15.7 | 1811.0 | 1873.9 | None | 0/0 |
| 64 | 200 | 200 | 0 | 0 | 0 | 15.7 | 3617.3 | 3644.4 | None | 0/0 |
| 128 | 384 | 256 | 0 | 128 | 0 | 17.4 | 5424.5 | 5459.1 | 1.6 | 128/128 |
| 256 | 768 | 256 | 0 | 512 | 0 | 17.4 | 5428.1 | 5503.0 | 1.6 | 512/512 |

## Model down (every turn falls back to a handoff)

| clients | sent | ok | rate_limited_429 | busy_503 | other | served_per_s | ok_p50_ms | ok_p95_ms | refused_p95_ms | refusals_with_retry_after |
|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 200 | 200 | 0 | 0 | 0 | 420.8 | 18.4 | 21.9 | None | 0/0 |
| 32 | 200 | 200 | 0 | 0 | 0 | 395.0 | 74.1 | 93.5 | None | 0/0 |
| 64 | 200 | 200 | 0 | 0 | 0 | 330.0 | 129.4 | 212.0 | None | 0/0 |
| 128 | 384 | 375 | 0 | 9 | 0 | 106.0 | 298.5 | 2286.8 | 8.3 | 9/9 |
| 256 | 768 | 768 | 0 | 0 | 0 | 140.2 | 1029.7 | 3836.8 | None | 0/0 |

Server counters at the end: {'inflight': 0, 'waiting': 0, 'inflight_peak': 32, 'waiting_peak': 64, 'rejected': {'busy': 649, 'too_large': 0, 'slow_body': 0}, 'served': 2935}

## Per-session rate limit (default 20/min)

30 back-to-back messages from one session: 20 answered, 10 refused with 429; Retry-After on the first refusal: 24 s.
