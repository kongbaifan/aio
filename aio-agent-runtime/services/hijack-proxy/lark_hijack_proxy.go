package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	maxFailureResponseBodyLogBytes = 4096
	maxRequestBodyLogBytes         = 4096
	truncatedLogSuffix             = " [truncated]"
)

const (
	defaultListenAddr            = "127.0.0.2:443"
	defaultHTTPListenPort        = "80"
	defaultMCPProxyURL           = "https://mcp-vm.bytedance.net/vm/hijack"
	defaultRequestTimeoutSeconds = 120

	certPath = "/hijack_proxy/output/cert.pem"
	keyPath  = "/hijack_proxy/output/key.pem"

	hopHeader                = "X-Hijack-Proxy-Hop"
	sessionIDHeaderKey       = "X-Hijack-Proxy-SessionID"
	requestTimeoutHeaderKey  = "X-Hijack-Proxy-RequestTimeoutSec"
	headerWhitelistHeaderKey = "X-Hijack-Proxy-Original-Header-Whitelist"

	listenAddrEnvKey          = "HIJACK_PROXY_LISTEN_ADDR"
	targetURLEnvKey           = "HIJACK_PROXY_TARGET_URL"
	requestTimeoutSecEnvKey   = "HIJACK_PROXY_REQUEST_TIMEOUT_SECONDS"
	logForwardedHeadersEnvKey = "HIJACK_PROXY_LOG_FORWARDED_HEADERS"
	ppeEnvKey                 = "PPE_ENV"
	clusterEnvKey             = "CLUSTER_ENV"
	sessionEnvKey             = "SESSION_ID"
)

type hijackProxyConfig struct {
	ListenAddr          string
	MCPProxyURL         string
	RequestTimeout      time.Duration
	LogForwardedHeaders bool
	PPEEnv              string
	ClusterEnv          string
	SessionID           string
	Target              *url.URL
}

func getEnvOrDefault(key, defaultValue string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return defaultValue
	}

	return value
}

func getRequestTimeout() (time.Duration, error) {
	value := strings.TrimSpace(os.Getenv(requestTimeoutSecEnvKey))
	if value == "" {
		return time.Duration(defaultRequestTimeoutSeconds) * time.Second, nil
	}

	seconds, err := strconv.Atoi(value)
	if err != nil || seconds <= 0 {
		return 0, fmt.Errorf("invalid %s=%q, expected positive integer seconds", requestTimeoutSecEnvKey, value)
	}

	return time.Duration(seconds) * time.Second, nil
}

func shouldLogForwardedHeaders() bool {
	return strings.TrimSpace(os.Getenv(logForwardedHeadersEnvKey)) == "1"
}

func loadHijackProxyConfig() (*hijackProxyConfig, error) {
	listenAddr := getEnvOrDefault(listenAddrEnvKey, defaultListenAddr)
	if _, _, err := net.SplitHostPort(listenAddr); err != nil {
		return nil, fmt.Errorf("invalid %s=%q: %w", listenAddrEnvKey, listenAddr, err)
	}

	mcpProxyURL := getEnvOrDefault(targetURLEnvKey, defaultMCPProxyURL)
	target, err := url.Parse(mcpProxyURL)
	if err != nil || target.Scheme == "" || target.Host == "" {
		return nil, fmt.Errorf("invalid %s=%q", targetURLEnvKey, mcpProxyURL)
	}

	requestTimeout, err := getRequestTimeout()
	if err != nil {
		return nil, err
	}

	return &hijackProxyConfig{
		ListenAddr:          listenAddr,
		MCPProxyURL:         mcpProxyURL,
		RequestTimeout:      requestTimeout,
		LogForwardedHeaders: shouldLogForwardedHeaders(),
		PPEEnv:              strings.TrimSpace(os.Getenv(ppeEnvKey)),
		ClusterEnv:          strings.TrimSpace(os.Getenv(clusterEnvKey)),
		SessionID:           strings.TrimSpace(os.Getenv(sessionEnvKey)),
		Target:              target,
	}, nil
}

