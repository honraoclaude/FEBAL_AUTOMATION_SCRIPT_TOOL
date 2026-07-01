#!/usr/bin/env bash
# Keyless K8s-manifest validation for the Autonomous QA Engineer Platform (INFRA-02).
#
# Renders every Kustomize group offline and schema-validates it — NO cluster, NO apply,
# NO credentials (T-11-12: catch malformed manifests before any apply, never
# apply-to-discover-errors). This is the automated half of INFRA-02; the LIVE deploy +
# explore->execute->dashboard e2e is Manual-Only (see README.md).
#
# Groups validated:
#   1. infra/k8s/base                     — the 7 core workloads (the SC1 e2e set)
#   2. infra/k8s/overlays/elasticsearch    — the optional ES search tier
#   3. infra/k8s/monitoring                — Prometheus + Grafana + exporters
#
# TOOLS: needs `kustomize` (or `kubectl kustomize`) to render + `kubeconform` to schema-check.
# If neither renderer is present it SKIP-CLEANS (exit 0) with a clear message so CI that
# installs the tools runs the real gate, while this Windows dev box (which lacks the
# standalone CLIs) does not fail the workflow. kubeconform being absent downgrades to a
# render-only check (still catches Kustomize/YAML errors), also skip-clean-noted.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

# Space-separated (the paths have no spaces). NOTE the var name is K8S_GROUPS, NOT
# `GROUPS` — `GROUPS` is a bash built-in array (the caller's group IDs) and assigning
# to it is silently ignored, so the loop would iterate over the GID. A plain word-split
# list iterates correctly everywhere.
K8S_GROUPS="infra/k8s/base infra/k8s/overlays/elasticsearch infra/k8s/monitoring"

# --- Pick a renderer: prefer standalone kustomize, fall back to `kubectl kustomize`. ---
RENDER=""
if command -v kustomize >/dev/null 2>&1; then
  RENDER="kustomize build"
elif command -v kubectl >/dev/null 2>&1 && kubectl kustomize --help >/dev/null 2>&1; then
  RENDER="kubectl kustomize"
fi

if [ -z "$RENDER" ]; then
  echo "SKIP: neither 'kustomize' nor 'kubectl kustomize' found on PATH."
  echo "      Install kustomize (https://kustomize.io) or kubectl to run this validation."
  echo "      (This dev box may lack them; CI installs them and runs the real gate.)"
  exit 0
fi
echo "renderer: $RENDER"

# --- Pick a schema validator (optional): kubeconform. ---
KUBECONFORM=""
if command -v kubeconform >/dev/null 2>&1; then
  KUBECONFORM="kubeconform -strict -summary"
  echo "validator: $KUBECONFORM"
else
  echo "NOTE: 'kubeconform' not found — running RENDER-ONLY (Kustomize/YAML errors still caught)."
  echo "      Install kubeconform (https://github.com/yannh/kubeconform) for -strict schema checks."
fi

# --- Drift guard: the K8s dashboard mirrors must equal the Plan-01 canonical source. ---
CANON="infra/monitoring/grafana/provisioning/dashboards"
MIRROR="infra/k8s/monitoring/dashboards"
for dash in platform-health.json domain-metrics.json; do
  if [ -f "$CANON/$dash" ] && [ -f "$MIRROR/$dash" ]; then
    if ! diff -q "$CANON/$dash" "$MIRROR/$dash" >/dev/null 2>&1; then
      echo "FAIL: $MIRROR/$dash has drifted from the canonical $CANON/$dash."
      echo "      Re-copy the Plan-01 dashboard into the K8s monitoring tree."
      exit 1
    fi
  fi
done
echo "dashboard mirrors: in sync with the Plan-01 source"

# --- Render (+ optionally schema-validate) every group. ---
FAIL=0
# shellcheck disable=SC2086  # intentional word-split of the space-separated list
for grp in $K8S_GROUPS; do
  echo "=== $grp ==="
  if [ -n "$KUBECONFORM" ]; then
    if ! $RENDER "$grp" | $KUBECONFORM; then
      echo "FAIL: $grp did not render+validate."
      FAIL=1
    fi
  else
    OUT="$($RENDER "$grp" 2>&1)"
    RC=$?
    if [ $RC -ne 0 ]; then
      echo "$OUT"
      echo "FAIL: $grp did not render."
      FAIL=1
    else
      COUNT="$(printf '%s\n' "$OUT" | grep -c '^kind:')"
      echo "OK: rendered ($COUNT objects)"
    fi
  fi
done

if [ "$FAIL" -ne 0 ]; then
  echo "VALIDATION FAILED"
  exit 1
fi
echo "VALIDATION PASSED"
exit 0
