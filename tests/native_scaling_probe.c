#include "../libuma_hook.c"

static int record_sleep(const struct timespec *req, struct timespec *rem) {
    (void)rem;
    printf("%ld %ld\n", (long)req->tv_sec, req->tv_nsec);
    return 0;
}

static int record_clock_sleep(clockid_t clock, int flags,
                              const struct timespec *req, struct timespec *rem) {
    (void)clock;
    (void)flags;
    return record_sleep(req, rem);
}

static int record_usleep(useconds_t delay) {
    struct timespec req = {delay / 1000000, (delay % 1000000) * 1000};
    return record_sleep(&req, NULL);
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    real_nanosleep = record_sleep;
    real_clock_nanosleep = record_clock_sleep;
    real_usleep = record_usleep;
    struct timespec req = {0, 1000000};
    struct timespec zero = {0, 0};
    if (!strcmp(argv[1], "nanosleep")) return nanosleep(&req, NULL);
    if (!strcmp(argv[1], "usleep")) return usleep(1000);
    if (!strcmp(argv[1], "clock-relative"))
        return clock_nanosleep(CLOCK_MONOTONIC_RAW, 0, &req, NULL);
    if (!strcmp(argv[1], "large-delay")) {
        req.tv_sec = LONG_MAX;
        return nanosleep(&req, NULL);
    }
    if (!strcmp(argv[1], "clock-absolute")) {
        publish_anchor(CLOCK_MONOTONIC_RAW, &zero, &zero);
        req.tv_sec = LONG_MAX;
        return clock_nanosleep(CLOCK_MONOTONIC_RAW, TIMER_ABSTIME, &req, NULL);
    }
    if (!strcmp(argv[1], "clock-scale")) {
        publish_anchor(CLOCK_MONOTONIC_RAW, &zero, &zero);
        req.tv_sec = LONG_MAX;
        scale_ts(CLOCK_MONOTONIC_RAW, &req);
    } else if (!strcmp(argv[1], "add-upper")) {
        req.tv_sec = LONG_MAX;
        req.tv_nsec = 999999998;
        ts_add_ns(&req, 2);
    } else if (!strcmp(argv[1], "add-lower")) {
        req.tv_sec = LONG_MIN;
        req.tv_nsec = 1;
        ts_add_ns(&req, -2);
    } else if (!strcmp(argv[1], "read")) {
        double speed;
        printf("read=%d\n", read_ctrl(&speed));
        return 0;
    } else {
        return 2;
    }
    return record_sleep(&req, NULL);
}
