"""
Helpers for the proxy tests: a fake authenticated upstream proxy and port utils.
"""
import socket
import threading
import time


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_listening(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


def read_head(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    return head, rest


class FakeUpstream:
    """An upstream HTTP proxy that records every request head it receives.

    CONNECT -> `connect_status`, then echoes the tunnel back upper-cased.
    Anything else -> a fixed 200 response, then closes.
    """

    def __init__(self, connect_status=b"200 Connection established"):
        self.connect_status = connect_status
        self.heads = []
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        with conn:
            head, rest = read_head(conn)
            self.heads.append(head)
            if head.startswith(b"CONNECT "):
                conn.sendall(b"HTTP/1.1 " + self.connect_status + b"\r\n\r\n")
                if not self.connect_status.startswith(b"2"):
                    return
                data = rest
                while True:
                    if data:
                        conn.sendall(data.upper())
                    data = conn.recv(4096)
                    if not data:
                        return
            else:
                body = b"hello from upstream"
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n"
                             % len(body) + body)

    def close(self):
        self.sock.close()


def header_values(head, name):
    name = name.lower().encode() + b":"
    return [line.split(b":", 1)[1].strip() for line in head.split(b"\r\n")[1:]
            if line.lower().startswith(name)]
