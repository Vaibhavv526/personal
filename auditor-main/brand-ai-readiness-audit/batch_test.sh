#!/usr/bin/env bash
# Batch-tests the marketplace CLI against a diverse set of sites, including
# edge cases the manual testing so far hasn't covered: DNS failure, 404,
# 500, redirects, non-HTML content, and a missing URL scheme.

set -u
OUTDIR="batch_reports"
RUNNER="skills/audit-orchestrator/scripts/run_audit.py"
TIMEOUT_SECS=300   # 5 min budget + small buffer before we kill it

# name|url
TESTS=(
  "python_org|https://www.python.org/"
  "hackernews|https://news.ycombinator.com/"
  "wikipedia_ai|https://en.wikipedia.org/wiki/Artificial_intelligence"
  "http_404|https://httpstat.us/404"
  "http_500|https://httpstat.us/500"
  "http_redirect|https://httpstat.us/301"
  "dns_failure|https://this-domain-should-not-exist-abc123xyz.com/"
  "no_scheme|example.com"
  "pdf_content|https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
)

PASS=0
FAIL=0
declare -a FAILED_NAMES

for entry in "${TESTS[@]}"; do
  name="${entry%%|*}"
  url="${entry#*|}"
  json_out="${OUTDIR}/${name}.json"
  log_out="${OUTDIR}/${name}.log"

  echo "=== ${name} (${url}) ==="
  start=$(date +%s)
  timeout "${TIMEOUT_SECS}" python3 -u "${RUNNER}" "${url}" > "${json_out}" 2> "${log_out}"
  exit_code=$?
  end=$(date +%s)
  elapsed=$((end - start))

  if [ "${exit_code}" -eq 124 ]; then
    echo "  RESULT: TIMEOUT after ${TIMEOUT_SECS}s"
    FAIL=$((FAIL + 1)); FAILED_NAMES+=("${name} (timeout)")
    continue
  fi

  if [ "${exit_code}" -ne 0 ]; then
    echo "  RESULT: CRASHED (exit ${exit_code}) after ${elapsed}s — see ${log_out}"
    tail -n 5 "${log_out}" | sed 's/^/    /'
    FAIL=$((FAIL + 1)); FAILED_NAMES+=("${name} (crash exit ${exit_code})")
    continue
  fi

  # Crashed processes sometimes still exit 0 but print a traceback to stdout
  if grep -q "Traceback (most recent call last)" "${json_out}"; then
    echo "  RESULT: TRACEBACK IN OUTPUT (exit 0 but not real JSON) after ${elapsed}s"
    FAIL=$((FAIL + 1)); FAILED_NAMES+=("${name} (traceback)")
    continue
  fi

  validation=$(python3 validate_report.py "${json_out}" 2>&1)
  if echo "${validation}" | grep -q "^PASS"; then
    echo "  RESULT: OK (${elapsed}s) — schema valid"
    PASS=$((PASS + 1))
  else
    echo "  RESULT: SCHEMA INVALID (${elapsed}s)"
    echo "${validation}" | sed 's/^/    /'
    FAIL=$((FAIL + 1)); FAILED_NAMES+=("${name} (schema)")
  fi
  echo ""
done

echo "================================================"
echo "TOTAL: ${PASS} passed, ${FAIL} failed (of ${#TESTS[@]})"
if [ "${FAIL}" -gt 0 ]; then
  echo "Failed cases:"
  for n in "${FAILED_NAMES[@]}"; do echo "  - ${n}"; done
fi
