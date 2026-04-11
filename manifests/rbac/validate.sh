#!/bin/bash
# AgentCube RBAC Validation Script
# This script validates the RBAC configuration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${AGENTCUBE_NAMESPACE:-agentcube}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================="
echo "AgentCube RBAC Validation"
echo "=================================="
echo ""

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo -e "${YELLOW}Warning: kubectl not found. Running in dry-run mode.${NC}"
    DRY_RUN=true
else
    DRY_RUN=false
fi

# Validate YAML syntax
echo "1. Validating YAML syntax..."
for file in "$SCRIPT_DIR"/*.yaml "$SCRIPT_DIR"/**/*.yaml; do
    if [ -f "$file" ]; then
        if python3 -c "import yaml; yaml.safe_load_all(open('$file'))" 2>/dev/null; then
            echo -e "   ${GREEN}✓${NC} $file"
        else
            echo -e "   ${RED}✗${NC} $file (invalid YAML)"
            exit 1
        fi
    fi
done
echo ""

# Validate RBAC structure
echo "2. Validating RBAC structure..."

# Check ServiceAccounts
SA_COUNT=$(find "$SCRIPT_DIR/serviceaccounts" -name "*.yaml" -type f 2>/dev/null | wc -l)
if [ "$SA_COUNT" -ge 2 ]; then
    echo -e "   ${GREEN}✓${NC} Found $SA_COUNT ServiceAccount manifests"
else
    echo -e "   ${RED}✗${NC} Expected at least 2 ServiceAccount manifests, found $SA_COUNT"
    exit 1
fi

# Check ClusterRoles
CR_COUNT=$(find "$SCRIPT_DIR/clusterroles" -name "*.yaml" -type f 2>/dev/null | wc -l)
if [ "$CR_COUNT" -ge 1 ]; then
    echo -e "   ${GREEN}✓${NC} Found $CR_COUNT ClusterRole manifests"
else
    echo -e "   ${RED}✗${NC} Expected at least 1 ClusterRole manifest, found $CR_COUNT"
    exit 1
fi

# Check ClusterRoleBindings
CRB_COUNT=$(find "$SCRIPT_DIR/clusterrolebindings" -name "*.yaml" -type f 2>/dev/null | wc -l)
if [ "$CRB_COUNT" -ge 1 ]; then
    echo -e "   ${GREEN}✓${NC} Found $CRB_COUNT ClusterRoleBinding manifests"
else
    echo -e "   ${RED}✗${NC} Expected at least 1 ClusterRoleBinding manifest, found $CRB_COUNT"
    exit 1
fi

# Check Roles
R_COUNT=$(find "$SCRIPT_DIR/roles" -name "*.yaml" -type f 2>/dev/null | wc -l)
if [ "$R_COUNT" -ge 1 ]; then
    echo -e "   ${GREEN}✓${NC} Found $R_COUNT Role manifests"
else
    echo -e "   ${RED}✗${NC} Expected at least 1 Role manifest, found $R_COUNT"
    exit 1
fi

# Check RoleBindings
RB_COUNT=$(find "$SCRIPT_DIR/rolebindings" -name "*.yaml" -type f 2>/dev/null | wc -l)
if [ "$RB_COUNT" -ge 1 ]; then
    echo -e "   ${GREEN}✓${NC} Found $RB_COUNT RoleBinding manifests"
else
    echo -e "   ${RED}✗${NC} Expected at least 1 RoleBinding manifest, found $RB_COUNT"
    exit 1
fi
echo ""

# Validate kubectl dry-run
if [ "$DRY_RUN" = false ]; then
    echo "3. Validating with kubectl dry-run..."
    if kubectl apply --dry-run=client -f "$SCRIPT_DIR/rbac-all.yaml" &> /dev/null; then
        echo -e "   ${GREEN}✓${NC} kubectl dry-run passed"
    else
        echo -e "   ${RED}✗${NC} kubectl dry-run failed"
        exit 1
    fi
    echo ""

    # Check if namespace exists
    echo "4. Checking namespace..."
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        echo -e "   ${GREEN}✓${NC} Namespace $NAMESPACE exists"
    else
        echo -e "   ${YELLOW}!${NC} Namespace $NAMESPACE does not exist"
        echo "      Create with: kubectl create namespace $NAMESPACE"
    fi
    echo ""

    # Verify permissions
    echo "5. Verifying RBAC permissions..."
    
    # Check WorkloadManager ServiceAccount
    if kubectl get sa/workloadmanager -n "$NAMESPACE" &> /dev/null; then
        echo -e "   ${GREEN}✓${NC} WorkloadManager ServiceAccount exists"
    else
        echo -e "   ${YELLOW}!${NC} WorkloadManager ServiceAccount not found in $NAMESPACE"
    fi
    
    # Check WorkloadManager ClusterRole
    if kubectl get clusterrole/workloadmanager &> /dev/null; then
        echo -e "   ${GREEN}✓${NC} WorkloadManager ClusterRole exists"
    else
        echo -e "   ${YELLOW}!${NC} WorkloadManager ClusterRole not found"
    fi
    
    # Check Router ServiceAccount
    if kubectl get sa/agentcube-router -n "$NAMESPACE" &> /dev/null; then
        echo -e "   ${GREEN}✓${NC} Router ServiceAccount exists"
    else
        echo -e "   ${YELLOW}!${NC} Router ServiceAccount not found in $NAMESPACE"
    fi
    
    # Check Router Role
    if kubectl get role/agentcube-router -n "$NAMESPACE" &> /dev/null; then
        echo -e "   ${GREEN}✓${NC} Router Role exists"
    else
        echo -e "   ${YELLOW}!${NC} Router Role not found in $NAMESPACE"
    fi
    echo ""
fi

# Validate combined manifest
echo "6. Validating combined manifest..."
DOC_COUNT=$(grep -c "^---$" "$SCRIPT_DIR/rbac-all.yaml" || echo "0")
if [ "$DOC_COUNT" -ge 10 ]; then
    echo -e "   ${GREEN}✓${NC} Combined manifest contains $DOC_COUNT documents"
else
    echo -e "   ${RED}✗${NC} Expected at least 10 documents in combined manifest, found $DOC_COUNT"
    exit 1
fi
echo ""

echo "=================================="
echo -e "${GREEN}Validation Complete!${NC}"
echo "=================================="
echo ""
echo "To apply RBAC configuration:"
echo "  kubectl apply -f $SCRIPT_DIR/rbac-all.yaml"
echo ""
echo "Or use kustomize:"
echo "  kubectl apply -k $SCRIPT_DIR"
echo ""
