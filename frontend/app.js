'use strict';

// Same-origin API paths: the browser only ever talks to the gateway that
// served this page (Nginx locally, the Ingress/LB in Kubernetes).
const API = { auth: '/api/auth', inventory: '/api/inventory', orders: '/api/orders' };
const ORDERS_PAGE_SIZE = 50;

const state = {
    token: null,
    user: null,
    role: null,
    products: [],
    sort: { field: null, direction: 'default' },
    ordersSkip: 0,
    ordersTotal: 0,
    orderIdempotencyKey: null,
    charts: {},
};

// ------------------------------------------------------------------ DOM helpers
// All API data is inserted as text (textContent / text nodes / Option text),
// never as HTML, so stored values such as product names cannot run scripts.

function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (value === null || value === undefined || value === false) continue;
        if (key === 'class') el.className = value;
        else if (key === 'dataset') Object.assign(el.dataset, value);
        else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
        else el.setAttribute(key, value === true ? '' : String(value));
    }
    for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        el.append(child instanceof Node ? child : String(child));
    }
    return el;
}

function $(id) { return document.getElementById(id); }

function setText(id, value) { $(id).textContent = value; }

function icon(name) { return h('i', { class: `fas ${name}` }); }

function messageRow(colspan, text, cls = 'text-muted') {
    return h('tr', {}, h('td', { colspan, class: `text-center ${cls}` }, text));
}

function money(value) {
    const n = Number(value);
    return Number.isFinite(n) ? `$${n.toFixed(2)}` : '—';
}

function dateTime(iso) {
    return iso ? new Date(iso).toLocaleString(undefined, { timeZoneName: 'short' }) : '—';
}

