#!/usr/bin/env python3
"""End-to-end test for HTTPS proxy (CONNECT) support in http_get.

Spins up, all on 127.0.0.1 with stdlib only:
  - a TLS server with a cert from a throwaway CA (via the openssl CLI),
  - a CONNECT proxy (good / refusing / auth-checking modes),
then builds a tiny Qasida program that http_get()s the TLS server
and runs it under different proxy envs.

Tests:
  1. direct (no proxy env)            -> body ok
  2. via proxy                        -> body ok, proxy saw CONNECT
  3. no_proxy=localhost bypass        -> body ok, proxy saw nothing
  4. proxy refuses (403)              -> nonzero exit, "proxy CONNECT refused"
  5. proxy auth (user:pass in URL)    -> body ok, auth header verified
  6. non-http proxy scheme ignored    -> body ok (direct, as before)

Exits 0 only if every test passes. Ambient proxy env vars are scrubbed
so the sandbox's own egress proxy cannot interfere.
"""
import base64
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BODY = "proxy-tls-ok"
PROXY_VARS = ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY",
              "no_proxy", "NO_PROXY")


def sh(*args, cwd):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{args} failed: {r.stderr.strip()}")
    return r


def make_certs(d):
    if not shutil.which("openssl"):
        print("SKIP: openssl CLI not found")
        sys.exit(2)
    sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", "ca.key",
       "-out", "ca.pem", "-days", "2", "-nodes", "-subj", "/CN=TestCA", cwd=d)
    sh("openssl", "req", "-newkey", "rsa:2048", "-keyout", "srv.key",
       "-out", "srv.csr", "-nodes", "-subj", "/CN=localhost", cwd=d)
    with open(os.path.join(d, "san.cnf"), "w") as f:
        f.write("subjectAltName=DNS:localhost,IP:127.0.0.1\n")
    sh("openssl", "x509", "-req", "-in", "srv.csr", "-CA", "ca.pem",
       "-CAkey", "ca.key", "-CAcreateserial", "-out", "srv.pem",
       "-days", "2", "-extfile", "san.cnf", cwd=d)


class TLSServer(threading.Thread):
    def __init__(self, d):
        super().__init__(daemon=True)
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(os.path.join(d, "srv.pem"),
                                 os.path.join(d, "srv.key"))
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.5)
        self.port = self.sock.getsockname()[1]
        self.stop_flag = False

    def run(self):
        while not self.stop_flag:
            try:
                raw, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                conn = self.ctx.wrap_socket(raw, server_side=True)
                data = b""
                while b"\r\n\r\n" not in data:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                payload = f"HTTP/1.0 200 OK\r\nContent-Length: {len(BODY)}\r\n\r\n{BODY}"
                conn.sendall(payload.encode())
                conn.close()
            except Exception:
                pass

    def stop(self):
        self.stop_flag = True
        self.sock.close()


def pump(src, dst):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class ProxyServer(threading.Thread):
    """CONNECT proxy. mode: 'good' | 'refuse' | 'auth'.
    In 'auth' mode, requires Proxy-Authorization: Basic <expect>."""

    def __init__(self, mode="good", expect=None):
        super().__init__(daemon=True)
        self.mode = mode
        self.expect = expect
        self.log = []
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.5)
        self.port = self.sock.getsockname()[1]
        self.stop_flag = False

    def run(self):
        while not self.stop_flag:
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self.handle, args=(conn,),
                             daemon=True).start()

    def handle(self, conn):
        try:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                data += chunk
            head = data.split(b"\r\n\r\n", 1)[0].decode("latin1")
            lines = head.split("\r\n")
            verb, target = lines[0].split(" ", 2)[0], lines[0].split(" ", 2)[1]
            if verb != "CONNECT":
                conn.sendall(b"HTTP/1.1 405 Nope\r\n\r\n")
                return
            if self.mode == "refuse":
                conn.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            if self.mode == "auth":
                auth = ""
                for ln in lines[1:]:
                    if ln.lower().startswith("proxy-authorization:"):
                        auth = ln.split(":", 1)[1].strip()
                if auth != "Basic " + self.expect:
                    conn.sendall(b"HTTP/1.1 407 Auth required\r\n\r\n")
                    return
            self.log.append(target)
            host, port = target.rsplit(":", 1)
            upstream = socket.create_connection((host, int(port)), timeout=10)
            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            t1 = threading.Thread(target=pump, args=(conn, upstream), daemon=True)
            t2 = threading.Thread(target=pump, args=(upstream, conn), daemon=True)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def stop(self):
        self.stop_flag = True
        self.sock.close()


