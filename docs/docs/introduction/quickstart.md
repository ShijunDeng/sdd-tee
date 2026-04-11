---
title: Quick Start
sidebar_label: Quick Start
---

# Quick Start Guide

This guide will help you get AgentCube up and running in minutes. You'll learn how to deploy AgentCube on Kubernetes and execute your first code in a secure sandbox.

## Prerequisites

Before you begin, ensure you have:

- **Kubernetes cluster** (v1.28+): You can use Minikube, Kind, or any cloud provider
- **kubectl** configured to access your cluster
- **Helm** (v3.x) installed
- **Redis** (v6+) running in your cluster or accessible

### Optional but Recommended

- **Volcano scheduler** for batch workloads
- **Prometheus** for monitoring
- **Grafana** for visualization

## Step 1: Install Dependencies

### Install Redis

If you don't have Redis running, deploy it using Helm:

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install redis bitnami/redis --set architecture=standalone
```

Get the Redis connection details:

```bash
REDIS_ADDR=$(kubectl get svc redis-master -o jsonpath='{.spec.clusterIP}:6379}')
echo "Redis address: $REDIS_ADDR"
```

### Install Volcano Scheduler (Optional)

```bash
kubectl apply -f https://raw.githubusercontent.com/volcano-sh/volcano/master/installer/volcano-development.yaml
```

## Step 2: Deploy AgentCube

### Add the AgentCube Helm Repository

```bash
helm repo add agentcube https://charts.agentcube.io
helm repo update
```

### Create a Custom Values File

Create `values.yaml` with your configuration:

```yaml
namespace: default

# Redis configuration
redis:
  addr: "redis-master:6379"
  password: ""

# Workload Manager configuration
workloadmanager:
  replicas: 1
  image:
    repository: agentcube/workloadmanager
    tag: "v1.0.0"
    pullPolicy: IfNotPresent
  service:
    type: ClusterIP
    port: 8080

# Router configuration
router:
  replicas: 1
  image:
    repository: agentcube/router
    tag: "v1.0.0"
    pullPolicy: IfNotPresent
  service:
    type: ClusterIP
    port: 8080
  rbac:
    create: true

# CRDs
crds:
  create: true

# Optional Volcano scheduler
volcano:
  scheduler:
    enabled: false
```

### Install AgentCube

```bash
helm install agentcube agentcube/agentcube -f values.yaml
```

Verify the installation:

```bash
kubectl get pods -n default
```

You should see:
- `workloadmanager-*` pods running
- `agentcube-router-*` pods running

## Step 3: Create Your First CodeInterpreter

### Define a CodeInterpreter CR

Create `codeinterpreter.yaml`:

```yaml
apiVersion: runtime.agentcube.volcano.sh/v1alpha1
kind: CodeInterpreter
metadata:
  name: my-interpreter
  namespace: default
spec:
  ports:
    - name: ssh
      containerPort: 2222
      protocol: TCP
  template:
    spec:
      containers:
        - name: sandbox
          image: agentcube/python-sandbox:v1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 2222
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
  sessionTimeout: "15m"
  maxSessionDuration: "8h"
  warmPoolSize: 2
  authMode: token
```

Apply the manifest:

```bash
kubectl apply -f codeinterpreter.yaml
```

Check the status:

```bash
kubectl get codeinterpreter my-interpreter
```

## Step 4: Execute Your First Code

### Using Python SDK

Install the SDK:

```bash
pip install agentcube-sdk
```

Create `first_script.py`:

```python
from agentcube import CodeInterpreterClient

# Initialize the client
router_url = "http://agentcube-router.default.svc.cluster.local:8080"
workload_manager_url = "http://workloadmanager.default.svc.cluster.local:8080"

with CodeInterpreterClient(
    router_url=router_url,
    workload_manager_url=workload_manager_url,
    name="my-interpreter",
    namespace="default"
) as client:
    # Execute Python code
    result = client.run_code("""
import math
print(f"Hello, AgentCube!")
print(f"Square root of 16: {math.sqrt(16)}")
    """)

    print("Output:", result["stdout"])
    print("Exit code:", result["exit_code"])
```

Run the script:

```bash
python first_script.py
```

Expected output:

```
Output: Hello, AgentCube!
Square root of 16: 4.0

Exit code: 0
```

### Using REST API

Get the Router service URL:

```bash
ROUTER_URL=$(kubectl get svc agentcube-router -o jsonpath='{.spec.clusterIP}:8080')
echo "Router URL: $ROUTER_URL"
```

Create a session:

```bash
curl -X POST "http://$ROUTER_URL/v1/sessions/default/CodeInterpreter/my-interpreter" \
  -H "Content-Type: application/json" \
  -d '{
    "ttl": 3600,
    "metadata": {
      "user": "demo-user"
    }
  }'
```

Save the `session_id` from the response.

Execute code:

```bash
SESSION_ID="<your-session-id>"

curl -X POST "http://$ROUTER_URL/api/execute" \
  -H "Content-Type: application/json" \
  -H "x-agentcube-session-id: $SESSION_ID" \
  -d '{
    "command": ["python3", "-c", "print(\"Hello from REST API!\")"],
    "timeout": "30s"
  }'
```

## Step 5: Clean Up

Delete the CodeInterpreter:

```bash
kubectl delete codeinterpreter my-interpreter
```

Uninstall AgentCube:

```bash
helm uninstall agentcube
```

Delete Redis (if you installed it):

```bash
helm uninstall redis
```

## Next Steps

Congratulations! You've successfully deployed AgentCube and executed your first code. Here's what you can do next:

- **[Learn Architecture](/architecture/overview)**: Understand how AgentCube works
- **[Explore APIs](/api/overview)**: Learn about REST, gRPC, and CRD APIs
- **[Advanced Tutorials](/tutorials/advanced-features)**: Discover advanced features
- **[Deployment Guide](/deployment/kubernetes)**: Learn production deployment strategies

## Troubleshooting

### Pod Not Starting

Check pod status and logs:

```bash
kubectl get pods
kubectl logs <pod-name>
```

Common issues:
- Image pull failures: Check image repository and credentials
- Resource limits: Adjust requests/limits in your CRD
- Redis connection: Verify Redis is accessible

### Session Creation Failed

Check Workload Manager logs:

```bash
kubectl logs -l app=workloadmanager --tail=50
```

Verify:
- Redis connection is working
- CRD exists and is properly configured
- RBAC permissions are correct

### Connection Timeouts

Check Router logs:

```bash
kubectl logs -l app=agentcube-router --tail=50
```

Verify:
- Router service is running
- Network policies allow traffic
- Workload Manager is accessible

## Getting Help

- **Documentation**: Browse the full documentation
- **GitHub Issues**: Report bugs or request features
- **Discord**: Join our community for real-time help