"""Forge package manager (qasida pkg).

A package is a directory with:
  forge.toml        [package] name/version, [dependencies] name = "path"
  src/main.fg       the program (entry point)
  tests/*.fg        programs that must exit 0 (run by `qasida pkg test`)
  vendor/<name>/    vendored dependencies (copied by `qasida pkg add`)

Commands (run from the package directory):
  qasida pkg init [name]     create a new package skeleton
  qasida pkg add <path>      vendor another package's src/*.fg into vendor/
  qasida pkg build [--mode safe|fast]   build src/main.fg to build/<name>
  qasida pkg run [-- args...]           build, then run the binary
  qasida pkg test            run every tests/*.fg, each must exit 0
  qasida pkg list            show name, version, dependencies
  qasida pkg lock            write forge.lock with sha256 of vendor files
  qasida pkg verify          check vendor files against forge.lock
  qasida pkg publish         copy this package into the local registry
  qasida pkg add name@ver    vendor a package from the local registry
                            (registry dir: $FORGE_REGISTRY or ~/.forge_registry)
  qasida pkg serve --dir D --port P
                            run the HTTP registry server (see
                            forge_lang/registry_server.py; no auth)
  qasida pkg publish-remote <url>
                            POST this package to an HTTP registry
  qasida pkg add-remote <url> name@ver
                            vendor a package from an HTTP registry

Dependencies are vendored, Go-style, not downloaded: `qasida pkg add`
copies files, so a build never needs the network or a registry.
Import a vendored package from src/main.fg with a path relative
to the package root, e.g. `import "vendor/stats/stats.fg";` — the
compiler resolves imports relative to the file, then the current
directory (the package root when you run `qasida pkg build`).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

from .errors import ForgeError
from .compiler import build as forge_build


def registry_dir():
    return os.environ.get("FORGE_REGISTRY") or os.path.expanduser("~/.forge_registry")


def read_manifest(cwd):
    path = os.path.join(cwd, "forge.toml")
    if not os.path.exists(path):
        raise ForgeError("no forge.toml in this directory (run 'qasida pkg init' first)")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    section = None
    pkg = {}
    deps = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        m = re.match(r'(\w[\w-]*)\s*=\s*"([^"]*)"', line)
        if not m:
            continue
        if section == "package":
            pkg[m.group(1)] = m.group(2)
        elif section == "dependencies":
            deps[m.group(1)] = m.group(2)
    return path, text, pkg, deps


def cmd_init(cwd, name):
    if os.path.exists(os.path.join(cwd, "forge.toml")):
        print("qasida pkg: forge.toml already exists here", file=sys.stderr)
        return 1
    if not name:
        name = os.path.basename(os.path.abspath(cwd)) or "mytool"
    name = re.sub(r"[^A-Za-z0-9_-]", "-", name)
    os.makedirs(os.path.join(cwd, "src"), exist_ok=True)
    os.makedirs(os.path.join(cwd, "tests"), exist_ok=True)
    os.makedirs(os.path.join(cwd, "build"), exist_ok=True)
    with open(os.path.join(cwd, "forge.toml"), "w", encoding="utf-8") as f:
        f.write(f'[package]\nname = "{name}"\nversion = "0.1.0"\n'
                f'description = ""\n\n[dependencies]\n')
    with open(os.path.join(cwd, "src", "main.fg"), "w", encoding="utf-8") as f:
        f.write(f'// {name}: a Forge package.\nfn main() -> int {{\n'
                f'    println("hello from {name}");\n    return 0;\n}}\n')
    with open(os.path.join(cwd, "tests", "smoke.fg"), "w", encoding="utf-8") as f:
        f.write('fn main() -> int {\n    println("smoke ok");\n    return 0;\n}\n')
    with open(os.path.join(cwd, "README.md"), "w", encoding="utf-8") as f:
        f.write(f"# {name}\n\nA Forge package. Build with `qasida pkg build`, "
                f"test with `qasida pkg test`.\n")
    with open(os.path.join(cwd, ".gitignore"), "w", encoding="utf-8") as f:
        f.write("build/\n")
    print(f"created package '{name}' in {cwd}")
    return 0


def cmd_add(cwd, src_path):
    _mp, text, _pkg, deps = read_manifest(cwd)
    src_abs = os.path.abspath(os.path.join(cwd, src_path))
    src_manifest = os.path.join(src_abs, "forge.toml")
    if not os.path.exists(src_manifest):
        print(f"qasida pkg: {src_path} is not a Forge package (no forge.toml)",
              file=sys.stderr)
        return 1
    # Reuse read_manifest on the source package directory.
    _sp, _st, src_pkg, _sd = read_manifest(src_abs)
    dep_name = src_pkg.get("name")
    if not dep_name:
        print("qasida pkg: source package has no name in forge.toml", file=sys.stderr)
        return 1
    src_dir = os.path.join(src_abs, "src")
    if not os.path.isdir(src_dir):
        print("qasida pkg: source package has no src/ directory", file=sys.stderr)
        return 1
    dest = os.path.join(cwd, "vendor", dep_name)
    os.makedirs(dest, exist_ok=True)
    copied = []
    for fn in sorted(os.listdir(src_dir)):
        # main.fg is the package's own entry point, not a library:
        # vendoring it would duplicate fn main if anyone imported it.
        if fn.endswith(".fg") and fn != "main.fg":
            shutil.copy2(os.path.join(src_dir, fn), os.path.join(dest, fn))
            copied.append(fn)
    if dep_name not in deps:
        if "[dependencies]" not in text:
            text = text.rstrip() + "\n\n[dependencies]\n"
        text = text.rstrip() + f'\n{dep_name} = "{src_path}"\n'
        with open(os.path.join(cwd, "forge.toml"), "w", encoding="utf-8") as f:
            f.write(text)
    print(f"vendored '{dep_name}' into vendor/{dep_name}/ ({', '.join(copied)})")
    print(f'import it with: import "vendor/{dep_name}/{copied[0]}";'
          if copied else "")
    return 0


def cmd_publish(cwd):
    _mp, _text, pkg, _deps = read_manifest(cwd)
    name = pkg.get("name")
    version = pkg.get("version", "0.1.0")
    if not name:
        print("qasida pkg: package has no name", file=sys.stderr)
        return 1
    dest = os.path.join(registry_dir(), name, version)
    os.makedirs(os.path.join(dest, "src"), exist_ok=True)
    src_dir = os.path.join(cwd, "src")
    copied = []
    for fn in sorted(os.listdir(src_dir)):
        if fn.endswith(".fg") and fn != "main.fg":
            shutil.copy2(os.path.join(src_dir, fn), os.path.join(dest, "src", fn))
            copied.append(fn)
    shutil.copy2(os.path.join(cwd, "forge.toml"), os.path.join(dest, "forge.toml"))
    print(f"published {name}@{version} to {dest} ({', '.join(copied)})")
    return 0


def _http_json(url, method="GET", body=None, token=None):
    import urllib.request
    import urllib.error
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def cmd_serve(cwd, rest):
    from .registry_server import serve
    root = os.path.expanduser("~/.forge_registry_server")
    port = 8765
    token = None
    if "--dir" in rest:
        root = rest[rest.index("--dir") + 1]
    if "--port" in rest:
        port = int(rest[rest.index("--port") + 1])
    if "--token" in rest:
        token = rest[rest.index("--token") + 1]
    serve(root, port, token=token)
    return 0


def cmd_publish_remote(cwd, url, token=None):
    _mp, _text, pkg, _deps = read_manifest(cwd)
    name = pkg.get("name")
    version = pkg.get("version", "0.1.0")
    if not name:
        print("qasida pkg: package has no name", file=sys.stderr)
        return 1
    src_dir = os.path.join(cwd, "src")
    files = {}
    for fn in sorted(os.listdir(src_dir)):
        if fn.endswith(".fg") and fn != "main.fg":
            with open(os.path.join(src_dir, fn), encoding="utf-8") as f:
                files[fn] = f.read()
    if not files:
        print("qasida pkg: nothing to publish (src/ has no library files)", file=sys.stderr)
        return 1
    status, body = _http_json(url.rstrip("/") + "/api/publish", method="POST",
                              body={"name": name, "version": version, "files": files},
                              token=token)
    if status != 200:
        print(f"qasida pkg: publish failed ({status}): {body}", file=sys.stderr)
        return 1
    print(f"published {name}@{version} to {url}")
    return 0


def cmd_add_remote(cwd, url, spec):
    import urllib.request
    name, _, version = spec.partition("@")
    if not name or not version:
        print("usage: qasida pkg add-remote <url> name@version", file=sys.stderr)
        return 1
    base = url.rstrip("/")
    status, body = _http_json(f"{base}/api/packages/{name}/{version}")
    if status != 200:
        print(f"qasida pkg: {name}@{version} not on {url} ({status})", file=sys.stderr)
        return 1
    files = json.loads(body).get("files", [])
    # Stage the remote package as a local package directory, then reuse cmd_add.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "src"))
        with open(os.path.join(tmp, "forge.toml"), "w", encoding="utf-8") as f:
            f.write(f'[package]\nname = "{name}"\nversion = "{version}"\n\n[dependencies]\n')
        for fn in files:
            with urllib.request.urlopen(f"{base}/api/packages/{name}/{version}/{fn}", timeout=10) as resp:
                text = resp.read().decode()
            with open(os.path.join(tmp, "src", fn), "w", encoding="utf-8") as f:
                f.write(text)
        return cmd_add(cwd, tmp)


def cmd_add_registry(cwd, spec):
    name, _, version = spec.partition("@")
    if not name or not version:
        print("usage: qasida pkg add name@version", file=sys.stderr)
        return 1
    src = os.path.join(registry_dir(), name, version)
    if not os.path.isdir(src):
        print(f"qasida pkg: {name}@{version} not in registry {registry_dir()}",
              file=sys.stderr)
        return 1
    return cmd_add(cwd, src)


def _build(cwd, mode):
    _mp, _text, pkg, _deps = read_manifest(cwd)
    name = pkg.get("name", "app")
    main = os.path.join(cwd, "src", "main.fg")
    if not os.path.exists(main):
        print("qasida pkg: src/main.fg not found", file=sys.stderr)
        return 1, None
    out_dir = os.path.join(cwd, "build")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, name)
    try:
        forge_build(main, out, mode=mode)
    except ForgeError as e:
        print(f"qasida: error: {e}", file=sys.stderr)
        return 1, None
    print(f"built: {out} (mode={mode})")
    return 0, out


def dispatch(argv, forge_path, cwd):
    if not argv:
        print("usage: qasida pkg <init|add|build|run|test|list> ...", file=sys.stderr)
        return 1
    cmd = argv[0]
    rest = argv[1:]
    try:
        if cmd == "init":
            return cmd_init(cwd, rest[0] if rest else None)
        if cmd == "add":
            if not rest:
                print("usage: qasida pkg add <path-to-package> or <name@version>", file=sys.stderr)
                return 1
            if "@" in rest[0] and not os.path.exists(rest[0]):
                return cmd_add_registry(cwd, rest[0])
            return cmd_add(cwd, rest[0])
        if cmd == "publish":
            return cmd_publish(cwd)
        if cmd == "serve":
            return cmd_serve(cwd, rest)
        if cmd == "publish-remote":
            if not rest:
                print("usage: qasida pkg publish-remote <url> [--token TOKEN]", file=sys.stderr)
                return 1
            token = rest[rest.index("--token") + 1] if "--token" in rest else None
            return cmd_publish_remote(cwd, rest[0], token=token)
        if cmd == "add-remote":
            if len(rest) < 2:
                print("usage: qasida pkg add-remote <url> name@version", file=sys.stderr)
                return 1
            return cmd_add_remote(cwd, rest[0], rest[1])
        if cmd == "list-remote":
            if not rest:
                print("usage: qasida pkg list-remote <url>", file=sys.stderr)
                return 1
            status, body = _http_json(rest[0].rstrip("/") + "/api/packages")
            if status != 200:
                print(f"qasida pkg: registry unreachable ({status})", file=sys.stderr)
                return 1
            for pkg in json.loads(body).get("packages", []):
                print(f"{pkg['name']} {', '.join(pkg['versions'])}")
            return 0
        if cmd == "list-static":
            if not rest:
                print("usage: qasida pkg list-static <base_url>", file=sys.stderr)
                return 1
            status, body = _http_json(rest[0].rstrip("/") + "/packages.json")
            if status != 200:
                print(f"qasida pkg: static registry unreachable ({status})", file=sys.stderr)
                return 1
            for pkg in json.loads(body).get("packages", []):
                print(f"{pkg['name']} {', '.join(pkg['versions'])}")
            return 0
        if cmd == "add-static":
            if len(rest) < 2:
                print("usage: qasida pkg add-static <base_url> name@version", file=sys.stderr)
                return 1
            base, spec = rest[0].rstrip("/"), rest[1]
            if "@" not in spec:
                print("usage: qasida pkg add-static <base_url> name@version", file=sys.stderr)
                return 1
            name, version = spec.split("@", 1)
            status, body = _http_json(f"{base}/packages.json")
            if status != 200:
                print(f"qasida pkg: static registry unreachable ({status})", file=sys.stderr)
                return 1
            files = None
            for pkg in json.loads(body).get("packages", []):
                if pkg["name"] == name:
                    files = pkg.get("files", {}).get(version)
            if files is None:
                print(f"qasida pkg: {spec} not in static registry", file=sys.stderr)
                return 1
            # Vendor via the same path as a local package.
            import tempfile
            tmp = tempfile.mkdtemp(prefix="forge_static_")
            try:
                pkg_dir = os.path.join(tmp, name)
                os.makedirs(os.path.join(pkg_dir, "src"))
                with open(os.path.join(pkg_dir, "forge.toml"), "w", encoding="utf-8") as f:
                    f.write(f"[package]\nname = \"{name}\"\nversion = \"{version}\"\n")
                for fname in files:
                    status, body = _http_json(f"{base}/packages/{name}/{version}/{fname}")
                    if status != 200:
                        print(f"qasida pkg: could not fetch {fname} ({status})", file=sys.stderr)
                        return 1
                    with open(os.path.join(pkg_dir, "src", fname), "w", encoding="utf-8") as f:
                        f.write(body)
                return cmd_add(cwd, pkg_dir)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        if cmd == "build":
            mode = "safe"
            if "--mode" in rest:
                mode = rest[rest.index("--mode") + 1]
            rc, _out = _build(cwd, mode)
            return rc
        if cmd == "run":
            mode = "safe"
            prog_args = rest
            if "--" in rest:
                idx = rest.index("--")
                prog_args = rest[idx + 1:]
                before = rest[:idx]
                if "--mode" in before:
                    mode = before[before.index("--mode") + 1]
            rc, out = _build(cwd, mode)
            if rc != 0:
                return rc
            proc = subprocess.run([out] + prog_args)
            return proc.returncode
        if cmd == "test":
            test_dir = os.path.join(cwd, "tests")
            files = sorted(f for f in os.listdir(test_dir)
                           if f.endswith(".fg")) if os.path.isdir(test_dir) else []
            if not files:
                print("no tests")
                return 0
            failures = []
            for fn in files:
                path = os.path.join(test_dir, fn)
                proc = subprocess.run([sys.executable, forge_path, "run", path],
                                      capture_output=True, text=True, cwd=cwd)
                if proc.returncode != 0:
                    failures.append(fn)
                    print(f"FAIL {fn}\n{proc.stdout}{proc.stderr}")
                else:
                    print(f"PASS {fn}")
            if failures:
                print(f"qasida pkg test: {len(failures)} failure(s)")
                return 1
            print(f"qasida pkg test: all {len(files)} test(s) passed")
            return 0
        if cmd == "list":
            _mp, _text, pkg, deps = read_manifest(cwd)
            print(f"{pkg.get('name', '?')} {pkg.get('version', '?')}")
            for k, v in deps.items():
                print(f"  {k} = {v}")
            return 0
        if cmd == "lock":
            _mp, _text, pkg, deps = read_manifest(cwd)
            lock = {"package": pkg.get("name", "?"), "dependencies": {}}
            vendor_dir = os.path.join(cwd, "vendor")
            if os.path.isdir(vendor_dir):
                for dep in sorted(os.listdir(vendor_dir)):
                    dep_dir = os.path.join(vendor_dir, dep)
                    if not os.path.isdir(dep_dir):
                        continue
                    lock["dependencies"][dep] = {}
                    for fn in sorted(os.listdir(dep_dir)):
                        if fn.endswith(".fg"):
                            with open(os.path.join(dep_dir, fn), "rb") as f:
                                lock["dependencies"][dep][fn] = hashlib.sha256(f.read()).hexdigest()
            with open(os.path.join(cwd, "forge.lock"), "w", encoding="utf-8") as f:
                json.dump(lock, f, indent=2)
                f.write("\n")
            print(f"wrote forge.lock ({len(lock['dependencies'])} dependencies)")
            return 0
        if cmd == "verify":
            lock_path = os.path.join(cwd, "forge.lock")
            if not os.path.exists(lock_path):
                print("qasida pkg: no forge.lock (run 'qasida pkg lock' first)", file=sys.stderr)
                return 1
            with open(lock_path, encoding="utf-8") as f:
                lock = json.load(f)
            bad = []
            for dep, files in lock.get("dependencies", {}).items():
                for fn, want in files.items():
                    path = os.path.join(cwd, "vendor", dep, fn)
                    if not os.path.exists(path):
                        bad.append(f"{dep}/{fn} missing")
                        continue
                    with open(path, "rb") as f:
                        got = hashlib.sha256(f.read()).hexdigest()
                    if got != want:
                        bad.append(f"{dep}/{fn} changed")
            if bad:
                for b in bad:
                    print(f"MISMATCH {b}")
                return 1
            print("forge.lock verified: all vendored files match")
            return 0
        print(f"qasida pkg: unknown subcommand '{cmd}'", file=sys.stderr)
        return 1
    except ForgeError as e:
        print(f"qasida: error: {e}", file=sys.stderr)
        return 1
