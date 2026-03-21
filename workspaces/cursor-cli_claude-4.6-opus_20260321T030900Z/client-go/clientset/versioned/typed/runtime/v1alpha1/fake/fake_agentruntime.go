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
	"context"

	runtimeapi "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/labels"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/testing"
)

// FakeAgentRuntimes implements AgentRuntimeInterface.
type FakeAgentRuntimes struct {
	Fake *FakeRuntimeV1alpha1
	ns   string
}

var agentRuntimesResource = runtimeapi.SchemeGroupVersion.WithResource("agentruntimes")
var agentRuntimesKind = runtimeapi.SchemeGroupVersion.WithKind(runtimeapi.AgentRuntimeKind)

// Get returns the named AgentRuntime.
func (c *FakeAgentRuntimes) Get(ctx context.Context, name string, options metav1.GetOptions) (result *runtimeapi.AgentRuntime, err error) {
	emptyResult := &runtimeapi.AgentRuntime{}
	obj, err := c.Fake.
		Invokes(testing.NewGetActionWithOptions(agentRuntimesResource, c.ns, name, options), emptyResult)
	if obj == nil {
		return emptyResult, err
	}
	return obj.(*runtimeapi.AgentRuntime), err
}

// List returns AgentRuntimes matching the list options.
func (c *FakeAgentRuntimes) List(ctx context.Context, opts metav1.ListOptions) (result *runtimeapi.AgentRuntimeList, err error) {
	emptyResult := &runtimeapi.AgentRuntimeList{}
	obj, err := c.Fake.
		Invokes(testing.NewListActionWithOptions(agentRuntimesResource, agentRuntimesKind, c.ns, opts), emptyResult)
	if obj == nil {
		return emptyResult, err
	}
	label, _, _ := testing.ExtractFromListOptions(opts)
	if label == nil {
		label = labels.Everything()
	}
	list := &runtimeapi.AgentRuntimeList{ListMeta: obj.(*runtimeapi.AgentRuntimeList).ListMeta}
	for _, item := range obj.(*runtimeapi.AgentRuntimeList).Items {
		if label.Matches(labels.Set(item.Labels)) {
			list.Items = append(list.Items, item)
		}
	}
	return list, err
}

// Watch watches AgentRuntimes.
func (c *FakeAgentRuntimes) Watch(ctx context.Context, opts metav1.ListOptions) (watch.Interface, error) {
	return c.Fake.InvokesWatch(testing.NewWatchActionWithOptions(agentRuntimesResource, c.ns, opts))
}

// Create creates an AgentRuntime.
func (c *FakeAgentRuntimes) Create(ctx context.Context, agentRuntime *runtimeapi.AgentRuntime, opts metav1.CreateOptions) (result *runtimeapi.AgentRuntime, err error) {
	emptyResult := &runtimeapi.AgentRuntime{}
	obj, err := c.Fake.
		Invokes(testing.NewCreateActionWithOptions(agentRuntimesResource, c.ns, agentRuntime, opts), emptyResult)
	if obj == nil {
		return emptyResult, err
	}
	return obj.(*runtimeapi.AgentRuntime), err
}

// Update updates an AgentRuntime.
func (c *FakeAgentRuntimes) Update(ctx context.Context, agentRuntime *runtimeapi.AgentRuntime, opts metav1.UpdateOptions) (result *runtimeapi.AgentRuntime, err error) {
	emptyResult := &runtimeapi.AgentRuntime{}
	obj, err := c.Fake.
		Invokes(testing.NewUpdateActionWithOptions(agentRuntimesResource, c.ns, agentRuntime, opts), emptyResult)
	if obj == nil {
		return emptyResult, err
	}
	return obj.(*runtimeapi.AgentRuntime), err
}

// UpdateStatus updates the status subresource of an AgentRuntime.
func (c *FakeAgentRuntimes) UpdateStatus(ctx context.Context, agentRuntime *runtimeapi.AgentRuntime, opts metav1.UpdateOptions) (result *runtimeapi.AgentRuntime, err error) {
	emptyResult := &runtimeapi.AgentRuntime{}
	obj, err := c.Fake.
		Invokes(testing.NewUpdateSubresourceActionWithOptions(agentRuntimesResource, "status", c.ns, agentRuntime, opts), emptyResult)
	if obj == nil {
		return emptyResult, err
	}
	return obj.(*runtimeapi.AgentRuntime), err
}

// Delete deletes an AgentRuntime.
func (c *FakeAgentRuntimes) Delete(ctx context.Context, name string, opts metav1.DeleteOptions) error {
	_, err := c.Fake.
		Invokes(testing.NewDeleteActionWithOptions(agentRuntimesResource, c.ns, name, opts), &runtimeapi.AgentRuntime{})
	return err
}

// DeleteCollection deletes a collection of AgentRuntimes.
func (c *FakeAgentRuntimes) DeleteCollection(ctx context.Context, opts metav1.DeleteOptions, listOpts metav1.ListOptions) error {
	action := testing.NewDeleteCollectionActionWithOptions(agentRuntimesResource, c.ns, opts, listOpts)
	_, err := c.Fake.Invokes(action, &runtimeapi.AgentRuntimeList{})
	return err
}

// Patch applies a patch to an AgentRuntime.
func (c *FakeAgentRuntimes) Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts metav1.PatchOptions, subresources ...string) (result *runtimeapi.AgentRuntime, err error) {
	emptyResult := &runtimeapi.AgentRuntime{}
	obj, err := c.Fake.
		Invokes(testing.NewPatchSubresourceActionWithOptions(agentRuntimesResource, c.ns, name, pt, data, opts, subresources...), emptyResult)
	if obj == nil {
		return emptyResult, err
	}
	return obj.(*runtimeapi.AgentRuntime), err
}
