# AR-031 — RBAC 配置 (SA/Role/Binding)

## Implementation Summary

**Module:** manifests  
**Language:** YAML  
**Size:** M  
**Status:** ST-4 completed

## Changes

### Files Created

1. **ServiceAccount Manifests** (`serviceaccounts/`)
   - `workloadmanager.yaml` - WorkloadManager ServiceAccount
   - `router.yaml` - Router ServiceAccount
   - `volcano-scheduler.yaml` - Volcano Scheduler ServiceAccount

2. **ClusterRole Manifests** (`clusterroles/`)
   - `workloadmanager.yaml` - WorkloadManager ClusterRole with full CRUD permissions for sandboxes, sandboxclaims, templates, warmpools, codeinterpreters
   - `volcano-scheduler.yaml` - Volcano Scheduler ClusterRole with pod scheduling permissions

3. **ClusterRoleBinding Manifests** (`clusterrolebindings/`)
   - `workloadmanager.yaml` - Binds WorkloadManager ClusterRole to ServiceAccount
   - `volcano-scheduler.yaml` - Binds Volcano Scheduler ClusterRole to ServiceAccount

4. **Role Manifests** (`roles/`)
   - `router.yaml` - Namespace-scoped Role for Router (read-only access to secrets, configmaps, pods)

5. **RoleBinding Manifests** (`rolebindings/`)
   - `router.yaml` - Binds Router Role to ServiceAccount

6. **Additional Files**
   - `namespace.yaml` - AgentCube namespace definition
   - `kustomization.yaml` - Kustomize configuration
   - `rbac-all.yaml` - Combined manifest for easy deployment
   - `validate.sh` - Validation script
   - `README.md` - Usage documentation
   - `tests/test_rbac.py` - Unit tests (26 tests)

## Permissions

### WorkloadManager
- Full CRUD on `sandboxes`, `sandboxclaims`, `sandboxtemplates`, `sandboxwarmpools`
- Full CRUD on `codeinterpreters` with status and finalizer support
- Read-only on `agentruntimes`
- Pod management (create, update, delete, watch, list, get, logs)
- Secret, ConfigMap, Service, Event management
- Token review and subject access review

### Router (Namespace-scoped)
- Read-only on Secrets, ConfigMaps, Pods, Events
- Service and Endpoint discovery

### Volcano Scheduler
- Pod scheduling and updates
- Node listing
- PodGroup management
- Queue and PriorityClass reading

## Testing

All tests pass (26/26):
```bash
cd manifests/rbac
python3 -m pytest tests/test_rbac.py -v
```

## Validation

Run the validation script:
```bash
./validate.sh
```

## Deployment

### Option 1: Combined Manifest
```bash
kubectl apply -f rbac-all.yaml
```

### Option 2: Kustomize
```bash
kubectl apply -k .
```

### Option 3: Individual Files
```bash
kubectl apply -f serviceaccounts/
kubectl apply -f clusterroles/
kubectl apply -f clusterrolebindings/
kubectl apply -f roles/
kubectl apply -f rolebindings/
```

## Security Considerations

1. **Least Privilege** - Each component has only required permissions
2. **Namespace Isolation** - Router uses namespace-scoped Role
3. **ServiceAccount Isolation** - Separate ServiceAccount per component
4. **Clear Separation** - Modular manifest structure for auditability

## Verification

Verify permissions with:
```bash
kubectl auth can-i <verb> <resource> --as=system:serviceaccount:agentcube:<sa-name>
```

Check resources:
```bash
kubectl get sa,clusterrole,clusterrolebinding,role,rolebinding -n agentcube
```

## References

- Kubernetes RBAC: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- ServiceAccounts: https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/
