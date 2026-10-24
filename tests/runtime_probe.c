#define _GNU_SOURCE
#include "runtime_paths.h"

int main(int argc, char **argv) {
    if (argc < 3) return 2;
    if (!strcmp(argv[1], "path")) {
        char path[PATH_MAX];
        if (uma_runtime_path(argv[2], path, sizeof(path)) < 0) return 1;
        puts(path);
        return 0;
    }
    char name[NAME_MAX + 1];
    int parent = uma_parent(argv[2], name, sizeof(name));
    if (parent < 0) return 1;
    if (!strcmp(argv[1], "parent-race")) {
        char path[PATH_MAX];
        snprintf(path, sizeof(path), "%s", argv[2]);
        char *slash = strrchr(path, '/');
        if (!slash || argc != 5) return 2;
        *slash = 0;
        if (rename(path, argv[3]) || symlink(argv[4], path)) return 2;
    }
    int reading = !strcmp(argv[1], "read");
    int fd = uma_open_runtime(parent, name, reading ? O_RDONLY : O_WRONLY | O_CREAT);
    close(parent);
    if (fd < 0) return 1;
    if (reading) {
        char buffer[64];
        ssize_t length = read(fd, buffer, sizeof(buffer));
        if (length < 0 || write(STDOUT_FILENO, buffer, length) != length) return 2;
    } else {
        if (ftruncate(fd, 0) || write(fd, "3", 1) != 1) return 2;
    }
    close(fd);
    return 0;
}
