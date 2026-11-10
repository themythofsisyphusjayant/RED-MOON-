"""Qasida -> C code generator.

Safe mode (default): checked int arithmetic, bounds-checked indexing.
Fast mode (--mode fast): unchecked arithmetic/indexing, -O3 -march=native
in the driver, for C++-style microsecond-latency work. Fast mode is an
explicit opt-in: it can wrap, crash on division by zero, and read out
of bounds, exactly like unchecked C/C++.
Arrays are contiguous C arrays (good for cache and auto-vectorisation),
shared by reference on assignment, like Python lists.
"""

from .errors import ForgeError
from . import ast_nodes as A
from .unions import (is_union_type, union_members, union_c_name,
                     union_str_index)
from .opaques import (is_opaque_type, opaque_trait, opaque_c_name,
                      impls_for_trait)
from .fixedints import (is_fixed_int, is_int_type, fixed_range,
                        FIXED_WIDTHS, FIXED_C_TYPES)
from .tuples import is_tuple_type, tuple_elems, tuple_c_name

C_SCALAR = {"int": "long long", "float": "double", "bool": "bool", "str": "char *", "void": "void",
            "never": "char", "range": "ForgeRange"}
C_SCALAR.update(FIXED_C_TYPES)
ARRAY_STRUCT = {"int": "ForgeIntArray", "float": "ForgeFloatArray",
                "bool": "ForgeBoolArray", "str": "ForgeStrArray"}
ARRAY_ELEM_C = {"int": "long long", "float": "double", "bool": "bool", "str": "char *"}
PUSH_FN = {"int": "forge_int_push", "float": "forge_float_push",
           "bool": "forge_bool_push", "str": "forge_str_push"}
GET_FN = {"int": "forge_int_get", "float": "forge_float_get",
          "bool": "forge_bool_get", "str": "forge_str_get"}
SET_FN = {"int": "forge_int_set", "float": "forge_float_set",
          "bool": "forge_bool_set", "str": "forge_str_set"}

HEADER = r"""#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <stdint.h>
#include <math.h>
#include <pthread.h>
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <sys/types.h>
#else
#include <sys/socket.h>
#include <netdb.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#endif
#if (!defined(_WIN32) && !defined(FORGE_NO_OPENSSL)) || defined(FORGE_HAVE_OPENSSL)
#include <openssl/ssl.h>
#include <openssl/err.h>
#endif
#include <time.h>

static void forge_free_str(char *p);
static void forge_fail(const char *msg);
/* Socket portability: Winsock sockets are 64-bit SOCKET handles, not
   ints; INVALID_SOCKET is not -1; close() is closesocket(); and
   WSAStartup must run before any socket call. POSIX builds keep the
   plain int fd path. */
#ifdef _WIN32
typedef SOCKET forge_sock_t;
#define FORGE_SOCK_INVALID INVALID_SOCKET
static int forge_sock_started = 0;
static void forge_sock_init(void) {
    if (!forge_sock_started) {
        WSADATA wsa;
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) forge_fail("WSAStartup failed");
        forge_sock_started = 1;
    }
}
static void forge_sock_close(forge_sock_t s) { closesocket(s); }
#else
typedef int forge_sock_t;
#define FORGE_SOCK_INVALID (-1)
static void forge_sock_init(void) {}
static void forge_sock_close(forge_sock_t s) { close(s); }
#endif
typedef struct { long long *data; long long len; long long cap; long long *ref; } ForgeIntArray;
typedef struct { double *data; long long len; long long cap; long long *ref; } ForgeFloatArray;
typedef struct { bool *data; long long len; long long cap; long long *ref; } ForgeBoolArray;
typedef struct { char **data; long long len; long long cap; long long *ref; } ForgeStrArray;
static long long forge_arr_allocs = 0;
static long long forge_arr_frees = 0;
static long long *forge_arr_ref_new(void) {
    long long *r = (long long *)malloc(sizeof(long long));
    if (!r) forge_fail("out of memory");
    *r = 1;
    forge_arr_allocs++;
    return r;
}
static void forge_arr_inc(long long *ref) { if (ref) (*ref)++; }
static void forge_weak_dead(long long *ref);
static void forge_int_array_free(ForgeIntArray a) {
    if (a.ref && --(*a.ref) == 0) { forge_weak_dead(a.ref); if (a.data) memset(a.data, 0, (size_t)a.cap * sizeof(*a.data)); free(a.data); if (a.ref) memset(a.ref, 0, sizeof(long long)); free(a.ref); forge_arr_frees++; }
}
static void forge_float_array_free(ForgeFloatArray a) {
    if (a.ref && --(*a.ref) == 0) { if (a.data) memset(a.data, 0, (size_t)a.cap * sizeof(*a.data)); free(a.data); if (a.ref) memset(a.ref, 0, sizeof(long long)); free(a.ref); forge_arr_frees++; }
}
static void forge_bool_array_free(ForgeBoolArray a) {
    if (a.ref && --(*a.ref) == 0) { if (a.data) memset(a.data, 0, (size_t)a.cap * sizeof(*a.data)); free(a.data); if (a.ref) memset(a.ref, 0, sizeof(long long)); free(a.ref); forge_arr_frees++; }
}
static void forge_str_array_free(ForgeStrArray a) {
    if (a.ref && --(*a.ref) == 0) {
        for (long long i = 0; i < a.len; i++) forge_free_str(a.data[i]);
        if (a.data) memset(a.data, 0, (size_t)a.cap * sizeof(*a.data)); free(a.data); if (a.ref) memset(a.ref, 0, sizeof(long long)); free(a.ref); forge_arr_frees++;
    }
}

static void forge_fail(const char *msg) {
    fprintf(stderr, "qasida: runtime error: %s\n", msg);
    exit(1);
}

static long long forge_str_allocs = 0;
static long long forge_str_frees = 0;

static char *forge_copy_str(const char *s) {
    size_t n = strlen(s) + 1;
    char *p = (char *)malloc(n);
    if (!p) forge_fail("out of memory");
    memcpy(p, s, n);
    forge_str_allocs++;
    return p;
}

static void forge_free_str(char *p) {
    if (p) {
        memset(p, 0, strlen(p) + 1);
        free(p);
        forge_str_frees++;
    }
}

static char *forge_str_at(const char *s, long long i) {
    long long n = (long long)strlen(s);
    if (i < 0 || i >= n) forge_fail("string index out of bounds");
    char *p = (char *)malloc(2);
    if (!p) forge_fail("out of memory");
    p[0] = s[i];
    p[1] = '\0';
    forge_str_allocs++;
    return p;
}

static char *forge_str_at_fast(const char *s, long long i) {
    char *p = (char *)malloc(2);
    if (!p) forge_fail("out of memory");
    p[0] = s[i];
    p[1] = '\0';
    forge_str_allocs++;
    return p;
}

static char *forge_concat(const char *a, const char *b) {
    size_t na = strlen(a), nb = strlen(b);
    char *p = (char *)malloc(na + nb + 1);
    if (!p) forge_fail("out of memory");
    memcpy(p, a, na);
    memcpy(p + na, b, nb + 1);
    return p;
}

static long long forge_add(long long a, long long b) {
    long long r;
    if (__builtin_add_overflow(a, b, &r)) forge_fail("integer overflow");
    return r;
}
static long long forge_sub(long long a, long long b) {
    long long r;
    if (__builtin_sub_overflow(a, b, &r)) forge_fail("integer overflow");
    return r;
}
static long long forge_mul(long long a, long long b) {
    long long r;
    if (__builtin_mul_overflow(a, b, &r)) forge_fail("integer overflow");
    return r;
}
static long long forge_neg(long long a) {
    if (a == (-9223372036854775807LL - 1)) forge_fail("integer overflow");
    return -a;
}
static long long forge_div(long long a, long long b) {
    if (b == 0) forge_fail("division by zero");
    if (a == (-9223372036854775807LL - 1) && b == -1) forge_fail("integer overflow");
    return a / b;
}
static long long forge_mod(long long a, long long b) {
    if (b == 0) forge_fail("division by zero");
    if (a == (-9223372036854775807LL - 1) && b == -1) return 0;
    return a % b;
}

/* Weak references over [int] (Top-500 #26): a runtime table
   of non-owning handles. weak_new registers the array's
   current buffer without gaining a holder; upgrade reads
   it back while it is alive, or reports dead after the
   last strong holder freed it. Push is the only operation
   that moves the buffer or changes len/cap (index
   assignment writes in place), so forge_int_push refreshes
   live entries after every push; a copy-on-write push
   gives the pusher a new ref, so the old entries (still
   pointing at the original array) are correctly untouched.
   Entries for dead arrays keep their ref pointer nulled
   (never dereferenced again) and their data pointer
   stale-but-unread: upgrade checks alive first. The table
   itself is never freed (one entry per weak_new call, no
   user data) — the documented v1 limit. */
typedef struct { long long *ref; long long *data; long long len; long long cap; int alive; } ForgeWeakEntry;
static ForgeWeakEntry *forge_weak_table = NULL;
static long long forge_weak_len = 0;
static long long forge_weak_cap = 0;
static long long forge_weak_register(ForgeIntArray a) {
    if (forge_weak_len >= forge_weak_cap) {
        long long nc = forge_weak_cap ? forge_weak_cap * 2 : 8;
        ForgeWeakEntry *nt = (ForgeWeakEntry *)realloc(forge_weak_table, sizeof(ForgeWeakEntry) * (size_t)nc);
        if (!nt) forge_fail("out of memory");
        forge_weak_table = nt; forge_weak_cap = nc;
    }
    ForgeWeakEntry *e = &forge_weak_table[forge_weak_len];
    e->ref = a.ref; e->data = a.data; e->len = a.len; e->cap = a.cap; e->alive = 1;
    return forge_weak_len++;
}
static void forge_weak_sync(ForgeIntArray *a) {
    if (!a->ref) return;
    for (long long i = 0; i < forge_weak_len; i++) {
        ForgeWeakEntry *e = &forge_weak_table[i];
        if (e->alive && e->ref == a->ref) { e->data = a->data; e->len = a->len; e->cap = a->cap; }
    }
}
static void forge_weak_dead(long long *ref) {
    if (!ref) return;
    for (long long i = 0; i < forge_weak_len; i++) {
        ForgeWeakEntry *e = &forge_weak_table[i];
        if (e->alive && e->ref == ref) { e->alive = 0; e->ref = NULL; }
    }
}
static int forge_weak_get(long long id, ForgeIntArray *out) {
    if (id < 0 || id >= forge_weak_len) return 0;
    ForgeWeakEntry *e = &forge_weak_table[id];
    if (!e->alive) return 0;
    out->data = e->data; out->len = e->len; out->cap = e->cap; out->ref = e->ref;
    forge_arr_inc(out->ref);
    return 1;
}

#define FORGE_ARRAY_HELPERS(CT, ST, FN, COPY, SYNC) \
static void FN##_push(ST *a, CT v) { \
    if (a->ref && *a->ref > 1) { \
        /* Copy-on-write: this array is shared, so growing it
           in place would realloc the shared buffer and leave
           the other holders dangling on the freed pointer
           (a real double-free, found by the arena module).
           Duplicate the buffer under a fresh ref, then grow
           the private copy below. */ \
        long long oc = a->cap ? a->cap : 4; \
        CT *nd = (CT *)malloc(sizeof(CT) * (size_t)oc); \
        if (!nd) forge_fail("out of memory"); \
        for (long long i = 0; i < a->len; i++) nd[i] = COPY; \
        (*a->ref)--; \
        a->data = nd; a->cap = oc; a->ref = forge_arr_ref_new(); \
    } \
    if (a->len >= a->cap) { \
        long long nc = a->cap ? a->cap * 2 : 4; \
        CT *nd = (CT *)realloc(a->data, sizeof(CT) * (size_t)nc); \
        if (!nd) forge_fail("out of memory"); \
        a->data = nd; a->cap = nc; \
    } \
    a->data[a->len++] = v; \
    SYNC \
} \
static CT FN##_get(ST a, long long i) { \
    if (i < 0 || i >= a.len) forge_fail("array index out of bounds"); \
    return a.data[i]; \
} \
static void FN##_set(ST *a, long long i, CT v) { \
    if (i < 0 || i >= a->len) forge_fail("array index out of bounds"); \
    a->data[i] = v; \
}

FORGE_ARRAY_HELPERS(long long, ForgeIntArray, forge_int, a->data[i], forge_weak_sync(a);)
FORGE_ARRAY_HELPERS(double, ForgeFloatArray, forge_float, a->data[i], )
FORGE_ARRAY_HELPERS(bool, ForgeBoolArray, forge_bool, a->data[i], )
FORGE_ARRAY_HELPERS(char *, ForgeStrArray, forge_str, forge_copy_str(a->data[i]), )

static ForgeIntArray forge_range(long long n) {
    ForgeIntArray a;
    a.len = n > 0 ? n : 0;
    a.cap = a.len;
    a.data = a.len ? (long long *)malloc(sizeof(long long) * (size_t)a.len) : NULL;
    if (a.len && !a.data) forge_fail("out of memory");
    a.ref = forge_arr_ref_new();
    for (long long i = 0; i < a.len; i++) a.data[i] = i;
    return a;
}

static long long forge_clock_micros(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000LL + ts.tv_nsec / 1000;
}

static ForgeStrArray forge_args_global;

static bool forge_file_exists(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return false;
    fclose(f);
    return true;
}

static char *forge_read_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) forge_fail("cannot read file");
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    if (sz < 0) { fclose(f); forge_fail("cannot read file"); }
    fseek(f, 0, SEEK_SET);
    char *buf = (char *)malloc((size_t)sz + 1);
    if (!buf) { fclose(f); forge_fail("out of memory"); }
    size_t got = fread(buf, 1, (size_t)sz, f);
    buf[got] = '\0';
    fclose(f);
    return buf;
}

static char *forge_read_line(void) {
    static char buf[8192];
    if (!fgets(buf, sizeof(buf), stdin)) {
        char *empty = (char *)malloc(1);
        if (!empty) forge_fail("out of memory");
        empty[0] = '\0';
        return empty;
    }
    size_t n = strlen(buf);
    while (n > 0 && (buf[n-1] == '\n' || buf[n-1] == '\r')) buf[--n] = '\0';
    char *out = (char *)malloc(n + 1);
    if (!out) forge_fail("out of memory");
    memcpy(out, buf, n + 1);
    return out;
}

// Raw 32-bit memory access for bare-metal code (Phase B of the
// freestanding track). Volatile so the compiler never optimises an
// MMIO access away, and deliberately UNCHECKED in every mode: a raw
// address is unsafe by definition, and safe-mode checks cannot judge
// whether an address is a valid device register.
static int64_t forge_peek32(int64_t addr) {
    return (int64_t)(*(volatile uint32_t *)(uintptr_t)addr);
}

static int64_t forge_poke32(int64_t addr, int64_t val) {
    *(volatile uint32_t *)(uintptr_t)addr = (uint32_t)val;
    return val;
}

static bool forge_write_file(const char *path, const char *content) {
    FILE *f = fopen(path, "wb");
    if (!f) return false;
    fputs(content, f);
    fclose(f);
    return true;
}

static ForgeIntArray forge_read_bytes(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) forge_fail("cannot read file");
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    if (sz < 0) { fclose(f); forge_fail("cannot read file"); }
    fseek(f, 0, SEEK_SET);
    ForgeIntArray out; out.len = sz; out.cap = sz; out.ref = forge_arr_ref_new();
    out.data = sz ? (long long *)malloc(sizeof(long long) * (size_t)sz) : NULL;
    if (sz && !out.data) { fclose(f); forge_fail("out of memory"); }
    unsigned char *raw = sz ? (unsigned char *)malloc((size_t)sz) : NULL;
    size_t got = sz ? fread(raw, 1, (size_t)sz, f) : 0;
    fclose(f);
    for (long i = 0; i < (long)got; i++) out.data[i] = raw[i];
    out.len = (long long)got;
    if (raw) memset(raw, 0, (size_t)sz);
    free(raw);
    return out;
}

static bool forge_write_bytes(const char *path, ForgeIntArray data) {
    FILE *f = fopen(path, "wb");
    if (!f) { forge_int_array_free(data); return false; }
    bool ok = true;
    for (long long i = 0; i < data.len; i++) {
        unsigned char byte = (unsigned char)(data.data[i] & 0xFF);
        if (fwrite(&byte, 1, 1, f) != 1) { ok = false; break; }
    }
    fclose(f);
    /* Consume the param hold (mirrors Qasida fn params,
       which are freed at fn end): a fresh literal's hold
       is freed here, a shared array's param hold is just
       dec'd and the caller's hold survives. Without this,
       every write_bytes call leaked its input array. */
    forge_int_array_free(data);
    return ok;
}

/* Memory-mapped files (Top-500 #31): a runtime table
   of mappings, keyed by an int id (Qasida has no
   pointer type, so the mapping cannot be an array
   value — array frees call free(), which would
   corrupt mmap'd memory). Writes go through
   MAP_SHARED into the file; close munmaps (which
   flushes). The table itself is never freed (one
   entry per mmap_open, no user data) — the same
   documented limit as the weak table. */
#ifndef _WIN32
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
typedef struct { void *ptr; long long len; int fd; int alive; } ForgeMmapEntry;
static ForgeMmapEntry *forge_mmap_table = NULL;
static long long forge_mmap_len = 0;
static long long forge_mmap_cap = 0;
static long long forge_mmap_open(const char *path) {
    int fd = open(path, O_RDWR);
    if (fd < 0) forge_fail("mmap: cannot open file");
    struct stat st;
    if (fstat(fd, &st) != 0) { close(fd); forge_fail("mmap: cannot stat file"); }
    if (st.st_size == 0) { close(fd); forge_fail("mmap: cannot map an empty file"); }
    void *ptr = mmap(NULL, (size_t)st.st_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (ptr == MAP_FAILED) { close(fd); forge_fail("mmap: mapping failed"); }
    if (forge_mmap_len >= forge_mmap_cap) {
        long long nc = forge_mmap_cap ? forge_mmap_cap * 2 : 8;
        ForgeMmapEntry *nt = (ForgeMmapEntry *)realloc(forge_mmap_table, sizeof(ForgeMmapEntry) * (size_t)nc);
        if (!nt) { munmap(ptr, (size_t)st.st_size); close(fd); forge_fail("out of memory"); }
        forge_mmap_table = nt; forge_mmap_cap = nc;
    }
    ForgeMmapEntry *e = &forge_mmap_table[forge_mmap_len];
    e->ptr = ptr; e->len = (long long)st.st_size; e->fd = fd; e->alive = 1;
    return forge_mmap_len++;
}
static long long forge_mmap_get(long long id, long long i) {
    if (id < 0 || id >= forge_mmap_len || !forge_mmap_table[id].alive) forge_fail("mmap: unknown mapping");
    ForgeMmapEntry *e = &forge_mmap_table[id];
    if (i < 0 || i >= e->len) forge_fail("mmap index out of bounds");
    return (long long)((unsigned char *)e->ptr)[i];
}
static void forge_mmap_set(long long id, long long i, long long v) {
    if (id < 0 || id >= forge_mmap_len || !forge_mmap_table[id].alive) forge_fail("mmap: unknown mapping");
    ForgeMmapEntry *e = &forge_mmap_table[id];
    if (i < 0 || i >= e->len) forge_fail("mmap index out of bounds");
    ((unsigned char *)e->ptr)[i] = (unsigned char)(v & 0xFF);
}
static long long forge_mmap_grow(long long id, long long new_len) {
    if (id < 0 || id >= forge_mmap_len || !forge_mmap_table[id].alive) forge_fail("mmap: unknown mapping");
    ForgeMmapEntry *e = &forge_mmap_table[id];
    if (new_len <= e->len) forge_fail("mmap: new size must be larger than current size");
    if (ftruncate(e->fd, (off_t)new_len) != 0) forge_fail("mmap: cannot grow file");
    /* Map the grown file first: if this fails the old mapping
       is still valid (only the file grew). Then drop the old
       mapping and point the entry at the new one — the id
       stays the same, so holders keep working. */
    void *ptr = mmap(NULL, (size_t)new_len, PROT_READ | PROT_WRITE, MAP_SHARED, e->fd, 0);
    if (ptr == MAP_FAILED) forge_fail("mmap: remap failed");
    munmap(e->ptr, (size_t)e->len);
    e->ptr = ptr; e->len = new_len;
    return new_len;
}
static long long forge_mmap_get32(long long id, long long i) {
    if (id < 0 || id >= forge_mmap_len || !forge_mmap_table[id].alive) forge_fail("mmap: unknown mapping");
    ForgeMmapEntry *e = &forge_mmap_table[id];
    if (i < 0 || i > e->len - 4) forge_fail("mmap index out of bounds");
    /* Little-endian word, assembled byte by byte (no
       alignment assumption, portable across hosts). The
       value is zero-extended, matching forge_peek32. */
    unsigned char *b = (unsigned char *)e->ptr + i;
    return (long long)((uint32_t)b[0] | ((uint32_t)b[1] << 8) |
                       ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24));
}
static void forge_mmap_set32(long long id, long long i, long long v) {
    if (id < 0 || id >= forge_mmap_len || !forge_mmap_table[id].alive) forge_fail("mmap: unknown mapping");
    ForgeMmapEntry *e = &forge_mmap_table[id];
    if (i < 0 || i > e->len - 4) forge_fail("mmap index out of bounds");
    unsigned char *b = (unsigned char *)e->ptr + i;
    uint32_t w = (uint32_t)(v & 0xFFFFFFFFLL);
    b[0] = (unsigned char)(w & 0xFF); b[1] = (unsigned char)((w >> 8) & 0xFF);
    b[2] = (unsigned char)((w >> 16) & 0xFF); b[3] = (unsigned char)((w >> 24) & 0xFF);
}
static void forge_mmap_close(long long id) {
    if (id < 0 || id >= forge_mmap_len || !forge_mmap_table[id].alive) forge_fail("mmap: already closed");
    ForgeMmapEntry *e = &forge_mmap_table[id];
    munmap(e->ptr, (size_t)e->len);
    close(e->fd);
    e->alive = 0;
}
#else
static long long forge_mmap_open(const char *path) { (void)path; forge_fail("mmap is not supported on Windows in v1"); return -1; }
static long long forge_mmap_get(long long id, long long i) { (void)id; (void)i; forge_fail("mmap is not supported on Windows in v1"); return 0; }
static void forge_mmap_set(long long id, long long i, long long v) { (void)id; (void)i; (void)v; forge_fail("mmap is not supported on Windows in v1"); }
static void forge_mmap_close(long long id) { (void)id; forge_fail("mmap is not supported on Windows in v1"); }
static long long forge_mmap_grow(long long id, long long new_len) { (void)id; (void)new_len; forge_fail("mmap is not supported on Windows in v1"); return -1; }
static long long forge_mmap_get32(long long id, long long i) { (void)id; (void)i; forge_fail("mmap is not supported on Windows in v1"); return 0; }
static void forge_mmap_set32(long long id, long long i, long long v) { (void)id; (void)i; (void)v; forge_fail("mmap is not supported on Windows in v1"); }
#endif

static double forge_parse_float(const char *s) {
    char *end = NULL;
    double v = strtod(s, &end);
    if (end == s || *end != '\0') forge_fail("parse_float: not a number");
    return v;
}

static long long forge_parse_int(const char *s) {
    char *end = NULL;
    long long v = strtoll(s, &end, 10);
    if (end == s || *end != '\0') forge_fail("parse_int: not an integer");
    return v;
}

static ForgeStrArray forge_split(const char *s, const char *sep) {
    ForgeStrArray out; out.len = 0; out.cap = 8; out.ref = forge_arr_ref_new();
    out.data = (char **)malloc(sizeof(char *) * 8);
    size_t sl = strlen(sep);
    if (sl == 0) { forge_str_push(&out, forge_copy_str(s)); return out; }
    const char *start = s;
    const char *hit;
    while ((hit = strstr(start, sep)) != NULL) {
        size_t n = (size_t)(hit - start);
        char *piece = (char *)malloc(n + 1);
        memcpy(piece, start, n); piece[n] = '\0';
        forge_str_push(&out, piece);
        start = hit + sl;
    }
    forge_str_push(&out, forge_copy_str(start));
    return out;
}

static char *forge_join(ForgeStrArray arr, const char *sep) {
    size_t sl = strlen(sep), total = 1;
    for (long long i = 0; i < arr.len; i++) total += strlen(arr.data[i]) + sl;
    char *buf = (char *)malloc(total);
    buf[0] = '\0';
    for (long long i = 0; i < arr.len; i++) {
        if (i) strcat(buf, sep);
        strcat(buf, arr.data[i]);
    }
    return buf;
}

static char *forge_substr(const char *s, long long start, long long len) {
    long long sl = (long long)strlen(s);
    if (start < 0 || start > sl) forge_fail("substr: start out of range");
    if (len < 0) forge_fail("substr: negative length");
    if (start + len > sl) len = sl - start;
    char *buf = (char *)malloc((size_t)len + 1);
    memcpy(buf, s + start, (size_t)len); buf[len] = '\0';
    return buf;
}

static bool forge_starts_with(const char *s, const char *prefix) {
    return strncmp(s, prefix, strlen(prefix)) == 0;
}

static bool forge_ends_with(const char *s, const char *suffix) {
    size_t sl = strlen(s), fl = strlen(suffix);
    return sl >= fl && strcmp(s + sl - fl, suffix) == 0;
}

static char *forge_trim(const char *s) {
    while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r') s++;
    size_t n = strlen(s);
    while (n > 0 && (s[n-1] == ' ' || s[n-1] == '\t' || s[n-1] == '\n' || s[n-1] == '\r')) n--;
    char *buf = (char *)malloc(n + 1);
    memcpy(buf, s, n); buf[n] = '\0';
    return buf;
}

static pthread_t forge_threads[1024];
static long long forge_thread_count = 0;
static long long forge_thread_joined[1024];

static void forge_join_scope(long long start) {
    for (long long i = start; i < forge_thread_count; i++) {
        if (!forge_thread_joined[i]) {
            pthread_join(forge_threads[i], NULL);
            forge_thread_joined[i] = 1;
        }
    }
}
static void forge_join_threads(void) {
    forge_join_scope(0);
    forge_thread_count = 0;
    for (long long i = 0; i < 1024; i++) forge_thread_joined[i] = 0;
}

/* HTTPS proxy (CONNECT) support, native backend only.
   Env: https_proxy (else HTTPS_PROXY), form http://[user[:pass]@]host[:port]
   (bare host[:port] also works; port defaults to 8080). Only plain HTTP
   proxies are honoured; any other scheme is ignored and the connection
   goes direct, as before. no_proxy (else NO_PROXY) lists hosts that
   bypass the proxy: comma-separated, exact match, leading-dot suffix
   match, or "*" for all. Plain http:// URLs never use a proxy.
   Caller provides phost[256], pport[16], pauth[512]. */
static int forge_ieq_n(const char *a, const char *b, size_t n) {
    for (size_t i = 0; i < n; i++) {
        char ca = a[i], cb = b[i];
        if (ca >= 'A' && ca <= 'Z') ca = (char)(ca - 'A' + 'a');
        if (cb >= 'A' && cb <= 'Z') cb = (char)(cb - 'A' + 'a');
        if (ca != cb) return 0;
    }
    return 1;
}

static int forge_ieq(const char *a, const char *b) {
    size_t la = strlen(a), lb = strlen(b);
    return la == lb && forge_ieq_n(a, b, la);
}

static void forge_b64(const unsigned char *in, size_t len, char *out) {
    static const char tbl[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t i = 0, o = 0;
    while (i + 3 <= len) {
        out[o++] = tbl[in[i] >> 2];
        out[o++] = tbl[((in[i] & 3) << 4) | (in[i + 1] >> 4)];
        out[o++] = tbl[((in[i + 1] & 15) << 2) | (in[i + 2] >> 6)];
        out[o++] = tbl[in[i + 2] & 63];
        i += 3;
    }
    if (len - i == 1) {
        out[o++] = tbl[in[i] >> 2];
        out[o++] = tbl[(in[i] & 3) << 4];
        out[o++] = '='; out[o++] = '=';
    } else if (len - i == 2) {
        out[o++] = tbl[in[i] >> 2];
        out[o++] = tbl[((in[i] & 3) << 4) | (in[i + 1] >> 4)];
        out[o++] = tbl[(in[i + 1] & 15) << 2];
        out[o++] = '=';
    }
    out[o] = '\0';
}

/* 1 = use proxy (phost/pport/pauth filled, pauth may be ""), 0 = direct,
   -1 = proxy env present but unusable (caller fails loudly). */
static int forge_proxy_for(const char *host, char *phost, char *pport, char *pauth) {
    const char *np = getenv("no_proxy");
    if (!np) np = getenv("NO_PROXY");
    if (np) {
        const char *p = np;
        while (*p) {
            while (*p == ' ' || *p == '\t') p++;
            const char *e = p;
            while (*e && *e != ',') e++;
            size_t n = (size_t)(e - p);
            while (n > 0 && (p[n - 1] == ' ' || p[n - 1] == '\t')) n--;
            if (n == 1 && p[0] == '*') return 0;
            if (n > 0 && n < 256) {
                char entry[256];
                memcpy(entry, p, n); entry[n] = '\0';
                if (forge_ieq(entry, host)) return 0;
                if (entry[0] == '.') {
                    size_t hl = strlen(host), el = strlen(entry);
                    if ((hl >= el && forge_ieq_n(host + hl - el, entry, el)) ||
                        forge_ieq(entry + 1, host)) return 0;
                }
            }
            p = e;
            if (*p == ',') p++;
        }
    }
    const char *px = getenv("https_proxy");
    if (!px) px = getenv("HTTPS_PROXY");
    if (!px || !*px) return 0;
    const char *s = px;
    const char *scheme = strstr(px, "://");
    if (scheme) {
        if (!((scheme - px) == 4 && forge_ieq_n(px, "http", 4))) return 0;
        s = scheme + 3;
    }
    /* s = [user[:pass]@]host[:port][/...] */
    const char *slash = strchr(s, '/');
    size_t auth_len = slash ? (size_t)(slash - s) : strlen(s);
    if (auth_len == 0 || auth_len >= 512) return -1;
    char spec[512];
    memcpy(spec, s, auth_len); spec[auth_len] = '\0';
    pauth[0] = '\0';
    const char *at = strchr(spec, '@');
    const char *hp = spec;
    if (at) {
        size_t ulen = (size_t)(at - spec);
        if (ulen == 0 || ulen > 300) return -1;
        char userpass[301];
        memcpy(userpass, spec, ulen); userpass[ulen] = '\0';
        forge_b64((unsigned char *)userpass, ulen, pauth);
        hp = at + 1;
    }
    if (hp[0] == '[') return -1; /* IPv6 proxy literals not supported */
    if (hp[0] == '\0') return -1;
    const char *colon = strchr(hp, ':');
    if (colon) {
        size_t hn = (size_t)(colon - hp);
        if (hn == 0 || hn >= 256) return -1;
        memcpy(phost, hp, hn); phost[hn] = '\0';
        const char *pp = colon + 1;
        if (pp[0] == '\0' || strlen(pp) >= 16) return -1;
        strcpy(pport, pp);
    } else {
        if (strlen(hp) >= 256) return -1;
        strcpy(phost, hp);
        strcpy(pport, "8080");
    }
    return 1;
}

static char *forge_https_get(const char *url) {
#if (defined(_WIN32) && !defined(FORGE_HAVE_OPENSSL)) || defined(FORGE_NO_OPENSSL)
    (void)url;
    forge_fail("https_get: HTTPS is not supported in this build (rebuild with OpenSSL to enable it)");
    return NULL;
#else
    forge_sock_init();
    // https://host[:port]/path, with certificate verification on.
    const char *rest = url + 8;
    const char *slash = strchr(rest, '/');
    char hostport[256];
    const char *path = "/";
    if (slash) {
        size_t hl = (size_t)(slash - rest);
        if (hl >= sizeof(hostport)) forge_fail("https_get: host too long");
        memcpy(hostport, rest, hl); hostport[hl] = '\0';
        path = slash;
    } else {
        if (strlen(rest) >= sizeof(hostport)) forge_fail("https_get: host too long");
        strcpy(hostport, rest);
    }
    char host[256]; char portstr[16] = "443";
    char *colon = strchr(hostport, ':');
    if (colon) { size_t hl = (size_t)(colon - hostport); memcpy(host, hostport, hl); host[hl] = '\0'; strcpy(portstr, colon + 1); }
    else strcpy(host, hostport);
    /* Proxy: only HTTPS uses CONNECT. Plain http:// stays direct. */
    char phost[256]; char pport[16]; char pauth[512];
    int px = forge_proxy_for(host, phost, pport, pauth);
    if (px < 0) forge_fail("https_get: cannot parse https_proxy");
    const char *conn_host = (px == 1) ? phost : host;
    const char *conn_port = (px == 1) ? pport : portstr;
    struct addrinfo hints; memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC; hints.ai_socktype = SOCK_STREAM;
    struct addrinfo *res = NULL;
    if (getaddrinfo(conn_host, conn_port, &hints, &res) != 0) forge_fail("https_get: cannot resolve host");
    forge_sock_t sock = FORGE_SOCK_INVALID;
    for (struct addrinfo *ai = res; ai != NULL; ai = ai->ai_next) {
        sock = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (sock == FORGE_SOCK_INVALID) continue;
        if (connect(sock, ai->ai_addr, ai->ai_addrlen) == 0) break;
        forge_sock_close(sock); sock = FORGE_SOCK_INVALID;
    }
    freeaddrinfo(res);
    if (sock == FORGE_SOCK_INVALID) forge_fail("https_get: cannot connect");
    if (px == 1) {
        /* CONNECT handshake; afterwards the socket carries TLS as usual. */
        char creq[2048];
        int cn;
        if (pauth[0])
            cn = snprintf(creq, sizeof(creq), "CONNECT %s:%s HTTP/1.1\r\nHost: %s:%s\r\nProxy-Authorization: Basic %s\r\n\r\n", host, portstr, host, portstr, pauth);
        else
            cn = snprintf(creq, sizeof(creq), "CONNECT %s:%s HTTP/1.1\r\nHost: %s:%s\r\n\r\n", host, portstr, host, portstr);
        if (cn < 0 || (size_t)cn >= sizeof(creq)) { forge_sock_close(sock); forge_fail("https_get: proxy CONNECT request too long"); }
        if (send(sock, creq, (size_t)cn, 0) < 0) { forge_sock_close(sock); forge_fail("https_get: proxy CONNECT failed"); }
        char resp[8192]; size_t rlen = 0; int done = 0;
        while (rlen + 1024 < sizeof(resp)) {
            ssize_t got = recv(sock, resp + rlen, sizeof(resp) - rlen - 1, 0);
            if (got <= 0) break;
            rlen += (size_t)got; resp[rlen] = '\0';
            if (strstr(resp, "\r\n\r\n")) { done = 1; break; }
        }
        if (!done) { forge_sock_close(sock); forge_fail("https_get: proxy CONNECT failed (no response)"); }
        int status = 0;
        if (sscanf(resp, "HTTP/%*s %d", &status) != 1 || status != 200) { forge_sock_close(sock); forge_fail("https_get: proxy CONNECT refused"); }
    }
    SSL_CTX *ctx = SSL_CTX_new(TLS_client_method());
    if (!ctx) { forge_sock_close(sock); forge_fail("https_get: cannot create SSL context"); }
    SSL_CTX_set_default_verify_paths(ctx);
    SSL *ssl = SSL_new(ctx);
    SSL_set_tlsext_host_name(ssl, host);
    SSL_set_fd(ssl, (int)sock);
    if (SSL_connect(ssl) != 1) { SSL_free(ssl); SSL_CTX_free(ctx); forge_sock_close(sock); forge_fail("https_get: TLS handshake failed"); }
    if (SSL_get_verify_result(ssl) != X509_V_OK) { SSL_free(ssl); SSL_CTX_free(ctx); forge_sock_close(sock); forge_fail("https_get: certificate verification failed"); }
    char req[1024];
    snprintf(req, sizeof(req), "GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n", path, host);
    SSL_write(ssl, req, (int)strlen(req));
    size_t cap = 8192, len = 0;
    char *buf = (char *)malloc(cap);
    int got;
    while ((got = SSL_read(ssl, buf + len, (int)(cap - len - 1))) > 0) {
        len += (size_t)got;
        if (len + 1024 >= cap) { cap *= 2; buf = (char *)realloc(buf, cap); }
    }
    SSL_free(ssl); SSL_CTX_free(ctx); forge_sock_close(sock);
    buf[len] = '\0';
    char *sep = strstr(buf, "\r\n\r\n");
    if (!sep) forge_fail("https_get: bad HTTP response");
    return forge_copy_str(sep + 4);
#endif
}

static char *forge_http_get(const char *url) {
    forge_sock_init();
    if (strncmp(url, "https://", 8) == 0) return forge_https_get(url);
    if (strncmp(url, "http://", 7) != 0) forge_fail("http_get: URL must start with http:// or https://");
    const char *rest = url + 7;
    const char *slash = strchr(rest, '/');
    char hostport[256];
    const char *path = "/";
    if (slash) {
        size_t hl = (size_t)(slash - rest);
        if (hl >= sizeof(hostport)) forge_fail("http_get: host too long");
        memcpy(hostport, rest, hl); hostport[hl] = '\0';
        path = slash;
    } else {
        if (strlen(rest) >= sizeof(hostport)) forge_fail("http_get: host too long");
        strcpy(hostport, rest);
    }
    char host[256]; char portstr[16] = "80";
    char *colon = strchr(hostport, ':');
    if (colon) { size_t hl = (size_t)(colon - hostport); memcpy(host, hostport, hl); host[hl] = '\0'; strcpy(portstr, colon + 1); }
    else strcpy(host, hostport);
    struct addrinfo hints; memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC; hints.ai_socktype = SOCK_STREAM;
    struct addrinfo *res = NULL;
    if (getaddrinfo(host, portstr, &hints, &res) != 0) forge_fail("http_get: cannot resolve host");
    forge_sock_t sock = FORGE_SOCK_INVALID;
    for (struct addrinfo *ai = res; ai != NULL; ai = ai->ai_next) {
        sock = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (sock == FORGE_SOCK_INVALID) continue;
        if (connect(sock, ai->ai_addr, ai->ai_addrlen) == 0) break;
        forge_sock_close(sock); sock = FORGE_SOCK_INVALID;
    }
    freeaddrinfo(res);
    if (sock == FORGE_SOCK_INVALID) forge_fail("http_get: cannot connect");
    char req[1024];
    snprintf(req, sizeof(req), "GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n", path, host);
    if (send(sock, req, strlen(req), 0) < 0) { forge_sock_close(sock); forge_fail("http_get: send failed"); }
    size_t cap = 8192, len = 0;
    char *buf = (char *)malloc(cap);
    ssize_t got;
    while ((got = recv(sock, buf + len, cap - len - 1, 0)) > 0) {
        len += (size_t)got;
        if (len + 1024 >= cap) { cap *= 2; buf = (char *)realloc(buf, cap); }
    }
    forge_sock_close(sock);
    buf[len] = '\0';
    char *sep = strstr(buf, "\r\n\r\n");
    if (!sep) forge_fail("http_get: bad HTTP response");
    return forge_copy_str(sep + 4);
}

/* Minimal HTTP server (native backend only). One request per
   connection, single read up to 8191 bytes, no TLS, no chunked
   bodies, IPv4 0.0.0.0. Enough for small services, CLIs with a
   status page, and webhooks; not a production web server. */
static long long forge_http_listen(long long port) {
    forge_sock_init();
    forge_sock_t fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd == FORGE_SOCK_INVALID) forge_fail("http_listen: socket failed");
    int one = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, (const char *)&one, sizeof(one));
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons((unsigned short)port);
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) != 0) { forge_sock_close(fd); forge_fail("http_listen: bind failed (port in use?)"); }
    if (listen(fd, 16) != 0) { forge_sock_close(fd); forge_fail("http_listen: listen failed"); }
    return fd;
}
static long long forge_http_accept(long long fd) {
    forge_sock_t client = accept((forge_sock_t)fd, NULL, NULL);
    if (client == FORGE_SOCK_INVALID) forge_fail("http_accept: accept failed");
    return client;
}
static char *forge_http_read_request(long long client) {
    char *buf = (char *)malloc(8192);
    ssize_t n = recv((forge_sock_t)client, buf, 8191, 0);
    if (n < 0) { memset(buf, 0, 8192); free(buf); forge_fail("http_read_request: recv failed"); }
    buf[n] = '\0';
    return buf;
}
static long long forge_http_send_response(long long client, long long status, const char *reason, const char *body) {
    char head[256];
    int hl = snprintf(head, sizeof(head), "HTTP/1.1 %lld %s\r\nContent-Type: text/plain\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n", status, reason, strlen(body));
    if (hl < 0 || hl >= (int)sizeof(head)) { forge_sock_close((forge_sock_t)client); forge_fail("http_respond: header failed"); }
    if (send((forge_sock_t)client, head, (size_t)hl, 0) < 0) { forge_sock_close((forge_sock_t)client); forge_fail("http_respond: send failed"); }
    if (send((forge_sock_t)client, body, strlen(body), 0) < 0) { forge_sock_close((forge_sock_t)client); forge_fail("http_respond: send failed"); }
    forge_sock_close((forge_sock_t)client);
    return (long long)hl + (long long)strlen(body);
}
static long long forge_http_respond(long long client, const char *body) {
    return forge_http_send_response(client, 200, "OK", body);
}
static long long forge_http_respond_status(long long client, long long status, const char *body) {
    const char *reason = "OK";
    if (status == 404) reason = "Not Found";
    else if (status == 500) reason = "Internal Server Error";
    else if (status == 400) reason = "Bad Request";
    else if (status == 401) reason = "Unauthorized";
    else if (status == 409) reason = "Conflict";
    else if (status == 201) reason = "Created";
    return forge_http_send_response(client, status, reason, body);
}
static long long forge_http_close(long long fd) {
    forge_sock_close((forge_sock_t)fd);
    return 0;
}

/* GPU-style parallel kernels, run on CPU threads here (no GPU in
   this VM, no CUDA/OpenCL). Each kernel splits its work into
   blocks, one pthread per block, like a GPU grid. Results are
   bit-identical to the serial version; no speedup is claimed
   on this 2-core VM, only correctness and the kernel shape. */
typedef struct { ForgeFloatArray a; ForgeFloatArray b; long long lo; long long hi; double partial; } ForgeDotTask;
static void *forge_dot_worker(void *arg) {
    ForgeDotTask *t = (ForgeDotTask *)arg;
    double s = 0.0;
    for (long long i = t->lo; i < t->hi; i++) s += t->a.data[i] * t->b.data[i];
    t->partial = s;
    return NULL;
}
static double forge_parallel_dot(ForgeFloatArray a, ForgeFloatArray b) {
    if (a.len != b.len) forge_fail("parallel_dot: length mismatch");
    if (a.len == 0) return 0.0;
    int nthreads = a.len < 4 ? (int)a.len : 4;
    pthread_t th[4];
    ForgeDotTask tasks[4];
    long long chunk = (a.len + nthreads - 1) / nthreads;
    for (int i = 0; i < nthreads; i++) {
        tasks[i].a = a; tasks[i].b = b;
        tasks[i].lo = (long long)i * chunk;
        tasks[i].hi = tasks[i].lo + chunk > a.len ? a.len : tasks[i].lo + chunk;
        tasks[i].partial = 0.0;
        pthread_create(&th[i], NULL, forge_dot_worker, &tasks[i]);
    }
    double total = 0.0;
    for (int i = 0; i < nthreads; i++) { pthread_join(th[i], NULL); total += tasks[i].partial; }
    return total;
}
typedef struct { ForgeFloatArray a; ForgeFloatArray b; ForgeFloatArray out; long long n; long long rlo; long long rhi; } ForgeMatTask;
static void *forge_mat_worker(void *arg) {
    ForgeMatTask *t = (ForgeMatTask *)arg;
    for (long long r = t->rlo; r < t->rhi; r++) {
        for (long long c = 0; c < t->n; c++) {
            double s = 0.0;
            for (long long k = 0; k < t->n; k++) s += t->a.data[r * t->n + k] * t->b.data[k * t->n + c];
            t->out.data[r * t->n + c] = s;
        }
    }
    return NULL;
}
static ForgeFloatArray forge_parallel_matmul(ForgeFloatArray a, ForgeFloatArray b, long long n) {
    ForgeFloatArray out;
    out.len = n * n; out.cap = n * n;
    out.data = (double *)malloc(sizeof(double) * (size_t)(n * n > 0 ? n * n : 1));
    if (!out.data) forge_fail("out of memory");
    out.ref = forge_arr_ref_new();
    if (n == 0) return out;
    int nthreads = n < 4 ? (int)n : 4;
    pthread_t th[4];
    ForgeMatTask tasks[4];
    long long chunk = (n + nthreads - 1) / nthreads;
    for (int i = 0; i < nthreads; i++) {
        tasks[i].a = a; tasks[i].b = b; tasks[i].out = out; tasks[i].n = n;
        tasks[i].rlo = (long long)i * chunk;
        tasks[i].rhi = tasks[i].rlo + chunk > n ? n : tasks[i].rlo + chunk;
        pthread_create(&th[i], NULL, forge_mat_worker, &tasks[i]);
    }
    for (int i = 0; i < nthreads; i++) pthread_join(th[i], NULL);
    return out;
}

"""


