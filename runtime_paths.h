#ifndef UMA_RUNTIME_PATHS_H
#define UMA_RUNTIME_PATHS_H

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int uma_private(int fd) {
    struct stat st;
    if (fstat(fd, &st) < 0) return -1;
    if (st.st_uid != geteuid() || (st.st_mode & 0077)) {
        errno = EPERM;
        return -1;
    }
    return 0;
}

static int uma_ancestor(int fd) {
    struct stat st;
    if (fstat(fd, &st) < 0) return -1;
    if ((st.st_uid != 0 && st.st_uid != geteuid()) ||
        ((st.st_mode & 0022) && !(st.st_mode & S_ISVTX))) {
        errno = EPERM;
        return -1;
    }
    return 0;
}

/* Walk from an open directory so links and renamed ancestors cannot redirect I/O. */
static int uma_directory(const char *path) {
    char copy[PATH_MAX];
    if (strlen(path) >= sizeof(copy)) { errno = ENAMETOOLONG; return -1; }
    strcpy(copy, path);
    int fd = open(path[0] == '/' ? "/" : ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (fd < 0) return -1;
    if (uma_ancestor(fd) < 0) { int error = errno; close(fd); errno = error; return -1; }
    char *save = NULL;
    for (char *part = strtok_r(copy, "/", &save); part; part = strtok_r(NULL, "/", &save)) {
        if (!strcmp(part, ".")) continue;
        if (!strcmp(part, "..")) { close(fd); errno = EINVAL; return -1; }
        int next = openat(fd, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        int error = errno;
        close(fd);
        if (next < 0) { errno = error; return -1; }
        fd = next;
        if (uma_ancestor(fd) < 0) { error = errno; close(fd); errno = error; return -1; }
    }
    return fd;
}

static int uma_runtime_path(const char *kind, char *out, size_t size) {
    const char *override = getenv(!strcmp(kind, "ctrl") ? "UMA_HOOK_CTRL" : "UMA_HOOK_LOG");
    if (override && *override) {
        if (strlen(override) >= size) { errno = ENAMETOOLONG; return -1; }
        strcpy(out, override);
        return 0;
    }
    const char *base = getenv("XDG_RUNTIME_DIR");
    int has_xdg = base && *base;
    if (!has_xdg) base = "/tmp";
    int base_fd = uma_directory(base);
    if (base_fd < 0) return -1;
    char name[64];
    if (has_xdg) strcpy(name, "uma-hook");
    else snprintf(name, sizeof(name), "uma-hook-%lu", (unsigned long)geteuid());
    int fd = -1;
    if (has_xdg && uma_private(base_fd) < 0) goto fail;
    if (mkdirat(base_fd, name, 0700) < 0 && errno != EEXIST) goto fail;
    fd = openat(base_fd, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0 || uma_private(fd) < 0) goto fail;
    close(fd);
    close(base_fd);
    int length = snprintf(out, size, "%s/%s/%s", base, name,
                          !strcmp(kind, "ctrl") ? "control" : "hook.log");
    if (length < 0 || (size_t)length >= size) { errno = ENAMETOOLONG; return -1; }
    return 0;
fail:
    {
        int error = errno;
        if (fd >= 0) close(fd);
        close(base_fd);
        errno = error;
        return -1;
    }
}

static int uma_parent(const char *path, char *name, size_t size) {
    char copy[PATH_MAX];
    if (strlen(path) >= sizeof(copy)) { errno = ENAMETOOLONG; return -1; }
    strcpy(copy, path);
    char *slash = strrchr(copy, '/');
    const char *leaf = slash ? slash + 1 : copy;
    if (!*leaf || !strcmp(leaf, ".") || !strcmp(leaf, "..") || strlen(leaf) >= size) {
        errno = EINVAL;
        return -1;
    }
    strcpy(name, leaf);
    const char *parent = ".";
    if (slash) {
        if (slash == copy) parent = "/";
        else { *slash = 0; parent = copy; }
    }
    int fd = uma_directory(parent);
    if (fd >= 0 && uma_private(fd) < 0) {
        int error = errno;
        close(fd);
        errno = error;
        return -1;
    }
    return fd;
}

static int uma_open_runtime(int parent_fd, const char *name, int flags) {
    int fd = openat(parent_fd, name, flags | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC, 0600);
    if (fd < 0) return -1;
    struct stat st;
    if (fstat(fd, &st) < 0) goto fail;
    if (!S_ISREG(st.st_mode) || st.st_nlink != 1) { errno = EPERM; goto fail; }
    if (uma_private(fd) < 0) goto fail;
    return fd;
fail:
    {
        int error = errno;
        close(fd);
        errno = error;
        return -1;
    }
}

#endif
