/*
  Copyright (c) 2009-2017 Dave Gamble and cJSON contributors

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
*/

/* cJSON */
/* JSON parser in C. */

#ifdef __GNUC__
#pragma GCC visibility push(default)
#endif

#include <string.h>
#include <stdio.h>
#include <math.h>
#include <stdlib.h>
#include <limits.h>
#include <ctype.h>

#ifdef __GNUC__
#pragma GCC visibility pop
#endif

#include "cJSON.h"

/* define our own boolean type */
#define true ((int)1)
#define false ((int)0)

/* Internal printbuffer struct */
typedef struct printbuffer
{
    char *buffer;
    int length;
    int offset;
    int noalloc;
} printbuffer;

/* global error pointer */
static const char *global_ep = NULL;

/* Global hooks */
static void *(*global_malloc_fn)(size_t sz) = malloc;
static void (*global_free_fn)(void *ptr) = free;

/* Internal constructor */
static cJSON *cJSON_New_Item(void)
{
    cJSON *node = (cJSON*)global_malloc_fn(sizeof(cJSON));
    if (node)
    {
        memset(node, 0, sizeof(cJSON));
    }
    return node;
}

/* Delete a cJSON entity. */
CJSON_PUBLIC(void) cJSON_Delete(cJSON *item)
{
    cJSON *next = NULL;
    while (item != NULL)
    {
        next = item->next;
        if (!(item->type & cJSON_IsReference) && (item->child != NULL))
        {
            cJSON_Delete(item->child);
        }
        if (!(item->type & cJSON_IsReference) && (item->valuestring != NULL))
        {
            global_free_fn(item->valuestring);
        }
        if (!(item->type & cJSON_StringIsConst) && (item->string != NULL))
        {
            global_free_fn(item->string);
        }
        global_free_fn(item);
        item = next;
    }
}

/* Internal: skip whitespace */
static const char *skip_whitespace(const char *in)
{
    while (in && *in && ((unsigned char)*in <= 32))
    {
        in++;
    }
    return in;
}

/* Parse the input text to get a number. */
static cJSON *parse_number(cJSON *const item, const char *const input, const char **const parse_end)
{
    double number = 0;
    unsigned char *after_end = NULL;
    if (input == NULL)
    {
        return NULL;
    }
    number = strtod(input, (char**)&after_end);
    if (after_end == (unsigned char*)input)
    {
        return NULL; /* parse error */
    }
    item->valuedouble = number;
    if (number >= INT_MAX)
    {
        item->valueint = INT_MAX;
    }
    else if (number <= INT_MIN)
    {
        item->valueint = INT_MIN;
    }
    else
    {
        item->valueint = (int)number;
    }
    item->type = cJSON_Number;
    if (parse_end != NULL)
    {
        *parse_end = (const char*)after_end;
    }
    return item;
}

/* Forward declarations for parse functions */
static cJSON *parse_value(cJSON *item, const char *value, const char **parse_end);
static cJSON *parse_array(cJSON *item, const char *value, const char **parse_end);
static cJSON *parse_object(cJSON *item, const char *value, const char **parse_end);
static cJSON *parse_string(cJSON *item, const char *value, const char **parse_end);

/* Render the number nicely from the given item into a string. */
static int print_number(const cJSON *const item, printbuffer *const output_buffer)
{
    char *output = NULL;
    double d = item->valuedouble;
    int length = 0;
    char number_buffer[64] = {0};

    if (output_buffer == NULL)
    {
        return false;
    }

    /* This checks for NaN and Infinity */
    if ((d != d) || (d > DBL_MAX) || (d < -DBL_MAX))
    {
        length = sprintf(number_buffer, "null");
    }
    else if ((fabs(floor(d) - d) <= DBL_EPSILON) && (fabs(d) < 1.0e15))
    {
        /* integer */
        length = sprintf(number_buffer, "%.0f", d);
    }
    else
    {
        /* decimal */
        length = sprintf(number_buffer, "%.17g", d);
    }

    /* sprintf failed */
    if (length < 0)
    {
        return false;
    }

    output = output_buffer->buffer + output_buffer->offset;
    memcpy(output, number_buffer, (size_t)length);
    output_buffer->offset += length;
    output[length] = '\0';

    return true;
}

/* Render a string to provide enough space in the buffer. */
static int print_string_ptr(const char *str, printbuffer *const output_buffer)
{
    const char *ptr = NULL;
    char *output = NULL;
    int length = 0;
    int output_length = 0;
    int escape_sequence = 0;

    if (output_buffer == NULL)
    {
        return false;
    }

    /* empty string */
    if (str == NULL)
    {
        output = output_buffer->buffer + output_buffer->offset;
        output[0] = '\"';
        output[1] = '\"';
        output_buffer->offset += 2;
        return true;
    }

    /* set length */
    for (ptr = str; *ptr != '\0'; ptr++)
    {
        switch (*ptr)
        {
            case '\"': case '\\': case '\b': case '\f':
            case '\n': case '\r': case '\t':
                escape_sequence++;
                break;
            default:
                if ((unsigned char)*ptr < 32)
                {
                    escape_sequence += 5;
                }
                break;
        }
    }
    length = (int)(ptr - str);
    output_length = length + escape_sequence + 2; /* two quotes */

    output = output_buffer->buffer + output_buffer->offset;
    output[0] = '\"';
    output_buffer->offset++;
    output++;

    for (ptr = str; *ptr != '\0'; ptr++)
    {
        if (*ptr > 31 && *ptr != '\"' && *ptr != '\\')
        {
            *output++ = *ptr;
            output_buffer->offset++;
        }
        else
        {
            *output++ = '\\';
            output_buffer->offset++;
            switch (*ptr)
            {
                case '\\': *output++ = '\\'; break;
                case '\"': *output++ = '\"'; break;
                case '\b': *output++ = 'b'; break;
                case '\f': *output++ = 'f'; break;
                case '\n': *output++ = 'n'; break;
                case '\r': *output++ = 'r'; break;
                case '\t': *output++ = 't'; break;
                default:
                    output += sprintf(output, "u%04x", (unsigned char)*ptr);
                    output_buffer->offset += 5;
                    continue;
            }
            output_buffer->offset++;
        }
    }
    *output++ = '\"';
    output_buffer->offset++;

    return true;
}

