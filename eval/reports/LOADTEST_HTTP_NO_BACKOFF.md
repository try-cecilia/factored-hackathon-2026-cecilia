# Load test of the HTTP surface (fixture warehouse, model simulated at 1800 ms)

Limits in force: max_concurrent_chats=32 chat_queue_max=64 chat_queue_wait_seconds=5.0 retry_after_seconds=3; rate limits raised out of the way for this run. Clients ignore Retry-After and resend at once.

## Model answering

| clients | sent | ok | rate_limited_429 | busy_503 | other | served_per_s | ok_p50_ms | ok_p95_ms | refused_p95_ms | refusals_with_retry_after |
|---|---|---|---|---|---|---|---|---|---|---|
| 128 | 384 | 96 | 0 | 288 | 0 | 17.2 | 3474.8 | 5129.0 | 156.6 | 288/288 |
| 256 | 768 | 128 | 0 | 640 | 0 | 17.3 | 3470.0 | 6295.5 | 1534.0 | 640/640 |

## Model down (every turn falls back to a handoff)

| clients | sent | ok | rate_limited_429 | busy_503 | other | served_per_s | ok_p50_ms | ok_p95_ms | refused_p95_ms | refusals_with_retry_after |
|---|---|---|---|---|---|---|---|---|---|---|
| 128 | 384 | 378 | 0 | 6 | 0 | 111.7 | 402.0 | 2311.9 | 26.7 | 6/6 |
| 256 | 768 | 766 | 0 | 2 | 0 | 113.0 | 1113.6 | 5462.1 | 5.8 | 2/2 |

Server counters at the end: {'inflight': 0, 'waiting': 0, 'inflight_peak': 32, 'waiting_peak': 64, 'rejected': {'busy': 936, 'too_large': 0, 'slow_body': 0}, 'served': 1400}

## Per-session rate limit (default 20/min)

30 back-to-back messages from one session: 20 answered, 10 refused with 429; Retry-After on the first refusal: 24 s.
