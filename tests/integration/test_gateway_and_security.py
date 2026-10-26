"""ARCH-01, SEC-02, SEC-03 (server side), SEC-04, API-01 through the gateway."""
import os

from conftest import unique


def test_frontend_is_served_by_the_gateway_without_localhost_urls(http):
    page = http.get("/")
    assert page.status_code == 200 and "Smart Inventory" in page.text
    app_js = http.get("/app.js").text
    assert "localhost" not in app_js and "8001" not in app_js and "8002" not in app_js
    assert "'/api/inventory'" in app_js and "'/api/orders'" in app_js


def test_security_headers(http):
    headers = http.get("/").headers
    assert "script-src 'self' https://cdn.jsdelivr.net" in headers["content-security-policy"]
    assert "unsafe-inline" not in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"


def test_health_paths_through_gateway(http):
    for path in ("/healthz", "/api/inventory/livez", "/api/inventory/readyz", "/api/orders/livez",
                 "/api/orders/readyz"):
        assert http.get(path).status_code == 200, path
    assert http.get("/api/unknown").status_code == 404


def test_anonymous_cannot_read_customer_data_or_write(http):
    assert http.get("/api/orders").status_code == 401
    assert http.get("/api/orders/1").status_code == 401
    assert http.get("/api/orders/stats").status_code == 401
    assert http.get("/api/inventory/products").status_code == 401
    assert http.post("/api/inventory/products", json={}).status_code == 401


def test_viewer_is_read_only(http, viewer, product):
    p = product()
    assert http.get("/api/orders", headers=viewer).status_code == 200
    assert http.post(f"/api/inventory/stock/{p['id']}/adjust", headers=viewer,
                     json={"adjustment": 1}).status_code == 403
    assert http.post("/api/orders", headers=viewer,
                     json={"items": [{"product_id": p["id"], "qty": 1}]}).status_code == 403


def test_gateway_strips_service_token(http):
    """Browsers must not be able to use the internal service credential."""
    token = os.getenv("SERVICE_TOKEN", "any-guess-at-the-service-token")
    r = http.get("/api/inventory/reservations/abcdefgh", headers={"X-Service-Token": token})
    assert r.status_code == 401


def test_html_in_product_fields_is_stored_as_plain_text(http, staff):
    payload = '<img src=x onerror="window.__xss=1"><script>alert(1)</script>'
    sku = unique()
    r = http.post("/api/inventory/products", headers=staff,
                  json={"sku": sku, "name": payload, "price": "1.00", "stock": 1})
    assert r.status_code == 201
    stored = http.get(f"/api/inventory/products/{r.json()['id']}", headers=staff).json()
    assert stored["name"] == payload  # unchanged text; the frontend renders it with textContent


def test_validation_through_gateway(http, staff):
    bad = [{"sku": unique(), "name": "n", "price": "-1"},
           {"sku": unique(), "name": "n", "price": "1", "stock": -3},
           {"sku": unique(), "name": "x" * 300, "price": "1"}]
    for body in bad:
        assert http.post("/api/inventory/products", headers=staff, json=body).status_code == 422
    assert http.get("/api/orders?limit=10000", headers=staff).status_code == 422
    r = http.post("/api/auth/login", json={"username": "u", "password": ""})
    assert r.status_code == 422 and "input" not in r.text  # rejected values are not echoed


def test_order_api_has_no_trailing_slash_redirect_to_internal_hosts(http, staff):
    r = http.get("/api/orders/", headers=staff, follow_redirects=False)
    assert r.status_code == 200


# Keep last: it uses up the login rate-limit budget for about a minute.
def test_login_is_rate_limited(http):
    codes = [http.post("/api/auth/login", json={"username": "nobody", "password": "wrong"}).status_code
             for _ in range(12)]
    assert 429 in codes and set(codes) <= {401, 429}
