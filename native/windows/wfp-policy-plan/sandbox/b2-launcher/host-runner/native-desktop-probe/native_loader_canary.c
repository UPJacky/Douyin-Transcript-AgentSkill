typedef unsigned long DWORD;
typedef int BOOL;
typedef void *HANDLE;
typedef HANDLE HMODULE;
typedef long long LONG_PTR;
typedef unsigned short wchar_t;
typedef wchar_t WCHAR;
typedef const WCHAR *LPCWSTR;
typedef void (__stdcall *FARPROC)(void);

#define WINAPI __stdcall
#define TRUE 1
#define FALSE 0
#define GENERIC_WRITE 0x40000000UL
#define FILE_SHARE_READ 0x00000001UL
#define CREATE_NEW 1UL
#define FILE_ATTRIBUTE_NORMAL 0x00000080UL
#define MOVEFILE_WRITE_THROUGH 0x00000008UL
#define UOI_NAME 2
#define ERROR_PROC_NOT_FOUND 127UL
#define ERROR_NOT_ATTEMPTED 0xffffffffUL
#define INVALID_HANDLE_VALUE ((HANDLE)(LONG_PTR)-1)

__declspec(dllimport) HANDLE WINAPI CreateFileW(LPCWSTR, DWORD, DWORD, void *, DWORD, DWORD, HANDLE);
__declspec(dllimport) BOOL WINAPI WriteFile(HANDLE, const void *, DWORD, DWORD *, void *);
__declspec(dllimport) BOOL WINAPI FlushFileBuffers(HANDLE);
__declspec(dllimport) BOOL WINAPI CloseHandle(HANDLE);
__declspec(dllimport) BOOL WINAPI MoveFileExW(LPCWSTR, LPCWSTR, DWORD);
__declspec(dllimport) BOOL WINAPI DeleteFileW(LPCWSTR);
__declspec(dllimport) DWORD WINAPI GetLastError(void);
__declspec(dllimport) DWORD WINAPI GetCurrentProcessId(void);
__declspec(dllimport) DWORD WINAPI GetCurrentThreadId(void);
__declspec(dllimport) BOOL WINAPI ProcessIdToSessionId(DWORD, DWORD *);
__declspec(dllimport) HMODULE WINAPI LoadLibraryW(LPCWSTR);
__declspec(dllimport) FARPROC WINAPI GetProcAddress(HMODULE, const char *);
__declspec(dllimport) BOOL WINAPI FreeLibrary(HMODULE);
__declspec(dllimport) void WINAPI Sleep(DWORD);
__declspec(dllimport) __declspec(noreturn) void WINAPI ExitProcess(DWORD);

typedef HANDLE (WINAPI *GetProcessWindowStationFn)(void);
typedef HANDLE (WINAPI *GetThreadDesktopFn)(DWORD);
typedef BOOL (WINAPI *GetUserObjectInformationWFn)(HANDLE, int, void *, DWORD, DWORD *);

typedef struct DiagnosticState {
    DWORD pid;
    DWORD sessionId;
    BOOL sessionKnown;
    BOOL user32Loaded;
    DWORD user32LoadError;
    BOOL stationApiResolved;
    BOOL desktopApiResolved;
    BOOL objectInfoApiResolved;
    BOOL stationNameObserved;
    BOOL desktopNameObserved;
    DWORD stationQueryError;
    DWORD stationNameQueryError;
    DWORD desktopQueryError;
    DWORD desktopNameQueryError;
    WCHAR stationName[128];
    WCHAR desktopName[128];
} DiagnosticState;

static BOOL AppendChar(char *buffer, DWORD capacity, DWORD *length, char value)
{
    if (*length + 1 >= capacity) return FALSE;
    buffer[(*length)++] = value;
    buffer[*length] = '\0';
    return TRUE;
}

static BOOL AppendAscii(char *buffer, DWORD capacity, DWORD *length, const char *value)
{
    while (*value != '\0') {
        if (!AppendChar(buffer, capacity, length, *value++)) return FALSE;
    }
    return TRUE;
}

static BOOL AppendUnsigned(char *buffer, DWORD capacity, DWORD *length, DWORD value)
{
    char digits[10];
    DWORD count = 0;
    do {
        digits[count++] = (char)('0' + (value % 10));
        value /= 10;
    } while (value != 0 && count < sizeof(digits));
    while (count > 0) {
        if (!AppendChar(buffer, capacity, length, digits[--count])) return FALSE;
    }
    return TRUE;
}

static BOOL AppendBoolean(char *buffer, DWORD capacity, DWORD *length, BOOL value)
{
    return AppendAscii(buffer, capacity, length, value ? "true" : "false");
}

static BOOL AppendHex4(char *buffer, DWORD capacity, DWORD *length, unsigned short value)
{
    const char hex[] = "0123456789abcdef";
    for (int shift = 12; shift >= 0; shift -= 4) {
        if (!AppendChar(buffer, capacity, length, hex[(value >> shift) & 0x0f])) return FALSE;
    }
    return TRUE;
}

