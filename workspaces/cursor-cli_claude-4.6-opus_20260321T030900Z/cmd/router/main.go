package main

import (
	"context"
	"flag"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/volcano-sh/agentcube/pkg/router"
	"github.com/volcano-sh/agentcube/pkg/store"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/klog/v2"
)

func restConfig() (*rest.Config, error) {
	if cfg, err := rest.InClusterConfig(); err == nil {
		return cfg, nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return nil, err
	}
	return clientcmd.BuildConfigFromFlags("", filepath.Join(home, ".kube", "config"))
}

func main() {
	klog.InitFlags(nil)
	port := flag.Int("port", 8443, "HTTP listen port")
	enableTLS := flag.Bool("enable-tls", false, "serve HTTPS")
	tlsCert := flag.String("tls-cert", "", "path to TLS certificate")
	tlsKey := flag.String("tls-key", "", "path to TLS private key")
	debug := flag.Bool("debug", false, "enable Gin debug mode")
	maxConcurrent := flag.Int("max-concurrent-requests", 0, "limit in-flight HTTP requests (0 = default 1000)")
	flag.Parse()

	rc, err := restConfig()
	if err != nil {
		klog.Fatal(err)
	}
	cs, err := kubernetes.NewForConfig(rc)
	if err != nil {
		klog.Fatal(err)
	}

	st, err := store.Storage()
	if err != nil {
		klog.Fatal(err)
	}
	defer func() {
		if err := st.Close(); err != nil {
			klog.ErrorS(err, "close store")
		}
	}()

	jwtm := router.NewJWTManager(cs)
	initCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	if err := jwtm.LoadOrCreateIdentity(initCtx); err != nil {
		klog.ErrorS(err, "router JWT identity not loaded; upstream auth may fail")
	}
	cancel()

	cfg := router.Config{
		Port:                  *port,
		EnableTLS:             *enableTLS,
		TLSCert:               *tlsCert,
		TLSKey:                *tlsKey,
		Debug:                 *debug,
		MaxConcurrentRequests: *maxConcurrent,
	}
	srv, err := router.NewServer(cfg, st, jwtm)
	if err != nil {
		klog.Fatal(err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	if err := srv.Run(ctx); err != nil && err != context.Canceled {
		klog.ErrorS(err, "router exited")
		os.Exit(1)
	}
}
