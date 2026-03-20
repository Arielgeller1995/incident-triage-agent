# OOMKilled Troubleshooting Guide

## What It Means
The Linux kernel's OOM killer terminated the container because it exceeded the memory
limit set in `resources.limits.memory`. The pod shows `OOMKilled` in its Last State and
exit code 137.

## Common Root Causes
- Memory limit set too low for the workload's actual footprint
- Memory leak in application code (unbounded caches, retained references, goroutine leaks)
- JVM heap not capped — JVM defaults to a fraction of host RAM, ignoring cgroup limits
- Sudden traffic spike causing a large number of in-flight requests to allocate heap
- Bulk data processing loading entire datasets into memory at once

## Diagnostic Steps
1. `kubectl describe pod <pod>` — confirm `OOMKilled` and exit code 137
2. `kubectl top pod <pod> --containers` — see live memory usage per container
3. `kubectl top pod --all-namespaces --sort-by=memory` — find the biggest consumers in the cluster
4. For JVM workloads: inspect `-Xmx` flag and compare with `limits.memory`
5. Enable Go/Python/Java heap profiling and capture a dump at peak load

## Remediation
- Increase `resources.limits.memory` in the pod spec (start with 1.5× the observed peak)
- Set `resources.requests.memory` close to the limit to prevent noisy-neighbour scheduling
- For JVM: add `-XX:MaxRAMPercentage=75.0` so the JVM respects cgroup limits automatically
- Fix memory leaks identified by heap analysis
- For batch jobs, implement streaming/chunked processing instead of loading full datasets
- Add a Vertical Pod Autoscaler (VPA) recommendation object for ongoing right-sizing
