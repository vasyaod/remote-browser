# Kubernetes Deployment

Example Kubernetes deployment configuration for the Remote Browser container.

## Deployment Example

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: remote-browser
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: remote-browser
  namespace: remote-browser
  labels:
    app: remote-browser
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: remote-browser
  template:
    metadata:
      labels:
        app: remote-browser
    spec:
      hostNetwork: true
      containers:
      - name: remote-browser
        image: vasiliiv/remote-browser:latest
        imagePullPolicy: Always
        env:
        - name: VNC_RESOLUTION
          value: "1920x1080x24"
        - name: VNC_PASSWORD
          valueFrom:
            secretKeyRef:
              name: vnc-password
              key: password
        - name: SESSION_DATA_PATH
          value: "/session-data"
        ports:
        - name: debug
          containerPort: 9222
          hostPort: 9222
        - name: vnc
          containerPort: 5900
          hostPort: 5900
        volumeMounts:
        - name: session-data
          mountPath: /session-data
        securityContext:
          privileged: true
      volumes:
      - name: session-data
        hostPath:
          path: /data/session-data
          type: DirectoryOrCreate
---
apiVersion: v1
kind: Service
metadata:
  name: remote-browser
  namespace: remote-browser
  labels:
    app: remote-browser
spec:
  selector:
    app: remote-browser
  ports:
  - name: debug
    protocol: TCP
    port: 9222
    targetPort: 9222
  - name: vnc
    protocol: TCP
    port: 5900
    targetPort: 5900
  type: ClusterIP
```

## VNC Password Secret

Create a secret for the VNC password:

```bash
kubectl create namespace remote-browser
kubectl create secret generic vnc-password \
  --from-literal=password=your-secure-password \
  -n remote-browser
```

## Apply the Deployment

Save the YAML configuration above to a file (e.g., `k8s-deployment.yaml`) and apply it:

```bash
kubectl apply -f k8s-deployment.yaml
```

## Access the Services

- **Chrome DevTools**: `http://<node-ip>:9222`
- **VNC Server**: Connect to `<node-ip>:5900` using any VNC client

## Notes

- The deployment uses `hostNetwork: true` to expose ports directly on the node
- `privileged: true` is required for Chromium to run in containers
- Session data is persisted to `/data/session-data` on the host
- The deployment uses `Recreate` strategy since only one replica is supported

