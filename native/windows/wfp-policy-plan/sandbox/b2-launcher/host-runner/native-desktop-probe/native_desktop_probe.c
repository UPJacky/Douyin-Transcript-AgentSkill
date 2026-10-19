#define WIN32_LEAN_AND_MEAN
#include <windows.h>

typedef HWINSTA (WINAPI *GetProcessWindowStationFn)(void);
typedef HDESK (WINAPI *GetThreadDesktopFn)(DWORD);
typedef BOOL (WINAPI *GetUserObjectInformationWFn)(HANDLE, int, PVOID, DWORD, LPDWORD);
typedef int (WINAPI *GetSysColorFn)(int);

typedef struct ProbeData {
    DWORD pid;
    DWORD session_id;
    DWORD user32_loaded;
    DWORD user32_load_error;
    DWORD trigger_resolve_error;
    DWORD trigger_resolved;
    DWORD trigger_called;
    int color_value;
    DWORD station_api_resolved;
    DWORD desktop_api_resolved;
    DWORD object_name_api_resolved;
    DWORD station_query_error;
    DWORD station_name_query_error;
    DWORD desktop_query_error;
    DWORD desktop_name_query_error;
    DWORD station_name_length;
    DWORD desktop_name_length;
    wchar_t station_name[128];
    wchar_t desktop_name[128];
} ProbeData;

static BOOL AppendAscii(char *buffer, DWORD capacity, DWORD *length, const char *text)
{
    while (*text != '\0') {
        if (*length + 1 >= capacity) return FALSE;
        buffer[(*length)++] = *text++;
    }
    buffer[*length] = '\0';
    return TRUE;
}

static BOOL AppendUnsigned(char *buffer, DWORD capacity, DWORD *length, DWORD value)
{
    char digits[16];
    DWORD count = 0;
    do {
        digits[count++] = (char)('0' + (value % 10));
        value /= 10;
    } while (value != 0 && count < ARRAYSIZE(digits));
    while (count > 0) {
        if (*length + 1 >= capacity) return FALSE;
        buffer[(*length)++] = digits[--count];
    }
    buffer[*length] = '\0';
    return TRUE;
}

static BOOL AppendSigned(char *buffer, DWORD capacity, DWORD *length, int value)
{
    if (value < 0) {
        if (!AppendAscii(buffer, capacity, length, "-")) return FALSE;
        return AppendUnsigned(buffer, capacity, length, (DWORD)(-(value + 1)) + 1);
    }
    return AppendUnsigned(buffer, capacity, length, (DWORD)value);
}

static BOOL AppendWideJsonString(char *buffer, DWORD capacity, DWORD *length, const wchar_t *value)
{
    if (!AppendAscii(buffer, capacity, length, "\"")) return FALSE;
    if (value != NULL) {
        while (*value != L'\0') {
            wchar_t ch = *value++;
            if (ch == L'"' || ch == L'\\') {
                if (*length + 2 >= capacity) return FALSE;
                buffer[(*length)++] = '\\';
                buffer[(*length)++] = (char)ch;
            } else if (ch >= 0x20 && ch <= 0x7e) {
                if (*length + 1 >= capacity) return FALSE;
                buffer[(*length)++] = (char)ch;
            } else {
                static const char hex[] = "0123456789ABCDEF";
                if (*length + 6 >= capacity) return FALSE;
                buffer[(*length)++] = '\\';
                buffer[(*length)++] = 'u';
                buffer[(*length)++] = hex[((unsigned short)ch >> 12) & 0xf];
                buffer[(*length)++] = hex[((unsigned short)ch >> 8) & 0xf];
                buffer[(*length)++] = hex[((unsigned short)ch >> 4) & 0xf];
                buffer[(*length)++] = hex[(unsigned short)ch & 0xf];
            }
        }
    }
    if (*length + 1 >= capacity) return FALSE;
    buffer[(*length)++] = '"';
    buffer[*length] = '\0';
    return TRUE;
}

static BOOL AppendBoolean(char *buffer, DWORD capacity, DWORD *length, BOOL value)
{
    return AppendAscii(buffer, capacity, length, value ? "true" : "false");
}

