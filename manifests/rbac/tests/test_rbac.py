#!/usr/bin/env python3
"""
Unit tests for AgentCube RBAC manifests.
Tests YAML structure, required fields, and RBAC correctness.
"""

import os
import sys
import yaml
import unittest
from pathlib import Path

RBAC_DIR = Path(__file__).parent.parent


class TestServiceAccounts(unittest.TestCase):
    """Test ServiceAccount manifests."""

    def test_workloadmanager_sa_exists(self):
        """Test WorkloadManager ServiceAccount exists."""
        path = RBAC_DIR / "serviceaccounts" / "workloadmanager.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_workloadmanager_sa_structure(self):
        """Test WorkloadManager ServiceAccount structure."""
        path = RBAC_DIR / "serviceaccounts" / "workloadmanager.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc["apiVersion"], "v1")
        self.assertEqual(doc["kind"], "ServiceAccount")
        self.assertEqual(doc["metadata"]["name"], "workloadmanager")
        self.assertIn("namespace", doc["metadata"])
        self.assertIn("labels", doc["metadata"])

    def test_router_sa_exists(self):
        """Test Router ServiceAccount exists."""
        path = RBAC_DIR / "serviceaccounts" / "router.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_router_sa_structure(self):
        """Test Router ServiceAccount structure."""
        path = RBAC_DIR / "serviceaccounts" / "router.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc["apiVersion"], "v1")
        self.assertEqual(doc["kind"], "ServiceAccount")
        self.assertEqual(doc["metadata"]["name"], "agentcube-router")

    def test_volcano_sa_exists(self):
        """Test Volcano Scheduler ServiceAccount exists."""
        path = RBAC_DIR / "serviceaccounts" / "volcano-scheduler.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_volcano_sa_structure(self):
        """Test Volcano Scheduler ServiceAccount structure."""
        path = RBAC_DIR / "serviceaccounts" / "volcano-scheduler.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc["apiVersion"], "v1")
        self.assertEqual(doc["kind"], "ServiceAccount")
        self.assertEqual(doc["metadata"]["name"], "volcano-scheduler")


class TestClusterRoles(unittest.TestCase):
    """Test ClusterRole manifests."""

    def test_workloadmanager_cr_exists(self):
        """Test WorkloadManager ClusterRole exists."""
        path = RBAC_DIR / "clusterroles" / "workloadmanager.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_workloadmanager_cr_structure(self):
        """Test WorkloadManager ClusterRole structure."""
        path = RBAC_DIR / "clusterroles" / "workloadmanager.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc["apiVersion"], "rbac.authorization.k8s.io/v1")
        self.assertEqual(doc["kind"], "ClusterRole")
        self.assertEqual(doc["metadata"]["name"], "workloadmanager")
        self.assertIn("rules", doc)
        self.assertIsInstance(doc["rules"], list)
        self.assertGreater(len(doc["rules"]), 0)

    def test_workloadmanager_cr_permissions(self):
        """Test WorkloadManager ClusterRole has required permissions."""
        path = RBAC_DIR / "clusterroles" / "workloadmanager.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        # Check for agents.x-k8s.io permissions
        sandbox_rule = None
        if doc and "rules" in doc:
            for rule in doc["rules"]:
                if rule and "agents.x-k8s.io" in rule.get("apiGroups", []):
                    if "sandboxes" in rule.get("resources", []):
                        sandbox_rule = rule
                        break

        self.assertIsNotNone(sandbox_rule, "Missing sandboxes permission")
        if sandbox_rule:
            self.assertIn("create", sandbox_rule.get("verbs", []))
            self.assertIn("delete", sandbox_rule.get("verbs", []))
            self.assertIn("get", sandbox_rule.get("verbs", []))
            self.assertIn("list", sandbox_rule.get("verbs", []))
            self.assertIn("watch", sandbox_rule.get("verbs", []))
            self.assertIn("update", sandbox_rule.get("verbs", []))
            self.assertIn("patch", sandbox_rule.get("verbs", []))

    def test_volcano_cr_exists(self):
        """Test Volcano Scheduler ClusterRole exists."""
        path = RBAC_DIR / "clusterroles" / "volcano-scheduler.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_volcano_cr_structure(self):
        """Test Volcano Scheduler ClusterRole structure."""
        path = RBAC_DIR / "clusterroles" / "volcano-scheduler.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc["apiVersion"], "rbac.authorization.k8s.io/v1")
        self.assertEqual(doc["kind"], "ClusterRole")
        self.assertEqual(doc["metadata"]["name"], "volcano-scheduler")
        self.assertIn("rules", doc)


