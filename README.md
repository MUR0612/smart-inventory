# Smart Inventory

Smart Inventory is a containerized inventory and order management system built with FastAPI microservices, MySQL, Redis, Nginx, Docker Compose, and Kubernetes deployment manifests.

The project models a small manufacturing-style inventory workflow: products are stored in an inventory service, orders are processed through an order service, stock is reserved and released through service-to-service communication, and low-stock events are published through Redis.

This project demonstrates backend service design, database-backed APIs, microservice communication, container orchestration, reverse proxy configuration, and deployment workflow for manufacturing or warehouse-style systems.

## Features

- Product CRUD APIs
- Inventory stock adjustment APIs
- Low-stock detection based on safety stock thresholds
- Order creation with inventory availability checks
- Stock reservation and release during order workflows
- Order status workflow management
- Redis Pub/Sub events for stock changes and low-stock alerts
- MySQL persistence with SQLAlchemy ORM
- Nginx reverse proxy for frontend and backend API routing
- Docker Compose local deployment
- Kubernetes manifests for service deployment, ingress, config, health checks, and autoscaling
- Static frontend dashboard for products, orders, inventory, stock alerts, and reports

## Tech Stack

- Python
- FastAPI
- SQLAlchemy
- MySQL
- Redis
- Nginx
- Docker / Docker Compose
- Kubernetes
- JavaScript / HTML / CSS
- PowerShell / Shell scripts

## System Architecture

```text
Browser UI
   |
   v
Nginx Reverse Proxy
   |
   +-- /api/inventory/* ---> Inventory Service ---> MySQL
   |                              |
   |                              +-- Redis cache / PubSub
   |
   +-- /api/orders/* ------> Order Service -------> MySQL
                                  |
                                  +-- calls Inventory Service
                                  +-- subscribes to Redis events
```

## Project Structure

```text
smart-inventory/
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── inventory-service/
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── routers/
│   │   └── services/
│   ├── Dockerfile
│   └── requirements.txt
├── order-service/
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── routers/
│   │   └── services/
│   ├── Dockerfile
│   └── requirements.txt
├── nginx/
│   └── nginx.conf
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── mysql.yaml
│   ├── redis.yaml
│   ├── inventory-service.yaml
│   ├── order-service.yaml
│   ├── ingress.yaml
│   └── hpa.yaml
└── docker-compose.yml
```

## Services

### Inventory Service

The inventory service owns product and stock data.

Main responsibilities:

- create, list, update, and delete products
- track current stock and safety stock
- adjust stock levels
- detect low-stock items
- publish stock-change and low-stock events through Redis
- cache product list responses with Redis

Example APIs:

```text
GET    /api/inventory/products
POST   /api/inventory/products
GET    /api/inventory/products/{product_id}
PUT    /api/inventory/products/{product_id}
DELETE /api/inventory/products/{product_id}

GET    /api/inventory/stock
GET    /api/inventory/stock/{product_id}
POST   /api/inventory/stock/{product_id}/adjust
GET    /api/inventory/low-stock
```

### Order Service

The order service owns order data and coordinates with the inventory service.

Main responsibilities:

- create orders
- check stock availability before order creation
- reserve stock by calling the inventory service
- release stock when orders are cancelled
- list and retrieve order details
- manage order status transitions
- subscribe to Redis inventory events

Example APIs:

```text
GET    /api/orders/
POST   /api/orders/
GET    /api/orders/{order_id}
PUT    /api/orders/{order_id}
PATCH  /api/orders/{order_id}/status
DELETE /api/orders/{order_id}
GET    /api/orders/{order_id}/workflow
```

## Data Model

Core tables include:

- `products`
- `inventory`
- `orders`
- `order_items`

The product and inventory tables are managed by the inventory service. The order and order item tables are managed by the order service.

## Redis Usage

Redis is used for:

- product list caching
- low-stock alert publishing
- stock-change event publishing
- inventory update event publishing

This adds an event-driven communication path between inventory changes and downstream service behavior.

## Local Development With Docker Compose

Create a local `.env` file:

```env
MYSQL_ROOT_PASSWORD=rootpassword
MYSQL_DATABASE=smart_inventory
MYSQL_USER=inventory_user
MYSQL_PASSWORD=inventory_password
REDIS_HOST=redis
REDIS_PORT=6379
INVENTORY_PORT=8001
ORDER_PORT=8002
```

Start the system:

```bash
docker compose up --build
```

The system runs:

```text
Frontend / Nginx:       http://localhost:8080
Inventory Service API:  http://localhost:8001
Order Service API:      http://localhost:8002
MySQL:                  localhost:3307
Redis:                  localhost:6379
```

Stop the system:

```bash
docker compose down
```

Remove volumes:

```bash
docker compose down -v
```

## Nginx Routing

Nginx serves the frontend and routes backend API traffic:

```text
/api/inventory/*  -> inventory-service:8001
/api/orders/*     -> order-service:8002
/healthz          -> Nginx health check
```

This provides a single browser-facing entry point while keeping backend services separated.

## Kubernetes Deployment

The `k8s/` directory contains deployment manifests and helper scripts for running the system on a Kubernetes cluster.

Included resources:

- namespace
- config maps
- MySQL deployment/service
- Redis deployment/service
- inventory service deployment/service
- order service deployment/service
- ingress
- horizontal pod autoscaler
- deployment and cleanup scripts

Typical deployment flow:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/mysql.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/inventory-service.yaml
kubectl apply -f k8s/order-service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
```

Check deployment status:

```bash
kubectl get pods -n smart-inventory
kubectl get services -n smart-inventory
kubectl get ingress -n smart-inventory
kubectl get hpa -n smart-inventory
```

## Testing And Validation

Suggested local checks:

```bash
docker compose up --build
```

Health checks:

```bash
curl http://localhost:8080/healthz
curl http://localhost:8001/api/healthz
curl http://localhost:8002/api/healthz
```

Kubernetes checks:

```bash
kubectl logs -f deployment/inventory-service -n smart-inventory
kubectl logs -f deployment/order-service -n smart-inventory
kubectl describe pod <pod-name> -n smart-inventory
```

## Security Note

Environment values should be stored in a local `.env` file or Kubernetes Secrets, not committed as real production credentials.

For portfolio use, keep only a `.env.example` file in the repository and add `.env` to `.gitignore`.

## Portfolio Focus

This project demonstrates:

- backend API design with FastAPI
- microservice separation
- service-to-service HTTP communication
- database-backed business workflows
- Redis caching and Pub/Sub events
- containerized local deployment
- Nginx reverse proxy routing
- Kubernetes deployment configuration
- health checks and operational validation
- manufacturing-style inventory/order system modeling

## Resume Summary

Smart Inventory is a containerized microservice-based inventory and order management system using FastAPI, MySQL, Redis, Nginx, Docker Compose, and Kubernetes. It models product management, stock adjustment, low-stock alerts, order creation, inventory reservation, and deployment workflows for manufacturing-style backend systems.

## Future Improvements

- Replace committed `.env` values with `.env.example` and secrets management.
- Add automated API tests for inventory and order workflows.
- Add transaction-safe stock reservation logic for concurrent orders.
- Add authentication and role-based access control.
- Add structured logging and request tracing.
- Add CI checks for Docker builds and service health tests.
- Add frontend build tooling or migrate the dashboard to a modern frontend framework.
