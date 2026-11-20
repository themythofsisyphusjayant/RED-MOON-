#!/usr/bin/env python3
"""PNG decoder v2 test (21 Nov 2026) — general PNG decode in pure Qasida.

Generates real PNG fixtures (all color types, all five filters,
stored/fixed/dynamic DEFLATE, Adam7 interlace, tRNS), computes the
reference pixels with PIL (convert("RGBA")), runs the Qasida
decoder under BOTH compilers (hosted default + QASIDA_COMPILER=python),
and compares stdout exactly AND the decoded RGBA bytes byte-exact
(the .fg drivers write RGBA to /tmp/pngdec2_<stem>.rgba).

Fixtures are (re)generated deterministically on every run into
tests/fixtures_png/ so the demo also works standalone.

Usage:
  python3 tests/test_pngdec2.py
"""
import os
import random
import struct
import subprocess
import sys
import zlib

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXDIR = os.path.join(ROOT, "tests", "fixtures_png")
FORGE_PY = os.environ.get(
    "FORGE_PY", os.path.expanduser("~/workspace/forge-v2/forge.py"))
FORGE = [sys.executable, FORGE_PY]
FAILURES = []

# Fixture order MUST match the hardcoded list in examples/pngdec2_test.fg
# (the test asserts the order by reading that file).
FIXTURES = ["rgb_8x8", "rgb_16x16", "gray_12x7", "palette_10x10",
            "grayalpha_9x9", "rgba_13x11", "rgb_interlaced_20x14",
            "photo_64x64", "rgb_trns", "gray_trns", "filt_none_8x8",
            "filt_sub_8x8", "filt_up_8x8", "filt_avg_8x8",
            "filt_paeth_8x8", "filt_mixed_8x8", "rgb_stored_8x8",
            "rgb_fixed_8x8", "rgb_level1_8x8", "rgb_level9_8x8"]

# (name, raw bytes) for the inflate demo; expected values are computed
# by zlib.decompress at runtime.
INF_DATA1 = b"hello world, hello deflate! " * 4
INF_DATA2 = b"The quick brown fox jumps over the lazy dog. " * 20


def _fixed(data):
    co = zlib.compressobj(9, zlib.DEFLATED, 15, 8, zlib.Z_FIXED)
    return co.compress(data) + co.flush()


INF_STREAMS = [
    ("inf_stored.bin", zlib.compress(INF_DATA1, 0)),
    ("inf_fixed.bin", _fixed(INF_DATA1)),
    ("inf_dynamic.bin", zlib.compress(INF_DATA1, 6)),
    ("inf_dynamic9.bin", zlib.compress(INF_DATA2, 9)),
    ("inf_empty.bin", zlib.compress(b"", 6)),
]
INF_EXPECTED = [  # (len, sum) of the decompressed bytes, per stream
    (len(zlib.decompress(s)), sum(zlib.decompress(s)))
    for _, s in INF_STREAMS
]


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def chunk(typ, data):
    out = struct.pack(">I", len(data)) + typ + data
    out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return out


def build_png(w, h, ctype, raw, level=6, strategy=zlib.Z_DEFAULT_STRATEGY,
              interlace=0, plte=None, trns=None, bitdepth=8):
    comp = zlib.compressobj(level, zlib.DEFLATED, 15, 8, strategy)
    idat = comp.compress(raw) + comp.flush()
    out = b"\x89PNG\r\n\x1a\n"
    out += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, bitdepth, ctype,
                                      0, 0, interlace))
    if plte is not None:
        out += chunk(b"PLTE", plte)
    if trns is not None:
        out += chunk(b"tRNS", trns)
    out += chunk(b"IDAT", idat)
    out += chunk(b"IEND", b"")
    return out


def apply_filter(ftype, row, prior, bpp):
    out = bytearray(len(row))
    for i, x in enumerate(row):
        a = row[i - bpp] if i >= bpp else 0
        b = prior[i] if prior else 0
        c = prior[i - bpp] if (prior and i >= bpp) else 0
        if ftype == 0:
            pred = 0
        elif ftype == 1:
            pred = a
        elif ftype == 2:
            pred = b
        elif ftype == 3:
            pred = (a + b) // 2
        else:
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            if pa <= pb and pa <= pc:
                pred = a
            elif pb <= pc:
                pred = b
            else:
                pred = c
        out[i] = (x - pred) & 0xFF
    return bytes(out)


