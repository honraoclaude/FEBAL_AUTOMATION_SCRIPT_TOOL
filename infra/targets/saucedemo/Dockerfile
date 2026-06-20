# Self-hosted SauceDemo (saucelabs/sample-app-web) — QUAL-04 / D-10.
#
# We build our own multi-stage image because the upstream repo's Dockerfile is
# unusable (node:14 base, no CMD/EXPOSE, bundles Sauce Connect cruft) — RESEARCH
# Pattern 5 / Alternatives Considered.
#
# Pinned to an exact upstream commit SHA (NOT "master") for reproducibility —
# threat T-01-25 (upstream drift/compromise): the build is fixed to a known
# revision and the final image only serves static files via nginx (no
# server-side code runs). Resolve a fresh SHA with:
#   git ls-remote https://github.com/saucelabs/sample-app-web.git HEAD
#
# build stage uses node:16-bullseye: the app's webpack/babel toolchain predates
# OpenSSL 3, so Node 17+ commonly fails with ERR_OSSL_EVP_UNSUPPORTED on the old
# webpack build (RESEARCH assumption A1 / Pitfall 9). node:16 ships OpenSSL 1.1.1
# (no md4 removal), so the `--openssl-legacy-provider` flag is neither needed nor
# accepted here — setting it globally via NODE_OPTIONS makes node abort
# ("not allowed in NODE_OPTIONS") even for `npm ci`. The pinned node:16 base IS
# the A1 mitigation; the legacy-provider flag is only relevant if this base is
# ever bumped to Node 17+.

FROM node:16-bullseye AS build
ARG SAUCEDEMO_SHA=89b11dca1b11b5cae36966e34b8c902212670c9a
RUN git clone https://github.com/saucelabs/sample-app-web.git /src \
 && cd /src && git checkout ${SAUCEDEMO_SHA}
WORKDIR /src
RUN npm ci && npm run build

FROM nginx:alpine
COPY --from=build /src/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Seeded-bug toggle (GEN-05 / D-08, Phase 6 plan 06-04). SEED_BUG defaults to 0 so the
# DEFAULT build is BYTE-IDENTICAL to the standard target (T-06-21 — no drift). When
# SEED_BUG=1 (only the profile-gated saucedemo-bug compose service sets it), one
# DETERMINISTIC DOM mutation is applied to the served bundle: the post-login success
# element class `.inventory_list` is renamed to `.inventory_list_BROKEN` across every
# served file. The post-login success assertion (`.inventory_list` visible) then FAILS
# vs this build — proving real-breakage detection. This is COMPOSE INFRA (a build-arg),
# NOT a package (T-06-SC: zero new packages). Paired with the planted spec in 06-04 Task 2,
# which asserts `.inventory_list` so it passes vs the default build and fails vs this one.
ARG SEED_BUG=0
RUN if [ "$SEED_BUG" = "1" ]; then \
      grep -rl 'inventory_list' /usr/share/nginx/html \
        | xargs -r sed -i 's/inventory_list/inventory_list_BROKEN/g'; \
    fi

EXPOSE 80
