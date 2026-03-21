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
	clientset "github.com/volcano-sh/agentcube/client-go/clientset/versioned"
	runtimev1alpha1 "github.com/volcano-sh/agentcube/client-go/clientset/versioned/typed/runtime/v1alpha1"
	fakeruntimev1alpha1 "github.com/volcano-sh/agentcube/client-go/clientset/versioned/typed/runtime/v1alpha1/fake"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/discovery"
	fakediscovery "k8s.io/client-go/discovery/fake"
	"k8s.io/client-go/testing"
)

// NewSimpleClientset returns a clientset backed by a simple object tracker.
func NewSimpleClientset(objects ...runtime.Object) *Clientset {
	o := testing.NewObjectTracker(scheme, codecs.UniversalDecoder())
	for _, obj := range objects {
		if err := o.Add(obj); err != nil {
			panic(err)
		}
	}

	cs := &Clientset{tracker: o}
	cs.discovery = &fakediscovery.FakeDiscovery{Fake: &cs.Fake}
	cs.AddReactor("*", "*", testing.ObjectReaction(o))
	cs.AddWatchReactor("*", func(action testing.Action) (handled bool, ret watch.Interface, err error) {
		gvr := action.GetResource()
		ns := action.GetNamespace()
		w, err := o.Watch(gvr, ns)
		if err != nil {
			return false, nil, err
		}
		return true, w, nil
	})

	return cs
}

// Clientset implements clientset.Interface. Embed it to fake individual methods.
type Clientset struct {
	testing.Fake
	discovery *fakediscovery.FakeDiscovery
	tracker   testing.ObjectTracker
}

// Discovery returns the fake discovery client.
func (c *Clientset) Discovery() discovery.DiscoveryInterface {
	return c.discovery
}

// Tracker returns the object tracker backing this clientset.
func (c *Clientset) Tracker() testing.ObjectTracker {
	return c.tracker
}

// RuntimeV1alpha1 returns the fake RuntimeV1alpha1 client.
func (c *Clientset) RuntimeV1alpha1() runtimev1alpha1.RuntimeV1alpha1Interface {
	return &fakeruntimev1alpha1.FakeRuntimeV1alpha1{Fake: &c.Fake}
}

var (
	_ clientset.Interface = &Clientset{}
	_ testing.FakeClient  = &Clientset{}
)
