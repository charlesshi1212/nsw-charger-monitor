# Publisher pacing fix - 26 October 2026

The earlier publisher used one sleep and `time.monotonic()` to estimate the remaining delay. On the reviewed Windows Python 3.12 environment, this clock used 15.625 ms ticks. A separate high-resolution measurement of 120 publications observed five intervals below 0.1 seconds, with a minimum of 0.085215 seconds.

## Implementation

- Encode JSON before the pacing wait.
- Use integer nanosecond deadlines from `time.perf_counter_ns()`.
- Recheck the deadline after each sleep, including an early wake.
- Start the next full interval after the previous successful broker PUBACK. This is deliberately conservative; acknowledgment/transport overhead adds to total replay time.
- Reject non-finite delays and values below 0.1 seconds before connecting.
- Clean up the MQTT client if connection/readiness fails, as well as after replay.

Event ordering, payloads, IDs, QoS 1 and duplicate handling retain their existing behavior. No runtime packages were added.

## Validation

The three new unit regressions passed. They cover early wakeups, invalid delays and waiting a full interval after each broker acknowledgment, including a slow acknowledgment.

The isolated real-MQTT check sent all 412 demo events and then replayed 10 duplicates. It measured 420 adjacent publication intervals across the two runs (411 plus 9), all at least 0.1 seconds. The minimum measured interval was **0.1007431 seconds**. All 412 unique events were committed, with 48 completed sessions and 1222.27 kWh; duplicate replay left the metrics unchanged. The output is retained in `publisher_timing_validation.json`, including raw high-resolution timestamps and intervals.

The measurement records entry to the real Paho publish wrapper. It does not claim that dashboard refreshes or subscriber receipt times are spaced exactly 0.1 seconds apart. The full 46,084-event MQTT stream was not replayed in this fix validation.

Reproduce from the project root using the Python environment described in README:

```bash
python -m unittest discover -s tests -v
python scripts/validate_mqtt_pacing.py
```

These new checks do not recreate the original report's missing nine-test suite. Update report/AI disclosure file references to match the final submission, and label the timing-fix evidence as a new run.
