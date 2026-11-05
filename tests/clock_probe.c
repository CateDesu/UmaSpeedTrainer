#define _GNU_SOURCE
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static double now(clockid_t clock) {
    struct timespec t;
    if (clock_gettime(clock, &t)) exit(1);
    return t.tv_sec + t.tv_nsec / 1e9;
}

static void wait_real(void) {
    struct timespec delay = {.tv_nsec = 180000000};
    if (syscall(SYS_nanosleep, &delay, NULL)) exit(1);
}

static void control(const char *speed) {
    FILE *f = fopen(getenv("UMA_HOOK_CTRL"), "w");
    if (!f) exit(1);
    fputs(speed, f);
    fclose(f);
    wait_real();
    now(CLOCK_MONOTONIC_RAW);
}

static void check_speed(double expected) {
    double raw = now(CLOCK_MONOTONIC_RAW);
    double mono = now(CLOCK_MONOTONIC);
    double wall = now(CLOCK_REALTIME);
    wait_real();
    raw = now(CLOCK_MONOTONIC_RAW) - raw;
    mono = now(CLOCK_MONOTONIC) - mono;
    wall = now(CLOCK_REALTIME) - wall;
    if (!isfinite(raw) || fabs(raw / mono - expected) > expected * .1 ||
        fabs(wall / mono - 1.0) > 0.05) {
        fprintf(stderr, "Expected %gx RAW, got %g; wall ratio %g\n",
                expected, raw / mono, wall / mono);
        exit(1);
    }
}

int main(void) {
    umask(0077);
    control("3.0");
    check_speed(3);
    control("nan");
    check_speed(3);
    control("4junk");
    check_speed(3);
    control("5                                                               junk");
    check_speed(3);
    if (unlink(getenv("UMA_HOOK_CTRL")) || mkfifo(getenv("UMA_HOOK_CTRL"), 0600)) exit(1);
    wait_real();
    check_speed(3);
    unlink(getenv("UMA_HOOK_CTRL"));
    control("0.5");
    check_speed(.5);
    control("1.0");
    check_speed(1);
    puts("RAW clock scales, wall and monotonic clocks stay real, invalid speeds ignored");
    return 0;
}
