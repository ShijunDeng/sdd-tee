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

	versioned "github.com/volcano-sh/agentcube/client-go/clientset/versioned"
	internalinterfaces "github.com/volcano-sh/agentcube/client-go/informers/externalversions/internalinterfaces"
	listersruntimev1alpha1 "github.com/volcano-sh/agentcube/client-go/listers/runtime/v1alpha1"
	runtimeapi "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	apimachineryruntime "k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/tools/cache"
)

// AgentRuntimeInformer provides access to a shared informer and lister for AgentRuntimes.
type AgentRuntimeInformer interface {
	Informer() cache.SharedIndexInformer
	Lister() listersruntimev1alpha1.AgentRuntimeLister
}

type agentRuntimeInformer struct {
	factory          internalinterfaces.SharedInformerFactory
	tweakListOptions internalinterfaces.TweakListOptionsFunc
	namespace        string
}

// NewAgentRuntimeInformer constructs a new informer for AgentRuntime (prefer the factory).
func NewAgentRuntimeInformer(client versioned.Interface, namespace string, resyncPeriod time.Duration, indexers cache.Indexers) cache.SharedIndexInformer {
	return NewFilteredAgentRuntimeInformer(client, namespace, resyncPeriod, indexers, nil)
}

// NewFilteredAgentRuntimeInformer constructs a new informer for AgentRuntime with optional list tweaks.
func NewFilteredAgentRuntimeInformer(client versioned.Interface, namespace string, resyncPeriod time.Duration, indexers cache.Indexers, tweakListOptions internalinterfaces.TweakListOptionsFunc) cache.SharedIndexInformer {
	return cache.NewSharedIndexInformer(
		&cache.ListWatch{
			ListFunc: func(options metav1.ListOptions) (apimachineryruntime.Object, error) {
				if tweakListOptions != nil {
					tweakListOptions(&options)
				}
				return client.RuntimeV1alpha1().AgentRuntimes(namespace).List(context.Background(), options)
			},
			WatchFunc: func(options metav1.ListOptions) (watch.Interface, error) {
				if tweakListOptions != nil {
					tweakListOptions(&options)
				}
				return client.RuntimeV1alpha1().AgentRuntimes(namespace).Watch(context.Background(), options)
			},
		},
		&runtimeapi.AgentRuntime{},
		resyncPeriod,
		indexers,
	)
}

func (f *agentRuntimeInformer) defaultInformer(client versioned.Interface, resyncPeriod time.Duration) cache.SharedIndexInformer {
	return NewFilteredAgentRuntimeInformer(client, f.namespace, resyncPeriod, cache.Indexers{cache.NamespaceIndex: cache.MetaNamespaceIndexFunc}, f.tweakListOptions)
}

func (f *agentRuntimeInformer) Informer() cache.SharedIndexInformer {
	return f.factory.InformerFor(&runtimeapi.AgentRuntime{}, f.defaultInformer)
}

func (f *agentRuntimeInformer) Lister() listersruntimev1alpha1.AgentRuntimeLister {
	return listersruntimev1alpha1.NewAgentRuntimeLister(f.Informer().GetIndexer())
}
