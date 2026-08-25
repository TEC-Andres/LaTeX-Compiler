#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

typedef struct {
    int32_t old_start;
    int32_t old_end;
    int32_t new_start;
    int32_t new_end;
} Hunk;

typedef struct {
    Hunk *hunks;
    int32_t count;
    int32_t capacity;
} DiffResult;

typedef struct {
    int32_t *indices;
    int32_t length;
} LCSResult;

static uint64_t fnv1a64(const uint8_t *data, size_t len) {
    uint64_t hash = 14695981039346656037ULL; // FNV offset basis
    for (size_t i = 0; i < len; i++) {
        hash ^= data[i];
        hash *= 1099511628211ULL;
    }
    return hash;
}

EXPORT uint64_t pagecache_hash_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    uint64_t hash = 14695981039346656037ULL; // FNV offset basis
    uint8_t buf[8192];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0) {
        for (size_t i = 0; i < n; i++) {
            hash ^= buf[i];
            hash *= 1099511628211ULL;
        }
    }
    if (ferror(f)) {
        fclose(f);
        return 0; // Return 0 or failure sentinel on partial read errors
    }
    
    fclose(f);
    return hash;
}

EXPORT uint64_t pagecache_hash_buffer(const uint8_t *data, size_t len) {
    return fnv1a64(data, len);
}

EXPORT DiffResult *pagecache_diff_new(int32_t capacity) {
    DiffResult *r = (DiffResult *)malloc(sizeof(DiffResult));
    if (!r) return NULL;
    r->hunks = (Hunk *)malloc(sizeof(Hunk) * capacity);
    if (!r->hunks) { free(r); return NULL; }
    r->count = 0;
    r->capacity = capacity;
    return r;
}

EXPORT void pagecache_diff_free(DiffResult *r) {
    if (r) {
        free(r->hunks);
        free(r);
    }
}

static void diff_push(DiffResult *r, int32_t os, int32_t oe, int32_t ns, int32_t ne) {
    if (r->count >= r->capacity) {
        r->capacity *= 2;
        r->hunks = (Hunk *)realloc(r->hunks, sizeof(Hunk) * r->capacity);
    }
    r->hunks[r->count].old_start = os;
    r->hunks[r->count].old_end = oe;
    r->hunks[r->count].new_start = ns;
    r->hunks[r->count].new_end = ne;
    r->count++;
}

EXPORT DiffResult *pagecache_diff_lines(
    const char **old_lines, int32_t old_count,
    const char **new_lines, int32_t new_count,
    int32_t context
) {
    if (!old_lines || !new_lines) return NULL;

    int32_t total = old_count + new_count + 2;
    int32_t *prev = (int32_t *)calloc(total + 1, sizeof(int32_t));
    int32_t *curr = (int32_t *)calloc(total + 1, sizeof(int32_t));
    if (!prev || !curr) { free(prev); free(curr); return NULL; }

    int32_t offset = old_count + 1;

    for (int32_t i = 1; i <= old_count; i++) {
        for (int32_t j = 1; j <= new_count; j++) {
            if (old_lines[i - 1] && new_lines[j - 1] &&
                strcmp(old_lines[i - 1], new_lines[j - 1]) == 0) {
                curr[j] = prev[j - 1] + 1;
            } else {
                int32_t a = prev[j];
                int32_t b = curr[j - 1];
                curr[j] = a > b ? a : b;
            }
        }
        int32_t *tmp = prev;
        prev = curr;
        curr = tmp;
        memset(curr, 0, (total + 1) * sizeof(int32_t));
    }

    int32_t lcs_len = prev[new_count];
    free(prev);
    free(curr);

    int32_t max_hunks = old_count + new_count;
    DiffResult *result = pagecache_diff_new(max_hunks > 16 ? max_hunks : 16);
    if (!result) return NULL;

    if (lcs_len == old_count && lcs_len == new_count) {
        return result;
    }

    int32_t i = 0, j = 0;
    while (i < old_count || j < new_count) {
        int32_t change_start_old = i;
        int32_t change_start_new = j;

        while (i < old_count && j < new_count &&
               old_lines[i] && new_lines[j] &&
               strcmp(old_lines[i], new_lines[j]) == 0) {
            i++;
            j++;
        }

        if (i == old_count && j == new_count) break;

        int32_t di = i, dj = j;
        while (di < old_count && dj < new_count) {
            int32_t match = 0;
            for (int32_t k = 0; k <= (di - i + dj - j); k++) {
                if (di + k < old_count && dj + k < new_count &&
                    old_lines[di + k] && new_lines[dj + k] &&
                    strcmp(old_lines[di + k], new_lines[dj + k]) == 0) {
                    match = 1;
                    break;
                }
            }
            if (match) break;
            di++;
            dj++;
        }

        if (di == old_count && dj == new_count && i < old_count && j < new_count) {
            di = old_count;
            dj = new_count;
        }

        int32_t cs = change_start_old - context;
        int32_t ce = di + context;
        int32_t ns = change_start_new - context;
        int32_t ne = dj + context;

        if (cs < 0) cs = 0;
        if (ns < 0) ns = 0;
        if (ce > old_count) ce = old_count;
        if (ne > new_count) ne = new_count;

        if (result->count > 0) {
            Hunk *last = &result->hunks[result->count - 1];
            if (cs <= last->old_end + 1 && ns <= last->new_end + 1) {
                if (ce > last->old_end) last->old_end = ce;
                if (ne > last->new_end) last->new_end = ne;
                i = di;
                j = dj;
                continue;
            }
        }

        diff_push(result, cs, ce, ns, ne);
        i = di;
        j = dj;
    }

    return result;
}

EXPORT int32_t pagecache_diff_count(DiffResult *r) {
    return r ? r->count : 0;
}

EXPORT Hunk pagecache_diff_get(DiffResult *r, int32_t index) {
    Hunk empty = {0, 0, 0, 0};
    if (!r || index < 0 || index >= r->count) return empty;
    return r->hunks[index];
}

EXPORT int32_t pagecache_diff_total_lines_removed(DiffResult *r) {
    if (!r) return 0;
    int32_t total = 0;
    for (int32_t i = 0; i < r->count; i++) {
        total += r->hunks[i].old_end - r->hunks[i].old_start;
    }
    return total;
}

EXPORT int32_t pagecache_diff_total_lines_added(DiffResult *r) {
    if (!r) return 0;
    int32_t total = 0;
    for (int32_t i = 0; i < r->count; i++) {
        total += r->hunks[i].new_end - r->hunks[i].new_start;
    }
    return total;
}

EXPORT int32_t pagecache_diff_touches_page_range(
    DiffResult *r,
    const int32_t *line_to_page,
    int32_t line_count,
    int32_t page_start,
    int32_t page_end
) {
    if (!r || !line_to_page) return 0;
    for (int32_t i = 0; i < r->count; i++) {
        Hunk h = r->hunks[i];
        for (int32_t line = h.old_start; line < h.old_end && line < line_count; line++) {
            int32_t p = line_to_page[line];
            if (p >= page_start && p < page_end) return 1;
        }
        for (int32_t line = h.new_start; line < h.new_end && line < line_count; line++) {
            int32_t p = line_to_page[line];
            if (p >= page_start && p < page_end) return 1;
        }
    }
    return 0;
}
