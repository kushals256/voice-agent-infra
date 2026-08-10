#!/usr/bin/env python3
"""Cold-start burst harness for the Vocobase challenge.

Implements exactly the section-5 test:

1. Open ``--steady`` (default 10) sessions and hold them open. With Cloud Run
   ``concurrency=1`` each lands on its own instance, so we are "at capacity".
2. Fire ``--burst`` (default 10) more sessions back-to-back as fast as we can
   issue them, keeping each alive as it connects.
3. For every burst session, measure wall time from the connection request to
   the first audio the bot speaks (the first binary WebSocket frame).
4. Report all values + median + p95, and PASS/FAIL against the 5s target.

The bot greets on connect, so we never need to send microphone audio; "first
audio" is simply the first binary frame the server sends.

Usage::

    python harness.py wss://<cloud-run-host>/ws-client
    python harness.py ws://localhost:7860/ws-client --steady 10 --burst 10
"""

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone

import websockets

FIRST_AUDIO_TIMEOUT = 120.0  # seconds to wait for first audio before giving up


async def run_session(uri, store, idx, connected_evt, stop_evt, label):
    """One conversation: connect, time first audio, then hold open until stop."""
    t0 = time.perf_counter()
    try:
        async with websockets.connect(
            uri,
            open_timeout=FIRST_AUDIO_TIMEOUT,
            max_size=None,
            ping_interval=20,
            ping_timeout=90,
        ) as ws:
            first_audio_at = None
            deadline = time.perf_counter() + FIRST_AUDIO_TIMEOUT
            while time.perf_counter() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=deadline - time.perf_counter())
                except asyncio.TimeoutError:
                    break
                except websockets.ConnectionClosed:
                    break
                if isinstance(msg, (bytes, bytearray)) and len(msg) > 0:
                    first_audio_at = time.perf_counter()
                    break

            if first_audio_at is None:
                store[idx] = {"label": label, "latency_s": None, "error": "no audio before timeout"}
                connected_evt.set()
                return

            store[idx] = {"label": label, "latency_s": first_audio_at - t0}
            connected_evt.set()

            # Keep the session alive (draining audio) until the test says stop.
            while not stop_evt.is_set():
                try:
                    await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except websockets.ConnectionClosed:
                    break
    except Exception as e:  # noqa: BLE001 - report any connect/transport failure
        store[idx] = {"label": label, "latency_s": None, "error": repr(e)}
        connected_evt.set()


def percentile(values, pct):
    """Linear-interpolation percentile (matches numpy's default)."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    rank = (pct / 100.0) * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] + (s[hi] - s[lo]) * frac


async def main():
    parser = argparse.ArgumentParser(description="Cold-start burst harness")
    parser.add_argument("uri", help="WebSocket URI, e.g. wss://host/ws-client")
    parser.add_argument("--steady", type=int, default=10, help="Steady sessions to hold first")
    parser.add_argument("--burst", type=int, default=10, help="Burst sessions fired back-to-back")
    parser.add_argument("--target", type=float, default=5.0, help="p95 pass threshold (seconds)")
    parser.add_argument("--out", default=None, help="Path to write JSON results")
    args = parser.parse_args()

    stop_evt = asyncio.Event()

    print(f"[harness] target URI: {args.uri}")
    print(f"[harness] phase 1: opening {args.steady} steady sessions (reach capacity)...")

    steady_store, steady_conn, steady_tasks = {}, [], []
    for i in range(args.steady):
        evt = asyncio.Event()
        steady_conn.append(evt)
        steady_tasks.append(
            asyncio.create_task(run_session(args.uri, steady_store, i, evt, stop_evt, "steady"))
        )
    await asyncio.gather(*(e.wait() for e in steady_conn))

    steady_ok = sum(1 for r in steady_store.values() if r.get("latency_s") is not None)
    print(f"[harness] steady sessions connected: {steady_ok}/{args.steady}")

    print(f"[harness] phase 2: firing {args.burst} burst sessions back-to-back...")
    burst_store, burst_conn, burst_tasks = {}, [], []
    burst_fire_start = time.perf_counter()
    for i in range(args.burst):
        evt = asyncio.Event()
        burst_conn.append(evt)
        burst_tasks.append(
            asyncio.create_task(run_session(args.uri, burst_store, i, evt, stop_evt, "burst"))
        )
    fire_span = time.perf_counter() - burst_fire_start
    print(f"[harness] all burst requests issued within {fire_span * 1000:.0f} ms")

    await asyncio.gather(*(e.wait() for e in burst_conn))

    # Everyone has first audio (or failed); release the sessions.
    stop_evt.set()
    await asyncio.gather(*steady_tasks, *burst_tasks, return_exceptions=True)

    burst = [burst_store[i] for i in sorted(burst_store)]
    latencies = [r["latency_s"] for r in burst if r.get("latency_s") is not None]

    print("\n===== BURST RESULTS (request -> first audio) =====")
    for i, r in enumerate(burst):
        if r.get("latency_s") is not None:
            print(f"  session {i + 11:>2}: {r['latency_s']:.3f} s")
        else:
            print(f"  session {i + 11:>2}: FAILED ({r.get('error')})")

    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    print("\n----- summary -----")
    print(f"  connected: {len(latencies)}/{args.burst}")
    if latencies:
        print(f"  min   : {min(latencies):.3f} s")
        print(f"  median: {p50:.3f} s")
        print(f"  p95   : {p95:.3f} s")
        print(f"  max   : {max(latencies):.3f} s")
    passed = bool(latencies) and len(latencies) == args.burst and p95 is not None and p95 < args.target
    print(f"\n  PASS (p95 < {args.target}s): {passed}")

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uri": args.uri,
        "steady": args.steady,
        "burst": args.burst,
        "target_s": args.target,
        "burst_results": burst,
        "steady_results": [steady_store[i] for i in sorted(steady_store)],
        "median_s": p50,
        "p95_s": p95,
        "passed": passed,
    }
    out = args.out
    if out is None:
        os.makedirs("results", exist_ok=True)
        out = os.path.join("results", f"burst-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n[harness] wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
