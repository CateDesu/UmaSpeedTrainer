/*
 * libuma_hook.c: runtime toggleable speedhack LD_PRELOAD for Uma Musume (Proton).
 *
 * Hooks libc time + sleep symbols. Wine's ntdll.so imports clock_gettime,
 * gettimeofday, time, usleep from glibc with zero inline syscalls (verified
 * via objdump -T on Proton 10/11/Experimental/CachyOS), so QPC and other
 * Windows time APIs inside the Unity game route through here.
 *
 * Speed control: a single float in /tmp/uma-hook.ctrl, re-read every ~100 ms.
 *
 * IMPORTANT, what we scale and why:
 *
 *   Only CLOCK_MONOTONIC_RAW is scaled. That is the clock Wine's modern
 *   ntdll uses for RtlQueryPerformanceCounter, which is what Unity reads for
 *   Time.deltaTime / realtimeSinceStartup.
 *
 *   CLOCK_MONOTONIC is deliberately left alone. Wine's fsync uses it for
 *   FUTEX_WAIT_BITSET absolute deadlines, and the kernel does not see our
 *   scaling. If we scaled MONOTONIC the kernel would sleep until its
 *   unscaled clock reached a fake future deadline, freezing every Wine
 *   cross-thread synchronization.
 *
 *   CLOCK_BOOTTIME / CLOCK_REALTIME also unscaled (GetTickCount64 / wall
 *   clock, so we do not trip server time skew detection, TLS cert checks,
 *   or break file timestamps).
 *
 *   Side effect: Time.realtimeSinceStartup (QPC) speeds up; GetTickCount64
 *   does not. Unity tolerates the divergence because most game logic reads QPC.
 *
 * Hot path is lockless: speed is stored as bit-cast atomic uint64, anchors
 * are seqlock-protected. Writers (speed changes, anchor init) serialize on
 * write_mutex. Readers (every clock_gettime) never block.
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdatomic.h>
#include <time.h>
#include <sys/time.h>
#include <dlfcn.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <fcntl.h>
#include <stdarg.h>
#include <errno.h>

#define LOG_PATH_DEFAULT  "/tmp/uma-hook.log"
#define CTRL_PATH_DEFAULT "/tmp/uma-hook.ctrl"
#define MAX_LOGGED_CALLS  20
#define MAX_CLOCK_ID      16
#define POLL_INTERVAL_NS  100000000L  /* re-read ctrl file at most every 100 ms */

static int log_fd = -1;
static int quiet = 0;
static int hook_active = 0;
static char proc_comm[64];
static char proc_cmdline[1024];
static char ctrl_path[256];

static pthread_mutex_t log_mutex = PTHREAD_MUTEX_INITIALIZER;

/* --- Lock-free state for the hot path --- */

/* Speed as bit-cast double in an atomic uint64. Aligned 64-bit loads/stores
 * are atomic on x86_64; the bit-cast keeps stdatomic happy. */
static atomic_uint_least64_t speed_bits;

/* Per-clock anchor with a seqlock. Even seq == stable; odd seq == being written. */
typedef struct {
    atomic_uint seq;
    int initialized;
    struct timespec real_t0;
    struct timespec fake_t0;
} anchor_t;
static anchor_t anchors[MAX_CLOCK_ID];

/* All writers serialize on this. Readers don't touch it. */
static pthread_mutex_t write_mutex = PTHREAD_MUTEX_INITIALIZER;

static inline double load_speed(void) {
    uint64_t b = atomic_load_explicit(&speed_bits, memory_order_relaxed);
    double d;
    memcpy(&d, &b, sizeof(d));
    return d;
}

static inline void store_speed_relaxed(double v) {
    uint64_t b;
    memcpy(&b, &v, sizeof(b));
    atomic_store_explicit(&speed_bits, b, memory_order_relaxed);
}

/* Stats (advisory; race-tolerant). */
typedef struct { uint64_t count; uint64_t logged; } stat_t;
static stat_t s_clock_gettime[MAX_CLOCK_ID];
static stat_t s_clock_nanosleep[MAX_CLOCK_ID];
static stat_t s_gettimeofday, s_time, s_nanosleep, s_usleep;

