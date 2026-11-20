#!/usr/bin/env python3
"""Baseline JPEG decoder tests (gap item, README.md:383).

Decodes real JPEGs with the pure-Qasida decoder
(forge_lang/stdlib/jpeg.fg, via examples/jpeg_demo.fg) and
compares every pixel against PIL (libjpeg). Reports the max
per-channel difference per file — integer-IDCT rounding is
expected, so the bar is maxdiff <= 5; anything above that
is a real bug, not rounding (nearest-neighbour upsampling
gave 95 at sharp chroma edges before fancy upsampling
landed; fancy upsampling brought it to IDCT level).

Fixtures (data/, generated once with PIL, deterministic):
  16x16 4:4:4 / 4:2:2 / 4:2:0, 17x13 4:2:0 (odd dims),
  24x16 grayscale, 32x32 with restart markers,
  32x32 quality 10, 320x240 photo (quality 85, 4:2:0),
  plus solid-colour and sharp-edge 4:2:0 images.
Also: a 16-bit-DQT file (DQT segment of the 4:4:4 file
rewritten with Pq=1, same values — must decode
identically), and negative cases (progressive JPEG and a
non-JPEG file must fail with a clear message).

Each fixture is run under BOTH compilers (hosted default
and QASIDA_COMPILER=python). The demo streams pixels on
stdout ("r g b" per line) — it does NOT save a PPM, because
building a whole PPM by repeated string concat is
quadratic and OOMs on a photo.
"""
import os
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
FAILURES = []
MAXDIFF_BAR = 5

FIXTURES = [
    "data/jpeg_16x16_444.jpg",
    "data/jpeg_16x16_422.jpg",
    "data/jpeg_16x16_420.jpg",
    "data/jpeg_17x13_420.jpg",
    "data/jpeg_24x16_gray.jpg",
    "data/jpeg_32x32_rst.jpg",
    "data/jpeg_32x32_q10.jpg",
    "data/jpeg_photo_320x240.jpg",
    "data/jpeg_solid_red.jpg",
    "data/jpeg_solid_gb.jpg",
    "data/jpeg_edge.jpg",
]


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_demo(path, compiler):
    env = dict(os.environ)
    if compiler == "python":
        env["QASIDA_COMPILER"] = "python"
    else:
        env.pop("QASIDA_COMPILER", None)
    return subprocess.run(
        FORGE + ["run", os.path.join("examples", "jpeg_demo.fg"), path, "pixels"],
        capture_output=True, text=True, cwd=ROOT, env=env, timeout=600)


def compare_pixels(jpg, compiler):
    """Returns (maxdiff, ndiff, sumabs) or None on run failure."""
    ref = Image.open(jpg).convert("RGB")
    w, h = ref.size
    rp = ref.load()
    r = run_demo(jpg, compiler)
    if r.returncode != 0:
        return None, f"exit {r.returncode}: {r.stdout[-200:]}{r.stderr[-200:]}"
    lines = r.stdout.split("\n")
    dw, dh = int(lines[0]), int(lines[1])
    if (dw, dh) != (w, h):
        return None, f"dims {(dw, dh)} != {(w, h)}"
    px = [tuple(map(int, ln.split())) for ln in lines[6:] if ln.strip()]
    if len(px) != w * h:
        return None, f"npixels {len(px)} != {w * h}"
    maxd = 0
    ndiff = 0
    sumd = 0
    for y in range(h):
        for x in range(w):
            for c in range(3):
                d = abs(px[y * w + x][c] - rp[x, y][c])
                maxd = max(maxd, d)
                sumd += d
                if d > 0:
                    ndiff += 1
    return (maxd, ndiff, sumd), ""


