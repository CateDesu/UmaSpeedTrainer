#define _GNU_SOURCE
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include <math.h>
#include <sys/stat.h>

static atomic_int done;
static atomic_ulong backwards;
static atomic_long worst;
static atomic_ulong samples;

static int64_t now(int direct) {
    struct timespec t;
    int r = direct ? syscall(SYS_clock_gettime, CLOCK_MONOTONIC_RAW, &t)
                   : clock_gettime(CLOCK_MONOTONIC_RAW, &t);
    if (r) exit(2);
    return (int64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}

static void wait_real(long ns) {
    struct timespec delay = {.tv_nsec = ns};
    if (syscall(SYS_nanosleep, &delay, NULL)) exit(2);
}

static void *reader(void *unused) {
    (void)unused;
    int64_t previous = 0;
    while (!atomic_load(&done)) {
        int64_t current = now(0);
        if (current < previous) {
            atomic_fetch_add(&backwards, 1);
            long delta = previous - current;
            long old = atomic_load(&worst);
            while (delta > old && !atomic_compare_exchange_weak(&worst, &old, delta)) {}
        }
        previous = current;
        atomic_fetch_add(&samples, 1);
    }
    return NULL;
}

int main(void) {
    umask(0077);
    pthread_t threads[4];
    for (int i = 0; i < 4; i++)
        if (pthread_create(&threads[i], NULL, reader, NULL)) return 2;
    for (int i = 0; i < 24; i++) {
        FILE *control = fopen(getenv("UMA_HOOK_CTRL"), "w");
        if (!control) return 2;
        if (fputs(i % 2 ? "1.0" : "5.0", control) < 0 || fclose(control)) return 2;
        wait_real(150000000);
        int64_t real = now(1), fake = now(0);
        wait_real(60000000);
        double ratio = (double)(now(0) - fake) / (now(1) - real);
        double expected = i % 2 ? 1.0 : 5.0;
        if (fabs(ratio - expected) > .5) {
            fprintf(stderr, "Expected %.0fx, observed %.2fx\n", expected, ratio);
            return 1;
        }
    }
    atomic_store(&done, 1);
    for (int i = 0; i < 4; i++) if (pthread_join(threads[i], NULL)) return 2;
    printf("Backward clock steps: %lu; worst: %ld ns\n", atomic_load(&backwards), atomic_load(&worst));
    return atomic_load(&backwards) || atomic_load(&samples) < 1000 ? 1 : 0;
}