static int (*real_clock_gettime)(clockid_t, struct timespec*);
static int (*real_gettimeofday)(struct timeval*, void*);
static time_t (*real_time)(time_t*);
static int (*real_nanosleep)(const struct timespec*, struct timespec*);
static int (*real_clock_nanosleep)(clockid_t, int, const struct timespec*, struct timespec*);
static int (*real_usleep)(useconds_t);

static const char *clock_name(clockid_t c) {
    switch (c) {
        case CLOCK_REALTIME:           return "REALTIME";
        case CLOCK_MONOTONIC:          return "MONOTONIC";
        case CLOCK_PROCESS_CPUTIME_ID: return "PROCESS_CPU";
        case CLOCK_THREAD_CPUTIME_ID:  return "THREAD_CPU";
        case CLOCK_MONOTONIC_RAW:      return "MONOTONIC_RAW";
        case CLOCK_REALTIME_COARSE:    return "REALTIME_COARSE";
        case CLOCK_MONOTONIC_COARSE:   return "MONOTONIC_COARSE";
        case CLOCK_BOOTTIME:           return "BOOTTIME";
        default:                       return "OTHER";
    }
}

static void logf_(const char *fmt, ...) {
    if (log_fd < 0 || quiet) return;
    char buf[512];
    va_list ap; va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    if (n <= 0) return;
    pthread_mutex_lock(&log_mutex);
    (void)!write(log_fd, buf, n);
    pthread_mutex_unlock(&log_mutex);
}

static inline int64_t ts_diff_ns(const struct timespec *a, const struct timespec *b) {
    return (int64_t)(a->tv_sec - b->tv_sec) * 1000000000LL + (a->tv_nsec - b->tv_nsec);
}

static inline void ts_add_ns(struct timespec *ts, int64_t ns) {
    ts->tv_sec += ns / 1000000000LL;
    int64_t rem = ns % 1000000000LL;
    ts->tv_nsec += rem;
    if (ts->tv_nsec >= 1000000000) { ts->tv_sec++; ts->tv_nsec -= 1000000000; }
    else if (ts->tv_nsec < 0)      { ts->tv_sec--; ts->tv_nsec += 1000000000; }
}

/* Scale ONLY CLOCK_MONOTONIC_RAW. Touching CLOCK_MONOTONIC breaks Wine fsync
 * absolute futex deadlines (kernel doesn't see our scaling). */
static inline int is_scalable(clockid_t c) {
    return c == CLOCK_MONOTONIC_RAW;
}

/* Snapshot anchor data lock-free via seqlock. Returns initialized flag. */
static int snapshot_anchor(unsigned ci, struct timespec *real_t0, struct timespec *fake_t0) {
    anchor_t *a = &anchors[ci];
    for (int retry = 0; retry < 32; retry++) {
        unsigned s1 = atomic_load_explicit(&a->seq, memory_order_acquire);
        if (s1 & 1u) continue;
        int init = a->initialized;
        struct timespec rt = a->real_t0;
        struct timespec ft = a->fake_t0;
        atomic_thread_fence(memory_order_acquire);
        unsigned s2 = atomic_load_explicit(&a->seq, memory_order_relaxed);
        if (s1 == s2) {
            *real_t0 = rt;
            *fake_t0 = ft;
            return init;
        }
    }
    return 0;
}

/* Publish a new anchor. Must hold write_mutex. */
static void publish_anchor(unsigned ci, const struct timespec *real_t0,
                           const struct timespec *fake_t0) {
    anchor_t *a = &anchors[ci];
    atomic_fetch_add_explicit(&a->seq, 1u, memory_order_release); /* odd: writing */
    a->real_t0 = *real_t0;
    a->fake_t0 = *fake_t0;
    a->initialized = 1;
    atomic_fetch_add_explicit(&a->seq, 1u, memory_order_release); /* even: stable */
}

