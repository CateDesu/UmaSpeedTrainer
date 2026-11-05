#define _GNU_SOURCE
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "line %d: %s, errno %d\n", __LINE__, #condition, errno); \
    exit(1); \
} } while (0)

static void alarm_handler(int sig) { (void)sig; }

static double real_now(void) {
    struct timespec t;
    CHECK(syscall(SYS_clock_gettime, CLOCK_MONOTONIC, &t) == 0);
    return t.tv_sec + t.tv_nsec / 1e9;
}

static void control(const char *value) {
    FILE *f = fopen(getenv("UMA_HOOK_CTRL"), "w");
    CHECK(f != NULL);
    CHECK(fputs(value, f) >= 0);
    CHECK(fclose(f) == 0);
    struct timespec delay = {0, 150000000}, t;
    CHECK(syscall(SYS_nanosleep, &delay, NULL) == 0);
    CHECK(clock_gettime(CLOCK_MONOTONIC_RAW, &t) == 0);
}

static void interrupt_after(double seconds) {
    struct itimerval timer = {0};
    timer.it_value.tv_sec = (time_t)seconds;
    timer.it_value.tv_usec = (long)((seconds - timer.it_value.tv_sec) * 1e6);
    CHECK(setitimer(ITIMER_REAL, &timer, NULL) == 0);
}

int main(void) {
    umask(0077);
    struct sigaction action = {.sa_handler = alarm_handler};
    CHECK(sigemptyset(&action.sa_mask) == 0);
    CHECK(sigaction(SIGALRM, &action, NULL) == 0);
    alarm(15);

    CHECK(unlink(getenv("UMA_HOOK_CTRL")) == 0);
    struct timespec t;
    errno = 0;
    CHECK(clock_gettime(-123, &t) == -1 && errno == EINVAL);
    errno = EDOM;
    CHECK(clock_gettime(CLOCK_MONOTONIC_RAW, &t) == 0 && errno == EDOM);
    control("3");

    struct timespec invalid[] = {{0, 1000000000}, {1, -1}, {-1, 0}};
    for (unsigned i = 0; i < sizeof(invalid) / sizeof(*invalid); i++) {
        errno = 0;
        CHECK(nanosleep(&invalid[i], NULL) == -1 && errno == EINVAL);
        errno = EDOM;
        CHECK(clock_nanosleep(CLOCK_MONOTONIC, 0, &invalid[i], NULL) == EINVAL);
        CHECK(errno == EDOM);
    }
    errno = 0;
    CHECK(nanosleep(NULL, NULL) == -1 && errno == EFAULT);
    CHECK(clock_nanosleep(CLOCK_MONOTONIC, 0, NULL, NULL) == EFAULT);

    for (int kind = 0; kind < 2; kind++) {
        struct timespec remaining = {1, 0};
        interrupt_after(.05);
        double before = real_now();
        errno = EDOM;
        int r = kind ? clock_nanosleep(CLOCK_MONOTONIC, 0, &remaining, &remaining)
                     : nanosleep(&remaining, &remaining);
        CHECK(kind ? r == EINTR && errno == EDOM : r == -1 && errno == EINTR);
        double elapsed = real_now() - before;
        double left = remaining.tv_sec + remaining.tv_nsec / 1e9;
        CHECK(left > 0 && fabs(elapsed * 3 + left - 1) < .08);
        r = kind ? clock_nanosleep(CLOCK_MONOTONIC, 0, &remaining, NULL)
                 : nanosleep(&remaining, NULL);
        CHECK(r == 0);
        elapsed = real_now() - before;
        CHECK(elapsed >= .31 && elapsed < .65);
    }

    CHECK(clock_gettime(CLOCK_MONOTONIC, &t) == 0);
    t.tv_nsec += 80000000;
    if (t.tv_nsec >= 1000000000) { t.tv_sec++; t.tv_nsec -= 1000000000; }
    double before = real_now();
    CHECK(clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &t, NULL) == 0);
    CHECK(real_now() - before >= .07);

    control("0.5");
    before = real_now();
    CHECK(usleep(40000) == 0);
    CHECK(real_now() - before >= .07);
    control("1e-300");
    interrupt_after(.05);
    errno = 0;
    struct timespec duration = {1, 0};
    int r = nanosleep(&duration, NULL);
    CHECK(r == -1 && errno == EOVERFLOW);
    CHECK(clock_nanosleep(CLOCK_MONOTONIC, 0, &duration, NULL) == EOVERFLOW);
    errno = 0;
    CHECK(usleep(1000) == -1 && errno == EOVERFLOW);
    interrupt_after(0);

    control("3");
    duration = (struct timespec){LONG_MAX, 999999999};
    interrupt_after(.05);
    errno = 0;
    r = nanosleep(&duration, NULL);
    CHECK(r == -1 && errno == EINTR);
    puts("Sleep validation, interruption, overflow and errno checks passed");
    return 0;
}
