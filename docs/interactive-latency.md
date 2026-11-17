# Interactive latency, 0.14.1 preview

The inspected live connection reported direct WebRTC (host to srflx),
1920 x 1080 at 6.7 received FPS, about 7 ms decoding and 16–27 ms network RTT.
This rules out a TURN relay on that session. It does not establish the host's
capture time or the actual input application latency. Low FPS on an unchanged
screen alone is not a measurement of interactive responsiveness.

The lossless encoder now compares immutable RGB buffers in bulk, reduces the
changed bytes into 64-pixel tiles and creates PIL tile objects only when they
need transmission. Codec context restoration and exact edge pixels are kept.
The test source image may be mutated or resized between frames.

Host input now uses the bounded InputDispatcher for both the dedicated
authenticated input channel and the TLS fallback. Slow Windows input no longer
blocks the main receive thread or the dedicated channel's decrypting thread.
Only consecutive mouse moves are replaced with the latest position; button,
key, wheel and release events remain ordered. Permissions, password revocation,
protected desktop state and service geometry are checked by apply_input at
application time. No additional access or elevation is granted.

Session information has stable rows for capture/encoding times, frame delivery,
outstanding frame count/bytes and input application time/route. Metrics contain
no keys, passwords, typed text or file contents. They are shown within the
already-authorized session; disk recording still requires DESK_METRICS_PATH.

A synthetic 36-frame HD text workload with a small moving rectangle measured:

| Resolution | Previous median | New median | Exact RGB roundtrip |
| --- | ---: | ---: | --- |
| 1920 x 1080 | 15.62 ms | 10.21 ms | yes |
| 2560 x 1440 | 28.29 ms | 16.99 ms | yes |

These are local synthetic measurements, not proof of a live end-to-end fix.
An additional synthetic TCP socketpair experiment found no material Nagle
delay on this PC; no speculative transport setting was changed for that reason.
The previous 0.14.0 binaries under Microsoft review are left unchanged.
New binaries remain unsigned and require independent Windows validation.