/* Invoke print_string_ptr (which is useful) on an item. */
static int print_string(const cJSON *const item, printbuffer *const pb)
{
    return print_string_ptr(item->valuestring, pb);
}

/* Forward declarations for print functions */
static int print_value(const cJSON *const item, const int depth, const int fmt, printbuffer *const output_buffer);
static int print_array(const cJSON *const item, const int depth, const int fmt, printbuffer *const output_buffer);
static int print_object(const cJSON *const item, const int depth, const int fmt, printbuffer *const output_buffer);

/* Utility to jump whitespace and cr/lf */
static int parse_hex4(const char *str)
{
    int h = 0;
    if (*str >= '0' && *str <= '9') h += (*str) - '0';
    else if (*str >= 'A' && *str <= 'F') h += 10 + (*str) - 'A';
    else if (*str >= 'a' && *str <= 'f') h += 10 + (*str) - 'a';
    else return 0;
    h = h << 4;
    str++;
    if (*str >= '0' && *str <= '9') h += (*str) - '0';
    else if (*str >= 'A' && *str <= 'F') h += 10 + (*str) - 'A';
    else if (*str >= 'a' && *str <= 'f') h += 10 + (*str) - 'a';
    else return 0;
    h = h << 4;
    str++;
    if (*str >= '0' && *str <= '9') h += (*str) - '0';
    else if (*str >= 'A' && *str <= 'F') h += 10 + (*str) - 'A';
    else if (*str >= 'a' && *str <= 'f') h += 10 + (*str) - 'a';
    else return 0;
    h = h << 4;
    str++;
    if (*str >= '0' && *str <= '9') h += (*str) - '0';
    else if (*str >= 'A' && *str <= 'F') h += 10 + (*str) - 'A';
    else if (*str >= 'a' && *str <= 'f') h += 10 + (*str) - 'a';
    else return 0;
    return h;
}

/* Parse the input text into an unescaped cstring. */
static unsigned char *utf16_string_to_utf8_string(const unsigned char *const input, size_t *output_len)
{
    /* Simplified UTF-16 to UTF-8 conversion for \uXXXX sequences */
    size_t input_len = 0;
    size_t i = 0;
    unsigned char *output = NULL;
    size_t output_index = 0;
    int first_code = 0;
    int second_code = 0;

    if (input == NULL)
    {
        return NULL;
    }

    input_len = strlen((const char*)input);
    output = (unsigned char*)global_malloc_fn(input_len + 1);
    if (output == NULL)
    {
        return NULL;
    }

    while (i < input_len)
    {
        if (input[i] == '\\' && (i + 1) < input_len && input[i + 1] == 'u')
        {
            /* Parse \uXXXX */
            if ((i + 5) < input_len)
            {
                char hex[5] = {0};
                memcpy(hex, input + i + 2, 4);
                first_code = (int)strtol(hex, NULL, 16);

                /* Check for surrogate pair */
                if ((i + 11) < input_len && input[i + 6] == '\\' && input[i + 7] == 'u')
                {
                    char hex2[5] = {0};
                    memcpy(hex2, input + i + 8, 4);
                    second_code = (int)strtol(hex2, NULL, 16);
                    if (first_code >= 0xD800 && first_code <= 0xDBFF &&
                        second_code >= 0xDC00 && second_code <= 0xDFFF)
                    {
                        /* Valid surrogate pair */
                        int codepoint = ((first_code - 0xD800) << 10) + (second_code - 0xDC00) + 0x10000;
                        output[output_index++] = (unsigned char)(0xF0 | ((codepoint >> 18) & 0x07));
                        output[output_index++] = (unsigned char)(0x80 | ((codepoint >> 12) & 0x3F));
                        output[output_index++] = (unsigned char)(0x80 | ((codepoint >> 6) & 0x3F));
                        output[output_index++] = (unsigned char)(0x80 | (codepoint & 0x3F));
                        i += 12;
                        continue;
                    }
                }

                /* Single \uXXXX */
                if (first_code < 0x80)
                {
                    output[output_index++] = (unsigned char)first_code;
                }
                else if (first_code < 0x800)
                {
                    output[output_index++] = (unsigned char)(0xC0 | ((first_code >> 6) & 0x1F));
                    output[output_index++] = (unsigned char)(0x80 | (first_code & 0x3F));
                }
                else
                {
                    output[output_index++] = (unsigned char)(0xE0 | ((first_code >> 12) & 0x0F));
                    output[output_index++] = (unsigned char)(0x80 | ((first_code >> 6) & 0x3F));
                    output[output_index++] = (unsigned char)(0x80 | (first_code & 0x3F));
                }
                i += 6;
                continue;
            }
        }
        output[output_index++] = input[i++];
    }
    output[output_index] = '\0';
    if (output_len != NULL)
    {
        *output_len = output_index;
    }
    return output;
}