static int read_ctrl(double *out) {
    int fd = open(ctrl_path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    char buf[64] = {0};
    int n = read(fd, buf, sizeof(buf) - 1);
    close(fd);
    if (n <= 0) return 0;
    buf[n] = 0;
    while (n > 0 && (buf[n-1] == '\n' || buf[n-1] == ' ' || buf[n-1] == '\r' || buf[n-1] == '\t'))
        buf[--n] = 0;
    double v = atof(buf);
    if (v <= 0.0 || v > 1000.0) return 0;
    *out = v;
    return 1;
}

/* Re-anchor every initialized clock at the current fake-time and swap to the
 * new speed. Holds write_mutex. */
static void apply_speed_change(double new_speed) {
    pthread_mutex_lock(&write_mutex);
    double cur = load_speed();
    if (new_speed == cur) {
        pthread_mutex_unlock(&write_mutex);
        return;
    }
    struct timespec now;
    for (int i = 0; i < MAX_CLOCK_ID; i++) {
        anchor_t *a = &anchors[i];
        if (!a->initialized) continue;
        if (real_clock_gettime((clockid_t)i, &now) != 0) continue;
        int64_t elapsed = ts_diff_ns(&now, &a->real_t0);
        int64_t scaled  = (int64_t)((double)elapsed * cur);
        struct timespec fake_now = a->fake_t0;
        ts_add_ns(&fake_now, scaled);
        publish_anchor((unsigned)i, &now, &fake_now);
    }
    store_speed_relaxed(new_speed);
    logf_("[uma_hook] speed %g -> %g (pid %d)\n", cur, new_speed, getpid());
    pthread_mutex_unlock(&write_mutex);
}

static atomic_long last_poll_ns = 0;
static void maybe_poll_ctrl(void) {
    struct timespec now;
    if (real_clock_gettime(CLOCK_MONOTONIC_COARSE, &now) != 0) return;
    long now_ns = (long)now.tv_sec * 1000000000L + now.tv_nsec;
    long last = atomic_load_explicit(&last_poll_ns, memory_order_relaxed);
    if (now_ns - last < POLL_INTERVAL_NS) return;
    if (!atomic_compare_exchange_strong_explicit(&last_poll_ns, &last, now_ns,
            memory_order_relaxed, memory_order_relaxed)) return;
    double new_speed;
    if (!read_ctrl(&new_speed)) return;
    apply_speed_change(new_speed);
}

/* Hot path. Lock-free unless we have to initialize a brand-new anchor. */
static void scale_ts(clockid_t clk, struct timespec *real) {
    if (!is_scalable(clk)) return;
    unsigned ci = (unsigned)clk;
    if (ci >= MAX_CLOCK_ID) return;

    double speed = load_speed();

    struct timespec real_t0, fake_t0;
    int init = snapshot_anchor(ci, &real_t0, &fake_t0);

    /* Fast path: nothing to scale and no anchor to maintain. */
    if (speed == 1.0 && !init) return;

    if (!init) {
        pthread_mutex_lock(&write_mutex);
        if (!anchors[ci].initialized)
            publish_anchor(ci, real, real);
        pthread_mutex_unlock(&write_mutex);
        return;
    }

    int64_t elapsed = ts_diff_ns(real, &real_t0);
    int64_t scaled  = (int64_t)((double)elapsed * speed);
    *real = fake_t0;
    ts_add_ns(real, scaled);
}

/* === Hooks === */

int clock_gettime(clockid_t clk, struct timespec *ts) {
    int r = real_clock_gettime(clk, ts);
    if (!hook_active) return r;

    maybe_poll_ctrl();

    unsigned ci = (unsigned)clk;
    if (ci < MAX_CLOCK_ID) {
        s_clock_gettime[ci].count++;
        if (s_clock_gettime[ci].logged < MAX_LOGGED_CALLS) {
            s_clock_gettime[ci].logged++;
            logf_("[%d/%s] clock_gettime(%s)\n", getpid(), proc_comm, clock_name(clk));
        }
    }
    if (r == 0) scale_ts(clk, ts);
    return r;
}

int gettimeofday(struct timeval *tv, void *tz) {
    int r = real_gettimeofday(tv, tz);
    if (!hook_active) return r;
    s_gettimeofday.count++;
    if (s_gettimeofday.logged < MAX_LOGGED_CALLS) {
        s_gettimeofday.logged++;
        logf_("[%d/%s] gettimeofday\n", getpid(), proc_comm);
    }
    return r;
}

time_t time(time_t *t) {
    time_t r = real_time(t);
    if (!hook_active) return r;
    s_time.count++;
    if (s_time.logged < MAX_LOGGED_CALLS) {
        s_time.logged++;
        logf_("[%d/%s] time -> %ld\n", getpid(), proc_comm, (long)r);
    }
    return r;
}

int nanosleep(const struct timespec *req, struct timespec *rem) {
    if (!hook_active) return real_nanosleep(req, rem);
    s_nanosleep.count++;
    if (s_nanosleep.logged < MAX_LOGGED_CALLS) {
        s_nanosleep.logged++;
        logf_("[%d/%s] nanosleep(%ld.%09ld)\n", getpid(), proc_comm,
              (long)req->tv_sec, req->tv_nsec);
    }
    double s = load_speed();
    if (s > 0.0 && s != 1.0) {
        struct timespec sc;
        int64_t ns = (int64_t)req->tv_sec * 1000000000LL + req->tv_nsec;
        ns = (int64_t)((double)ns / s);
        sc.tv_sec  = ns / 1000000000LL;
        sc.tv_nsec = ns % 1000000000LL;
        return real_nanosleep(&sc, rem);
    }
    return real_nanosleep(req, rem);
}

int clock_nanosleep(clockid_t clk, int flags, const struct timespec *req, struct timespec *rem) {
    if (!hook_active) return real_clock_nanosleep(clk, flags, req, rem);
    unsigned ci = (unsigned)clk;
    if (ci < MAX_CLOCK_ID) {
        s_clock_nanosleep[ci].count++;
        if (s_clock_nanosleep[ci].logged < MAX_LOGGED_CALLS) {
            s_clock_nanosleep[ci].logged++;
            logf_("[%d/%s] clock_nanosleep(%s, flags=0x%x, %ld.%09ld)\n",
                  getpid(), proc_comm, clock_name(clk), flags,
                  (long)req->tv_sec, req->tv_nsec);
        }
    }
    double s = load_speed();
    if (s > 0.0 && s != 1.0) {
        if ((flags & TIMER_ABSTIME) && is_scalable(clk) && ci < MAX_CLOCK_ID) {
            struct timespec real_t0, fake_t0;
            if (snapshot_anchor(ci, &real_t0, &fake_t0)) {
                int64_t fake_delta = ts_diff_ns(req, &fake_t0);
                int64_t real_delta = (int64_t)((double)fake_delta / s);
                struct timespec target = real_t0;
                ts_add_ns(&target, real_delta);
                return real_clock_nanosleep(clk, flags, &target, rem);
            }
        } else if (!(flags & TIMER_ABSTIME)) {
            struct timespec sc;
            int64_t ns = (int64_t)req->tv_sec * 1000000000LL + req->tv_nsec;
            ns = (int64_t)((double)ns / s);
            sc.tv_sec  = ns / 1000000000LL;
            sc.tv_nsec = ns % 1000000000LL;
            return real_clock_nanosleep(clk, flags, &sc, rem);
        }
    }
    return real_clock_nanosleep(clk, flags, req, rem);
}

int usleep(useconds_t us) {
    if (!hook_active) return real_usleep(us);
    s_usleep.count++;
    if (s_usleep.logged < MAX_LOGGED_CALLS) {
        s_usleep.logged++;
        logf_("[%d/%s] usleep(%u)\n", getpid(), proc_comm, us);
    }
    double s = load_speed();
    if (s > 0.0 && s != 1.0)
        return real_usleep((useconds_t)((double)us / s));
    return real_usleep(us);
}

/* === Init === */

static void read_comm(void) {
    int fd = open("/proc/self/comm", O_RDONLY);
    proc_comm[0] = 0;
    if (fd < 0) return;
    int n = read(fd, proc_comm, sizeof(proc_comm) - 1);
    close(fd);
    if (n > 0) {
        proc_comm[n] = 0;
        char *nl = strchr(proc_comm, '\n');
        if (nl) *nl = 0;
    }
}

static void read_cmdline(void) {
    int fd = open("/proc/self/cmdline", O_RDONLY);
    proc_cmdline[0] = 0;
    if (fd < 0) return;
    int n = read(fd, proc_cmdline, sizeof(proc_cmdline) - 1);
    close(fd);
    if (n <= 0) return;
    for (int i = 0; i < n; i++) if (proc_cmdline[i] == 0) proc_cmdline[i] = ' ';
    proc_cmdline[n] = 0;
}

static int filter_matches(const char *filter) {
    if (!filter || !*filter) return 1;
    char buf[256];
    snprintf(buf, sizeof(buf), "%s", filter);
    char *save = NULL;
    for (char *t = strtok_r(buf, ",", &save); t; t = strtok_r(NULL, ",", &save)) {
        if (strstr(proc_cmdline, t)) return 1;
    }
    return 0;
}

__attribute__((constructor)) static void uma_init(void) {
    real_clock_gettime   = dlsym(RTLD_NEXT, "clock_gettime");
    real_gettimeofday    = dlsym(RTLD_NEXT, "gettimeofday");
    real_time            = dlsym(RTLD_NEXT, "time");
    real_nanosleep       = dlsym(RTLD_NEXT, "nanosleep");
    real_clock_nanosleep = dlsym(RTLD_NEXT, "clock_nanosleep");
    real_usleep          = dlsym(RTLD_NEXT, "usleep");

    const char *log_path = getenv("UMA_HOOK_LOG");
    if (!log_path || !*log_path) log_path = LOG_PATH_DEFAULT;
    log_fd = open(log_path, O_WRONLY | O_CREAT | O_APPEND, 0644);

    const char *cp = getenv("UMA_HOOK_CTRL");
    if (!cp || !*cp) cp = CTRL_PATH_DEFAULT;
    snprintf(ctrl_path, sizeof(ctrl_path), "%s", cp);

    quiet = getenv("UMA_HOOK_QUIET") && atoi(getenv("UMA_HOOK_QUIET"));

    double init_speed = 1.0;
    if (!read_ctrl(&init_speed)) {
        const char *m = getenv("UMA_SPEED");
        if (m) init_speed = atof(m);
        if (init_speed <= 0.0) init_speed = 1.0;
    }
    store_speed_relaxed(init_speed);

    read_comm();
    read_cmdline();

    const char *filt = getenv("UMA_HOOK_FILTER");
    hook_active = filter_matches(filt);

    logf_("\n=== uma_hook LOADED pid=%d comm=%s active=%d speed=%g ctrl=%s filter=%s cmdline=%.180s ===\n",
          getpid(), proc_comm, hook_active, init_speed,
          ctrl_path, filt ? filt : "(none)", proc_cmdline);
}

static void dump_stats(void) {
    for (int i = 0; i < MAX_CLOCK_ID; i++)
        if (s_clock_gettime[i].count)
            logf_("  clock_gettime(%s) = %lu\n", clock_name((clockid_t)i),
                  (unsigned long)s_clock_gettime[i].count);
    if (s_gettimeofday.count) logf_("  gettimeofday = %lu\n", (unsigned long)s_gettimeofday.count);
    if (s_time.count)         logf_("  time = %lu\n",         (unsigned long)s_time.count);
    if (s_nanosleep.count)    logf_("  nanosleep = %lu\n",    (unsigned long)s_nanosleep.count);
    for (int i = 0; i < MAX_CLOCK_ID; i++)
        if (s_clock_nanosleep[i].count)
            logf_("  clock_nanosleep(%s) = %lu\n", clock_name((clockid_t)i),
                  (unsigned long)s_clock_nanosleep[i].count);
    if (s_usleep.count)       logf_("  usleep = %lu\n",       (unsigned long)s_usleep.count);
}

__attribute__((destructor)) static void uma_fini(void) {
    if (log_fd < 0) return;
    logf_("\n=== uma_hook UNLOAD pid=%d comm=%s ===\n", getpid(), proc_comm);
    dump_stats();
    close(log_fd);
}
