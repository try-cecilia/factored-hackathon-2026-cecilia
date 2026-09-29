# Load test of the HTTP surface (fixture warehouse, model simulated at 1800 ms)

Limits in force: max_concurrent_chats=32 chat_queue_max=64 chat_queue_wait_seconds=5.0 retry_after_seconds=3; rate limits raised out of the way for this run. Clients ignore Retry-After and resend at once.

## Model answering



| clients | sent | ok | rate_limited_429 | busy_503 | other | served_per_s | ok_p50_ms | ok_p95_ms | refused_p95_ms | refusals_with_retry_after | wrong_outcome | tickets_written |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 128 | 384 | 96 | 0 | 288 | 0 | 17.2 | 3457.7 | 5106.9 | 122.8 | 288/288 | 0 | 0 |
| 256 | 768 | 128 | 0 | 640 | 0 | 17.3 | 3466.7 | 6242.4 | 2048.4 | 640/640 | 0 | 0 |

## Model down: degraded resolution

A plain balance question is answered without the model

| clients | sent | ok | rate_limited_429 | busy_503 | other | served_per_s | ok_p50_ms | ok_p95_ms | refused_p95_ms | refusals_with_retry_after | wrong_outcome | tickets_written |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 128 | 384 | 376 | 0 | 8 | 0 | 150.6 | 338.8 | 1534.4 | 19.5 | 8/8 | 0 | 0 |
| 256 | 768 | 762 | 0 | 6 | 0 | 106.1 | 1059.6 | 5852.9 | 11.8 | 6/6 | 0 | 0 |

## Model down: handoff

A request that needs the model is handed to a person, and a ticket is written

| clients | sent | ok | rate_limited_429 | busy_503 | other | served_per_s | ok_p50_ms | ok_p95_ms | refused_p95_ms | refusals_with_retry_after | wrong_outcome | tickets_written |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 128 | 384 | 384 | 0 | 0 | 0 | 78.7 | 740.3 | 3384.8 | None | 0/0 | 0 | 384 |
| 256 | 768 | 742 | 0 | 26 | 0 | 58.8 | 2136.4 | 8781.2 | 6152.7 | 26/26 | 0 | 742 |

Server counters at the end: {'inflight': 0, 'waiting': 0, 'inflight_peak': 32, 'waiting_peak': 64, 'rejected': {'busy': 968, 'too_large': 0, 'slow_body': 0}, 'served': 2536}

## Per-session rate limit (default 20/min)

30 back-to-back messages from one session: 20 answered, 10 refused with 429; Retry-After on the first refusal: 24 s.
