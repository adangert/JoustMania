// Grafana Live Publisher
//
// Receives OTLP metrics from OTEL Collector and pushes acceleration metrics
// to Grafana Live for real-time WebSocket streaming to dashboards.
//
// Endpoints:
//   - POST /v1/metrics - OTLP HTTP metrics receiver (JSON format)
//   - GET /health - Health check
//
// Environment variables:
//   - PORT: HTTP server port (default: 4318)
//   - GRAFANA_URL: Grafana base URL (default: http://grafana:3000)
//   - GRAFANA_PUSH_PATH: Grafana Live push path (default: joustmania/accel)
package main

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

// Config holds service configuration
type Config struct {
	Port            string
	GrafanaURL      string
	GrafanaPushPath string
}

// AccelMessage represents acceleration data for Grafana Live
type AccelMessage struct {
	Time      int64   `json:"time"`      // Milliseconds since epoch
	Serial    string  `json:"serial"`    // Controller serial
	X         float64 `json:"x"`         // X acceleration
	Y         float64 `json:"y"`         // Y acceleration
	Z         float64 `json:"z"`         // Z acceleration
	Magnitude float64 `json:"magnitude"` // Total magnitude
}

// OTLP JSON structures (simplified)
type OTLPMetricsRequest struct {
	ResourceMetrics []ResourceMetrics `json:"resourceMetrics"`
}

type ResourceMetrics struct {
	ScopeMetrics []ScopeMetrics `json:"scopeMetrics"`
}

type ScopeMetrics struct {
	Metrics []Metric `json:"metrics"`
}

type Metric struct {
	Name  string `json:"name"`
	Gauge *Gauge `json:"gauge,omitempty"`
}

type Gauge struct {
	DataPoints []DataPoint `json:"dataPoints"`
}

type DataPoint struct {
	Attributes   []Attribute `json:"attributes"`
	TimeUnixNano string      `json:"timeUnixNano"`
	AsDouble     *float64    `json:"asDouble,omitempty"`
	AsInt        *int64      `json:"asInt,omitempty"`
}

type Attribute struct {
	Key   string         `json:"key"`
	Value AttributeValue `json:"value"`
}

type AttributeValue struct {
	StringValue string `json:"stringValue,omitempty"`
}

var (
	config       Config
	httpClient   *http.Client
	messageBuf   []AccelMessage
	messageMutex sync.Mutex
)

func main() {
	config = Config{
		Port:            getEnv("PORT", "4318"),
		GrafanaURL:      getEnv("GRAFANA_URL", "http://grafana:3000"),
		GrafanaPushPath: getEnv("GRAFANA_PUSH_PATH", "joustmania/accel"),
	}

	httpClient = &http.Client{
		Timeout: 5 * time.Second,
	}

	// Start background pusher
	go pushLoop()

	http.HandleFunc("/v1/metrics", handleMetrics)
	http.HandleFunc("/health", handleHealth)

	addr := ":" + config.Port
	log.Printf("Grafana Live Publisher starting on %s", addr)
	log.Printf("  Grafana URL: %s", config.GrafanaURL)
	log.Printf("  Push path: %s", config.GrafanaPushPath)

	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("ok"))
}

func handleMetrics(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Read body, handle gzip if needed
	var body []byte
	var err error

	if r.Header.Get("Content-Encoding") == "gzip" {
		reader, err := gzip.NewReader(r.Body)
		if err != nil {
			http.Error(w, "Failed to decompress", http.StatusBadRequest)
			return
		}
		defer reader.Close()
		body, err = io.ReadAll(reader)
		if err != nil {
			http.Error(w, "Failed to read body", http.StatusBadRequest)
			return
		}
	} else {
		body, err = io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "Failed to read body", http.StatusBadRequest)
			return
		}
	}
	defer r.Body.Close()

	// Parse OTLP metrics (JSON format)
	messages, err := parseOTLPJSON(body)
	if err != nil {
		log.Printf("Failed to parse OTLP: %v", err)
		// Still return OK to not block the collector
		w.WriteHeader(http.StatusOK)
		return
	}

	// Buffer messages for batch push
	if len(messages) > 0 {
		messageMutex.Lock()
		messageBuf = append(messageBuf, messages...)
		messageMutex.Unlock()
	}

	w.WriteHeader(http.StatusOK)
}

func parseOTLPJSON(data []byte) ([]AccelMessage, error) {
	var req OTLPMetricsRequest
	if err := json.Unmarshal(data, &req); err != nil {
		return nil, fmt.Errorf("json unmarshal: %w", err)
	}

	var messages []AccelMessage
	now := time.Now().UnixMilli()

	for _, rm := range req.ResourceMetrics {
		for _, sm := range rm.ScopeMetrics {
			for _, m := range sm.Metrics {
				// Filter for acceleration metrics
				if !isAccelMetric(m.Name) {
					continue
				}

				// Extract data points from gauge
				if m.Gauge != nil {
					msgs := extractAccelFromGauge(m.Name, m.Gauge, now)
					messages = append(messages, msgs...)
				}
			}
		}
	}

	return messages, nil
}

