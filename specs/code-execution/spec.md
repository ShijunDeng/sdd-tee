# Code Execution (PicoD) Specification

## Purpose

PicoD is an HTTP daemon that runs commands inside a configurable workspace jail, manages workspace files, and exposes a health endpoint with JWT (RSA)–protected APIs.

## Requirements

### Requirement: Command execution API

The system SHALL accept `POST /api/execute` with a JSON body, run `command[0]` with `command[1:]` as arguments via `exec.CommandContext`, capture stdout and stderr into buffers, and respond with HTTP 200 and an `ExecuteResponse` for successful request handling (including non-zero command exit). The request SHALL NOT accept stdin from the client; the process stdin is not set from the request body.

#### Scenario: Valid execution with defaults

- **GIVEN** a valid JWT and JSON body with non-empty `command` and empty `timeout`
- **WHEN** the client calls `POST /api/execute`
- **THEN** the server uses a default timeout of 60 seconds, runs the command, and returns `stdout`, `stderr`, `exit_code`, `duration` (seconds), `start_time`, and `end_time` as JSON

#### Scenario: Custom timeout

- **GIVEN** a valid JWT and JSON body where `timeout` is a non-empty string parseable by Go `time.ParseDuration` (e.g. `"30s"`, `"500ms"`)
- **WHEN** the client calls `POST /api/execute`
- **THEN** the server uses that duration for the command context timeout

#### Scenario: Timeout exceeded

- **GIVEN** execution exceeds the context deadline
- **WHEN** the context is cancelled
- **THEN** the response `exit_code` SHALL be `124` (`TimeoutExitCode`) and stderr SHALL include a message that the command timed out with the timeout length in seconds (integer formatting)

#### Scenario: Invalid timeout

- **GIVEN** `timeout` is non-empty and not a valid duration
- **WHEN** the client calls `POST /api/execute`
- **THEN** the server responds HTTP 400 with JSON `error` describing invalid timeout format and `code` 400

#### Scenario: Empty command

- **GIVEN** JSON binds successfully but `command` has length zero
- **WHEN** the client calls `POST /api/execute`
- **THEN** the server responds HTTP 400 with `error` `"command cannot be empty"` and `code` 400

#### Scenario: Working directory inside workspace

- **GIVEN** `working_dir` is non-empty
- **WHEN** the server resolves it with the same path-safety rules as file APIs
- **THEN** `cmd.Dir` is set to the sanitized absolute path; if resolution fails, the server responds HTTP 400 with `error` prefixed by `"Invalid working directory: "`

#### Scenario: Environment augmentation

- **GIVEN** `env` is non-empty
- **WHEN** the command runs
- **THEN** `cmd.Env` is the current process environment plus additional entries `key=value` for each map entry

#### Scenario: Malformed JSON

- **GIVEN** the body is not valid JSON for `ExecuteRequest`
- **WHEN** binding fails
- **THEN** the server responds HTTP 400 with `error` from the binder and `code` 400

### Requirement: File upload API

The system SHALL accept `POST /api/files`. If `Content-Type` starts with `multipart/form-data`, the server SHALL treat the request as multipart upload; otherwise it SHALL bind JSON for `UploadFileRequest`.

#### Scenario: Multipart upload

- **GIVEN** `Content-Type` has prefix `multipart/form-data`, form field `path` is set, and form file `file` is present
- **WHEN** the client posts to `POST /api/files`
- **THEN** the server creates parent directories with mode `0755`, writes the uploaded stream to a sanitized path, applies mode from form field `mode` via `parseFileMode` (default `0644` when empty/invalid/exceeds max), and responds HTTP 200 with `FileInfo` using `path` as relative to the workspace root

#### Scenario: Multipart missing path or file

- **GIVEN** multipart request with empty `path` or missing/unreadable `file`
- **WHEN** the handler runs
- **THEN** the server responds HTTP 400 with an appropriate `error` and `code` 400

#### Scenario: JSON Base64 upload

- **GIVEN** non-multipart request with JSON `path` and `content` (Base64 standard encoding) required
- **WHEN** the client posts to `POST /api/files`
- **THEN** the server decodes content, creates directories, writes the file with `parseFileMode` on `mode`, and responds HTTP 200 with `FileInfo` (relative `path`)

#### Scenario: Invalid Base64

- **GIVEN** JSON upload with invalid Base64 in `content`
- **WHEN** decoding fails
- **THEN** the server responds HTTP 400 with `error` describing invalid base64 and `code` 400

### Requirement: File listing API

The system SHALL accept `GET /api/files?path=...`, require the `path` query parameter, read the directory at the sanitized path, and return JSON `ListFilesResponse`.

