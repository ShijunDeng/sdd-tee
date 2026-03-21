package store_test

import (
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/volcano-sh/agentcube/pkg/store"
)

func TestErrNotFound(t *testing.T) {
	err := store.ErrNotFound
	assert.True(t, errors.Is(err, store.ErrNotFound))
	wrapped := errors.Join(errors.New("context"), store.ErrNotFound)
	assert.True(t, errors.Is(wrapped, store.ErrNotFound))
}

func TestStorageSingleton_UnsupportedStoreType(t *testing.T) {
	store.ResetStorageForTest()
	t.Setenv("STORE_TYPE", "not-a-real-backend")
	t.Cleanup(store.ResetStorageForTest)

	_, err := store.Storage()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "unsupported STORE_TYPE")
}

func TestStorageSingleton_RedisRequiresAddr(t *testing.T) {
	store.ResetStorageForTest()
	t.Setenv("STORE_TYPE", "redis")
	t.Setenv("REDIS_ADDR", "")
	t.Cleanup(store.ResetStorageForTest)

	_, err := store.Storage()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "REDIS_ADDR")
}