function newKey() {
    return (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
}

function showAlert(message, type = 'info') {
    const alert = h('div', { class: `alert alert-${type} alert-dismissible fade show`, role: 'alert' },
        h('span', {}, message),
        h('button', { type: 'button', class: 'btn-close', 'data-bs-dismiss': 'alert', 'aria-label': 'Close' }));
    $('alerts').append(alert);
    setTimeout(() => alert.remove(), 6000);
}

function modal(id) { return bootstrap.Modal.getOrCreateInstance($(id)); }

// ------------------------------------------------------------------ session

const storage = {
    get(key) { try { return sessionStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { sessionStorage.setItem(key, value); } catch { /* private mode */ } },
    clear() { try { sessionStorage.clear(); } catch { /* ignore */ } },
};

class ApiError extends Error {
    constructor(status, detail) {
        super(ApiError.describe(detail) || `Request failed (${status})`);
        this.status = status;
    }

    static describe(detail) {
        if (!detail) return '';
        if (typeof detail === 'string') return detail;
        if (Array.isArray(detail)) return detail.map(d => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ');
        if (detail.message) {
            const items = (detail.items || []).map(i => `product ${i.product_id}: requested ${i.requested}, available ${i.available}`);
            return [detail.message, ...items].join(' — ');
        }
        return JSON.stringify(detail);
    }
}

async function api(path, { method = 'GET', body, headers = {} } = {}) {
    const init = { method, headers: { ...headers } };
    if (state.token) init.headers.Authorization = `Bearer ${state.token}`;
    if (body !== undefined) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(body);
    }
    const response = await fetch(path, init);
    let data = null;
    try { data = await response.json(); } catch { /* empty or non-JSON body */ }
    if (response.status === 401 && path !== `${API.auth}/login`) {
        logout('Your session has expired. Please sign in again.');
    }
    if (!response.ok) throw new ApiError(response.status, data && data.detail);
    return data;
}

function applySession() {
    const signedIn = Boolean(state.token);
    $('login-view').hidden = signedIn;
    $('app-view').hidden = !signedIn;
    document.body.classList.toggle('role-viewer', state.role !== 'staff');
    setText('current-user', state.user || '');
    setText('current-role', state.role || '');
}

async function login(event) {
    event.preventDefault();
    $('login-error').hidden = true;
    try {
        const data = await api(`${API.auth}/login`, {
            method: 'POST',
            body: { username: $('login-username').value, password: $('login-password').value },
        });
        state.token = data.access_token;
        state.user = data.username;
        state.role = data.role;
        storage.set('token', state.token);
        storage.set('user', state.user);
        storage.set('role', state.role);
        $('login-password').value = '';
        applySession();
        showSection('dashboard');
    } catch (error) {
        $('login-error').textContent = error.status === 429 ? 'Too many attempts, wait a minute.' : error.message;
        $('login-error').hidden = false;
    }
}

function logout(message) {
    state.token = state.user = state.role = null;
    storage.clear();
    applySession();
    if (message) {
        $('login-error').textContent = message;
        $('login-error').hidden = false;
    }
}

// ------------------------------------------------------------------ navigation

function showSection(name) {
    document.querySelectorAll('.content-section').forEach(s => { s.hidden = s.id !== `${name}-section`; });
    document.querySelectorAll('.nav-link[data-section]').forEach(link => {
        link.classList.toggle('active', link.dataset.section === name);
    });
    const loaders = {
        dashboard: loadDashboard, products: loadProducts, inventory: loadInventory,
        orders: loadOrders, reports: loadReports,
    };
    (loaders[name] || loadDashboard)();
}

// ------------------------------------------------------------------ dashboard

function stockStatus(product) {
    const stock = product.stock || 0;
    if (stock === 0) return { text: 'Out of Stock', badge: 'bg-danger', cls: 'text-danger' };
    if (stock <= (product.safety_stock || 0)) return { text: 'Low Stock', badge: 'bg-warning', cls: 'text-warning' };
    return { text: 'In Stock', badge: 'bg-success', cls: '' };
}

async function loadDashboard() {
    const [products, invStats, orderStats, health] = await Promise.allSettled([
        api(`${API.inventory}/products`),
        api(`${API.inventory}/stats`),
        api(`${API.orders}/stats`),
        api(`${API.inventory}/healthz`),
    ]);
    // A failed request shows "—" instead of a misleading 0.
    setText('total-products', invStats.status === 'fulfilled' ? invStats.value.total_products : '—');
    setText('total-orders', orderStats.status === 'fulfilled' ? orderStats.value.total_orders : '—');
    setText('low-stock-count', invStats.status === 'fulfilled'
        ? invStats.value.low_stock + invStats.value.out_of_stock : '—');
    setText('system-status', health.status === 'fulfilled'
        ? (health.value.status === 'ok' ? 'Healthy' : 'Degraded') : 'Unavailable');

    if (products.status === 'fulfilled') {
        renderStockAlerts(products.value);
        renderInventoryChart(products.value);
    } else {
        $('low-stock-list').replaceChildren(h('div', { class: 'text-danger' }, 'Could not load products'));
    }
}

function renderStockAlerts(products) {
    const out = products.filter(p => (p.stock || 0) === 0);
    const low = products.filter(p => (p.stock || 0) > 0 && p.stock <= (p.safety_stock || 0));
    const block = (title, cls, items) => items.length ? [
        h('h6', { class: `text-${cls} mb-2` }, title),
        items.map(p => h('div', { class: `alert alert-${cls} mb-2` },
            h('strong', {}, p.sku), ` - ${p.name}`, h('br'),
            h('small', {}, `Current: ${p.stock || 0} | Safety: ${p.safety_stock || 0}`))),
    ] : [];
    const content = [...block('Out of Stock', 'danger', out), ...block('Low Stock', 'warning', low)];
    $('low-stock-list').replaceChildren(...(content.length
        ? content.flat() : [h('div', { class: 'text-center text-muted' }, 'No stock alerts')]));
}

function renderChart(key, canvasId, config) {
    if (state.charts[key]) state.charts[key].destroy();
    if (typeof Chart === 'undefined') return;  // CDN blocked: data tables still work
    state.charts[key] = new Chart($(canvasId).getContext('2d'), config);
}

function renderInventoryChart(products) {
    renderChart('inventory', 'inventoryChart', {
        type: 'bar',
        data: {
            labels: products.map(p => p.name),
            datasets: [
                { label: 'Current Stock', data: products.map(p => p.stock || 0),
                  backgroundColor: 'rgba(54, 162, 235, 0.2)', borderColor: 'rgba(54, 162, 235, 1)', borderWidth: 1 },
                { label: 'Safety Stock', data: products.map(p => p.safety_stock || 0),
                  backgroundColor: 'rgba(255, 99, 132, 0.2)', borderColor: 'rgba(255, 99, 132, 1)', borderWidth: 1 },
            ],
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } },
    });
}

// ------------------------------------------------------------------ products

async function loadProducts() {
    try {
        state.products = await api(`${API.inventory}/products`);
        renderProducts();
    } catch (error) {
        $('products-table').replaceChildren(messageRow(8, `Error loading products: ${error.message}`, 'text-danger'));
    }
}

function visibleProducts() {
    const filter = $('status-filter').value;
    const term = $('product-search').value.trim().toLowerCase();
    let list = state.products.filter(p => {
        const status = stockStatus(p).text;
        if (filter === 'in-stock' && status !== 'In Stock') return false;
        if (filter === 'low-stock' && status !== 'Low Stock') return false;
        if (filter === 'out-of-stock' && status !== 'Out of Stock') return false;
        return !term || p.sku.toLowerCase().includes(term) || p.name.toLowerCase().includes(term);
    });
    const { field, direction } = state.sort;
    if (field && direction !== 'default') {
        const value = p => field === 'price' ? Number(p.price) : String(p[field] || '').toLowerCase();
        list = [...list].sort((a, b) => {
            const cmp = value(a) < value(b) ? -1 : value(a) > value(b) ? 1 : 0;
            return direction === 'asc' ? cmp : -cmp;
        });
    }
    return list;
}

function renderProducts() {
    const list = visibleProducts();
    if (!list.length) {
        $('products-table').replaceChildren(messageRow(8, 'No products found'));
        return;
    }
    $('products-table').replaceChildren(...list.map((p, index) => {
        const status = stockStatus(p);
        return h('tr', {},
            h('td', {}, index + 1),
            h('td', {}, p.sku),
            h('td', {}, p.name),
            h('td', {}, money(p.price)),
            h('td', { class: status.cls }, p.stock || 0),
            h('td', {}, p.safety_stock || 0),
            h('td', {}, h('span', { class: `badge ${status.badge}` }, status.text)),
            h('td', {},
                h('button', { class: 'btn btn-sm btn-outline-primary staff-only', title: 'Edit',
                              onclick: () => editProduct(p.id) }, icon('fa-edit')),
                ' ',
                h('button', { class: 'btn btn-sm btn-outline-danger staff-only', title: 'Delete',
                              onclick: () => deleteProduct(p.id) }, icon('fa-trash'))));
    }));
}

function sortProducts(field) {
    const s = state.sort;
    if (s.field !== field) Object.assign(s, { field, direction: 'asc' });
    else if (s.direction === 'asc') s.direction = 'desc';
    else Object.assign(s, { field: null, direction: 'default' });
    ['sku', 'name', 'price'].forEach(f => {
        $(`sort-${f}-icon`).className = s.field !== f ? 'fas fa-minus'
            : s.direction === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down';
    });
    renderProducts();
}

async function addProduct() {
    const form = $('add-product-form');
    if (!form.reportValidity()) return;
    try {
        await api(`${API.inventory}/products`, {
            method: 'POST',
            body: {
                sku: $('product-sku').value,
                name: $('product-name').value,
                price: $('product-price').value,  // sent as a string: exact decimal on the server
                safety_stock: Number.parseInt($('product-safety-stock').value, 10),
                stock: Number.parseInt($('product-stock').value, 10),
            },
        });
        modal('addProductModal').hide();
        form.reset();
        showAlert('Product added', 'success');
        loadProducts();
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'danger');
    }
}

