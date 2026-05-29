/*
 * uma_speed_trainer.c
 *
 * Windows GUI EXE. Has the speedhack DLL embedded as a resource. When the
 * user clicks "Inject into game" it:
 *   1. writes the embedded DLL to %TEMP%\uma_hook_<our_pid>.dll
 *   2. finds the running UmamusumePrettyDerby.exe
 *   3. injects via OpenProcess + VirtualAllocEx + WriteProcessMemory +
 *      CreateRemoteThread on kernel32!LoadLibraryA
 *
 * The DLL itself polls %TEMP%\uma-hook.ctrl. The ON / OFF buttons in this
 * window just write a number to that file. So you can toggle speed
 * mid-game without touching anything else.
 *
 * Build with mingw (cross compile on Linux, or MSYS2 on Windows):
 *   make
 *
 * Untested on real Windows. The Linux LD_PRELOAD version works at 5x;
 * this one mirrors the same logic.
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <psapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ID_INJECT_BTN 100
#define ID_ON_BTN     101
#define ID_OFF_BTN    102
#define ID_SPEED_EDIT 103
#define ID_STATUS_LBL 104
#define ID_TIMER      1
#define DLL_RES_ID    1
#define TARGET_EXE    "UmamusumePrettyDerby.exe"

static char  dll_temp_path[MAX_PATH];
static char  ctrl_path[MAX_PATH];
static HWND  hStatus;
static HWND  hSpeed;
static DWORD injected_pid = 0;

/* Extract the embedded DLL resource to %TEMP%\uma_hook_<our_pid>.dll.
 * Using our pid in the name avoids collisions when an old DLL is still
 * loaded into the game from a previous run. */
static int extract_dll(void) {
    HRSRC res = FindResourceA(NULL, MAKEINTRESOURCEA(DLL_RES_ID), RT_RCDATA);
    if (!res) return 0;
    HGLOBAL hres = LoadResource(NULL, res);
    if (!hres) return 0;
    DWORD size = SizeofResource(NULL, res);
    void *data = LockResource(hres);
    if (!data || !size) return 0;

    char tmp[MAX_PATH];
    DWORD n = GetTempPathA(MAX_PATH, tmp);
    if (n == 0 || n + 32 > MAX_PATH) return 0;
    snprintf(dll_temp_path, sizeof dll_temp_path,
             "%suma_hook_%lu.dll", tmp,
             (unsigned long)GetCurrentProcessId());

    HANDLE f = CreateFileA(dll_temp_path, GENERIC_WRITE, 0, NULL,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE) return 0;
    DWORD wrote = 0;
    BOOL ok = WriteFile(f, data, size, &wrote, NULL);
    CloseHandle(f);
    return ok && wrote == size;
}

static DWORD find_process(const char *name) {
    DWORD pids[4096];
    DWORD needed = 0;
    if (!EnumProcesses(pids, sizeof pids, &needed)) return 0;
    DWORD count = needed / sizeof(DWORD);
    for (DWORD i = 0; i < count; i++) {
        if (!pids[i]) continue;
        HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION
                             | PROCESS_VM_READ, FALSE, pids[i]);
        if (!h) continue;
        char path[MAX_PATH] = {0};
        if (GetModuleFileNameExA(h, NULL, path, MAX_PATH)) {
            const char *base = strrchr(path, '\\');
            base = base ? base + 1 : path;
            if (_stricmp(base, name) == 0) {
                CloseHandle(h);
                return pids[i];
            }
        }
        CloseHandle(h);
    }
    return 0;
}

static int inject_dll(DWORD pid, const char *path) {
    HANDLE h = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION
                         | PROCESS_VM_OPERATION | PROCESS_VM_WRITE
                         | PROCESS_VM_READ, FALSE, pid);
    if (!h) return 0;
    size_t len = strlen(path) + 1;
    LPVOID addr = VirtualAllocEx(h, NULL, len,
                                 MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!addr) { CloseHandle(h); return 0; }
    if (!WriteProcessMemory(h, addr, path, len, NULL)) {
        VirtualFreeEx(h, addr, 0, MEM_RELEASE);
        CloseHandle(h);
        return 0;
    }
    FARPROC ll = GetProcAddress(GetModuleHandleA("kernel32.dll"),
                                "LoadLibraryA");
    if (!ll) { CloseHandle(h); return 0; }
    HANDLE t = CreateRemoteThread(h, NULL, 0,
                                  (LPTHREAD_START_ROUTINE)ll, addr, 0, NULL);
    if (!t) {
        VirtualFreeEx(h, addr, 0, MEM_RELEASE);
        CloseHandle(h);
        return 0;
    }
    WaitForSingleObject(t, 5000);
    CloseHandle(t);
    CloseHandle(h);
    return 1;
}

static void write_speed(double speed) {
    FILE *f = fopen(ctrl_path, "w");
    if (!f) return;
    fprintf(f, "%g", speed);
    fclose(f);
}

static double read_speed_or_neg(void) {
    FILE *f = fopen(ctrl_path, "r");
    if (!f) return -1.0;
    char buf[64] = {0};
    if (!fgets(buf, sizeof buf, f)) { fclose(f); return -1.0; }
    fclose(f);
    return atof(buf);
}

