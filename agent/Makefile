# Makefile for Asset Agent (MinGW-w64)
# 编译: make
# 清理: make clean

CC      = gcc
CFLAGS  = -Wall -O2 -DUNICODE -D_UNICODE -D_WIN32_WINNT=0x0501 -DAGENT_VERSION=\"1.0.0\"
LDFLAGS = -mwindows
LIBS    = -lwininet -liphlpapi -lwtsapi32 -ladvapi32 -lole32 -lcrypt32 -lshell32

SOURCES = main.c config.c collector.c collect_user.c fingerprint.c reporter.c service.c cJSON.c
HEADERS = config.h collector.h collect_user.h fingerprint.h reporter.h service.h cJSON.h
OBJECTS = $(SOURCES:.c=.o)
TARGET  = asset-agent.exe

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CC) $(LDFLAGS) -o $@ $^ $(LIBS)

# cJSON is a third-party library — suppress its internal warnings
cJSON.o: cJSON.c cJSON.h
	$(CC) $(CFLAGS) -Wno-unused-variable -Wno-unused-but-set-variable -Wno-unused-function -c -o $@ $<

%.o: %.c $(HEADERS)
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	del /Q $(OBJECTS) $(TARGET) 2>nul || true