func snapshotRequestBody(req *http.Request) ([]byte, error) {
	if req == nil || req.Body == nil {
		return nil, nil
	}

	bodyBytes, err := io.ReadAll(req.Body)
	if err != nil {
		return nil, err
	}
	resetRequestBody(req, bodyBytes)
	return bodyBytes, nil
}

func resetRequestBody(req *http.Request, bodyBytes []byte) {
	if req == nil {
		return
	}
	req.Body = io.NopCloser(bytes.NewReader(bodyBytes))
	req.GetBody = func() (io.ReadCloser, error) {
		return io.NopCloser(bytes.NewReader(bodyBytes)), nil
	}
	if bodyBytes == nil {
		req.ContentLength = 0
		return
	}
	req.ContentLength = int64(len(bodyBytes))
}

func formatBodyForLog(bodyBytes []byte, limit int) string {
	if len(bodyBytes) == 0 {
		return ""
	}
	if limit > 0 && len(bodyBytes) > limit {
		return string(bodyBytes[:limit]) + truncatedLogSuffix
	}
	return string(bodyBytes)
}

func buildOriginalRequestURL(req *http.Request) string {
	if req == nil {
		return ""
	}
	target := &url.URL{
		Scheme:   originalRequestScheme(req),
		Host:     req.Host,
		Path:     req.URL.Path,
		RawPath:  req.URL.RawPath,
		RawQuery: req.URL.RawQuery,
	}
	if target.Path == "" {
		target.Path = "/"
	}
	return target.String()
}

func originalRequestScheme(req *http.Request) string {
	if req != nil && req.TLS != nil {
		return "https"
	}
	return "http"
}

func buildOriginalRequestDebugCurl(req *http.Request, bodyBytes []byte) string {
	if req == nil {
		return "curl"
	}

	parts := []string{"curl", "-X", shellQuote(req.Method)}
	if req.Host != "" {
		parts = append(parts, "-H", shellQuote("Host: "+req.Host))
	}

	keys := make([]string, 0, len(req.Header))
	for key := range req.Header {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		for _, value := range req.Header.Values(key) {
			parts = append(parts, "-H", shellQuote(key+": "+value))
		}
	}
	if len(bodyBytes) > 0 {
		parts = append(parts, "--data-raw", shellQuote(string(bodyBytes)))
	}
	parts = append(parts, shellQuote(buildOriginalRequestURL(req)))
	return strings.Join(parts, " ")
}

func buildOriginalHeaderWhitelist(header http.Header) string {
	if len(header) == 0 {
		return ""
	}

	keys := make([]string, 0, len(header))
	seen := make(map[string]struct{}, len(header))
	for key := range header {
		canonicalKey := http.CanonicalHeaderKey(strings.TrimSpace(key))
		if canonicalKey == "" {
			continue
		}
		if _, ok := seen[canonicalKey]; ok {
			continue
		}
		seen[canonicalKey] = struct{}{}
		keys = append(keys, canonicalKey)
	}
	sort.Strings(keys)
	return strings.Join(keys, ",")
}

func shellQuote(value string) string {
	if value == "" {
		return "''"
	}
	return "'" + strings.ReplaceAll(value, "'", `'"'"'`) + "'"
}

func applyHijackRequestHeaders(req *http.Request, cfg *hijackProxyConfig, originalHost, originalPath, originalRequestURI, headerWhitelist string) {
	req.Header.Set("X-Original-Host", originalHost)
	req.Header.Set("X-Original-Path", originalPath)
	req.Header.Set("X-Original-Request-Uri", originalRequestURI)
	req.Header.Set(hopHeader, "1")
	req.Header.Set(requestTimeoutHeaderKey, strconv.FormatInt(int64(cfg.RequestTimeout/time.Second), 10))
	if headerWhitelist != "" {
		req.Header.Set(headerWhitelistHeaderKey, headerWhitelist)
	}
	if cfg.PPEEnv != "" {
		req.Header.Set("X-Tt-Env", cfg.PPEEnv)
		req.Header.Set("X-Use-Ppe", "1")
	}
	if cfg.ClusterEnv != "" {
		req.Header.Set("X-Original-Cluster", cfg.ClusterEnv)
	}
	if cfg.SessionID != "" {
		req.Header.Set(sessionIDHeaderKey, cfg.SessionID)
	}
}

