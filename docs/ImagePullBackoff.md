# ImagePullBackoff Troubleshooting Guide

## What It Means
Kubernetes cannot pull the container image from the registry. After successive failures the
kubelet enters a back-off loop (similar to CrashLoopBackOff). It shows as `ImagePullBackOff`
or `ErrImagePull` in `kubectl get pods`.

## Common Root Causes
- Typo in image name or tag (`ngnix:latest` instead of `nginx:latest`)
- Tag no longer exists in the registry (deleted or overwritten)
- Private registry requires credentials that are missing or expired
- Registry is unreachable from cluster nodes (firewall, DNS, private endpoint)
- Rate limiting — Docker Hub imposes pull limits on unauthenticated/free-tier accounts
- Wrong architecture — amd64 image on arm64 nodes (or vice versa)

## Diagnostic Steps
1. `kubectl describe pod <pod>` — read the Events section for the exact error message
2. `kubectl get pod <pod> -o jsonpath='{.spec.containers[*].image}'` — confirm the full image ref
3. From a cluster node: `docker pull <image>` (or `crictl pull <image>`) — test connectivity and auth
4. `kubectl get secret <pull-secret> -o yaml` — verify the imagePullSecret exists and is base64-encoded correctly
5. `kubectl get events --field-selector reason=Failed` — see all recent image pull failures cluster-wide

## Remediation
- Fix the image name/tag in the Deployment or Pod spec
- Create or update the pull secret:
  ```
  kubectl create secret docker-registry regcred \
    --docker-server=<registry> \
    --docker-username=<user> \
    --docker-password=<token>
  ```
- Reference the secret in the pod spec under `spec.imagePullSecrets`
- For Docker Hub rate limits, authenticate with a paid account or mirror to a private registry
- If the tag was deleted, update to a valid tag or use image digest (`@sha256:…`) for immutability
- For multi-arch issues, use a manifest-list image or add node affinity for the correct architecture
