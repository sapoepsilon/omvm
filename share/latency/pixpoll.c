// pixpoll X Y: keeps one wlr-screencopy request for a 1x1 region of the first output
// outstanding, and prints "<monotonic_raw ns> <ready ns monotonic> <red>" whenever the
// red byte crosses 128 (and "first" on the first frame). One persistent connection,
// so the sampling is the compositor's frames, not a process spawn per sample.
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/mman.h>
#include <wayland-client.h>
#include "wlr-screencopy-unstable-v1-client-protocol.h"
static struct wl_shm *shm; static struct wl_output *output; static struct zwlr_screencopy_manager_v1 *mgr;
static int X, Y; static struct wl_buffer *buf; static void *data; static uint32_t bfmt, bw, bh, bstride;
static int done, failed, last = -1; static uint64_t ready_ns;
static uint64_t now(clockid_t c) { struct timespec t; clock_gettime(c, &t); return t.tv_sec * 1000000000ull + t.tv_nsec; }
static void reg(void *d, struct wl_registry *r, uint32_t n, const char *i, uint32_t v) {
    if (!strcmp(i, wl_shm_interface.name)) shm = wl_registry_bind(r, n, &wl_shm_interface, 1);
    else if (!strcmp(i, wl_output_interface.name) && !output) output = wl_registry_bind(r, n, &wl_output_interface, 1);
    else if (!strcmp(i, zwlr_screencopy_manager_v1_interface.name)) mgr = wl_registry_bind(r, n, &zwlr_screencopy_manager_v1_interface, 3);
}
static void regrm(void *d, struct wl_registry *r, uint32_t n) {}
static const struct wl_registry_listener rl = { reg, regrm };
static void f_buffer(void *d, struct zwlr_screencopy_frame_v1 *f, uint32_t fmt, uint32_t w, uint32_t h, uint32_t stride) {
    if (!buf) {
        bfmt = fmt; bw = w; bh = h; bstride = stride;
        int fd = memfd_create("pixpoll", 0); ftruncate(fd, stride * h);
        data = mmap(NULL, stride * h, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        struct wl_shm_pool *p = wl_shm_create_pool(shm, fd, stride * h);
        buf = wl_shm_pool_create_buffer(p, 0, w, h, stride, fmt); wl_shm_pool_destroy(p); close(fd);
    }
}
static void f_flags(void *d, struct zwlr_screencopy_frame_v1 *f, uint32_t fl) {}
static void f_ready(void *d, struct zwlr_screencopy_frame_v1 *f, uint32_t hi, uint32_t lo, uint32_t ns) {
    ready_ns = (((uint64_t)hi << 32) | lo) * 1000000000ull + ns; done = 1;
}
static void f_failed(void *d, struct zwlr_screencopy_frame_v1 *f) { failed = 1; done = 1; }
static void f_damage(void *d, struct zwlr_screencopy_frame_v1 *f, uint32_t x, uint32_t y, uint32_t w, uint32_t h) {}
static void f_dmabuf(void *d, struct zwlr_screencopy_frame_v1 *f, uint32_t a, uint32_t b, uint32_t c) {}
static void f_bdone(void *d, struct zwlr_screencopy_frame_v1 *f) { zwlr_screencopy_frame_v1_copy(f, buf); }
static const struct zwlr_screencopy_frame_v1_listener fl = { f_buffer, f_flags, f_ready, f_failed, f_damage, f_dmabuf, f_bdone };
int main(int argc, char **argv) {
    X = atoi(argv[1]); Y = atoi(argv[2]);
    setvbuf(stdout, NULL, _IOLBF, 0);
    struct wl_display *dpy = wl_display_connect(NULL); if (!dpy) { perror("connect"); return 1; }
    struct wl_registry *r = wl_display_get_registry(dpy); wl_registry_add_listener(r, &rl, NULL); wl_display_roundtrip(dpy);
    if (!mgr || !output || !shm) { fprintf(stderr, "missing globals\n"); return 1; }
    for (;;) {
        done = failed = 0;
        struct zwlr_screencopy_frame_v1 *f = zwlr_screencopy_manager_v1_capture_output_region(mgr, 0, output, X, Y, 1, 1);
        zwlr_screencopy_frame_v1_add_listener(f, &fl, NULL);
        while (!done && wl_display_dispatch(dpy) != -1) {}
        uint64_t t = now(CLOCK_MONOTONIC_RAW);
        zwlr_screencopy_frame_v1_destroy(f);
        if (failed) { fprintf(stderr, "failed\n"); usleep(10000); continue; }
        // XRGB/ARGB8888 little endian: byte 2 is red; bgr formats: byte 0
        unsigned char *p = data; int red = (bfmt == WL_SHM_FORMAT_XBGR8888 || bfmt == WL_SHM_FORMAT_ABGR8888) ? p[0] : p[2];
        int side = red > 128;
        if (last < 0) printf("first %llu %d fmt %x\n", (unsigned long long)t, red, bfmt);
        else if (side != last) printf("%llu %llu %d\n", (unsigned long long)t, (unsigned long long)ready_ns, red);
        last = side;
        { static uint64_t t1 = 0; static int n = 0; n++; if (!t1) t1 = t; if (getenv("PIXPOLL_RATE") && t - t1 >= 1000000000ull) { fprintf(stderr, "rate %d/s\n", n); n = 0; t1 = t; } }
    }
}
