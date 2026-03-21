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

// CodeInterpreterLister lists CodeInterpreter objects from all namespaces or combines namespace listers.
type CodeInterpreterLister interface {
	List(selector labels.Selector) (ret []*runtimeapi.CodeInterpreter, err error)
	CodeInterpreters(namespace string) CodeInterpreterNamespaceLister
	CodeInterpreterListerExpansion
}

// CodeInterpreterNamespaceLister can list and get CodeInterpreters in one namespace.
type CodeInterpreterNamespaceLister interface {
	List(selector labels.Selector) (ret []*runtimeapi.CodeInterpreter, err error)
	Get(name string) (*runtimeapi.CodeInterpreter, error)
	CodeInterpreterNamespaceListerExpansion
}

type codeInterpreterLister struct {
	indexer cache.Indexer
}

// NewCodeInterpreterLister returns a new CodeInterpreterLister.
func NewCodeInterpreterLister(indexer cache.Indexer) CodeInterpreterLister {
	return &codeInterpreterLister{indexer: indexer}
}

func (s *codeInterpreterLister) List(selector labels.Selector) (ret []*runtimeapi.CodeInterpreter, err error) {
	err = cache.ListAll(s.indexer, selector, func(m interface{}) {
		ret = append(ret, m.(*runtimeapi.CodeInterpreter))
	})
	return ret, err
}

func (s *codeInterpreterLister) CodeInterpreters(namespace string) CodeInterpreterNamespaceLister {
	return codeInterpreterNamespaceLister{indexer: s.indexer, namespace: namespace}
}

type codeInterpreterNamespaceLister struct {
	indexer   cache.Indexer
	namespace string
}

func (s codeInterpreterNamespaceLister) List(selector labels.Selector) (ret []*runtimeapi.CodeInterpreter, err error) {
	err = cache.ListAllByNamespace(s.indexer, s.namespace, selector, func(m interface{}) {
		ret = append(ret, m.(*runtimeapi.CodeInterpreter))
	})
	return ret, err
}

func (s codeInterpreterNamespaceLister) Get(name string) (*runtimeapi.CodeInterpreter, error) {
	obj, exists, err := s.indexer.GetByKey(s.namespace + "/" + name)
	if err != nil {
		return nil, err
	}
	if !exists {
		return nil, apierrors.NewNotFound(runtimeapi.Resource("codeinterpreters"), name)
	}
	return obj.(*runtimeapi.CodeInterpreter), nil
}
