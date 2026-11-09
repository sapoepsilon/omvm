// flipwin: a fullscreen shm xdg-toplevel; each line on stdin flips it white/black and
// commits at once; prints "<monotonic_raw ns at commit> <side>". Compositor floor for
// pixpoll: commit -> composited frame for a plain shm client.
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <poll.h>
#include <sys/mman.h>
#include <wayland-client.h>
#include "xdg-shell-client-protocol.h"
#include "presentation-time-client-protocol.h"
static struct wp_presentation *pres; static uint32_t pres_clk = 1;
static struct wl_compositor *comp; static struct wl_shm *shm; static struct xdg_wm_base *wm;
static int W = 0, H = 0, configured = 0; static struct wl_buffer *buf[2]; static int cur = 0;
static uint64_t now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC_RAW, &t); return t.tv_sec * 1000000000ull + t.tv_nsec; }
static void reg(void *d, struct wl_registry *r, uint32_t n, const char *i, uint32_t v) {
    if (!strcmp(i, "wl_compositor")) comp = wl_registry_bind(r, n, &wl_compositor_interface, 4);
    else if (!strcmp(i, "wl_shm")) shm = wl_registry_bind(r, n, &wl_shm_interface, 1);
    else if (!strcmp(i, "xdg_wm_base")) wm = wl_registry_bind(r, n, &xdg_wm_base_interface, 1);
    else if (!strcmp(i, "wp_presentation")) pres = wl_registry_bind(r, n, &wp_presentation_interface, 1);
}
static void regrm(void *d, struct wl_registry *r, uint32_t n) {}
static const struct wl_registry_listener rl = { reg, regrm };
static void ping(void *d, struct xdg_wm_base *b, uint32_t s) { xdg_wm_base_pong(b, s); }
static const struct xdg_wm_base_listener wml = { ping };
static void sconf(void *d, struct xdg_surface *s, uint32_t serial) { xdg_surface_ack_configure(s, serial); configured = 1; }
static const struct xdg_surface_listener sl = { sconf };
static void tconf(void *d, struct xdg_toplevel *t, int32_t w, int32_t h, struct wl_array *st) { if (w && h) { W = w; H = h; } }
static void tclose(void *d, struct xdg_toplevel *t) { exit(0); }
static void tbounds(void *d, struct xdg_toplevel *t, int32_t w, int32_t h) {}
static void tcaps(void *d, struct xdg_toplevel *t, struct wl_array *c) {}
static const struct xdg_toplevel_listener tl = { tconf, tclose, tbounds, tcaps };
static void p_clock(void *d, struct wp_presentation *p, uint32_t c) { pres_clk = c; }
static const struct wp_presentation_listener pl = { p_clock };
static void fb_sync(void *d, struct wp_presentation_feedback *f, struct wl_output *o) {}
static void fb_presented(void *d, struct wp_presentation_feedback *f, uint32_t hi, uint32_t lo, uint32_t ns, uint32_t refresh, uint32_t shi, uint32_t slo, uint32_t flags) {
    uint64_t t = ((((uint64_t)hi) << 32) | lo) * 1000000000ull + ns;
    struct timespec a, b; clock_gettime(pres_clk, &a); clock_gettime(CLOCK_MONOTONIC_RAW, &b);
    int64_t off = (int64_t)(b.tv_sec * 1000000000ll + b.tv_nsec) - (int64_t)(a.tv_sec * 1000000000ll + a.tv_nsec);
    printf("presented %lld %u %x\n", (long long)(t + off), refresh, flags); wp_presentation_feedback_destroy(f);
}
static void fb_discarded(void *d, struct wp_presentation_feedback *f) { printf("discarded\n"); wp_presentation_feedback_destroy(f); }
static const struct wp_presentation_feedback_listener fl = { fb_sync, fb_presented, fb_discarded };
static struct wl_buffer *mk(uint32_t color) {
    int stride = W * 4, size = stride * H, fd = memfd_create("flip", 0); ftruncate(fd, size);
    uint32_t *p = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    for (int i = 0; i < W * H; i++) p[i] = color;
    struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, size);
    struct wl_buffer *b = wl_shm_pool_create_buffer(pool, 0, W, H, stride, WL_SHM_FORMAT_XRGB8888);
    wl_shm_pool_destroy(pool); close(fd); return b;
}
int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0);
    struct wl_display *dpy = wl_display_connect(NULL);
    struct wl_registry *r = wl_display_get_registry(dpy); wl_registry_add_listener(r, &rl, NULL); wl_display_roundtrip(dpy);
    xdg_wm_base_add_listener(wm, &wml, NULL);
    if (pres) { wp_presentation_add_listener(pres, &pl, NULL); wl_display_roundtrip(dpy); }
    struct wl_surface *s = wl_compositor_create_surface(comp);
    struct xdg_surface *xs = xdg_wm_base_get_xdg_surface(wm, s); xdg_surface_add_listener(xs, &sl, NULL);
    struct xdg_toplevel *t = xdg_surface_get_toplevel(xs); xdg_toplevel_add_listener(t, &tl, NULL);
    xdg_toplevel_set_title(t, "flipwin"); xdg_toplevel_set_app_id(t, "flipwin"); if (!getenv("FLIP_WINDOWED")) xdg_toplevel_set_fullscreen(t, NULL);
    wl_surface_commit(s);
    while (!configured) wl_display_dispatch(dpy);
    if (!W) { W = 1512; H = 982; }
    buf[0] = mk(0xff000000); buf[1] = mk(0xffffffff);
    wl_surface_attach(s, buf[0], 0, 0); wl_surface_damage(s, 0, 0, W, H); wl_surface_commit(s); wl_display_flush(dpy);
    printf("ready %d %d\n", W, H);
    char line[64]; struct pollfd pf[2] = { { 0, POLLIN }, { wl_display_get_fd(dpy), POLLIN } };
    for (;;) {
        wl_display_flush(dpy);
        poll(pf, 2, -1);
        if (pf[1].revents) wl_display_dispatch(dpy);
        if (pf[0].revents) {
            if (!fgets(line, sizeof line, stdin)) break;
            cur ^= 1; wl_surface_attach(s, buf[cur], 0, 0); wl_surface_damage(s, 0, 0, W, H);
            if (pres) wp_presentation_feedback_add_listener(wp_presentation_feedback(pres, s), &fl, NULL);
            wl_surface_commit(s);
            uint64_t t0 = now(); wl_display_flush(dpy); printf("%llu %d\n", (unsigned long long)t0, cur);
        }
    }
}