static BOOL WriteJsonFile(const wchar_t *name, const char *json, DWORD length)
{
    wchar_t temporary[MAX_PATH];
    DWORD nameLength = 0;
    while (name[nameLength] != L'\0') {
        if (nameLength + 5 >= ARRAYSIZE(temporary)) return FALSE;
        temporary[nameLength] = name[nameLength];
        ++nameLength;
    }
    const wchar_t suffix[] = L".tmp";
    for (DWORD index = 0; index < ARRAYSIZE(suffix); ++index) {
        if (nameLength + index >= ARRAYSIZE(temporary)) return FALSE;
        temporary[nameLength + index] = suffix[index];
    }
    HANDLE file = CreateFileW(temporary, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    DWORD written = 0;
    BOOL success = WriteFile(file, json, length, &written, NULL) && written == length;
    if (success) success = FlushFileBuffers(file);
    CloseHandle(file);
    if (success) success = MoveFileExW(temporary, name, MOVEFILE_WRITE_THROUGH);
    if (!success) DeleteFileW(temporary);
    return success;
}

static BOOL WritePreMarker(const wchar_t *name, const char *kind)
{
    char json[256];
    DWORD length = 0;
    DWORD session = 0;
    DWORD pid = GetCurrentProcessId();
    BOOL sessionKnown = ProcessIdToSessionId(pid, &session);
    BOOL ok = AppendAscii(json, ARRAYSIZE(json), &length, "{\"schema\":\"native-desktop-diagnostic/v1\",\"kind\":")
        && AppendAscii(json, ARRAYSIZE(json), &length, kind)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"stage\":\"pre_user32\",\"pid\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, pid)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"session_id_known\":")
        && AppendBoolean(json, ARRAYSIZE(json), &length, sessionKnown)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"session_id\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, session)
        && AppendAscii(json, ARRAYSIZE(json), &length, "}");
    return ok && WriteJsonFile(name, json, length);
}

static BOOL QueryObjectName(GetUserObjectInformationWFn query, HANDLE object,
    wchar_t *name, DWORD capacityChars, DWORD *error, DWORD *lengthBytes)
{
    DWORD needed = 0;
    if (!query(object, UOI_NAME, name, capacityChars * sizeof(wchar_t), &needed)) {
        *error = GetLastError();
        return FALSE;
    }
    *error = 0;
    *lengthBytes = needed;
    name[capacityChars - 1] = L'\0';
    return TRUE;
}

static void ProbeUser32(ProbeData *data)
{
    HMODULE user32 = LoadLibraryW(L"user32.dll");
    if (user32 == NULL) {
        data->user32_load_error = GetLastError();
        return;
    }
    data->user32_loaded = TRUE;

    FARPROC triggerProc = GetProcAddress(user32, "GetSysColor");
    GetSysColorFn trigger = (GetSysColorFn)triggerProc;
    data->trigger_resolved = trigger != NULL;
    if (trigger != NULL) {
        data->color_value = trigger(COLOR_WINDOW);
        data->trigger_called = TRUE;
    } else {
        data->trigger_resolve_error = GetLastError();
    }

    GetProcessWindowStationFn getStation =
        (GetProcessWindowStationFn)GetProcAddress(user32, "GetProcessWindowStation");
    GetThreadDesktopFn getDesktop =
        (GetThreadDesktopFn)GetProcAddress(user32, "GetThreadDesktop");
    GetUserObjectInformationWFn getObjectInfo =
        (GetUserObjectInformationWFn)GetProcAddress(user32, "GetUserObjectInformationW");
    data->station_api_resolved = getStation != NULL;
    data->desktop_api_resolved = getDesktop != NULL;
    data->object_name_api_resolved = getObjectInfo != NULL;

    if (getStation != NULL) {
        HWINSTA station = getStation();
        if (station == NULL) data->station_query_error = GetLastError();
        else if (getObjectInfo == NULL) data->station_name_query_error = ERROR_PROC_NOT_FOUND;
        else (void)QueryObjectName(getObjectInfo, station, data->station_name,
            ARRAYSIZE(data->station_name), &data->station_name_query_error, &data->station_name_length);
    } else {
        data->station_query_error = ERROR_PROC_NOT_FOUND;
    }

    if (getDesktop != NULL) {
        HDESK desktop = getDesktop(GetCurrentThreadId());
        if (desktop == NULL) data->desktop_query_error = GetLastError();
        else if (getObjectInfo == NULL) data->desktop_name_query_error = ERROR_PROC_NOT_FOUND;
        else (void)QueryObjectName(getObjectInfo, desktop, data->desktop_name,
            ARRAYSIZE(data->desktop_name), &data->desktop_name_query_error, &data->desktop_name_length);
    } else {
        data->desktop_query_error = ERROR_PROC_NOT_FOUND;
    }
}