func snapshotResponseBodyForLog(resp *http.Response) (string, error) {
	if resp == nil || resp.Body == nil {
		return "", nil
	}

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	resp.Body = io.NopCloser(bytes.NewReader(bodyBytes))

	if len(bodyBytes) == 0 {
		return "", nil
	}

	if len(bodyBytes) > maxFailureResponseBodyLogBytes {
		return string(bodyBytes[:maxFailureResponseBodyLogBytes]) + truncatedLogSuffix, nil
	}

	return string(bodyBytes), nil
}

type timeoutRoundTripper struct {
	base    http.RoundTripper
	timeout time.Duration
}

type cancelOnCloseReadCloser struct {
	io.ReadCloser
	cancel context.CancelFunc
}

func (c *cancelOnCloseReadCloser) Close() error {
	err := c.ReadCloser.Close()
	c.cancel()
	return err
}

func (t *timeoutRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	ctx, cancel := context.WithTimeout(req.Context(), t.timeout)
	resp, err := t.base.RoundTrip(req.Clone(ctx))
	if err != nil {
		cancel()
		return nil, err
	}

	resp.Body = &cancelOnCloseReadCloser{
		ReadCloser: resp.Body,
		cancel:     cancel,
	}
	return resp, nil
}

func getHTTPRedirectListenAddr(httpsListenAddr string) (string, error) {
	host, _, err := net.SplitHostPort(httpsListenAddr)
	if err != nil {
		return "", fmt.Errorf("invalid https listen addr %q: %w", httpsListenAddr, err)
	}

	return net.JoinHostPort(host, defaultHTTPListenPort), nil
}

func buildHTTPRedirectURL(req *http.Request) string {
	target := &url.URL{
		Scheme:   "https",
		Host:     req.Host,
		Path:     req.URL.Path,
		RawPath:  req.URL.RawPath,
		RawQuery: req.URL.RawQuery,
	}
	if target.Path == "" {
		target.Path = "/"
	}

	return target.String()
}

func newHTTPRedirectHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		target := buildHTTPRedirectURL(req)
		log.Printf(
			"↪️ hijack proxy redirect http request method=%s host=%s path=%s target=%s remote_addr=%s",
			req.Method,
			req.Host,
			req.URL.Path,
			target,
			req.RemoteAddr,
		)
		http.Redirect(w, req, target, http.StatusMovedPermanently)
	})
}

