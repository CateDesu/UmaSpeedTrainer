/*
 * uma_hook_win.c
 *
 * Windows port of the Uma Musume speedhack. Same idea as the Linux version:
 * intercept the time functions the game uses, scale the result, and let the
 * user toggle the multiplier at runtime through a small control file.
 *
 * What this hooks:
 *   QueryPerformanceCounter   (kernel32)   <- Unity Time.deltaTime and friends
 *   GetTickCount              (kernel32)
 *   GetTickCount64            (kernel32)
 *   timeGetTime               (winmm)
 *
 * How it gets into the game:
 *   Use any DLL injector. I tested injection on Linux+Wine but cannot test
 *   on real Windows from this environment. Bundled inject.py is a minimal
 *   ctypes injector that does the standard
 *   OpenProcess + VirtualAllocEx + WriteProcessMemory + CreateRemoteThread
 *   dance against kernel32.LoadLibraryA.
 *
 * Control file:
 *   %TEMP%\uma-hook.ctrl
 *   Write a single positive float and the hook picks it up within 100 ms.
 *
 * Build (cross compile on Linux with mingw-w64):
 *   x86_64-w64-mingw32-gcc -O2 -shared -o uma_hook.dll uma_hook_win.c \
 *     -Wl,--out-implib,uma_hook.lib -lpsapi
 *
 * Disclaimer: this code has not been validated on real Windows. Treat it
 * as a starting point, not a finished product.
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define POLL_MS 100

/* Real function pointers, resolved before any patching happens. */
static BOOL      (WINAPI *real_QPC)(LARGE_INTEGER*);
static ULONGLONG (WINAPI *real_GetTickCount64)(void);
static DWORD     (WINAPI *real_GetTickCount)(void);
static DWORD     (WINAPI *real_timeGetTime)(void);

/* Shared state. The critical section is held only for short reads and
 * the rare speed change, so contention should not freeze the game. */
static CRITICAL_SECTION state_lock;
static double current_speed = 1.0;

typedef struct {
    int       initialized;
    LONGLONG  real_t0;
    LONGLONG  fake_t0;
} anchor_t;
static anchor_t a_qpc, a_tick64, a_tick, a_timegt;

static char ctrl_path[MAX_PATH];

/* === Math helpers === */

static LONGLONG scale_value(anchor_t *a, LONGLONG real_val, double speed) {
    if (speed == 1.0 && !a->initialized) return real_val;
    if (!a->initialized) {
        a->real_t0 = real_val;
        a->fake_t0 = real_val;
        a->initialized = 1;
        return real_val;
    }
    LONGLONG elapsed = real_val - a->real_t0;
    LONGLONG scaled  = (LONGLONG)((double)elapsed * speed);
    return a->fake_t0 + scaled;
}

static void reanchor(anchor_t *a, LONGLONG real_now, double old_speed) {
    if (!a->initialized) return;
    LONGLONG elapsed = real_now - a->real_t0;
    LONGLONG scaled  = (LONGLONG)((double)elapsed * old_speed);
    a->fake_t0 = a->fake_t0 + scaled;
    a->real_t0 = real_now;
}

/* === Hook functions === */

static BOOL WINAPI my_QPC(LARGE_INTEGER *out) {
    BOOL ok = real_QPC(out);
    if (!ok) return ok;
    EnterCriticalSection(&state_lock);
    out->QuadPart = scale_value(&a_qpc, out->QuadPart, current_speed);
    LeaveCriticalSection(&state_lock);
    return ok;
}

static ULONGLONG WINAPI my_GetTickCount64(void) {
    ULONGLONG v = real_GetTickCount64();
    EnterCriticalSection(&state_lock);
    LONGLONG s = scale_value(&a_tick64, (LONGLONG)v, current_speed);
    LeaveCriticalSection(&state_lock);
    return (ULONGLONG)s;
}

static DWORD WINAPI my_GetTickCount(void) {
    DWORD v = real_GetTickCount();
    EnterCriticalSection(&state_lock);
    LONGLONG s = scale_value(&a_tick, (LONGLONG)v, current_speed);
    LeaveCriticalSection(&state_lock);
    return (DWORD)s;
}

static DWORD WINAPI my_timeGetTime(void) {
    DWORD v = real_timeGetTime();
    EnterCriticalSection(&state_lock);
    LONGLONG s = scale_value(&a_timegt, (LONGLONG)v, current_speed);
    LeaveCriticalSection(&state_lock);
    return (DWORD)s;
}

/* === Import Address Table patching ===
 *
 * Instead of trying to overwrite the real function bytes (which is fragile
 * across Windows updates), we walk the PE import tables of every loaded
 * module and swap the IAT entries that point at the real functions for
 * pointers to our hooks. Each module that calls QPC through its imports
 * will now call our version instead. */

