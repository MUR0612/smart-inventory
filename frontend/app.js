// API Configuration
const API_BASE = {
    inventory: 'http://localhost:8001/api',
    orders: 'http://localhost:8002/api'
};

// Global variables
let products = [];
let orders = [];
let inventoryData = [];
let filteredProducts = [];
let currentSort = { field: null, direction: 'asc' };
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
    } else if (sectionName === 'reports') {
        loadReports();
    }
}

// Load dashboard data
async function loadDashboardData() {
    try {
        // Load statistics
        const [productsRes, ordersRes, lowStockRes, healthRes] = await Promise.all([
            fetch(`${API_BASE.inventory}/inventory/products`),
            fetch(`${API_BASE.orders}/orders/`),
            fetch(`${API_BASE.inventory}/inventory/low-stock`),
            fetch(`${API_BASE.inventory}/healthz`)
        ]);

        const productsData = await productsRes.json();
        const ordersData = await ordersRes.json();
        const lowStockData = await lowStockRes.json();
        const healthData = await healthRes.json();

        // 計算庫存警告統計
        const outOfStockCount = productsData.filter(p => (p.stock || 0) === 0).length;
        const lowStockCount = productsData.filter(p => {
            const stock = p.stock || 0;
            const safetyStock = p.safety_stock || 0;
            return stock > 0 && stock <= safetyStock;
        }).length;
        const totalStockAlerts = outOfStockCount + lowStockCount;

        // Update statistics
        document.getElementById('total-products').textContent = productsData.length || 0;
        document.getElementById('total-orders').textContent = ordersData.length || 0;
        document.getElementById('low-stock-count').textContent = totalStockAlerts || 0;
        document.getElementById('system-status').textContent = healthData.status === 'ok' ? 'Healthy' : 'Unhealthy';

        // Load low stock and out of stock alerts
        loadStockAlerts(productsData);

        // Load inventory chart
        loadInventoryChart(productsData);

    } catch (error) {
        console.error('Error loading dashboard data:', error);
        showAlert('Error loading dashboard data', 'danger');
    }
}

// Load low stock alerts
function loadStockAlerts(productsData) {
    const container = document.getElementById('low-stock-list');
    
    // 分類產品：Out of Stock 和 Low Stock
    const outOfStockItems = [];
    const lowStockItems = [];
    
    productsData.forEach(product => {
        const stock = product.stock || 0;
        const safetyStock = product.safety_stock || 0;
        
        if (stock === 0) {
            outOfStockItems.push(product);
        } else if (stock <= safetyStock) {
            lowStockItems.push(product);
        }
    });
    
    let html = '';
    
    // 顯示 Out of Stock 項目（紅色警告）
    if (outOfStockItems.length > 0) {
        html += '<h6 class="text-danger mb-2"><i class="fas fa-exclamation-triangle"></i> Out of Stock</h6>';
        outOfStockItems.forEach(item => {
            html += `
                <div class="alert alert-danger alert-dismissible fade show mb-2" role="alert">
                    <strong>${item.sku}</strong> - ${item.name}<br>
                    <small>Current: <span class="text-danger fw-bold">${item.stock || 0}</span> | Safety: ${item.safety_stock || 0}</small>
                </div>
            `;
        });
    }
    
    // 顯示 Low Stock 項目（黃色警告）
    if (lowStockItems.length > 0) {
        html += '<h6 class="text-warning mb-2"><i class="fas fa-exclamation-circle"></i> Low Stock</h6>';
        lowStockItems.forEach(item => {
            html += `
                <div class="alert alert-warning alert-dismissible fade show mb-2" role="alert">
                    <strong>${item.sku}</strong> - ${item.name}<br>
                    <small>Current: <span class="text-warning fw-bold">${item.stock || 0}</span> | Safety: ${item.safety_stock || 0}</small>
                </div>
            `;
        });
    }
    
    // 如果沒有任何警告項目
    if (outOfStockItems.length === 0 && lowStockItems.length === 0) {
        html = '<div class="text-center text-muted">No stock alerts</div>';
    }
    
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
        const response = await fetch(`${API_BASE.inventory}/inventory/products`);
        products = await response.json();
        
        // Initialize filtered products
        filteredProducts = [...products];
        
        // Apply current filters and sorting
        applyFiltersAndSort();
        
    } catch (error) {
        console.error('Error loading products:', error);
        showAlert('Error loading products', 'danger');
    }
}

