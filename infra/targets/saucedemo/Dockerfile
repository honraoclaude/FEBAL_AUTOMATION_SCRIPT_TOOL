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

# =====================================================================================
# QUAL-02 benign-vs-breaking mutation catalog (Phase 8 plan 08-04). Extends the SEED_BUG
# build-arg pattern above into a catalog that the keyless mutation harness
# (apps/api/tests/functional/test_healing_mutations.py) runs the heal-wired planted spec
# against. EVERY arg below defaults to 0, so the DEFAULT build and the existing
# saucedemo / saucedemo-bug builds stay BYTE-IDENTICAL (T-08-17 / T-06-21 — no drift).
#
# All mutations target ONE deterministic element — the LOGIN BUTTON, rendered by the
# bundle component as <input type="submit" class="submit-button btn_action"
# data-test="login-button" id="login-button" name="login-button" value="Login">. The
# button component renders via the unique bundle expr
#   (0,Ue.jsx)("input",ke(ke({type:"submit",className:"submit-button".concat(o),value:r}, ...
# and the login screen calls it via the unique usage expr
#   (0,Ue.jsx)(xr,{customClass:"btn_action",testId:"login-button",value:"Login"})
# Each `sed` rewrite below targets one of those VERIFIED-UNIQUE strings (1 occurrence
# in the hashed main.*.js bundle), gated by its own build-arg, mirroring SEED_BUG exactly.
#
# CATALOG -> EXPECTED OUTCOME (sourced from 08-RESEARCH Pattern 6):
#   BENIGN (the element survives + stays identifiable on a lower tier -> MUST HEAL):
#     BENIGN_RENAME_DATATEST  data-test/id/name "login-button" -> "login-button-v2"
#                             (found by visible text "Login"; new data-test re-validates count 1)
#     BENIGN_CHANGE_TEXT      value "Login" -> "Sign In"
#                             (data-test unchanged; found by tag input; re-validates count 1)
#     BENIGN_CHANGE_TAG       <input type=submit value="Login"> -> <button type=submit>Login</button>
#                             (role/a11y-name + visible text "Login" survive; re-validates count 1)
#     BENIGN_WRAP             wrap the button in an extra <div> (ancestry/xpath shift only;
#                             attrs/role/text/bbox unchanged -> re-validates count 1)
#   BREAKING (the structural false-heal guard MUST hold -> NEVER auto_heal):
#     BREAK_REMOVE            delete the login button entirely
#                             (no candidate clears the band; the best leftover input is a
#                              low-confidence unrelated element -> fail_as_defect, never auto_heal)
#     BREAK_DUPLICATE         render the login button TWICE (ambiguous)
#                             (the heal selector re-validates to live_match_count > 1 ->
#                              the HARD uniqueness gate (count != 1) forbids heal -> fail_as_defect)
#     SEED_BUG (above)        break the post-login flow (.inventory_list -> _BROKEN)
#                             (an ASSERTION target, not a locator -> product_failure, never a heal)
#
# This is COMPOSE INFRA (build-args), NOT a package (T-08-SC: zero new packages, no image-diff lib).
# busybox `sed` (BRE): literal `.` `[` are escaped (`\.` `\[`); `(` `)` `{` `}` are literal in BRE.
# `_BUNDLE` is the hashed bundle glob (filename carries a content hash, never sed by exact name).
# =====================================================================================
ARG BENIGN_RENAME_DATATEST=0
ARG BENIGN_CHANGE_TEXT=0
ARG BENIGN_CHANGE_TAG=0
ARG BENIGN_WRAP=0
ARG BREAK_REMOVE=0
ARG BREAK_DUPLICATE=0
RUN _BUNDLE=$(ls /usr/share/nginx/html/static/js/main.*.js); \
    if [ "$BENIGN_RENAME_DATATEST" = "1" ]; then \
      sed -i 's/testId:"login-button"/testId:"login-button-v2"/' "$_BUNDLE"; \
    fi; \
    if [ "$BENIGN_CHANGE_TEXT" = "1" ]; then \
      sed -i 's/testId:"login-button",value:"Login"/testId:"login-button",value:"Sign In"/' "$_BUNDLE"; \
    fi; \
    if [ "$BENIGN_CHANGE_TAG" = "1" ]; then \
      sed -i 's/jsx)("input",ke(ke({type:"submit",className:"submit-button"\.concat(o),value:r}/jsx)("button",ke(ke({type:"submit",className:"submit-button".concat(o),children:r}/' "$_BUNDLE"; \
    fi; \
    if [ "$BENIGN_WRAP" = "1" ]; then \
      sed -i 's/(0,Ue\.jsx)(xr,{customClass:"btn_action",testId:"login-button",value:"Login"})/(0,Ue.jsx)("div",{className:"heal-wrap",children:(0,Ue.jsx)(xr,{customClass:"btn_action",testId:"login-button",value:"Login"})})/' "$_BUNDLE"; \
    fi; \
    if [ "$BREAK_REMOVE" = "1" ]; then \
      sed -i 's/(0,Ue\.jsx)(xr,{customClass:"btn_action",testId:"login-button",value:"Login"})/null/' "$_BUNDLE"; \
    fi; \
    if [ "$BREAK_DUPLICATE" = "1" ]; then \
      sed -i 's/(0,Ue\.jsx)(xr,{customClass:"btn_action",testId:"login-button",value:"Login"})/(0,Ue.jsxs)("div",{children:[(0,Ue.jsx)(xr,{customClass:"btn_action",testId:"login-button",value:"Login"}),(0,Ue.jsx)(xr,{customClass:"btn_action",testId:"login-button",value:"Login"})]})/' "$_BUNDLE"; \
    fi

EXPOSE 80
