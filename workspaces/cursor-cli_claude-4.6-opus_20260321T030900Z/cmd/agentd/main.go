package main

import (
	"os"

	"github.com/volcano-sh/agentcube/pkg/agentd"
	agentsandboxv1 "github.com/volcano-sh/agentcube/pkg/apis/agentsandbox/v1alpha1"
	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	"k8s.io/klog/v2"
	ctrl "sigs.k8s.io/controller-runtime"
)

func main() {
	klog.InitFlags(nil)
	ctrl.SetLogger(klog.Background())

	scheme := runtime.NewScheme()
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))
	utilruntime.Must(agentsandboxv1.AddToScheme(scheme))

	cfg, err := ctrl.GetConfig()
	if err != nil {
		klog.Fatal(err)
	}

	mgr, err := ctrl.NewManager(cfg, ctrl.Options{
		Scheme: scheme,
	})
	if err != nil {
		klog.Fatal(err)
	}

	rec := &agentd.Reconciler{
		Client: mgr.GetClient(),
		Scheme: mgr.GetScheme(),
	}
	if err := rec.SetupWithManager(mgr); err != nil {
		klog.Fatal(err)
	}

	klog.InfoS("starting agentd manager")
	if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
		klog.ErrorS(err, "agentd manager exited")
		os.Exit(1)
	}
}