function editProduct(id) {
    const p = state.products.find(x => x.id === id);
    if (!p) return showAlert('Product not found', 'danger');
    $('edit-product-id').value = p.id;
    $('edit-product-sku').value = p.sku;
    $('edit-product-name').value = p.name;
    $('edit-product-price').value = p.price;
    $('edit-product-safety-stock').value = p.safety_stock;
    modal('editProductModal').show();
}

async function updateProduct() {
    if (!$('edit-product-form').reportValidity()) return;
    try {
        await api(`${API.inventory}/products/${encodeURIComponent($('edit-product-id').value)}`, {
            method: 'PUT',
            body: {
                name: $('edit-product-name').value,
                price: $('edit-product-price').value,
                safety_stock: Number.parseInt($('edit-product-safety-stock').value, 10),
            },
        });
        modal('editProductModal').hide();
        showAlert('Product updated', 'success');
        loadProducts();
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'danger');
    }
}

async function deleteProduct(id) {
    if (!confirm('Delete this product?')) return;
    try {
        await api(`${API.inventory}/products/${id}`, { method: 'DELETE' });
        showAlert('Product deleted', 'success');
        loadProducts();
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'danger');
    }
}

// ------------------------------------------------------------------ inventory

function fillProductSelects(products) {
    document.querySelectorAll('.product-select').forEach(select => {
        const current = select.value;
        select.replaceChildren(new Option('Select product...', ''),
            ...products.map(p => new Option(`${p.name} (${p.sku}) — stock ${p.stock}`, String(p.id))));
        select.value = current;
    });
}