# Freestanding prelude (Phase C): NO libc at all. Only <stdint.h>
# and <stdbool.h>, which are freestanding-compatible headers: they
# define types, not linkable symbols. Checked arithmetic via gcc
# builtins (no libm, no libc). forge_fail halts: there is no OS
# to exit to. Array struct types are included so unused array/str
# parameters still declare, but no allocator exists: strings and
# arrays have no values in freestanding v1 (see the gen_expr guard).
FREESTANDING_HEADER = r"""#include <stdint.h>
#include <stdbool.h>

typedef struct { int64_t *data; int64_t len; int64_t cap; int64_t *ref; } ForgeIntArray;
typedef struct { double *data; int64_t len; int64_t cap; int64_t *ref; } ForgeFloatArray;
typedef struct { bool *data; int64_t len; int64_t cap; int64_t *ref; } ForgeBoolArray;
typedef struct { char **data; int64_t len; int64_t cap; int64_t *ref; } ForgeStrArray;

static void forge_fail(const char *msg) {
    (void)msg;
    for (;;) {}
}
static int64_t forge_add(int64_t a, int64_t b) {
    int64_t r;
    if (__builtin_add_overflow(a, b, &r)) forge_fail("integer overflow");
    return r;
}
static int64_t forge_sub(int64_t a, int64_t b) {
    int64_t r;
    if (__builtin_sub_overflow(a, b, &r)) forge_fail("integer overflow");
    return r;
}
static int64_t forge_mul(int64_t a, int64_t b) {
    int64_t r;
    if (__builtin_mul_overflow(a, b, &r)) forge_fail("integer overflow");
    return r;
}
static int64_t forge_neg(int64_t a) {
    if (a == (-9223372036854775807LL - 1)) forge_fail("integer overflow");
    return -a;
}
static int64_t forge_div(int64_t a, int64_t b) {
    if (b == 0) forge_fail("division by zero");
    if (a == (-9223372036854775807LL - 1) && b == -1) forge_fail("integer overflow");
    return a / b;
}
static int64_t forge_mod(int64_t a, int64_t b) {
    if (b == 0) forge_fail("division by zero");
    if (a == (-9223372036854775807LL - 1) && b == -1) return 0;
    return a % b;
}
static int64_t forge_peek32(int64_t addr) {
    return (int64_t)(*(volatile uint32_t *)(uintptr_t)addr);
}
static int64_t forge_poke32(int64_t addr, int64_t val) {
    *(volatile uint32_t *)(uintptr_t)addr = (uint32_t)val;
    return val;
}

"""