#### Scenario: Successful listing

- **GIVEN** `path` refers to an existing directory inside the workspace
- **WHEN** the client calls `GET /api/files?path=<dir>`
- **THEN** the server responds HTTP 200 with `files` as an array of `FileEntry` objects (`name`, `size`, `modified`, `mode`, `is_dir`), skipping entries where `entry.Info()` fails

#### Scenario: Missing query parameter

- **GIVEN** the `path` query parameter is absent or empty
- **WHEN** the client calls `GET /api/files`
- **THEN** the server responds HTTP 400 with `error` `"Missing 'path' query parameter"` and `code` 400

#### Scenario: Directory not found

- **GIVEN** sanitized path does not exist
- **WHEN** `os.ReadDir` fails with not exist
- **THEN** the server responds HTTP 404 with `error` `"Directory not found"` and `code` 404

### Requirement: File download API

The system SHALL serve file contents at `GET /api/files/*path` for a sanitized file path, set download-oriented headers, and stream the file with `c.File`.

#### Scenario: Successful download

- **GIVEN** the wildcard path resolves to a regular file inside the workspace
- **WHEN** the client calls `GET /api/files/<path>`
- **THEN** the server sets `Content-Description` to `File Transfer`, `Content-Transfer-Encoding` to `binary`, `Content-Disposition` to `attachment; filename="<basename>"`, `Content-Type` from `mime.TypeByExtension` or `application/octet-stream`, and returns the file body

#### Scenario: Path escapes workspace

- **GIVEN** the requested path fails `sanitizePath`
- **WHEN** the client calls the download endpoint
- **THEN** the server responds HTTP 400 with `error` describing access denied / workspace jail

#### Scenario: Not a file

- **GIVEN** the path exists but is a directory
- **WHEN** the client downloads
- **THEN** the server responds HTTP 400 with `error` `"Path is a directory, not a file"` and `code` 400

#### Scenario: File missing

- **GIVEN** the path does not exist
- **WHEN** stat fails with not exist
- **THEN** the server responds HTTP 404 with `error` `"File not found"` and `code` 404

### Requirement: Health endpoint

The system SHALL expose `GET /health` without JWT middleware and respond HTTP 200 with JSON including `status`, `service`, `version`, and `uptime`.

#### Scenario: Unauthenticated health

- **GIVEN** no `Authorization` header
- **WHEN** the client calls `GET /health`
- **THEN** the server responds HTTP 200 with `status` `"ok"`, `service` `"PicoD"`, `version` `"0.0.1"`, and `uptime` as a string from `time.Since(server start)`

### Requirement: JWT authentication for API routes

The system SHALL register `/api` routes under a Gin group that uses `AuthManager.AuthMiddleware`. The middleware SHALL require header `Authorization: Bearer <token>`, parse the JWT with an RSA public key, and reject non-RSA signing methods. Valid tokens SHALL allow the request to proceed; after validation the request body SHALL be wrapped with `http.MaxBytesReader` limiting size to `MaxBodySize`.

#### Scenario: Missing or malformed Authorization

- **GIVEN** missing header, or a header that is not exactly two space-separated parts with first part `Bearer`
- **WHEN** an `/api` route is hit
- **THEN** the server responds HTTP 401 with JSON including `error`, `code` 401, and `detail` explaining the failure

#### Scenario: Invalid or expired JWT

- **GIVEN** a Bearer token that fails verification (signature, expiry, etc.) with options `WithExpirationRequired`, `WithIssuedAt`, and `WithLeeway(1 minute)`
- **WHEN** the middleware runs
- **THEN** the server responds HTTP 401 with `error` `"Invalid token"`, `code` 401, and `detail` containing the verification error

#### Scenario: Public key required at startup

- **GIVEN** `PICOD_AUTH_PUBLIC_KEY` is unset or does not decode to an RSA public key in PEM form
- **WHEN** `NewServer` initializes
- **THEN** the process SHALL log a fatal error and not continue serving (there is no unauthenticated API mode when the key is missing)

### Requirement: Server configuration

The system SHALL read CLI flags `-port` and `-workspace`, build `picod.Config`, and listen on `":<port>"`. If `workspace` is empty, the workspace root SHALL be the current working directory (fatal if `os.Getwd` fails). The HTTP server SHALL use `ReadHeaderTimeout` of 10 seconds.

#### Scenario: Defaults from CLI

- **GIVEN** `-port` and `-workspace` use program defaults
- **WHEN** the binary starts
- **THEN** `port` defaults to `8080`, `workspace` defaults to empty (resolved to CWD), and Gin runs in `ReleaseMode` with `Logger` and `Recovery` middleware globally
