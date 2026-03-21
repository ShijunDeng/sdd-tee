package main

import (
	"context"
	"errors"
	"flag"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	agentsandboxv1 "github.com/volcano-sh/agentcube/pkg/apis/agentsandbox/v1alpha1"
	runtimev1alpha1 "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
	"github.com/volcano-sh/agentcube/pkg/controller/workloadmanager"
	"github.com/volcano-sh/agentcube/pkg/store"
	wlm "github.com/volcano-sh/agentcube/pkg/workloadmanager"
	"golang.org/x/sync/errgroup"
	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	"k8s.io/klog/v2"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	metricsserver "sigs.k8s.io/controller-runtime/pkg/metrics/server"
)

func main() {
	klog.InitFlags(nil)
	port := flag.Int("port", 8082, "HTTP listen port for workload-manager API")
	runtimeClass := flag.String("runtime-class-name", "kuasar-vmm", "default RuntimeClass for sandboxes without spec")
	enableTLS := flag.Bool("enable-tls", false, "serve HTTPS")
	tlsCert := flag.String("tls-cert", "", "path to TLS certificate")
	tlsKey := flag.String("tls-key", "", "path to TLS private key")
	enableAuth := flag.Bool("enable-auth", false, "require Authorization: Bearer token validated via TokenReview")
	flag.Parse()

	scheme := runtime.NewScheme()
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))
	utilruntime.Must(agentsandboxv1.AddToScheme(scheme))
	utilruntime.Must(runtimev1alpha1.AddToScheme(scheme))

	cfg, err := ctrl.GetConfig()
	if err != nil {
		klog.Fatal(err)
	}

	kube, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		klog.Fatal(err)
	}
	dyn, err := dynamic.NewForConfig(cfg)
	if err != nil {
		klog.Fatal(err)
	}

	mgr, err := ctrl.NewManager(cfg, ctrl.Options{
		Scheme: scheme,
		Metrics: metricsserver.Options{
			BindAddress: "0",
		},
		HealthProbeBindAddress: "0",
		LeaderElection:         false,
	})
	if err != nil {
		klog.Fatal(err)
	}

	if err := mgr.AddHealthzCheck("ping", healthz.Ping); err != nil {
		klog.Fatal(err)
	}

	sandboxRec := &workloadmanager.SandboxReconciler{
		Client:           mgr.GetClient(),
		Scheme:           mgr.GetScheme(),
		RuntimeClassName: strings.TrimSpace(*runtimeClass),
	}
	if err := sandboxRec.SetupWithManager(mgr); err != nil {
		klog.Fatal(err)
	}

	ciRec := &workloadmanager.CodeInterpreterReconciler{
		Client: mgr.GetClient(),
		Scheme: mgr.GetScheme(),
		Warm:   &wlm.CodeInterpreterReconciler{Dyn: dyn},
	}
	if err := ciRec.SetupWithManager(mgr); err != nil {
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

	initCtx, cancelInit := context.WithTimeout(context.Background(), 30*time.Second)
	if err := wlm.InitPublicKeyCache(initCtx, kube); err != nil {
		klog.ErrorS(err, "init public key cache")
	}
	cancelInit()

	rc := wlm.NewSandboxReconciler()
	builder := &wlm.SandboxBuilder{Dyn: dyn, Kube: kube, RC: rc}

	var tc *wlm.TokenCache
	if *enableAuth {
		tc, err = wlm.NewTokenCache()
		if err != nil {
			klog.Fatal(err)
		}
	}

	wcfg := wlm.Config{
		Port:             *port,
		RuntimeClassName: strings.TrimSpace(*runtimeClass),
		EnableTLS:        *enableTLS,
		TLSCert:          strings.TrimSpace(*tlsCert),
		TLSKey:           strings.TrimSpace(*tlsKey),
		EnableAuth:       *enableAuth,
	}
	api := wlm.NewAPIServer(wcfg, kube, dyn, st, builder, rc, tc)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	wlm.StartGarbageCollection(ctx, kube, dyn, st)

	grp, gctx := errgroup.WithContext(ctx)

	grp.Go(func() error {
		klog.InfoS("starting controller-runtime manager")
		return mgr.Start(gctx)
	})

	grp.Go(func() error {
		if err := api.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			return err
		}
		return nil
	})

	grp.Go(func() error {
		<-gctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		return api.Shutdown(shutdownCtx)
	})

	if err := grp.Wait(); err != nil && !errors.Is(err, context.Canceled) {
		klog.ErrorS(err, "workload-manager exited")
		os.Exit(1)
	}
}
