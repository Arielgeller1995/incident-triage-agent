# API Authentication Failures

## Symptoms
- HTTP 401 Unauthorized responses
- HTTP 403 Forbidden responses
- JWT token validation errors
- "Token has expired" errors
- "Invalid signature" errors
- OAuth2 authentication failures
- API key rejected or invalid
- Service account authentication failures
- "Bearer token" errors
- RBAC permission denied errors

## Likely Causes
- JWT token expired — tokens have a short TTL (typically 1-24 hours)
- Wrong or rotated API key
- Service account credentials revoked or deleted
- Clock skew between services causing token validation to fail
- Wrong audience or issuer in JWT claims
- Missing or incorrect Authorization header
- OAuth2 client secret rotated without updating dependent services
- RBAC role missing required permissions
- Token signed with wrong key or algorithm

## Diagnostic Steps
1. Decode the JWT token to check expiry:
```bash
   echo "" | cut -d. -f2 | base64 -d | jq .exp
   # Compare with current time: date +%s
```
2. Check service account token validity:
```bash
   kubectl get serviceaccount  -n  -o yaml
   kubectl describe secret 
```
3. Verify RBAC permissions:
```bash
   kubectl auth can-i   --as=system:serviceaccount::
```
4. Check for clock skew between nodes:
```bash
   kubectl get nodes -o wide
   # SSH to nodes and compare: date -u
```
5. Review authentication logs:
```bash
   kubectl logs -n kube-system -l component=kube-apiserver | grep "401\|403\|Unauthorized"
```
6. Test the token manually:
```bash
   curl -H "Authorization: Bearer " https:///health
```

## Possible Fixes
- Rotate and reissue the expired JWT token
- Update the secret containing the API key or OAuth client secret:
```bash
  kubectl create secret generic  --from-literal=token= \
    --dry-run=client -o yaml | kubectl apply -f -
```
- Restart pods to pick up new secret values:
```bash
  kubectl rollout restart deployment/
```
- Fix clock skew by syncing NTP on affected nodes
- Update RBAC role to include missing permissions:
```bash
  kubectl edit clusterrole 
```
- Implement token refresh logic in the application
- Use Kubernetes service account tokens with automatic rotation instead of static tokens
- Set shorter token TTL and implement refresh before expiry

## Notes
- JWT tokens have three parts: header.payload.signature — decode payload to inspect claims
- `exp` claim in JWT is Unix timestamp — compare with `date +%s` to check expiry
- Kubernetes service account tokens auto-rotate since K8s 1.21
- Clock skew > 5 minutes will cause JWT validation failures
- Always use secrets for credentials — never hardcode tokens in pod specs or ConfigMaps
- 401 = not authenticated (wrong/missing credentials), 403 = not authorized (valid credentials but insufficient permissions)