def raw_scanlines(w, h, bpp, pixels, filters):
    raw = bytearray()
    for r in range(h):
        f = filters[r] if isinstance(filters, list) else filters
        row = pixels[r * w * bpp:(r + 1) * w * bpp]
        prior = pixels[(r - 1) * w * bpp:r * w * bpp] if r > 0 else None
        raw.append(f)
        raw += apply_filter(f, row, prior, bpp)
    return bytes(raw)


ADAM7_PASSES = [(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
                (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]


def adam7_raw(w, h, bpp, pixels, filters=0):
    """Filtered scanlines of all 7 Adam7 passes, in pass order."""
    raw = bytearray()
    for (x0, y0, dx, dy) in ADAM7_PASSES:
        pw = (w - x0 + dx - 1) // dx if w > x0 else 0
        ph = (h - y0 + dy - 1) // dy if h > y0 else 0
        for py in range(ph):
            row = bytearray()
            prior = bytearray()
            for px in range(pw):
                sx, sy = x0 + px * dx, y0 + py * dy
                row += pixels[(sy * w + sx) * bpp:(sy * w + sx + 1) * bpp]
                if py > 0:
                    sx2, sy2 = x0 + px * dx, y0 + (py - 1) * dy
                    prior += pixels[(sy2 * w + sx2) * bpp:
                                    (sy2 * w + sx2 + 1) * bpp]
            f = filters[py] if isinstance(filters, list) else filters
            raw.append(f)
            raw += apply_filter(f, bytes(row),
                                bytes(prior) if py > 0 else None, bpp)
    return bytes(raw)


def gen_fixtures():
    os.makedirs(FIXDIR, exist_ok=True)
    for name, data in INF_STREAMS:
        with open(os.path.join(FIXDIR, name), "wb") as f:
            f.write(data)
    # PIL images (color types + interlace).
    img = Image.new("RGB", (8, 8))
    img.putdata([(x * 36 % 256, y * 36 % 256, (x + y) * 18 % 256)
                 for y in range(8) for x in range(8)])
    img.save(os.path.join(FIXDIR, "rgb_8x8.png"))
    img = Image.new("RGB", (16, 16))
    img.putdata([((x * 16) % 256, (y * 16) % 256, ((x ^ y) * 16) % 256)
                 for y in range(16) for x in range(16)])
    img.save(os.path.join(FIXDIR, "rgb_16x16.png"))
    img = Image.new("L", (12, 7))
    img.putdata([(x * 20 + y * 30) % 256
                 for y in range(7) for x in range(12)])
    img.save(os.path.join(FIXDIR, "gray_12x7.png"))
    img = Image.new("P", (10, 10))
    img.putpalette([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0,
                    0, 255, 255, 255, 0, 255, 128, 128, 128, 0, 0, 0])
    img.putdata([(x + y) % 8 for y in range(10) for x in range(10)])
    img.save(os.path.join(FIXDIR, "palette_10x10.png"),
             transparency=bytes([255, 128, 0, 255, 255, 64, 255, 255]))
    img = Image.new("LA", (9, 9))
    img.putdata([((x * 28) % 256, (y * 28) % 256)
                 for y in range(9) for x in range(9)])
    img.save(os.path.join(FIXDIR, "grayalpha_9x9.png"))
    img = Image.new("RGBA", (13, 11))
    img.putdata([((x * 20) % 256, (y * 24) % 256, ((x + y) * 12) % 256,
                  (x * y * 3) % 256)
                 for y in range(11) for x in range(13)])
    img.save(os.path.join(FIXDIR, "rgba_13x11.png"))
    # Adam7 interlaced RGB, hand-built (PIL's save ignores interlace=1).
    px20 = bytes([v for y in range(14) for x in range(20)
                  for v in ((x * 13) % 256, (y * 19) % 256,
                            (x * y) % 256)])
    with open(os.path.join(FIXDIR, "rgb_interlaced_20x14.png"),
              "wb") as f:
        f.write(build_png(20, 14, 2, adam7_raw(20, 14, 3, px20),
                          level=6, interlace=1))
    rng = random.Random(7)
    img = Image.new("RGB", (64, 64))
    img.putdata([((x * 4 + rng.randrange(40)) % 256,
                  (y * 4 + rng.randrange(40)) % 256,
                  ((x + y) * 2 + rng.randrange(40)) % 256)
                 for y in range(64) for x in range(64)])
    img.save(os.path.join(FIXDIR, "photo_64x64.png"))
    # Hand-built PNGs (filter / level / tRNS control).
    px = b"".join(bytes([(x * 32) % 256, (y * 32) % 256,
                         ((x + y) * 16) % 256])
                   for y in range(8) for x in range(8))
    for ftype, stem in [(0, "filt_none_8x8"), (1, "filt_sub_8x8"),
                        (2, "filt_up_8x8"), (3, "filt_avg_8x8"),
                        (4, "filt_paeth_8x8")]:
        raw = raw_scanlines(8, 8, 3, px, ftype)
        with open(os.path.join(FIXDIR, stem + ".png"), "wb") as f:
            f.write(build_png(8, 8, 2, raw, level=6))
    raw = raw_scanlines(8, 8, 3, px, [r % 5 for r in range(8)])
    with open(os.path.join(FIXDIR, "filt_mixed_8x8.png"), "wb") as f:
        f.write(build_png(8, 8, 2, raw, level=6))
    raw = raw_scanlines(8, 8, 3, px, 0)
    with open(os.path.join(FIXDIR, "rgb_stored_8x8.png"), "wb") as f:
        f.write(build_png(8, 8, 2, raw, level=0))
    with open(os.path.join(FIXDIR, "rgb_fixed_8x8.png"), "wb") as f:
        f.write(build_png(8, 8, 2, raw, level=9,
                          strategy=zlib.Z_FIXED))
    with open(os.path.join(FIXDIR, "rgb_level1_8x8.png"), "wb") as f:
        f.write(build_png(8, 8, 2, raw, level=1))
    with open(os.path.join(FIXDIR, "rgb_level9_8x8.png"), "wb") as f:
        f.write(build_png(8, 8, 2, raw, level=9))
    # tRNS: RGB with transparent red, gray with transparent value 100.
    px6 = b"".join(bytes([255, 0, 0] if (x + y) % 3 == 0 else
                         [(x * 40) % 256, (y * 40) % 256, 128])
                   for y in range(5) for x in range(6))
    raw = raw_scanlines(6, 5, 3, px6, 0)
    with open(os.path.join(FIXDIR, "rgb_trns.png"), "wb") as f:
        f.write(build_png(6, 5, 2, raw, level=6,
                          trns=bytes([0, 255, 0, 0, 0, 0])))
    pxg = bytes([(x * 40 + y * 10) % 256 for y in range(5)
                 for x in range(6)])
    pxg = bytearray(pxg)
    pxg[0] = 100
    raw = raw_scanlines(6, 5, 1, bytes(pxg), 0)
    with open(os.path.join(FIXDIR, "gray_trns.png"), "wb") as f:
        f.write(build_png(6, 5, 0, raw, level=6,
                          trns=bytes([0, 100])))


def reference(stem):
    """(w, h, rgba bytes) for a fixture, from PIL."""
    path = os.path.join(FIXDIR, stem + ".png")
    im = Image.open(path).convert("RGBA")
    return im.width, im.height, im.tobytes()


def run_fg(name, env_extra, timeout=300):
    path = os.path.join(ROOT, "examples", name + ".fg")
    env = dict(os.environ)
    env.update(env_extra)
    try:
        r = subprocess.run(FORGE + ["run", path], capture_output=True,
                           text=True, cwd=ROOT, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"TIMEOUT after {timeout}s"
    return r, ""


def main():
    print("PNG decoder v2 test — 21 Nov 2026")
    gen_fixtures()
    # The .fg fixture list must match FIXTURES (order matters).
    with open(os.path.join(ROOT, "examples", "pngdec2_test.fg")) as f:
        fg_text = f.read()
    listed = [p.split("/")[-1][:-4] for p in
              __import__("re").findall(r"tests/fixtures_png/([a-z0-9_]+\.png)",
                                       fg_text)]
    check("pngdec2_test.fg fixture list matches FIXTURES",
          listed == FIXTURES, f"listed={listed}")
    # Expected stdout for pngdec2_test.fg: w, h, ok, sum, write-ok
    # per fixture, in order.
    expected_lines = []
    for stem in FIXTURES:
        w, h, rgba = reference(stem)
        expected_lines += [str(w), str(h), "1", str(sum(rgba)), "1"]
    expected_test = "\n".join(expected_lines) + "\n"
    # Expected stdout for the inflate demo: len + sum per stream.
    expected_inf = "".join(f"{n}\n{s}\n" for n, s in INF_EXPECTED)
    # Expected stdout for the photo demo.
    w, h, rgba = reference("photo_64x64")
    expected_demo = f"{w}\n{h}\n4\n1\n{sum(rgba)}\n1\n"

    for label, env_extra in [("hosted", {}),
                             ("python", {"QASIDA_COMPILER": "python"})]:
        print(f"pngdec2_test ({label}):")
        r, err = run_fg("pngdec2_test", env_extra)
        if r is None:
            check("pngdec2_test runs", False, err)
            continue
        check("pngdec2_test runs rc=0", r.returncode == 0,
              r.stderr[-300:])
        check("pngdec2_test exact stdout", r.stdout == expected_test,
              "" if r.stdout == expected_test
              else f"got: {r.stdout[:200]!r} ...")
        for stem in FIXTURES:
            _, _, rgba = reference(stem)
            got_path = f"/tmp/pngdec2_{stem}.rgba"
            ok = os.path.exists(got_path)
            got = open(got_path, "rb").read() if ok else b""
            check(f"pngdec2 {stem} RGBA byte-exact ({label})",
                  ok and got == rgba,
                  f"got {len(got)} bytes, want {len(rgba)}"
                  if ok else "missing output file")
        print(f"zlinflate_demo ({label}):")
        r, err = run_fg("zlinflate_demo", env_extra)
        if r is None:
            check("zlinflate_demo runs", False, err)
            continue
        check("zlinflate_demo runs rc=0", r.returncode == 0,
              r.stderr[-300:])
        check("zlinflate_demo exact stdout", r.stdout == expected_inf,
              "" if r.stdout == expected_inf
              else f"got: {r.stdout!r}")
        print(f"pngdec2_demo ({label}):")
        r, err = run_fg("pngdec2_demo", env_extra)
        if r is None:
            check("pngdec2_demo runs", False, err)
            continue
        check("pngdec2_demo runs rc=0", r.returncode == 0,
              r.stderr[-300:])
        check("pngdec2_demo exact stdout", r.stdout == expected_demo,
              "" if r.stdout == expected_demo
              else f"got: {r.stdout!r}")
        _, _, rgba = reference("photo_64x64")
        got_path = "/tmp/pngdec2_demo.rgba"
        ok = os.path.exists(got_path)
        got = open(got_path, "rb").read() if ok else b""
        check(f"pngdec2_demo photo RGBA byte-exact ({label})",
              ok and got == rgba,
              f"got {len(got)} bytes, want {len(rgba)}"
              if ok else "missing output file")
        print(f"pngdec_demo backward compat ({label}):")
        r, err = run_fg("pngdec_demo", env_extra)
        if r is None:
            check("pngdec_demo runs", False, err)
            continue
        check("pngdec_demo runs rc=0", r.returncode == 0,
              r.stderr[-300:])
        check("pngdec_demo exact stdout",
              r.stdout == "1\n1\n200\n100\n50\n1\n0\n",
              "" if r.stdout == "1\n1\n200\n100\n50\n1\n0\n"
              else f"got: {r.stdout!r}")
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
