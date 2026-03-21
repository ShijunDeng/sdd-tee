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
	"net/http"

	"github.com/volcano-sh/agentcube/client-go/clientset/versioned/scheme"
	runtimeapi "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
	"k8s.io/client-go/rest"
)

// RuntimeV1alpha1Interface has methods to work with runtime.agentcube.volcano.sh/v1alpha1 resources.
type RuntimeV1alpha1Interface interface {
	RESTClient() rest.Interface
	AgentRuntimesGetter
	CodeInterpretersGetter
}

// RuntimeV1alpha1Client is used to interact with features provided by the runtime.agentcube.volcano.sh group.
type RuntimeV1alpha1Client struct {
	restClient rest.Interface
}

func (c *RuntimeV1alpha1Client) AgentRuntimes(namespace string) AgentRuntimeInterface {
	return newAgentRuntimes(c, namespace)
}

func (c *RuntimeV1alpha1Client) CodeInterpreters(namespace string) CodeInterpreterInterface {
	return newCodeInterpreters(c, namespace)
}

// NewForConfig creates a new RuntimeV1alpha1Client for the given config.
func NewForConfig(c *rest.Config) (*RuntimeV1alpha1Client, error) {
	config := *c
	if err := setConfigDefaults(&config); err != nil {
		return nil, err
	}
	httpClient, err := rest.HTTPClientFor(&config)
	if err != nil {
		return nil, err
	}
	return NewForConfigAndClient(&config, httpClient)
}

// NewForConfigAndClient creates a new RuntimeV1alpha1Client for the given config and HTTP client.
func NewForConfigAndClient(c *rest.Config, h *http.Client) (*RuntimeV1alpha1Client, error) {
	config := *c
	if err := setConfigDefaults(&config); err != nil {
		return nil, err
	}
	client, err := rest.RESTClientForConfigAndClient(&config, h)
	if err != nil {
		return nil, err
	}
	return &RuntimeV1alpha1Client{client}, nil
}

// NewForConfigOrDie creates a new RuntimeV1alpha1Client for the given config and panics on error.
func NewForConfigOrDie(c *rest.Config) *RuntimeV1alpha1Client {
	client, err := NewForConfig(c)
	if err != nil {
		panic(err)
	}
	return client
}

// New creates a new RuntimeV1alpha1Client for the given RESTClient.
func New(c rest.Interface) *RuntimeV1alpha1Client {
	return &RuntimeV1alpha1Client{c}
}

func setConfigDefaults(config *rest.Config) error {
	gv := runtimeapi.SchemeGroupVersion
	config.GroupVersion = &gv
	config.APIPath = "/apis"
	config.NegotiatedSerializer = scheme.Codecs.WithoutConversion()

	if config.UserAgent == "" {
		config.UserAgent = rest.DefaultKubernetesUserAgent()
	}

	return nil
}

// RESTClient returns a RESTClient used by this client implementation.
func (c *RuntimeV1alpha1Client) RESTClient() rest.Interface {
	if c == nil {
		return nil
	}
	return c.restClient
}