/* Parse the input text into a string item. */
static cJSON *parse_string(cJSON *const item, const char *const input, const char **const parse_end)
{
    const char *ptr = input + 1;
    const char *end_ptr = NULL;
    char *output = NULL;
    int output_length = 0;
    size_t utf8_len = 0;

    if (input == NULL || *input != '\"')
    {
        goto fail;
    }

    /* find the end of the string */
    while (*ptr != '\"')
    {
        if (*ptr == '\0')
        {
            goto fail;
        }
        if (*ptr == '\\')
        {
            ptr++;
            if (*ptr == '\0')
            {
                goto fail;
            }
        }
        ptr++;
    }

    end_ptr = ptr;
    ptr = input + 1;

    /* calculate output length */
    output_length = (int)(end_ptr - ptr);
    output = (char*)global_malloc_fn(output_length + 1);
    if (output == NULL)
    {
        goto fail;
    }

    /* copy with escape handling */
    {
        int i = 0;
        while (ptr < end_ptr)
        {
            if (*ptr != '\\')
            {
                output[i++] = *ptr++;
            }
            else
            {
                ptr++;
                switch (*ptr)
                {
                    case 'b': output[i++] = '\b'; break;
                    case 'f': output[i++] = '\f'; break;
                    case 'n': output[i++] = '\n'; break;
                    case 'r': output[i++] = '\r'; break;
                    case 't': output[i++] = '\t'; break;
                    case '\"': output[i++] = '\"'; break;
                    case '\\': output[i++] = '\\'; break;
                    case '/': output[i++] = '/'; break;
                    case 'u':
                    {
                        /* Handle \uXXXX escape sequences */
                        unsigned char *utf8_str = NULL;
                        size_t utf8_out_len = 0;
                        char *u_start = (char*)(ptr - 1);
                        int seq_len = 2; /* \u */

                        /* Find end of all consecutive \uXXXX sequences */
                        while (u_start[seq_len - 1] == 'u' || (u_start[seq_len] == '\\' && u_start[seq_len + 1] == 'u'))
                        {
                            if (u_start[seq_len - 1] == 'u')
                            {
                                seq_len += 4; /* XXXX */
                                if (u_start[seq_len] == '\\' && u_start[seq_len + 1] == 'u')
                                {
                                    seq_len += 2; /* \u */
                                }
                            }
                            else
                            {
                                break;
                            }
                        }

                        utf8_str = utf16_string_to_utf8_string((const unsigned char*)u_start, &utf8_out_len);
                        if (utf8_str != NULL)
                        {
                            memcpy(output + i, utf8_str, utf8_out_len);
                            i += (int)utf8_out_len;
                            global_free_fn(utf8_str);
                        }
                        ptr += 4; /* skip XXXX after \u */
                        break;
                    }
                    default: output[i++] = *ptr; break;
                }
                ptr++;
            }
        }
        output[i] = '\0';
    }

    item->type = cJSON_String;
    item->valuestring = output;

    if (parse_end != NULL)
    {
        *parse_end = end_ptr + 1;
    }
    return item;

fail:
    if (parse_end != NULL)
    {
        *parse_end = input;
    }
    return NULL;
}

/* Parser core. */
static cJSON *parse_value(cJSON *const item, const char *value, const char **const parse_end)
{
    if (value == NULL)
    {
        return NULL;
    }

    value = skip_whitespace(value);

    switch (*value)
    {
        case '{':
            return parse_object(item, value, parse_end);
        case '[':
            return parse_array(item, value, parse_end);
        case '\"':
            return parse_string(item, value, parse_end);
        case '-':
        case '0': case '1': case '2': case '3': case '4':
        case '5': case '6': case '7': case '8': case '9':
            return parse_number(item, value, parse_end);
        case 't':
            if (strncmp(value, "true", 4) == 0)
            {
                item->type = cJSON_True;
                item->valueint = 1;
                item->valuedouble = 1;
                if (parse_end) *parse_end = value + 4;
                return item;
            }
            break;
        case 'f':
            if (strncmp(value, "false", 5) == 0)
            {
                item->type = cJSON_False;
                item->valueint = 0;
                item->valuedouble = 0;
                if (parse_end) *parse_end = value + 5;
                return item;
            }
            break;
        case 'n':
            if (strncmp(value, "null", 4) == 0)
            {
                item->type = cJSON_NULL;
                if (parse_end) *parse_end = value + 4;
                return item;
            }
            break;
        default:
            break;
    }

    global_ep = value;
    return NULL;
}

/* Build an array from input text. */
static cJSON *parse_array(cJSON *const item, const char *value, const char **const parse_end)
{
    cJSON *child = NULL;
    cJSON *new_item = NULL;

    if (value == NULL || *value != '[')
    {
        goto fail;
    }

    item->type = cJSON_Array;
    value = skip_whitespace(value + 1);

    if (*value == ']')
    {
        if (parse_end) *parse_end = value + 1;
        return item;
    }

    child = cJSON_New_Item();
    if (child == NULL)
    {
        goto fail;
    }
    item->child = child;

    if (parse_value(child, value, &value) == NULL)
    {
        goto fail;
    }

    while (*value == ',')
    {
        new_item = cJSON_New_Item();
        if (new_item == NULL)
        {
            goto fail;
        }
        child->next = new_item;
        new_item->prev = child;
        child = new_item;

        value = skip_whitespace(value + 1);
        if (parse_value(child, value, &value) == NULL)
        {
            goto fail;
        }
    }

    value = skip_whitespace(value);
    if (*value != ']')
    {
        goto fail;
    }

    if (parse_end) *parse_end = value + 1;
    return item;

fail:
    global_ep = value;
    if (parse_end) *parse_end = value;
    return NULL;
}

/* Build an object from the input text. */
static cJSON *parse_object(cJSON *const item, const char *value, const char **const parse_end)
{
    cJSON *child = NULL;
    cJSON *new_item = NULL;
    cJSON *string_item = NULL;

    if (value == NULL || *value != '{')
    {
        goto fail;
    }

    item->type = cJSON_Object;
    value = skip_whitespace(value + 1);

    if (*value == '}')
    {
        if (parse_end) *parse_end = value + 1;
        return item;
    }

    child = cJSON_New_Item();
    if (child == NULL)
    {
        goto fail;
    }
    item->child = child;

    /* parse key */
    string_item = cJSON_New_Item();
    if (string_item == NULL)
    {
        goto fail;
    }
    if (parse_string(string_item, value, &value) == NULL)
    {
        cJSON_Delete(string_item);
        goto fail;
    }
    child->string = string_item->valuestring;
    string_item->valuestring = NULL;
    cJSON_Delete(string_item);

    value = skip_whitespace(value);
    if (*value != ':')
    {
        goto fail;
    }
    value = skip_whitespace(value + 1);

    if (parse_value(child, value, &value) == NULL)
    {
        goto fail;
    }

    while (*value == ',')
    {
        value = skip_whitespace(value + 1);

        new_item = cJSON_New_Item();
        if (new_item == NULL)
        {
            goto fail;
        }
        child->next = new_item;
        new_item->prev = child;
        child = new_item;

        /* parse key */
        string_item = cJSON_New_Item();
        if (string_item == NULL)
        {
            goto fail;
        }
        if (parse_string(string_item, value, &value) == NULL)
        {
            cJSON_Delete(string_item);
            goto fail;
        }
        child->string = string_item->valuestring;
        string_item->valuestring = NULL;
        cJSON_Delete(string_item);

        value = skip_whitespace(value);
        if (*value != ':')
        {
            goto fail;
        }
        value = skip_whitespace(value + 1);

        if (parse_value(child, value, &value) == NULL)
        {
            goto fail;
        }
    }

    value = skip_whitespace(value);
    if (*value != '}')
    {
        goto fail;
    }

    if (parse_end) *parse_end = value + 1;
    return item;

fail:
    global_ep = value;
    if (parse_end) *parse_end = value;
    return NULL;
}

