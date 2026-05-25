/*
Copyright The Volcano Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package workloadmanager

import (
	"time"
)

const (
	DefaultSandboxTTL          = 8 * time.Hour
	DefaultSandboxIdleTimeout  = 15 * time.Minute
	DefaultGCInterval          = 15 * time.Second
	DefaultTokenCacheTTL       = 5 * time.Minute
	DefaultTokenCacheSize      = 1000
	DefaultClientCacheSize     = 100
	DefaultClientCacheExpiry   = 30 * time.Minute
	DefaultHTTPReadTimeout     = 15 * time.Second
	DefaultHTTPIdleTimeout     = 90 * time.Second
	DefaultShutdownTimeout     = 15 * time.Second
	DefaultInformerSyncTimeout = 1 * time.Minute
)
