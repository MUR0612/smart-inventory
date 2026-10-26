"""Code shared by inventory-service and order-service (config, auth, logging).

Both service images copy this package next to their own ``app`` package, so
the configuration contract and authentication rules stay identical.
"""
