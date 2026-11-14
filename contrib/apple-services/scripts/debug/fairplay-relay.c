/* Experimental one-request transport to Apple's AvpFairPlay user client.
 * No backend emulation, credential handling, listening socket, or payload logs.
 */
#define __STDC_WANT_LIB_EXT1__ 1
#include <IOKit/IOKitLib.h>
#include <errno.h>
#include <stdint.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_BUFFER (1024u * 1024u)
enum { ST_CALL = 0, ST_FRAME = 1, ST_SERVICE = 2, ST_OPEN = 3, ST_MEMORY = 4 };
static uint32_t get32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static void put32(unsigned char *p, uint32_t v) {
    for (unsigned i = 0; i < 4; ++i) p[i] = (unsigned char)(v >> (8 * i));
}
static int reply(uint32_t stage, uint32_t status, const void *body, uint32_t length) {
    unsigned char h[16] = {'O','F','R','1'};
    put32(h + 4, stage); put32(h + 8, status); put32(h + 12, length);
    if (fwrite(h, 1, sizeof h, stdout) != sizeof h ||
        (length && fwrite(body, 1, length, stdout) != length) || fflush(stdout)) return 2;
    return stage == ST_CALL && status == KERN_SUCCESS ? 0 : 1;
}
int main(void) {
    if (signal(SIGPIPE, SIG_IGN) == SIG_ERR) return 2;
    unsigned char h[12];
    if (fread(h, 1, sizeof h, stdin) != sizeof h ||
        (memcmp(h, "OFP1", 4) && memcmp(h, "OFP2", 4)))
        return reply(ST_FRAME, EPROTO, NULL, 0);
    uint32_t queue = 3;
    if (!memcmp(h, "OFP2", 4)) {
        unsigned char q[4];
        if (fread(q, 1, sizeof q, stdin) != sizeof q)
            return reply(ST_FRAME, EPROTO, NULL, 0);
        queue = get32(q);
        if (queue != 0 && queue != 3)
            return reply(ST_FRAME, EINVAL, NULL, 0);
    }
    uint32_t input_length = get32(h + 4), capacity = get32(h + 8);
    if (!input_length || !capacity || input_length > MAX_BUFFER || capacity > MAX_BUFFER)
        return reply(ST_FRAME, EINVAL, NULL, 0);
    unsigned char *input = malloc(input_length), *output = calloc(1, capacity);
    if (!input || !output) {
        free(input); free(output); return reply(ST_MEMORY, ENOMEM, NULL, 0);
    }
    int result;
    if (fread(input, 1, input_length, stdin) != input_length || fgetc(stdin) != EOF || ferror(stdin)) {
        result = reply(ST_FRAME, EPROTO, NULL, 0); goto done;
    }
    io_service_t service = IOServiceGetMatchingService(kIOMainPortDefault,
        IOServiceMatching("AvpFairPlayDriver"));
    if (!service) { result = reply(ST_SERVICE, kIOReturnNotFound, NULL, 0); goto done; }
    io_connect_t connection = IO_OBJECT_NULL;
    kern_return_t status = IOServiceOpen(service, mach_task_self(), 0, &connection);
    IOObjectRelease(service);
    if (status != KERN_SUCCESS) { result = reply(ST_OPEN, status, NULL, 0); goto done; }
    size_t output_length = capacity;
    status = IOConnectCallStructMethod(connection, queue == 0 ? 26 : 100,
                                     input, input_length, output, &output_length);
    IOServiceClose(connection);
    if (output_length > capacity) {
        result = reply(ST_CALL, kIOReturnOverrun, NULL, 0); goto done;
    }
    result = reply(ST_CALL, status, output, status == KERN_SUCCESS ? (uint32_t)output_length : 0);
done:
    (void)memset_s(input, input_length, 0, input_length);
    (void)memset_s(output, capacity, 0, capacity);
    free(input); free(output); return result;
}
