from http.server import BaseHTTPRequestHandler, HTTPServer
import os

class MetricReceiver(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        client_ip = self.client_address[0]
        # Clean up IPv6 local loopback string if it appears
        if client_ip == "::1": 
            client_ip = "127.0.0.1"
        
        # Save the log to our Windows path
        log_path = f"C:\\CustomMonitor\\logs\\{client_ip}.log"
        with open(log_path, "w") as f:
            f.write(post_data)
            
        print(f"[SUCCESS] Received data from {client_ip}")
        self.send_response(200)
        self.end_headers()

if __name__ == "__main__":
    server = HTTPServer(('0.0.0.0', 8080), MetricReceiver)
    print("Local Receiver running on http://127.0.0.1:8080...")
    print("Press Ctrl+C to stop the server.")
    server.serve_forever()