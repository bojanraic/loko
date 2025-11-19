#!/bin/sh

# Loko test app entrypoint
APP_INFO="<p><strong>Description:</strong> Loko Test App for Registry and TLS Validation</p>"

# Get namespace from service account mount (standard Kubernetes)
NAMESPACE="unknown"
if [ -f "/var/run/secrets/kubernetes.io/serviceaccount/namespace" ]; then
    NAMESPACE=$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)
fi

# Deployment info
DEPLOYMENT_INFO=""
if [ -n "$KUBERNETES_SERVICE_HOST" ]; then
    DEPLOYMENT_INFO="<p><strong>Deployment:</strong> Running in your local Kubernetes cluster</p>"
fi


cat > /www/index.html <<EOF
<html>
<head>
    <meta charset="utf-8">
    <title>Loko Test App - Registry & TLS Validation</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; color: #333; transition: background-color 0.3s ease, color 0.3s ease; }
        .container { background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: background-color 0.3s ease, box-shadow 0.3s ease; }
        h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; transition: color 0.3s ease, border-color 0.3s ease; }
        .info { background-color: #ecf0f1; padding: 15px; border-radius: 5px; margin: 10px 0; transition: background-color 0.3s ease; }
        .chart-info { background-color: #e8f5e8; border-left: 4px solid #27ae60; }
        .pod-info { background-color: #fff3cd; border-left: 4px solid #ffc107; }
        .success { background-color: #d4edda; border-left: 4px solid #28a745; }

        /* Dark mode styles */
        @media (prefers-color-scheme: dark) {
            body { background-color: #1a1a1a; color: #e0e0e0; }
            .container { background-color: #2d2d2d; box-shadow: 0 2px 4px rgba(0,0,0,0.3); }
            h1 { color: #74c0fc; border-bottom-color: #74c0fc; }
            .info { background-color: #404040; }
            .chart-info { background-color: #1e3a1e; border-left-color: #4caf50; }
            .pod-info { background-color: #3d3317; border-left-color: #ffeb3b; }
            .success { background-color: #1e3a1e; border-left-color: #4caf50; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>&#x2705; Loko Test App - Validation Successful!</h1>
        
        <div class="info success">
            <h3>Validation Status</h3>
            <p>&#x2705; <strong>Registry:</strong> Image successfully pulled from local registry</p>
            <p>&#x2705; <strong>TLS:</strong> HTTPS certificate working correctly</p>
            <p>&#x2705; <strong>Ingress:</strong> Traefik routing configured properly</p>
        </div>
        
        <div class="info">
            <h3>Registry Information</h3>
            <p>This Kubernetes workload is running an image hosted in the local container registry within the cluster.</p>
            <p>The image was built and pushed during the validation process.</p>
        </div>
        
        <div class="info chart-info">
            <h3>Deployment Information</h3>
            $APP_INFO
            <p><strong>Namespace:</strong> $NAMESPACE</p>
            $DEPLOYMENT_INFO
        </div>
        
        <div class="info pod-info">
            <h3>Pod Information</h3>
            <p><strong>Pod Name:</strong> $HOSTNAME</p>
            <p><strong>Image Tag:</strong> ${IMAGE_TAG:-latest}</p>
        </div>
    </div>
</body>
</html>
EOF

httpd -f -h /www