def run_case(binary, env_extra, d):
    env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS}
    env["SSL_CERT_FILE"] = os.path.join(d, "ca.pem")
    env.update(env_extra)
    r = subprocess.run([binary], capture_output=True, text=True,
                       timeout=30, env=env)
    return r


def main():
    fails = []

    def check(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail and not ok else ""))
        if not ok:
            fails.append(name)

    with tempfile.TemporaryDirectory(prefix="qasida-proxy-") as d:
        make_certs(d)
        tls = TLSServer(d)
        tls.start()
        good = ProxyServer("good")
        good.start()
        refuse = ProxyServer("refuse")
        refuse.start()
        expect = base64.b64encode(b"user:pass").decode()
        auth = ProxyServer("auth", expect=expect)
        auth.start()
        try:
            prog = os.path.join(d, "get.fg")
            with open(prog, "w") as f:
                f.write('fn main() -> int {\n'
                        f'    let body = http_get("https://localhost:{tls.port}/");\n'
                        '    println(body);\n'
                        '    return 0;\n'
                        '}\n')
            binary = os.path.join(d, "getbin")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "forge.py"),
                                "build", prog, "-o", binary],
                               capture_output=True, text=True, cwd=ROOT)
            if r.returncode != 0:
                print("BUILD FAILED:", r.stdout, r.stderr)
                return 1

            r = run_case(binary, {}, d)
            check("1 direct, no proxy env", r.returncode == 0 and r.stdout.strip() == BODY,
                  f"rc={r.returncode} out={r.stdout!r} err={r.stderr[-200:]!r}")

            good.log.clear()
            r = run_case(binary, {"https_proxy": f"127.0.0.1:{good.port}"}, d)
            check("2 via proxy", r.returncode == 0 and r.stdout.strip() == BODY
                  and good.log == [f"localhost:{tls.port}"],
                  f"rc={r.returncode} out={r.stdout!r} log={good.log} err={r.stderr[-200:]!r}")

            good.log.clear()
            r = run_case(binary, {"https_proxy": f"127.0.0.1:{good.port}",
                                  "no_proxy": "localhost"}, d)
            check("3 no_proxy bypass", r.returncode == 0 and r.stdout.strip() == BODY
                  and good.log == [],
                  f"rc={r.returncode} out={r.stdout!r} log={good.log}")

            r = run_case(binary, {"https_proxy": f"127.0.0.1:{refuse.port}"}, d)
            check("4 proxy refuses", r.returncode != 0 and "proxy CONNECT refused" in r.stderr,
                  f"rc={r.returncode} err={r.stderr[-200:]!r}")

            r = run_case(binary, {"https_proxy": f"http://user:pass@127.0.0.1:{auth.port}"}, d)
            check("5 proxy auth", r.returncode == 0 and r.stdout.strip() == BODY,
                  f"rc={r.returncode} out={r.stdout!r} err={r.stderr[-200:]!r}")

            r = run_case(binary, {"https_proxy": f"socks5://127.0.0.1:{good.port}"}, d)
            check("6 non-http scheme ignored (direct)", r.returncode == 0 and r.stdout.strip() == BODY,
                  f"rc={r.returncode} out={r.stdout!r} err={r.stderr[-200:]!r}")
        finally:
            tls.stop()
            good.stop()
            refuse.stop()
            auth.stop()

    print()
    if fails:
        print(f"PROXY TEST FAILED: {len(fails)} failing: {', '.join(fails)}")
        return 1
    print("PROXY TEST PASSED: HTTPS CONNECT works, bypass and errors behave.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
