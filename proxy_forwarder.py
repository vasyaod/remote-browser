#!/usr/bin/env python3
"""
Local HTTP proxy forwarder for an authenticated upstream proxy.

Chromium cannot take user:pass in --proxy-server, so start.sh points it at this
forwarder on 127.0.0.1 and the forwarder adds `Proxy-Authorization: Basic` on
every request it relays to the upstream named by PROXY_URL
(http://<user>:<pass>@host:port, URL-encoded userinfo).

PROXY_URL is a credential: it is read from the environment only (never argv) and
neither it nor the derived header is ever logged. Log lines name the upstream by
host:port only.

- CONNECT host:port  -> upstream CONNECT with auth, then a raw tunnel.
- GET http://...     -> forwarded to the upstream with auth and `Connection: close`,
                        so a reused client connection can never carry a second
                        request past the header rewrite.

Fail closed: if the upstream is unreachable or refuses, the client gets a 502
and nothing is ever sent directly.
"""
import asyncio
import base64
import os
import sys
from urllib.parse import unquote, urlsplit

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.environ.get("PROXY_FORWARDER_PORT", "3128"))
HEADER_LIMIT = 64 * 1024
CONNECT_TIMEOUT = 30
# Headers a client may send to *this* proxy that must not reach the upstream.
HOP_HEADERS = {b"proxy-authorization", b"proxy-connection", b"connection", b"keep-alive"}


def log(msg):
    print(f"[proxy-forwarder] {msg}", flush=True)


def parse_upstream(url):
    """Return (host, port, auth_header_value_or_None). Never echoes the URL."""
    try:
        parts = urlsplit(url)
        host, port = parts.hostname, parts.port
    except ValueError:
        raise SystemExit("[proxy-forwarder] PROXY_URL is not a valid URL") from None
    if parts.scheme != "http":
        raise SystemExit("[proxy-forwarder] PROXY_URL must be an http:// URL")
    if not host or not port:
        raise SystemExit("[proxy-forwarder] PROXY_URL must name a host and a port")
    auth = None
    if parts.username is not None:
        cred = f"{unquote(parts.username)}:{unquote(parts.password or '')}"
        auth = b"Basic " + base64.b64encode(cred.encode("utf-8"))
    return host, port, auth


async def read_head(reader):
    """Read an HTTP head (start line + headers) up to and including CRLFCRLF."""
    return await reader.readuntil(b"\r\n\r\n")


def split_head(head):
    lines = head[:-4].split(b"\r\n")
    return lines[0], lines[1:]


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            if writer.can_write_eof():
                writer.write_eof()
        except (OSError, RuntimeError):
            pass


async def relay(a_reader, a_writer, b_reader, b_writer):
    await asyncio.gather(pipe(a_reader, b_writer), pipe(b_reader, a_writer))


async def reply(writer, status, reason):
    body = f"{status} {reason}\n".encode()
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/plain\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
    )
    try:
        await writer.drain()
    except ConnectionError:
        pass


class Forwarder:
    def __init__(self, host, port, auth):
        self.host, self.port, self.auth = host, port, auth

    def auth_lines(self):
        return [b"Proxy-Authorization: " + self.auth] if self.auth else []

    async def open_upstream(self):
        return await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT
        )

    async def handle(self, reader, writer):
        up_writer = None
        try:
            try:
                head = await read_head(reader)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
                return
            start, headers = split_head(head)
            fields = start.split(b" ")
            if len(fields) != 3:
                await reply(writer, 400, "Bad Request")
                return
            method, target, version = fields
            try:
                up_reader, up_writer = await self.open_upstream()
            except (OSError, asyncio.TimeoutError) as e:
                log(f"upstream {self.host}:{self.port} unreachable: {type(e).__name__}")
                await reply(writer, 502, "Bad Gateway")
                return
            if method.upper() == b"CONNECT":
                await self.tunnel(target, reader, writer, up_reader, up_writer)
            else:
                await self.forward(method, target, version, headers,
                                   reader, writer, up_reader, up_writer)
        except Exception as e:  # never let one client take the forwarder down
            log(f"connection error: {type(e).__name__}")
        finally:
            for w in (up_writer, writer):
                if w is not None:
                    w.close()

    async def tunnel(self, target, reader, writer, up_reader, up_writer):
        up_writer.write(
            b"\r\n".join([b"CONNECT " + target + b" HTTP/1.1", b"Host: " + target]
                         + self.auth_lines()) + b"\r\n\r\n"
        )
        await up_writer.drain()
        try:
            resp = await asyncio.wait_for(read_head(up_reader), CONNECT_TIMEOUT)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError,
                asyncio.TimeoutError, ConnectionError):
            await reply(writer, 502, "Bad Gateway")
            return
        status_line, _ = split_head(resp)
        parts = status_line.split(b" ", 2)
        status = parts[1] if len(parts) > 1 else b""
        if not status.startswith(b"2"):
            # A 407 relayed as-is would make Chromium prompt for proxy credentials;
            # the upstream's refusal is a gateway error from the browser's view.
            log(f"upstream refused CONNECT: {status.decode('ascii', 'replace')}")
            await reply(writer, 502, "Bad Gateway")
            return
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        await relay(reader, writer, up_reader, up_writer)

    async def forward(self, method, target, version, headers,
                      reader, writer, up_reader, up_writer):
        kept = [h for h in headers
                if h.split(b":", 1)[0].strip().lower() not in HOP_HEADERS]
        up_writer.write(
            b"\r\n".join([b" ".join([method, target, version])] + kept
                         + self.auth_lines() + [b"Connection: close"]) + b"\r\n\r\n"
        )
        await up_writer.drain()
        # The request body (if any) and the whole response stream through; the
        # upstream closes after one response because of Connection: close.
        await relay(reader, writer, up_reader, up_writer)


async def main():
    url = os.environ.get("PROXY_URL", "")
    if not url:
        raise SystemExit("[proxy-forwarder] PROXY_URL is empty")
    host, port, auth = parse_upstream(url)
    del url
    os.environ.pop("PROXY_URL", None)
    fwd = Forwarder(host, port, auth)
    server = await asyncio.start_server(fwd.handle, LISTEN_HOST, LISTEN_PORT,
                                        limit=HEADER_LIMIT)
    log(f"listening on {LISTEN_HOST}:{LISTEN_PORT}, upstream {host}:{port}"
        f" ({'with' if auth else 'without'} credentials)")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
