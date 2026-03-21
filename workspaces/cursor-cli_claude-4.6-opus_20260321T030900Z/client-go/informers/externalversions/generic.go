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

package externalversions

import (
	"fmt"

	runtimeapi "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/tools/cache"
)

// GenericInformer is a SharedIndexInformer that delegates to typed informers by resource.
type GenericInformer interface {
	Informer() cache.SharedIndexInformer
	Lister() cache.GenericLister
}

type genericInformer struct {
	informer cache.SharedIndexInformer
	resource schema.GroupResource
}

// Informer returns the SharedIndexInformer.
func (f *genericInformer) Informer() cache.SharedIndexInformer {
	return f.informer
}

// Lister returns the GenericLister.
func (f *genericInformer) Lister() cache.GenericLister {
	return cache.NewGenericLister(f.Informer().GetIndexer(), f.resource)
}

// ForResource returns a GenericInformer for the given GroupVersionResource.
func (f *sharedInformerFactory) ForResource(resource schema.GroupVersionResource) (GenericInformer, error) {
	switch resource {
	case runtimeapi.SchemeGroupVersion.WithResource("agentruntimes"):
		return &genericInformer{
			resource: resource.GroupResource(),
			informer: f.Runtime().V1alpha1().AgentRuntimes().Informer(),
		}, nil
	case runtimeapi.SchemeGroupVersion.WithResource("codeinterpreters"):
		return &genericInformer{
			resource: resource.GroupResource(),
			informer: f.Runtime().V1alpha1().CodeInterpreters().Informer(),
		}, nil
	default:
		return nil, fmt.Errorf("no informer found for %v", resource)
	}
}