static BOOL WritePostMarker(const wchar_t *name, const char *kind, const ProbeData *data)
{
    char json[2048];
    DWORD length = 0;
    BOOL ok = AppendAscii(json, ARRAYSIZE(json), &length,
            "{\"schema\":\"native-desktop-diagnostic/v1\",\"kind\":")
        && AppendAscii(json, ARRAYSIZE(json), &length, kind)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"stage\":\"post_user32\",\"pid\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, data->pid)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"session_id\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, data->session_id)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"user32_loaded\":")
        && AppendBoolean(json, ARRAYSIZE(json), &length, data->user32_loaded != 0)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"user32_load_error\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, data->user32_load_error)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"get_sys_color_resolve_error\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, data->trigger_resolve_error)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"get_sys_color_resolved\":")
        && AppendBoolean(json, ARRAYSIZE(json), &length, data->trigger_resolved != 0)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"get_sys_color_called\":")
        && AppendBoolean(json, ARRAYSIZE(json), &length, data->trigger_called != 0)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"get_sys_color_value\":")
        && AppendSigned(json, ARRAYSIZE(json), &length, data->color_value)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"get_process_window_station_resolved\":")
        && AppendBoolean(json, ARRAYSIZE(json), &length, data->station_api_resolved != 0)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"get_thread_desktop_resolved\":")
        && AppendBoolean(json, ARRAYSIZE(json), &length, data->desktop_api_resolved != 0)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"get_user_object_information_resolved\":")
        && AppendBoolean(json, ARRAYSIZE(json), &length, data->object_name_api_resolved != 0)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"station_query_error\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, data->station_query_error)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"station_name_query_error\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, data->station_name_query_error)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"window_station\":")
        && AppendWideJsonString(json, ARRAYSIZE(json), &length,
            data->station_name_query_error == 0 ? data->station_name : NULL)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"desktop_query_error\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, data->desktop_query_error)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"desktop_name_query_error\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, data->desktop_name_query_error)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"desktop\":")
        && AppendWideJsonString(json, ARRAYSIZE(json), &length,
            data->desktop_name_query_error == 0 ? data->desktop_name : NULL)
        && AppendAscii(json, ARRAYSIZE(json), &length, "}");
    return ok && WriteJsonFile(name, json, length);
}

static DWORD RunProbe(BOOL child)
{
    const wchar_t *preName = child ? L"native-child-pre.json" : L"native-root-pre.json";
    const wchar_t *postName = child ? L"native-child-post.json" : L"native-root-post.json";
    ProbeData data;
    DWORD session = 0;
    data.pid = GetCurrentProcessId();
    data.session_id = ProcessIdToSessionId(data.pid, &session) ? session : 0;
    data.user32_loaded = 0;
    data.user32_load_error = 0;
    data.trigger_resolve_error = 0;
    data.trigger_resolved = 0;
    data.trigger_called = 0;
    data.color_value = 0;
    data.station_api_resolved = 0;
    data.desktop_api_resolved = 0;
    data.object_name_api_resolved = 0;
    data.station_query_error = 0;
    data.station_name_query_error = 0;
    data.desktop_query_error = 0;
    data.desktop_name_query_error = 0;
    data.station_name_length = 0;
    data.desktop_name_length = 0;
    data.station_name[0] = L'\0';
    data.desktop_name[0] = L'\0';
    if (!WritePreMarker(preName, child ? "\"child\"" : "\"root\"")) return 11;

    ProbeUser32(&data);
    if (!WritePostMarker(postName, child ? "\"child\"" : "\"root\"", &data)) return 12;
    if (child) Sleep(4000);

    return data.user32_load_error == 0 && data.trigger_called
        && data.station_query_error == 0 && data.station_name_query_error == 0
        && data.desktop_query_error == 0 && data.desktop_name_query_error == 0 ? 0 : 20;
}

static BOOL BuildChildCommandLine(wchar_t *command, DWORD capacity)
{
    wchar_t module[MAX_PATH];
    DWORD length = GetModuleFileNameW(NULL, module, ARRAYSIZE(module));
    if (length == 0 || length >= ARRAYSIZE(module)) return FALSE;
    DWORD out = 0;
    if (out + 1 >= capacity) return FALSE;
    command[out++] = L'"';
    for (DWORD index = 0; index < length; ++index) {
        if (out + 1 >= capacity) return FALSE;
        command[out++] = module[index];
    }
    const wchar_t suffix[] = L"\" --child";
    for (DWORD index = 0; index < ARRAYSIZE(suffix); ++index) {
        if (out + 1 >= capacity) return FALSE;
        command[out++] = suffix[index];
    }
    return TRUE;
}

