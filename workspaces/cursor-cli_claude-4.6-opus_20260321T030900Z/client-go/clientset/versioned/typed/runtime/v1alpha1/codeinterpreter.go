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

// CodeInterpretersGetter returns a CodeInterpreterInterface scoped to a namespace.
type CodeInterpretersGetter interface {
	CodeInterpreters(namespace string) CodeInterpreterInterface
}

// CodeInterpreterInterface has methods to work with CodeInterpreter resources.
type CodeInterpreterInterface interface {
	Create(ctx context.Context, codeInterpreter *runtimeapi.CodeInterpreter, opts metav1.CreateOptions) (*runtimeapi.CodeInterpreter, error)
	Update(ctx context.Context, codeInterpreter *runtimeapi.CodeInterpreter, opts metav1.UpdateOptions) (*runtimeapi.CodeInterpreter, error)
	UpdateStatus(ctx context.Context, codeInterpreter *runtimeapi.CodeInterpreter, opts metav1.UpdateOptions) (*runtimeapi.CodeInterpreter, error)
	Delete(ctx context.Context, name string, opts metav1.DeleteOptions) error
	DeleteCollection(ctx context.Context, opts metav1.DeleteOptions, listOpts metav1.ListOptions) error
	Get(ctx context.Context, name string, opts metav1.GetOptions) (*runtimeapi.CodeInterpreter, error)
	List(ctx context.Context, opts metav1.ListOptions) (*runtimeapi.CodeInterpreterList, error)
	Watch(ctx context.Context, opts metav1.ListOptions) (watch.Interface, error)
	Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts metav1.PatchOptions, subresources ...string) (*runtimeapi.CodeInterpreter, error)
	CodeInterpreterExpansion
}

type codeInterpreters struct {
	client rest.Interface
	ns     string
}

func newCodeInterpreters(c *RuntimeV1alpha1Client, namespace string) *codeInterpreters {
	return &codeInterpreters{
		client: c.RESTClient(),
		ns:     namespace,
	}
}

func (c *codeInterpreters) Get(ctx context.Context, name string, options metav1.GetOptions) (result *runtimeapi.CodeInterpreter, err error) {
	result = &runtimeapi.CodeInterpreter{}
	err = c.client.Get().
		Namespace(c.ns).
		Resource("codeinterpreters").
		Name(name).
		VersionedParams(&options, scheme.ParameterCodec).
		Do(ctx).
		Into(result)
	return
}

func (c *codeInterpreters) List(ctx context.Context, opts metav1.ListOptions) (result *runtimeapi.CodeInterpreterList, err error) {
	var timeout time.Duration
	if opts.TimeoutSeconds != nil {
		timeout = time.Duration(*opts.TimeoutSeconds) * time.Second
	}
	result = &runtimeapi.CodeInterpreterList{}
	err = c.client.Get().
		Namespace(c.ns).
		Resource("codeinterpreters").
		VersionedParams(&opts, scheme.ParameterCodec).
		Timeout(timeout).
		Do(ctx).
		Into(result)
	return
}

func (c *codeInterpreters) Watch(ctx context.Context, opts metav1.ListOptions) (watch.Interface, error) {
	var timeout time.Duration
	if opts.TimeoutSeconds != nil {
		timeout = time.Duration(*opts.TimeoutSeconds) * time.Second
	}
	opts.Watch = true
	return c.client.Get().
		Namespace(c.ns).
		Resource("codeinterpreters").
		VersionedParams(&opts, scheme.ParameterCodec).
		Timeout(timeout).
		Watch(ctx)
}

func (c *codeInterpreters) Create(ctx context.Context, codeInterpreter *runtimeapi.CodeInterpreter, opts metav1.CreateOptions) (result *runtimeapi.CodeInterpreter, err error) {
	result = &runtimeapi.CodeInterpreter{}
	err = c.client.Post().
		Namespace(c.ns).
		Resource("codeinterpreters").
		VersionedParams(&opts, scheme.ParameterCodec).
		Body(codeInterpreter).
		Do(ctx).
		Into(result)
	return
}

func (c *codeInterpreters) Update(ctx context.Context, codeInterpreter *runtimeapi.CodeInterpreter, opts metav1.UpdateOptions) (result *runtimeapi.CodeInterpreter, err error) {
	result = &runtimeapi.CodeInterpreter{}
	err = c.client.Put().
		Namespace(c.ns).
		Resource("codeinterpreters").
		Name(codeInterpreter.Name).
		VersionedParams(&opts, scheme.ParameterCodec).
		Body(codeInterpreter).
		Do(ctx).
		Into(result)
	return
}

func (c *codeInterpreters) UpdateStatus(ctx context.Context, codeInterpreter *runtimeapi.CodeInterpreter, opts metav1.UpdateOptions) (result *runtimeapi.CodeInterpreter, err error) {
	result = &runtimeapi.CodeInterpreter{}
	err = c.client.Put().
		Namespace(c.ns).
		Resource("codeinterpreters").
		Name(codeInterpreter.Name).
		SubResource("status").
		VersionedParams(&opts, scheme.ParameterCodec).
		Body(codeInterpreter).
		Do(ctx).
		Into(result)
	return
}

func (c *codeInterpreters) Delete(ctx context.Context, name string, opts metav1.DeleteOptions) error {
	return c.client.Delete().
		Namespace(c.ns).
		Resource("codeinterpreters").
		Name(name).
		Body(&opts).
		Do(ctx).
		Error()
}

func (c *codeInterpreters) DeleteCollection(ctx context.Context, opts metav1.DeleteOptions, listOpts metav1.ListOptions) error {
	var timeout time.Duration
	if listOpts.TimeoutSeconds != nil {
		timeout = time.Duration(*listOpts.TimeoutSeconds) * time.Second
	}
	return c.client.Delete().
		Namespace(c.ns).
		Resource("codeinterpreters").
		VersionedParams(&listOpts, scheme.ParameterCodec).
		Timeout(timeout).
		Body(&opts).
		Do(ctx).
		Error()
}

func (c *codeInterpreters) Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts metav1.PatchOptions, subresources ...string) (result *runtimeapi.CodeInterpreter, err error) {
	result = &runtimeapi.CodeInterpreter{}
	patch := c.client.Patch(pt).
		Namespace(c.ns).
		Resource("codeinterpreters").
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