async function loadInventory() {
    try {
        state.products = await api(`${API.inventory}/products`);
        fillProductSelects(state.products);
        $('stock-levels').replaceChildren(...(state.products.length ? state.products.map(p =>
            h('div', { class: 'd-flex justify-content-between align-items-center mb-2' },
                h('span', {}, p.name),
                h('span', { class: stockStatus(p).cls }, `${p.stock || 0} / ${p.safety_stock || 0}`)))
            : [h('div', { class: 'text-center text-muted' }, 'No inventory data')]));
    } catch (error) {
        $('stock-levels').replaceChildren(h('div', { class: 'text-danger' }, `Error: ${error.message}`));
    }
}

async function adjustStock(event) {
    event.preventDefault();
    const productId = $('product-select').value;
    const adjustment = Number.parseInt($('adjustment-amount').value, 10);
    if (!productId || !Number.isInteger(adjustment) || adjustment === 0) {
        return showAlert('Select a product and enter a non-zero whole number', 'warning');
    }
    try {
        const result = await api(`${API.inventory}/stock/${encodeURIComponent(productId)}/adjust`,
            { method: 'POST', body: { adjustment } });
        showAlert(`Stock adjusted. New level: ${result.current_stock}`, 'success');
        $('adjustment-amount').value = '';
        loadInventory();
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'danger');
    }
}

// ------------------------------------------------------------------ orders

const STATUS_BADGE = {
    PENDING: 'bg-secondary', CREATED: 'bg-primary', PAID: 'bg-success', SHIPPED: 'bg-info',
    CANCELLED: 'bg-danger', REFUNDED: 'bg-warning', FAILED: 'bg-dark',
};

function statusBadge(order) {
    const badge = h('span', { class: `badge ${STATUS_BADGE[order.status] || 'bg-secondary'}` }, order.status);
    if (!/_PENDING$/.test(order.inventory_sync || '')) return badge;
    return h('span', {}, badge, ' ', h('span', { class: 'badge bg-light text-dark', title: 'Stock update pending; it is retried automatically' },
        icon('fa-clock'), ' stock sync'));
}

async function loadOrders() {
    try {
        const page = await api(`${API.orders}?skip=${state.ordersSkip}&limit=${ORDERS_PAGE_SIZE}`);
        state.ordersTotal = page.total;
        const rows = page.items.map(o => h('tr', {},
            h('td', {}, o.id),
            h('td', {}, o.customer_name || '—'),
            h('td', {}, statusBadge(o)),
            h('td', {}, money(o.total)),
            h('td', {}, dateTime(o.created_at)),
            h('td', {},
                h('button', { class: 'btn btn-sm btn-outline-primary', title: 'View', onclick: () => viewOrder(o.id) }, icon('fa-eye')),
                ' ',
                h('button', { class: 'btn btn-sm btn-outline-success staff-only', title: 'Change status',
                              onclick: () => openStatusModal(o.id) }, icon('fa-edit')),
                ' ',
                h('button', { class: 'btn btn-sm btn-outline-danger staff-only', title: 'Delete (closed orders only)',
                              onclick: () => deleteOrder(o.id) }, icon('fa-trash')))));
        $('orders-table').replaceChildren(...(rows.length ? rows : [messageRow(6, 'No orders found')]));
        const first = page.total ? page.skip + 1 : 0;
        setText('orders-page-info', `Showing ${first}-${page.skip + page.items.length} of ${page.total}`);
        $('orders-prev').disabled = page.skip === 0;
        $('orders-next').disabled = page.skip + page.items.length >= page.total;
    } catch (error) {
        $('orders-table').replaceChildren(messageRow(6, `Error loading orders: ${error.message}`, 'text-danger'));
        setText('orders-page-info', '');
    }
}

