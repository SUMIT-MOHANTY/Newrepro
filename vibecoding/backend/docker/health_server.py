#!/usr/bin/env python3
"""
Lightweight health check server that runs on a separate port.
This server starts immediately and reports the health status of the main application.
"""
import os
import sys
import socket
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for health checks"""
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass
    
    def do_GET(self):
        """Handle GET requests to /health"""
        if self.path == '/health':
            # Check if the main application port is open
            main_port = int(os.environ.get('PORT', '8080'))
            is_healthy = self.check_port_open(main_port)
            
            if is_healthy:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = '{"status": "healthy", "port": %d}\n' % main_port
                self.wfile.write(response.encode())
            else:
                self.send_response(503)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = '{"status": "unhealthy", "reason": "main application not ready", "port": %d}\n' % main_port
                self.wfile.write(response.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def check_port_open(self, port, timeout=0.5):
        """Check if a port is open and accepting connections"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            return result == 0
        except:
            return False


def start_health_server(port=9090):
    """Start the health check server on the specified port"""
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        print(f"🏥 Health check server running on port {port}", flush=True)
        server.serve_forever()
    except Exception as e:
        print(f"❌ Health server failed: {e}", flush=True)
        sys.exit(1)


if __name__ == '__main__':
    health_port = int(os.environ.get('HEALTH_PORT', '9090'))
    start_health_server(health_port)
