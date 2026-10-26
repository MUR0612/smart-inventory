# Local-only manifests (Docker Desktop)

`metrics-server-insecure-tls*.yaml` run metrics-server with `--kubelet-insecure-tls`, because
Docker Desktop's kubelet certificate cannot be verified. That **disables TLS verification**
between metrics-server and the kubelet. Use it only on a single-user local cluster to make the
HPA demo work there.

Never apply these to GKE or any shared cluster. GKE (and k3s) ship their own metrics server, and
no overlay references this directory.
