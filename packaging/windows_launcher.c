/* Native GUI entry point for CometForge. No shell, console, or system Python. */
#ifndef UNICODE
#define UNICODE 1
#endif
#ifndef _UNICODE
#define _UNICODE 1
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#include <windows.h>
#include <shellapi.h>
#include <shobjidl.h>
#include <wchar.h>

#define PATH_CAPACITY 32768
#define APP_ID L"com.cometforge.desktop"

static int fail(const wchar_t *message, DWORD error) {
    wchar_t details[1024];
    _snwprintf(details, 1023, L"%ls\n\nWindows error: %lu", message, error);
    details[1023] = L'\0';
    MessageBoxW(NULL, details, L"CometForge", MB_OK | MB_ICONERROR);
    return 1;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous,
                   PWSTR arguments, int show) {
    (void)instance; (void)previous; (void)show;
    SetCurrentProcessExplicitAppUserModelID(APP_ID);
    wchar_t *directory = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                                  PATH_CAPACITY * sizeof(wchar_t));
    wchar_t *python = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                               PATH_CAPACITY * sizeof(wchar_t));
    wchar_t *script = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                               PATH_CAPACITY * sizeof(wchar_t));
    wchar_t *command = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                                PATH_CAPACITY * sizeof(wchar_t));
    if (!directory || !python || !script || !command)
        return fail(L"CometForge could not allocate its launcher buffers.", ERROR_NOT_ENOUGH_MEMORY);

    DWORD length = GetModuleFileNameW(NULL, directory, PATH_CAPACITY);
    if (!length || length >= PATH_CAPACITY)
        return fail(L"CometForge could not locate its installation folder.", GetLastError());
    wchar_t *separator = wcsrchr(directory, L'\\');
    if (!separator) return fail(L"CometForge's installation path is invalid.", ERROR_BAD_PATHNAME);
    *separator = L'\0';

    if (wcslen(directory) + 32 >= PATH_CAPACITY)
        return fail(L"CometForge's installation path is too long.", ERROR_FILENAME_EXCED_RANGE);
    _snwprintf(python, PATH_CAPACITY, L"%ls\\runtime\\pythonw.exe", directory);
    _snwprintf(script, PATH_CAPACITY, L"%ls\\launcher.py", directory);
    if (GetFileAttributesW(python) == INVALID_FILE_ATTRIBUTES ||
        GetFileAttributesW(script) == INVALID_FILE_ATTRIBUTES)
        return fail(L"CometForge's bundled runtime is missing. Reinstall CometForge.", ERROR_FILE_NOT_FOUND);

    const wchar_t *extra = arguments ? arguments : L"";
    size_t required = wcslen(python) + wcslen(script) + wcslen(extra) + 24;
    if (required >= PATH_CAPACITY)
        return fail(L"CometForge's launch command is too long.", ERROR_FILENAME_EXCED_RANGE);
    /* Windows filenames cannot contain quotation marks. The fixed executable
       and script paths are quoted; user arguments are forwarded as supplied by
       Windows, without going through cmd.exe or any other shell. */
    _snwprintf(command, PATH_CAPACITY, L"\"%ls\" \"%ls\" --desktop %ls", python, script, extra);

    STARTUPINFOW startup;
    PROCESS_INFORMATION process;
    ZeroMemory(&startup, sizeof(startup));
    ZeroMemory(&process, sizeof(process));
    startup.cb = sizeof(startup);
    /* pythonw is already a GUI executable. CREATE_NO_WINDOW prevents console
       attachment without SW_HIDE, which could hide the first real app window. */
    if (!CreateProcessW(python, command, NULL, NULL, FALSE, CREATE_NO_WINDOW,
                        NULL, directory, &startup, &process))
        return fail(L"CometForge could not start. Try reinstalling the application.", GetLastError());

    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD exit_code = 0;
    GetExitCodeProcess(process.hProcess, &exit_code);
    CloseHandle(process.hProcess);
    HeapFree(GetProcessHeap(), 0, command);
    HeapFree(GetProcessHeap(), 0, script);
    HeapFree(GetProcessHeap(), 0, python);
    HeapFree(GetProcessHeap(), 0, directory);
    return (int)exit_code;
}
