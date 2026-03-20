# CrashLoopBackOff Troubleshooting Guide

## What It Means
Kubernetes restarts a container repeatedly because it keeps exiting with a non-zero code.
The back-off timer (10 s → 20 s → 40 s … up to 5 min) grows between attempts.

## Common Root Causes
- Application crash on startup (bad config, missing env var, failed DB connection)
- OOM kill disguised as a crash (exit code 137)
- Wrong container entrypoint or command in the manifest
- Liveness probe too aggressive — kills the container before it finishes initialising
- Permission denied errors reading mounted secrets or config maps

## Diagnostic Steps
1. `kubectl logs <pod> --previous` — read the last crash's stdout/stderr
2. `kubectl describe pod <pod>` — check Exit Code and Last State section
3. `kubectl get events --field-selector involvedObject.name=<pod>` — spot OOM or probe failures
4. `kubectl rollout history deployment/<name>` — identify if a recent rollout introduced the regression
5. `kubectl exec -it <pod> -- /bin/sh` (if the container starts briefly) — validate env vars and filesystem mounts

## Remediation
- Fix the application-level crash shown in `--previous` logs
- If Exit Code is 137, increase `resources.limits.memory`
- If the probe is killing the pod, raise `initialDelaySeconds` on the liveness probe
- Rollback with `kubectl rollout undo deployment/<name>` for a quick recovery
- Validate config maps and secrets: `kubectl get configmap <name> -o yaml`
