#ifndef SWARM_PROTOCOL_H
#define SWARM_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>

// Small, allocation-free parser for the flat command objects in protocol v1.
// Reject malformed/oversized fields instead of truncating them into commands.
namespace SwarmProtocol {
    inline void whitespace(const char*& p) {
        while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') ++p;
    }

    inline bool string(const char*& p, char* out, size_t cap) {
        if (*p++ != '"') return false;
        size_t size = 0;
        while (*p && *p != '"') {
            unsigned char c = (unsigned char)*p++;
            if (c < 32) return false;
            if (c == '\\') {
                c = (unsigned char)*p++;
                switch (c) {
                    case '"': case '\\': case '/': break;
                    case 'b': c = '\b'; break;
                    case 'f': c = '\f'; break;
                    case 'n': c = '\n'; break;
                    case 'r': c = '\r'; break;
                    case 't': c = '\t'; break;
                    // UTF-8 is sent directly by the Python SDK. Escaped Unicode
                    // is rejected rather than decoded incorrectly by firmware.
                    default: return false;
                }
            }
            if (out) {
                if (size + 1 >= cap) return false;
                out[size] = (char)c;
            }
            ++size;
        }
        if (*p != '"') return false;
        ++p;
        if (out) out[size] = '\0';
        return true;
    }

    inline bool number(const char*& p) {
        if (*p == '-') ++p;
        if (*p == '0') ++p;
        else {
            if (*p < '1' || *p > '9') return false;
            while (*p >= '0' && *p <= '9') ++p;
        }
        return true;
    }

    inline const char* field(const char* json, const char* key) {
        const char* p = json;
        whitespace(p);
        if (*p++ != '{') return nullptr;
        const char* found = nullptr;
        whitespace(p);
        if (*p == '}') { ++p; whitespace(p); return nullptr; }
        for (;;) {
            char name[24];
            if (!string(p, name, sizeof(name))) return nullptr;
            whitespace(p);
            if (*p++ != ':') return nullptr;
            whitespace(p);
            const char* value = p;
            if (*p == '"') {
                if (!string(p, nullptr, 0)) return nullptr;
            } else if (!number(p)) return nullptr;
            if (strcmp(name, key) == 0) {
                if (found) return nullptr; // ambiguous duplicate field
                found = value;
            }
            whitespace(p);
            if (*p == '}') {
                ++p; whitespace(p);
                return *p == '\0' ? found : nullptr;
            }
            if (*p++ != ',') return nullptr;
            whitespace(p);
        }
    }

    inline bool extractString(const char* json, const char* key, char* out, size_t cap) {
        const char* p = field(json, key);
        return p && cap && string(p, out, cap);
    }

    inline bool extractInt(const char* json, const char* key, int16_t& out) {
        const char* p = field(json, key);
        if (!p || *p == '"') return false;
        errno = 0;
        char* end = nullptr;
        long value = strtol(p, &end, 10);
        if (end == p || errno == ERANGE || value < -32768L || value > 32767L) return false;
        out = (int16_t)value;
        return true;
    }

    inline bool validName(const char* name, size_t maxLength = 15) {
        if (!name || !*name || strlen(name) > maxLength) return false;
        for (const char* p = name; *p; ++p) {
            if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
                  (*p >= '0' && *p <= '9') || *p == '_' || *p == '-')) return false;
        }
        return true;
    }

    inline bool acceptSeq(int16_t incomingSeq, int16_t& lastSeq) {
        if (incomingSeq < 1) return false;
        if (lastSeq <= 0) {
            lastSeq = incomingSeq;
            return true;
        }
        // The sender cycles over 1..32767 (zero is reserved). Wider arithmetic
        // avoids signed 16-bit overflow on AVR.
        uint16_t distance = (uint16_t)(((int32_t)incomingSeq - lastSeq + 32767L) % 32767L);
        if (distance == 0 || distance > 16383) return false;
        lastSeq = incomingSeq;
        return true;
    }

    inline int16_t scheduleDelayMs(int16_t atMs, uint32_t nowMs) {
        int16_t now15 = (int16_t)(nowMs & 0x7FFF);
        return (int16_t)((((int32_t)atMs - now15 + 16384L) & 0x7FFF) - 16384L);
    }
}
#endif
