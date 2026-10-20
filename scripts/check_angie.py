"""Real binary integration checks; uses unprivileged ports and temporary state."""

import argparse
import asyncio
import json
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import grpc
import httpx
from aioquic.asyncio import QuicConnectionProtocol, connect
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import DataReceived, HeadersReceived
from aioquic.quic.configuration import QuicConfiguration

from apm.agent import Agent, Deployment
from apm.certificates import install_certificate
from apm.compiler import Compiler
from apm.config import Settings
from apm.schemas import Certificate, Route, Runtime, Stream


class HTTP3Client(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http = H3Connection(self._quic)
        self.body = bytearray()
        self.response = asyncio.get_running_loop().create_future()

    def quic_event_received(self, event):
        for received in self.http.handle_event(event):
            if isinstance(received, DataReceived):
                self.body.extend(received.data)
            if isinstance(received, (HeadersReceived, DataReceived)) and received.stream_ended:
                if not self.response.done():
                    self.response.set_result(bytes(self.body))

    async def get(self):
        stream = self._quic.get_next_available_stream_id()
        self.http.send_headers(
            stream_id=stream,
            headers=[
                (b":method", b"GET"),
                (b":scheme", b"https"),
                (b":authority", b"localhost"),
                (b":path", b"/"),
            ],
            end_stream=True,
        )
        self.transmit()
        return await asyncio.wait_for(self.response, timeout=10)


async def check_http3():
    async with connect(
        "127.0.0.1",
        18443,
        configuration=QuicConfiguration(
            is_client=True, alpn_protocols=H3_ALPN, verify_mode=ssl.CERT_NONE, server_name="localhost"
        ),
        create_protocol=HTTP3Client,
    ) as client:
        assert await client.get() == b"apm-real-upstream"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"apm-real-upstream")

    def log_message(self, *args):
        pass


