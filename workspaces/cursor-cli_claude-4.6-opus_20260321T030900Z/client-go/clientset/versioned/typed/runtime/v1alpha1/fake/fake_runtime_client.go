// Copyright 2026 The Volcano Authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//	http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package fake

import (
	runtimev1alpha1 "github.com/volcano-sh/agentcube/client-go/clientset/versioned/typed/runtime/v1alpha1"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/testing"
)

// FakeRuntimeV1alpha1 implements RuntimeV1alpha1Interface using a testing.Fake.
type FakeRuntimeV1alpha1 struct {
	*testing.Fake
}

func (c *FakeRuntimeV1alpha1) AgentRuntimes(namespace string) runtimev1alpha1.AgentRuntimeInterface {
	return &FakeAgentRuntimes{c, namespace}
}

func (c *FakeRuntimeV1alpha1) CodeInterpreters(namespace string) runtimev1alpha1.CodeInterpreterInterface {
	return &FakeCodeInterpreters{c, namespace}
}

// RESTClient returns nil for the fake client.
func (c *FakeRuntimeV1alpha1) RESTClient() rest.Interface {
	var ret *rest.RESTClient
	return ret
}
