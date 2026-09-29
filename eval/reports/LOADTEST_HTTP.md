# Load test of the HTTP surface (fixture warehouse, model simulated at 1800 ms)

Limits in force: max_concurrent_chats=32 chat_queue_max=64 chat_queue_wait_seconds=5.0 retry_after_seconds=3; rate limits raised out of the way for this run. Clients wait out Retry-After.

## Model answering



| clients | sent | ok | rate_limited_429 | busy_503 | other | served_per_s | ok_p50_ms | ok_p95_ms | refused_p95_ms | refusals_with_retry_after | wrong_outcome | tickets_written |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 200 | 200 | 0 | 0 | 0 | 4.4 | 1812.8 | 1834.9 | None | 0/0 | 0 | 0 |
| 32 | 200 | 200 | 0 | 0 | 0 | 15.7 | 1818.9 | 1862.0 | None | 0/0 | 0 | 0 |
| 64 | 200 | 200 | 0 | 0 | 0 | 15.8 | 3614.6 | 3624.8 | None | 0/0 | 0 | 0 |
| 128 | 384 | 256 | 0 | 128 | 0 | 17.5 | 5421.6 | 5448.7 | 5.7 | 128/128 | 0 | 0 |
| 256 | 768 | 256 | 0 | 512 | 0 | 17.5 | 5422.6 | 5437.5 | 2.0 | 512/512 | 0 | 0 |

## Model down: degraded resolution

A plain balance question is answered without the model

| clients | sent | ok | rate_limited_429 | busy_503 | other | served_per_s | ok_p50_ms | ok_p95_ms | refused_p95_ms | refusals_with_retry_after | wrong_outcome | tickets_written |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 200 | 200 | 0 | 0 | 0 | 394.3 | 19.8 | 23.5 | None | 0/0 | 0 | 0 |
| 32 | 200 | 200 | 0 | 0 | 0 | 382.9 | 78.5 | 83.4 | None | 0/0 | 0 | 0 |
| 64 | 200 | 200 | 0 | 0 | 0 | 292.6 | 141.5 | 278.4 | None | 0/0 | 0 | 0 |
| 128 | 384 | 384 | 0 | 0 | 0 | 251.0 | 215.7 | 853.9 | None | 0/0 | 0 | 0 |
| 256 | 768 | 758 | 0 | 10 | 0 | 114.4 | 904.7 | 5328.3 | 22.0 | 10/10 | 0 | 0 |

## Model down: handoff

A request that needs the model is handed to a person, and a ticket is written

| clients | sent | ok | rate_limited_429 | busy_503 | other | served_per_s | ok_p50_ms | ok_p95_ms | refused_p95_ms | refusals_with_retry_after | wrong_outcome | tickets_written |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 200 | 200 | 0 | 0 | 0 | 228.1 | 34.1 | 48.9 | None | 0/0 | 0 | 200 |
| 32 | 200 | 200 | 0 | 0 | 0 | 216.7 | 135.0 | 235.3 | None | 0/0 | 0 | 200 |
| 64 | 200 | 200 | 0 | 0 | 0 | 216.3 | 225.1 | 390.5 | None | 0/0 | 0 | 200 |
| 128 | 384 | 372 | 0 | 12 | 0 | 90.5 | 803.4 | 2673.4 | 13.6 | 12/12 | 0 | 372 |
| 256 | 768 | 728 | 0 | 40 | 0 | 52.0 | 2284.1 | 9619.2 | 6404.5 | 40/40 | 0 | 728 |

Server counters at the end: {'inflight': 0, 'waiting': 0, 'inflight_peak': 32, 'waiting_peak': 64, 'rejected': {'busy': 702, 'too_large': 0, 'slow_body': 0}, 'served': 4674}

## Per-session rate limit (default 20/min)

30 back-to-back messages from one session: 20 answered, 10 refused with 429; Retry-After on the first refusal: 24 s.
