# Makefile for check_env.exe (GUI版本)
# 支持MinGW-w64和MSVC编译

# MinGW (默认)
CC = gcc
CFLAGS = -Wall -O2 -DUNICODE -D_UNICODE
LDFLAGS = -static
RES_CMD = windres resource.rc -o resource.o
RES_FILE = resource.o
LINK_CMD = $(CC) check_env.c $(RES_FILE) -o check_env.exe $(CFLAGS) $(LDFLAGS) -mwindows -ladvapi32 -lversion -lshell32 -lcomctl32 -luser32 -lgdi32

# MSVC (make CC=cl)
ifeq ($(CC),cl)
CFLAGS = /O2 /DUNICODE /D_UNICODE
LDFLAGS = /MT
RES_CMD = rc resource.rc
RES_FILE = resource.res
LINK_CMD = cl check_env.c $(RES_FILE) $(CFLAGS) $(LDFLAGS) /Fe:check_env.exe advapi32.lib version.lib shell32.lib comctl32.lib user32.lib gdi32.lib
endif

TARGET = check_env.exe

.PHONY: all clean

all: $(TARGET)

$(TARGET): check_env.c resource.rc app.manifest
	$(RES_CMD)
	$(LINK_CMD)

clean:
ifeq ($(CC),cl)
	-del /f $(TARGET) $(RES_FILE) 2>nul
else
	rm -f $(TARGET) $(RES_FILE)
endif