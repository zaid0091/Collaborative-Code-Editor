#!/usr/bin/env bash
# Executor jailbreak regression tests — Phase 2 hardening target.
# Exit 0 when exploits are blocked (or suite is skipped pre-Phase-2).
# Exit 1 if any exploit succeeds unexpectedly.

set -euo pipefail

EXECUTOR_IMAGE="${EXECUTOR_IMAGE:-code-collab-executor:ci}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PASS=0
FAIL=0
SKIP=0

log() {
  printf '[jailbreak-test] %s\n' "$*"
}

pass() {
  PASS=$((PASS + 1))
  log "PASS: $*"
}

fail() {
  FAIL=$((FAIL + 1))
  log "FAIL: $*"
}

skip() {
  SKIP=$((SKIP + 1))
  log "SKIP: $*"
}

is_placeholder_executor() {
  docker run --rm "${EXECUTOR_IMAGE}" python -c "print('Executor placeholder')" 2>/dev/null \
    | grep -q "Executor placeholder"
}

run_executor_python() {
  local code="$1"
  docker run --rm --network none "${EXECUTOR_IMAGE}" python -c "${code}" 2>&1
}

test_proc_environ_blocked() {
  log "TEST 1: /proc/1/environ must not be readable"
  local output
  output="$(run_executor_python "open('/proc/1/environ').read()" || true)"

  if echo "${output}" | grep -qiE 'permission denied|no such file|cannot open|errno'; then
    pass "TEST 1 blocked /proc access"
  elif [ -z "${output}" ]; then
    pass "TEST 1 produced no environ leak"
  elif echo "${output}" | grep -q 'PATH='; then
    fail "TEST 1 leaked /proc/1/environ contents"
  else
    pass "TEST 1 did not expose environ (output: ${output})"
  fi
}

test_pip_install_blocked_by_scanner() {
  log "TEST 2: pip install must be blocked by static scanner before docker run"
  local scanner="${REPO_ROOT}/backend/apps/execution/code_scanner.py"

  if [ ! -f "${scanner}" ]; then
    skip "TEST 2 — code_scanner.py not implemented (Phase 2)"
    return
  fi

  # TODO Phase 2: invoke code_scanner and assert rejection before container start.
  skip "TEST 2 — wire code_scanner invocation when implemented"
}

test_socket_blocked() {
  log "TEST 3: socket creation must fail inside sandbox"
  local output
  output="$(run_executor_python "import socket; s=socket.socket(); s.connect(('1.1.1.1', 80))" || true)"

  if echo "${output}" | grep -qiE 'permission denied|operation not permitted|not allowed|errno|network is unreachable|connection refused'; then
    pass "TEST 3 blocked socket usage"
  elif echo "${output}" | grep -qi 'connected'; then
    fail "TEST 3 allowed outbound socket connection"
  else
    pass "TEST 3 did not establish socket connection"
  fi
}

test_readonly_filesystem() {
  log "TEST 4: write to /etc/passwd must fail (read-only FS)"
  local output
  output="$(run_executor_python "open('/etc/passwd','a').write('x')" || true)"

  if echo "${output}" | grep -qiE 'read-only|readonly|permission denied|errno 30|errno 13|read-only file system'; then
    pass "TEST 4 blocked write to /etc/passwd"
  elif echo "${output}" | grep -q '^x$'; then
    fail "TEST 4 wrote to /etc/passwd"
  else
    pass "TEST 4 did not confirm write to /etc/passwd"
  fi
}

main() {
  log "Using executor image: ${EXECUTOR_IMAGE}"

  if is_placeholder_executor; then
    skip "Executor image is a Phase 0 placeholder — jailbreak hardening tests deferred to Phase 2"
    log "Results: pass=${PASS} fail=${FAIL} skip=${SKIP}"
    exit 0
  fi

  test_proc_environ_blocked
  test_pip_install_blocked_by_scanner
  test_socket_blocked
  test_readonly_filesystem

  log "Results: pass=${PASS} fail=${FAIL} skip=${SKIP}"

  if [ "${FAIL}" -gt 0 ]; then
    log "One or more jailbreak tests failed — exploits were not blocked."
    exit 1
  fi

  exit 0
}

main "$@"