function orderItemRow() {
    return h('div', { class: 'row mb-2 order-item-row' },
        h('div', { class: 'col-md-6' }, h('select', { class: 'form-select product-select', required: true })),
        h('div', { class: 'col-md-4' }, h('input', { type: 'number', class: 'form-control quantity-input',
                                                      placeholder: 'Quantity', min: 1, step: 1, required: true })),
        h('div', { class: 'col-md-2' }, h('button', { type: 'button', class: 'btn btn-danger btn-sm',
                                                       onclick: e => e.currentTarget.closest('.row').remove() },
            icon('fa-trash'))));
}

async function openCreateOrder() {
    $('create-order-form').reset();
    $('order-items').replaceChildren(orderItemRow());
    state.orderIdempotencyKey = newKey();  // one key per order attempt; reused on retries
    modal('createOrderModal').show();
    try {
        state.products = await api(`${API.inventory}/products`);
        fillProductSelects(state.products);
    } catch (error) {
        showAlert(`Error loading products: ${error.message}`, 'danger');
    }
}

function addOrderItem() {
    $('order-items').append(orderItemRow());
    fillProductSelects(state.products);
}

async function createOrder() {
    const form = $('create-order-form');
    if (!form.reportValidity()) return;
    const items = [...document.querySelectorAll('#order-items .order-item-row')].map(row => ({
        product_id: Number.parseInt(row.querySelector('.product-select').value, 10),
        qty: Number.parseInt(row.querySelector('.quantity-input').value, 10),
    })).filter(i => Number.isInteger(i.product_id) && Number.isInteger(i.qty));
    if (!items.length) return showAlert('Add at least one item', 'warning');

    try {
        await api(API.orders, {
            method: 'POST',
            headers: { 'Idempotency-Key': state.orderIdempotencyKey },
            body: {
                items,
                customer_name: $('customer-name').value,
                customer_email: $('customer-email').value,
                shipping_address: $('shipping-address').value,
                notes: $('order-notes').value || null,
            },
        });
        modal('createOrderModal').hide();
        showAlert('Order created', 'success');
        loadOrders();
    } catch (error) {
        // Unknown outcome (5xx/network): keep the key so a retry cannot double-book.
        // Definite rejection (4xx): the next attempt is a new request.
        if (error.status && error.status < 500) state.orderIdempotencyKey = newKey();
        showAlert(`Error: ${error.message}`, 'danger');
    }
}

function detailTable(rows) {
    return h('table', { class: 'table table-sm' },
        h('tbody', {}, rows.filter(Boolean).map(([label, value]) => h('tr', {}, h('td', {}, h('strong', {}, label)), h('td', {}, value)))));
}

async function viewOrder(id) {
    try {
        const o = await api(`${API.orders}/${id}`);
        const itemRows = o.items.map(i => h('tr', {},
            h('td', {}, i.product_name), h('td', {}, i.product_sku), h('td', {}, i.qty),
            h('td', {}, money(i.unit_price)), h('td', {}, money(i.subtotal))));
        $('order-details').replaceChildren(
            h('div', { class: 'row' },
                h('div', { class: 'col-md-6' }, h('h6', {}, 'Order Information'), detailTable([
                    ['Order ID:', `#${o.id}`],
                    ['Status:', statusBadge(o)],
                    ['Total:', money(o.total)],
                    ['Created:', dateTime(o.created_at)],
                    ['Updated:', dateTime(o.updated_at)],
                    o.paid_at && ['Paid:', dateTime(o.paid_at)],
                    o.shipped_at && ['Shipped:', dateTime(o.shipped_at)],
                    ['Stock:', o.sync_error ? `${o.inventory_sync} (${o.sync_error})` : o.inventory_sync],
                ])),
                h('div', { class: 'col-md-6' }, h('h6', {}, 'Customer Information'), detailTable([
                    ['Name:', o.customer_name || '—'],
                    ['Email:', o.customer_email || '—'],
                    ['Address:', h('span', { class: 'preserve-lines' }, o.shipping_address || '—')],
                ]))),
            o.notes ? h('div', { class: 'mt-3' }, h('h6', {}, 'Notes'),
                h('div', { class: 'alert alert-info' }, h('pre', { class: 'preserve-lines' }, o.notes))) : null,
            h('div', { class: 'mt-3' }, h('h6', {}, 'Order Items'),
                h('div', { class: 'table-responsive' }, h('table', { class: 'table table-sm' },
                    h('thead', {}, h('tr', {}, ['Product', 'SKU', 'Qty', 'Unit Price', 'Subtotal'].map(t => h('th', {}, t)))),
                    h('tbody', {}, itemRows),
                    h('tfoot', {}, h('tr', { class: 'table-active' }, h('th', { colspan: 4 }, 'Total'), h('th', {}, money(o.total))))))));
        modal('viewOrderModal').show();
    } catch (error) {
        showAlert(`Error loading order: ${error.message}`, 'danger');
    }
}

