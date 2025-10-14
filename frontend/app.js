// API Configuration
const API_BASE = {
    inventory: 'http://localhost:8001/api/inventory',
    orders: 'http://localhost:8002/api/orders'
};

// Global variables
let products = [];
let orders = [];
let inventoryData = [];
let charts = {};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadDashboardData();
    loadProducts();
    loadOrders();
    loadInventory();
});

// Show different sections
function showSection(sectionName) {
    // Hide all sections
    document.querySelectorAll('.content-section').forEach(section => {
        section.style.display = 'none';
    });
    
    // Show selected section
    document.getElementById(sectionName + '-section').style.display = 'block';
    
    // Update navigation state
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Reload data
    if (sectionName === 'dashboard') {
        loadDashboardData();
    } else if (sectionName === 'products') {
        loadProducts();
    } else if (sectionName === 'inventory') {
        loadInventory();
    } else if (sectionName === 'orders') {
        loadOrders();
    }
}

// Load dashboard data
async function loadDashboardData() {
    try {
        // Load statistics
        const [productsRes, ordersRes, lowStockRes, healthRes] = await Promise.all([
            fetch(`${API_BASE.inventory}/products`),
            fetch(`${API_BASE.orders}/`),
            fetch(`${API_BASE.inventory}/low-stock`),
            fetch(`${API_BASE.inventory}/healthz`)
        ]);

        const productsData = await productsRes.json();
        const ordersData = await ordersRes.json();
        const lowStockData = await lowStockRes.json();
        const healthData = await healthRes.json();

        // Update statistics
        document.getElementById('total-products').textContent = productsData.length || 0;
        document.getElementById('total-orders').textContent = ordersData.length || 0;
        document.getElementById('low-stock-count').textContent = lowStockData.length || 0;
        document.getElementById('system-status').textContent = healthData.status === 'ok' ? 'Healthy' : 'Unhealthy';

        // Load low stock alerts
        loadLowStockAlerts(lowStockData);

        // Load inventory chart
        loadInventoryChart(productsData);

    } catch (error) {
        console.error('Error loading dashboard data:', error);
        showAlert('Error loading dashboard data', 'danger');
    }
}

