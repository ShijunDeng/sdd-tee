package store

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
	"k8s.io/klog/v2"
)

type valkeyStore struct {
	rdb *redis.Client
}

func newValkeyStoreFromEnv() (Store, error) {
	addr := strings.TrimSpace(os.Getenv("VALKEY_ADDR"))
	if addr == "" {
		return nil, fmt.Errorf("VALKEY_ADDR is required")
	}
	password := os.Getenv("VALKEY_PASSWORD")
	disableCache := parseBoolEnv(os.Getenv("VALKEY_DISABLE_CACHE"), false)
	forceSingle := parseBoolEnv(os.Getenv("VALKEY_FORCE_SINGLE"), false)

	opts := &redis.Options{
		Addr:     addr,
		Password: password,
		DB:       0,
	}
	if disableCache {
		klog.V(4).InfoS("VALKEY_DISABLE_CACHE set; go-redis v9 uses opt-in client caching — no per-conn hook applied")
	}
	if forceSingle {
		opts.PoolSize = 1
		opts.MinIdleConns = 0
	}

	rdb := redis.NewClient(opts)
	vs := &valkeyStore{rdb: rdb}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := vs.Ping(ctx); err != nil {
		_ = rdb.Close()
		return nil, fmt.Errorf("valkey ping: %w", err)
	}
	klog.InfoS("valkey store initialized", "addr", addr, "disableCache", disableCache, "forceSingle", forceSingle)
	return vs, nil
}

func (s *valkeyStore) sessionKey(id string) string {
	return redisKeySessionPrefix + id
}

func (s *valkeyStore) Ping(ctx context.Context) error {
	return s.rdb.Ping(ctx).Err()
}

func (s *valkeyStore) GetSandboxBySessionID(ctx context.Context, sessionID string) (*Sandbox, error) {
	data, err := s.rdb.HGet(ctx, s.sessionKey(sessionID), hashFieldData).Bytes()
	if err == redis.Nil {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	var sb Sandbox
	if err := json.Unmarshal(data, &sb); err != nil {
		return nil, fmt.Errorf("unmarshal sandbox: %w", err)
	}
	return &sb, nil
}

func (s *valkeyStore) StoreSandbox(ctx context.Context, sb *Sandbox) error {
	if sb == nil || sb.SessionID == "" {
		return fmt.Errorf("sandbox session id required")
	}
	data, err := json.Marshal(sb)
	if err != nil {
		return err
	}
	pipe := s.rdb.TxPipeline()
	pipe.HSet(ctx, s.sessionKey(sb.SessionID), hashFieldData, data)
	pipe.ZAdd(ctx, redisKeyExpiryZSet, redis.Z{Score: float64(sb.ExpiresAt), Member: sb.SessionID})
	pipe.ZAdd(ctx, redisKeyLastActivityZSet, redis.Z{Score: float64(sb.LastActivity), Member: sb.SessionID})
	_, err = pipe.Exec(ctx)
	return err
}

func (s *valkeyStore) UpdateSandbox(ctx context.Context, sb *Sandbox) error {
	if sb == nil || sb.SessionID == "" {
		return fmt.Errorf("sandbox session id required")
	}
	data, err := json.Marshal(sb)
	if err != nil {
		return err
	}
	pipe := s.rdb.TxPipeline()
	pipe.HSet(ctx, s.sessionKey(sb.SessionID), hashFieldData, data)
	pipe.ZAdd(ctx, redisKeyExpiryZSet, redis.Z{Score: float64(sb.ExpiresAt), Member: sb.SessionID})
	pipe.ZAdd(ctx, redisKeyLastActivityZSet, redis.Z{Score: float64(sb.LastActivity), Member: sb.SessionID})
	_, err = pipe.Exec(ctx)
	return err
}

func (s *valkeyStore) DeleteSandboxBySessionID(ctx context.Context, sessionID string) error {
	pipe := s.rdb.TxPipeline()
	pipe.Del(ctx, s.sessionKey(sessionID))
	pipe.ZRem(ctx, redisKeyExpiryZSet, sessionID)
	pipe.ZRem(ctx, redisKeyLastActivityZSet, sessionID)
	_, err := pipe.Exec(ctx)
	return err
}

func (s *valkeyStore) ListExpiredSandboxes(ctx context.Context, beforeUnix int64, limit int) ([]*Sandbox, error) {
	return s.listByZSetRange(ctx, redisKeyExpiryZSet, "-inf", strconv.FormatInt(beforeUnix, 10), limit)
}

func (s *valkeyStore) ListInactiveSandboxes(ctx context.Context, lastActivityBeforeUnix int64, limit int) ([]*Sandbox, error) {
	return s.listByZSetRange(ctx, redisKeyLastActivityZSet, "-inf", strconv.FormatInt(lastActivityBeforeUnix, 10), limit)
}

func (s *valkeyStore) listByZSetRange(ctx context.Context, zset, min, max string, limit int) ([]*Sandbox, error) {
	if limit <= 0 {
		limit = 16
	}
	ids, err := s.rdb.ZRangeByScore(ctx, zset, &redis.ZRangeBy{
		Min: min, Max: max, Offset: 0, Count: int64(limit),
	}).Result()
	if err != nil {
		return nil, err
	}
	out := make([]*Sandbox, 0, len(ids))
	for _, id := range ids {
		sb, err := s.GetSandboxBySessionID(ctx, id)
		if err == ErrNotFound {
			continue
		}
		if err != nil {
			klog.ErrorS(err, "load sandbox during zset scan", "sessionID", id)
			continue
		}
		out = append(out, sb)
	}
	return out, nil
}

func (s *valkeyStore) UpdateSessionLastActivity(ctx context.Context, sessionID string, ts int64) error {
	sb, err := s.GetSandboxBySessionID(ctx, sessionID)
	if err != nil {
		return err
	}
	sb.LastActivity = ts
	return s.UpdateSandbox(ctx, sb)
}

func (s *valkeyStore) Close() error {
	return s.rdb.Close()
}