const STATUS_HELP = {
    PAID: 'Marks the order as paid. Stock stays reserved.',
    SHIPPED: 'Goods leave the warehouse; the stock reservation becomes final.',
    CANCELLED: 'Cancels an unpaid order and returns its stock (once).',
    REFUNDED: 'Before shipping: returns stock. After shipping: money only; restock returned goods manually.',
};

async function openStatusModal(id) {
    try {
        const o = await api(`${API.orders}/${id}`);
        $('update-order-id').value = o.id;
        $('current-status').value = o.status;
        $('status-notes').value = '';
        $('new-status').replaceChildren(new Option('Select new status...', ''),
            ...o.valid_transitions.map(s => new Option(s, s)));
        setText('status-help', o.valid_transitions.length ? '' : 'No further status changes are possible.');
        modal('updateOrderStatusModal').show();
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'danger');
    }
}

async function confirmStatusChange() {
    const status = $('new-status').value;
    if (!status) return showAlert('Select a new status', 'warning');
    try {
        const o = await api(`${API.orders}/${encodeURIComponent($('update-order-id').value)}/status`, {
            method: 'PATCH', body: { status, notes: $('status-notes').value || null },
        });
        modal('updateOrderStatusModal').hide();
        showAlert(o.sync_error ? `Status updated; stock sync pending (${o.sync_error})` : 'Status updated',
            o.sync_error ? 'warning' : 'success');
        loadOrders();
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'danger');
    }
}

async function deleteOrder(id) {
    if (!confirm('Delete this order permanently? Only cancelled, refunded or failed orders can be deleted.')) return;
    try {
        await api(`${API.orders}/${id}`, { method: 'DELETE' });
        showAlert('Order deleted', 'success');
        loadOrders();
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'danger');
    }
}

// ------------------------------------------------------------------ reports

function statCard(value, label, cls) {
    return h('div', { class: 'col-6 mb-3' }, h('div', { class: 'card bg-light' }, h('div', { class: 'card-body text-center' },
        h('h5', { class: `card-title text-${cls}` }, value), h('p', { class: 'card-text small' }, label))));
}

function productTable(rows, emptyText, rowClass) {
    return h('div', { class: 'table-responsive' }, h('table', { class: 'table table-sm' },
        h('thead', {}, h('tr', {}, ['Product Name', 'SKU', 'Current Stock', 'Safety Stock'].map(t => h('th', {}, t)))),
        h('tbody', {}, rows.length ? rows.map(p => h('tr', { class: rowClass },
            h('td', {}, p.name), h('td', {}, p.sku), h('td', {}, p.current_stock), h('td', {}, p.safety_stock)))
            : messageRow(4, emptyText))));
}

async function loadReports() {
    await Promise.all([loadInventoryReport(), loadOrderReport()]);
}

async function loadInventoryReport() {
    try {
        const [stats, lowStock] = await Promise.all([
            api(`${API.inventory}/stats`), api(`${API.inventory}/low-stock`)]);
        $('inventory-report').replaceChildren(
            h('h6', { class: 'text-primary mb-3' }, 'Inventory Overview'),
            h('div', { class: 'row' },
                statCard(money(stats.total_value), 'Total Inventory Value', 'success'),
                statCard(stats.total_products, 'Total Products', 'info')),
            h('h6', { class: 'text-primary mb-3' }, 'Inventory Status Distribution'),
            h('div', { class: 'chart-box chart-box-lg' }, h('canvas', { id: 'inventoryStatusChart' })),
            h('h6', { class: 'text-danger mt-3 mb-3' }, 'Out of Stock'),
            productTable(lowStock.filter(p => p.current_stock === 0), 'No out of stock products', 'table-danger'),
            h('h6', { class: 'text-warning mt-3 mb-3' }, 'Low Stock'),
            productTable(lowStock.filter(p => p.current_stock > 0), 'No low stock products', 'table-warning'));
        renderChart('inventoryStatus', 'inventoryStatusChart', {
            type: 'doughnut',
            data: {
                labels: ['In Stock', 'Low Stock', 'Out of Stock'],
                datasets: [{ data: [stats.in_stock, stats.low_stock, stats.out_of_stock],
                             backgroundColor: ['rgba(40, 167, 69, 0.8)', 'rgba(255, 193, 7, 0.8)', 'rgba(220, 53, 69, 0.8)'] }],
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } },
        });
    } catch (error) {
        $('inventory-report').replaceChildren(h('div', { class: 'alert alert-danger' }, `Error loading inventory report: ${error.message}`));
    }
}

