// Public market reads only. No signing, credentials, price cache, or wallet APIs.
#include <curl/curl.h>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>

namespace {
constexpr size_t limit = 2 * 1024 * 1024;
std::once_flag init;
struct Connection {
    CURL* handle;
    curl_slist* headers;
    Connection() : handle(curl_easy_init()), headers(nullptr) {
        headers = curl_slist_append(headers, "Accept: application/json");
        headers = curl_slist_append(headers, "Cache-Control: no-cache");
    }
    ~Connection() { if (handle) curl_easy_cleanup(handle); curl_slist_free_all(headers); }
};
size_t receive(char* data, size_t size, size_t count, void* output) noexcept {
    try {
        auto& body = *static_cast<std::string*>(output);
        if (size && count > limit / size) return 0;
        const size_t bytes = size * count;
        if (bytes > limit - body.size()) return 0;
        body.append(data, bytes);
        return bytes;
    } catch (...) { return 0; }
}
}
extern "C" int rally_market_get(const char* url, char** output, size_t* length,
                                  long* status, double* milliseconds) noexcept {
    if (!url || !output || !length || !status || !milliseconds) return -1;
    *output = nullptr; *length = 0; *status = 0; *milliseconds = 0;
    try {
        const std::string address(url);
        if (address.rfind("https://api.geckoterminal.com/api/v2/", 0) != 0 &&
            address.rfind("https://api.coingecko.com/api/v3/", 0) != 0) return -2;
        if (address.size() > 1024 || address.find_first_of("\r\n") != std::string::npos) return -2;
        std::call_once(init, [] { curl_global_init(CURL_GLOBAL_DEFAULT); });
        thread_local Connection connection;
        CURL* handle = connection.handle;
        if (!handle) return -3;
        curl_easy_reset(handle);
        std::string body;
        curl_easy_setopt(handle, CURLOPT_URL, url);
        curl_easy_setopt(handle, CURLOPT_HTTPGET, 1L);
        curl_easy_setopt(handle, CURLOPT_HTTPHEADER, connection.headers);
        curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);
        curl_easy_setopt(handle, CURLOPT_PROTOCOLS_STR, "https");
        curl_easy_setopt(handle, CURLOPT_SSL_VERIFYPEER, 1L);
        curl_easy_setopt(handle, CURLOPT_SSL_VERIFYHOST, 2L);
        curl_easy_setopt(handle, CURLOPT_NOSIGNAL, 1L);
        curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT_MS, 1500L);
        curl_easy_setopt(handle, CURLOPT_TIMEOUT_MS, 4500L);
        curl_easy_setopt(handle, CURLOPT_ACCEPT_ENCODING, "");
        curl_easy_setopt(handle, CURLOPT_USERAGENT, "Rally-Market-Read/1.0");
        curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, receive);
        curl_easy_setopt(handle, CURLOPT_WRITEDATA, &body);
        auto result = curl_easy_perform(handle);
        double elapsed = 0;
        curl_easy_getinfo(handle, CURLINFO_TOTAL_TIME, &elapsed);
        curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, status);
        *milliseconds = elapsed * 1000;
        if (result != CURLE_OK) return static_cast<int>(result);
        auto* buffer = static_cast<char*>(std::malloc(body.size() + 1));
        if (!buffer) return -4;
        std::memcpy(buffer, body.data(), body.size()); buffer[body.size()] = 0;
        *output = buffer; *length = body.size(); return 0;
    } catch (...) { return -5; }
}
extern "C" void rally_market_free(void* buffer) noexcept { std::free(buffer); }