static BOOL WriteRootSummary(DWORD childPid, DWORD createError, DWORD waitError, DWORD childExitCode)
{
    char json[512];
    DWORD length = 0;
    BOOL childCreated = childPid != 0;
    BOOL childExited = childCreated && waitError == 0;
    BOOL ok = AppendAscii(json, ARRAYSIZE(json), &length,
            "{\"schema\":\"native-desktop-diagnostic/v1\",\"kind\":\"root_summary\",\"pid\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, GetCurrentProcessId())
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"child_created\":")
        && AppendBoolean(json, ARRAYSIZE(json), &length, childCreated)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"child_process_id\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, childPid)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"child_create_error\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, createError)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"child_wait_error\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, waitError)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"child_exit_observed\":")
        && AppendBoolean(json, ARRAYSIZE(json), &length, childExited)
        && AppendAscii(json, ARRAYSIZE(json), &length, ",\"child_exit_code\":")
        && AppendUnsigned(json, ARRAYSIZE(json), &length, childExitCode)
        && AppendAscii(json, ARRAYSIZE(json), &length, "}");
    return ok && WriteJsonFile(L"native-root-summary.json", json, length);
}

static DWORD RunRoot(void)
{
    DWORD ownProbeResult = RunProbe(FALSE);
    wchar_t commandLine[MAX_PATH + 32];
    if (!BuildChildCommandLine(commandLine, ARRAYSIZE(commandLine))) {
        (void)WriteRootSummary(0, GetLastError(), ERROR_INVALID_PARAMETER, 0);
        return 30;
    }

    STARTUPINFOW startup;
    startup.cb = sizeof(startup);
    startup.lpReserved = NULL;
    startup.lpDesktop = NULL;
    startup.lpTitle = NULL;
    startup.dwX = 0;
    startup.dwY = 0;
    startup.dwXSize = 0;
    startup.dwYSize = 0;
    startup.dwXCountChars = 0;
    startup.dwYCountChars = 0;
    startup.dwFillAttribute = 0;
    startup.dwFlags = STARTF_USESHOWWINDOW;
    startup.wShowWindow = SW_HIDE;
    startup.cbReserved2 = 0;
    startup.lpReserved2 = NULL;
    startup.hStdInput = NULL;
    startup.hStdOutput = NULL;
    startup.hStdError = NULL;

    PROCESS_INFORMATION process;
    process.hProcess = NULL;
    process.hThread = NULL;
    process.dwProcessId = 0;
    process.dwThreadId = 0;
    BOOL created = CreateProcessW(NULL, commandLine, NULL, NULL, FALSE,
        CREATE_NO_WINDOW, NULL, NULL, &startup, &process);
    if (!created) {
        DWORD error = GetLastError();
        (void)WriteRootSummary(0, error, ERROR_INVALID_PARAMETER, 0);
        return 31;
    }

    DWORD waitError = 0;
    DWORD childExitCode = 0;
    DWORD waitResult = WaitForSingleObject(process.hProcess, 7000);
    if (waitResult != WAIT_OBJECT_0) waitError = waitResult == WAIT_FAILED ? GetLastError() : ERROR_TIMEOUT;
    else if (!GetExitCodeProcess(process.hProcess, &childExitCode)) waitError = GetLastError();
    DWORD childPid = process.dwProcessId;
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    BOOL summaryWritten = WriteRootSummary(childPid, 0, waitError, childExitCode);
    if (!summaryWritten || waitError != 0 || childExitCode != 0) return 32;
    return ownProbeResult == 0 ? 0 : 33;
}

static BOOL IsChildCommandLine(void)
{
    const wchar_t *command = GetCommandLineW();
    if (command == NULL) return FALSE;
    if (*command == L'"') {
        ++command;
        while (*command != L'\0' && *command != L'"') ++command;
        if (*command == L'"') ++command;
    } else {
        while (*command != L'\0' && *command != L' ' && *command != L'\t') ++command;
    }
    while (*command == L' ' || *command == L'\t') ++command;
    const wchar_t expected[] = L"--child";
    for (DWORD index = 0; expected[index] != L'\0'; ++index) {
        if (command[index] != expected[index]) return FALSE;
    }
    return command[ARRAYSIZE(expected) - 1] == L'\0'
        || command[ARRAYSIZE(expected) - 1] == L' ';
}

void WINAPI EntryPoint(void)
{
    DWORD exitCode = IsChildCommandLine() ? RunProbe(TRUE) : RunRoot();
    ExitProcess(exitCode);
}
