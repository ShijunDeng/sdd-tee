/*
Copyright The Volcano Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package workloadmanager

import (
	"context"

	"k8s.io/apimachinery/pkg/runtime/schema"
)

var (
	SandboxGVR = schema.GroupVersionResource{
		Group:    "agents.x-k8s.io",
		Version:  "v1alpha1",
		Resource: "sandboxes",
	}

	SandboxClaimGVR = schema.GroupVersionResource{
		Group:    "agents.x-k8s.io",
		Version:  "v1alpha1",
		Resource: "sandboxclaims",
	}
)

type K8sClient struct{}

func NewK8sClient() *K8sClient {
	return &K8sClient{}
}

func (c *K8sClient) DeleteSandbox(ctx context.Context, namespace, name string) error {
	return nil
}

func (c *K8sClient) DeleteSandboxClaim(ctx context.Context, namespace, name string) error {
	return nil
}
