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

package internalinterfaces

import (
	"time"

	versioned "github.com/volcano-sh/agentcube/client-go/clientset/versioned"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/tools/cache"
)

// NewInformerFunc returns a SharedIndexInformer for the given clientset and resync period.
type NewInformerFunc func(versioned.Interface, time.Duration) cache.SharedIndexInformer

// SharedInformerFactory is a minimal factory interface to avoid import cycles.
type SharedInformerFactory interface {
	Start(stopCh <-chan struct{})
	InformerFor(obj runtime.Object, newFunc NewInformerFunc) cache.SharedIndexInformer
}

// TweakListOptionsFunc transforms list options before listing or watching.
type TweakListOptionsFunc func(*metav1.ListOptions)