func isAccelMetric(name string) bool {
	// Match acceleration-related metrics
	return strings.Contains(name, "accel") ||
		strings.Contains(name, "acceleration") ||
		name == "controller_accel_magnitude" ||
		name == "controller_accel_x" ||
		name == "controller_accel_y" ||
		name == "controller_accel_z"
}

func extractAccelFromGauge(metricName string, gauge *Gauge, defaultTime int64) []AccelMessage {
	var messages []AccelMessage

	for _, dp := range gauge.DataPoints {
		msg := AccelMessage{
			Time: parseTime(dp.TimeUnixNano, defaultTime),
		}

		// Extract serial from attributes
		for _, attr := range dp.Attributes {
			if attr.Key == "serial" {
				msg.Serial = attr.Value.StringValue
			}
		}

		// Get the value
		var val float64
		if dp.AsDouble != nil {
			val = *dp.AsDouble
		} else if dp.AsInt != nil {
			val = float64(*dp.AsInt)
		}

		// Assign based on metric name
		switch {
		case strings.HasSuffix(metricName, "_x"):
			msg.X = val
		case strings.HasSuffix(metricName, "_y"):
			msg.Y = val
		case strings.HasSuffix(metricName, "_z"):
			msg.Z = val
		case strings.Contains(metricName, "magnitude"):
			msg.Magnitude = val
		default:
			// Single magnitude metric
			msg.Magnitude = val
		}

		if msg.Serial != "" {
			messages = append(messages, msg)
		}
	}

	return messages
}

func parseTime(timeStr string, defaultTime int64) int64 {
	if timeStr == "" {
		return defaultTime
	}
	// TimeUnixNano is a string in OTLP JSON
	var nanos int64
	fmt.Sscanf(timeStr, "%d", &nanos)
	if nanos > 0 {
		return nanos / 1e6 // Convert nanos to millis
	}
	return defaultTime
}

func pushLoop() {
	ticker := time.NewTicker(10 * time.Millisecond) // 100Hz push rate
	defer ticker.Stop()

	for range ticker.C {
		messageMutex.Lock()
		if len(messageBuf) == 0 {
			messageMutex.Unlock()
			continue
		}

		// Take all buffered messages
		toSend := messageBuf
		messageBuf = nil
		messageMutex.Unlock()

		// Aggregate by serial (combine X, Y, Z if separate)
		aggregated := aggregateBySerial(toSend)

		// Push to Grafana Live
		for _, msg := range aggregated {
			pushToGrafanaLive(msg)
		}
	}
}

func aggregateBySerial(messages []AccelMessage) []AccelMessage {
	bySerial := make(map[string]*AccelMessage)

	for _, m := range messages {
		existing, ok := bySerial[m.Serial]
		if !ok {
			msg := m
			bySerial[m.Serial] = &msg
			continue
		}

		// Merge values (take non-zero)
		if m.X != 0 {
			existing.X = m.X
		}
		if m.Y != 0 {
			existing.Y = m.Y
		}
		if m.Z != 0 {
			existing.Z = m.Z
		}
		if m.Magnitude != 0 {
			existing.Magnitude = m.Magnitude
		}
		if m.Time > existing.Time {
			existing.Time = m.Time
		}
	}

	// Calculate magnitude if not set
	result := make([]AccelMessage, 0, len(bySerial))
	for _, m := range bySerial {
		if m.Magnitude == 0 && (m.X != 0 || m.Y != 0 || m.Z != 0) {
			m.Magnitude = math.Sqrt(m.X*m.X + m.Y*m.Y + m.Z*m.Z)
		}
		result = append(result, *m)
	}

	return result
}

func pushToGrafanaLive(msg AccelMessage) {
	// Grafana Live push endpoint
	url := fmt.Sprintf("%s/api/live/push/%s", config.GrafanaURL, config.GrafanaPushPath)

	data, err := json.Marshal(msg)
	if err != nil {
		log.Printf("Failed to marshal message: %v", err)
		return
	}

	req, err := http.NewRequest("POST", url, bytes.NewReader(data))
	if err != nil {
		log.Printf("Failed to create request: %v", err)
		return
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := httpClient.Do(req)
	if err != nil {
		// Log at debug level - Grafana might not be ready
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		log.Printf("Grafana Live push failed: %d - %s", resp.StatusCode, string(body))
	}
}
