/* collect_user.c - 用户信息采集实现 */
#include "collect_user.h"
#include "collector.h"
#include <windows.h>
#include <wtsapi32.h>
#include <stdio.h>
#include <string.h>

/* collect_logged_in_user: 采集当前Windows登录用户名
 * 使用 GetUserNameW() 获取当前交互式登录用户名。
 * 在 SYSTEM 账户下运行时，通过 WTSGetActiveConsoleSessionId() +
 * WTSQuerySessionInformationW(WTSUserName) 获取实际登录用户。
 * 若两者均无法获取，记录空字符串。
 */
void collect_logged_in_user(char *buf, size_t bufsize) {
    if (!buf || bufsize == 0) return;
    buf[0] = '\0';

    /* 方法1: GetUserNameW - 在用户进程上下文中有效 */
    wchar_t wbuf[256];
    DWORD wsize = sizeof(wbuf) / sizeof(wchar_t);
    if (GetUserNameW(wbuf, &wsize)) {
        wide_to_utf8(wbuf, buf, bufsize);
        if (buf[0] != '\0') return;
    }

    /* 方法2: WTS查询 - 在SYSTEM账户下获取实际登录用户 */
    DWORD sessionId = WTSGetActiveConsoleSessionId();
    if (sessionId != 0xFFFFFFFF) {
        wchar_t *pUserName = NULL;
        DWORD userNameLen = 0;
        if (WTSQuerySessionInformationW(WTS_CURRENT_SERVER_HANDLE, sessionId,
                                         WTSUserName, &pUserName, &userNameLen)) {
            if (pUserName && userNameLen > 0) {
                wide_to_utf8(pUserName, buf, bufsize);
            }
            if (pUserName)
                WTSFreeMemory(pUserName);
            if (buf[0] != '\0') return;
        }
    }

    /* 两种方法均失败，保留空字符串 */
}