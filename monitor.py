#!/usr/bin/env python3
"""
Continuous latency probe with Prometheus metrics for cloud-robotics links.

Probes one or more targets on a fixed interval and exposes latency statistics
at http://<host>:<port>/metrics for Prometheus scraping. Two probe types:

  * icmp:HOST            - ICMP echo RTT (reuses ping3.do_one; datagram->raw)
  * tcp:HOST:PORT        - TCP connect (handshake) RTT; works where ICMP is
                           blocked and reflects reachability of a real service

Besides the raw histogram (for aggregation in Prometheus via
histogram_quantile), it also publishes rolling-window gauges computed locally
(p50/p95/p99, min/max/mean/stddev, IPDV jitter, loss ratio) so the numbers are
readable straight from /metrics without a Prometheus server.

Config via CLI flags or environment variables:
  PROBE_TARGETS   comma-separated targets, e.g. "icmp:8.8.8.8,tcp:api:443"
  PROBE_INTERVAL  seconds between probes per target        (default 1.0)
  PROBE_TIMEOUT   per-probe timeout in seconds             (default 2.0)
  PROBE_WINDOW    rolling window size (samples)            (default 100)
  METRICS_PORT    HTTP port for /metrics                   (default 9145)
"""
import os
import sys
import time
import socket
import argparse
import threading
import collections

import numpy as np
from prometheus_client import start_http_server, Histogram, Gauge, Counter

import ping3  # reuse the hardened ICMP implementation (do_one)


# Buckets (seconds) span LAN (sub-ms) to WAN (seconds) latencies.
DEFAULT_BUCKETS = (0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05,
                   0.1, 0.2, 0.5, 1.0, 2.0, 5.0)

LABELS = ['target', 'proto']

rtt_hist = Histogram('probe_rtt_seconds', 'RTT of successful probes',
                     LABELS, buckets=DEFAULT_BUCKETS)
probes_total = Counter('probe_total', 'Probes attempted', LABELS)
failures_total = Counter('probe_failures_total', 'Probes failed or timed out', LABELS)
success_g = Gauge('probe_success', '1 if the last probe succeeded else 0', LABELS)

# Rolling-window computed gauges.
g_p50 = Gauge('probe_rtt_p50_seconds', 'Rolling median RTT', LABELS)
g_p95 = Gauge('probe_rtt_p95_seconds', 'Rolling p95 RTT', LABELS)
g_p99 = Gauge('probe_rtt_p99_seconds', 'Rolling p99 RTT', LABELS)
g_min = Gauge('probe_rtt_min_seconds', 'Rolling min RTT', LABELS)
g_max = Gauge('probe_rtt_max_seconds', 'Rolling max RTT', LABELS)
g_mean = Gauge('probe_rtt_mean_seconds', 'Rolling mean RTT', LABELS)
g_std = Gauge('probe_rtt_stddev_seconds', 'Rolling stddev of RTT', LABELS)
g_jitter = Gauge('probe_jitter_seconds',
                 'Rolling mean |RTT_i - RTT_(i-1)| (IPDV jitter)', LABELS)
g_loss = Gauge('probe_loss_ratio', 'Rolling fraction of failed probes', LABELS)


def parse_target(spec):
    """Parse "icmp:HOST" or "tcp:HOST:PORT" into (proto, host, port, label)."""
    spec = spec.strip()
    parts = spec.split(':')
    proto = parts[0].lower()
    if proto == 'icmp' and len(parts) == 2:
        return 'icmp', parts[1], None, 'icmp:' + parts[1]
    if proto == 'tcp' and len(parts) == 3:
        return 'tcp', parts[1], int(parts[2]), 'tcp:%s:%s' % (parts[1], parts[2])
    raise ValueError(
        'bad target %r (use icmp:HOST or tcp:HOST:PORT; IPv4/hostname)' % spec)


def tcp_probe(host, port, timeout):
    """Return the TCP connect (handshake) time in seconds, or None on failure."""
    start = time.perf_counter()
    try:
        conn = socket.create_connection((host, port), timeout=timeout)
        conn.close()
        return time.perf_counter() - start
    except OSError:
        return None


def _update_gauges(labels, rtts, results):
    if results:
        g_loss.labels(**labels).set(1.0 - sum(results) / len(results))
    if rtts:
        arr = np.fromiter(rtts, dtype=float)
        g_p50.labels(**labels).set(float(np.percentile(arr, 50)))
        g_p95.labels(**labels).set(float(np.percentile(arr, 95)))
        g_p99.labels(**labels).set(float(np.percentile(arr, 99)))
        g_min.labels(**labels).set(float(arr.min()))
        g_max.labels(**labels).set(float(arr.max()))
        g_mean.labels(**labels).set(float(arr.mean()))
        g_std.labels(**labels).set(float(arr.std()))
        if arr.size >= 2:
            g_jitter.labels(**labels).set(float(np.mean(np.abs(np.diff(arr)))))


def run_probe(spec, interval, timeout, window):
    proto, host, port, label = spec
    labels = {'target': label, 'proto': proto}
    rtts = collections.deque(maxlen=window)     # successful RTTs (seconds)
    results = collections.deque(maxlen=window)  # True/False per attempt
    # Initialise label sets so the series exist before the first success.
    success_g.labels(**labels).set(0)
    probes_total.labels(**labels)
    failures_total.labels(**labels)

    while True:
        start = time.perf_counter()
        try:
            if proto == 'icmp':
                rtt = ping3.do_one(host, timeout)
            else:
                rtt = tcp_probe(host, port, timeout)
        except Exception as e:  # keep the probe thread alive on any error
            rtt = None
            print('probe error [%s]: %s' % (label, e), file=sys.stderr)

        probes_total.labels(**labels).inc()
        if rtt is None:
            failures_total.labels(**labels).inc()
            success_g.labels(**labels).set(0)
            results.append(False)
        else:
            rtt_hist.labels(**labels).observe(rtt)
            success_g.labels(**labels).set(1)
            rtts.append(rtt)
            results.append(True)

        _update_gauges(labels, rtts, results)

        # Sleep the remainder of the interval (probe time already elapsed).
        time.sleep(max(0.0, interval - (time.perf_counter() - start)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--targets', default=os.environ.get('PROBE_TARGETS', ''),
                    help='comma-separated icmp:HOST or tcp:HOST:PORT')
    ap.add_argument('--interval', type=float,
                    default=float(os.environ.get('PROBE_INTERVAL', '1.0')))
    ap.add_argument('--timeout', type=float,
                    default=float(os.environ.get('PROBE_TIMEOUT', '2.0')))
    ap.add_argument('--window', type=int,
                    default=int(os.environ.get('PROBE_WINDOW', '100')))
    ap.add_argument('--port', type=int,
                    default=int(os.environ.get('METRICS_PORT', '9145')))
    args = ap.parse_args()

    specs = [parse_target(t) for t in args.targets.split(',') if t.strip()]
    if not specs:
        print('No targets. Set PROBE_TARGETS or --targets, '
              'e.g. "icmp:8.8.8.8,tcp:api.example.com:443"', file=sys.stderr)
        sys.exit(1)

    start_http_server(args.port)
    print('metrics on :%d  interval=%.3gs timeout=%.3gs window=%d'
          % (args.port, args.interval, args.timeout, args.window))
    for spec in specs:
        threading.Thread(target=run_probe,
                         args=(spec, args.interval, args.timeout, args.window),
                         daemon=True).start()
        print('probing', spec[3])

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
