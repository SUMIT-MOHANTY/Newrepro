from flask import Flask, request, Response
import requests
import os
import json
from pathlib import Path

app = Flask(__name__)

# Load project → port mapping from project_manager's container registry
ARTIFACTS_DIR = Path(os.getenv('ARTIFACTS_DIR', './artifacts'))

def get_container_port(project_id: str) -> str:
    """Get the container port for a project by reading its container info"""
    try:
        # Check running containers registry
        registry_file = ARTIFACTS_DIR / '.container_registry.json'
        print(f"Looking for registry at: {registry_file}")
        print(f"Registry exists: {registry_file.exists()}")
        
        if registry_file.exists():
            with open(registry_file, 'r') as f:
                registry = json.load(f)
                print(f"Registry contents: {registry}")
                container_name = f"vibecoding_{project_id}"
                print(f"Looking for container: {container_name}")
                if container_name in registry:
                    return registry[container_name]['port']
    except Exception as e:
        print(f"Error reading container registry: {e}")
    print(f"No port found for project_id: {project_id}")
    return None

def proxy_request(target_base: str):
    """Generic proxy handler"""
    # Construct target URL
    path = request.path
    token_prefix = "/vibecoding/app/" + request.view_args.get("token")
    forward_path = path.replace(token_prefix, "", 1)
    target_url = target_base + forward_path
    
    # Forward query params
    if request.query_string:
        target_url += "?" + request.query_string.decode()
    
    # Forward headers (excluding host)
    headers = {
        key: value
        for key, value in request.headers
        if key.lower() not in ["host", "x-forwarded-for", "x-forwarded-proto"]
    }
    
    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=(5, 30)  # connect, read timeouts
        )
        
        excluded_headers = [
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection"
        ]
        
        response_headers = [
            (name, value)
            for name, value in resp.raw.headers.items()
            if name.lower() not in excluded_headers
        ]
        
        return Response(
            resp.content,
            resp.status_code,
            response_headers
        )
    except requests.exceptions.RequestException as e:
        return Response(f"Proxy Error: {str(e)}", status=502)

@app.route("/vibecoding/app/<token>/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@app.route("/vibecoding/app/<token>/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def route_proxy(token, path):
    """Route requests to the appropriate container based on project token"""
    # Get container port for this project
    port = get_container_port(token)
    print(port)
    if not port:
        return Response(
            f"Project '{token}' not found or container not running",
            status=404
        )
    
    target = f"http://127.0.0.1:{port}"
    return proxy_request(target)

@app.route("/health")
def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "preview-proxy"}

@app.route("/")
def home():
    """Root endpoint showing service info"""
    return "VibeCoding Preview Proxy - Use /app/{project_id}/ to access previews"

if __name__ == "__main__":
    # For production, use gunicorn:
    # gunicorn -w 4 -b 0.0.0.0:80 preview_proxy:app
    app.run(host="0.0.0.0", port=80)