/* Render a value to text. */
static int print_value(const cJSON *const item, const int depth, const int fmt, printbuffer *const output_buffer)
{
    char *output = NULL;

    if (output_buffer == NULL || item == NULL)
    {
        return false;
    }

    switch ((item->type) & 0xFF)
    {
        case cJSON_NULL:
            output = output_buffer->buffer + output_buffer->offset;
            memcpy(output, "null", 4);
            output_buffer->offset += 4;
            output[4] = '\0';
            return true;
        case cJSON_False:
            output = output_buffer->buffer + output_buffer->offset;
            memcpy(output, "false", 5);
            output_buffer->offset += 5;
            output[5] = '\0';
            return true;
        case cJSON_True:
            output = output_buffer->buffer + output_buffer->offset;
            memcpy(output, "true", 4);
            output_buffer->offset += 4;
            output[4] = '\0';
            return true;
        case cJSON_Number:
            return print_number(item, output_buffer);
        case cJSON_Raw:
            if (item->valuestring == NULL)
            {
                return false;
            }
            {
                int raw_len = (int)strlen(item->valuestring);
                output = output_buffer->buffer + output_buffer->offset;
                memcpy(output, item->valuestring, (size_t)raw_len);
                output_buffer->offset += raw_len;
                output[raw_len] = '\0';
            }
            return true;
        case cJSON_String:
            return print_string(item, output_buffer);
        case cJSON_Array:
            return print_array(item, depth, fmt, output_buffer);
        case cJSON_Object:
            return print_object(item, depth, fmt, output_buffer);
        default:
            return false;
    }
}

/* Render an array to text. */
static int print_array(const cJSON *const item, const int depth, const int fmt, printbuffer *const output_buffer)
{
    int i = 0;
    cJSON *current_item = NULL;
    char *output = NULL;

    if (output_buffer == NULL)
    {
        return false;
    }

    output = output_buffer->buffer + output_buffer->offset;
    output[0] = '[';
    output_buffer->offset++;
    output++;

    current_item = item->child;
    if (current_item == NULL)
    {
        output[0] = ']';
        output_buffer->offset++;
        return true;
    }

    while (current_item != NULL)
    {
        if (fmt)
        {
            /* indentation */
            int j;
            output = output_buffer->buffer + output_buffer->offset;
            output[0] = '\n';
            output_buffer->offset++;
            for (j = 0; j < depth + 1; j++)
            {
                output = output_buffer->buffer + output_buffer->offset;
                output[0] = '\t';
                output_buffer->offset++;
            }
        }

        if (!print_value(current_item, depth + 1, fmt, output_buffer))
        {
            return false;
        }

        current_item = current_item->next;
        if (current_item != NULL)
        {
            output = output_buffer->buffer + output_buffer->offset;
            output[0] = ',';
            output_buffer->offset++;
        }
    }

    if (fmt)
    {
        int j;
        output = output_buffer->buffer + output_buffer->offset;
        output[0] = '\n';
        output_buffer->offset++;
        for (j = 0; j < depth; j++)
        {
            output = output_buffer->buffer + output_buffer->offset;
            output[0] = '\t';
            output_buffer->offset++;
        }
    }

    output = output_buffer->buffer + output_buffer->offset;
    output[0] = ']';
    output_buffer->offset++;

    return true;
}

/* Render an object to text. */
static int print_object(const cJSON *const item, const int depth, const int fmt, printbuffer *const output_buffer)
{
    cJSON *current_item = NULL;
    char *output = NULL;

    if (output_buffer == NULL)
    {
        return false;
    }

    output = output_buffer->buffer + output_buffer->offset;
    output[0] = '{';
    output_buffer->offset++;
    output++;

    current_item = item->child;
    if (current_item == NULL)
    {
        output[0] = '}';
        output_buffer->offset++;
        return true;
    }

    while (current_item != NULL)
    {
        if (fmt)
        {
            int j;
            output = output_buffer->buffer + output_buffer->offset;
            output[0] = '\n';
            output_buffer->offset++;
            for (j = 0; j < depth + 1; j++)
            {
                output = output_buffer->buffer + output_buffer->offset;
                output[0] = '\t';
                output_buffer->offset++;
            }
        }

        if (!print_string_ptr(current_item->string, output_buffer))
        {
            return false;
        }

        output = output_buffer->buffer + output_buffer->offset;
        if (fmt)
        {
            output[0] = ':';
            output[1] = ' ';
            output_buffer->offset += 2;
        }
        else
        {
            output[0] = ':';
            output_buffer->offset++;
        }

        if (!print_value(current_item, depth + 1, fmt, output_buffer))
        {
            return false;
        }

        current_item = current_item->next;
        if (current_item != NULL)
        {
            output = output_buffer->buffer + output_buffer->offset;
            output[0] = ',';
            output_buffer->offset++;
        }
    }

    if (fmt)
    {
        int j;
        output = output_buffer->buffer + output_buffer->offset;
        output[0] = '\n';
        output_buffer->offset++;
        for (j = 0; j < depth; j++)
        {
            output = output_buffer->buffer + output_buffer->offset;
            output[0] = '\t';
            output_buffer->offset++;
        }
    }

    output = output_buffer->buffer + output_buffer->offset;
    output[0] = '}';
    output_buffer->offset++;

    return true;
}

/* Calculate how much memory is needed for the printed text */
static int calculate_print_length(const cJSON *const item, const int depth, const int fmt)
{
    /* Rough estimate: use a large buffer */
    int length = 0;
    char *printed = NULL;
    printbuffer buffer;

    /* First pass: estimate size */
    length = 1024; /* start with 1KB */
    if (item != NULL)
    {
        /* Count items for rough estimate */
        cJSON *cur = item->child;
        while (cur != NULL)
        {
            length += 256;
            cur = cur->next;
        }
    }

    return length;
}