async function loadOrderReport() {
    try {
        const stats = await api(`${API.orders}/stats`);
        const statuses = Object.keys(stats.by_status);
        $('order-report').replaceChildren(
            h('h6', { class: 'text-primary mb-3' }, `Order Overview (${stats.scope})`),
            h('div', { class: 'row' },
                statCard(money(stats.revenue), 'Revenue (paid + shipped)', 'success'),
                statCard(stats.total_orders, 'Total Orders', 'info'),
                statCard(money(stats.average_order_value), 'Average Paid Order', 'warning'),
                statCard(stats.pending_inventory_sync, 'Orders Awaiting Stock Sync', 'secondary')),
            h('h6', { class: 'text-primary mb-3' }, 'Order Status Distribution'),
            h('div', { class: 'chart-box chart-box-md' }, h('canvas', { id: 'orderStatusChart' })),
            h('h6', { class: 'text-primary mt-3 mb-3' }, 'Top Customers (paid + shipped)'),
            h('div', { class: 'table-responsive' }, h('table', { class: 'table table-sm' },
                h('thead', {}, h('tr', {}, ['Customer Name', 'Orders', 'Total Spent'].map(t => h('th', {}, t)))),
                h('tbody', {}, stats.top_customers.length ? stats.top_customers.map(c => h('tr', {},
                    h('td', {}, c.customer_name), h('td', {}, c.orders), h('td', {}, money(c.total))))
                    : messageRow(3, 'No paid orders yet')))));
        renderChart('orderStatus', 'orderStatusChart', {
            type: 'bar',
            data: { labels: statuses, datasets: [{ label: 'Orders', data: statuses.map(s => stats.by_status[s]),
                                                  backgroundColor: 'rgba(54, 162, 235, 0.8)' }] },
            options: { responsive: true, maintainAspectRatio: false,
                       scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }, plugins: { legend: { display: false } } },
        });
    } catch (error) {
        $('order-report').replaceChildren(h('div', { class: 'alert alert-danger' }, `Error loading order report: ${error.message}`));
    }
}

// ------------------------------------------------------------------ wiring

function bindEvents() {
    $('login-form').addEventListener('submit', login);
    $('logout-btn').addEventListener('click', () => logout());
    document.querySelectorAll('.nav-link[data-section]').forEach(link => link.addEventListener('click', event => {
        event.preventDefault();
        showSection(event.currentTarget.dataset.section);
    }));
    document.querySelectorAll('[data-sort]').forEach(btn => btn.addEventListener('click', event => {
        sortProducts(event.currentTarget.dataset.sort);
    }));
    $('refresh-dashboard').addEventListener('click', loadDashboard);
    $('status-filter').addEventListener('change', renderProducts);
    $('product-search').addEventListener('input', renderProducts);
    $('add-product-btn').addEventListener('click', () => modal('addProductModal').show());
    $('add-product-submit').addEventListener('click', addProduct);
    $('edit-product-submit').addEventListener('click', updateProduct);
    $('stock-adjustment-form').addEventListener('submit', adjustStock);
    $('create-order-btn').addEventListener('click', openCreateOrder);
    $('add-order-item').addEventListener('click', addOrderItem);
    $('create-order-submit').addEventListener('click', createOrder);
    $('update-status-submit').addEventListener('click', confirmStatusChange);
    $('new-status').addEventListener('change', e => setText('status-help', STATUS_HELP[e.target.value] || ''));
    $('orders-prev').addEventListener('click', () => {
        state.ordersSkip = Math.max(0, state.ordersSkip - ORDERS_PAGE_SIZE);
        loadOrders();
    });
    $('orders-next').addEventListener('click', () => {
        state.ordersSkip += ORDERS_PAGE_SIZE;
        loadOrders();
    });
}

document.addEventListener('DOMContentLoaded', () => {
    bindEvents();
    state.token = storage.get('token');
    state.user = storage.get('user');
    state.role = storage.get('role');
    applySession();
    if (state.token) showSection('dashboard');
});
