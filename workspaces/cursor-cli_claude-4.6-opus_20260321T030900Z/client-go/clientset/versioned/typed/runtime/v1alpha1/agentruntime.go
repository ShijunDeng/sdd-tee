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

package v1alpha1

import (
	"context"
	"time"

	"github.com/volcano-sh/agentcube/client-go/clientset/versioned/scheme"
	runtimeapi "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/rest"
)

// AgentRuntimesGetter returns an AgentRuntimeInterface scoped to a namespace.
type AgentRuntimesGetter interface {
	AgentRuntimes(namespace string) AgentRuntimeInterface
}

// AgentRuntimeInterface has methods to work with AgentRuntime resources.
type AgentRuntimeInterface interface {
	Create(ctx context.Context, agentRuntime *runtimeapi.AgentRuntime, opts metav1.CreateOptions) (*runtimeapi.AgentRuntime, error)
	Update(ctx context.Context, agentRuntime *runtimeapi.AgentRuntime, opts metav1.UpdateOptions) (*runtimeapi.AgentRuntime, error)
	UpdateStatus(ctx context.Context, agentRuntime *runtimeapi.AgentRuntime, opts metav1.UpdateOptions) (*runtimeapi.AgentRuntime, error)
	Delete(ctx context.Context, name string, opts metav1.DeleteOptions) error
	DeleteCollection(ctx context.Context, opts metav1.DeleteOptions, listOpts metav1.ListOptions) error
	Get(ctx context.Context, name string, opts metav1.GetOptions) (*runtimeapi.AgentRuntime, error)
	List(ctx context.Context, opts metav1.ListOptions) (*runtimeapi.AgentRuntimeList, error)
	Watch(ctx context.Context, opts metav1.ListOptions) (watch.Interface, error)
	Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts metav1.PatchOptions, subresources ...string) (*runtimeapi.AgentRuntime, error)
	AgentRuntimeExpansion
}

type agentRuntimes struct {
	client rest.Interface
	ns     string
}

func newAgentRuntimes(c *RuntimeV1alpha1Client, namespace string) *agentRuntimes {
	return &agentRuntimes{
		client: c.RESTClient(),
		ns:     namespace,
	}
}

func (c *agentRuntimes) Get(ctx context.Context, name string, options metav1.GetOptions) (result *runtimeapi.AgentRuntime, err error) {
	result = &runtimeapi.AgentRuntime{}
	err = c.client.Get().
		Namespace(c.ns).
		Resource("agentruntimes").
		Name(name).
		VersionedParams(&options, scheme.ParameterCodec).
		Do(ctx).
		Into(result)
	return
}

func (c *agentRuntimes) List(ctx context.Context, opts metav1.ListOptions) (result *runtimeapi.AgentRuntimeList, err error) {
	var timeout time.Duration
	if opts.TimeoutSeconds != nil {
		timeout = time.Duration(*opts.TimeoutSeconds) * time.Second
	}
	result = &runtimeapi.AgentRuntimeList{}
	err = c.client.Get().
		Namespace(c.ns).
		Resource("agentruntimes").
		VersionedParams(&opts, scheme.ParameterCodec).
		Timeout(timeout).
		Do(ctx).
		Into(result)
	return
}

func (c *agentRuntimes) Watch(ctx context.Context, opts metav1.ListOptions) (watch.Interface, error) {
	var timeout time.Duration
	if opts.TimeoutSeconds != nil {
		timeout = time.Duration(*opts.TimeoutSeconds) * time.Second
	}
	opts.Watch = true
	return c.client.Get().
		Namespace(c.ns).
		Resource("agentruntimes").
		VersionedParams(&opts, scheme.ParameterCodec).
		Timeout(timeout).
		Watch(ctx)
}

func (c *agentRuntimes) Create(ctx context.Context, agentRuntime *runtimeapi.AgentRuntime, opts metav1.CreateOptions) (result *runtimeapi.AgentRuntime, err error) {
	result = &runtimeapi.AgentRuntime{}
	err = c.client.Post().
		Namespace(c.ns).
		Resource("agentruntimes").
		VersionedParams(&opts, scheme.ParameterCodec).
		Body(agentRuntime).
		Do(ctx).
		Into(result)
	return
}

func (c *agentRuntimes) Update(ctx context.Context, agentRuntime *runtimeapi.AgentRuntime, opts metav1.UpdateOptions) (result *runtimeapi.AgentRuntime, err error) {
	result = &runtimeapi.AgentRuntime{}
	err = c.client.Put().
		Namespace(c.ns).
		Resource("agentruntimes").
		Name(agentRuntime.Name).
		VersionedParams(&opts, scheme.ParameterCodec).
		Body(agentRuntime).
		Do(ctx).
		Into(result)
	return
}

func (c *agentRuntimes) UpdateStatus(ctx context.Context, agentRuntime *runtimeapi.AgentRuntime, opts metav1.UpdateOptions) (result *runtimeapi.AgentRuntime, err error) {
	result = &runtimeapi.AgentRuntime{}
	err = c.client.Put().
		Namespace(c.ns).
		Resource("agentruntimes").
		Name(agentRuntime.Name).
		SubResource("status").
		VersionedParams(&opts, scheme.ParameterCodec).
		Body(agentRuntime).
		Do(ctx).
		Into(result)
	return
}

func (c *agentRuntimes) Delete(ctx context.Context, name string, opts metav1.DeleteOptions) error {
	return c.client.Delete().
		Namespace(c.ns).
		Resource("agentruntimes").
		Name(name).
		Body(&opts).
		Do(ctx).
		Error()
}

func (c *agentRuntimes) DeleteCollection(ctx context.Context, opts metav1.DeleteOptions, listOpts metav1.ListOptions) error {
	var timeout time.Duration
	if listOpts.TimeoutSeconds != nil {
		timeout = time.Duration(*listOpts.TimeoutSeconds) * time.Second
	}
	return c.client.Delete().
		Namespace(c.ns).
		Resource("agentruntimes").
		VersionedParams(&listOpts, scheme.ParameterCodec).
		Timeout(timeout).
		Body(&opts).
		Do(ctx).
		Error()
}

func (c *agentRuntimes) Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts metav1.PatchOptions, subresources ...string) (result *runtimeapi.AgentRuntime, err error) {
	result = &runtimeapi.AgentRuntime{}
	patch := c.client.Patch(pt).
		Namespace(c.ns).
		Resource("agentruntimes").
		Name(name)
	if len(subresources) > 0 {
		patch.SubResource(subresources...)
	}
	err = patch.VersionedParams(&opts, scheme.ParameterCodec).
		Body(data).
		Do(ctx).
		Into(result)
	return
}