class TestClusterRoleBindings(unittest.TestCase):
    """Test ClusterRoleBinding manifests."""

    def test_workloadmanager_crb_exists(self):
        """Test WorkloadManager ClusterRoleBinding exists."""
        path = RBAC_DIR / "clusterrolebindings" / "workloadmanager.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_workloadmanager_crb_structure(self):
        """Test WorkloadManager ClusterRoleBinding structure."""
        path = RBAC_DIR / "clusterrolebindings" / "workloadmanager.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc["apiVersion"], "rbac.authorization.k8s.io/v1")
        self.assertEqual(doc["kind"], "ClusterRoleBinding")
        self.assertEqual(doc["metadata"]["name"], "workloadmanager")
        self.assertIn("roleRef", doc)
        self.assertEqual(doc["roleRef"]["kind"], "ClusterRole")
        self.assertEqual(doc["roleRef"]["name"], "workloadmanager")
        self.assertIn("subjects", doc)
        self.assertEqual(len(doc["subjects"]), 1)
        self.assertEqual(doc["subjects"][0]["kind"], "ServiceAccount")
        self.assertEqual(doc["subjects"][0]["name"], "workloadmanager")

    def test_volcano_crb_exists(self):
        """Test Volcano Scheduler ClusterRoleBinding exists."""
        path = RBAC_DIR / "clusterrolebindings" / "volcano-scheduler.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_volcano_crb_structure(self):
        """Test Volcano Scheduler ClusterRoleBinding structure."""
        path = RBAC_DIR / "clusterrolebindings" / "volcano-scheduler.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc["apiVersion"], "rbac.authorization.k8s.io/v1")
        self.assertEqual(doc["kind"], "ClusterRoleBinding")
        self.assertEqual(doc["metadata"]["name"], "volcano-scheduler")


class TestRoles(unittest.TestCase):
    """Test Role manifests."""

    def test_router_role_exists(self):
        """Test Router Role exists."""
        path = RBAC_DIR / "roles" / "router.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_router_role_structure(self):
        """Test Router Role structure."""
        path = RBAC_DIR / "roles" / "router.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc["apiVersion"], "rbac.authorization.k8s.io/v1")
        self.assertEqual(doc["kind"], "Role")
        self.assertEqual(doc["metadata"]["name"], "agentcube-router")
        self.assertEqual(doc["metadata"]["namespace"], "agentcube")
        self.assertIn("rules", doc)

    def test_router_role_is_namespace_scoped(self):
        """Test Router Role is namespace-scoped (not ClusterRole)."""
        path = RBAC_DIR / "roles" / "router.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc["kind"], "Role", "Router should use Role, not ClusterRole")
        self.assertIn("namespace", doc["metadata"])


class TestRoleBindings(unittest.TestCase):
    """Test RoleBinding manifests."""

    def test_router_rb_exists(self):
        """Test Router RoleBinding exists."""
        path = RBAC_DIR / "rolebindings" / "router.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_router_rb_structure(self):
        """Test Router RoleBinding structure."""
        path = RBAC_DIR / "rolebindings" / "router.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc["apiVersion"], "rbac.authorization.k8s.io/v1")
        self.assertEqual(doc["kind"], "RoleBinding")
        self.assertEqual(doc["metadata"]["name"], "agentcube-router")
        self.assertEqual(doc["metadata"]["namespace"], "agentcube")
        self.assertIn("roleRef", doc)
        self.assertEqual(doc["roleRef"]["kind"], "Role")
        self.assertEqual(doc["roleRef"]["name"], "agentcube-router")
        self.assertIn("subjects", doc)


class TestCombinedManifest(unittest.TestCase):
    """Test combined rbac-all.yaml manifest."""

    def test_combined_manifest_exists(self):
        """Test combined manifest exists."""
        path = RBAC_DIR / "rbac-all.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_combined_manifest_documents(self):
        """Test combined manifest contains all documents."""
        path = RBAC_DIR / "rbac-all.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))

        # Filter out None documents (from empty YAML sections)
        docs = [d for d in docs if d is not None]

        # Should have at least 10 documents
        self.assertGreaterEqual(len(docs), 10, f"Expected >=10 documents, got {len(docs)}")

        # Check for required kinds
        kinds = [doc.get("kind") for doc in docs]
        self.assertIn("Namespace", kinds)
        self.assertIn("ServiceAccount", kinds)
        self.assertIn("ClusterRole", kinds)
        self.assertIn("ClusterRoleBinding", kinds)
        self.assertIn("Role", kinds)
        self.assertIn("RoleBinding", kinds)


class TestNamespace(unittest.TestCase):
    """Test namespace manifest."""

    def test_namespace_exists(self):
        """Test namespace manifest exists."""
        path = RBAC_DIR / "namespace.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_namespace_structure(self):
        """Test namespace manifest structure."""
        path = RBAC_DIR / "namespace.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc["apiVersion"], "v1")
        self.assertEqual(doc["kind"], "Namespace")
        self.assertEqual(doc["metadata"]["name"], "agentcube")


class TestKustomization(unittest.TestCase):
    """Test kustomization.yaml."""

    def test_kustomization_exists(self):
        """Test kustomization.yaml exists."""
        path = RBAC_DIR / "kustomization.yaml"
        self.assertTrue(path.exists(), f"File not found: {path}")

    def test_kustomization_structure(self):
        """Test kustomization.yaml structure."""
        path = RBAC_DIR / "kustomization.yaml"
        with open(path) as f:
            doc = yaml.safe_load(f)

        self.assertIn("apiVersion", doc)
        self.assertIn("kind", doc)
        self.assertEqual(doc["kind"], "Kustomization")
        self.assertIn("resources", doc)
        self.assertIn("namespace", doc)
        self.assertEqual(doc["namespace"], "agentcube")


if __name__ == "__main__":
    unittest.main(verbosity=2)
