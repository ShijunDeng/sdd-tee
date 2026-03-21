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

const (
	redisKeySessionPrefix    = "session:"
	redisKeyExpiryZSet       = "session:expiry"
	redisKeyLastActivityZSet = "session:last_activity"
	hashFieldData            = "data"
)

type redisStore struct {
	rdb *redis.Client
}

func newRedisStoreFromEnv() (Store, error) {
	addr := strings.TrimSpace(os.Getenv("REDIS_ADDR"))
	if addr == "" {
		return nil, fmt.Errorf("REDIS_ADDR is required")
	}
	password := os.Getenv("REDIS_PASSWORD")
	required := parseBoolEnv(os.Getenv("REDIS_PASSWORD_REQUIRED"), true)
	if required && password == "" {
		return nil, fmt.Errorf("REDIS_PASSWORD is required when REDIS_PASSWORD_REQUIRED is true")
	}

	rdb := redis.NewClient(&redis.Options{
		Addr:     addr,
		Password: password,
		DB:       0,
	})
	rs := &redisStore{rdb: rdb}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rs.Ping(ctx); err != nil {
		_ = rdb.Close()
		return nil, fmt.Errorf("redis ping: %w", err)
	}
	klog.InfoS("redis store initialized", "addr", addr)
	return rs, nil
}

func (s *redisStore) sessionKey(id string) string {
	return redisKeySessionPrefix + id
}

func (s *redisStore) Ping(ctx context.Context) error {
	return s.rdb.Ping(ctx).Err()
}

func (s *redisStore) GetSandboxBySessionID(ctx context.Context, sessionID string) (*Sandbox, error) {
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

func (s *redisStore) StoreSandbox(ctx context.Context, sb *Sandbox) error {
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

func (s *redisStore) UpdateSandbox(ctx context.Context, sb *Sandbox) error {
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

func (s *redisStore) DeleteSandboxBySessionID(ctx context.Context, sessionID string) error {
	pipe := s.rdb.TxPipeline()
	pipe.Del(ctx, s.sessionKey(sessionID))
	pipe.ZRem(ctx, redisKeyExpiryZSet, sessionID)
	pipe.ZRem(ctx, redisKeyLastActivityZSet, sessionID)
	_, err := pipe.Exec(ctx)
	return err
}

func (s *redisStore) ListExpiredSandboxes(ctx context.Context, beforeUnix int64, limit int) ([]*Sandbox, error) {
	return s.listByZSetRange(ctx, redisKeyExpiryZSet, "-inf", strconv.FormatInt(beforeUnix, 10), limit)
}

func (s *redisStore) ListInactiveSandboxes(ctx context.Context, lastActivityBeforeUnix int64, limit int) ([]*Sandbox, error) {
	return s.listByZSetRange(ctx, redisKeyLastActivityZSet, "-inf", strconv.FormatInt(lastActivityBeforeUnix, 10), limit)
}

func (s *redisStore) listByZSetRange(ctx context.Context, zset, min, max string, limit int) ([]*Sandbox, error) {
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

func (s *redisStore) UpdateSessionLastActivity(ctx context.Context, sessionID string, ts int64) error {
	sb, err := s.GetSandboxBySessionID(ctx, sessionID)
	if err != nil {
		return err
	}
	sb.LastActivity = ts
	return s.UpdateSandbox(ctx, sb)
}

func (s *redisStore) Close() error {
	return s.rdb.Close()
}

func parseBoolEnv(s string, def bool) bool {
	if strings.TrimSpace(s) == "" {
		return def
	}
	v, err := strconv.ParseBool(strings.ToLower(strings.TrimSpace(s)))
	if err != nil {
		return def
	}
	return v
}