static void update_status(void) {
    char buf[256];
    if (injected_pid == 0) {
        strcpy(buf, "Not injected. Start the game and click Inject.");
    } else {
        double s = read_speed_or_neg();
        if (s < 0 || s == 1.0) {
            snprintf(buf, sizeof buf,
                     "Injected (pid %lu). Speed: OFF (1.0x)",
                     (unsigned long)injected_pid);
        } else {
            snprintf(buf, sizeof buf,
                     "Injected (pid %lu). Speed: %gx",
                     (unsigned long)injected_pid, s);
        }
    }
    SetWindowTextA(hStatus, buf);
}

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_CREATE: {
            HFONT font = (HFONT)GetStockObject(DEFAULT_GUI_FONT);

            HWND b = CreateWindowA("BUTTON", "Inject into game",
                WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
                12, 12, 320, 36, hwnd,
                (HMENU)(intptr_t)ID_INJECT_BTN, NULL, NULL);
            SendMessageA(b, WM_SETFONT, (WPARAM)font, TRUE);

            hStatus = CreateWindowA("STATIC", "Not injected.",
                WS_VISIBLE | WS_CHILD,
                12, 56, 320, 40, hwnd,
                (HMENU)(intptr_t)ID_STATUS_LBL, NULL, NULL);
            SendMessageA(hStatus, WM_SETFONT, (WPARAM)font, TRUE);

            HWND lbl = CreateWindowA("STATIC", "Speed:",
                WS_VISIBLE | WS_CHILD,
                12, 110, 50, 24, hwnd, NULL, NULL, NULL);
            SendMessageA(lbl, WM_SETFONT, (WPARAM)font, TRUE);

            hSpeed = CreateWindowA("EDIT", "3.0",
                WS_VISIBLE | WS_CHILD | WS_BORDER | ES_AUTOHSCROLL,
                64, 107, 60, 26, hwnd,
                (HMENU)(intptr_t)ID_SPEED_EDIT, NULL, NULL);
            SendMessageA(hSpeed, WM_SETFONT, (WPARAM)font, TRUE);

            HWND on = CreateWindowA("BUTTON", "ON",
                WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
                140, 102, 90, 36, hwnd,
                (HMENU)(intptr_t)ID_ON_BTN, NULL, NULL);
            SendMessageA(on, WM_SETFONT, (WPARAM)font, TRUE);

            HWND off = CreateWindowA("BUTTON", "OFF",
                WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
                242, 102, 90, 36, hwnd,
                (HMENU)(intptr_t)ID_OFF_BTN, NULL, NULL);
            SendMessageA(off, WM_SETFONT, (WPARAM)font, TRUE);

            SetTimer(hwnd, ID_TIMER, 500, NULL);
            return 0;
        }
        case WM_TIMER:
            update_status();
            return 0;
        case WM_COMMAND: {
            int id = LOWORD(wp);
            if (id == ID_INJECT_BTN) {
                DWORD pid = find_process(TARGET_EXE);
                if (!pid) {
                    MessageBoxA(hwnd,
                        "Could not find " TARGET_EXE ".\r\n"
                        "Start the game first, then try again.",
                        "Uma Speed Trainer", MB_OK | MB_ICONWARNING);
                    return 0;
                }
                if (inject_dll(pid, dll_temp_path)) {
                    injected_pid = pid;
                } else {
                    MessageBoxA(hwnd, "Injection failed.",
                        "Uma Speed Trainer", MB_OK | MB_ICONERROR);
                }
                update_status();
            } else if (id == ID_ON_BTN) {
                char buf[64];
                GetWindowTextA(hSpeed, buf, sizeof buf);
                double v = atof(buf);
                if (v <= 0) v = 3.0;
                write_speed(v);
                update_status();
            } else if (id == ID_OFF_BTN) {
                write_speed(1.0);
                update_status();
            }
            return 0;
        }
        case WM_DESTROY:
            KillTimer(hwnd, ID_TIMER);
            PostQuitMessage(0);
            return 0;
    }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

int WINAPI WinMain(HINSTANCE inst, HINSTANCE prev, LPSTR cmd, int show) {
    (void)prev; (void)cmd;

    char tmp[MAX_PATH];
    DWORD n = GetTempPathA(MAX_PATH, tmp);
    if (n == 0 || n + 16 > MAX_PATH) {
        strcpy(tmp, "C:\\Temp\\");
    }
    snprintf(ctrl_path, sizeof ctrl_path, "%suma-hook.ctrl", tmp);
    write_speed(1.0);

    if (!extract_dll()) {
        MessageBoxA(NULL, "Could not extract embedded DLL.",
                    "Uma Speed Trainer", MB_OK | MB_ICONERROR);
        return 1;
    }

    INITCOMMONCONTROLSEX icex = { sizeof icex, ICC_STANDARD_CLASSES };
    InitCommonControlsEx(&icex);

    WNDCLASSA wc = {0};
    wc.lpfnWndProc   = WndProc;
    wc.hInstance     = inst;
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = "UmaSpeedTrainerWnd";
    RegisterClassA(&wc);

    HWND hwnd = CreateWindowA(wc.lpszClassName, "Uma Speed Trainer",
        WS_OVERLAPPEDWINDOW & ~(WS_THICKFRAME | WS_MAXIMIZEBOX),
        CW_USEDEFAULT, CW_USEDEFAULT, 360, 200,
        NULL, NULL, inst, NULL);
    if (!hwnd) return 1;
    ShowWindow(hwnd, show);

    MSG m;
    while (GetMessage(&m, NULL, 0, 0)) {
        TranslateMessage(&m);
        DispatchMessage(&m);
    }
    return 0;
}
