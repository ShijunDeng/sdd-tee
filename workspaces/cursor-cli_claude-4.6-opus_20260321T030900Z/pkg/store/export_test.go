package store

import "sync"

// ResetStorageForTest clears the Storage() singleton between tests.
func ResetStorageForTest() {
	storageOnce = sync.Once{}
	storageInst = nil
	storageErr = nil
}