static BOOL AppendWideJsonString(char *buffer, DWORD capacity, DWORD *length, const WCHAR *value)
{
    if (value == 0) return AppendAscii(buffer, capacity, length, "null");
    if (!AppendChar(buffer, capacity, length, '"')) return FALSE;
    while (*value != 0) {
        unsigned short character = (unsigned short)*value++;
        if (character == '"' || character == '\\') {
            if (!AppendChar(buffer, capacity, length, '\\')
                || !AppendChar(buffer, capacity, length, (char)character)) return FALSE;
        } else if (character >= 0x20 && character <= 0x7e) {
            if (!AppendChar(buffer, capacity, length, (char)character)) return FALSE;
        } else {
            if (!AppendAscii(buffer, capacity, length, "\\u")
                || !AppendHex4(buffer, capacity, length, character)) return FALSE;
        }
    }
    return AppendChar(buffer, capacity, length, '"');
}

static BOOL WriteJsonFile(const WCHAR *name, const char *json, DWORD length)
{
    WCHAR temporary[64];
    DWORD nameLength = 0;
    while (name[nameLength] != 0) {
        if (nameLength + 5 >= sizeof(temporary) / sizeof(temporary[0])) return FALSE;
        temporary[nameLength] = name[nameLength];
        ++nameLength;
    }
    temporary[nameLength++] = L'.';
    temporary[nameLength++] = L't';
    temporary[nameLength++] = L'm';
    temporary[nameLength++] = L'p';
    temporary[nameLength] = 0;

    HANDLE file = CreateFileW(temporary, GENERIC_WRITE, FILE_SHARE_READ, 0, CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL, 0);
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    DWORD written = 0;
    BOOL success = WriteFile(file, json, length, &written, 0) && written == length;
    if (success) success = FlushFileBuffers(file);
    if (!CloseHandle(file)) success = FALSE;
    if (success) success = MoveFileExW(temporary, name, MOVEFILE_WRITE_THROUGH);
    if (!success) DeleteFileW(temporary);
    return success;
}

static BOOL WritePreMarker(const DiagnosticState *state)
{
    char json[320];
    json[0] = '\0';
    DWORD length = 0;
    BOOL ok = AppendAscii(json, sizeof(json), &length,
            "{\"schema\":\"native-desktop-diagnostic/v1\",\"kind\":\"root\",\"stage\":\"pre_user32\",\"pid\":")
        && AppendUnsigned(json, sizeof(json), &length, state->pid)
        && AppendAscii(json, sizeof(json), &length, ",\"session_id_known\":")
        && AppendBoolean(json, sizeof(json), &length, state->sessionKnown)
        && AppendAscii(json, sizeof(json), &length, ",\"session_id\":")
        && AppendUnsigned(json, sizeof(json), &length, state->sessionId)
        && AppendChar(json, sizeof(json), &length, '}');
    return ok && WriteJsonFile(L"native-root-pre.json", json, length);
}

static BOOL QueryObjectName(GetUserObjectInformationWFn query, HANDLE object,
    WCHAR *name, DWORD capacityChars, DWORD *error)
{
    DWORD needed = 0;
    if (!query(object, UOI_NAME, name, capacityChars * (DWORD)sizeof(WCHAR), &needed)) {
        *error = GetLastError();
        return FALSE;
    }
    *error = 0;
    name[capacityChars - 1] = 0;
    return TRUE;
}

static void ProbeUser32(DiagnosticState *state)
{
    HMODULE user32 = LoadLibraryW(L"user32.dll");
    if (user32 == 0) {
        state->user32LoadError = GetLastError();
        return;
    }
    state->user32Loaded = TRUE;

    GetProcessWindowStationFn getStation =
        (GetProcessWindowStationFn)GetProcAddress(user32, "GetProcessWindowStation");
    GetThreadDesktopFn getDesktop =
        (GetThreadDesktopFn)GetProcAddress(user32, "GetThreadDesktop");
    GetUserObjectInformationWFn getObjectInfo =
        (GetUserObjectInformationWFn)GetProcAddress(user32, "GetUserObjectInformationW");
    state->stationApiResolved = getStation != 0;
    state->desktopApiResolved = getDesktop != 0;
    state->objectInfoApiResolved = getObjectInfo != 0;

    if (getStation == 0) state->stationQueryError = ERROR_PROC_NOT_FOUND;
    else {
        HANDLE station = getStation();
        if (station == 0) state->stationQueryError = GetLastError();
        else if (getObjectInfo == 0) state->stationNameQueryError = ERROR_PROC_NOT_FOUND;
        else state->stationNameObserved = QueryObjectName(getObjectInfo, station, state->stationName,
            sizeof(state->stationName) / sizeof(state->stationName[0]), &state->stationNameQueryError);
    }

    if (getDesktop == 0) state->desktopQueryError = ERROR_PROC_NOT_FOUND;
    else {
        HANDLE desktop = getDesktop(GetCurrentThreadId());
        if (desktop == 0) state->desktopQueryError = GetLastError();
        else if (getObjectInfo == 0) state->desktopNameQueryError = ERROR_PROC_NOT_FOUND;
        else state->desktopNameObserved = QueryObjectName(getObjectInfo, desktop, state->desktopName,
            sizeof(state->desktopName) / sizeof(state->desktopName[0]), &state->desktopNameQueryError);
    }
    (void)FreeLibrary(user32);
}