// Apply filters and sorting, then render
function applyFiltersAndSort() {
    let filtered = [...products];
    
    // Apply status filter
    const statusFilter = document.getElementById('status-filter')?.value || 'all';
    if (statusFilter !== 'all') {
        filtered = filtered.filter(product => {
            const stock = product.stock || 0;
            const safetyStock = product.safety_stock || 0;
            
            if (statusFilter === 'in-stock') {
                // In Stock: 庫存充足 (庫存 > 安全庫存)
                return stock > safetyStock;
            } else if (statusFilter === 'low-stock') {
                // Low Stock: 庫存不足但還有庫存 (0 < 庫存 <= 安全庫存)
                return stock > 0 && stock <= safetyStock;
            } else if (statusFilter === 'out-of-stock') {
                // Out of Stock: 沒有庫存 (庫存 = 0)
                return stock === 0;
            }
            return true;
        });
    }
    
    // Apply search filter
    const searchTerm = document.getElementById('product-search')?.value?.toLowerCase() || '';
    if (searchTerm) {
        filtered = filtered.filter(product => 
            product.sku.toLowerCase().includes(searchTerm) ||
            product.name.toLowerCase().includes(searchTerm)
        );
    }
    
    // Apply sorting
    if (currentSort.field && currentSort.direction !== 'default') {
        filtered.sort((a, b) => {
            let aVal = a[currentSort.field];
            let bVal = b[currentSort.field];
            
            // Handle different data types
            if (currentSort.field === 'price') {
                aVal = parseFloat(aVal) || 0;
                bVal = parseFloat(bVal) || 0;
            } else {
                aVal = String(aVal || '').toLowerCase();
                bVal = String(bVal || '').toLowerCase();
            }
            
            if (aVal < bVal) return currentSort.direction === 'asc' ? -1 : 1;
            if (aVal > bVal) return currentSort.direction === 'asc' ? 1 : -1;
            return 0;
        });
    }
    
    filteredProducts = filtered;
    renderProducts();
}