func main() {
	cfg, err := loadHijackProxyConfig()
	if err != nil {
		log.Fatalf("init hijack proxy config failed: %v", err)
		return
	}

	proxy := httputil.NewSingleHostReverseProxy(cfg.Target)
	proxy.Transport = &timeoutRoundTripper{
		base:    http.DefaultTransport,
		timeout: cfg.RequestTimeout,
	}

	originalDirector := proxy.Director
	proxy.Director = func(req *http.Request) {
		originalHost := req.Host
		originalPath := req.URL.EscapedPath()
		if originalPath == "" {
			originalPath = req.URL.Path
		}
		originalRequestURI := req.RequestURI
		if (originalPath == "" || originalPath == "/") && originalRequestURI != "" && originalRequestURI != "/" {
			if parsedURI, parseErr := url.ParseRequestURI(originalRequestURI); parseErr == nil && parsedURI.Path != "" {
				originalPath = parsedURI.Path
			}
		}
		originalQuery := req.URL.RawQuery
		bodyBytes, bodyErr := snapshotRequestBody(req)
		if bodyErr != nil {
			log.Printf("read original request body failed: %v", bodyErr)
		}
		headerWhitelist := buildOriginalHeaderWhitelist(req.Header)
		contentLength := strconv.FormatInt(req.ContentLength, 10)

		log.Printf(
			"➡️ hijack request method=%s host=%s path=%s request_uri=%q query=%q remote_addr=%s ua=%q content_length=%s session_id=%q",
			req.Method,
			originalHost,
			originalPath,
			originalRequestURI,
			originalQuery,
			req.RemoteAddr,
			req.UserAgent(),
			contentLength,
			cfg.SessionID,
		)
		if cfg.LogForwardedHeaders {
			log.Printf(
				"🧾 hijack original request body method=%s host=%s path=%s body=%q body_read_err=%v",
				req.Method,
				originalHost,
				originalPath,
				formatBodyForLog(bodyBytes, maxRequestBodyLogBytes),
				bodyErr,
			)
			log.Printf(
				"🧪 hijack original request curl method=%s host=%s path=%s curl=%s",
				req.Method,
				originalHost,
				originalPath,
				buildOriginalRequestDebugCurl(req, bodyBytes),
			)
		}

		originalDirector(req)
		// 强制转发到 vm_proxy 固定入口
		req.URL.Scheme = cfg.Target.Scheme
		req.URL.Host = cfg.Target.Host
		req.URL.Path = cfg.Target.Path
		req.Host = cfg.Target.Host
		// 传递原始飞书域名和路径给 vm_proxy
		applyHijackRequestHeaders(req, cfg, originalHost, originalPath, originalRequestURI, headerWhitelist)
	}

	proxy.ModifyResponse = func(resp *http.Response) error {
		logID := resp.Header.Get("X-Tt-Logid")
		sessionID := resp.Request.Header.Get(sessionIDHeaderKey)
		if resp.StatusCode >= 200 && resp.StatusCode < 400 {
			log.Printf(
				"✅ hijack response success method=%s status=%d target=%s original_host=%s original_path=%s logid=%q session_id=%q",
				resp.Request.Method,
				resp.StatusCode,
				resp.Request.URL.String(),
				resp.Request.Header.Get("X-Original-Host"),
				resp.Request.Header.Get("X-Original-Path"),
				logID,
				sessionID,
			)
			return nil
		}

		responseBody, bodyErr := snapshotResponseBodyForLog(resp)
		log.Printf(
			"❌ hijack response failure method=%s status=%d target=%s original_host=%s original_path=%s logid=%q session_id=%q response_body=%q response_body_read_err=%v",
			resp.Request.Method,
			resp.StatusCode,
			resp.Request.URL.String(),
			resp.Request.Header.Get("X-Original-Host"),
			resp.Request.Header.Get("X-Original-Path"),
			logID,
			sessionID,
			responseBody,
			bodyErr,
		)
		return nil
	}

	proxy.ErrorHandler = func(w http.ResponseWriter, req *http.Request, err error) {
		log.Printf(
			"🚨 hijack proxy upstream error method=%s host=%s path=%s remote_addr=%s session_id=%q err=%v",
			req.Method,
			req.Host,
			req.URL.Path,
			req.RemoteAddr,
			req.Header.Get(sessionIDHeaderKey),
			err,
		)
		http.Error(w, "bad gateway", http.StatusBadGateway)
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if req.Header.Get(hopHeader) != "" {
			log.Printf(
				"🚫 hijack proxy loop detected method=%s host=%s path=%s request_uri=%q remote_addr=%s",
				req.Method,
				req.Host,
				req.URL.Path,
				req.RequestURI,
				req.RemoteAddr,
			)
			http.Error(w, "hijack proxy loop detected", http.StatusBadGateway)
			return
		}

		proxy.ServeHTTP(w, req)
	})

	httpRedirectListenAddr, err := getHTTPRedirectListenAddr(cfg.ListenAddr)
	if err != nil {
		log.Fatalf("build http redirect listen addr failed: %v", err)
		return
	}

	go func() {
		log.Printf("✅ hijack proxy http redirect start: %s -> https://<original-host>", httpRedirectListenAddr)
		if serveErr := http.ListenAndServe(httpRedirectListenAddr, newHTTPRedirectHandler()); serveErr != nil {
			log.Fatalf("start hijack proxy http redirect failed: %v", serveErr)
		}
	}()

	if cfg.PPEEnv != "" {
		log.Printf("✅ hijack proxy start: %s → %s, request_timeout=%s, ppe_env=%s", cfg.ListenAddr, cfg.MCPProxyURL, cfg.RequestTimeout, cfg.PPEEnv)
	} else {
		log.Printf("✅ hijack proxy start: %s → %s, request_timeout=%s", cfg.ListenAddr, cfg.MCPProxyURL, cfg.RequestTimeout)
	}
	log.Fatal(http.ListenAndServeTLS(cfg.ListenAddr, certPath, keyPath, handler))
}