def item(kind, data, object_id=None):
    return {"id": object_id or str(uuid.uuid4()), "kind": kind, "data": data, "enabled": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--conf-dir", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    backend = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=backend.serve_forever, daemon=True).start()
    grpc_server = grpc.server(ThreadPoolExecutor(max_workers=2))
    grpc_server.add_generic_rpc_handlers(
        [
            grpc.method_handlers_generic_handler(
                "apm.Echo", {"Send": grpc.unary_unary_rpc_method_handler(lambda value, context: value)}
            )
        ]
    )
    grpc_port = grpc_server.add_insecure_port("127.0.0.1:0")
    grpc_server.start()
    tcp = socket.socket()
    tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp.bind(("127.0.0.1", 0))
    tcp.listen()
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("127.0.0.1", 0))

    def tcp_echo():
        while True:
            connection, _ = tcp.accept()
            with connection:
                connection.sendall(connection.recv(1024))

    def udp_echo():
        while True:
            data, address = udp.recvfrom(1024)
            udp.sendto(data, address)

    threading.Thread(target=tcp_echo, daemon=True).start()
    threading.Thread(target=udp_echo, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix="angie-test-", dir=args.work) as temporary:
        root = Path(temporary)
        config = Settings(data_dir=root, angie_binary=args.binary, admin_listen="127.0.0.1:18182")
        agent = Agent(config)
        caps = agent.capabilities()
        assert caps["available"], caps
        certificate_id = str(uuid.uuid4())
        installed = install_certificate(
            config,
            certificate_id,
            (root / "bootstrap/fullchain.pem").read_bytes(),
            (root / "bootstrap/privkey.pem").read_bytes(),
            ["localhost"],
        )
        resources = [
            item(
                "certificates",
                {**Certificate(domains=["localhost"]).model_dump(), **installed},
                certificate_id,
            ),
            item(
                "proxy-hosts",
                Route(
                    domains=["localhost"],
                    host="127.0.0.1",
                    port=backend.server_port,
                    tls="certificate",
                    certificate_id=certificate_id,
                    http3=True,
                    locations=[
                        {"path": "/apm.Echo/", "host": "127.0.0.1", "port": grpc_port, "scheme": "grpc"}
                    ],
                    force_ssl=False,
                ).model_dump(),
            ),
            item(
                "streams", Stream(listen_port=19081, host="127.0.0.1", port=tcp.getsockname()[1]).model_dump()
            ),
            item(
                "streams",
                Stream(
                    listen_port=19082, protocol="udp", host="127.0.0.1", port=udp.getsockname()[1]
                ).model_dump(),
            ),
        ]
        resources.append(item("runtime", Runtime(access_logs=True, analytics=True).model_dump()))

        def deployment(objects):
            revision = uuid.uuid4()
            bundle = Compiler(config, caps, root / "revisions" / str(revision)).compile(objects)
            # The production configuration still uses 80/443 and the packaged mime types.
            text = (
                bundle.config.replace("user angie apm;", "")
                .replace("listen 80", "listen 18080")
                .replace("listen [::]:80", "listen [::]:18080")
            )
            text = text.replace("listen 443", "listen 18443").replace("listen [::]:443", "listen [::]:18443")
            text = text.replace("/etc/angie/mime.types", str(args.conf_dir / "mime.types"))
            text = text.replace("/etc/angie/fastcgi_params", str(args.conf_dir / "fastcgi_params"))
            return Deployment(revision_id=revision, configuration=text, files=bundle.files)

        initial = deployment([])
        agent.stage(initial)
        agent.switch(str(initial.revision_id))
        config.root_config.write_text(f'include "{root}/current/angie.conf";\n')
        # Prefix isolates all temporary directories created by the binary.
        process = subprocess.Popen(
            [args.binary, "-p", str(root), "-c", str(config.root_config), "-g", "daemon off;"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            for _ in range(50):
                if process.poll() is not None:
                    raise RuntimeError(process.stderr.read().decode())
                try:
                    agent.generation()
                    break
                except httpx.HTTPError:
                    time.sleep(0.1)
            candidate = deployment(resources)
            staged = agent.stage(candidate)
            diagnostic = subprocess.run(
                [args.binary, "-p", str(root), "-t", "-c", str(staged / "angie.conf")],
                capture_output=True,
                text=True,
            )
            if diagnostic.returncode:
                raise RuntimeError("Fixture configuration failed: " + diagnostic.stderr)
            result = agent.apply(candidate)
            assert result["generation"] > 0
            response = httpx.get("http://127.0.0.1:18080/", headers={"Host": "localhost"}, trust_env=False)
            assert response.status_code == 200 and response.text == "apm-real-upstream", response.text
            response = httpx.get(
                "https://localhost:18443/", headers={"Host": "localhost"}, verify=False, trust_env=False
            )
            assert response.status_code == 200 and response.text == "apm-real-upstream"
            credentials = grpc.ssl_channel_credentials(
                root_certificates=(root / "bootstrap/fullchain.pem").read_bytes()
            )
            with grpc.secure_channel(
                "127.0.0.1:18443", credentials, options=(("grpc.ssl_target_name_override", "localhost"),)
            ) as channel:
                send = channel.unary_unary("/apm.Echo/Send")
                assert send(b"grpc-through-angie", timeout=5) == b"grpc-through-angie"
            asyncio.run(check_http3())
            with socket.create_connection(("127.0.0.1", 19081), timeout=3) as connection:
                connection.sendall(b"tcp-through-angie")
                assert connection.recv(1024) == b"tcp-through-angie"
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
                connection.settimeout(3)
                connection.sendto(b"udp-through-angie", ("127.0.0.1", 19082))
                assert connection.recvfrom(1024)[0] == b"udp-through-angie"
            bad = Deployment(
                revision_id=uuid.uuid4(), configuration=candidate.configuration + "\ninvalid_directive on;\n"
            )
            try:
                agent.apply(bad)
                raise AssertionError("Invalid candidate was accepted")
            except ValueError:
                pass
            assert agent.current() == str(candidate.revision_id)
            assert (
                httpx.get("http://127.0.0.1:18080/", headers={"Host": "localhost"}, trust_env=False).text
                == "apm-real-upstream"
            )
            print(
                json.dumps(
                    {
                        "binary": caps["version"],
                        "generation": result["generation"],
                        "checks": [
                            "angie -t",
                            "atomic reload",
                            "HTTP",
                            "TLS",
                            "gRPC over HTTP/2",
                            "HTTP/3 over QUIC",
                            "TCP",
                            "UDP",
                            "invalid configuration preserves traffic",
                        ],
                    },
                    indent=2,
                )
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            backend.shutdown()
            grpc_server.stop(0)


if __name__ == "__main__":
    main()
