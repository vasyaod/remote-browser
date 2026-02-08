#!/usr/bin/env python3
"""
HTTP proxy for Chrome DevTools with Basic Authentication.
"""
import os
import sys
import base64
import http.server
import socketserver
import urllib.request
import urllib.parse

class AuthProxyHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.target_host = kwargs.pop('target_host', '127.0.0.1')
        self.target_port = kwargs.pop('target_port', 9223)
        self.auth_token = kwargs.pop('auth_token', None)
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if not self.authenticate():
            self.send_auth_required()
            return
        
        self.proxy_request()
    
    def do_POST(self):
        if not self.authenticate():
            self.send_auth_required()
            return
        
        self.proxy_request()
    
    def do_PUT(self):
        if not self.authenticate():
            self.send_auth_required()
            return
        
        self.proxy_request()
    
    def do_DELETE(self):
        if not self.authenticate():
            self.send_auth_required()
            return
        
        self.proxy_request()
    
    def do_HEAD(self):
        if not self.authenticate():
            self.send_auth_required()
            return
        
        self.proxy_request()
    
    def authenticate(self):
        if not self.auth_token:
            return True  # No auth required if token not set
        
        auth_header = self.headers.get('Authorization', '')
        if not auth_header.startswith('Basic '):
            return False
        
        try:
            encoded = auth_header.split(' ', 1)[1]
            decoded = base64.b64decode(encoded).decode('utf-8')
            username, password = decoded.split(':', 1)
            
            # Support both "token" as username with password, or just password
            if username == 'token' and password == self.auth_token:
                return True
            if username == '' and password == self.auth_token:
                return True
            if password == self.auth_token:
                return True
        except:
            pass
        
        return False
    
    def send_auth_required(self):
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Chrome DevTools"')
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<html><body><h1>401 Unauthorized</h1></body></html>')
    
    def proxy_request(self):
        target_url = f'http://{self.target_host}:{self.target_port}{self.path}'
        
        try:
            # Create request
            req = urllib.request.Request(target_url)
            
            # Copy headers (except Host and Authorization)
            for header, value in self.headers.items():
                if header.lower() not in ('host', 'authorization', 'connection'):
                    req.add_header(header, value)
            
            # Handle request body for POST/PUT
            if self.command in ('POST', 'PUT'):
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    req.data = self.rfile.read(content_length)
            
            # Make request
            with urllib.request.urlopen(req) as response:
                # Send response headers
                self.send_response(response.getcode())
                for header, value in response.headers.items():
                    if header.lower() not in ('connection', 'transfer-encoding'):
                        self.send_header(header, value)
                self.end_headers()
                
                # Send response body
                self.wfile.write(response.read())
        
        except Exception as e:
            self.send_error(502, f"Proxy error: {str(e)}")
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

def main():
    listen_port = int(os.environ.get('EXTERNAL_DEBUG_PORT', '9222'))
    target_host = os.environ.get('INTERNAL_DEBUG_HOST', '127.0.0.1')
    target_port = int(os.environ.get('INTERNAL_DEBUG_PORT', '9223'))
    auth_token = os.environ.get('DEVTOOLS_TOKEN', None)
    
    if auth_token:
        print(f"DevTools proxy started on port {listen_port} with authentication")
    else:
        print(f"DevTools proxy started on port {listen_port} without authentication")
    
    handler = lambda *args, **kwargs: AuthProxyHandler(
        *args,
        target_host=target_host,
        target_port=target_port,
        auth_token=auth_token,
        **kwargs
    )
    
    with socketserver.TCPServer(("0.0.0.0", listen_port), handler) as httpd:
        httpd.serve_forever()

if __name__ == '__main__':
    main()