def make_16bit_dqt(src, dst):
    """Rewrite the DQT segments of src with Pq=1 (16-bit),
    same quant values. Must decode identically to src."""
    d = bytearray(open(src, "rb").read())
    pos = 2
    out = bytearray(d[:2])
    while pos < len(d):
        m = d[pos + 1]
        if m == 0xD9:
            out += d[pos:pos + 2]
            break
        if m == 0xDA:
            out += d[pos:]
            break
        ln = (d[pos + 2] << 8) + d[pos + 3]
        seg = d[pos + 4:pos + 2 + ln]
        if m == 0xDB:
            # Rebuild DQT with 16-bit values.
            new = bytearray()
            p = 0
            while p < len(seg):
                tq = seg[p] & 15
                p += 1
                new.append(0x10 | tq)
                for _ in range(64):
                    v = seg[p]
                    p += 1
                    new.append(v >> 8)
                    new.append(v & 255)
            ln2 = len(new) + 2
            out += bytes([0xFF, 0xDB, ln2 >> 8, ln2 & 255]) + bytes(new)
        else:
            out += d[pos:pos + 2 + ln]
        pos += 2 + ln
    open(dst, "wb").write(bytes(out))


def main():
    print("baseline JPEG decoder vs PIL (libjpeg)")
    for jpg in FIXTURES:
        for compiler in ("python", "hosted"):
            (res, err) = compare_pixels(os.path.join(ROOT, jpg), compiler)
            name = f"{os.path.basename(jpg)} [{compiler}]"
            if res is None:
                check(name, False, err)
                continue
            maxd, ndiff, sumd = res
            check(name, maxd <= MAXDIFF_BAR,
                  f"maxdiff={maxd} ndiff={ndiff} sumabs={sumd}")
    # 16-bit DQT (generated, in /tmp so it is not pushed).
    src = os.path.join(ROOT, "data/jpeg_16x16_444.jpg")
    dst = "/tmp/jpeg_16bit_dqt.jpg"
    make_16bit_dqt(src, dst)
    for compiler in ("python", "hosted"):
        (res, err) = compare_pixels(dst, compiler)
        name = f"16-bit-DQT [{compiler}]"
        if res is None:
            check(name, False, err)
            continue
        maxd, ndiff, sumd = res
        check(name, maxd <= MAXDIFF_BAR,
              f"maxdiff={maxd} ndiff={ndiff} sumabs={sumd}")
    # 640x480 noisy photo (generated, in /tmp so it is not
    # pushed). Bar is 6, not 5: same per-value error as the
    # 320x240 (avg ~0.5) but 4x the pixels, so the max of the
    # error distribution runs one higher. Still IDCT rounding.
    import random
    random.seed(11)
    w640, h640 = 640, 480
    big = Image.new("RGB", (w640, h640))
    bp = big.load()
    for yy in range(h640):
        for xx in range(w640):
            r = (xx * 200 // w640 + yy * 55 // h640 + random.randint(-10, 10)) % 256
            g = (yy * 220 // h640 + xx * 35 // w640 + random.randint(-10, 10)) % 256
            b = ((xx * yy) % 251 + random.randint(-10, 10)) % 256
            bp[xx, yy] = (r, g, b)
    big640 = "/tmp/jpeg_photo_640x480.jpg"
    big.save(big640, "JPEG", quality=90, subsampling=2)
    for compiler in ("python", "hosted"):
        (res, err) = compare_pixels(big640, compiler)
        name = f"photo-640x480 [{compiler}]"
        if res is None:
            check(name, False, err)
            continue
        maxd, ndiff, sumd = res
        check(name, maxd <= 6,
              f"maxdiff={maxd} ndiff={ndiff} sumabs={sumd}")
    # Negative cases: progressive JPEG and a non-JPEG file.
    prog = "/tmp/jpeg_progressive.jpg"
    Image.new("RGB", (16, 16), (9, 9, 9)).save(prog, "JPEG", progressive=True)
    for compiler in ("python", "hosted"):
        r = run_demo(prog, compiler)
        out = (r.stdout + r.stderr).lower()
        check(f"progressive rejected [{compiler}]",
              r.returncode != 0 and "progressive" in out,
              f"exit={r.returncode} out={out[-120:]!r}")
    bad = "/tmp/jpeg_notajpeg.txt"
    with open(bad, "w") as f:
        f.write("this is not a jpeg\n")
    for compiler in ("python", "hosted"):
        r = run_demo(bad, compiler)
        out = (r.stdout + r.stderr).lower()
        check(f"non-JPEG rejected [{compiler}]",
              r.returncode != 0 and "not a jpeg" in out,
              f"exit={r.returncode} out={out[-120:]!r}")
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
