"""Wave-0 fixtures for Slice 1: a SauceDemo fixture KG + four-case then_refs + a fake driver.

This module is PURE DATA + a fake Neo4j driver factory — it runs NO gates and imports NO
neo4j. It is importable with no neo4j and no provider keys, so the assertion-gate unit tests
(Task 2) and the generate_scenarios unit tests (Task 3) can resolve refs against a fake driver
whose existence answers are scripted per element/page/edge.

The fake driver mirrors the kg/reader `driver=` injection: it exposes `.session()` as an async
context manager whose `.execute_read(tx)` runs the passed transaction function against a fake
`tx` that returns scripted records. We don't parse the Cypher — we answer existence based on the
PARAMS the gate passes ($entity / $element_key / $fp / $url) against the fixture sets below, so
the gate's read shape (execute_read + parameterized) is exercised exactly while the answer is
deterministic. Every query the gate runs is recorded on `driver.calls` so a test can assert that
NO Cypher was built for an unknown kind / disallowed edge_type (injection-safety).
"""

from __future__ import annotations

# --- Fixture KG (SauceDemo subset) -------------------------------------------------------
# An inventory page, one element on it, and a Cart BusinessEntity reachable by an Updates edge.
INVENTORY_FP = "fp-inventory"
INVENTORY_URL = "https://www.saucedemo.com/inventory.html"
ADD_TO_CART_KEY = "fp-inventory#button:Add to cart"
CART_ENTITY = "Cart"

# The set of existing nodes/edges the fake driver resolves as exists=true.
EXISTING_ELEMENT_KEYS = {ADD_TO_CART_KEY}
EXISTING_PAGE_FPS = {INVENTORY_FP}
EXISTING_PAGE_URLS = {INVENTORY_URL}
# (edge_type, entity) pairs that resolve true. Only Updates→Cart exists in the fixture.
EXISTING_EDGES = {("Updates", CART_ENTITY)}


# A page_detail-shaped structure (mirrors kg/reader.page_detail output) for Examples derivation.
INVENTORY_PAGE_DETAIL = {
    "fingerprint": INVENTORY_FP,
    "url": INVENTORY_URL,
    "title": "Products",
    "elements": [
        {"key": ADD_TO_CART_KEY, "role": "button", "label": "Add to cart"},
    ],
    "forms": [{"key": "fp-inventory#form:cart"}],
    "navigates_to": [],
}

# A login page_detail with a real form carrying fields → Examples columns.
LOGIN_FP = "fp-login"
LOGIN_URL = "https://www.saucedemo.com/"
LOGIN_PAGE_DETAIL = {
    "fingerprint": LOGIN_FP,
    "url": LOGIN_URL,
    "title": "Swag Labs",
    "elements": [
        {"key": "fp-login#input:username", "role": "textbox", "label": "username"},
        {"key": "fp-login#input:password", "role": "textbox", "label": "password"},
        {"key": "fp-login#button:login", "role": "button", "label": "Login"},
    ],
    "forms": [
        {
            "key": "fp-login#form:login",
            "fields": [
                {"name": "username", "label": "Username"},
                {"name": "password", "label": "Password"},
            ],
        }
    ],
    "navigates_to": [{"to": INVENTORY_FP, "url": INVENTORY_URL, "via": "login"}],
}


# --- Four-case then_refs sets ------------------------------------------------------------
# (a) Every Then resolvable: an Updates→Cart edge, a present element, a present page.
THEN_REFS_ALL_RESOLVABLE = [
    {
        "then_text": "the cart is updated",
        "kind": "edge",
        "ref": {"edge_type": "Updates", "entity": CART_ENTITY},
    },
    {
        "then_text": "the add to cart button exists",
        "kind": "element",
        "ref": {"element_key": ADD_TO_CART_KEY},
    },
    {
        "then_text": "the inventory page is shown",
        "kind": "page",
        "ref": {"page_fingerprint": INVENTORY_FP},
    },
]

# (b) A Then with NO ref at all → vacuous.
THEN_REFS_NO_REF = [
    {"then_text": "something good happens", "kind": "page", "ref": {}},
]

# (c) A Then whose ref does NOT resolve (page that doesn't exist) → vacuous.
THEN_REFS_UNRESOLVABLE = [
    {
        "then_text": "the ghost page is shown",
        "kind": "page",
        "ref": {"page_fingerprint": "fp-does-not-exist"},
    },
]

# (d) A Then with an UNKNOWN kind → vacuous, and NO Cypher should run for it.
THEN_REFS_UNKNOWN_KIND = [
    {"then_text": "the vibe is correct", "kind": "feeling", "ref": {"x": "y"}},
]

# (e) An edge ref whose edge_type is OUTSIDE {Creates,Updates,Deletes} → vacuous + NO Cypher
#     (injection-safety: the LLM edge_type string is never interpolated).
THEN_REFS_DISALLOWED_EDGE = [
    {
        "then_text": "the cart is owned",
        "kind": "edge",
        "ref": {"edge_type": "Owns", "entity": CART_ENTITY},
    },
]

# (f) A scenario with ZERO Thens → vacuous (nothing asserted).
THEN_REFS_EMPTY: list = []


# --- Fake driver -------------------------------------------------------------------------
class _FakeResult:
    """Async-iterable result yielding the scripted records (mirrors a neo4j result)."""

    def __init__(self, records: list[dict]):
        self._records = records

    def __aiter__(self):
        async def _gen():
            for rec in self._records:
                yield rec

        return _gen()


class _FakeTx:
    """A fake managed-read transaction: .run(cypher, **params) returns scripted records.

    Existence is computed from the PARAMS the gate passes (not by parsing Cypher), against the
    fixture EXISTING_* sets above. Each call is appended to the parent driver's `.calls` log so a
    test can assert no query ran for an unknown kind / disallowed edge_type.
    """

    def __init__(self, driver: "FakeDriver"):
        self._driver = driver

    async def run(self, cypher: str, **params):
        self._driver.calls.append({"cypher": cypher, "params": dict(params)})
        exists = self._driver._resolve(cypher, params)
        return _FakeResult([{"exists": exists}])


class _FakeSession:
    def __init__(self, driver: "FakeDriver"):
        self._driver = driver

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute_read(self, tx_func):
        return await tx_func(_FakeTx(self._driver))


class FakeDriver:
    """A minimal stand-in for a neo4j AsyncDriver usable as the gate's `driver=` kwarg.

    Resolves existence deterministically from the fixture sets, keyed on the params the gate
    passes ($entity + the edge_type baked into the cypher, $element_key, $fp/$url).
    """

    def __init__(self):
        self.calls: list[dict] = []

    def session(self):
        return _FakeSession(self)

    def _resolve(self, cypher: str, params: dict) -> bool:
        # element existence: keyed on $element_key.
        if "element_key" in params:
            return params["element_key"] in EXISTING_ELEMENT_KEYS
        # page existence: keyed on $fp and/or $url.
        if "fp" in params or "url" in params:
            return (
                params.get("fp") in EXISTING_PAGE_FPS
                or params.get("url") in EXISTING_PAGE_URLS
            )
        # edge existence: keyed on $entity + the edge_type CONSTANT baked into the cypher
        # (the gate validated edge_type against the allow-list and injected the constant).
        if "entity" in params:
            for edge_type, entity in EXISTING_EDGES:
                if entity == params["entity"] and edge_type in cypher:
                    return True
            return False
        return False


def fake_driver() -> FakeDriver:
    """Factory: a fresh FakeDriver (so each test gets a clean `.calls` log)."""
    return FakeDriver()