/* Public API: Parse a JSON string */
CJSON_PUBLIC(cJSON *) cJSON_Parse(const char *value)
{
    return cJSON_ParseWithOpts(value, 0, 0);
}

CJSON_PUBLIC(cJSON *) cJSON_ParseWithOpts(const char *value, const char **return_parse_end, int require_null_terminated)
{
    const char *end = NULL;
    cJSON *item = NULL;

    global_ep = NULL;

    if (value == NULL)
    {
        goto fail;
    }

    item = cJSON_New_Item();
    if (item == NULL)
    {
        goto fail;
    }

    end = value;
    if (parse_value(item, end, &end) == NULL)
    {
        cJSON_Delete(item);
        item = NULL;
        goto fail;
    }

    if (require_null_terminated)
    {
        end = skip_whitespace(end);
        if (*end != '\0')
        {
            cJSON_Delete(item);
            item = NULL;
            global_ep = end;
            goto fail;
        }
    }

    if (return_parse_end)
    {
        *return_parse_end = end;
    }

    return item;

fail:
    if (return_parse_end)
    {
        *return_parse_end = value;
    }
    return NULL;
}

/* Public API: Print cJSON to string */
CJSON_PUBLIC(char *) cJSON_Print(const cJSON *item)
{
    return cJSON_PrintBuffered(item, 256, 1);
}

CJSON_PUBLIC(char *) cJSON_PrintUnformatted(const cJSON *item)
{
    return cJSON_PrintBuffered(item, 256, 0);
}

CJSON_PUBLIC(char *) cJSON_PrintBuffered(const cJSON *item, int prebuffer, int fmt)
{
    printbuffer buffer;
    char *output = NULL;
    int length = 0;

    if (item == NULL)
    {
        return NULL;
    }

    /* First pass: calculate needed size by printing into a large buffer */
    length = calculate_print_length(item, 0, fmt);
    if (length < prebuffer)
    {
        length = prebuffer;
    }
    length += 1024; /* extra safety margin */

    output = (char*)global_malloc_fn((size_t)length);
    if (output == NULL)
    {
        return NULL;
    }

    buffer.buffer = output;
    buffer.length = length;
    buffer.offset = 0;
    buffer.noalloc = 0;

    if (!print_value(item, 0, fmt, &buffer))
    {
        global_free_fn(output);
        return NULL;
    }

    return output;
}

CJSON_PUBLIC(int) cJSON_PrintPreallocated(cJSON *item, char *buffer, const int length, const int format)
{
    printbuffer p;

    if (buffer == NULL || length <= 0)
    {
        return false;
    }

    p.buffer = buffer;
    p.length = length;
    p.offset = 0;
    p.noalloc = 1;

    if (!print_value(item, 0, format, &p))
    {
        return false;
    }

    return true;
}

CJSON_PUBLIC(void) cJSON_InitHooks(cJSON_Hooks* hooks)
{
    if (hooks == NULL)
    {
        global_malloc_fn = malloc;
        global_free_fn = free;
    }
    else
    {
        global_malloc_fn = hooks->malloc_fn;
        global_free_fn = hooks->free_fn;
    }
}

