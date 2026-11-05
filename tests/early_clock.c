#define _GNU_SOURCE
#include <stdlib.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

__attribute__((constructor)) static void early_clock(void) {
    struct timespec t, delay = {0};
    struct timeval tv;
    if (clock_gettime(CLOCK_MONOTONIC, &t) || gettimeofday(&tv, NULL) ||
        time(NULL) == (time_t)-1 || nanosleep(&delay, NULL) ||
        clock_nanosleep(CLOCK_MONOTONIC, 0, &delay, NULL) || usleep(0))
        abort();
}
