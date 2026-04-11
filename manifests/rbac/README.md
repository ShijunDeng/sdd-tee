# AgentCube RBAC Configuration

This directory contains Kubernetes RBAC (Role-Based Access Control) manifests for AgentCube components.

## Overview

The RBAC configuration provides least-privilege permissions for three main components:

1. **WorkloadManager** - Cluster-wide permissions for managing sandboxes, pods, and secrets
2. **Router** - Namespace-scoped permissions for routing and session management
3. **Volcano Scheduler** - Cluster-wide permissions for pod scheduling (optional)

## Directory Structure

```
rbac/
├── namespace.yaml                  # AgentCube namespace
├── kustomization.yaml              # Kustomize configuration
├── rbac-all.yaml                   # Combined manifest for easy deployment
├── validate.sh                     # Validation script
├── serviceaccounts/
│   ├── workloadmanager.yaml        # WorkloadManager ServiceAccount
│   ├── router.yaml                 # Router ServiceAccount
│   └── volcano-scheduler.yaml      # Volcano Scheduler ServiceAccount
├── clusterroles/
│   ├── workloadmanager.yaml        # WorkloadManager ClusterRole
│   └── volcano-scheduler.yaml      # Volcano Scheduler ClusterRole
├── clusterrolebindings/
│   ├── workloadmanager.yaml        # WorkloadManager ClusterRoleBinding
│   └── volcano-scheduler.yaml      # Volcano Scheduler ClusterRoleBinding
├── roles/
│   └── router.yaml                 # Router Role (namespace-scoped)
└── rolebindings/
    └── router.yaml                 # Router RoleBinding
```

## Quick Start

### Option 1: Apply Combined Manifest

```bash
kubectl apply -f rbac-all.yaml
```

### Option 2: Apply with Kustomize

```bash
kubectl apply -k .
```

### Option 3: Apply Individual Files

```bash
# Create namespace
kubectl apply -f namespace.yaml

# Create ServiceAccounts
kubectl apply -f serviceaccounts/

# Create ClusterRoles and ClusterRoleBindings
kubectl apply -f clusterroles/
kubectl apply -f clusterrolebindings/

# Create Role and RoleBinding
kubectl apply -f roles/
kubectl apply -f rolebindings/
```

## Validation

Run the validation script to check the RBAC configuration:

```bash
./validate.sh
```

The script will:
- Validate YAML syntax
- Check RBAC structure
- Run kubectl dry-run validation
- Verify resource creation (if cluster is accessible)

## Permissions Summary

### WorkloadManager

**ClusterRole** permissions include:
- Full CRUD on `sandboxes`, `sandboxclaims`, `sandboxtemplates`, `sandboxwarmpools`
- Full CRUD on `codeinterpreters` and status updates
- Read-only access to `agentruntimes`
- Pod management (create, update, delete, watch)
- Secret and ConfigMap management
- Service and Event management
- Token review and subject access review

### Router

**Role** (namespace-scoped) permissions include:
- Read-only access to Secrets, ConfigMaps, Pods, Events
- Service and Endpoint discovery

### Volcano Scheduler (Optional)

**ClusterRole** permissions include:
- Pod scheduling and updates
- Node listing
- PodGroup management
- Queue reading
- PriorityClass reading

## Customization

### Custom Namespace

To use a custom namespace instead of `agentcube`:

1. Update the `namespace` field in each manifest
2. Or use kustomize with a namespace overlay:

```bash
kubectl apply -k . --namespace=my-custom-namespace
```

### Minimal RBAC

For minimal installations, you can apply only the required components:

```bash
# WorkloadManager only
kubectl apply -f serviceaccounts/workloadmanager.yaml
kubectl apply -f clusterroles/workloadmanager.yaml
kubectl apply -f clusterrolebindings/workloadmanager.yaml

# Router only
kubectl apply -f serviceaccounts/router.yaml
kubectl apply -f roles/router.yaml
kubectl apply -f rolebindings/router.yaml
```

## Security Considerations

1. **Least Privilege**: Each component has only the permissions it needs
2. **Namespace Isolation**: Router uses namespace-scoped Role, not ClusterRole
3. **ServiceAccount Isolation**: Each component has its own ServiceAccount
4. **Auditability**: Clear separation of concerns in manifest structure

## Troubleshooting

### Permission Denied Errors

Check if the RBAC resources are created:

```bash
kubectl get sa,clusterrole,clusterrolebinding,role,rolebinding -n agentcube
```

Verify permissions with:

```bash
kubectl auth can-i <verb> <resource> --as=system:serviceaccount:agentcube:<sa-name>
```

### ServiceAccount Not Found

Ensure the namespace exists and ServiceAccounts are created:

```bash
kubectl create namespace agentcube
kubectl apply -f serviceaccounts/
```

## References

- [Kubernetes RBAC Documentation](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Kubernetes ServiceAccounts](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)
- [Kustomize Documentation](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/)
