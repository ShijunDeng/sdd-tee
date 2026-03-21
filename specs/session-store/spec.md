# Session Store Specification

## Purpose
Persist sandbox metadata keyed by session id, index sessions by expiry and last activity for garbage collection, and support Redis or Valkey backends selected by configuration.

## Requirements

### Requirement: Store interface contract
The system SHALL provide a `Store` interface implemented by Redis and Valkey providers with methods: `Ping`, `GetSandboxBySessionID`, `StoreSandbox`, `UpdateSandbox`, `DeleteSandboxBySessionID`, `ListExpiredSandboxes`, `ListInactiveSandboxes`, `UpdateSessionLastActivity`, and `Close`.

#### Scenario: Ping verifies connectivity
- **GIVEN** a healthy Redis/Valkey server
- **WHEN** `Ping(ctx)` is called
- **THEN** the implementation issues PING and requires string response `PONG`

### Requirement: Not found semantics
The system SHALL return package error `ErrNotFound` (message `store: not found`) when a session key is absent on read or when last-activity update targets a missing session.

#### Scenario: Get missing session
- **GIVEN** no key `session:{id}` in backend
- **WHEN** `GetSandboxBySessionID` runs
- **THEN** error is `ErrNotFound` (Redis: `Nil`; Valkey: `IsValkeyNil`)

### Requirement: Session key naming
The system SHALL use string prefix `session:` concatenated with the session id as the primary key for JSON document storage.

#### Scenario: Key construction
- **GIVEN** session id `abc`
- **WHEN** the store writes sandbox data
- **THEN** the string key is `session:abc`

### Requirement: Expiry index
The system SHALL maintain sorted set key `session:expiry` with member = session id and score = `ExpiresAt` Unix seconds. `StoreSandbox` SHALL add the member with the sandbox expiry score. `DeleteSandboxBySessionID` SHALL remove the member.

#### Scenario: List expired uses ZRANGEBYSCORE
- **GIVEN** `ListExpiredSandboxes(ctx, before, limit)` with limit > 0
- **WHEN** the implementation queries the index
- **THEN** it selects members with scores from negative infinity through `before.Unix()`, limited to `limit` entries

### Requirement: Last-activity index
The system SHALL maintain sorted set key `session:last_activity` with member = session id and score = last activity Unix seconds. `StoreSandbox` SHALL ZADD with score `time.Now().Unix()` on initial store. `UpdateSessionLastActivity` SHALL ZADD with the provided timestamp (or now if zero). `DeleteSandboxBySessionID` SHALL ZREM the member.

#### Scenario: List inactive uses activity index
- **GIVEN** `ListInactiveSandboxes(ctx, before, limit)`
- **WHEN** executed
- **THEN** members with last-activity score ≤ `before.Unix()` are returned up to `limit`

### Requirement: StoreSandbox atomicity and validation
The system SHALL reject nil sandbox or zero `ExpiresAt`. The system SHALL execute SETNX on session key, ZADD expiry, and ZADD last_activity in one pipeline/multi block. The system SHALL fail if any command in the batch errors.

#### Scenario: Nil sandbox rejected
- **GIVEN** `StoreSandbox(ctx, nil)`
- **WHEN** called
- **THEN** error indicates sandbox is nil

### Requirement: UpdateSandbox semantics
The system SHALL update only the session JSON value using SET with XX (key must exist). The system SHALL NOT modify expiry or last-activity ZSET entries in this operation.

#### Scenario: Missing key on update
- **GIVEN** session key does not exist
- **WHEN** `UpdateSandbox` runs
- **THEN** Redis: SETXX returns false → error `key not exists`; Valkey: response not OK → same error class

### Requirement: DeleteSandboxBySessionID cleanup
The system SHALL delete session key and remove session id from both sorted sets in one pipeline/multi.

#### Scenario: Full removal
- **GIVEN** an existing session
- **WHEN** delete succeeds
- **THEN** GET session key returns not found and ZSETs no longer contain the member

### Requirement: List loaders tolerate missing keys
When listing by ZSET returns session ids, the system SHALL load JSON per id; SHALL skip entries where the string key is missing (Redis pipeline GET nil, Valkey MGET empty string) without failing the whole batch.

#### Scenario: Orphan ZSET member
- **GIVEN** a session id in ZSET without a hash/string value
- **WHEN** `loadSandboxesBySessionIDs` runs
- **THEN** that id is omitted from the returned slice

### Requirement: UpdateSessionLastActivity preconditions
The system SHALL reject empty session id. If `at` is zero time, the system SHALL use `time.Now()`. The system SHALL verify the session key exists before ZADD; if absent, SHALL return `ErrNotFound`.

#### Scenario: Activity bump for unknown session
- **GIVEN** no `session:{id}` key
- **WHEN** `UpdateSessionLastActivity` is called
- **THEN** return `ErrNotFound`

### Requirement: Provider selection via STORE_TYPE
The system SHALL read `STORE_TYPE` case-insensitively; if unset, SHALL default to `redis`. Supported values SHALL be `redis` and `valkey`; any other value SHALL fail initialization.

#### Scenario: Default redis
- **GIVEN** `STORE_TYPE` is not set
- **WHEN** `Storage()` first initializes
- **THEN** Redis implementation is constructed

### Requirement: Redis environment and password policy
The system SHALL require `REDIS_ADDR`. The system SHALL require non-empty `REDIS_PASSWORD` unless `REDIS_PASSWORD_REQUIRED` is set case-insensitively to `false`.

#### Scenario: Password required by default
- **GIVEN** `REDIS_ADDR` set and `REDIS_PASSWORD` empty and `REDIS_PASSWORD_REQUIRED` unset
- **WHEN** Redis store initializes
- **THEN** initialization fails with error stating password required

### Requirement: Valkey environment and options
The system SHALL require `VALKEY_ADDR` (comma-separated addresses split for `InitAddress`). The system SHALL require non-empty `VALKEY_PASSWORD` unless `VALKEY_PASSWORD_REQUIRED=false`. The system SHALL set `DisableCache` true when `VALKEY_DISABLE_CACHE` parses as true; SHALL set `ForceSingleClient` true when `VALKEY_FORCE_SINGLE` parses as true.

#### Scenario: Optional client flags
- **GIVEN** `VALKEY_DISABLE_CACHE=true`
- **WHEN** Valkey client options are built
- **THEN** `DisableCache` is true on `ClientOption`

### Requirement: Singleton access
The system SHALL expose `func Storage() Store` using `sync.Once`; failed init SHALL log fatal via klog.

#### Scenario: Single initialization
- **GIVEN** multiple goroutines call `Storage()`
- **WHEN** they run concurrently
- **THEN** `initStore` executes exactly once
