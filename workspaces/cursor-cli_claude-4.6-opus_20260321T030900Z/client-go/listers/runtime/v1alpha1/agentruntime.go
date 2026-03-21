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
	runtimeapi "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/labels"
	"k8s.io/client-go/tools/cache"
)

// AgentRuntimeLister lists AgentRuntime objects from all namespaces or combines namespace listers.
type AgentRuntimeLister interface {
	List(selector labels.Selector) (ret []*runtimeapi.AgentRuntime, err error)
	AgentRuntimes(namespace string) AgentRuntimeNamespaceLister
	AgentRuntimeListerExpansion
}

// AgentRuntimeNamespaceLister can list and get AgentRuntimes in one namespace.
type AgentRuntimeNamespaceLister interface {
	List(selector labels.Selector) (ret []*runtimeapi.AgentRuntime, err error)
	Get(name string) (*runtimeapi.AgentRuntime, error)
	AgentRuntimeNamespaceListerExpansion
}

type agentRuntimeLister struct {
	indexer cache.Indexer
}

// NewAgentRuntimeLister returns a new AgentRuntimeLister.
func NewAgentRuntimeLister(indexer cache.Indexer) AgentRuntimeLister {
	return &agentRuntimeLister{indexer: indexer}
}

func (s *agentRuntimeLister) List(selector labels.Selector) (ret []*runtimeapi.AgentRuntime, err error) {
	err = cache.ListAll(s.indexer, selector, func(m interface{}) {
		ret = append(ret, m.(*runtimeapi.AgentRuntime))
	})
	return ret, err
}

func (s *agentRuntimeLister) AgentRuntimes(namespace string) AgentRuntimeNamespaceLister {
	return agentRuntimeNamespaceLister{indexer: s.indexer, namespace: namespace}
}

type agentRuntimeNamespaceLister struct {
	indexer   cache.Indexer
	namespace string
}

func (s agentRuntimeNamespaceLister) List(selector labels.Selector) (ret []*runtimeapi.AgentRuntime, err error) {
	err = cache.ListAllByNamespace(s.indexer, s.namespace, selector, func(m interface{}) {
		ret = append(ret, m.(*runtimeapi.AgentRuntime))
	})
	return ret, err
}

func (s agentRuntimeNamespaceLister) Get(name string) (*runtimeapi.AgentRuntime, error) {
	obj, exists, err := s.indexer.GetByKey(s.namespace + "/" + name)
	if err != nil {
		return nil, err
	}
	if !exists {
		return nil, apierrors.NewNotFound(runtimeapi.Resource("agentruntimes"), name)
	}
	return obj.(*runtimeapi.AgentRuntime), nil
}