static void patch_iat_one(HMODULE mod, const char *dll_name,
                          const char *func_name, void *new_func) {
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER*)mod;
    if (!dos || dos->e_magic != IMAGE_DOS_SIGNATURE) return;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS*)((BYTE*)mod + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return;

    DWORD imp_rva = nt->OptionalHeader
        .DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    if (!imp_rva) return;
    IMAGE_IMPORT_DESCRIPTOR *imp =
        (IMAGE_IMPORT_DESCRIPTOR*)((BYTE*)mod + imp_rva);

    for (; imp->Name; imp++) {
        const char *name = (const char*)((BYTE*)mod + imp->Name);
        if (_stricmp(name, dll_name) != 0) continue;

        IMAGE_THUNK_DATA *int_t = imp->OriginalFirstThunk
            ? (IMAGE_THUNK_DATA*)((BYTE*)mod + imp->OriginalFirstThunk)
            : (IMAGE_THUNK_DATA*)((BYTE*)mod + imp->FirstThunk);
        IMAGE_THUNK_DATA *iat_t =
            (IMAGE_THUNK_DATA*)((BYTE*)mod + imp->FirstThunk);

        for (; int_t->u1.AddressOfData; int_t++, iat_t++) {
            if (int_t->u1.Ordinal & IMAGE_ORDINAL_FLAG) continue;
            IMAGE_IMPORT_BY_NAME *by =
                (IMAGE_IMPORT_BY_NAME*)((BYTE*)mod + int_t->u1.AddressOfData);
            if (strcmp((char*)by->Name, func_name) != 0) continue;

            DWORD old_prot;
            VirtualProtect(&iat_t->u1.Function, sizeof(void*),
                           PAGE_READWRITE, &old_prot);
            iat_t->u1.Function = (ULONGLONG)(uintptr_t)new_func;
            VirtualProtect(&iat_t->u1.Function, sizeof(void*),
                           old_prot, &old_prot);
            return;
        }
    }
}

static void patch_all_modules(void) {
    HMODULE mods[1024];
    DWORD needed = 0;
    HANDLE proc = GetCurrentProcess();
    if (!EnumProcessModules(proc, mods, sizeof(mods), &needed)) return;
    DWORD n = needed / sizeof(HMODULE);
    for (DWORD i = 0; i < n; i++) {
        char path[MAX_PATH] = {0};
        GetModuleFileNameA(mods[i], path, MAX_PATH);
        /* Skip our own DLL and the core Windows libraries. */
        if (strstr(path, "uma_hook")) continue;
        if (strstr(path, "\\Windows\\System32\\") ||
            strstr(path, "\\Windows\\SysWOW64\\")) continue;
        patch_iat_one(mods[i], "KERNEL32.dll", "QueryPerformanceCounter", my_QPC);
        patch_iat_one(mods[i], "KERNEL32.dll", "GetTickCount64",          my_GetTickCount64);
        patch_iat_one(mods[i], "KERNEL32.dll", "GetTickCount",            my_GetTickCount);
        patch_iat_one(mods[i], "WINMM.dll",    "timeGetTime",             my_timeGetTime);
    }
}

/* === Control file poll thread === */

static int read_ctrl_file(double *out) {
    FILE *f = fopen(ctrl_path, "r");
    if (!f) return 0;
    char buf[64] = {0};
    if (!fgets(buf, sizeof(buf), f)) { fclose(f); return 0; }
    fclose(f);
    double v = atof(buf);
    if (v <= 0.0 || v > 1000.0) return 0;
    *out = v;
    return 1;
}

static void update_speed_and_reanchor(double new_speed) {
    EnterCriticalSection(&state_lock);
    if (new_speed != current_speed) {
        LARGE_INTEGER qpc_now;
        real_QPC(&qpc_now);
        ULONGLONG tick64_now = real_GetTickCount64();
        DWORD     tick_now   = real_GetTickCount();
        DWORD     timegt_now = real_timeGetTime();
        double    old        = current_speed;
        reanchor(&a_qpc,    qpc_now.QuadPart,      old);
        reanchor(&a_tick64, (LONGLONG)tick64_now,  old);
        reanchor(&a_tick,   (LONGLONG)tick_now,    old);
        reanchor(&a_timegt, (LONGLONG)timegt_now,  old);
        current_speed = new_speed;
    }
    LeaveCriticalSection(&state_lock);
}

static DWORD WINAPI poll_thread(LPVOID arg) {
    (void)arg;
    for (;;) {
        Sleep(POLL_MS);
        double v;
        if (read_ctrl_file(&v)) update_speed_and_reanchor(v);
    }
}

/* === DllMain === */

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(inst);
        InitializeCriticalSection(&state_lock);

        HMODULE k32   = GetModuleHandleA("kernel32.dll");
        HMODULE winmm = LoadLibraryA("winmm.dll");
        if (!k32 || !winmm) return FALSE;
        real_QPC            = (BOOL     (WINAPI*)(LARGE_INTEGER*)) GetProcAddress(k32,   "QueryPerformanceCounter");
        real_GetTickCount64 = (ULONGLONG(WINAPI*)(void))           GetProcAddress(k32,   "GetTickCount64");
        real_GetTickCount   = (DWORD    (WINAPI*)(void))           GetProcAddress(k32,   "GetTickCount");
        real_timeGetTime    = (DWORD    (WINAPI*)(void))           GetProcAddress(winmm, "timeGetTime");
        if (!real_QPC || !real_GetTickCount64 || !real_GetTickCount || !real_timeGetTime)
            return FALSE;

        DWORD n = GetTempPathA(MAX_PATH, ctrl_path);
        if (n == 0 || n + 16 > MAX_PATH) {
            strncpy(ctrl_path, "C:\\Temp\\", MAX_PATH - 1);
        }
        strncat(ctrl_path, "uma-hook.ctrl",
                MAX_PATH - strlen(ctrl_path) - 1);

        patch_all_modules();

        CreateThread(NULL, 0, poll_thread, NULL, 0, NULL);
    }
    return TRUE;
}
