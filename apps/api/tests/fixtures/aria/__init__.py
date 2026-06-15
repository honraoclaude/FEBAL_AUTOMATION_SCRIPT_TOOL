"""Hand-built normalized node trees + aria_snapshot YAML samples (Phase 4, Slice 2).

PURE fixtures — no browser, no LLM, no spend. The fingerprint hashing path consumes a
plain node tree (the shape `fingerprint.normalize_aria_tree` produces from a Playwright
aria_snapshot), so these fixtures let the structural fingerprint + the two-run convergence
proof exercise the REAL hashing/saturation/budget code with zero stack.

Node tree shape (the contract `structural_fingerprint` walks):
    {"role": str, "tag": str | None, "attrs": {str: str}, "children": [<node>, ...]}

Two screens are modeled:
  * PRODUCT_LIST_6 / PRODUCT_LIST_4 — SAME skeleton, different INSTANCE counts (6 vs 4
    items) and different text/ids. With sibling folding ON they fingerprint IDENTICALLY
    (template equality); with folding OFF they differ (the tunable).
  * CART_PAGE — a structurally DIFFERENT landmark/heading skeleton (must hash differently).
  * LOGIN_PAGE / POST_LOGIN_PAGE — auth fixtures reused by test_auth_detect.py (a password
    input present vs absent).
"""

from __future__ import annotations


def _item(name: str, price: str) -> dict:
    """One product-list item subtree — same STRUCTURE, different text/ids (stripped)."""
    return {
        "role": "listitem",
        "tag": "li",
        "attrs": {"id": f"item_{name}_{price}", "data-test": f"inventory-item-{name}"},
        "children": [
            {"role": "heading", "tag": "h3", "attrs": {"aria-level": "3"}, "children": []},
            {"role": "paragraph", "tag": "p", "attrs": {}, "children": []},
            {
                "role": "button",
                "tag": "button",
                "attrs": {"data-test": f"add-to-cart-{name}"},
                "children": [],
            },
        ],
    }


def _product_list(items: list[tuple[str, str]]) -> dict:
    """A product-list page skeleton with N item subtrees (the instance count varies)."""
    return {
        "role": "document",
        "tag": "html",
        "attrs": {},
        "children": [
            {
                "role": "banner",
                "tag": "header",
                "attrs": {},
                "children": [
                    {"role": "heading", "tag": "h1", "attrs": {"aria-level": "1"}, "children": []}
                ],
            },
            {
                "role": "main",
                "tag": "main",
                "attrs": {},
                "children": [
                    {
                        "role": "list",
                        "tag": "ul",
                        "attrs": {"data-test": "inventory-list"},
                        "children": [_item(n, p) for n, p in items],
                    }
                ],
            },
        ],
    }


# Six-item product list (instance data: 6 products, specific names/prices).
PRODUCT_LIST_6 = _product_list(
    [
        ("backpack", "29.99"),
        ("bikelight", "9.99"),
        ("tshirt", "15.99"),
        ("jacket", "49.99"),
        ("onesie", "7.99"),
        ("redshirt", "15.99"),
    ]
)

# Four-item product list — SAME skeleton, DIFFERENT instance count + different text/ids.
PRODUCT_LIST_4 = _product_list(
    [
        ("widget", "1.00"),
        ("gadget", "2.50"),
        ("gizmo", "3.75"),
        ("doohickey", "4.20"),
    ]
)

# Same screen rendered twice with different text/ids only (no structural change at all).
PRODUCT_LIST_6_ALT = _product_list(
    [
        ("alpha", "10.00"),
        ("bravo", "11.00"),
        ("charlie", "12.00"),
        ("delta", "13.00"),
        ("echo", "14.00"),
        ("foxtrot", "15.00"),
    ]
)


# A structurally DIFFERENT page: a cart with a table + a heading skeleton unlike the list.
CART_PAGE = {
    "role": "document",
    "tag": "html",
    "attrs": {},
    "children": [
        {
            "role": "banner",
            "tag": "header",
            "attrs": {},
            "children": [
                {"role": "heading", "tag": "h1", "attrs": {"aria-level": "1"}, "children": []}
            ],
        },
        {
            "role": "main",
            "tag": "main",
            "attrs": {},
            "children": [
                {
                    "role": "table",
                    "tag": "table",
                    "attrs": {"data-test": "cart-table"},
                    "children": [
                        {
                            "role": "row",
                            "tag": "tr",
                            "attrs": {},
                            "children": [
                                {"role": "cell", "tag": "td", "attrs": {}, "children": []},
                                {"role": "cell", "tag": "td", "attrs": {}, "children": []},
                            ],
                        }
                    ],
                },
                {
                    "role": "button",
                    "tag": "button",
                    "attrs": {"data-test": "checkout"},
                    "children": [],
                },
            ],
        },
    ],
}


# --- Auth fixtures (Task 3) — node trees with/without a password input. ---

LOGIN_PAGE = {
    "role": "document",
    "tag": "html",
    "attrs": {},
    "children": [
        {
            "role": "main",
            "tag": "main",
            "attrs": {},
            "children": [
                {
                    "role": "form",
                    "tag": "form",
                    "attrs": {},
                    "children": [
                        {
                            "role": "textbox",
                            "tag": "input",
                            "attrs": {"type": "text", "id": "user-name", "name": "user-name"},
                            "children": [],
                        },
                        {
                            "role": "textbox",
                            "tag": "input",
                            "attrs": {"type": "password", "id": "password", "name": "password"},
                            "children": [],
                        },
                        {
                            "role": "button",
                            "tag": "input",
                            "attrs": {"type": "submit", "id": "login-button"},
                            "children": [],
                        },
                    ],
                }
            ],
        }
    ],
}

# After login — the inventory page; NO password input present (not a login page).
POST_LOGIN_PAGE = PRODUCT_LIST_6

# An email-style login (heuristic must accept type=email as the nearby text input too).
LOGIN_PAGE_EMAIL = {
    "role": "document",
    "tag": "html",
    "attrs": {},
    "children": [
        {
            "role": "form",
            "tag": "form",
            "attrs": {},
            "children": [
                {
                    "role": "textbox",
                    "tag": "input",
                    "attrs": {"type": "email", "id": "email", "name": "email"},
                    "children": [],
                },
                {
                    "role": "textbox",
                    "tag": "input",
                    "attrs": {"type": "password", "id": "pw", "name": "pw"},
                    "children": [],
                },
                {
                    "role": "button",
                    "tag": "button",
                    "attrs": {"type": "submit"},
                    "children": [],
                },
            ],
        }
    ],
}
