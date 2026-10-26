// SEC-03 regression test: API data containing HTML must render as text in every
// view (lists, selects, order details, reports). Runs the real frontend/app.js in
// jsdom with a mocked API; no server needed.   cd tests/frontend && npm test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const root = new URL('../../frontend/', import.meta.url);
const PAYLOAD = '<img src=x onerror="window.__xss=1"><script>window.__xss=1</script>';

const product = (id, stock) => ({ id, sku: `SKU-${id}`, name: `${PAYLOAD} product ${id}`, price: '2.50', safety_stock: 5, stock });
const products = [product(1, 0), product(2, 3), product(3, 50)];
const order = {
    id: 7, status: 'PAID', total: '2.50', customer_name: `${PAYLOAD} Mallory`, customer_email: 'm@example.com',
    shipping_address: `${PAYLOAD} street`, notes: `${PAYLOAD} note`, created_at: '2026-10-26T00:00:00Z',
    updated_at: '2026-10-26T00:00:00Z', paid_at: null, shipped_at: null, inventory_sync: 'RESERVED', sync_error: null,
    valid_transitions: ['SHIPPED', 'REFUNDED'],
    items: [{ id: 1, product_id: 2, product_name: `${PAYLOAD} item`, product_sku: `${PAYLOAD}sku`, qty: 1, unit_price: '2.50', subtotal: '2.50' }],
};
const routes = {
    '/api/inventory/products': products,
    '/api/inventory/stats': { total_products: 3, total_units: 53, total_value: '132.50', in_stock: 1, low_stock: 1, out_of_stock: 1 },
    '/api/inventory/healthz': { status: 'ok' },
    '/api/inventory/low-stock': products.slice(0, 2).map(p => ({ product_id: p.id, sku: p.sku, name: p.name, current_stock: p.stock, safety_stock: 5 })),
    '/api/orders/stats': { scope: 'all orders', total_orders: 1, by_status: { PAID: 1 }, revenue: '2.50', revenue_orders: 1,
                           average_order_value: '2.50', pending_inventory_sync: 0,
                           top_customers: [{ customer_name: `${PAYLOAD} Mallory`, orders: 1, total: '2.50' }] },
    '/api/orders/7': order,
};

async function boot() {
    const html = readFileSync(new URL('index.html', root), 'utf8').replace(/<script[^>]*src="[^"]*"[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, { runScripts: 'dangerously', url: 'http://gateway.test/' });
    const { window } = dom;
    window.sessionStorage.setItem('token', 'test-token');
    window.sessionStorage.setItem('role', 'staff');
    window.bootstrap = { Modal: { getOrCreateInstance: () => ({ show() {}, hide() {} }) } };
    window.fetch = async (url) => {
        const path = new URL(url, 'http://gateway.test').pathname;
        const body = path === '/api/orders' ? { items: [{ ...order, item_count: 1 }], total: 1, skip: 0, limit: 50 } : routes[path];
        return { ok: body !== undefined, status: body ? 200 : 404, json: async () => body ?? { detail: 'not found' } };
    };
    // Load app.js as a classic script so its functions become globals, like in the browser.
    const script = window.document.createElement('script');
    script.textContent = readFileSync(new URL('app.js', root), 'utf8');
    window.document.head.append(script);
    window.document.dispatchEvent(new window.Event('DOMContentLoaded'));
    return window;
}

const settle = () => new Promise(r => setTimeout(r, 50));

function assertTextOnly(window, containerId) {
    const el = window.document.getElementById(containerId);
    assert.equal(el.querySelectorAll('img, script').length, 0, `${containerId} contains injected elements`);
    assert.ok(el.textContent.includes('<img src=x onerror='), `${containerId} should show the payload as text`);
}

test('API data is rendered as text in every view', async () => {
    const window = await boot();
    for (const section of ['dashboard', 'products', 'inventory', 'orders', 'reports']) {
        window.showSection(section);
        await settle();
    }
    for (const id of ['low-stock-list', 'products-table', 'stock-levels', 'orders-table', 'inventory-report', 'order-report']) {
        assertTextOnly(window, id);
    }
    const options = [...window.document.querySelectorAll('#product-select option')];
    assert.ok(options.some(o => o.textContent.includes('<script>')));
    assert.equal(window.document.querySelectorAll('#product-select img, #product-select script').length, 0);

    await window.viewOrder(7);
    assertTextOnly(window, 'order-details');
    assert.equal(window.__xss, undefined);
});

test('failed API calls show a dash, not a misleading zero', async () => {
    const window = await boot();
    window.fetch = async () => ({ ok: false, status: 503, json: async () => ({ detail: 'down' }) });
    await window.loadDashboard();
    for (const id of ['total-products', 'total-orders', 'low-stock-count']) {
        assert.equal(window.document.getElementById(id).textContent, '—');
    }
    assert.equal(window.document.getElementById('system-status').textContent, 'Unavailable');
});