def c_type(t):
    # Newtypes map to their underlying C type: a newtype value IS
    # its underlying value at runtime; only the checker keeps them
    # apart. The map is set by Codegen.__init__ (the compiler is
    # single-threaded and every compilation builds a Codegen).
    t = _resolve_newtype(t)
    if is_union_type(t):
        return union_c_name(t)
    if is_opaque_type(t):
        return opaque_c_name(t)
    if t in C_SCALAR:
        return C_SCALAR[t]
    from .readonly import is_readonly, readonly_inner
    if is_readonly(t):
        # A view shares the underlying array's C layout.
        return c_type(readonly_inner(t))
    from .tuples import is_tuple_type, tuple_c_name
    if is_tuple_type(t):
        return tuple_c_name(t)
    if t.startswith("[") and t.endswith("]"):
        from .sizedarrays import is_sized_array, sized_elem
        if is_sized_array(t):
            # v1 representation is the dynamic array of the same
            # element type; the size lives in the type, not the C
            # layout, so every downstream use sees the dynamic form.
            return c_type(f"[{sized_elem(t)}]")
        inner = t[1:-1]
        if inner in ARRAY_STRUCT:
            return ARRAY_STRUCT[inner]
        if inner == "?":
            return t
        if is_fixed_int(inner):
            # Arrays of fixed-width integers are a later slice:
            # their element helpers do not exist yet.
            raise ForgeError(f"arrays of {inner} are not supported in v1")
        if inner.startswith("["):
            # Nested array: ForgeArray_<inner C array type>.
            return f"ForgeArray_{c_type(inner)}"
        if "<" in inner:
            from .generics import mangle_type
            return f"ForgeArray_{mangle_type(inner)}"
        return f"ForgeArray_{inner}"
    # Generic struct types use their mangled concrete name.
    if "<" in t:
        from .generics import mangle_type
        return mangle_type(t)
    # Struct types use their typedef name directly.
    return t


def elem_of(arr_type):
    from .sizedarrays import array_elem
    return array_elem(arr_type) if arr_type.startswith("[") else "int"


_NEWTYPE_MAP = {}


def _resolve_newtype(t):
    if t in _NEWTYPE_MAP:
        return _resolve_newtype(_NEWTYPE_MAP[t])
    from .readonly import is_readonly, readonly_inner
    if is_readonly(t):
        return f"readonly {_resolve_newtype(readonly_inner(t))}"
    if t.startswith("[") and t.endswith("]"):
        from .sizedarrays import is_sized_array, sized_elem, sized_len
        if is_sized_array(t):
            return f"[{_resolve_newtype(sized_elem(t))}; {sized_len(t)}]"
        return "[" + _resolve_newtype(t[1:-1]) + "]"
    if "<" in t:
        from .generics import parse_generic
        g = parse_generic(t)
        if g is not None:
            base, args = g
            return base + "<" + ", ".join(_resolve_newtype(a) for a in args) + ">"
    return t


