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

// FakeCodeInterpreters implements CodeInterpreterInterface.
type FakeCodeInterpreters struct {
	Fake *FakeRuntimeV1alpha1
	ns   string
}

var codeInterpretersResource = runtimeapi.SchemeGroupVersion.WithResource("codeinterpreters")

var codeInterpretersKind = runtimeapi.SchemeGroupVersion.WithKind(runtimeapi.CodeInterpreterKind)

// Get returns the named CodeInterpreter.
func (c *FakeCodeInterpreters) Get(ctx context.Context, name string, options metav1.GetOptions) (result *runtimeapi.CodeInterpreter, err error) {
	emptyResult := &runtimeapi.CodeInterpreter{}
	obj, err := c.Fake.
		Invokes(testing.NewGetActionWithOptions(codeInterpretersResource, c.ns, name, options), emptyResult)

	if obj == nil {
		return emptyResult, err
	}
	return obj.(*runtimeapi.CodeInterpreter), err
}

// List returns CodeInterpreters matching the list options.
func (c *FakeCodeInterpreters) List(ctx context.Context, opts metav1.ListOptions) (result *runtimeapi.CodeInterpreterList, err error) {
	emptyResult := &runtimeapi.CodeInterpreterList{}
	obj, err := c.Fake.
		Invokes(testing.NewListActionWithOptions(codeInterpretersResource, codeInterpretersKind, c.ns, opts), emptyResult)

	if obj == nil {
		return emptyResult, err
	}

	label, _, _ := testing.ExtractFromListOptions(opts)
	if label == nil {
		label = labels.Everything()
	}
	list := &runtimeapi.CodeInterpreterList{ListMeta: obj.(*runtimeapi.CodeInterpreterList).ListMeta}
	for _, item := range obj.(*runtimeapi.CodeInterpreterList).Items {
		if label.Matches(labels.Set(item.Labels)) {
			list.Items = append(list.Items, item)
		}
	}
	return list, err
}

// Watch watches CodeInterpreters.
func (c *FakeCodeInterpreters) Watch(ctx context.Context, opts metav1.ListOptions) (watch.Interface, error) {
	return c.Fake.
		InvokesWatch(testing.NewWatchActionWithOptions(codeInterpretersResource, c.ns, opts))
}

// Create creates a CodeInterpreter.
func (c *FakeCodeInterpreters) Create(ctx context.Context, codeInterpreter *runtimeapi.CodeInterpreter, opts metav1.CreateOptions) (result *runtimeapi.CodeInterpreter, err error) {
	emptyResult := &runtimeapi.CodeInterpreter{}
	obj, err := c.Fake.
		Invokes(testing.NewCreateActionWithOptions(codeInterpretersResource, c.ns, codeInterpreter, opts), emptyResult)

	if obj == nil {
		return emptyResult, err
	}
	return obj.(*runtimeapi.CodeInterpreter), err
}

// Update updates a CodeInterpreter.
func (c *FakeCodeInterpreters) Update(ctx context.Context, codeInterpreter *runtimeapi.CodeInterpreter, opts metav1.UpdateOptions) (result *runtimeapi.CodeInterpreter, err error) {
	emptyResult := &runtimeapi.CodeInterpreter{}
	obj, err := c.Fake.
		Invokes(testing.NewUpdateActionWithOptions(codeInterpretersResource, c.ns, codeInterpreter, opts), emptyResult)

	if obj == nil {
		return emptyResult, err
	}
	return obj.(*runtimeapi.CodeInterpreter), err
}

// UpdateStatus updates the status subresource of a CodeInterpreter.
func (c *FakeCodeInterpreters) UpdateStatus(ctx context.Context, codeInterpreter *runtimeapi.CodeInterpreter, opts metav1.UpdateOptions) (result *runtimeapi.CodeInterpreter, err error) {
	emptyResult := &runtimeapi.CodeInterpreter{}
	obj, err := c.Fake.
		Invokes(testing.NewUpdateSubresourceActionWithOptions(codeInterpretersResource, "status", c.ns, codeInterpreter, opts), emptyResult)

	if obj == nil {
		return emptyResult, err
	}
	return obj.(*runtimeapi.CodeInterpreter), err
}

// Delete deletes a CodeInterpreter.
func (c *FakeCodeInterpreters) Delete(ctx context.Context, name string, opts metav1.DeleteOptions) error {
	_, err := c.Fake.
		Invokes(testing.NewDeleteActionWithOptions(codeInterpretersResource, c.ns, name, opts), &runtimeapi.CodeInterpreter{})

	return err
}

// DeleteCollection deletes a collection of CodeInterpreters.
func (c *FakeCodeInterpreters) DeleteCollection(ctx context.Context, opts metav1.DeleteOptions, listOpts metav1.ListOptions) error {
	action := testing.NewDeleteCollectionActionWithOptions(codeInterpretersResource, c.ns, opts, listOpts)

	_, err := c.Fake.Invokes(action, &runtimeapi.CodeInterpreterList{})
	return err
}

// Patch applies a patch to a CodeInterpreter.
func (c *FakeCodeInterpreters) Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts metav1.PatchOptions, subresources ...string) (result *runtimeapi.CodeInterpreter, err error) {
	emptyResult := &runtimeapi.CodeInterpreter{}
	obj, err := c.Fake.
		Invokes(testing.NewPatchSubresourceActionWithOptions(codeInterpretersResource, c.ns, name, pt, data, opts, subresources...), emptyResult)

	if obj == nil {
		return emptyResult, err
	}
	return obj.(*runtimeapi.CodeInterpreter), err
}