// Load low stock alerts
function loadLowStockAlerts(lowStockData) {
    const container = document.getElementById('low-stock-list');
    
    if (lowStockData.length === 0) {
        container.innerHTML = '<div class="text-center text-muted">No low stock items</div>';
        return;
    }

    let html = '';
    lowStockData.forEach(item => {
        html += `
            <div class="alert alert-warning alert-dismissible fade show" role="alert">
                <strong>${item.sku}</strong> - ${item.name}<br>
                <small>Current: ${item.current_stock} | Safety: ${item.safety_stock}</small>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// Load inventory chart
function loadInventoryChart(productsData) {
    const ctx = document.getElementById('inventoryChart').getContext('2d');
    
    // Destroy existing chart
    if (charts.inventory) {
        charts.inventory.destroy();
    }

    const labels = productsData.map(p => p.name);
    const stockData = productsData.map(p => p.stock || 0);
    const safetyStockData = productsData.map(p => p.safety_stock || 0);

    charts.inventory = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Current Stock',
                data: stockData,
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }, {
                label: 'Safety Stock',
                data: safetyStockData,
                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

// Load products
async function loadProducts() {
    try {
        const response = await fetch(`${API_BASE.inventory}/products`);
        products = await response.json();
        
        const tbody = document.getElementById('products-table');
        if (products.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No products found</td></tr>';
            return;
        }

        let html = '';
        products.forEach(product => {
            const statusClass = (product.stock || 0) <= (product.safety_stock || 0) ? 'low-stock' : '';
            const statusText = (product.stock || 0) <= (product.safety_stock || 0) ? 'Low Stock' : 'In Stock';
            
            html += `
                <tr>
                    <td>${product.id}</td>
                    <td>${product.sku}</td>
                    <td>${product.name}</td>
                    <td>$${product.price}</td>
                    <td class="${statusClass}">${product.stock || 0}</td>
                    <td>${product.safety_stock || 0}</td>
                    <td><span class="badge ${statusClass ? 'bg-warning' : 'bg-success'}">${statusText}</span></td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="editProduct(${product.id})">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteProduct(${product.id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
        });
        
        tbody.innerHTML = html;
    } catch (error) {
        console.error('Error loading products:', error);
        showAlert('Error loading products', 'danger');
    }
}

// Load orders
async function loadOrders() {
    try {
        const response = await fetch(`${API_BASE.orders}/`);
        orders = await response.json();
        
        const tbody = document.getElementById('orders-table');
        if (orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No orders found</td></tr>';
            return;
        }

        let html = '';
        orders.forEach(order => {
            const statusClass = getStatusClass(order.status);
            const createdDate = new Date(order.created_at).toLocaleDateString();
            
            html += `
                <tr>
                    <td>${order.id}</td>
                    <td>${order.customer_name}</td>
                    <td><span class="badge ${statusClass}">${order.status}</span></td>
                    <td>$${order.total}</td>
                    <td>${createdDate}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="viewOrder(${order.id})">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-success" onclick="updateOrderStatus(${order.id})">
                            <i class="fas fa-edit"></i>
                        </button>
                    </td>
                </tr>
            `;
        });
        
        tbody.innerHTML = html;
    } catch (error) {
        console.error('Error loading orders:', error);
        showAlert('Error loading orders', 'danger');
    }
}

// Load inventory
async function loadInventory() {
    try {
        const response = await fetch(`${API_BASE.inventory}/products`);
        inventoryData = await response.json();
        
        // Update product select options
        updateProductSelects();
        
        // Load stock levels
        loadStockLevels();
    } catch (error) {
        console.error('Error loading inventory:', error);
        showAlert('Error loading inventory', 'danger');
    }
}

// Update product select options
function updateProductSelects() {
    const selects = document.querySelectorAll('.product-select');
    selects.forEach(select => {
        select.innerHTML = '<option value="">Select Product...</option>';
        inventoryData.forEach(product => {
            select.innerHTML += `<option value="${product.id}">${product.name} (${product.sku})</option>`;
        });
    });
}

// Load stock levels
function loadStockLevels() {
    const container = document.getElementById('stock-levels');
    
    if (inventoryData.length === 0) {
        container.innerHTML = '<div class="text-center text-muted">No inventory data</div>';
        return;
    }

    let html = '';
    inventoryData.forEach(product => {
        const statusClass = (product.stock || 0) <= (product.safety_stock || 0) ? 'low-stock' : '';
        html += `
            <div class="d-flex justify-content-between align-items-center mb-2">
                <span>${product.name}</span>
                <span class="${statusClass}">${product.stock || 0} / ${product.safety_stock || 0}</span>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// Show add product modal
function showAddProductModal() {
    const modal = new bootstrap.Modal(document.getElementById('addProductModal'));
    modal.show();
}

// Add product
async function addProduct() {
    const form = document.getElementById('add-product-form');
    const formData = new FormData(form);
    
    const productData = {
        sku: document.getElementById('product-sku').value,
        name: document.getElementById('product-name').value,
        price: parseFloat(document.getElementById('product-price').value),
        safety_stock: parseInt(document.getElementById('product-safety-stock').value)
    };

    try {
        const response = await fetch(`${API_BASE.inventory}/products`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(productData)
        });

        if (response.ok) {
            showAlert('Product added successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('addProductModal')).hide();
            form.reset();
            loadProducts();
            loadInventory();
        } else {
            const error = await response.json();
            showAlert(`Error: ${error.detail || 'Failed to add product'}`, 'danger');
        }
    } catch (error) {
        console.error('Error adding product:', error);
        showAlert('Error adding product', 'danger');
    }
}

// Show create order modal
function showCreateOrderModal() {
    const modal = new bootstrap.Modal(document.getElementById('createOrderModal'));
    modal.show();
    updateProductSelects();
}

// Add order item
function addOrderItem() {
    const container = document.getElementById('order-items');
    const newItem = document.createElement('div');
    newItem.className = 'row mb-2';
    newItem.innerHTML = `
        <div class="col-md-6">
            <select class="form-select product-select" required>
                <option value="">Select Product...</option>
            </select>
        </div>
        <div class="col-md-4">
            <input type="number" class="form-control quantity-input" placeholder="Quantity" min="1" required>
        </div>
        <div class="col-md-2">
            <button type="button" class="btn btn-danger btn-sm" onclick="removeOrderItem(this)">
                <i class="fas fa-trash"></i>
            </button>
        </div>
    `;
    container.appendChild(newItem);
    updateProductSelects();
}

// Remove order item
function removeOrderItem(button) {
    button.closest('.row').remove();
}

// Create order
async function createOrder() {
    const form = document.getElementById('create-order-form');
    const items = [];
    
    // Collect order items
    document.querySelectorAll('#order-items .row').forEach(row => {
        const productSelect = row.querySelector('.product-select');
        const quantityInput = row.querySelector('.quantity-input');
        
        if (productSelect.value && quantityInput.value) {
            items.push({
                product_id: parseInt(productSelect.value),
                qty: parseInt(quantityInput.value)
            });
        }
    });

    if (items.length === 0) {
        showAlert('Please add at least one item to the order', 'warning');
        return;
    }

    const orderData = {
        items: items,
        customer_name: document.getElementById('customer-name').value,
        customer_email: document.getElementById('customer-email').value,
        shipping_address: document.getElementById('shipping-address').value,
        notes: document.getElementById('order-notes').value
    };

    try {
        const response = await fetch(`${API_BASE.orders}/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(orderData)
        });

        if (response.ok) {
            showAlert('Order created successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('createOrderModal')).hide();
            form.reset();
            document.getElementById('order-items').innerHTML = `
                <div class="row mb-2">
                    <div class="col-md-6">
                        <select class="form-select product-select" required>
                            <option value="">Select Product...</option>
                        </select>
                    </div>
                    <div class="col-md-4">
                        <input type="number" class="form-control quantity-input" placeholder="Quantity" min="1" required>
                    </div>
                    <div class="col-md-2">
                        <button type="button" class="btn btn-danger btn-sm" onclick="removeOrderItem(this)">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
            loadOrders();
        } else {
            const error = await response.json();
            showAlert(`Error: ${error.detail || 'Failed to create order'}`, 'danger');
        }
    } catch (error) {
        console.error('Error creating order:', error);
        showAlert('Error creating order', 'danger');
    }
}

// Stock adjustment form submission
document.getElementById('stock-adjustment-form').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const productId = document.getElementById('product-select').value;
    const adjustment = parseInt(document.getElementById('adjustment-amount').value);
    
    if (!productId || !adjustment) {
        showAlert('Please select a product and enter adjustment amount', 'warning');
        return;
    }

    try {
        const response = await fetch(`${API_BASE.inventory}/stock/${productId}/adjust`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ adjustment: adjustment })
        });

        if (response.ok) {
            const result = await response.json();
            showAlert(`Stock adjusted successfully. New stock level: ${result.current_stock}`, 'success');
            loadInventory();
            loadProducts();
        } else {
            const error = await response.json();
            showAlert(`Error: ${error.detail || 'Failed to adjust stock'}`, 'danger');
        }
    } catch (error) {
        console.error('Error adjusting stock:', error);
        showAlert('Error adjusting stock', 'danger');
    }
});

// Helper functions
function getStatusClass(status) {
    switch (status) {
        case 'CREATED': return 'bg-primary';
        case 'PAID': return 'bg-success';
        case 'SHIPPED': return 'bg-info';
        case 'CANCELLED': return 'bg-danger';
        default: return 'bg-secondary';
    }
}

function showAlert(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.parentNode.removeChild(alertDiv);
        }
    }, 5000);
}

function refreshDashboard() {
    loadDashboardData();
}

// Placeholder functions for future implementation
function editProduct(id) {
    showAlert('Edit product functionality coming soon', 'info');
}

function deleteProduct(id) {
    if (confirm('Are you sure you want to delete this product?')) {
        showAlert('Delete product functionality coming soon', 'info');
    }
}

function viewOrder(id) {
    showAlert('View order functionality coming soon', 'info');
}

function updateOrderStatus(id) {
    showAlert('Update order status functionality coming soon', 'info');
}