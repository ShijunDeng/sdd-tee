package main

import (
	"context"
	"flag"
	"os"
	"os/signal"
	"syscall"

	"github.com/volcano-sh/agentcube/pkg/picod"
	"k8s.io/klog/v2"
)

func main() {
	klog.InitFlags(nil)
	port := flag.Int("port", 8080, "HTTP listen port")
	workspace := flag.String("workspace", "", "workspace directory exposed to agents")
	flag.Parse()

	cfg := picod.Config{
		Port:      *port,
		Workspace: *workspace,
	}

	srv, err := picod.NewServer(cfg)
	if err != nil {
		klog.Fatal(err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	if err := srv.Run(ctx); err != nil && err != context.Canceled {
		klog.ErrorS(err, "picod exited")
		os.Exit(1)
	}
}