// Render products table
function renderProducts() {
        const tbody = document.getElementById('products-table');
    if (filteredProducts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No products found</td></tr>';
            return;
        }

        let html = '';
    filteredProducts.forEach((product, index) => {
        const stock = product.stock || 0;
        const safetyStock = product.safety_stock || 0;
        
        let statusClass = '';
        let statusText = '';
        
        if (stock === 0) {
            statusClass = 'bg-danger';
            statusText = 'Out of Stock';
        } else if (stock <= safetyStock) {
            statusClass = 'bg-warning';
            statusText = 'Low Stock';
        } else {
            statusClass = 'bg-success';
            statusText = 'In Stock';
        }
            
            html += `
                <tr>
                <td>${index + 1}</td>
                    <td>${product.sku}</td>
                    <td>${product.name}</td>
                    <td>$${product.price}</td>
                <td class="${stock === 0 ? 'text-danger' : (stock <= safetyStock ? 'text-warning' : '')}">${product.stock || 0}</td>
                    <td>${product.safety_stock || 0}</td>
                <td><span class="badge ${statusClass}">${statusText}</span></td>
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
}

// Sort products
function sortProducts(field) {
    if (currentSort.field === field) {
        // Cycle through: default -> asc -> desc -> default
        if (currentSort.direction === 'asc') {
            currentSort.direction = 'desc';
        } else if (currentSort.direction === 'desc') {
            currentSort.field = null;
            currentSort.direction = 'default';
        }
    } else {
        // New field, start with ascending
        currentSort.field = field;
        currentSort.direction = 'asc';
    }
    
    // Update sort icons
    updateSortIcons();
    
    // Apply sorting
    applyFiltersAndSort();
}

// Update sort icons
function updateSortIcons() {
    // Reset all icons to default (minus)
    document.querySelectorAll('[id$="-icon"]').forEach(icon => {
        icon.className = 'fas fa-minus';
    });
    
    // Set current sort icon
    if (currentSort.field && currentSort.direction !== 'default') {
        const icon = document.getElementById(`sort-${currentSort.field}-icon`);
        if (icon) {
            if (currentSort.direction === 'asc') {
                icon.className = 'fas fa-sort-up';
            } else if (currentSort.direction === 'desc') {
                icon.className = 'fas fa-sort-down';
            }
        }
    }
}

// Filter products by status
function filterProducts() {
    applyFiltersAndSort();
}

// Search products
function searchProducts() {
    applyFiltersAndSort();
}

// Load orders
async function loadOrders() {
    try {
        const response = await fetch(`${API_BASE.orders}/orders/`);
        orders = await response.json();
        
        const tbody = document.getElementById('orders-table');
        if (orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No orders found</td></tr>';
            return;
        }

        let html = '';
        orders.forEach((order, index) => {
            const statusClass = getStatusClass(order.status);
            const createdDate = new Date(order.created_at).toLocaleDateString();
            
            html += `
                <tr>
                    <td>${index + 1}</td>
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
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteOrder(${order.id})">
                            <i class="fas fa-trash"></i>
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
        const response = await fetch(`${API_BASE.inventory}/inventory/products`);
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
        safety_stock: parseInt(document.getElementById('product-safety-stock').value),
        stock: parseInt(document.getElementById('product-stock').value)
    };

    try {
        const response = await fetch(`${API_BASE.inventory}/inventory/products`, {
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
        const response = await fetch(`${API_BASE.orders}/orders/`, {
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
    const adjustmentValue = document.getElementById('adjustment-amount').value;
    const adjustment = parseInt(adjustmentValue);
    
    if (!productId || !adjustmentValue || isNaN(adjustment)) {
        showAlert('Please select a product and enter a valid adjustment amount', 'warning');
        return;
    }

    try {
        const response = await fetch(`${API_BASE.inventory}/inventory/stock/${productId}/adjust`, {
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

// Show edit product modal
function editProduct(id) {
    // 找到要編輯的產品
    const product = products.find(p => p.id === id);
    if (!product) {
        showAlert('Product not found', 'danger');
        return;
    }

    // 填充表單數據
    document.getElementById('edit-product-id').value = product.id;
    document.getElementById('edit-product-sku').value = product.sku;
    document.getElementById('edit-product-name').value = product.name;
    document.getElementById('edit-product-price').value = product.price;
    document.getElementById('edit-product-safety-stock').value = product.safety_stock;

    // 顯示模態框
    const modal = new bootstrap.Modal(document.getElementById('editProductModal'));
    modal.show();
}

// Update product
async function updateProduct() {
    const productId = document.getElementById('edit-product-id').value;
    const productData = {
        name: document.getElementById('edit-product-name').value,
        price: parseFloat(document.getElementById('edit-product-price').value),
        safety_stock: parseInt(document.getElementById('edit-product-safety-stock').value)
    };

    try {
        const response = await fetch(`${API_BASE.inventory}/inventory/products/${productId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(productData)
        });

        if (response.ok) {
            showAlert('Product updated successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('editProductModal')).hide();
            loadProducts();
            loadInventory();
            loadDashboardData(); // 刷新儀表板數據
        } else {
            const error = await response.json();
            showAlert(`Error: ${error.detail || 'Failed to update product'}`, 'danger');
        }
    } catch (error) {
        console.error('Error updating product:', error);
        showAlert('Error updating product', 'danger');
    }
}

async function deleteProduct(id) {
    if (confirm('Are you sure you want to delete this product?')) {
        try {
            const response = await fetch(`${API_BASE.inventory}/inventory/products/${id}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                showAlert('Product deleted successfully', 'success');
                loadProducts();
                loadInventory();
                loadDashboardData(); // 刷新儀表板數據
            } else {
                const error = await response.json();
                showAlert(`Error: ${error.detail || 'Failed to delete product'}`, 'danger');
            }
        } catch (error) {
            console.error('Error deleting product:', error);
            showAlert('Error deleting product', 'danger');
        }
    }
}

// Delete order
async function deleteOrder(id) {
    if (confirm('Are you sure you want to delete this order? This action cannot be undone.')) {
        try {
            const response = await fetch(`${API_BASE.orders}/orders/${id}/delete`, {
                method: 'DELETE'
            });

            if (response.ok) {
                showAlert('Order deleted successfully', 'success');
                loadOrders();
                loadDashboardData(); // 刷新儀表板數據
            } else {
                const error = await response.json();
                showAlert(`Error: ${error.detail || 'Failed to delete order'}`, 'danger');
            }
        } catch (error) {
            console.error('Error deleting order:', error);
            showAlert('Error deleting order', 'danger');
        }
    }
}

// View order details
async function viewOrder(id) {
    try {
        const response = await fetch(`${API_BASE.orders}/orders/${id}`);
        if (!response.ok) {
            throw new Error('Failed to fetch order details');
        }
        
        const order = await response.json();
        
        // Display order details
        const orderDetails = document.getElementById('order-details');
        orderDetails.innerHTML = `
            <div class="row">
                <div class="col-md-6">
                    <h6>Order Information</h6>
                    <table class="table table-sm">
                        <tr>
                            <td><strong>Order ID:</strong></td>
                            <td>#${order.id}</td>
                        </tr>
                        <tr>
                            <td><strong>Status:</strong></td>
                            <td><span class="badge ${getStatusClass(order.status)}">${order.status}</span></td>
                        </tr>
                        <tr>
                            <td><strong>Total:</strong></td>
                            <td>$${order.total}</td>
                        </tr>
                        <tr>
                            <td><strong>Created:</strong></td>
                            <td>${new Date(order.created_at).toLocaleString()}</td>
                        </tr>
                        <tr>
                            <td><strong>Updated:</strong></td>
                            <td>${new Date(order.updated_at).toLocaleString()}</td>
                        </tr>
                        ${order.paid_at ? `
                        <tr>
                            <td><strong>Paid:</strong></td>
                            <td>${new Date(order.paid_at).toLocaleString()}</td>
                        </tr>
                        ` : ''}
                        ${order.shipped_at ? `
                        <tr>
                            <td><strong>Shipped:</strong></td>
                            <td>${new Date(order.shipped_at).toLocaleString()}</td>
                        </tr>
                        ` : ''}
                    </table>
                </div>
                <div class="col-md-6">
                    <h6>Customer Information</h6>
                    <table class="table table-sm">
                        <tr>
                            <td><strong>Name:</strong></td>
                            <td>${order.customer_name}</td>
                        </tr>
                        <tr>
                            <td><strong>Email:</strong></td>
                            <td>${order.customer_email}</td>
                        </tr>
                        <tr>
                            <td><strong>Address:</strong></td>
                            <td>${order.shipping_address || 'N/A'}</td>
                        </tr>
                    </table>
                </div>
            </div>
            
            ${order.notes ? `
            <div class="mt-3">
                <h6>Notes</h6>
                <div class="alert alert-info">
                    <pre style="white-space: pre-wrap; margin: 0;">${order.notes}</pre>
                </div>
            </div>
            ` : ''}
            
            <div class="mt-3">
                <h6>Order Items</h6>
                <div class="table-responsive">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>Product</th>
                                <th>SKU</th>
                                <th>Qty</th>
                                <th>Unit Price</th>
                                <th>Subtotal</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${order.items.map(item => `
                                <tr>
                                    <td>${item.product_name}</td>
                                    <td>${item.product_sku}</td>
                                    <td>${item.qty}</td>
                                    <td>$${item.unit_price}</td>
                                    <td>$${item.subtotal}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                        <tfoot>
                            <tr class="table-active">
                                <th colspan="4">Total</th>
                                <th>$${order.total}</th>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            </div>
        `;
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('viewOrderModal'));
        modal.show();
        
    } catch (error) {
        console.error('Error loading order details:', error);
        showAlert('Error loading order details', 'danger');
    }
}

// Update order status
async function updateOrderStatus(id) {
    try {
        // Get current order details
        const response = await fetch(`${API_BASE.orders}/orders/${id}`);
        if (!response.ok) {
            throw new Error('Failed to fetch order details');
        }
        
        const order = await response.json();
        
        // Get valid transitions for current status
        const workflowResponse = await fetch(`${API_BASE.orders}/orders/${id}/workflow`);
        if (!workflowResponse.ok) {
            throw new Error('Failed to fetch workflow information');
        }
        
        const workflow = await workflowResponse.json();
        
        // Populate form
        document.getElementById('update-order-id').value = order.id;
        document.getElementById('current-status').value = order.status;
        
        // Populate status options
        const statusSelect = document.getElementById('new-status');
        statusSelect.innerHTML = '<option value="">Select new status...</option>';
        
        workflow.valid_transitions.forEach(status => {
            const option = document.createElement('option');
            option.value = status;
            option.textContent = status;
            statusSelect.appendChild(option);
        });
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('updateOrderStatusModal'));
        modal.show();
        
    } catch (error) {
        console.error('Error loading order status update:', error);
        showAlert('Error loading order status update', 'danger');
    }
}

// Confirm update order status
async function confirmUpdateOrderStatus() {
    const orderId = document.getElementById('update-order-id').value;
    const newStatus = document.getElementById('new-status').value;
    const notes = document.getElementById('status-notes').value;
    
    if (!newStatus) {
        showAlert('Please select a new status', 'warning');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE.orders}/orders/${orderId}/status`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                status: newStatus,
                notes: notes || null
            })
        });
        
        if (response.ok) {
            showAlert('Order status updated successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('updateOrderStatusModal')).hide();
            loadOrders(); // Refresh orders list
        } else {
            const error = await response.json();
            showAlert(`Error: ${error.detail || 'Failed to update order status'}`, 'danger');
        }
    } catch (error) {
        console.error('Error updating order status:', error);
        showAlert('Error updating order status', 'danger');
    }
}

// ==================== REPORTS FUNCTIONALITY ====================

// Load reports data
async function loadReports() {
    try {
        // Load both inventory and order reports in parallel
        await Promise.all([
            loadInventoryReport(),
            loadOrderReport()
        ]);
    } catch (error) {
        console.error('Error loading reports:', error);
        showAlert('Error loading reports', 'danger');
    }
}

// Load inventory report
async function loadInventoryReport() {
    try {
        const [productsRes, lowStockRes] = await Promise.all([
            fetch(`${API_BASE.inventory}/inventory/products`),
            fetch(`${API_BASE.inventory}/inventory/low-stock`)
        ]);

        const products = await productsRes.json();
        const lowStockProducts = await lowStockRes.json();

        // Calculate inventory statistics
        const totalValue = products.reduce((sum, product) => {
            const stock = product.stock || 0;
            const price = product.price || 0;
            return sum + stock * price;
        }, 0);
        const totalProducts = products.length;
        const outOfStockCount = products.filter(p => (p.stock || 0) === 0).length;
        const lowStockCount = products.filter(p => {
            const stock = p.stock || 0;
            const safetyStock = p.safety_stock || 0;
            return stock > 0 && stock <= safetyStock;
        }).length;
        const inStockCount = totalProducts - outOfStockCount - lowStockCount;

        // Calculate inventory turnover (simplified - based on orders)
        const ordersRes = await fetch(`${API_BASE.orders}/orders/`);
        const orders = await ordersRes.json();
        const totalOrderValue = orders.reduce((sum, order) => sum + (order.total || 0), 0);
        const turnoverRate = totalValue > 0 ? (totalOrderValue / totalValue).toFixed(2) : 0;

        // Generate inventory report HTML
        const inventoryReport = document.getElementById('inventory-report');
        inventoryReport.innerHTML = `
            <div class="row">
                <div class="col-12">
                    <h6 class="text-primary mb-3">Inventory Overview</h6>
                    <div class="row mb-3">
                        <div class="col-6">
                            <div class="card bg-light">
                                <div class="card-body text-center">
                                    <h5 class="card-title text-success">$${totalValue.toLocaleString()}</h5>
                                    <p class="card-text small">Total Inventory Value</p>
                                </div>
                            </div>
                        </div>
                        <div class="col-6">
                            <div class="card bg-light">
                                <div class="card-body text-center">
                                    <h5 class="card-title text-info">${totalProducts}</h5>
                                    <p class="card-text small">Total Products</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="row">
                <div class="col-12">
                    <h6 class="text-primary mb-3">Inventory Status Distribution</h6>
                    <div style="height: 300px; position: relative;">
                        <canvas id="inventoryStatusChart"></canvas>
                    </div>
                </div>
            </div>
            
            <div class="row mt-3">
                <div class="col-12">
                    <h6 class="text-primary mb-3">Inventory Turnover Rate</h6>
                    <div class="alert alert-info">
                        <strong>Turnover Rate:</strong> ${turnoverRate}x
                        <br><small class="text-muted">Based on Total Order Value / Total Inventory Value</small>
                    </div>
                </div>
            </div>
            
            <div class="row mt-3">
                <div class="col-12">
                    <h6 class="text-danger mb-3">Out of Stock</h6>
                    <div class="table-responsive">
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>Product Name</th>
                                    <th>SKU</th>
                                    <th>Current Stock</th>
                                    <th>Safety Stock</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${lowStockProducts.filter(product => {
                                    const currentStock = product.current_stock || product.stock || 0;
                                    return currentStock === 0;
                                }).slice(0, 5).map(product => {
                                    const currentStock = product.current_stock || product.stock || 0;
                                    const safetyStock = product.safety_stock || 0;
                                    
                                    return `
                                        <tr class="table-danger">
                                            <td>${product.name}</td>
                                            <td>${product.sku}</td>
                                            <td>${currentStock}</td>
                                            <td>${safetyStock}</td>
                                        </tr>
                                    `;
                                }).join('')}
                                ${lowStockProducts.filter(product => {
                                    const currentStock = product.current_stock || product.stock || 0;
                                    return currentStock === 0;
                                }).length === 0 ? `
                                    <tr>
                                        <td colspan="4" class="text-center text-muted">No out of stock products</td>
                                    </tr>
                                ` : ''}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <div class="row mt-3">
                <div class="col-12">
                    <h6 class="text-warning mb-3">Low Stock Alerts</h6>
                    <div class="table-responsive">
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>Product Name</th>
                                    <th>SKU</th>
                                    <th>Current Stock</th>
                                    <th>Safety Stock</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${lowStockProducts.filter(product => {
                                    const currentStock = product.current_stock || product.stock || 0;
                                    const safetyStock = product.safety_stock || 0;
                                    return currentStock > 0 && currentStock <= safetyStock;
                                }).slice(0, 5).map(product => {
                                    const currentStock = product.current_stock || product.stock || 0;
                                    const safetyStock = product.safety_stock || 0;
                                    
                                    return `
                                        <tr class="table-warning">
                                            <td>${product.name}</td>
                                            <td>${product.sku}</td>
                                            <td>${currentStock}</td>
                                            <td>${safetyStock}</td>
                                        </tr>
                                    `;
                                }).join('')}
                                ${lowStockProducts.filter(product => {
                                    const currentStock = product.current_stock || product.stock || 0;
                                    const safetyStock = product.safety_stock || 0;
                                    return currentStock > 0 && currentStock <= safetyStock;
                                }).length === 0 ? `
                                    <tr>
                                        <td colspan="4" class="text-center text-muted">No low stock products</td>
                                    </tr>
                                ` : ''}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        // Create inventory status chart
        createInventoryStatusChart(inStockCount, lowStockCount, outOfStockCount);

    } catch (error) {
        console.error('Error loading inventory report:', error);
        document.getElementById('inventory-report').innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle"></i> Error loading inventory report
            </div>
        `;
    }
}

// Load order report
async function loadOrderReport() {
    try {
        const ordersRes = await fetch(`${API_BASE.orders}/orders/`);
        const orders = await ordersRes.json();

        // Calculate order statistics
        const totalOrders = orders.length;
        const totalRevenue = orders.reduce((sum, order) => sum + (order.total || 0), 0);
        const avgOrderValue = totalOrders > 0 ? (totalRevenue / totalOrders).toFixed(2) : 0;

        // Order status distribution
        const statusCounts = orders.reduce((acc, order) => {
            acc[order.status] = (acc[order.status] || 0) + 1;
            return acc;
        }, {});

        // Customer statistics
        const customerOrders = orders.reduce((acc, order) => {
            const customer = order.customer_name;
            if (!acc[customer]) {
                acc[customer] = { count: 0, total: 0 };
            }
            acc[customer].count++;
            acc[customer].total += order.total || 0;
            return acc;
        }, {});

        const topCustomers = Object.entries(customerOrders)
            .sort((a, b) => b[1].total - a[1].total)
            .slice(0, 5);

        // Generate order report HTML
        const orderReport = document.getElementById('order-report');
        orderReport.innerHTML = `
            <div class="row">
                <div class="col-12">
                    <h6 class="text-primary mb-3">Order Overview</h6>
                    <div class="row mb-3">
                        <div class="col-6">
                            <div class="card bg-light">
                                <div class="card-body text-center">
                                    <h5 class="card-title text-success">$${totalRevenue.toLocaleString()}</h5>
                                    <p class="card-text small">Total Revenue</p>
                                </div>
                            </div>
                        </div>
                        <div class="col-6">
                            <div class="card bg-light">
                                <div class="card-body text-center">
                                    <h5 class="card-title text-info">${totalOrders}</h5>
                                    <p class="card-text small">Total Orders</p>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="row mb-3">
                        <div class="col-12">
                            <div class="card bg-light">
                                <div class="card-body text-center">
                                    <h5 class="card-title text-warning">$${avgOrderValue}</h5>
                                    <p class="card-text small">Average Order Value</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="row">
                <div class="col-12">
                    <h6 class="text-primary mb-3">Order Status Distribution</h6>
                    <div style="height: 250px; position: relative;">
                        <canvas id="orderStatusChart"></canvas>
                    </div>
                </div>
            </div>
            
            <div class="row mt-3">
                <div class="col-12">
                    <h6 class="text-primary mb-3">Top Customers</h6>
                    <div class="table-responsive">
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>Customer Name</th>
                                    <th>Order Count</th>
                                    <th>Total Spent</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${topCustomers.map(([customer, data]) => `
                                    <tr>
                                        <td>${customer}</td>
                                        <td>${data.count}</td>
                                        <td>$${data.total.toFixed(2)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        // Create order status chart
        createOrderStatusChart(statusCounts);

    } catch (error) {
        console.error('Error loading order report:', error);
        document.getElementById('order-report').innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle"></i> Error loading order report
            </div>
        `;
    }
}

// Create inventory status chart
function createInventoryStatusChart(inStock, lowStock, outOfStock) {
    const ctx = document.getElementById('inventoryStatusChart').getContext('2d');
    
    // Destroy existing chart if it exists
    if (charts.inventoryStatus) {
        charts.inventoryStatus.destroy();
    }

    charts.inventoryStatus = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['In Stock', 'Low Stock', 'Out of Stock'],
            datasets: [{
                data: [inStock, lowStock, outOfStock],
                backgroundColor: [
                    'rgba(40, 167, 69, 0.8)',
                    'rgba(255, 193, 7, 0.8)',
                    'rgba(220, 53, 69, 0.8)'
                ],
                borderColor: [
                    'rgba(40, 167, 69, 1)',
                    'rgba(255, 193, 7, 1)',
                    'rgba(220, 53, 69, 1)'
                ],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
}

// Create order status chart
function createOrderStatusChart(statusCounts) {
    const ctx = document.getElementById('orderStatusChart').getContext('2d');
    
    // Destroy existing chart if it exists
    if (charts.orderStatus) {
        charts.orderStatus.destroy();
    }

    const statusLabels = {
        'CREATED': 'Created',
        'PAID': 'Paid',
        'PICKING': 'Picking',
        'SHIPPED': 'Shipped',
        'CANCELLED': 'Cancelled'
    };

    const labels = Object.keys(statusCounts).map(status => statusLabels[status] || status);
    const data = Object.values(statusCounts);
    const colors = [
        'rgba(54, 162, 235, 0.8)',
        'rgba(40, 167, 69, 0.8)',
        'rgba(255, 193, 7, 0.8)',
        'rgba(23, 162, 184, 0.8)',
        'rgba(220, 53, 69, 0.8)'
    ];

    charts.orderStatus = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Order Count',
                data: data,
                backgroundColor: colors.slice(0, labels.length),
                borderColor: colors.slice(0, labels.length).map(color => color.replace('0.8', '1')),
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
}