static BOOL WritePostMarker(const DiagnosticState *state)
{
    char json[1400];
    json[0] = '\0';
    DWORD length = 0;
    BOOL ok = AppendAscii(json, sizeof(json), &length,
            "{\"schema\":\"native-desktop-diagnostic/v1\",\"kind\":\"root\",\"stage\":\"post_user32\",\"pid\":")
        && AppendUnsigned(json, sizeof(json), &length, state->pid)
        && AppendAscii(json, sizeof(json), &length, ",\"session_id\":")
        && AppendUnsigned(json, sizeof(json), &length, state->sessionId)
        && AppendAscii(json, sizeof(json), &length, ",\"user32_loaded\":")
        && AppendBoolean(json, sizeof(json), &length, state->user32Loaded)
        && AppendAscii(json, sizeof(json), &length, ",\"user32_load_error\":")
        && AppendUnsigned(json, sizeof(json), &length, state->user32LoadError)
        && AppendAscii(json, sizeof(json), &length, ",\"get_process_window_station_resolved\":")
        && AppendBoolean(json, sizeof(json), &length, state->stationApiResolved)
        && AppendAscii(json, sizeof(json), &length, ",\"get_thread_desktop_resolved\":")
        && AppendBoolean(json, sizeof(json), &length, state->desktopApiResolved)
        && AppendAscii(json, sizeof(json), &length, ",\"get_user_object_information_resolved\":")
        && AppendBoolean(json, sizeof(json), &length, state->objectInfoApiResolved)
        && AppendAscii(json, sizeof(json), &length, ",\"station_query_error\":")
        && AppendUnsigned(json, sizeof(json), &length, state->stationQueryError)
        && AppendAscii(json, sizeof(json), &length, ",\"station_name_query_error\":")
        && AppendUnsigned(json, sizeof(json), &length, state->stationNameQueryError)
        && AppendAscii(json, sizeof(json), &length, ",\"station_name_observed\":")
        && AppendBoolean(json, sizeof(json), &length, state->stationNameObserved)
        && AppendAscii(json, sizeof(json), &length, ",\"window_station\":")
        && AppendWideJsonString(json, sizeof(json), &length,
            state->stationNameObserved ? state->stationName : 0)
        && AppendAscii(json, sizeof(json), &length, ",\"desktop_query_error\":")
        && AppendUnsigned(json, sizeof(json), &length, state->desktopQueryError)
        && AppendAscii(json, sizeof(json), &length, ",\"desktop_name_query_error\":")
        && AppendUnsigned(json, sizeof(json), &length, state->desktopNameQueryError)
        && AppendAscii(json, sizeof(json), &length, ",\"desktop_name_observed\":")
        && AppendBoolean(json, sizeof(json), &length, state->desktopNameObserved)
        && AppendAscii(json, sizeof(json), &length, ",\"desktop\":")
        && AppendWideJsonString(json, sizeof(json), &length,
            state->desktopNameObserved ? state->desktopName : 0)
        && AppendChar(json, sizeof(json), &length, '}');
    return ok && WriteJsonFile(L"native-root-post.json", json, length);
}

void WINAPI EntryPoint(void)
{
    DiagnosticState state;
    state.pid = 0;
    state.sessionId = 0;
    state.sessionKnown = FALSE;
    state.user32Loaded = FALSE;
    state.user32LoadError = 0;
    state.stationApiResolved = FALSE;
    state.desktopApiResolved = FALSE;
    state.objectInfoApiResolved = FALSE;
    state.stationNameObserved = FALSE;
    state.desktopNameObserved = FALSE;
    state.stationQueryError = 0;
    state.stationNameQueryError = ERROR_NOT_ATTEMPTED;
    state.desktopQueryError = 0;
    state.desktopNameQueryError = ERROR_NOT_ATTEMPTED;
    state.stationName[0] = 0;
    state.desktopName[0] = 0;
    state.pid = GetCurrentProcessId();
    state.sessionKnown = ProcessIdToSessionId(state.pid, &state.sessionId);
    if (!WritePreMarker(&state)) ExitProcess(11);
    ProbeUser32(&state);
    if (!WritePostMarker(&state)) ExitProcess(12);
    Sleep(1500);
    ExitProcess(0);
}