CJSON_PUBLIC(cJSON *) cJSON_Create(void)
{
    cJSON *item = cJSON_New_Item();
    if (item)
    {
        item->type = cJSON_Invalid;
    }
    return item;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateNull(void)
{
    cJSON *item = cJSON_New_Item();
    if (item)
    {
        item->type = cJSON_NULL;
    }
    return item;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateTrue(void)
{
    cJSON *item = cJSON_New_Item();
    if (item)
    {
        item->type = cJSON_True;
        item->valueint = 1;
    }
    return item;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateFalse(void)
{
    cJSON *item = cJSON_New_Item();
    if (item)
    {
        item->type = cJSON_False;
        item->valueint = 0;
    }
    return item;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateBool(int boolean)
{
    cJSON *item = cJSON_New_Item();
    if (item)
    {
        item->type = boolean ? cJSON_True : cJSON_False;
        item->valueint = boolean ? 1 : 0;
    }
    return item;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateNumber(double num)
{
    cJSON *item = cJSON_New_Item();
    if (item)
    {
        item->type = cJSON_Number;
        item->valuedouble = num;
        if (num >= INT_MAX)
        {
            item->valueint = INT_MAX;
        }
        else if (num <= INT_MIN)
        {
            item->valueint = INT_MIN;
        }
        else
        {
            item->valueint = (int)num;
        }
    }
    return item;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateString(const char *string)
{
    cJSON *item = cJSON_New_Item();
    if (item)
    {
        item->type = cJSON_String;
        item->valuestring = (char*)global_malloc_fn(strlen(string) + 1);
        if (item->valuestring)
        {
            strcpy(item->valuestring, string);
        }
    }
    return item;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateRaw(const char *raw)
{
    cJSON *item = cJSON_New_Item();
    if (item)
    {
        item->type = cJSON_Raw;
        item->valuestring = (char*)global_malloc_fn(strlen(raw) + 1);
        if (item->valuestring)
        {
            strcpy(item->valuestring, raw);
        }
    }
    return item;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateArray(void)
{
    cJSON *item = cJSON_New_Item();
    if (item)
    {
        item->type = cJSON_Array;
    }
    return item;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateObject(void)
{
    cJSON *item = cJSON_New_Item();
    if (item)
    {
        item->type = cJSON_Object;
    }
    return item;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateIntArray(const int *numbers, int count)
{
    int i = 0;
    cJSON *n = NULL, *p = NULL, *a = cJSON_CreateArray();
    for (i = 0; a && (i < count); i++)
    {
        n = cJSON_CreateNumber(numbers[i]);
        if (!n)
        {
            cJSON_Delete(a);
            return NULL;
        }
        if (!i)
        {
            a->child = n;
        }
        else
        {
            p->next = n;
            n->prev = p;
        }
        p = n;
    }
    return a;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateDoubleArray(const double *numbers, int count)
{
    int i = 0;
    cJSON *n = NULL, *p = NULL, *a = cJSON_CreateArray();
    for (i = 0; a && (i < count); i++)
    {
        n = cJSON_CreateNumber(numbers[i]);
        if (!n)
        {
            cJSON_Delete(a);
            return NULL;
        }
        if (!i)
        {
            a->child = n;
        }
        else
        {
            p->next = n;
            n->prev = p;
        }
        p = n;
    }
    return a;
}

CJSON_PUBLIC(cJSON *) cJSON_CreateStringArray(const char **strings, int count)
{
    int i = 0;
    cJSON *n = NULL, *p = NULL, *a = cJSON_CreateArray();
    for (i = 0; a && (i < count); i++)
    {
        n = cJSON_CreateString(strings[i]);
        if (!n)
        {
            cJSON_Delete(a);
            return NULL;
        }
        if (!i)
        {
            a->child = n;
        }
        else
        {
            p->next = n;
            n->prev = p;
        }
        p = n;
    }
    return a;
}

CJSON_PUBLIC(void) cJSON_AddItemToArray(cJSON *array, cJSON *item)
{
    cJSON *child = NULL;
    if (array == NULL || item == NULL)
    {
        return;
    }
    child = array->child;
    if (child == NULL)
    {
        array->child = item;
        item->prev = NULL;
    }
    else
    {
        while (child->next)
        {
            child = child->next;
        }
        child->next = item;
        item->prev = child;
    }
    item->next = NULL;
}

CJSON_PUBLIC(void) cJSON_AddItemToObject(cJSON *object, const char *string, cJSON *item)
{
    if (object == NULL || item == NULL)
    {
        return;
    }
    if (item->string)
    {
        global_free_fn(item->string);
    }
    item->string = (char*)global_malloc_fn(strlen(string) + 1);
    if (item->string)
    {
        strcpy(item->string, string);
    }
    cJSON_AddItemToArray(object, item);
}

CJSON_PUBLIC(void) cJSON_AddItemToObjectCS(cJSON *object, const char *string, cJSON *item)
{
    if (object == NULL || item == NULL)
    {
        return;
    }
    if (item->string)
    {
        global_free_fn(item->string);
    }
    item->string = (char*)string;
    item->type |= cJSON_StringIsConst;
    cJSON_AddItemToArray(object, item);
}

CJSON_PUBLIC(cJSON *) cJSON_DetachItemViaPointer(cJSON *parent, cJSON *const item)
{
    if (parent == NULL || item == NULL)
    {
        return NULL;
    }
    if (item->prev)
    {
        item->prev->next = item->next;
    }
    if (item->next)
    {
        item->next->prev = item->prev;
    }
    if (parent->child == item)
    {
        parent->child = item->next;
    }
    item->prev = NULL;
    item->next = NULL;
    return item;
}

CJSON_PUBLIC(cJSON *) cJSON_DetachItemFromArray(cJSON *array, int which)
{
    cJSON *item = cJSON_GetArrayItem(array, which);
    return cJSON_DetachItemViaPointer(array, item);
}

CJSON_PUBLIC(void) cJSON_DeleteItemFromArray(cJSON *array, int which)
{
    cJSON_Delete(cJSON_DetachItemFromArray(array, which));
}

CJSON_PUBLIC(cJSON *) cJSON_DetachItemFromObject(cJSON *object, const char *string)
{
    cJSON *item = cJSON_GetObjectItem(object, string);
    return cJSON_DetachItemViaPointer(object, item);
}

CJSON_PUBLIC(cJSON *) cJSON_DetachItemFromObjectCaseSensitive(cJSON *object, const char *string)
{
    cJSON *item = cJSON_GetObjectItemCaseSensitive(object, string);
    return cJSON_DetachItemViaPointer(object, item);
}

CJSON_PUBLIC(void) cJSON_DeleteItemFromObject(cJSON *object, const char *string)
{
    cJSON_Delete(cJSON_DetachItemFromObject(object, string));
}

CJSON_PUBLIC(void) cJSON_DeleteItemFromObjectCaseSensitive(cJSON *object, const char *string)
{
    cJSON_Delete(cJSON_DetachItemFromObjectCaseSensitive(object, string));
}

CJSON_PUBLIC(void) cJSON_InsertItemInArray(cJSON *array, int which, cJSON *newitem)
{
    cJSON *after = NULL;
    if (array == NULL || newitem == NULL)
    {
        return;
    }
    after = cJSON_GetArrayItem(array, which);
    if (after == NULL)
    {
        cJSON_AddItemToArray(array, newitem);
        return;
    }
    newitem->next = after;
    newitem->prev = after->prev;
    after->prev = newitem;
    if (after == array->child)
    {
        array->child = newitem;
    }
    else
    {
        newitem->prev->next = newitem;
    }
}

CJSON_PUBLIC(void) cJSON_ReplaceItemViaPointer(cJSON *parent, cJSON *const item, cJSON *replacement)
{
    if (parent == NULL || item == NULL || replacement == NULL)
    {
        return;
    }
    if (replacement->next)
    {
        replacement->next = NULL;
    }
    if (replacement->prev)
    {
        replacement->prev = NULL;
    }
    replacement->next = item->next;
    replacement->prev = item->prev;
    if (replacement->next)
    {
        replacement->next->prev = replacement;
    }
    if (item->prev)
    {
        item->prev->next = replacement;
    }
    if (parent->child == item)
    {
        parent->child = replacement;
    }
    item->next = NULL;
    item->prev = NULL;
    cJSON_Delete(item);
}

CJSON_PUBLIC(void) cJSON_ReplaceItemInArray(cJSON *array, int which, cJSON *newitem)
{
    cJSON *item = cJSON_GetArrayItem(array, which);
    cJSON_ReplaceItemViaPointer(array, item, newitem);
}

CJSON_PUBLIC(void) cJSON_ReplaceItemInObject(cJSON *object, const char *string, cJSON *newitem)
{
    cJSON *item = cJSON_GetObjectItem(object, string);
    if (item == NULL)
    {
        cJSON_AddItemToObject(object, string, newitem);
        return;
    }
    if (newitem->string)
    {
        global_free_fn(newitem->string);
    }
    newitem->string = (char*)global_malloc_fn(strlen(string) + 1);
    if (newitem->string)
    {
        strcpy(newitem->string, string);
    }
    cJSON_ReplaceItemViaPointer(object, item, newitem);
}

CJSON_PUBLIC(void) cJSON_ReplaceItemInObjectCaseSensitive(cJSON *object, const char *string, cJSON *newitem)
{
    cJSON *item = cJSON_GetObjectItemCaseSensitive(object, string);
    if (item == NULL)
    {
        cJSON_AddItemToObject(object, string, newitem);
        return;
    }
    if (newitem->string)
    {
        global_free_fn(newitem->string);
    }
    newitem->string = (char*)global_malloc_fn(strlen(string) + 1);
    if (newitem->string)
    {
        strcpy(newitem->string, string);
    }
    cJSON_ReplaceItemViaPointer(object, item, newitem);
}

CJSON_PUBLIC(cJSON *) cJSON_Duplicate(const cJSON *item, int recurse)
{
    cJSON *newitem = NULL;
    cJSON *child = NULL;
    cJSON *newchild = NULL;
    cJSON *next = NULL;

    if (item == NULL)
    {
        return NULL;
    }

    newitem = cJSON_New_Item();
    if (newitem == NULL)
    {
        return NULL;
    }

    newitem->type = item->type;
    newitem->valueint = item->valueint;
    newitem->valuedouble = item->valuedouble;

    if (item->valuestring)
    {
        newitem->valuestring = (char*)global_malloc_fn(strlen(item->valuestring) + 1);
        if (newitem->valuestring)
        {
            strcpy(newitem->valuestring, item->valuestring);
        }
    }

    if (item->string)
    {
        newitem->string = (char*)global_malloc_fn(strlen(item->string) + 1);
        if (newitem->string)
        {
            strcpy(newitem->string, item->string);
        }
    }

    if (!recurse)
    {
        return newitem;
    }

    child = item->child;
    while (child != NULL)
    {
        newchild = cJSON_Duplicate(child, 1);
        if (newchild == NULL)
        {
            cJSON_Delete(newitem);
            return NULL;
        }
        if (newitem->child == NULL)
        {
            newitem->child = newchild;
        }
        else
        {
            next = newitem->child;
            while (next->next)
            {
                next = next->next;
            }
            next->next = newchild;
            newchild->prev = next;
        }
        child = child->next;
    }

    return newitem;
}

CJSON_PUBLIC(int) cJSON_Compare(const cJSON *a, const cJSON *b, const int case_sensitive)
{
    if (a == NULL || b == NULL)
    {
        return (a == b) ? 1 : 0;
    }

    if ((a->type & 0xFF) != (b->type & 0xFF))
    {
        return 0;
    }

    switch (a->type & 0xFF)
    {
        case cJSON_Number:
            if (a->valuedouble != b->valuedouble)
            {
                return 0;
            }
            break;
        case cJSON_String:
            if (case_sensitive)
            {
                if (strcmp(a->valuestring, b->valuestring) != 0)
                {
                    return 0;
                }
            }
            else
            {
                if (_stricmp(a->valuestring, b->valuestring) != 0)
                {
                    return 0;
                }
            }
            break;
        case cJSON_Array:
        case cJSON_Object:
        {
            cJSON *a_child = a->child;
            cJSON *b_child = b->child;
            while (a_child && b_child)
            {
                if (!cJSON_Compare(a_child, b_child, case_sensitive))
                {
                    return 0;
                }
                a_child = a_child->next;
                b_child = b_child->next;
            }
            if (a_child || b_child)
            {
                return 0;
            }
            break;
        }
        default:
            break;
    }

    if (a->string && b->string)
    {
        if (case_sensitive)
        {
            if (strcmp(a->string, b->string) != 0)
            {
                return 0;
            }
        }
        else
        {
            if (_stricmp(a->string, b->string) != 0)
            {
                return 0;
            }
        }
    }

    return 1;
}

CJSON_PUBLIC(void) cJSON_Minify(char *json)
{
    char *into = json;
    while (*json)
    {
        if (*json == ' ')
        {
            json++;
        }
        else if (*json == '\t')
        {
            json++;
        }
        else if (*json == '\r')
        {
            json++;
        }
        else if (*json == '\n')
        {
            json++;
        }
        else if (*json == '\"')
        {
            *into++ = *json++;
            while (*json && (*json != '\"'))
            {
                if (*json == '\\')
                {
                    *into++ = *json++;
                }
                *into++ = *json++;
            }
            *into++ = *json++;
        }
        else if (*json == '/' && json[1] == '/')
        {
            while (*json && *json != '\n')
            {
                json++;
            }
        }
        else if (*json == '/' && json[1] == '*')
        {
            json += 2;
            while (*json && !(*json == '*' && json[1] == '/'))
            {
                json++;
            }
            if (*json)
            {
                json += 2;
            }
        }
        else
        {
            *into++ = *json++;
        }
    }
    *into = '\0';
}

CJSON_PUBLIC(const char *) cJSON_GetErrorPtr(void)
{
    return global_ep;
}

CJSON_PUBLIC(char *) cJSON_GetStringValue(cJSON *item)
{
    if (!cJSON_IsString(item))
    {
        return NULL;
    }
    return item->valuestring;
}

CJSON_PUBLIC(double) cJSON_GetNumberValue(cJSON *item)
{
    if (!cJSON_IsNumber(item))
    {
        return (double)0;
    }
    return item->valuedouble;
}

CJSON_PUBLIC(int) cJSON_GetArraySize(const cJSON *array)
{
    cJSON *child = NULL;
    int size = 0;
    if (array == NULL)
    {
        return 0;
    }
    child = array->child;
    while (child != NULL)
    {
        size++;
        child = child->next;
    }
    return size;
}

CJSON_PUBLIC(cJSON *) cJSON_GetArrayItem(const cJSON *array, int index)
{
    cJSON *child = NULL;
    if (array == NULL)
    {
        return NULL;
    }
    child = array->child;
    while (index > 0 && child != NULL)
    {
        child = child->next;
        index--;
    }
    return child;
}

CJSON_PUBLIC(cJSON *) cJSON_GetObjectItem(const cJSON *object, const char *string)
{
    cJSON *child = NULL;
    if (object == NULL || string == NULL)
    {
        return NULL;
    }
    child = object->child;
    while (child != NULL)
    {
        if (child->string && strcmp(child->string, string) == 0)
        {
            return child;
        }
        child = child->next;
    }
    return NULL;
}

CJSON_PUBLIC(cJSON *) cJSON_GetObjectItemCaseSensitive(const cJSON *object, const char *string)
{
    cJSON *child = NULL;
    if (object == NULL || string == NULL)
    {
        return NULL;
    }
    child = object->child;
    while (child != NULL)
    {
        if (child->string && _stricmp(child->string, string) == 0)
        {
            return child;
        }
        child = child->next;
    }
    return NULL;
}

CJSON_PUBLIC(int) cJSON_HasObjectItem(const cJSON *object, const char *string)
{
    return cJSON_GetObjectItem(object, string) ? 1 : 0;
}

CJSON_PUBLIC(int) cJSON_IsInvalid(const cJSON *const item)
{
    if (item == NULL) return 0;
    return (item->type & 0xFF) == cJSON_Invalid;
}

CJSON_PUBLIC(int) cJSON_IsFalse(const cJSON *const item)
{
    if (item == NULL) return 0;
    return (item->type & 0xFF) == cJSON_False;
}

CJSON_PUBLIC(int) cJSON_IsTrue(const cJSON *const item)
{
    if (item == NULL) return 0;
    return (item->type & 0xFF) == cJSON_True;
}

CJSON_PUBLIC(int) cJSON_IsBool(const cJSON *const item)
{
    if (item == NULL) return 0;
    return ((item->type & 0xFF) == cJSON_True) || ((item->type & 0xFF) == cJSON_False);
}

CJSON_PUBLIC(int) cJSON_IsNull(const cJSON *const item)
{
    if (item == NULL) return 0;
    return (item->type & 0xFF) == cJSON_NULL;
}

CJSON_PUBLIC(int) cJSON_IsNumber(const cJSON *const item)
{
    if (item == NULL) return 0;
    return (item->type & 0xFF) == cJSON_Number;
}

CJSON_PUBLIC(int) cJSON_IsString(const cJSON *const item)
{
    if (item == NULL) return 0;
    return (item->type & 0xFF) == cJSON_String;
}

CJSON_PUBLIC(int) cJSON_IsArray(const cJSON *const item)
{
    if (item == NULL) return 0;
    return (item->type & 0xFF) == cJSON_Array;
}

CJSON_PUBLIC(int) cJSON_IsObject(const cJSON *const item)
{
    if (item == NULL) return 0;
    return (item->type & 0xFF) == cJSON_Object;
}

CJSON_PUBLIC(int) cJSON_IsRaw(const cJSON *const item)
{
    if (item == NULL) return 0;
    return (item->type & 0xFF) == cJSON_Raw;
}

/* Convenience functions */
CJSON_PUBLIC(cJSON *) cJSON_AddNullToObject(cJSON *const object, const char *const name)
{
    cJSON *null_item = cJSON_CreateNull();
    if (null_item == NULL) return NULL;
    cJSON_AddItemToObject(object, name, null_item);
    return null_item;
}

CJSON_PUBLIC(cJSON *) cJSON_AddTrueToObject(cJSON *const object, const char *const name)
{
    cJSON *true_item = cJSON_CreateTrue();
    if (true_item == NULL) return NULL;
    cJSON_AddItemToObject(object, name, true_item);
    return true_item;
}

CJSON_PUBLIC(cJSON *) cJSON_AddFalseToObject(cJSON *const object, const char *const name)
{
    cJSON *false_item = cJSON_CreateFalse();
    if (false_item == NULL) return NULL;
    cJSON_AddItemToObject(object, name, false_item);
    return false_item;
}

CJSON_PUBLIC(cJSON *) cJSON_AddBoolToObject(cJSON *const object, const char *const name, const int boolean)
{
    cJSON *bool_item = cJSON_CreateBool(boolean);
    if (bool_item == NULL) return NULL;
    cJSON_AddItemToObject(object, name, bool_item);
    return bool_item;
}

CJSON_PUBLIC(cJSON *) cJSON_AddNumberToObject(cJSON *const object, const char *const name, const double number)
{
    cJSON *num_item = cJSON_CreateNumber(number);
    if (num_item == NULL) return NULL;
    cJSON_AddItemToObject(object, name, num_item);
    return num_item;
}

CJSON_PUBLIC(cJSON *) cJSON_AddStringToObject(cJSON *const object, const char *const name, const char *const string)
{
    cJSON *str_item = cJSON_CreateString(string);
    if (str_item == NULL) return NULL;
    cJSON_AddItemToObject(object, name, str_item);
    return str_item;
}

CJSON_PUBLIC(cJSON *) cJSON_AddRawToObject(cJSON *const object, const char *const name, const char *const raw)
{
    cJSON *raw_item = cJSON_CreateRaw(raw);
    if (raw_item == NULL) return NULL;
    cJSON_AddItemToObject(object, name, raw_item);
    return raw_item;
}

CJSON_PUBLIC(cJSON *) cJSON_AddObjectToObject(cJSON *const object, const char *const name)
{
    cJSON *obj_item = cJSON_CreateObject();
    if (obj_item == NULL) return NULL;
    cJSON_AddItemToObject(object, name, obj_item);
    return obj_item;
}

CJSON_PUBLIC(cJSON *) cJSON_AddArrayToObject(cJSON *const object, const char *const name)
{
    cJSON *arr_item = cJSON_CreateArray();
    if (arr_item == NULL) return NULL;
    cJSON_AddItemToObject(object, name, arr_item);
    return arr_item;
}

CJSON_PUBLIC(void) cJSON_SetNumberHelper(cJSON *object, double number)
{
    object->valuedouble = number;
    if (number >= INT_MAX)
    {
        object->valueint = INT_MAX;
    }
    else if (number <= INT_MIN)
    {
        object->valueint = INT_MIN;
    }
    else
    {
        object->valueint = (int)number;
    }
    object->type = cJSON_Number;
}