class Codegen:
    def __init__(self, program, mode="safe", debug=False, freestanding=False):
        self.program = program
        self.mode = mode
        self.freestanding = freestanding
        # --debug: emit #line directives mapping
        # generated C back to .fg files/lines, so
        # gdb (and readelf's line table) step through
        # Qasida source instead of generated C.
        self.debug = debug
        self.current_file = ""
        self.func_ret = {fn.name: fn.ret for fn in program.funcs}
        self.func_params = {fn.name: list(fn.params) for fn in program.funcs}
        self.func_is_extern = {fn.name: bool(getattr(fn, "is_extern", False))
                               for fn in program.funcs}
        self.try_counter = 0
        self.assign_counter = 0
        self.owned_stack = [{}]
        self.moved_fields = set()
        self.structs = {sd.name: dict(sd.fields)
                        for sd in (getattr(program, "structs", None) or [])}
        self.newtype_targets = {nd.name: nd.target
                                for nd in (getattr(program, "newtypes", None) or [])}
        global _NEWTYPE_MAP
        _NEWTYPE_MAP = dict(self.newtype_targets)
        self.enums = {ed.name: list(ed.variants)
                      for ed in (getattr(program, "enums", None) or [])}
        self.enum_templates = {}
        for ed in (getattr(program, "enums", None) or []):
            payloads = getattr(ed, "variant_payloads", None) or {}
            self.enum_templates[ed.name] = (
                list(getattr(ed, "type_params", None) or []),
                {v: payloads.get(v) for v in ed.variants},
                list(ed.variants))
        self.lines = []
        self.indent = 0
        self.arr_counter = 0
        self.loop_counter = 0
        self.loop_frames = []
        self.spawn_counter = 0
        self.current_fn = None
        self._types = {}
        # Check-elimination state (native codegen only, safe mode only
        # for the checks themselves; the state is reset per statement
        # for the duplicate cache and per function for the facts).
        # _check_cache: identical checked operations already proven
        # in-bounds / non-overflowing within the current statement,
        # so a repeat may use the unchecked (fast-mode) emission.
        # _facts: int variable intervals proven by if-guards, used to
        # skip overflow/div-zero checks that cannot fire.
        # _let_stack: names bound by `let` inside each open branch,
        # so a branch-local binding never leaks into join facts.
        self._check_cache = {}
        self._facts = {}
        self._let_stack = []
        # Structured concurrency: open scopes as (start-variable,
        # loop depth at entry). A scope joins every task spawned
        # while it is open (watermark into forge_threads); the
        # joined flags keep nested scopes and the main-exit join
        # from joining any thread twice.
        self.scope_stack = []
        self.scope_counter = 0

    def owned_add(self, name, typ="str"):
        self.owned_stack[-1][name] = typ

    def moved_flag(self, name):
        """C variable holding a variable's runtime moved flag
        (move v2): 1 once a conditional move of it has run."""
        return f"__forge_moved_{name}"

    def _field_path(self, expr):
        """Dotted path for a field access rooted at a variable,
        or None for any other base (mirrors checker)."""
        parts = []
        node = expr
        while isinstance(node, A.FieldAccess):
            parts.append(node.field)
            node = node.base
        if not isinstance(node, A.Var):
            return None
        parts.append(node.name)
        return ".".join(reversed(parts))

    def emit_guarded(self, name, code):
        """Emit a free statement string only when `name`'s moved
        flag is clear (move v2): a variable moved in a branch or
        loop has no value left to free on the path that moved it,
        but still does on the path that did not."""
        if code:
            self.emit(f"if (!{self.moved_flag(name)}) {{ {code} }}")

    def owned_forget(self, name):
        """Drop a variable from ownership tracking: its hold moved
        elsewhere, so scope-end frees must skip it. Only for
        straight-line moves (the checker annotates conditional
        moves, which use the runtime moved flag instead): a
        straight-line forget always executes before any later
        free of that frame — no path can free a hold that
        already moved, or leak one that never did."""
        for s in reversed(self.owned_stack):
            if name in s:
                del s[name]
                return

    def owned_contains(self, name):
        return any(name in s for s in reversed(self.owned_stack))

    def owned_type(self, name):
        """Declared type of an owned variable, or None when untracked."""
        for s in reversed(self.owned_stack):
            if name in s:
                return s[name]
        return None

    # ---- Union values (Top-500 #7, v1) ----
    # A union value is a C struct { long long tag; union { ... } payload }.
    # Construction wraps a member value into that struct; copying a
    # union only deep-copies when the tag says str; freeing only
    # frees when the tag says str. Non-str unions need no runtime
    # calls at all, so they work in freestanding mode too.

    def union_wrap(self, value_code, value_type, union_type, copy_str=False):
        """Wrap a member value into its union struct (fresh value).

        copy_str deep-copies a str payload first: without it the
        union would share the string with its source and both
        owners would free it.
        """
        idx = union_members(union_type).index(value_type)
        cname = union_c_name(union_type)
        if copy_str:
            value_code = f"forge_copy_str({value_code})"
        return (f"(({cname}){{.tag = {idx}, "
                f".payload = {{._{idx} = ({value_code})}}}})")

    def union_copy_stmt(self, temp_code, union_type):
        """Statement deep-copying a union temp's str payload in place.

        Empty when the union has no str member. The temp holds a
        shallow copy already; only the str payload needs its own
        copy, and only when the tag says the value is a str.
        """
        s = union_str_index(union_type)
        if s is None:
            return ""
        return (f"if ({temp_code}.tag == {s}) "
                f"{temp_code}.payload._{s} = forge_copy_str({temp_code}.payload._{s});")

    def union_free_code(self, var_code, union_type):
        """Statement freeing a union value's str payload, or ''."""
        s = union_str_index(union_type)
        if s is None:
            return ""
        return (f"if ({var_code}.tag == {s}) "
                f"forge_free_str({var_code}.payload._{s});")

    # ---- Fixed-width integers (Top-500 #9, v1) ----
    # Checked arithmetic by widening: small widths compute in long
    # long / unsigned long long (where they cannot overflow), then
    # range-check and narrow; u64 uses the overflow builtins
    # directly. Shifts check the count; division checks zero and
    # signed-min / -1. Bitwise and comparison need nothing: C
    # promotion plus narrowing at the use site is exact.

    def _fx_temp(self):
        self.assign_counter += 1
        return f"__forge_fx{self.assign_counter}"

    def fixed_checked_binop(self, op, left_code, right_code, t):
        """Safe-mode checked BinOp on a fixed-width integer type."""
        ct = FIXED_C_TYPES[t]
        signed = t in ("i8", "i16", "i32")
        if op in ("+", "-", "*"):
            if t == "u64":
                builtin = {"+": "__builtin_add_overflow",
                           "-": "__builtin_sub_overflow",
                           "*": "__builtin_mul_overflow"}[op]
                tmp = self._fx_temp()
                return (f"({{unsigned long long {tmp}; "
                        f"if ({builtin}((unsigned long long)({left_code}), "
                        f"(unsigned long long)({right_code}), &{tmp})) "
                        f"forge_fail(\"integer overflow\"); {tmp};}})")
            w = "long long" if signed else "unsigned long long"
            tmp = self._fx_temp()
            lo, hi = fixed_range(t)
            return (f"({{{w} {tmp} = ({w})({left_code}) {op} ({w})({right_code}); "
                    f"if ({tmp} < {lo} || {tmp} > {hi}) "
                    f"forge_fail(\"integer overflow\"); ({ct})({tmp});}})")
        if op == "/":
            if signed:
                dt = self._fx_temp()
                nt = self._fx_temp()
                lo, _hi = fixed_range(t)
                return (f"({{long long {dt} = (long long)({right_code}); "
                        f"if ({dt} == 0) forge_fail(\"division by zero\"); "
                        f"long long {nt} = (long long)({left_code}); "
                        f"if ({nt} == {lo} && {dt} == -1) "
                        f"forge_fail(\"integer overflow\"); "
                        f"({ct})({nt} / {dt});}})")
            dt = self._fx_temp()
            return (f"({{unsigned long long {dt} = "
                    f"(unsigned long long)({right_code}); "
                    f"if ({dt} == 0) forge_fail(\"division by zero\"); "
                    f"({ct})((unsigned long long)({left_code}) / {dt});}})")
        if op == "%":
            w = "long long" if signed else "unsigned long long"
            dt = self._fx_temp()
            return (f"({{{w} {dt} = ({w})({right_code}); "
                    f"if ({dt} == 0) forge_fail(\"division by zero\"); "
                    f"({left_code} % {right_code});}})")
        if op in ("<<", ">>"):
            width = FIXED_WIDTHS[t]
            at = self._fx_temp()
            if op == "<<":
                uct = {"i8": "uint8_t", "i16": "uint16_t", "i32": "uint32_t",
                       "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t",
                       "u64": "uint64_t"}[t]
                return (f"({{long long {at} = (long long)({right_code}); "
                        f"if ({at} < 0 || {at} >= {width}) "
                        f"forge_fail(\"shift count out of range\"); "
                        f"({ct})(({uct})({left_code}) << {at});}})")
            return (f"({{long long {at} = (long long)({right_code}); "
                    f"if ({at} < 0 || {at} >= {width}) "
                    f"forge_fail(\"shift count out of range\"); "
                    f"(({left_code}) >> {at});}})")
        raise ForgeError(f"no checked form for '{op}' on {t}")

    def int_cast_code(self, value_code, from_type, to_type):
        """Cast between int types: free when widening, checked
        when narrowing (a value outside the target range fails)."""
        ct = c_type(to_type)
        if to_type == "int":
            tlo, thi = (-9223372036854775808, 9223372036854775807)
        else:
            tlo, thi = fixed_range(to_type)
        if from_type == "int":
            flo, fhi = (-9223372036854775808, 9223372036854775807)
        else:
            flo, fhi = fixed_range(from_type)
        if flo >= tlo and fhi <= thi:
            return f"({ct})({value_code})"
        w = "unsigned long long" if from_type == "u64" else "long long"
        tmp = self._fx_temp()
        if w == "unsigned long long" and tlo <= 0:
            # Unsigned values are never below a non-positive bound;
            # comparing them against a negative bound in C would
            # convert the bound to a huge unsigned value and fail
            # every cast, so only the upper bound is checked.
            cond = f"{tmp} > {thi}"
        else:
            cond = f"{tmp} < {tlo} || {tmp} > {thi}"
        return (f"({{{w} {tmp} = ({w})({value_code}); "
                f"if ({cond}) "
                f"forge_fail(\"integer overflow\"); ({ct})({tmp});}})")

    def float_to_int_cast(self, value_code, to_type):
        """Cast from float to an int type: checked in safe mode,
        plain truncating C cast in fast mode. Safe mode fails
        when the float is outside the target range, or NaN or
        infinite (NaN fails both comparisons, so it fails the
        check too). The upper bound is exclusive: max+1 is a
        power of two for every int width, so it is exactly
        representable as a double."""
        ct = c_type(to_type)
        if self.mode != "safe":
            return f"({ct})({value_code})"
        if to_type == "int":
            tlo, thi = (-9223372036854775808, 9223372036854775807)
        else:
            tlo, thi = fixed_range(to_type)
        lo = float(tlo)
        hi = float(thi + 1)
        tmp = self._fx_temp()
        return (f"({{ double {tmp} = ({value_code}); "
                f"if (!({tmp} >= {lo!r} && {tmp} < {hi!r})) "
                f"forge_fail(\"float to int cast out of range\"); "
                f"({ct})({tmp});}})")

    def never_wrap(self, code, expected):
        """Wrap a never-typed value with a dummy of the expected
        C type: the diverging call never returns, so the dummy
        never runs, but C needs a value of the right type here."""
        return f"({{ {code}; ({c_type(expected)})0; }})"

    def is_fresh_union(self, expr):
        """A union value fresh from its producer (no copy needed)."""
        if isinstance(expr, (A.Call, A.MethodCall)):
            return True
        return False

    # ---- Opaque values (Top-500 #8, v1) ----
    # An opaque value is a C struct { long long tag; union { ... }
    # payload }, the tag selecting the implementation in
    # impl-block order for the trait, the payload a union over the
    # implementing structs. Method calls, copies, and frees all
    # dispatch on the tag.

    def opaque_wrap(self, value_code, struct_type, opaque_type):
        """Wrap a concrete struct value into its opaque struct."""
        trait = opaque_trait(opaque_type)
        impls = impls_for_trait(self.program, trait)
        idx = impls.index(struct_type)
        cname = opaque_c_name(opaque_type)
        return (f"(({cname}){{.tag = {idx}, "
                f".payload = {{._{idx} = ({value_code})}}}})")

    def opaque_convert(self, code, value_type, opaque_type, expr):
        """Convert a value to an opaque type at a site.

        A concrete struct implementing the trait wraps into the
        tagged struct (gaining independent fields when shared); a
        shared value already of the opaque type gains an
        independent copy through the generated helper.
        """
        if value_type in impls_for_trait(self.program,
                                          opaque_trait(opaque_type)):
            if not self.is_fresh_struct(expr):
                self.assign_counter += 1
                n = self.assign_counter
                own = self.struct_own_code(f"__forge_op{n}", value_type)
                return (f"({{{c_type(value_type)} __forge_op{n} = {code}; "
                        f"{own} {self.opaque_wrap(f'__forge_op{n}', value_type, opaque_type)};}})")
            return self.opaque_wrap(code, value_type, opaque_type)
        if value_type == opaque_type and not self.is_fresh_union(expr):
            return f"forge_copy_{opaque_c_name(opaque_type)}({code})"
        return code

    def owned_all(self):
        """Owned variables currently in scope, innermost first, deduped: [(name, type)]."""
        seen = set()
        out = []
        for s in reversed(self.owned_stack):
            for name, typ in s.items():
                if name not in seen:
                    seen.add(name)
                    out.append((name, typ))
        return out

    def drop_hook_name(self, typ):
        """Mangled drop-hook name for a struct type, or None.

        The hook fires only when the struct's whole field tree
        is ownable by struct_own_code (scalars, str, arrays,
        structs, tuples — no union/opaque field anywhere):
        struct_own_code does not own union/opaque payloads
        while struct_free_code DOES free them, so hooking
        such a struct could double-free the caller's payload.
        Generics are skipped in v1. The checker already
        enforces the drop signature (one receiver param,
        void return); codegen re-checks it defensively.
        """
        resolved = self.resolve_newtype(typ)
        if "<" in resolved:
            return None
        fname = f"{resolved}__drop"
        params = self.func_params.get(fname)
        if params is None or len(params) != 1 or params[0][1] != resolved:
            return None
        if self.func_ret.get(fname) != "void":
            return None
        from .tuples import tuple_elems, is_tuple_type
        seen = set()

        def ownable(t):
            if t in ("int", "float", "bool", "str"):
                return True
            if is_union_type(t) or is_opaque_type(t):
                return False
            if is_tuple_type(t):
                return all(ownable(e) for e in tuple_elems(t))
            if self.is_array_type(t):
                inner = t[1:-1]
                return ownable(inner)
            if self.is_struct_type(t):
                name = self.struct_type_name(t)
                if name in seen:
                    return True
                seen.add(name)
                return all(ownable(ft)
                           for ft in self.structs.get(name, {}).values())
            return False

        if not ownable(resolved):
            return None
        return fname

    def emit_drop_hook(self, name, typ):
        """Call Struct__drop on an independently owned copy of
        `name` before it is freed (Top-500 #33). The copy
        pattern is the proven call-arg one: str fields are
        deep-copied, array refs inc'd, so the callee's
        param free on return balances the incs here, and
        the original's free afterwards is untouched.
        """
        fname = self.drop_hook_name(typ)
        if fname is None:
            return
        resolved = self.resolve_newtype(typ)
        self.assign_counter += 1
        n = self.assign_counter
        tmp = f"__forge_drop{n}"
        own = self.struct_own_code(tmp, resolved)
        self.emit(f"{{ {c_type(resolved)} {tmp} = {name}; {own} "
                  f"{fname}({tmp}); }}")

    def _emit_free_one(self, name, typ):
        # A conditional move leaves the flag as the only record
        # of whether this variable still owns its value: skip
        # the whole free when the flag says it moved (move v2).
        # Every owned variable gets a flag at its declaration
        # (Let, parameter, match binding), so this is always
        # in scope wherever the variable can be freed.
        self.emit(f"if (!{self.moved_flag(name)}) {{")
        self.indent += 1
        if typ == "str":
            self.emit(f"forge_free_str({name});")
        elif is_union_type(typ):
            code = self.union_free_code(name, typ)
            if code:
                self.emit(code)
        elif is_opaque_type(typ):
            self.emit(f"forge_free_{opaque_c_name(typ)}({name});")
        elif is_tuple_type(typ):
            self.emit(self.tuple_free_code(name, typ))
        elif self.is_array_type(typ):
            self.emit(self.array_free_code(name, typ))
        elif self.is_struct_type(typ):
            if any(p.startswith(name + ".") for p in self.moved_fields):
                # A field of this struct moved away: the drop
                # hook must not read it, and the free must skip
                # it (the new owner frees it) — move v2.
                self.emit_struct_free(name, typ, path=name)
            else:
                # Destructor hook first: fields must still be alive
                # when drop reads them (Top-500 #33). Never for the
                # drop method's own receiver parameter — that would
                # recurse forever (see gen_func's drop_receiver).
                if getattr(self, "drop_receiver", None) != name:
                    self.emit_drop_hook(name, typ)
                self.emit_struct_free(name, typ)
        self.indent -= 1
        self.emit("}")

    def emit_free_owned(self):
        if self.freestanding:
            # No owned values can exist: strings/arrays have no
            # values in freestanding v1, so there is nothing to free
            # (unused str/array parameters are dead declarations).
            return
        for name, typ in self.owned_all():
            self._emit_free_one(name, typ)

    def emit_free_frame(self):
        # Free only the current (innermost) ownership frame: the
        # variables declared inside one block / loop body / if arm.
        # Previously these frames were popped without freeing, so
        # every array or struct created inside a loop body leaked
        # once per iteration — the leak that OOM-killed long
        # training runs (each step's ~221k-node tape). Function
        # exit and Return already free all frames, so a Return
        # inside a body makes this code unreachable, never a
        # double free. Values that escape the frame via Assign
        # or Return already gained their own reference/copy.
        frame = self.owned_stack[-1] if self.owned_stack else {}
        # A variable assigned inside this frame may also sit in an
        # outer frame (Assign re-adds its target to the current
        # frame even when declared outside it). Free only names
        # this frame truly owns: the outer frame frees the rest
        # when it ends, and freeing both would double-free.
        outer = set()
        for f in self.owned_stack[:-1]:
            outer.update(f.keys())
        for name, typ in frame.items():
            if name not in outer:
                self._emit_free_one(name, typ)

    def emit_free_frames_downto(self, idx):
        # Free every ownership frame from the innermost down to frame
        # idx (inclusive), without popping: used by `break`, which must
        # free the loop body's locals (and any nested block's locals)
        # that the normal block-end frees would otherwise handle, since
        # breaking jumps past them. A name is freed by exactly one
        # frame: the frame below it that also holds it wins, matching
        # emit_free_frame — so process innermost-first and skip names
        # held by any frame below the one being freed.
        for i in range(len(self.owned_stack) - 1, idx - 1, -1):
            frame = self.owned_stack[i]
            below = set()
            for f in self.owned_stack[:i]:
                below.update(f.keys())
            for name, typ in frame.items():
                if name not in below:
                    self._emit_free_one(name, typ)

    def is_array_type(self, t):
        t = self.resolve_newtype(t)
        from .sizedarrays import is_sized_array, sized_elem
        from .readonly import is_readonly, readonly_inner
        if is_readonly(t):
            return self.is_array_type(readonly_inner(t))
        if is_sized_array(t):
            return self.is_array_type(f"[{sized_elem(t)}]")
        if not (t.startswith("[") and t.endswith("]")):
            return False
        inner = t[1:-1]
        return (inner in ("int", "float", "bool", "str")
                or self.is_struct_type(inner) or self.is_array_type(inner))

    def array_free_code(self, var_code, typ):
        """C statements freeing the array value var_code of type typ
        (refcounted; nested arrays free element arrays first)."""
        from .sizedarrays import is_sized_array, sized_elem
        from .readonly import is_readonly, readonly_inner
        if is_readonly(typ):
            typ = readonly_inner(typ)
        if is_sized_array(typ):
            typ = f"[{sized_elem(typ)}]"
        inner = typ[1:-1]
        if inner in ("int", "float", "bool", "str"):
            fn = {"int": "forge_int_array_free", "float": "forge_float_array_free",
                  "bool": "forge_bool_array_free", "str": "forge_str_array_free"}[inner]
            return f"{fn}({var_code});"
        if self.is_struct_type(inner):
            return f"forge_{self.struct_type_name(inner)}_array_free({var_code});"
        # Nested array: refcount the outer, free each element array,
        # then the outer buffer.
        i = f"__forge_fi{self.assign_counter}"
        self.assign_counter += 1
        inner_code = self.array_free_code(f"{var_code}.data[{i}]", inner)
        return (f"if ({var_code}.ref && --(*{var_code}.ref) == 0) {{ "
                f"for (long long {i} = 0; {i} < {var_code}.len; {i}++) {{ {inner_code} }} "
                f"if ({var_code}.data) memset({var_code}.data, 0, (size_t){var_code}.cap * sizeof(*{var_code}.data)); free({var_code}.data); if ({var_code}.ref) memset({var_code}.ref, 0, sizeof(long long)); free({var_code}.ref); forge_arr_frees++; }}")

    def struct_type_name(self, t):
        if "<" in t:
            from .generics import mangle_type
            return mangle_type(t)
        return t

    def resolve_newtype(self, t):
        targets = self.newtype_targets
        if t in targets:
            return self.resolve_newtype(targets[t])
        from .readonly import is_readonly, readonly_inner
        if is_readonly(t):
            return f"readonly {self.resolve_newtype(readonly_inner(t))}"
        if t.startswith("[") and t.endswith("]"):
            from .sizedarrays import is_sized_array, sized_elem, sized_len
            if is_sized_array(t):
                return f"[{self.resolve_newtype(sized_elem(t))}; {sized_len(t)}]"
            return "[" + self.resolve_newtype(t[1:-1]) + "]"
        if "<" in t:
            from .generics import parse_generic
            g = parse_generic(t)
            if g is not None:
                base, args = g
                return base + "<" + ", ".join(self.resolve_newtype(a)
                                              for a in args) + ">"
        return t

    def is_struct_type(self, t):
        t = self.resolve_newtype(t)
        if not t or t in ("int", "float", "bool", "str", "void"):
            return False
        if self.is_array_type(t):
            return False
        return self.struct_type_name(t) in self.structs

    def struct_own_code(self, var_code, t):
        """C statements making a struct value independently owned:
        deep-copy str fields, gain array references, recurse into nested structs."""
        fields = self.structs.get(self.struct_type_name(t), {})
        parts = []
        for fname, ftype in fields.items():
            code = f"{var_code}.{fname}"
            if ftype == "str":
                parts.append(f"{code} = forge_copy_str({code});")
            elif self.is_array_type(ftype):
                parts.append(f"forge_arr_inc({code}.ref);")
            elif self.is_struct_type(ftype):
                parts.append(self.struct_own_code(code, ftype))
        return " ".join(parts)

    def emit_struct_own(self, var_code, t):
        code = self.struct_own_code(var_code, t)
        if code:
            self.emit(code)

    def tuple_own_code(self, var_code, t):
        """C statements making a tuple value independently owned:
        copy str elements, gain array references, recurse into
        nested struct/tuple elements (mirrors struct_own_code)."""
        from .tuples import tuple_elems, is_tuple_type
        parts = []
        for i, et in enumerate(tuple_elems(t)):
            code = f"{var_code}._{i}"
            if et == "str":
                parts.append(f"{code} = forge_copy_str({code});")
            elif is_union_type(et):
                ucopy = self.union_copy_stmt(code, et)
                if ucopy:
                    parts.append(ucopy)
            elif is_opaque_type(et):
                parts.append(f"{code} = forge_copy_{opaque_c_name(et)}({code});")
            elif self.is_array_type(et):
                parts.append(f"forge_arr_inc({code}.ref);")
            elif self.is_struct_type(et):
                parts.append(self.struct_own_code(code, et))
            elif is_tuple_type(et):
                parts.append(self.tuple_own_code(code, et))
        return " ".join(parts)

    def emit_tuple_own(self, var_code, t):
        code = self.tuple_own_code(var_code, t)
        if code:
            self.emit(code)

    def tuple_free_code(self, var_code, t):
        """C statements freeing a tuple value's owned elements
        (mirrors struct_free_code)."""
        from .tuples import tuple_elems, is_tuple_type
        parts = []
        for i, et in enumerate(tuple_elems(t)):
            code = f"{var_code}._{i}"
            if et == "str":
                parts.append(f"forge_free_str({code});")
            elif is_union_type(et):
                ufree = self.union_free_code(code, et)
                if ufree:
                    parts.append(ufree)
            elif is_opaque_type(et):
                parts.append(f"forge_free_{opaque_c_name(et)}({code});")
            elif self.is_array_type(et):
                parts.append(self.array_free_code(code, et))
            elif self.is_struct_type(et):
                parts.append(self.struct_free_code(code, et))
            elif is_tuple_type(et):
                parts.append(self.tuple_free_code(code, et))
        return " ".join(parts)

    def emit_tuple_free(self, var_code, t):
        code = self.tuple_free_code(var_code, t)
        if code:
            self.emit(code)

    def is_fresh_tuple(self, expr):
        if isinstance(expr, (A.TupleLit, A.Call, A.MethodCall)):
            return True
        return False

    def struct_free_code(self, var_code, t, path=None):
        """Free code for a struct value's owned fields. When
        `path` is the variable's dotted path, fields recorded
        in moved_fields (move v2: straight-line field moves)
        are skipped — their new owner frees them."""
        fields = self.structs.get(self.struct_type_name(t), {})
        parts = []
        for fname, ftype in fields.items():
            full = f"{path}.{fname}" if path is not None else None
            if full is not None and full in self.moved_fields:
                continue
            code = f"{var_code}.{fname}"
            if ftype == "str":
                parts.append(f"forge_free_str({code});")
            elif is_union_type(ftype):
                ufree = self.union_free_code(code, ftype)
                if ufree:
                    parts.append(ufree)
            elif is_opaque_type(ftype):
                # Unreachable in checked code (opaque struct fields
                # are rejected), but free correctly if one appears.
                parts.append(f"forge_free_{opaque_c_name(ftype)}({code});")
            elif self.is_array_type(ftype):
                parts.append(self.array_free_code(code, ftype))
            elif self.is_struct_type(ftype):
                parts.append(self.struct_free_code(code, ftype, path=full))
        return " ".join(parts)

    def emit_struct_free(self, var_code, t, path=None):
        code = self.struct_free_code(var_code, t, path=path)
        if code:
            self.emit(code)

    def is_fresh_struct(self, expr):
        if isinstance(expr, A.StructLit):
            return True
        if isinstance(expr, A.MethodCall):
            # A method returning a struct is fresh, like a call
            # returning a struct: the result is a new owned value.
            from .traits import mangle
            struct_t = self.expr_type(expr.base)
            mangled = mangle(struct_t, expr.method)
            rt = self.func_ret.get(mangled)
            return bool(rt and self.is_struct_type(rt))
        if isinstance(expr, A.Call):
            if expr.name == "move":
                # A moved value transfers its hold: the receiving
                # site must not inc it (see the move branch in
                # gen_expr, which also forgets the source).
                return True
            if expr.name == "try_alloc":
                # A try_alloc Result is a new owned value (the
                # statement expression builds it fresh); the
                # receiving site must not copy it.
                return True
            rt = self.func_ret.get(expr.name)
            if rt and self.is_struct_type(rt):
                return True
            return False
        if isinstance(expr, A.Index) and self.is_struct_type(self.expr_type(expr)):
            # A struct-array get already returns an owned copy.
            return True
        return False

    def is_fresh_array(self, expr):
        """True if the expression creates a fresh array (ref=1, sole owner)."""
        if isinstance(expr, A.ArrayLit):
            return True
        if isinstance(expr, A.Call):
            if expr.name in ("range", "split", "parallel_matmul", "args", "move", "read_bytes"):
                return True
            if self.func_ret.get(expr.name) and self.is_array_type(self.func_ret[expr.name]):
                return True
            return False
        return False

    def is_fresh_str(self, expr):
        """True if the expression already returns a fresh, owned string
        (a user-function return, a str helper, or string concat),
        so taking it as-is does not leak or double-own."""
        if isinstance(expr, A.Call):
            if expr.name in ("read_file", "read_line", "join", "substr", "trim", "http_get", "http_read_request", "move"):
                return True
            if self.func_ret.get(expr.name) == "str" and not self.func_is_extern.get(expr.name):
                return True
            return False
        if isinstance(expr, A.BinOp) and expr.op == "+" and self.expr_type(expr.left) == "str":
            return True
        if isinstance(expr, A.Index) and self.expr_type(expr.base) == "str":
            return True
        return False

    def collect_spawns(self, block, out):
        for stmt in block.stmts:
            if isinstance(stmt, A.Spawn):
                out.append(stmt.call)
            elif isinstance(stmt, A.Block):
                self.collect_spawns(stmt, out)
            elif isinstance(stmt, A.Scope):
                self.collect_spawns(stmt.body, out)
            elif isinstance(stmt, A.If):
                self.collect_spawns(stmt.then, out)
                if stmt.els is not None:
                    self.collect_spawns(stmt.els, out)
            elif isinstance(stmt, A.While):
                self.collect_spawns(stmt.body, out)
            elif isinstance(stmt, A.For):
                self.collect_spawns(stmt.body, out)
            elif isinstance(stmt, A.Match):
                for _pat, _bind, body in stmt.arms:
                    self.collect_spawns(body, out)

    def _enum_variant_map(self):
        """variant -> (enum name, tag, template payload type)."""
        if not hasattr(self, "_variant_map_cache"):
            m = {}
            for enum_name, (_params, payloads, variants) in self.enum_templates.items():
                for i, v in enumerate(variants):
                    m[v] = (enum_name, i, payloads[v])
            self._variant_map_cache = m
        return self._variant_map_cache

    def enum_concrete_info(self, t):
        """(base, {variant: (tag, payload type)}) for a concrete enum type."""
        from .generics import parse_generic, substitute_type
        if t in self.enum_templates and not self.enum_templates[t][0]:
            _params, payloads, variants = self.enum_templates[t]
            return t, {v: (i, payloads[v]) for i, v in enumerate(variants)}
        g = parse_generic(t)
        if g is not None and g[0] in self.enum_templates:
            base, args = g
            params, payloads, variants = self.enum_templates[base]
            if len(args) != len(params) or "?" in args:
                return None
            bindings = dict(zip(params, args))
            return base, {v: (i, substitute_type(payloads[v], bindings) if payloads[v] is not None else None)
                          for i, v in enumerate(variants)}
        return None

    def collect_enum_types(self):
        """All concrete enum types used, from signatures, fields, and infer types."""
        out = set()
        for fn in self.program.funcs:
            if getattr(fn, "type_params", None):
                continue
            for _n, pt in fn.params:
                if self.enum_concrete_info(pt):
                    out.add(pt)
            if self.enum_concrete_info(fn.ret):
                out.add(fn.ret)
        for sd in (getattr(self.program, "structs", None) or []):
            if getattr(sd, "type_params", None):
                continue
            for _f, ft in sd.fields:
                if self.enum_concrete_info(ft):
                    out.add(ft)
        for t in self._types.values():
            if self.enum_concrete_info(t):
                out.add(t)
        return out

    def collect_nested_array_types(self):
        """All nested array types used (signatures, fields, Let
        annotations, and infer types), innermost first."""
        out = set()

        def add(t):
            # Add t and every nested array prefix it contains.
            # Sized sizes are stripped first: the C layout is the
            # dynamic form, so only dynamic types get typedefs.
            from .sizedarrays import normalize_sized
            t = normalize_sized(t)
            while t.startswith("[") and t.endswith("]"):
                inner = t[1:-1]
                if inner.startswith("["):
                    out.add(t)
                t = inner

        def walk_block(block):
            for s in getattr(block, "stmts", []):
                ann = getattr(s, "ann", None)
                if ann:
                    add(ann)
                if isinstance(s, A.Block):
                    walk_block(s)
                for attr in ("body", "then", "els"):
                    b = getattr(s, attr, None)
                    if b is not None:
                        walk_block(b)
                for _pat, _bind, arm_body in getattr(s, "arms", []) or []:
                    walk_block(arm_body)

        for fn in self.program.funcs:
            if getattr(fn, "type_params", None):
                continue
            for _n, pt in fn.params:
                add(pt)
            add(fn.ret)
            if getattr(fn, "body", None) is not None:
                walk_block(fn.body)
        for sd in (getattr(self.program, "structs", None) or []):
            if getattr(sd, "type_params", None):
                continue
            fields = sd.fields
            pairs = fields.items() if isinstance(fields, dict) else fields
            for _fname, ft in pairs:
                add(ft)
        for t in self._types.values():
            add(t)
        # Innermost first: a typedef may only reference types
        # already defined (scalar arrays are in the preamble,
        # struct arrays are emitted just before this section).
        return sorted(out, key=lambda t: t.count("["))

    def generate(self):
        self.lines.append(FREESTANDING_HEADER if self.freestanding else HEADER)
        # Skip generic templates: only concrete structs are emitted.
        # self.structs is built from program.structs, which includes
        # templates; rebuild it from concrete structs only.
        concrete_structs = {}
        for sd in (getattr(self.program, "structs", None) or []):
            if getattr(sd, "type_params", None):
                continue
            concrete_structs[sd.name] = dict(sd.fields)
        self.structs = concrete_structs
        # Enums: non-payload enums as C enums; payload enums as
        # tag+union structs, one per concrete type.
        for name, variants in self.enums.items():
            _params, payloads, _vs = self.enum_templates.get(name, ([], {}, variants))
            if any(p is not None for p in payloads.values()):
                continue
            self.emit(f"typedef enum {{ {', '.join(variants)} }} {name};")
        concrete_enums = self.collect_enum_types()
        for t in sorted(concrete_enums):
            info = self.enum_concrete_info(t)
            if info is None:
                continue
            base, variant_info = info
            _params, payloads, _vs = self.enum_templates[base]
            if not any(p is not None for p in payloads.values()):
                # Non-payload generic enum: alias the base C enum.
                from .generics import mangle_type
                if "<" in t:
                    self.emit(f"typedef {base} {mangle_type(t)};")
                continue
            from .generics import mangle_type
            cname = mangle_type(t)
            self.emit(f"typedef struct {cname} {cname};")
            self.emit(f"struct {cname} {{ int tag;")
            union_fields = []
            for v, (tag, pt) in variant_info.items():
                if pt is not None:
                    union_fields.append(f"{c_type(pt)} payload_{v};")
            if union_fields:
                self.emit("    union {")
                for uf in union_fields:
                    self.emit(f"        {uf}")
                self.emit("    } payload;")
            self.emit("};")
        if self.enums:
            self.lines.append("")
        for name in self.structs:
            self.emit(f"typedef struct {name} {name};")
        # Union types: one tag+payload struct per distinct union
        # spelling, payload fields by member index (_0, _1, ...).
        from .unions import find_unions
        union_types = find_unions(self.program)
        if self.freestanding:
            for ut in union_types:
                if union_str_index(ut) is not None:
                    raise ForgeError(
                        f"unions with str members need the hosted runtime "
                        f"(not in freestanding v1); union '{ut}' has one",
                        0, 0)
        for ut in union_types:
            cname = union_c_name(ut)
            self.emit(f"typedef struct {cname} {cname};")
            self.emit(f"struct {cname} {{ long long tag;")
            self.emit("    union {")
            for i, m in enumerate(union_members(ut)):
                self.emit(f"        {C_SCALAR[m]} _{i};")
            self.emit("    } payload;")
            self.emit("};")
        if union_types:
            self.lines.append("")
        # Ranges: a lazy start/end pair, no array. The struct is
        # emitted unconditionally (it is two longs, and range
        # values may appear anywhere a scalar can).
        self.emit("typedef struct { long long start; long long end; } ForgeRange;")
        self.lines.append("")
        # Composite bodies (structs, tuples, opaques) in
        # dependency order: a value field needs its type
        # complete, so a struct with a tuple field needs that
        # tuple first, a tuple with a struct element needs
        # that struct first, and so on. Forward references
        # between structs (A has a B field, B defined later)
        # work for the same reason. Arrays hold pointers, so
        # they never force an order. A cycle (a struct
        # containing itself through tuples) is infinitely
        # sized and fails here with a clear error.
        from .tuples import find_tuples, tuple_elems, tuple_c_name
        tuple_types = find_tuples(self.program)
        # weak_upgrade returns (bool, [int]); a builtin call's
        # return type is spelled nowhere, so the tuple walk
        # never sees it — union it in explicitly when any
        # weak call exists.
        from .weaks import uses_weak
        if uses_weak(self.program) and "(bool, [int])" not in tuple_types:
            tuple_types.append("(bool, [int])")
        if self.freestanding:
            for tt in tuple_types:
                for e in tuple_elems(tt):
                    # Nested tuples are separate entries in
                    # tuple_types, so their elements are checked
                    # at their own level.
                    if e == "str" or self.is_array_type(e):
                        raise ForgeError(
                            f"tuples with str/array elements need the hosted runtime "
                            f"(not in freestanding v1); tuple '{tt}' has one",
                            0, 0)
        opaque_traits = []
        for idf in (getattr(self.program, "impls", None) or []):
            if getattr(idf, "trait", None) is not None \
                    and idf.trait not in opaque_traits:
                opaque_traits.append(idf.trait)
        for tt in tuple_types:
            self.emit(f"typedef struct {tuple_c_name(tt)} {tuple_c_name(tt)};")
        for trait in opaque_traits:
            self.emit(f"typedef struct Opaque_{trait} Opaque_{trait};")
        # Array typedefs before composite bodies (fix track:
        # nested arrays as struct fields). A struct body holds
        # array fields BY VALUE (ForgeArray_...), so their
        # typedefs must precede the body — the old order emitted
        # them after the bodies, and `[[int]]` (or `[Point]`)
        # fields failed with "unknown type name". Per-struct
        # array typedefs first (nested typedefs reference them),
        # then nested array typedefs innermost-first. The
        # per-struct helpers stay after the bodies (they access
        # fields, so they need complete struct types); only the
        # typedef lines move. All forward declarations above
        # precede this block, so tuple/opaque element pointers
        # are declared. Residual, documented: enum payload
        # structs with nested-array payloads still need their
        # typedef before the enum section, which precedes this
        # block — that corner is not covered here.
        for name in self.structs:
            self.emit(f"typedef struct {{ {name} *data; long long len; long long cap; "
                      f"long long *ref; }} ForgeArray_{name};")
        nested_early = self.collect_nested_array_types()
        from .sizedarrays import array_elem as _array_elem
        for t in nested_early:
            self.emit(f"typedef struct {{ {c_type(_array_elem(t))} *data; long long len; "
                      f"long long cap; long long *ref; }} {c_type(t)};")
        if self.structs or nested_early:
            self.lines.append("")
        nodes = []
        for name, fields in self.structs.items():
            nodes.append(("struct", name, list(fields.values())))
        for tt in tuple_types:
            nodes.append(("tuple", tuple_c_name(tt), tuple_elems(tt)))
        for trait in opaque_traits:
            nodes.append(("opaque", f"Opaque_{trait}",
                          impls_for_trait(self.program, trait)))
        body_names = {cname for _kind, cname, _deps in nodes}
        emitted = set()
        order = []
        remaining = list(nodes)
        while remaining:
            picked = None
            for node in remaining:
                _kind, cname, ftypes = node
                deps = set()
                for ft in ftypes:
                    ct = c_type(ft)
                    if ct in body_names:
                        deps.add(ct)
                if deps <= emitted:
                    picked = node
                    break
            if picked is None:
                cycle = ", ".join(c for _k, c, _d in remaining)
                raise ForgeError(f"cyclic type definition involving {cycle}; "
                                 f"a type cannot contain itself by value",
                                 0, 0)
            remaining.remove(picked)
            emitted.add(picked[1])
            order.append(picked)
        struct_fields = {name: fields for name, fields in self.structs.items()}
        for kind, cname, ftypes in order:
            if kind == "struct":
                self.emit(f"struct {cname} {{")
                for fname, ftype in struct_fields[cname].items():
                    self.emit(f"    {c_type(ftype)} {fname};")
                self.emit("};")
            elif kind == "tuple":
                self.emit(f"struct {cname} {{")
                for i, e in enumerate(ftypes):
                    self.emit(f"    {c_type(e)} _{i};")
                self.emit("};")
            else:
                trait = cname[len("Opaque_"):]
                impls = impls_for_trait(self.program, trait)
                self.emit(f"struct {cname} {{ long long tag;")
                self.emit("    union {")
                for i, st in enumerate(impls):
                    self.emit(f"        {st} _{i};")
                self.emit("    } payload;")
                self.emit("};")
        if order:
            self.lines.append("")
        # Per-struct array types and helpers: a [Point] value is a
        # ForgeArray_Point (same refcounted layout as scalar arrays).
        # Element get returns an independently owned copy; set frees
        # the old element before storing; push appends as-is (the
        # caller owns the value first, mirroring str push).
        # Freestanding (Top-500 #39): arrays of structs cannot exist
        # (every array value is rejected at check time), so these
        # heap-array helpers are dead code — and they break the
        # build, because they use memset/free/size_t, none of which
        # exists under the freestanding header. Skip them; a plain
        # struct value is a stack value and needs none of this.
        for name in (self.structs if not self.freestanding else ()):
            arr_t = f"ForgeArray_{name}"
            self.emit(f"static void forge_{name}_array_free({arr_t} a) {{")
            self.emit("    if (a.ref && --(*a.ref) == 0) {")
            self.emit("        for (long long i = 0; i < a.len; i++) {")
            free_code = self.struct_free_code("a.data[i]", name)
            if free_code:
                self.emit(f"            {free_code}")
            self.emit("        }")
            self.emit("        if (a.data) memset(a.data, 0, (size_t)a.cap * sizeof(*a.data)); free(a.data); if (a.ref) memset(a.ref, 0, sizeof(long long)); free(a.ref); forge_arr_frees++;")
            self.emit("    }")
            self.emit("}")
            for suffix, check in (("", True), ("_fast", False)):
                self.emit(f"static {name} forge_{name}_get{suffix}({arr_t} a, long long i) {{")
                if check:
                    self.emit('    if (i < 0 || i >= a.len) forge_fail("array index out of bounds");')
                self.emit(f"    {name} v = a.data[i];")
                own_code = self.struct_own_code("v", name)
                if own_code:
                    self.emit(f"    {own_code}")
                self.emit("    return v;")
                self.emit("}")
                self.emit(f"static void forge_{name}_set{suffix}({arr_t} *a, long long i, {name} v) {{")
                if check:
                    self.emit('    if (i < 0 || i >= a->len) forge_fail("array index out of bounds");')
                old_free = self.struct_free_code("a->data[i]", name)
                if old_free:
                    self.emit(f"    {old_free}")
                self.emit("    a->data[i] = v;")
                self.emit("}")
            self.emit(f"static void forge_{name}_push({arr_t} *a, {name} v) {{")
            own = self.struct_own_code("nd[i]", name)
            self.emit("    if (a->ref && *a->ref > 1) {")
            self.emit("        /* Copy-on-write (fix track): this array is")
            self.emit("           shared, so growing it in place would")
            self.emit("           realloc the shared buffer and leave the")
            self.emit("           other holders dangling — the two-sided")
            self.emit("           probe double-freed in realloc. Detach")
            self.emit("           first, mirroring FORGE_ARRAY_HELPERS:")
            self.emit("           fresh buffer, copy slots gaining")
            self.emit("           ownership of their fields each (the")
            self.emit("           struct free path frees one hold per")
            self.emit("           slot, so the inc keeps the counts")
            self.emit("           exact), drop this holder's count on")
            self.emit("           the old buffer without freeing it. */")
            self.emit("        long long oc = a->cap ? a->cap : 4;")
            self.emit(f"        {name} *nd = ({name} *)malloc(sizeof({name}) * (size_t)oc);")
            self.emit('        if (!nd) forge_fail("out of memory");')
            self.emit("        for (long long i = 0; i < a->len; i++) {")
            self.emit(f"            nd[i] = a->data[i];{(' ' + own) if own else ''}")
            self.emit("        }")
            self.emit("        (*a->ref)--;")
            self.emit("        a->data = nd; a->cap = oc; a->ref = forge_arr_ref_new();")
            self.emit("    }")
            self.emit("    if (a->len >= a->cap) {")
            self.emit("        long long nc = a->cap ? a->cap * 2 : 4;")
            self.emit(f"        {name} *nd = ({name} *)realloc(a->data, sizeof({name}) * (size_t)nc);")
            self.emit('        if (!nd) forge_fail("out of memory");')
            self.emit("        a->data = nd; a->cap = nc;")
            self.emit("    }")
            self.emit("    a->data[a->len++] = v;")
            self.emit("}")
        if self.structs:
            self.lines.append("")
        for fn in self.program.funcs:
            if getattr(fn, "type_params", None):
                continue
            if fn.name != "main":
                sig = self.c_sig_extern(fn) if getattr(fn, "is_extern", False) else self.c_sig(fn)
                self.emit(f"{sig};")
        self.lines.append("")
        # Opaque copy/free helpers, one per trait with
        # implementations: both dispatch on the tag, reusing the
        # struct own/free code for the active implementation.
        for trait in opaque_traits:
            impls = impls_for_trait(self.program, trait)
            cname = f"Opaque_{trait}"
            self.emit(f"static {cname} forge_copy_{cname}({cname} v) {{")
            self.emit("    switch (v.tag) {")
            for i, st in enumerate(impls):
                own = self.struct_own_code(f"v.payload._{i}", st)
                self.emit(f"    case {i}:")
                if own:
                    for line in own.strip().split("\n"):
                        self.emit(f"        {line.strip()}")
                self.emit("        break;")
            self.emit("    }")
            self.emit("    return v;")
            self.emit("}")
            self.emit(f"static void forge_free_{cname}({cname} v) {{")
            self.emit("    switch (v.tag) {")
            for i, st in enumerate(impls):
                free = self.struct_free_code(f"v.payload._{i}", st)
                self.emit(f"    case {i}:")
                if free:
                    self.emit(f"        {free}")
                self.emit("        break;")
            self.emit("    }")
            self.emit("}")
        if opaque_traits:
            self.lines.append("")
        # Thread wrappers for every spawned function (collected once).
        spawns = []
        for fn in self.program.funcs:
            if getattr(fn, "type_params", None):
                continue
            if not getattr(fn, "is_extern", False):
                self.collect_spawns(fn.body, spawns)
        seen_wrappers = set()
        for call in spawns:
            if call.name in seen_wrappers:
                continue
            seen_wrappers.add(call.name)
            if call.args:
                self.emit(f"static void *forge_thread_{call.name}(void *arg) {{")
                self.emit(f"    long long v = *(long long *)arg; memset(arg, 0, sizeof(long long)); free(arg); {call.name}(v); return NULL;")
                self.emit("}")
            else:
                self.emit(f"static void *forge_thread_{call.name}(void *arg) {{")
                self.emit(f"    (void)arg; {call.name}(); return NULL;")
                self.emit("}")
        if seen_wrappers:
            self.lines.append("")
        for fn in self.program.funcs:
            if getattr(fn, "type_params", None):
                continue
            if getattr(fn, "is_extern", False):
                continue
            self.gen_func(fn)
        if self.freestanding and "main" in [f.name for f in self.program.funcs]:
            # x86_64 Linux entry: no CRT, no libc. _start calls the
            # program's main and exits with its value via the raw
            # exit_group syscall (231, code in rdi).
            self.emit("__attribute__((noreturn)) void _start(void) {")
            self.emit("    long long code = qasida_main();")
            self.emit('    __asm__ volatile ("syscall" :: "a" (231L), "D" (code) : "rcx", "r11", "memory");')
            self.emit("    __builtin_unreachable();")
            self.emit("}")
        return "\n".join(self.lines)

    def c_sig_extern(self, fn):
        # C ABI types: Forge int is long long internally, but a real
        # C function like puts/system returns int, and its str param
        # is const char * in the standard library.
        def ct(t):
            if t == "int":
                return "int"
            if t == "str":
                return "const char *"
            return c_type(t)
        params = ", ".join(f"{ct(pt)} {pn}" for pn, pt in fn.params)
        return f"{ct(fn.ret)} {fn.name}({params if params else 'void'})"

    def emit(self, text=""):
        self.lines.append(("    " * self.indent) + text if text else "")

    def c_sig(self, fn):
        params = ", ".join(f"{c_type(pt)} {pn}" for pn, pt in fn.params)
        # A never function never returns, so its C signature is
        # void: no value is ever produced to declare.
        ret = "void" if fn.ret == "never" else c_type(fn.ret)
        return f"{ret} {fn.name}({params if params else 'void'})"

    @staticmethod
    def c_str_literal(value):
        out = []
        for ch in value:
            mapping = {"\n": "\\n", "\t": "\\t", "\r": "\\r", "\\": "\\\\", '"': '\\"', "\0": "\\0"}
            out.append(mapping.get(ch, ch))
        return '"' + "".join(out) + '"'

    def expr_type(self, expr):
        return self._types.get(id(expr), "int")

    def attach_types(self, types):
        self._types = types

    def gen_func(self, fn):
        self.current_fn = fn.name
        self.moved_fields = set()
        # Destructor hooks (Top-500 #33): a drop method's own
        # receiver parameter must not hook on its return free,
        # or the hook would call itself forever (the receiver
        # is an owned param, so its death would re-enter drop).
        # The free itself still runs; only the hook is skipped
        # for this one name. Corner, documented: a local inside
        # drop that shadows the receiver name also skips its
        # hook — do not shadow the receiver name inside drop.
        self.drop_receiver = (fn.params[0][0]
                              if fn.name.endswith("__drop") and fn.params
                              else None)
        self._check_cache = {}
        self._facts = {}
        self._let_stack = []
        self.scope_stack = []
        self.current_file = getattr(fn, "file", "") or ""
        self.owned_stack = [{}]
        self.local_types = {}
        self.loop_frames = []
        # Deferred calls, one list per enclosing block (innermost
        # last). A block's defers run at its exit, innermost
        # first within the block (LIFO); returns and loop exits
        # run the frames they abandon. defer_loop_stack holds
        # the defer_stack depth at each loop entry, so break and
        # continue run exactly the frames entered inside the loop.
        self.defer_stack = [[]]
        self.defer_loop_stack = []
        # String parameters own their copy after copy-on-call (see gen_expr Call).
        # Array parameters own a reference after refcount-on-call (see gen_expr Call).
        # Struct parameters own their fields after own-on-call (see gen_expr Call).
        # Union and opaque parameters own their value after copy-on-call (see gen_expr Call).
        for pn, pt in fn.params:
            self.local_types[pn] = pt
            if pt == "str" or self.is_array_type(pt) or self.is_struct_type(pt) \
                    or is_union_type(pt) or is_opaque_type(pt):
                self.owned_stack[0][pn] = pt
        sig = ("long long qasida_main(void)"
               if fn.name == "main" and self.freestanding
               else "int main(int __forge_argc, char **__forge_argv)"
               if fn.name == "main" else self.c_sig(fn))
        self.emit(sig + " {")
        self.indent += 1
        # Runtime moved flags for owned parameters (move v2):
        # a conditional move of a parameter must be visible
        # to the function-end free, which checks this flag.
        for pn, pt in fn.params:
            if pt == "str" or self.is_array_type(pt) or self.is_struct_type(pt) \
                    or is_union_type(pt) or is_opaque_type(pt) or is_tuple_type(pt):
                self.emit(f"int {self.moved_flag(pn)} = 0;")
        if fn.name == "main" and not self.freestanding:
            self.emit("forge_args_global.len = __forge_argc > 0 ? __forge_argc - 1 : 0;")
            self.emit("forge_args_global.cap = forge_args_global.len;")
            self.emit("forge_args_global.data = forge_args_global.len ? "
                      "(char **)malloc(sizeof(char *) * (size_t)forge_args_global.len) : NULL;")
            self.emit("for (long long __forge_arg_i = 0; __forge_arg_i < forge_args_global.len; "
                      "__forge_arg_i++) forge_args_global.data[__forge_arg_i] = "
                      "forge_copy_str(__forge_argv[__forge_arg_i + 1]);")
        self.gen_block(fn.body, fn.ret)
        if fn.name == "main":
            self._emit_defer_frame(self.defer_stack[0], fn.ret)
            if not self.freestanding:
                self.emit("forge_join_threads();")
                self.emit_free_owned()
            self.emit("return 0;")
        elif fn.ret == "void":
            self._emit_defer_frame(self.defer_stack[0], fn.ret)
            self.emit_free_owned()
        self.indent -= 1
        self.emit("}")
        self.lines.append("")
        self.current_fn = None
        self.drop_receiver = None
        self.owned_stack = [{}]
        self.loop_frames = []
        self.defer_stack = [[]]
        self.defer_loop_stack = []

    # ---- Check elimination: intervals, duplicate checks, comparisons ----
    INT_MIN = -(2 ** 63)
    INT_MAX = 2 ** 63 - 1

    def _subtree_has_call(self, node):
        """True if the AST subtree contains a call (a possible mutation)."""
        if isinstance(node, (A.Call, A.MethodCall)):
            return True
        if isinstance(node, (list, tuple)):
            return any(self._subtree_has_call(x) for x in node)
        if isinstance(node, dict):
            return any(self._subtree_has_call(v) for v in node.values())
        if hasattr(node, "__dict__"):
            return any(self._subtree_has_call(v) for v in vars(node).values())
        return False

    def _int_interval(self, node):
        """Proven (lo, hi) for an int expression, or None if unknown.

        Intervals are always clamped to the int64 range: an int
        variable's true value is always inside it, so a fact like
        n >= 2 is (2, INT_MAX), and n - 1 is then provably safe.
        """
        if isinstance(node, A.IntLit):
            v = node.value
            return (max(v, self.INT_MIN), min(v, self.INT_MAX))
        if isinstance(node, A.Var):
            return self._facts.get(node.name, (self.INT_MIN, self.INT_MAX))
        return None

    def _narrow(self, facts, var, lo, hi):
        """Intersect facts[var] with (lo, hi); drop var if empty.

        None means unbounded on that side. Mutates and returns facts.
        """
        lo = self.INT_MIN if lo is None else max(lo, self.INT_MIN)
        hi = self.INT_MAX if hi is None else min(hi, self.INT_MAX)
        if lo > hi:
            facts.pop(var, None)
            return facts
        old = facts.get(var)
        if old is None:
            facts[var] = (lo, hi)
        else:
            nlo, nhi = max(old[0], lo), min(old[1], hi)
            if nlo > nhi:
                facts.pop(var, None)
            else:
                facts[var] = (nlo, nhi)
        return facts

    def _cond_fact(self, cond, truth):
        """(var, lo, hi) proven by a comparison, or None.

        truth=True: the comparison holds; truth=False: it does not.
        Only var-vs-int-literal comparisons are tracked; anything
        else (including !=) yields no fact.
        """
        if not isinstance(cond, A.BinOp):
            return None
        if cond.op not in ("<", "<=", ">", ">=", "=="):
            return None
        left, right, op = cond.left, cond.right, cond.op
        if isinstance(left, A.IntLit) and isinstance(right, A.Var):
            left, right = right, left
            op = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "=="}[op]
        if not (isinstance(left, A.Var) and isinstance(right, A.IntLit)):
            return None
        if self.expr_type(left) != "int":
            return None
        lit = right.value
        if not truth:
            if op == "==":
                return None
            op = {"<": ">=", "<=": ">", ">": "<=", ">=": "<"}[op]
        table = {"<": (None, lit - 1), "<=": (None, lit),
                 ">": (lit + 1, None), ">=": (lit, None),
                 "==": (lit, lit)}
        lo, hi = table[op]
        return (left.name, lo, hi)

    def _apply_cond_facts(self, cond, truth):
        fact = self._cond_fact(cond, truth)
        if fact is not None:
            var, lo, hi = fact
            self._narrow(self._facts, var, lo, hi)

    def _hull_facts(self, f1, f2):
        """Join across two paths: a var keeps the hull of both
        intervals, and only if both paths know it. Anything known on
        one path only is unknown after the join (the other path may
        hold any value)."""
        out = {}
        for var, (lo1, hi1) in f1.items():
            if var in f2:
                lo2, hi2 = f2[var]
                out[var] = (min(lo1, lo2), max(hi1, hi2))
        return out

    def _binop_safe(self, op, lnode, rnode):
        """True if the checked int op provably cannot fail."""
        li = self._int_interval(lnode)
        ri = self._int_interval(rnode)
        if li is None or ri is None:
            return False
        if op == "+":
            lo, hi = li[0] + ri[0], li[1] + ri[1]
        elif op == "-":
            lo, hi = li[0] - ri[1], li[1] - ri[0]
        elif op == "*":
            prods = [a * b for a in li for b in ri]
            lo, hi = min(prods), max(prods)
        elif op in ("/", "%"):
            # forge_div/forge_mod fail on a zero divisor, and on
            # INT_MIN / -1 (div aborts, mod special-cases it, but
            # plain C % on that pair is still UB, so exclude it).
            if not (ri[1] < 0 or ri[0] > 0):
                return False
            if li[0] == self.INT_MIN and ri[0] <= -1 <= ri[1]:
                return False
            return True
        else:
            return False
        return self.INT_MIN <= lo and hi <= self.INT_MAX

    def _branch_exits(self, block):
        """True if a block's last statement always leaves it.

        Return and fail() exit the function; a bare break exits the
        enclosing loop, so following code in the same iteration is
        skipped. Anything else (including a nested if) may fall
        through, so it does not count."""
        stmts = getattr(block, "stmts", None)
        if not stmts:
            return False
        last = stmts[-1]
        if isinstance(last, (A.Return, A.Break, A.Continue)):
            return True
        if (isinstance(last, A.ExprStmt) and isinstance(last.expr, A.Call)
                and last.expr.name == "fail"):
            return True
        return False

    def _str_index_cmp(self, expr):
        """Specialized `s[i] == "a"` / `s[i] == s[j]` / `!=` variants.

        String indexing allocates a fresh 1-char string per access,
        so a bare `s[i] == "a"` pays a malloc, a bounds check, and a
        strcmp. When one side is a string index and the other is a
        1-byte literal (or another string index), compare the bytes
        directly: the bounds check is still emitted in safe mode
        (out-of-bounds must abort exactly as forge_str_at does), but
        no string is allocated. Returns C code, or None to use the
        generic strcmp path. The literal must be exactly 1 byte
        (not 1 character: a multi-byte character's first byte alone
        would compare unequal to the full literal under strcmp).
        """
        def idx_side(node):
            return (isinstance(node, A.Index)
                    and self.expr_type(node.base) == "str")

        def lit1_side(node):
            return (isinstance(node, A.StrLit)
                    and len(node.value.encode("utf-8")) == 1)

        left, right = expr.left, expr.right
        op = "==" if expr.op == "==" else "!="
        sides = []
        if idx_side(left) and lit1_side(right):
            sides = [("idx", left), ("lit", right)]
        elif lit1_side(left) and idx_side(right):
            sides = [("lit", left), ("idx", right)]
        elif idx_side(left) and idx_side(right):
            sides = [("idx", left), ("idx", right)]
        else:
            return None
        n = self.arr_counter
        self.arr_counter += 1
        decls = []
        cmps = []
        for k, (kind, node) in enumerate(sides):
            if kind == "lit":
                cmps.append(f"{self.c_str_literal(node.value)}[0]")
                continue
            base = self.gen_expr(node.base)
            idx = self.gen_expr(node.index)
            ts = f"__forge_sc{n}s{k}"
            ti = f"__forge_sc{n}i{k}"
            tn = f"__forge_sc{n}n{k}"
            decls.append(f"const char *{ts} = {base}; long long {ti} = {idx}; ")
            if self.mode == "safe":
                decls.append(
                    f"long long {tn} = (long long)strlen({ts}); "
                    f"if ({ti} < 0 || {ti} >= {tn}) "
                    f"forge_fail(\"string index out of bounds\"); ")
            cmps.append(f"{ts}[{ti}]")
        return "({ " + "".join(decls) + f"({cmps[0]} {op} {cmps[1]}); }})"

    def _facts_update_from_rhs(self, name, rhs, is_let):
        """After `let name = rhs` / `name = rhs`, refresh name's facts.

        Only a `let` is a new binding: branch joins drop let-bound
        names (the binding is gone after the branch), while an
        assignment to an outer variable keeps its joined facts."""
        if isinstance(rhs, A.IntLit):
            v = max(min(rhs.value, self.INT_MAX), self.INT_MIN)
            self._facts[name] = (v, v)
        elif isinstance(rhs, A.Var) and rhs.name in self._facts:
            self._facts[name] = self._facts[rhs.name]
        else:
            self._facts.pop(name, None)
        if is_let:
            for s in self._let_stack:
                s.add(name)

    def gen_block(self, block, ret_type):
        for stmt in block.stmts:
            if self.debug and self.current_file:
                line = getattr(stmt, "line", None)
                if line:
                    # Column 0: emit() would indent it,
                    # and a #line directive must not be
                    # indented to be safe with cc.
                    esc = self.current_file.replace("\\", "\\\\").replace('"', '\\"')
                    self.lines.append(f'#line {line} "{esc}"')
            self.gen_stmt(stmt, ret_type)

    def _emit_defer_frame(self, frame, ret_type):
        """Emit one block's deferred calls, LIFO, as statements
        at the exit point. Arguments evaluate here, at exit
        time, in v1 (documented)."""
        for call in reversed(frame):
            self.gen_stmt(A.ExprStmt(call, call.line, call.col), ret_type)

    def _emit_defers_downto(self, depth, ret_type):
        """Emit the defers of every frame from `depth` upward,
        innermost block first, each block LIFO."""
        for frame in reversed(self.defer_stack[depth:]):
            self._emit_defer_frame(frame, ret_type)

    def _emit_all_defers(self, ret_type):
        self._emit_defers_downto(0, ret_type)

    def gen_arm_block(self, body, ret_type):
        """A match arm's block: its own defer frame, run at arm
        exit (arms have no owned frame of their own)."""
        self.defer_stack.append([])
        self.gen_block(body, ret_type)
        self._emit_defer_frame(self.defer_stack[-1], ret_type)
        self.defer_stack.pop()

    def gen_stmt(self, stmt, ret_type):
        # Duplicate checks live within one statement only: every
        # statement starts with an empty cache (a later statement may
        # reassign the array or the index, and calls clear it too).
        self._check_cache = {}
        if isinstance(stmt, A.Block):
            saved_facts = dict(self._facts)
            self.emit("{")
            self.indent += 1
            self.owned_stack.append({})
            self.defer_stack.append([])
            self.gen_block(stmt, ret_type)
            self._facts = saved_facts
            self._emit_defer_frame(self.defer_stack[-1], ret_type)
            self.defer_stack.pop()
            self.emit_free_frame()
            self.owned_stack.pop()
            self.indent -= 1
            self.emit("}")
            return
        if isinstance(stmt, A.Let):
            t = stmt.ann if (stmt.ann and (is_opaque_type(stmt.ann)
                             or is_union_type(stmt.ann)
                             or self.expr_type(stmt.expr) == "never"
                             or (isinstance(stmt.expr, A.ArrayLit)
                                 and not stmt.expr.elems))) else self.expr_type(stmt.expr)
            expr = self.gen_expr(stmt.expr)
            if self.expr_type(stmt.expr) == "never":
                expr = self.never_wrap(expr, t)
            self.local_types[stmt.name] = t
            self._facts_update_from_rhs(stmt.name, stmt.expr, True)
            if t == "str":
                if not self.is_fresh_str(stmt.expr):
                    expr = f"forge_copy_str({expr})"
                self.owned_add(stmt.name, "str")
                # Runtime moved flag (move v2), declared with
                # the variable so it shares its block scope.
                self.emit(f"int {self.moved_flag(stmt.name)} = 0;")
            elif is_opaque_type(t):
                # A concrete implementation wraps into the opaque
                # value; a shared opaque value gains a copy.
                expr = self.opaque_convert(expr, self.expr_type(stmt.expr),
                                           t, stmt.expr)
                self.owned_add(stmt.name, t)
                self.emit(f"{c_type(t)} {stmt.name} = {expr};")
                self.emit(f"int {self.moved_flag(stmt.name)} = 0;")
                return
            elif is_union_type(t):
                # A member value wraps into the union (fresh); a
                # shared union value gains an independent str
                # payload, if any, before this owner takes it.
                et = self.expr_type(stmt.expr)
                if et in union_members(t):
                    copy_str = et == "str" and not self.is_fresh_str(stmt.expr)
                    expr = self.union_wrap(expr, et, t, copy_str=copy_str)
                elif et == t and not self.is_fresh_union(stmt.expr):
                    self.assign_counter += 1
                    n = self.assign_counter
                    copy = self.union_copy_stmt(f"__forge_let{n}", t)
                    expr = (f"({{{c_type(t)} __forge_let{n} = {expr}; "
                            f"{copy} __forge_let{n};}})")
                self.owned_add(stmt.name, t)
                self.emit(f"{c_type(t)} {stmt.name} = {expr};")
                self.emit(f"int {self.moved_flag(stmt.name)} = 0;")
                return
            elif self.is_array_type(t):
                # Fresh arrays are taken as-is (ref=1); shared arrays
                # gain a reference for this new owner.
                self.owned_add(stmt.name, t)
                self.emit(f"{c_type(t)} {stmt.name} = {expr};")
                self.emit(f"int {self.moved_flag(stmt.name)} = 0;")
                if not self.is_fresh_array(stmt.expr):
                    self.emit(f"forge_arr_inc({stmt.name}.ref);")
                return
            elif self.is_struct_type(t):
                # Fresh structs (literal/call) are already owned;
                # shared structs gain independent fields for this owner.
                self.owned_add(stmt.name, t)
                self.emit(f"{c_type(t)} {stmt.name} = {expr};")
                self.emit(f"int {self.moved_flag(stmt.name)} = 0;")
                if not self.is_fresh_struct(stmt.expr):
                    self.emit_struct_own(stmt.name, t)
                return
            elif is_tuple_type(t):
                # Fresh tuples (literal/call) are already owned;
                # shared tuples gain independent elements for this owner.
                self.owned_add(stmt.name, t)
                self.emit(f"{c_type(t)} {stmt.name} = {expr};")
                self.emit(f"int {self.moved_flag(stmt.name)} = 0;")
                if not self.is_fresh_tuple(stmt.expr):
                    self.emit_tuple_own(stmt.name, t)
                return
            self.emit(f"{c_type(t)} {stmt.name} = {expr};")
            return
        if isinstance(stmt, A.Assign):
            expr = self.gen_expr(stmt.expr)
            self._facts_update_from_rhs(stmt.name, stmt.expr, False)
            et = self.expr_type(stmt.expr)
            vt = self.owned_type(stmt.name)
            if et == "never":
                expected = self.local_types.get(stmt.name) or vt
                if expected:
                    expr = self.never_wrap(expr, expected)
            if vt is not None and is_opaque_type(vt):
                # Evaluate into a temp first (the new value may
                # reference the old one), then free the old value
                # and take the converted temp.
                self.assign_counter += 1
                n = self.assign_counter
                temp = f"__forge_assign{n}"
                converted = self.opaque_convert(expr, et, vt, stmt.expr)
                self.emit(f"{c_type(vt)} {temp} = {converted};")
                if self.owned_contains(stmt.name):
                    self.emit_guarded(stmt.name, f"forge_free_{opaque_c_name(vt)}({stmt.name});")
                self.emit(f"{stmt.name} = {temp};")
                self.owned_add(stmt.name, vt)
                self.emit(f"{self.moved_flag(stmt.name)} = 0;")
            elif vt is not None and is_union_type(vt):
                # Evaluate into a temp first (the new value may
                # reference the old one), copy the temp's str
                # payload before freeing the old value, then take
                # the temp. A member value wraps into the union,
                # copying a shared str payload on the way in.
                self.assign_counter += 1
                n = self.assign_counter
                temp = f"__forge_assign{n}"
                if et in union_members(vt):
                    copy_str = et == "str" and not self.is_fresh_str(stmt.expr)
                    expr = self.union_wrap(expr, et, vt, copy_str=copy_str)
                self.emit(f"{c_type(vt)} {temp} = {expr};")
                if et == vt and not self.is_fresh_union(stmt.expr):
                    copy = self.union_copy_stmt(temp, vt)
                    if copy:
                        self.emit(copy)
                if self.owned_contains(stmt.name):
                    self.emit_guarded(stmt.name, self.union_free_code(stmt.name, vt))
                self.emit(f"{stmt.name} = {temp};")
                self.owned_add(stmt.name, vt)
                self.emit(f"{self.moved_flag(stmt.name)} = 0;")
            elif et == "str":
                if not self.is_fresh_str(stmt.expr):
                    expr = f"forge_copy_str({expr})"
                # Evaluate first, then free the old value: the new
                # expression may reference the old value (out = out + x).
                n = self.assign_counter
                self.assign_counter += 1
                self.emit(f"char * __forge_assign{n} = {expr};")
                if self.owned_contains(stmt.name):
                    self.emit_guarded(stmt.name, f"forge_free_str({stmt.name});")
                self.emit(f"{stmt.name} = __forge_assign{n};")
                self.owned_add(stmt.name, "str")
                self.emit(f"{self.moved_flag(stmt.name)} = 0;")
            elif self.is_array_type(et):
                # Evaluate into a temp, free the old array (refcounted),
                # then take the new one, gaining a reference if shared.
                n = self.assign_counter
                self.assign_counter += 1
                self.emit(f"{c_type(et)} __forge_assign{n} = {expr};")
                if self.owned_contains(stmt.name):
                    self.emit_guarded(stmt.name, self.array_free_code(stmt.name, et))
                self.emit(f"{stmt.name} = __forge_assign{n};")
                if not self.is_fresh_array(stmt.expr):
                    self.emit(f"forge_arr_inc({stmt.name}.ref);")
                self.owned_add(stmt.name, et)
                self.emit(f"{self.moved_flag(stmt.name)} = 0;")
            elif self.is_struct_type(et):
                # Evaluate into a temp, make it independently owned
                # (so freeing the old value cannot free the new one),
                # then free the old struct and take the new one.
                n = self.assign_counter
                self.assign_counter += 1
                self.emit(f"{c_type(et)} __forge_assign{n} = {expr};")
                if not self.is_fresh_struct(stmt.expr):
                    self.emit_struct_own(f"__forge_assign{n}", et)
                if self.owned_contains(stmt.name):
                    self.emit_guarded(stmt.name, self.struct_free_code(stmt.name, et, path=stmt.name))
                self.emit(f"{stmt.name} = __forge_assign{n};")
                self.owned_add(stmt.name, et)
                self.emit(f"{self.moved_flag(stmt.name)} = 0;")
                self.moved_fields = {p for p in self.moved_fields
                                     if not p.startswith(stmt.name + ".")}
            elif is_tuple_type(et):
                # Same temp-first shape as structs, with tuple
                # ownership on the temp and tuple frees on the old.
                n = self.assign_counter
                self.assign_counter += 1
                self.emit(f"{c_type(et)} __forge_assign{n} = {expr};")
                if not self.is_fresh_tuple(stmt.expr):
                    self.emit_tuple_own(f"__forge_assign{n}", et)
                if self.owned_contains(stmt.name):
                    self.emit_guarded(stmt.name, self.tuple_free_code(stmt.name, et))
                self.emit(f"{stmt.name} = __forge_assign{n};")
                self.owned_add(stmt.name, et)
                self.emit(f"{self.moved_flag(stmt.name)} = 0;")
            else:
                self.emit(f"{stmt.name} = {expr};")
            return
        if isinstance(stmt, A.FieldAssign):
            # A field that moved away (move v2) holds no value
            # to free: assigning it revives it, so its old free
            # is skipped and the path leaves moved_fields below.
            field_path = self._field_path(stmt.target)
            field_moved = field_path is not None and field_path in self.moved_fields
            target_code = self.gen_expr(stmt.target)
            ft = self.expr_type(stmt.target)
            val = self.gen_expr(stmt.expr)
            if self.expr_type(stmt.expr) == "never":
                val = self.never_wrap(val, ft)
            # Mirror Assign's temp-first ownership: evaluate the
            # new value, make it independently owned, free the
            # old field value, then take the new one. Field
            # assignment previously skipped the own and free
            # steps for arrays and structs entirely, so a field
            # written from a shared value undercounted its
            # reference and freed it while still in use (found
            # by the arena module: push to a shared array, then
            # write it back into its struct field).
            if ft == "str":
                if not self.is_fresh_str(stmt.expr):
                    val = f"forge_copy_str({val})"
                self.assign_counter += 1
                n = self.assign_counter
                self.emit(f"char * __forge_fa{n} = {val};")
                if not field_moved:
                    self.emit(f"forge_free_str({target_code});")
                self.emit(f"{target_code} = __forge_fa{n};")
            elif is_union_type(ft):
                vt = self.expr_type(stmt.expr)
                if vt in union_members(ft):
                    copy_str = vt == "str" and not self.is_fresh_str(stmt.expr)
                    val = self.union_wrap(val, vt, ft, copy_str=copy_str)
                self.assign_counter += 1
                n = self.assign_counter
                self.emit(f"{c_type(ft)} __forge_fa{n} = {val};")
                if vt == ft and not self.is_fresh_union(stmt.expr):
                    copy = self.union_copy_stmt(f"__forge_fa{n}", ft)
                    if copy:
                        self.emit(copy)
                ufree = self.union_free_code(target_code, ft)
                if ufree and not field_moved:
                    self.emit(ufree)
                self.emit(f"{target_code} = __forge_fa{n};")
            elif self.is_array_type(ft):
                self.assign_counter += 1
                n = self.assign_counter
                self.emit(f"{c_type(ft)} __forge_fa{n} = {val};")
                if not self.is_fresh_array(stmt.expr):
                    self.emit(f"forge_arr_inc(__forge_fa{n}.ref);")
                if not field_moved:
                    self.emit(self.array_free_code(target_code, ft))
                self.emit(f"{target_code} = __forge_fa{n};")
            elif self.is_struct_type(ft):
                self.assign_counter += 1
                n = self.assign_counter
                self.emit(f"{c_type(ft)} __forge_fa{n} = {val};")
                if not self.is_fresh_struct(stmt.expr):
                    self.emit_struct_own(f"__forge_fa{n}", ft)
                if not field_moved:
                    self.emit_struct_free(target_code, ft, path=field_path)
                self.emit(f"{target_code} = __forge_fa{n};")
            elif is_tuple_type(ft):
                self.assign_counter += 1
                n = self.assign_counter
                self.emit(f"{c_type(ft)} __forge_fa{n} = {val};")
                if not self.is_fresh_tuple(stmt.expr):
                    self.emit_tuple_own(f"__forge_fa{n}", ft)
                if not field_moved:
                    self.emit_tuple_free(target_code, ft)
                self.emit(f"{target_code} = __forge_fa{n};")
            else:
                self.emit(f"{target_code} = {val};")
            if field_path is not None:
                self.moved_fields.discard(field_path)
            return
        if isinstance(stmt, A.IndexAssign):
            base = stmt.base.base
            if isinstance(base, A.Index) and self.is_array_type(self.expr_type(base)):
                # Chained index assignment (m[i][j] = v): the inner
                # array is a shared reference, so storing through a
                # temp still mutates the shared buffer.
                inner_code = self.gen_expr(base)
                inner_t = c_type(self.expr_type(base))
                tmp = f"__forge_base{self.assign_counter}"
                self.assign_counter += 1
                self.emit(f"{inner_t} {tmp} = {inner_code};")
                base_code = tmp
                base_is_temp = True
            elif isinstance(base, (A.Var, A.FieldAccess)):
                base_code = self.gen_expr(base)
                base_is_temp = False
            else:
                raise ForgeError("index assignment target must be a variable or a field")
            et = self.expr_type(stmt.base)
            idx = self.gen_expr(stmt.base.index)
            val = self.gen_expr(stmt.expr)
            if et == "str":
                val = f"forge_copy_str({val})"
            if self.is_struct_type(et):
                if not self.is_fresh_struct(stmt.expr):
                    tmp = f"__forge_setv{self.assign_counter}"
                    self.assign_counter += 1
                    self.emit(f"{c_type(et)} {tmp} = {val};")
                    self.emit_struct_own(tmp, et)
                    val = tmp
                suffix = "" if self.mode == "safe" else "_fast"
                self.emit(f"forge_{self.struct_type_name(et)}_set{suffix}(&{base_code}, {idx}, {val});")
            elif self.is_array_type(et):
                # Array element assignment: gain a reference for the
                # slot (unless fresh), free the old element, store.
                # Bind base and index to temps first: they are used
                # more than once below.
                if not isinstance(base, A.Var) and not base_is_temp:
                    btmp = f"__forge_sb{self.assign_counter}"
                    self.assign_counter += 1
                    self.emit(f"{c_type(self.expr_type(stmt.base.base))} {btmp} = {base_code};")
                    base_code = btmp
                if not self.is_fresh_array(stmt.expr):
                    tmp = f"__forge_seta{self.assign_counter}"
                    self.assign_counter += 1
                    self.emit(f"{c_type(et)} {tmp} = {val};")
                    self.emit(f"forge_arr_inc({tmp}.ref);")
                    val = tmp
                itmp = f"__forge_si{self.assign_counter}"
                self.assign_counter += 1
                self.emit(f"long long {itmp} = {idx};")
                if self.mode == "safe":
                    self.emit(f"if ({itmp} < 0 || {itmp} >= {base_code}.len) "
                              f"forge_fail(\"array index out of bounds\");")
                self.emit(self.array_free_code(f"{base_code}.data[{itmp}]", et))
                self.emit(f"{base_code}.data[{itmp}] = {val};")
            elif self.mode == "safe":
                self.emit(f"{SET_FN[et]}(&{base_code}, {idx}, {val});")
            else:
                self.emit(f"({base_code}).data[{idx}] = {val};")
            return
        if isinstance(stmt, A.Match):
            et = self.expr_type(stmt.expr)
            if is_union_type(et):
                # Union match: evaluate once into a temp, match on
                # .tag, bind the member value into a local (str
                # payloads copied, as for payload enums).
                members = union_members(et)
                n = self.loop_counter
                self.loop_counter += 1
                temp = f"__forge_match{n}"
                self.emit("{")
                self.indent += 1
                self.emit(f"{c_type(et)} {temp} = {self.gen_expr(stmt.expr)};")
                match_pre = dict(self._facts)
                for idx, (pat, binding, body) in enumerate(stmt.arms):
                    if pat == "_":
                        if idx == 0:
                            self.emit("{")
                        else:
                            self.emit("} else {")
                        self.indent += 1
                        self._facts = dict(match_pre)
                        self.gen_arm_block(body, ret_type)
                        self.indent -= 1
                        self.emit("}")
                    else:
                        midx = members.index(pat)
                        kw = "if" if idx == 0 else "} else if"
                        self.emit(f"{kw} ({temp}.tag == {midx}) {{")
                        self.indent += 1
                        self._facts = dict(match_pre)
                        payload_code = f"{temp}.payload._{midx}"
                        if pat == "str":
                            payload_code = f"forge_copy_str({payload_code})"
                        self.emit(f"{c_type(pat)} {binding} = {payload_code};")
                        if pat == "str" or self.is_array_type(pat) or self.is_struct_type(pat) \
                                or is_tuple_type(pat) or is_union_type(pat) or is_opaque_type(pat):
                            self.emit(f"int {self.moved_flag(binding)} = 0;")
                        self._facts.pop(binding, None)
                        self.gen_arm_block(body, ret_type)
                        self.indent -= 1
                        if idx == len(stmt.arms) - 1:
                            self.emit("}")
                self.indent -= 1
                self.emit("}")
                self._facts = {}
                return
            info = self.enum_concrete_info(et)
            is_payload = False
            if info is not None:
                _base, variant_info = info
                is_payload = any(pt is not None for _tag, pt in variant_info.values())
            if not is_payload:
                target = self.gen_expr(stmt.expr)
                # Match arms are alternatives, not sequential code:
                # each arm starts from the pre-match facts, and no
                # arm's facts propagate past the match.
                match_pre = dict(self._facts)
                for idx, (pat, _binding, body) in enumerate(stmt.arms):
                    if pat == "_":
                        if idx == 0:
                            self.emit("{")
                        else:
                            self.emit("} else {")
                        self.indent += 1
                        self._facts = dict(match_pre)
                        self.gen_arm_block(body, ret_type)
                        self.indent -= 1
                        self.emit("}")
                    else:
                        kw = "if" if idx == 0 else "} else if"
                        self.emit(f"{kw} ({target} == {pat}) {{")
                        self.indent += 1
                        self._facts = dict(match_pre)
                        self.gen_arm_block(body, ret_type)
                        self.indent -= 1
                        if idx == len(stmt.arms) - 1:
                            self.emit("}")
                self._facts = {}
                return
            # Payload enum: evaluate once into a temp, match on .tag,
            # bind the payload into a local for arms that bind it.
            n = self.loop_counter
            self.loop_counter += 1
            temp = f"__forge_match{n}"
            self.emit("{")
            self.indent += 1
            self.emit(f"{c_type(et)} {temp} = {self.gen_expr(stmt.expr)};")
            match_pre = dict(self._facts)
            for idx, (pat, binding, body) in enumerate(stmt.arms):
                if pat == "_":
                    if idx == 0:
                        self.emit("{")
                    else:
                        self.emit("} else {")
                    self.indent += 1
                    self._facts = dict(match_pre)
                    self.gen_arm_block(body, ret_type)
                    self.indent -= 1
                    self.emit("}")
                else:
                    tag, pt = variant_info[pat]
                    kw = "if" if idx == 0 else "} else if"
                    self.emit(f"{kw} ({temp}.tag == {tag}) {{")
                    self.indent += 1
                    self._facts = dict(match_pre)
                    if binding is not None:
                        payload_code = f"{temp}.payload.payload_{pat}"
                        if pt == "str":
                            payload_code = f"forge_copy_str({payload_code})"
                        self.emit(f"{c_type(pt)} {binding} = {payload_code};")
                        if pt == "str" or self.is_array_type(pt) or self.is_struct_type(pt) \
                                or is_tuple_type(pt) or is_union_type(pt) or is_opaque_type(pt):
                            self.emit(f"int {self.moved_flag(binding)} = 0;")
                        # The payload binding shadows any outer variable
                        # of the same name for this arm: its value is
                        # unknown, so drop the outer variable's facts.
                        self._facts.pop(binding, None)
                    self.gen_arm_block(body, ret_type)
                    self.indent -= 1
                    if idx == len(stmt.arms) - 1:
                        self.emit("}")
            self.indent -= 1
            self.emit("}")
            self._facts = {}
            return
        if isinstance(stmt, A.Spawn):
            call = stmt.call
            n = self.spawn_counter
            self.spawn_counter += 1
            self.emit("{")
            self.indent += 1
            if call.args:
                self.emit(f"long long *__forge_spawn_arg{n} = (long long *)malloc(sizeof(long long));")
                self.emit(f"*__forge_spawn_arg{n} = {self.gen_expr(call.args[0])};")
                arg = f"__forge_spawn_arg{n}"
            else:
                arg = "NULL"
            self.emit(f"pthread_t __forge_t{n};")
            self.emit(f"pthread_create(&__forge_t{n}, NULL, forge_thread_{call.name}, {arg});")
            self.emit(f"forge_threads[forge_thread_count++] = __forge_t{n};")
            self.indent -= 1
            self.emit("}")
            return
        if isinstance(stmt, A.If):
            # Facts flow: the condition's facts hold inside each arm
            # (true facts in `then`, false facts in `else`), and the
            # code after the if sees the hull of both arms' facts —
            # or only the surviving arm's facts when the other arm
            # always exits. The emitted C is unchanged; only the
            # check elision inside the arms and after the if differs.
            pre = dict(self._facts)
            cond_code = self.gen_expr(stmt.cond)
            self.emit(f"if ({cond_code}) {{")
            self.indent += 1
            self.owned_stack.append({})
            self._apply_cond_facts(stmt.cond, True)
            then_lets = set()
            self._let_stack.append(then_lets)
            self.defer_stack.append([])
            self.gen_block(stmt.then, ret_type)
            self._let_stack.pop()
            then_facts = {k: v for k, v in self._facts.items()
                          if k not in then_lets}
            then_exits = self._branch_exits(stmt.then)
            self._emit_defer_frame(self.defer_stack[-1], ret_type)
            self.defer_stack.pop()
            self.emit_free_frame()
            self.owned_stack.pop()
            self.indent -= 1
            self._facts = dict(pre)
            self._apply_cond_facts(stmt.cond, False)
            if stmt.els is not None:
                self.emit("} else {")
                self.indent += 1
                self.owned_stack.append({})
                else_lets = set()
                self._let_stack.append(else_lets)
                self.defer_stack.append([])
                self.gen_block(stmt.els, ret_type)
                self._let_stack.pop()
                else_facts = {k: v for k, v in self._facts.items()
                              if k not in else_lets}
                else_exits = self._branch_exits(stmt.els)
                self._emit_defer_frame(self.defer_stack[-1], ret_type)
                self.defer_stack.pop()
                self.emit_free_frame()
                self.owned_stack.pop()
                self.indent -= 1
            else:
                else_facts = dict(self._facts)
                else_exits = False
            if then_exits and else_exits:
                self._facts = {}
            elif then_exits:
                self._facts = else_facts
            elif else_exits:
                self._facts = then_facts
            else:
                self._facts = self._hull_facts(then_facts, else_facts)
            self.emit("}")
            return
        if isinstance(stmt, A.Break):
            if not self.loop_frames:
                raise ForgeError("break outside a loop", stmt.line, stmt.col)
            # Defers first: a deferred call runs while its block's
            # locals are still alive, before joins and frees.
            self._emit_defers_downto(self.defer_loop_stack[-1], ret_type)
            # A break leaves every scope entered inside the innermost
            # loop's body (those scopes' blocks are abandoned, so
            # their normal-end join never runs). Scopes entered
            # outside that loop survive the break and are not joined.
            for start_var, depth in reversed(self.scope_stack):
                if depth == len(self.loop_frames):
                    self.emit(f"forge_join_scope({start_var});")
            self.emit_free_frames_downto(self.loop_frames[-1])
            self.emit("break;")
            return
        if isinstance(stmt, A.Continue):
            if not self.loop_frames:
                raise ForgeError("continue outside a loop", stmt.line, stmt.col)
            self._emit_defers_downto(self.defer_loop_stack[-1], ret_type)
            # A continue ends the current iteration exactly like a
            # break ends the loop: body scopes are abandoned, so the
            # same joins and frame frees apply, then C's continue
            # runs the loop's own increment/condition step.
            for start_var, depth in reversed(self.scope_stack):
                if depth == len(self.loop_frames):
                    self.emit(f"forge_join_scope({start_var});")
            self.emit_free_frames_downto(self.loop_frames[-1])
            self.emit("continue;")
            return
        if isinstance(stmt, A.While):
            # A loop body runs many times: facts proven before the
            # loop may be stale by the second iteration, so no facts
            # cross a loop boundary in either direction.
            self._facts = {}
            self.emit(f"while ({self.gen_expr(stmt.cond)}) {{")
            self.indent += 1
            self.owned_stack.append({})
            self.loop_frames.append(len(self.owned_stack) - 1)
            self.defer_loop_stack.append(len(self.defer_stack))
            self.defer_stack.append([])
            self.gen_block(stmt.body, ret_type)
            self.defer_loop_stack.pop()
            self._emit_defer_frame(self.defer_stack[-1], ret_type)
            self.defer_stack.pop()
            self.loop_frames.pop()
            self.emit_free_frame()
            self.owned_stack.pop()
            self.indent -= 1
            self.emit("}")
            self._facts = {}
            return
        if isinstance(stmt, A.For):
            self._facts = {}
            arr_type = self.expr_type(stmt.expr)
            if arr_type == "range":
                # Lazy iteration: no array is built; the loop runs
                # directly over the endpoints. The increment can
                # never overflow: it fires only while x < end, so
                # x + 1 <= end <= INT64_MAX.
                self.local_types[stmt.name] = "int"
                rng_tmp = f"__forge_rng{self.arr_counter}"
                self.arr_counter += 1
                self.emit("{")
                self.indent += 1
                self.emit(f"ForgeRange {rng_tmp} = {self.gen_expr(stmt.expr)};")
                self.emit(f"for (long long {stmt.name} = {rng_tmp}.start; "
                          f"{stmt.name} < {rng_tmp}.end; {stmt.name}++) {{")
                self.indent += 1
                self.owned_stack.append({})
                self.loop_frames.append(len(self.owned_stack) - 1)
                self.defer_loop_stack.append(len(self.defer_stack))
                self.defer_stack.append([])
                self.gen_block(stmt.body, ret_type)
                self.defer_loop_stack.pop()
                self._emit_defer_frame(self.defer_stack[-1], ret_type)
                self.defer_stack.pop()
                self.loop_frames.pop()
                self.emit_free_frame()
                self.owned_stack.pop()
                self.indent -= 1
                self.emit("}")
                self.indent -= 1
                self.emit("}")
                self._facts = {}
                return
            et = elem_of(arr_type)
            self.local_types[stmt.name] = et
            arr_tmp = f"__forge_arr{self.arr_counter}"
            self.arr_counter += 1
            idx = f"__forge_i{self.loop_counter}"
            self.loop_counter += 1
            self.emit("{")
            self.indent += 1
            self.emit(f"{c_type(arr_type)} {arr_tmp} = {self.gen_expr(stmt.expr)};")
            self.emit(f"for (long long {idx} = 0; {idx} < {arr_tmp}.len; {idx}++) {{")
            self.indent += 1
            # Borrowed element view (like str loop vars): the array
            # owns the fields; uses that need ownership copy on use.
            self.emit(f"{c_type(et)} {stmt.name} = {arr_tmp}.data[{idx}];")
            self.owned_stack.append({})
            self.loop_frames.append(len(self.owned_stack) - 1)
            self.defer_loop_stack.append(len(self.defer_stack))
            self.defer_stack.append([])
            self.gen_block(stmt.body, ret_type)
            self.defer_loop_stack.pop()
            self._emit_defer_frame(self.defer_stack[-1], ret_type)
            self.defer_stack.pop()
            self.loop_frames.pop()
            self.emit_free_frame()
            self.owned_stack.pop()
            self.indent -= 1
            self.emit("}")
            self.indent -= 1
            self.emit("}")
            self._facts = {}
            return
        if isinstance(stmt, A.Scope):
            n = self.scope_counter
            self.scope_counter += 1
            start_var = f"__forge_scope{n}"
            self.emit(f"long long {start_var} = forge_thread_count;")
            self.scope_stack.append((start_var, len(self.loop_frames)))
            scope_pre = dict(self._facts)
            scope_lets = set()
            self._let_stack.append(scope_lets)
            self.emit("{")
            self.indent += 1
            self.owned_stack.append({})
            self.defer_stack.append([])
            self.gen_block(stmt.body, ret_type)
            self._let_stack.pop()
            # Join before freeing the frame: tasks finish before
            # their spawning frame is torn down. Lets bound inside
            # the scope are gone after it, so their facts revert to
            # the pre-scope facts; assignments to outer variables
            # keep their updated facts (the scope always executes).
            for name in scope_lets:
                if name in scope_pre:
                    self._facts[name] = scope_pre[name]
                else:
                    self._facts.pop(name, None)
            self._emit_defer_frame(self.defer_stack[-1], ret_type)
            self.defer_stack.pop()
            self.emit(f"forge_join_scope({start_var});")
            self.emit_free_frame()
            self.owned_stack.pop()
            self.indent -= 1
            self.emit("}")
            self.scope_stack.pop()
            return
        if isinstance(stmt, A.Return):
            # Defers run before joins and frees: a deferred call
            # runs while its block's locals are still alive, and
            # any task it spawns is still joined below.
            self._emit_all_defers(ret_type)
            # A return leaves every enclosing scope: join innermost
            # first (an outer join would skip the already-joined
            # threads via the flags, but the order documents intent).
            for start_var, _depth in reversed(self.scope_stack):
                self.emit(f"forge_join_scope({start_var});")
            if self.current_fn == "main" and not self.freestanding:
                self.emit("forge_join_threads();")
            if stmt.expr is None:
                self.emit_free_owned()
                self.emit("return 0;" if self.current_fn == "main" else "return;")
            else:
                ret_code = self.gen_expr(stmt.expr)
                if self.expr_type(stmt.expr) == "never":
                    ret_code = self.never_wrap(ret_code, ret_type)
                if ret_type == "str" and not self.is_fresh_str(stmt.expr):
                    ret_code = f"forge_copy_str({ret_code})"
                if is_opaque_type(ret_type):
                    ret_code = self.opaque_convert(ret_code,
                                                   self.expr_type(stmt.expr),
                                                   ret_type, stmt.expr)
                if is_union_type(ret_type):
                    rt = self.expr_type(stmt.expr)
                    if rt in union_members(ret_type):
                        copy_str = rt == "str" and not self.is_fresh_str(stmt.expr)
                        ret_code = self.union_wrap(ret_code, rt, ret_type,
                                                   copy_str=copy_str)
                self.emit(f"{c_type(ret_type)} __forge_ret = {ret_code};")
                if self.is_array_type(ret_type) and not self.is_fresh_array(stmt.expr):
                    # Shared array return: gain a reference before
                    # freeing owned locals, so the returned array survives.
                    self.emit("forge_arr_inc(__forge_ret.ref);")
                if self.is_struct_type(ret_type) and not self.is_fresh_struct(stmt.expr):
                    # Shared struct return: gain independent fields before
                    # freeing owned locals, so the returned struct survives.
                    self.emit_struct_own("__forge_ret", ret_type)
                if is_tuple_type(ret_type) and not self.is_fresh_tuple(stmt.expr):
                    # Shared tuple return: gain independent elements before
                    # freeing owned locals, so the returned tuple survives.
                    self.emit_tuple_own("__forge_ret", ret_type)
                if is_union_type(ret_type) and self.expr_type(stmt.expr) == ret_type \
                        and not self.is_fresh_union(stmt.expr):
                    # Shared union return: gain an independent str
                    # payload before freeing owned locals.
                    copy = self.union_copy_stmt("__forge_ret", ret_type)
                    if copy:
                        self.emit(copy)
                self.emit_free_owned()
                self.emit("return __forge_ret;")
            return
        if isinstance(stmt, A.Defer):
            # Record only: the call is emitted at the enclosing
            # block's exit (or at any earlier return, break, or
            # continue that abandons the block), LIFO.
            self.defer_stack[-1].append(stmt.call)
            return
        if isinstance(stmt, A.ExprStmt):
            call = stmt.expr
            if isinstance(call, A.Call) and call.name == "assert":
                cond = self.gen_expr(call.args[0])
                msg = self.gen_expr(call.args[1])
                self.emit(f"if (!({cond})) {{ fprintf(stderr, \"qasida: assertion failed: %s\\n\", {msg}); exit(1); }}")
                return
            if isinstance(call, A.Call) and call.name in ("print", "println"):
                self.gen_print(call)
                return
            if isinstance(call, A.Call) and call.name == "push":
                var_code = self.gen_expr(call.args[0])
                et = self.expr_type(call.args[1])
                val = self.gen_expr(call.args[1])
                if et == "str":
                    val = f"forge_copy_str({val})"
                if self.is_struct_type(et):
                    if not self.is_fresh_struct(call.args[1]):
                        tmp = f"__forge_pushv{self.assign_counter}"
                        self.assign_counter += 1
                        self.emit(f"{c_type(et)} {tmp} = {val};")
                        self.emit_struct_own(tmp, et)
                        val = tmp
                    self.emit(f"forge_{self.struct_type_name(et)}_push(&{var_code}, {val});")
                elif self.is_array_type(et):
                    # Nested push: gain a reference for the slot
                    # (unless fresh), then grow + append inline
                    # through a pointer (single evaluation of the
                    # target, which may be a field access).
                    if not self.is_fresh_array(call.args[1]):
                        tmp = f"__forge_pusha{self.assign_counter}"
                        self.assign_counter += 1
                        self.emit(f"{c_type(et)} {tmp} = {val};")
                        self.emit(f"forge_arr_inc({tmp}.ref);")
                        val = tmp
                    ptr = f"__forge_pp{self.assign_counter}"
                    self.assign_counter += 1
                    self.emit(f"{c_type(self.expr_type(call.args[0]))} *{ptr} = &{var_code};")
                    elem_c = c_type(et)
                    # Copy-on-write (batch-18 gap): the scalar push
                    # helpers detach a shared array before growing
                    # it, but this inline path used to realloc the
                    # shared buffer in place — dangling the other
                    # holders and double-freeing at scope exit.
                    # Detach first, mirroring FORGE_ARRAY_HELPERS:
                    # fresh buffer, copy slots gaining an inner
                    # reference each (the free path decrements one
                    # per slot, so the inc keeps the counts exact),
                    # drop this holder's count on the old buffer
                    # without freeing it — the other holders still
                    # own it.
                    ocap = f"__forge_ocap{self.assign_counter}"
                    self.assign_counter += 1
                    nbuf = f"__forge_nbuf{self.assign_counter}"
                    self.assign_counter += 1
                    li = f"__forge_li{self.assign_counter}"
                    self.assign_counter += 1
                    self.emit(f"if ({ptr}->ref && *{ptr}->ref > 1) {{")
                    self.emit(f"    long long {ocap} = {ptr}->cap ? {ptr}->cap : 4;")
                    self.emit(f"    {elem_c} *{nbuf} = ({elem_c} *)malloc(sizeof({elem_c}) * (size_t){ocap});")
                    self.emit(f"    if (!{nbuf}) forge_fail(\"out of memory\");")
                    self.emit(f"    for (long long {li} = 0; {li} < {ptr}->len; {li}++) {{ {nbuf}[{li}] = {ptr}->data[{li}]; forge_arr_inc({nbuf}[{li}].ref); }}")
                    self.emit(f"    (*{ptr}->ref)--;")
                    self.emit(f"    {ptr}->data = {nbuf}; {ptr}->cap = {ocap}; {ptr}->ref = forge_arr_ref_new();")
                    self.emit("}")
                    ncap = f"__forge_ncap{self.assign_counter}"
                    self.assign_counter += 1
                    self.emit(f"if ({ptr}->len >= {ptr}->cap) {{")
                    self.emit(f"    long long {ncap} = {ptr}->cap ? {ptr}->cap * 2 : 4;")
                    self.emit(f"    {elem_c} *nd = ({elem_c} *)realloc({ptr}->data, sizeof({elem_c}) * (size_t){ncap});")
                    self.emit('    if (!nd) forge_fail("out of memory");')
                    self.emit(f"    {ptr}->data = nd; {ptr}->cap = {ncap};")
                    self.emit("}")
                    self.emit(f"{ptr}->data[{ptr}->len++] = {val};")
                else:
                    self.emit(f"{PUSH_FN[et]}(&{var_code}, {val});")
                return
            if isinstance(call, A.Call) and call.name == "fail":
                self.emit(f'fprintf(stderr, "qasida: %s\\n", {self.gen_expr(call.args[0])});')
                self.emit("exit(1);")
                return
            if isinstance(call, A.Call) and call.name == "pin":
                # Pinning is compile-time only (Top-500 #34): the
                # checker enforces immovability, so there is no
                # runtime effect and no code to emit.
                return
            self.emit(f"{self.gen_expr(stmt.expr)};")
            return
        raise ForgeError(f"unsupported statement {type(stmt).__name__}")

    def gen_print(self, call):
        newline = call.name == "println"
        for idx, arg in enumerate(call.args):
            t = self.expr_type(arg)
            code = self.gen_expr(arg)
            if t == "int":
                self.emit(f'printf("%lld", {code});')
            elif is_fixed_int(t):
                if t in ("i8", "i16", "i32"):
                    self.emit(f'printf("%lld", (long long)({code}));')
                else:
                    self.emit(f'printf("%llu", (unsigned long long)({code}));')
            elif t == "float":
                self.emit(f'printf("%.6g", {code});')
            elif t == "bool":
                self.emit(f'printf("%s", {code} ? "true" : "false");')
            elif t == "str":
                self.emit(f'printf("%s", {code});')
            else:
                raise ForgeError(f"cannot print a value of type {t}", call.line, call.col)
            if idx < len(call.args) - 1:
                self.emit('printf(" ");')
        if newline:
            self.emit('printf("\\n");')

    def gen_expr(self, expr):
        if self.freestanding:
            # Freestanding v1 has no allocator: strings and arrays
            # have no values, so any program that builds one fails
            # here with a clear error, never with a C or link error.
            if isinstance(expr, (A.StrLit, A.ArrayLit)):
                raise ForgeError("freestanding v1 does not support strings/arrays yet",
                                 expr.line, expr.col)
            t = self.expr_type(expr)
            if t == "str" or self.is_array_type(t):
                raise ForgeError("freestanding v1 does not support strings/arrays yet",
                                 expr.line, expr.col)
            if t in self.structs:
                # A struct value carrying str/array fields would need
                # the hosted copy/free helpers on use; reject it here
                # rather than at link time.
                for ft in self.structs[t].values():
                    if ft == "str" or self.is_array_type(ft):
                        raise ForgeError("freestanding v1 does not support strings/arrays yet",
                                         expr.line, expr.col)
        if isinstance(expr, A.IntLit):
            return f"{expr.value}LL"
        if isinstance(expr, A.FloatLit):
            return repr(float(expr.value))
        if isinstance(expr, A.StrLit):
            return self.c_str_literal(expr.value)
        if isinstance(expr, A.BoolLit):
            return "true" if expr.value else "false"
        if isinstance(expr, A.Var):
            if expr.name in self._enum_variant_map():
                enum_name, tag, payload_type = self._enum_variant_map()[expr.name]
                _params, payloads, _vs = self.enum_templates[enum_name]
                if any(p is not None for p in payloads.values()):
                    if payload_type is not None:
                        raise ForgeError(f"variant '{expr.name}' has a payload; write {expr.name}(value)")
                    et = self.expr_type(expr)
                    return f"({c_type(et)}){{ .tag = {tag} }}"
            return expr.name
        if isinstance(expr, A.RangeLit):
            # A range is just its two endpoints; nothing is
            # materialized, so iteration and methods stay O(1).
            return (f"(ForgeRange){{ .start = {self.gen_expr(expr.start)}, "
                    f".end = {self.gen_expr(expr.end)} }}")
        if isinstance(expr, A.TupleLit):
            t = self.expr_type(expr)
            cname = c_type(t)
            elems = tuple_elems(t)
            parts = []
            for i, eexpr in enumerate(expr.elems):
                code = self.gen_expr(eexpr)
                et = elems[i]
                if self.expr_type(eexpr) == "never":
                    code = self.never_wrap(code, et)
                if et == "str":
                    code = f"forge_copy_str({code})"
                elif is_union_type(et):
                    evt = self.expr_type(eexpr)
                    if evt in union_members(et):
                        copy_str = evt == "str" and not self.is_fresh_str(eexpr)
                        code = self.union_wrap(code, evt, et, copy_str=copy_str)
                    elif evt == et and not self.is_fresh_union(eexpr):
                        self.assign_counter += 1
                        n = self.assign_counter
                        copy = self.union_copy_stmt(f"__forge_arg{n}", et)
                        code = (f"({{{c_type(et)} __forge_arg{n} = {code}; "
                                f"{copy} __forge_arg{n};}})")
                elif is_opaque_type(et):
                    code = self.opaque_convert(code, self.expr_type(eexpr),
                                               et, eexpr)
                elif self.is_array_type(et) and not self.is_fresh_array(eexpr):
                    self.assign_counter += 1
                    n = self.assign_counter
                    code = (f"({{{c_type(et)} __forge_arg{n} = {code}; "
                            f"forge_arr_inc(__forge_arg{n}.ref); __forge_arg{n};}})")
                elif self.is_struct_type(et) and not self.is_fresh_struct(eexpr):
                    self.assign_counter += 1
                    n = self.assign_counter
                    own = self.struct_own_code(f"__forge_arg{n}", et)
                    code = (f"({{{c_type(et)} __forge_arg{n} = {code}; "
                            f"{own} __forge_arg{n};}})")
                elif is_tuple_type(et) and not self.is_fresh_tuple(eexpr):
                    self.assign_counter += 1
                    n = self.assign_counter
                    own = self.tuple_own_code(f"__forge_arg{n}", et)
                    code = (f"({{{c_type(et)} __forge_arg{n} = {code}; "
                            f"{own} __forge_arg{n};}})")
                parts.append(code)
            return f"({cname}){{ {', '.join(parts)} }}"
        if isinstance(expr, A.StructLit):
            concrete = getattr(expr, "concrete_type", None) or expr.name
            cname = c_type(concrete)
            fields = self.structs.get(cname, self.structs.get(expr.name, {}))
            parts = []
            for fname, fexpr in expr.fields:
                code = self.gen_expr(fexpr)
                ft = fields.get(fname)
                if self.expr_type(fexpr) == "never" and ft:
                    code = self.never_wrap(code, ft)
                if ft == "str":
                    code = f"forge_copy_str({code})"
                elif ft and is_union_type(ft):
                    fvt = self.expr_type(fexpr)
                    if fvt in union_members(ft):
                        copy_str = fvt == "str" and not self.is_fresh_str(fexpr)
                        code = self.union_wrap(code, fvt, ft, copy_str=copy_str)
                    elif fvt == ft and not self.is_fresh_union(fexpr):
                        # Shared union stored in a struct: struct
                        # gains an independent str payload, if any.
                        self.assign_counter += 1
                        n = self.assign_counter
                        copy = self.union_copy_stmt(f"__forge_arg{n}", ft)
                        code = (f"({{{c_type(ft)} __forge_arg{n} = {code}; "
                                f"{copy} __forge_arg{n};}})")
                elif ft and self.is_array_type(ft) and not self.is_fresh_array(fexpr):
                    # Shared array stored in a struct: struct gains a reference.
                    self.assign_counter += 1
                    n = self.assign_counter
                    code = (f"({{{c_type(ft)} __forge_arg{n} = {code}; "
                            f"forge_arr_inc(__forge_arg{n}.ref); __forge_arg{n};}})")
                elif ft and self.is_struct_type(ft) and not self.is_fresh_struct(fexpr):
                    # Shared nested struct stored in a struct: gain independent fields.
                    self.assign_counter += 1
                    n = self.assign_counter
                    own = self.struct_own_code(f"__forge_arg{n}", ft)
                    code = (f"({{{c_type(ft)} __forge_arg{n} = {code}; "
                            f"{own} __forge_arg{n};}})")
                elif ft and is_tuple_type(ft) and not self.is_fresh_tuple(fexpr):
                    # Shared tuple stored in a struct: gain independent elements.
                    self.assign_counter += 1
                    n = self.assign_counter
                    own = self.tuple_own_code(f"__forge_arg{n}", ft)
                    code = (f"({{{c_type(ft)} __forge_arg{n} = {code}; "
                            f"{own} __forge_arg{n};}})")
                parts.append(f".{fname} = {code}")
            return f"({cname}){{ {', '.join(parts)} }}"
        if isinstance(expr, A.TupleIndex):
            base = self.gen_expr(expr.base)
            return f"({base})._{expr.index}"
        if isinstance(expr, A.FieldAccess):
            if (isinstance(expr.base, A.Index)
                    and self.is_array_type(self.expr_type(expr.base.base))
                    and self.is_struct_type(self.expr_type(expr.base))):
                # Direct field read from a struct-array element: no
                # full owned copy, so no leaked sibling fields.
                arr_t = c_type(self.expr_type(expr.base.base))
                arr = self.gen_expr(expr.base.base)
                idx = self.gen_expr(expr.base.index)
                if self.mode == "safe":
                    fa_key = ("fa", arr, idx, expr.field)
                    fa_pure = (not self._subtree_has_call(expr.base.base)
                               and not self._subtree_has_call(expr.base.index))
                    if fa_pure and fa_key in self._check_cache:
                        return f"({arr}).data[{idx}].{expr.field}"
                    tmp_a = f"__forge_fa{self.arr_counter}"
                    tmp_i = f"__forge_fi{self.arr_counter}"
                    self.arr_counter += 1
                    if fa_pure:
                        self._check_cache[fa_key] = True
                    return (f"({{ {arr_t} {tmp_a} = {arr}; long long {tmp_i} = {idx}; "
                            f"if ({tmp_i} < 0 || {tmp_i} >= {tmp_a}.len) "
                            f"forge_fail(\"array index out of bounds\"); "
                            f"{tmp_a}.data[{tmp_i}].{expr.field}; }})")
                return f"({arr}).data[{idx}].{expr.field}"
            base = self.gen_expr(expr.base)
            return f"({base}).{expr.field}"
        if isinstance(expr, A.ArrayLit):
            arr_type = self.expr_type(expr)
            if arr_type in ("[?]", "int"):
                raise ForgeError("array literal needs a known element type "
                                 "(annotate the variable or use non-empty literal)",
                                 expr.line, expr.col)
            et = elem_of(arr_type)
            struct = c_type(arr_type)
            elem_c = c_type(et)
            tmp = f"__forge_arr{self.arr_counter}"
            self.arr_counter += 1
            n = len(expr.elems)
            parts = [f"{struct} {tmp}"]
            body = f"{tmp}.len = {n}; {tmp}.cap = {n}; {tmp}.ref = forge_arr_ref_new(); "
            body += f"{tmp}.data = " + (f"( {elem_c} *)malloc(sizeof({elem_c}) * {n})" if n else "NULL") + "; "
            for i, e in enumerate(expr.elems):
                code = self.gen_expr(e)
                if et == "str":
                    code = f"forge_copy_str({code})"
                body += f"{tmp}.data[{i}] = {code}; "
                if self.is_struct_type(et) and not self.is_fresh_struct(e):
                    # Shared struct element: gain independent fields
                    # for the array's copy.
                    own = self.struct_own_code(f"{tmp}.data[{i}]", et)
                    if own:
                        body += f"{own} "
                elif self.is_array_type(et) and not self.is_fresh_array(e):
                    # Shared array element: gain a reference for the
                    # outer array's copy.
                    body += f"forge_arr_inc({tmp}.data[{i}].ref); "
            body += f"{tmp}"
            return "({" + " ".join(parts) + "; " + body + "; })"
        if isinstance(expr, A.Index):
            idx_pure = (not self._subtree_has_call(expr.base)
                        and not self._subtree_has_call(expr.index))
            if self.expr_type(expr.base) == "str":
                base = self.gen_expr(expr.base)
                idx = self.gen_expr(expr.index)
                if self.mode == "safe":
                    key = ("str", base, idx)
                    if idx_pure and key in self._check_cache:
                        return f"forge_str_at_fast({base}, {idx})"
                    if idx_pure:
                        self._check_cache[key] = True
                    return f"forge_str_at({base}, {idx})"
                return f"forge_str_at_fast({base}, {idx})"
            et = self.expr_type(expr)
            base = self.gen_expr(expr.base)
            idx = self.gen_expr(expr.index)
            if self.is_struct_type(et):
                if self.mode == "safe":
                    key = ("arr", base, idx)
                    if idx_pure and key in self._check_cache:
                        return f"forge_{self.struct_type_name(et)}_get_fast({base}, {idx})"
                    if idx_pure:
                        self._check_cache[key] = True
                    return f"forge_{self.struct_type_name(et)}_get({base}, {idx})"
                return f"forge_{self.struct_type_name(et)}_get_fast({base}, {idx})"
            if self.is_array_type(et):
                # Array element: a shared refcounted value. Safe mode
                # bounds-checks via temps (single evaluation); the
                # caller gains a reference when storing it.
                if self.mode == "safe":
                    key = ("arr", base, idx)
                    if idx_pure and key in self._check_cache:
                        return f"({base}).data[{idx}]"
                    arr_t = c_type(self.expr_type(expr.base))
                    tmp_a = f"__forge_ia{self.arr_counter}"
                    tmp_i = f"__forge_ii{self.arr_counter}"
                    self.arr_counter += 1
                    if idx_pure:
                        self._check_cache[key] = True
                    return (f"({{ {arr_t} {tmp_a} = {base}; long long {tmp_i} = {idx}; "
                            f"if ({tmp_i} < 0 || {tmp_i} >= {tmp_a}.len) "
                            f"forge_fail(\"array index out of bounds\"); "
                            f"{tmp_a}.data[{tmp_i}]; }})")
                return f"({base}).data[{idx}]"
            if self.mode == "safe":
                key = ("arr", base, idx)
                if idx_pure and key in self._check_cache:
                    return f"({base}).data[{idx}]"
                if idx_pure:
                    self._check_cache[key] = True
                return f"{GET_FN[et]}({base}, {idx})"
            return f"({base}).data[{idx}]"
        if isinstance(expr, A.Cast):
            code = self.gen_expr(expr.expr)
            if is_union_type(expr.target):
                inner_type = self.expr_type(expr.expr)
                copy_str = inner_type == "str" and not self.is_fresh_str(expr.expr)
                return self.union_wrap(code, inner_type, expr.target,
                                       copy_str=copy_str)
            inner_type = self.expr_type(expr.expr)
            if expr.target == "float":
                return f"(double)({code})"
            if is_int_type(inner_type) and is_int_type(expr.target) \
                    and inner_type != expr.target:
                return self.int_cast_code(code, inner_type, expr.target)
            if inner_type == "float" and is_int_type(expr.target):
                return self.float_to_int_cast(code, expr.target)
            return f"(long long)({code})"
        if isinstance(expr, A.Try):
            n = self.try_counter
            self.try_counter += 1
            inner = self.gen_expr(expr.expr)
            inner_type = self.expr_type(expr.expr)
            ret_type = getattr(expr, "ret_type", None) or self.func_ret.get(self.current_fn, "void")
            c_inner = c_type(inner_type)
            c_ret = c_type(ret_type)
            temp = f"__forge_try{n}"
            if expr.kind == "Option":
                if ret_type == inner_type:
                    early = f"return {temp};"
                else:
                    y = ret_type[ret_type.find("<") + 1:ret_type.rfind(">")] if "<" in ret_type else "int"
                    dummy = {"int": "0", "float": "0.0", "bool": "false", "str": 'forge_copy_str("")'}.get(y)
                    if dummy is None:
                        raise ForgeError("? for Option with a non-scalar return value type is not supported yet")
                    early = f"return ({c_ret}){{ .present = false, .value = {dummy} }};"
                return (f"({{ {c_inner} {temp} = {inner}; "
                        f"if (!{temp}.present) {{ {early} }} {temp}.value; }})")
            if expr.kind == "Result":
                if ret_type == inner_type:
                    early = f"return {temp};"
                else:
                    ret_args = ret_type[ret_type.find("<") + 1:ret_type.rfind(">")].split(",")
                    y = ret_args[0].strip() if ret_args else "int"
                    e = ret_args[1].strip() if len(ret_args) > 1 else "str"
                    dummy = {"int": "0", "float": "0.0", "bool": "false", "str": 'forge_copy_str("")'}.get(y)
                    if dummy is None:
                        raise ForgeError("? for Result with a non-scalar return value type is not supported yet")
                    err_code = f"forge_copy_str({temp}.error)" if e == "str" else f"{temp}.error"
                    early = f"return ({c_ret}){{ .ok = false, .value = {dummy}, .error = {err_code} }};"
                return (f"({{ {c_inner} {temp} = {inner}; "
                        f"if (!{temp}.ok) {{ {early} }} {temp}.value; }})")
            raise ForgeError("? expression was not checked as Option/Result")
        if isinstance(expr, A.UnaryOp):
            if expr.op == "-" and self.expr_type(expr.expr) == "int" and self.mode == "safe":
                code = self.gen_expr(expr.expr)
                iv = self._int_interval(expr.expr)
                if iv is not None and iv[0] > self.INT_MIN:
                    return f"(-{code})"
                return f"forge_neg({code})"
            if expr.op == "-" and is_fixed_int(self.expr_type(expr.expr)) and self.mode == "safe":
                t = self.expr_type(expr.expr)
                code = self.gen_expr(expr.expr)
                ct = FIXED_C_TYPES[t]
                if t in ("i8", "i16", "i32"):
                    tmp = self._fx_temp()
                    lo, hi = fixed_range(t)
                    return (f"({{long long {tmp} = -(long long)({code}); "
                            f"if ({tmp} < {lo} || {tmp} > {hi}) "
                            f"forge_fail(\"integer overflow\"); ({ct})({tmp});}})")
                tmp = self._fx_temp()
                return (f"({{unsigned long long {tmp} = "
                        f"(unsigned long long)({code}); "
                        f"if ({tmp} != 0) forge_fail(\"integer overflow\"); "
                        f"({ct})(0);}})")
            return f"({expr.op}{self.gen_expr(expr.expr)})"
        if isinstance(expr, A.BinOp):
            if expr.op in ("==", "!=") and self.expr_type(expr.left) == "str":
                spec = self._str_index_cmp(expr)
                if spec is not None:
                    return spec
            left = self.gen_expr(expr.left)
            right = self.gen_expr(expr.right)
            if expr.op == "+" and self.expr_type(expr.left) == "str":
                return f"forge_concat({left}, {right})"
            if expr.op == "==" and self.expr_type(expr.left) == "str":
                return f"(strcmp({left}, {right}) == 0)"
            if expr.op == "!=" and self.expr_type(expr.left) == "str":
                return f"(strcmp({left}, {right}) != 0)"
            if self.expr_type(expr.left) == "int" and self.expr_type(expr.right) == "int":
                if self.mode == "safe":
                    checked = {"+": "forge_add", "-": "forge_sub", "*": "forge_mul",
                               "/": "forge_div", "%": "forge_mod"}
                    if expr.op in checked:
                        if self._binop_safe(expr.op, expr.left, expr.right):
                            return f"({left} {expr.op} {right})"
                        pure = (not self._subtree_has_call(expr.left)
                                and not self._subtree_has_call(expr.right))
                        key = ("bin", expr.op, left, right)
                        if pure and key in self._check_cache:
                            return f"({left} {expr.op} {right})"
                        if pure:
                            self._check_cache[key] = True
                        return f"{checked[expr.op]}({left}, {right})"
                # Bitwise shifts have defined two's-complement semantics:
                # << wraps through uint64, >> is arithmetic, and the
                # count is masked to 0..63 so all backends agree
                # (WASM masks to 64, big32 masks to 32 — see the
                # freestanding docs for the cross-backend note).
                if expr.op == "<<":
                    return f"((int64_t)((uint64_t)({left}) << ((uint64_t)({right}) & 63)))"
                if expr.op == ">>":
                    return f"(({left}) >> (({right}) & 63))"
            lt_t = self.expr_type(expr.left)
            rt_t = self.expr_type(expr.right)
            ft = lt_t if is_fixed_int(lt_t) else (rt_t if is_fixed_int(rt_t) else None)
            if ft is not None:
                if self.mode == "safe" and expr.op in ("+", "-", "*", "/", "%", "<<", ">>"):
                    return self.fixed_checked_binop(expr.op, left, right, ft)
                if expr.op in ("<<", ">>"):
                    # Fast mode: shifts mask the count to the width,
                    # like int shifts mask to 0..63.
                    width = FIXED_WIDTHS[ft]
                    mask = width - 1
                    if expr.op == "<<":
                        uct = {"i8": "uint8_t", "i16": "uint16_t", "i32": "uint32_t",
                               "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t",
                               "u64": "uint64_t"}[ft]
                        return f"(({FIXED_C_TYPES[ft]})(({uct})({left}) << (({right}) & {mask})))"
                    return f"(({left}) >> (({right}) & {mask}))"
            return f"({left} {expr.op} {right})"
        if isinstance(expr, A.MethodCall):
            # Opaque receiver: dispatch on the tag. The receiver is
            # evaluated once into a temp; each case calls the
            # implementing struct's mangled method with the payload.
            # Arguments are converted once, as for ordinary calls
            # (string arguments copied, shared arrays referenced,
            # shared structs owned), and used by every case.
            from .traits import mangle
            struct_t = self.expr_type(expr.base)
            if struct_t == "range":
                # Built-in range methods. The receiver is evaluated
                # once into a temp; len and sum use unsigned
                # arithmetic so the full int64 span cannot overflow
                # the difference, and fail in safe mode when the
                # result itself does not fit in int.
                self.loop_counter += 1
                n = self.loop_counter
                recv = f"__forge_rng{n}"
                recv_code = self.gen_expr(expr.base)
                if expr.method == "start":
                    return f"({{ ForgeRange {recv} = {recv_code}; {recv}.start; }})"
                if expr.method == "end":
                    return f"({{ ForgeRange {recv} = {recv_code}; {recv}.end; }})"
                if expr.method == "contains":
                    arg = self.gen_expr(expr.args[0])
                    return (f"({{ ForgeRange {recv} = {recv_code}; "
                            f"long long __forge_x{n} = {arg}; "
                            f"({recv}.start <= __forge_x{n} && __forge_x{n} < {recv}.end); }})")
                if expr.method == "len":
                    if self.mode == "safe":
                        return (f"({{ ForgeRange {recv} = {recv_code}; long long __forge_l{n} = 0; "
                                f"if ({recv}.end > {recv}.start) {{ "
                                f"unsigned long long __forge_d{n} = (unsigned long long){recv}.end - (unsigned long long){recv}.start; "
                                f"if (__forge_d{n} > 9223372036854775807ULL) forge_fail(\"integer overflow\"); "
                                f"__forge_l{n} = (long long)__forge_d{n}; }} __forge_l{n}; }})")
                    return (f"({{ ForgeRange {recv} = {recv_code}; "
                            f"({recv}.end > {recv}.start ? (long long)((unsigned long long){recv}.end - (unsigned long long){recv}.start) : 0); }})")
                if expr.method == "sum":
                    # Arithmetic series: n * (first + last) / 2, in
                    # __int128 so the intermediate is exact for
                    # every int64 span; the result is checked
                    # against int64 in safe mode.
                    if self.mode == "safe":
                        return (f"({{ ForgeRange {recv} = {recv_code}; __int128 __forge_s{n} = 0; "
                                f"if ({recv}.end > {recv}.start) {{ "
                                f"__int128 __forge_n{n} = (__int128)((unsigned long long){recv}.end - (unsigned long long){recv}.start); "
                                f"__forge_s{n} = __forge_n{n} * ((__int128){recv}.start + (__int128){recv}.end - 1) / 2; "
                                f"if (__forge_s{n} > 9223372036854775807 || __forge_s{n} < (-9223372036854775807 - 1)) forge_fail(\"integer overflow\"); }} "
                                f"(long long)__forge_s{n}; }})")
                    return (f"({{ ForgeRange {recv} = {recv_code}; "
                            f"({recv}.end > {recv}.start ? (long long)(((__int128)((unsigned long long){recv}.end - (unsigned long long){recv}.start)) * ((__int128){recv}.start + (__int128){recv}.end - 1) / 2) : 0); }})")
                raise ForgeError(f"range has no method '{expr.method}'",
                                 expr.line, expr.col)
            if is_opaque_type(struct_t):
                trait = opaque_trait(struct_t)
                impls = impls_for_trait(self.program, trait)
                sigs = {}
                for td in (getattr(self.program, "traits", None) or []):
                    if td.name == trait:
                        sigs = {m: (params, ret)
                                for (m, params, ret, _l, _c) in td.methods}
                params, ret = sigs[expr.method]
                arg_codes = []
                for a, (_pn, pt) in zip(expr.args, params):
                    code = self.gen_expr(a)
                    if pt == "str" and not self.is_fresh_str(a):
                        code = f"forge_copy_str({code})"
                    elif self.is_array_type(pt) and not self.is_fresh_array(a):
                        self.assign_counter += 1
                        n = self.assign_counter
                        code = (f"({{{c_type(pt)} __forge_arg{n} = {code}; "
                                f"forge_arr_inc(__forge_arg{n}.ref); __forge_arg{n};}})")
                    elif self.is_struct_type(pt) and not self.is_fresh_struct(a):
                        self.assign_counter += 1
                        n = self.assign_counter
                        own = self.struct_own_code(f"__forge_arg{n}", pt)
                        code = (f"({{{c_type(pt)} __forge_arg{n} = {code}; "
                                f"{own} __forge_arg{n};}})")
                    arg_codes.append(code)
                self.loop_counter += 1
                n = self.loop_counter
                recv = f"__forge_recv{n}"
                cname = opaque_c_name(struct_t)
                parts = [f"({{{cname} {recv} = {self.gen_expr(expr.base)};"]
                if ret != "void":
                    parts.append(f"{c_type(ret)} __forge_mret{n};")
                parts.append(f"switch ({recv}.tag) {{")
                for i, st in enumerate(impls):
                    mangled = mangle(st, expr.method)
                    # The callee frees its receiver parameter on
                    # return, so it must get an independently owned
                    # copy of the payload, never the caller's own.
                    own = self.struct_own_code(f"__forge_mrecv{n}_{i}", st)
                    if own:
                        recv_code = (f"({{{c_type(st)} __forge_mrecv{n}_{i} = "
                                     f"{recv}.payload._{i}; {own} "
                                     f"__forge_mrecv{n}_{i};}})")
                    else:
                        recv_code = f"{recv}.payload._{i}"
                    call = f"{mangled}({recv_code}"
                    if arg_codes:
                        call += ", " + ", ".join(arg_codes)
                    call += ")"
                    parts.append(f"case {i}: {{")
                    if ret != "void":
                        parts.append(f"__forge_mret{n} = {call};")
                    else:
                        parts.append(f"{call};")
                    parts.append("break; }")
                parts.append("}")
                if ret != "void":
                    parts.append(f"__forge_mret{n};")
                parts.append("})")
                return " ".join(parts)
            # Static dispatch: receiver type -> mangled function,
            # receiver passed as the first argument. Delegating to
            # the ordinary Call path keeps struct ownership handling.
            from .traits import mangle
            if struct_t not in self.structs:
                raise ForgeError("trait method call needs a struct "
                                 f"receiver, got {struct_t}",
                                 expr.line, expr.col)
            mangled = mangle(struct_t, expr.method)
            if mangled not in self.func_params:
                raise ForgeError(f"struct '{struct_t}' has no method "
                                 f"'{expr.method}'", expr.line, expr.col)
            return self.gen_expr(A.Call(mangled, [expr.base] +
                                        list(expr.args),
                                        expr.line, expr.col))
        if isinstance(expr, A.Call):
            # A call may mutate shared state (an array passed to it
            # can be written through its parameter), so it ends any
            # duplicate-check run inside this expression.
            self._check_cache = {}
            if expr.name == "len":
                arg = expr.args[0]
                code = self.gen_expr(arg)
                if self.expr_type(arg) == "str":
                    return f"strlen({code})"
                return f"({code}).len"
            if expr.name == "range":
                return f"forge_range({self.gen_expr(expr.args[0])})"
            if expr.name == "clock_micros":
                return "forge_clock_micros()"
            if expr.name in ("sqrt", "exp", "log"):
                return f"{expr.name}({self.gen_expr(expr.args[0])})"
            if expr.name == "pow":
                return f"pow({self.gen_expr(expr.args[0])}, {self.gen_expr(expr.args[1])})"
            if expr.name == "abs":
                return f"llabs({self.gen_expr(expr.args[0])})"
            if expr.name in ("wrapping_add", "wrapping_sub", "wrapping_mul"):
                # Unsigned arithmetic wraps by definition; the cast
                # back reinterprets the bits as signed. This bypasses
                # the checked forge_add/sub/mul helpers on purpose:
                # wrapping is defined behaviour in both modes.
                op = {"wrapping_add": "+", "wrapping_sub": "-",
                      "wrapping_mul": "*"}[expr.name]
                a = self.gen_expr(expr.args[0])
                b = self.gen_expr(expr.args[1])
                return (f"((long long)((unsigned long long)({a}) {op} "
                        f"(unsigned long long)({b})))")
            if expr.name == "wrapping_neg":
                a = self.gen_expr(expr.args[0])
                return f"((long long)(0ULL - (unsigned long long)({a})))"
            if expr.name == "file_exists":
                return f"forge_file_exists({self.gen_expr(expr.args[0])})"
            if expr.name == "read_file":
                return f"forge_read_file({self.gen_expr(expr.args[0])})"
            if expr.name == "read_line":
                return "forge_read_line()"
            if expr.name == "peek32":
                return f"forge_peek32({self.gen_expr(expr.args[0])})"
            if expr.name == "poke32":
                return (f"forge_poke32({self.gen_expr(expr.args[0])}, "
                        f"{self.gen_expr(expr.args[1])})")
            if expr.name in ("csr_read", "csr_write", "csr_set", "csr_clear", "ecall", "ecall3"):
                raise ForgeError(f"{expr.name}() needs RISC-V CSRs/ecall "
                                 f"(big32 target only)",
                                 expr.line, expr.col)
            if expr.name == "write_file":
                return (f"forge_write_file({self.gen_expr(expr.args[0])}, "
                        f"{self.gen_expr(expr.args[1])})")
            if expr.name == "read_bytes":
                return f"forge_read_bytes({self.gen_expr(expr.args[0])})"
            if expr.name == "try_alloc":
                # Top-500 #36: fallible allocation. A GNU statement
                # expression (the codebase's established pattern for
                # multi-statement builtins): evaluate n once, then
                # calloc for a zero-initialised [int]; NULL (or a bad
                # size) yields an Err Result instead of forge_fail.
                # The empty array in the Err path gets a fresh ref
                # (the forge_arr_ref_new() pattern from weak_upgrade);
                # the error str is a heap copy (forge_copy_str) so the
                # Result owns it and its free is safe. v1 limit: the
                # tiny bookkeeping mallocs (refcount, error copy) can
                # still forge_fail if the system is truly out of
                # memory; only the big calloc is fallible.
                self.assign_counter += 1
                n = self.assign_counter
                n_code = self.gen_expr(expr.args[0])
                rt = c_type("Result<[int], str>")
                empty = "(ForgeIntArray){NULL, 0, 0, forge_arr_ref_new()}"
                err = (f"({rt}){{ .ok = false, .value = {empty}, "
                       f".error = forge_copy_str(\"%s\") }}")
                return (
                    f"({{ {rt} __forge_tryalloc{n}; "
                    f"long long __forge_n{n} = {n_code}; "
                    f"if (__forge_n{n} < 0) {{ "
                    f"__forge_tryalloc{n} = {err % 'bad size'}; }} "
                    f"else if (__forge_n{n} == 0) {{ "
                    f"__forge_tryalloc{n} = ({rt}){{ .ok = true, .value = {empty}, "
                    f".error = forge_copy_str(\"\") }}; }} "
                    f"else {{ "
                    f"long long *__forge_data{n} = (long long *)calloc("
                    f"(size_t)__forge_n{n}, sizeof(long long)); "
                    f"if (!__forge_data{n}) {{ "
                    f"__forge_tryalloc{n} = {err % 'out of memory'}; }} "
                    f"else {{ ForgeIntArray __forge_arr{n}; "
                    f"__forge_arr{n}.len = __forge_n{n}; "
                    f"__forge_arr{n}.cap = __forge_n{n}; "
                    f"__forge_arr{n}.data = __forge_data{n}; "
                    f"__forge_arr{n}.ref = forge_arr_ref_new(); "
                    f"__forge_tryalloc{n} = ({rt}){{ .ok = true, "
                    f".value = __forge_arr{n}, "
                    f".error = forge_copy_str(\"\") }}; }} }} "
                    f"__forge_tryalloc{n}; }})"
                )
            if expr.name == "write_bytes":
                # Ownership (audit fix): forge_write_bytes FREES
                # its array parameter (batch 25), but builtin
                # callers transfer nothing — so a variable
                # argument lost its hold (UAF, audit probes P1/P2).
                # Follow the ordinary function-parameter rule:
                # non-fresh array arguments arrive with an extra
                # hold the helper frees; fresh arguments arrive
                # as-is and are freed. The path stays borrowed,
                # like every other str parameter.
                path_code = self.gen_expr(expr.args[0])
                data = expr.args[1]
                data_code = self.gen_expr(data)
                if not self.is_fresh_array(data):
                    self.assign_counter += 1
                    n = self.assign_counter
                    data_code = (f"({{{c_type(self.expr_type(data))} __forge_arg{n} = {data_code}; "
                                 f"forge_arr_inc(__forge_arg{n}.ref); __forge_arg{n};}})")
                return f"forge_write_bytes({path_code}, {data_code})"
            if expr.name == "args":
                return "forge_args_global"
            if expr.name == "parse_float":
                return f"forge_parse_float({self.gen_expr(expr.args[0])})"
            if expr.name == "parse_int":
                return f"forge_parse_int({self.gen_expr(expr.args[0])})"
            if expr.name == "split":
                return (f"forge_split({self.gen_expr(expr.args[0])}, "
                        f"{self.gen_expr(expr.args[1])})")
            if expr.name == "join":
                return (f"forge_join({self.gen_expr(expr.args[0])}, "
                        f"{self.gen_expr(expr.args[1])})")
            if expr.name == "substr":
                return (f"forge_substr({self.gen_expr(expr.args[0])}, "
                        f"{self.gen_expr(expr.args[1])}, {self.gen_expr(expr.args[2])})")
            if expr.name == "trim":
                return f"forge_trim({self.gen_expr(expr.args[0])})"
            if expr.name == "starts_with":
                return (f"forge_starts_with({self.gen_expr(expr.args[0])}, "
                        f"{self.gen_expr(expr.args[1])})")
            if expr.name == "ends_with":
                return (f"forge_ends_with({self.gen_expr(expr.args[0])}, "
                        f"{self.gen_expr(expr.args[1])})")
            if expr.name == "http_get":
                return f"forge_http_get({self.gen_expr(expr.args[0])})"
            if expr.name == "http_listen":
                return f"forge_http_listen({self.gen_expr(expr.args[0])})"
            if expr.name == "http_accept":
                return f"forge_http_accept({self.gen_expr(expr.args[0])})"
            if expr.name == "http_read_request":
                return f"forge_http_read_request({self.gen_expr(expr.args[0])})"
            if expr.name == "http_respond":
                return f"forge_http_respond({self.gen_expr(expr.args[0])}, {self.gen_expr(expr.args[1])})"
            if expr.name == "http_respond_status":
                return f"forge_http_respond_status({self.gen_expr(expr.args[0])}, {self.gen_expr(expr.args[1])}, {self.gen_expr(expr.args[2])})"
            if expr.name == "http_close":
                return f"forge_http_close({self.gen_expr(expr.args[0])})"
            if expr.name in ("alloc_count", "free_count"):
                return "forge_str_allocs" if expr.name == "alloc_count" else "forge_str_frees"
            if expr.name in ("arr_alloc_count", "arr_free_count"):
                return "forge_arr_allocs" if expr.name == "arr_alloc_count" else "forge_arr_frees"
            if expr.name == "refcount":
                # Read the array's holder count WITHOUT gaining a
                # holder: the temp is a plain copy of the array
                # struct, never inc'd and never freed, so the
                # observed count is exactly the program's own.
                self.assign_counter += 1
                n = self.assign_counter
                at = self.expr_type(expr.args[0])
                code = self.gen_expr(expr.args[0])
                return (f"({{{c_type(at)} __forge_arg{n} = {code}; "
                        f"__forge_arg{n}.ref ? *__forge_arg{n}.ref : 0;}})")
            if expr.name == "move":
                # Transfer, not copy: the freshness helpers make
                # the receiving Let/Assign/Call-arg/Return sites
                # skip their inc too, so the hold arrives exactly
                # once. A straight-line move forgets the source
                # at compile time; a conditional move (checker
                # annotation) sets a runtime flag instead — the
                # branch or loop may not run, so only the flag
                # can tell scope-end frees whether the hold
                # already left. A second conditional move fails
                # at runtime instead of transferring a freed
                # buffer a second time. A field move records
                # its path so struct frees skip that field.
                arg = expr.args[0]
                if isinstance(arg, A.FieldAccess):
                    path = self._field_path(arg)
                    if path is not None:
                        self.moved_fields.add(path)
                    return self.gen_expr(arg)
                if getattr(expr, "in_conditional", False):
                    flag = self.moved_flag(arg.name)
                    return (f"({{ if ({flag}) forge_fail(\"use of moved value "
                            f"'{arg.name}'\"); {flag} = 1; "
                            f"{self.gen_expr(arg)}; }})")
                self.owned_forget(arg.name)
                return self.gen_expr(arg)
            if expr.name == "mmap_open":
                return f"forge_mmap_open({self.gen_expr(expr.args[0])})"
            if expr.name == "mmap_get":
                return f"forge_mmap_get({self.gen_expr(expr.args[0])}, {self.gen_expr(expr.args[1])})"
            if expr.name == "mmap_set":
                return f"forge_mmap_set({self.gen_expr(expr.args[0])}, {self.gen_expr(expr.args[1])}, {self.gen_expr(expr.args[2])})"
            if expr.name == "mmap_close":
                return f"forge_mmap_close({self.gen_expr(expr.args[0])})"
            if expr.name == "mmap_grow":
                return f"forge_mmap_grow({self.gen_expr(expr.args[0])}, {self.gen_expr(expr.args[1])})"
            if expr.name == "mmap_get32":
                return f"forge_mmap_get32({self.gen_expr(expr.args[0])}, {self.gen_expr(expr.args[1])})"
            if expr.name == "mmap_set32":
                return f"forge_mmap_set32({self.gen_expr(expr.args[0])}, {self.gen_expr(expr.args[1])}, {self.gen_expr(expr.args[2])})"
            if expr.name == "weak_new":
                # Register without gaining a holder: the weak
                # must not keep the array alive.
                self.assign_counter += 1
                n = self.assign_counter
                code = self.gen_expr(expr.args[0])
                return (f"({{ForgeIntArray __forge_arg{n} = {code}; "
                        f"forge_weak_register(__forge_arg{n});}})")
            if expr.name == "weak_upgrade":
                # (alive, array): alive fills the array with an
                # inc (a genuine strong hold for the caller);
                # dead fills an empty array the caller ignores.
                self.assign_counter += 1
                n = self.assign_counter
                self.assign_counter += 1
                m = self.assign_counter
                id_code = self.gen_expr(expr.args[0])
                return (f"({{long long __forge_arg{n} = {id_code}; "
                        f"ForgeTuple_bool_Arr_int __forge_arg{m}; "
                        f"__forge_arg{m}._0 = forge_weak_get(__forge_arg{n}, &__forge_arg{m}._1); "
                        f"if (!__forge_arg{m}._0) {{ __forge_arg{m}._1 = (ForgeIntArray){{NULL, 0, 0, forge_arr_ref_new()}}; }} "
                        f"__forge_arg{m};}})")
            if expr.name == "parallel_dot":
                return f"forge_parallel_dot({self.gen_expr(expr.args[0])}, {self.gen_expr(expr.args[1])})"
            if expr.name == "parallel_matmul":
                return (f"forge_parallel_matmul({self.gen_expr(expr.args[0])}, "
                        f"{self.gen_expr(expr.args[1])}, {self.gen_expr(expr.args[2])})")
            # Enum variant construction: Some(42), None(), Circle(3.0).
            if expr.name in self._enum_variant_map():
                enum_name, tag, payload_type = self._enum_variant_map()[expr.name]
                concrete = getattr(expr, "concrete_type", None) or self.expr_type(expr)
                info = self.enum_concrete_info(concrete)
                if info is None:
                    raise ForgeError(f"enum construction '{expr.name}' has unknown concrete type {concrete}")
                _base, variant_info = info
                if payload_type is None and not any(p is not None for p in self.enum_templates[enum_name][1].values()):
                    # Non-payload enum: bare constant, call syntax is sugar.
                    return expr.name
                cname = c_type(concrete)
                if not expr.args:
                    return f"({cname}){{ .tag = {tag} }}"
                arg_code = self.gen_expr(expr.args[0])
                if payload_type == "str":
                    arg_code = f"forge_copy_str({arg_code})"
                return f"({cname}){{ .tag = {tag}, .payload.payload_{expr.name} = {arg_code} }}"
            # User-function call: string arguments are copied, so the
            # callee owns its parameter and can free it on return.
            # Fresh string arguments are passed as-is (already owned).
            params = self.func_params.get(expr.name, [])
            arg_codes = []
            for a, (_pn, pt) in zip(expr.args, params):
                code = self.gen_expr(a)
                if self.expr_type(a) == "never":
                    code = self.never_wrap(code, pt)
                if is_opaque_type(pt):
                    code = self.opaque_convert(code, self.expr_type(a),
                                               pt, a)
                elif is_union_type(pt):
                    at = self.expr_type(a)
                    if at in union_members(pt):
                        copy_str = at == "str" and not self.is_fresh_str(a)
                        code = self.union_wrap(code, at, pt, copy_str=copy_str)
                    elif at == pt and not self.is_fresh_union(a):
                        # Shared union argument: callee gains an
                        # independent str payload, if any.
                        self.assign_counter += 1
                        n = self.assign_counter
                        copy = self.union_copy_stmt(f"__forge_arg{n}", pt)
                        code = (f"({{{c_type(pt)} __forge_arg{n} = {code}; "
                                f"{copy} __forge_arg{n};}})")
                elif pt == "str" and not self.is_fresh_str(a):
                    code = f"forge_copy_str({code})"
                elif self.is_array_type(pt) and not self.is_fresh_array(a):
                    # Shared array argument: callee gains a reference.
                    self.assign_counter += 1
                    n = self.assign_counter
                    code = (f"({{{c_type(pt)} __forge_arg{n} = {code}; "
                            f"forge_arr_inc(__forge_arg{n}.ref); __forge_arg{n};}})")
                elif self.is_struct_type(pt) and not self.is_fresh_struct(a):
                    # Shared struct argument: callee gains independent fields.
                    self.assign_counter += 1
                    n = self.assign_counter
                    own = self.struct_own_code(f"__forge_arg{n}", pt)
                    code = (f"({{{c_type(pt)} __forge_arg{n} = {code}; "
                            f"{own} __forge_arg{n};}})")
                elif is_tuple_type(pt) and not self.is_fresh_tuple(a):
                    # Shared tuple argument: callee gains independent elements.
                    self.assign_counter += 1
                    n = self.assign_counter
                    own = self.tuple_own_code(f"__forge_arg{n}", pt)
                    code = (f"({{{c_type(pt)} __forge_arg{n} = {code}; "
                            f"{own} __forge_arg{n};}})")
                arg_codes.append(code)
            # Arguments beyond the known signature (should not happen
            # for checked code) are passed through unchanged.
            if len(expr.args) > len(params):
                for a in expr.args[len(params):]:
                    arg_codes.append(self.gen_expr(a))
            return f"{expr.name}({', '.join(arg_codes)})"
        raise ForgeError(f"unsupported expression {type(expr).__name__}")


def generate(program, types, mode="safe", debug=False, freestanding=False):
    gen = Codegen(program, mode=mode, debug=debug, freestanding=freestanding)
    gen.attach_types(types)
    return gen.generate()
