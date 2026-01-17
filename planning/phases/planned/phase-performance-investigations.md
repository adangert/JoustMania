# Performance Investigations
Absolutely! Below is your **complete, production-quality prompt** with all key performance facts, code observations, and investigation asks, suitable for internal/external SRE, performance consulting, or expert AI assistance.

---

## 🚦 JoustMania dev-refactor: Comprehensive Performance Investigation Prompt

**Project Context**
I’m investigating performance issues in the refactored [JoustMania](https://github.com/WatchMeJoustMyFlags/JoustMania/tree/dev-refactor) (`dev-refactor` branch):
- **Architecture:** Microservices (7+ Python services), gRPC for communication, OpenTelemetry/Jaeger (tracing), Prometheus (metrics), and (soon) centralized logs in Loki
- **ControllerManager service** runs PS Move controller IO using [psmoveapi](https://github.com/thp/psmoveapi).
- After migrating from a monolithic, multiprocessing Python app, performance has suffered (higher latency and missed controller frames).

---

### 📊 **CRITICAL PERFORMANCE FACTS**
- **Controller polling (`psmoveapi`):**
  - *Old* PS Move controllers: ~88 Hz/message (2 frames/message, so ~176 Hz)
  - *New* PS Move controllers: ~790 Hz for `move.poll()` (buffers usually hold 90–160 frames!)
  - Original code (see `joust_test.py`) measures latency *per controller*:
    - Old buffer: 64–65 new messages
    - New buffer: 90–160 new messages
- **gRPC architecture change:**
  - Intended: 1000 Hz polling → 60 Hz gRPC streaming (per README)
  - Unclear:
    - If ControllerManager actually achieves this rate stably after refactor
    - If internal delays (e.g., `time.sleep(0.02)` and `time.sleep(0.05)` in `common.py:get_move()`) throttle performance
    - If concurrency is maintained (old: one process per controller via Python multiprocessing)
- **Symptoms:**
  - Latency between controller event and game response feels worse
  - Some controller states (“missed frames”) seem to be dropped under load
  - Possible bottlenecks in Python GIL, suboptimal polling, or streaming overhead

---

### ❓ **What I Need**

Please provide **step-by-step, actionable guidance** on **diagnosing and resolving** performance bottlenecks in this pipeline:
`psmoveapi polling` → `ControllerManager service` → `gRPC streaming` → `downstream services` (GameCoordinator, Menu, WebUI, etc).

**Specifically:**
1. **Pinpoint where performance is lost:**
  - Is it hardware polling, Python concurrency model (GIL/threads/processes), protocol buffer encoding, or network streaming?
2. **Controller polling:**
  - Optimal rate and threading/process model for Python+psmoveapi
  - Are hardcoded sleeps necessary or causing delays?
3. **gRPC streaming:**
  - How to efficiently stream high-frequency sensor data (batching, message size, backpressure, sampling, buffering)?
4. **Observability stack:**
  - Correlate Prometheus metrics (polling, latency, missed frames), Jaeger traces (slow RPCs), and (with Loki) log spikes/errors
  - Example queries to use in Loki and techniques for log/trace/metric correlation in Grafana
5. **Instrumentation/overhead:**
  - How much tracing and logging is too much? What patterns minimize overhead but maximize diagnosability?
6. **Validation:**
  - How to benchmark with reference to the *monolith's* “real” performance (as shown in `joust_test.py`)
  - What numbers should I expect, and which tests to automate?
7. **Practical suggestions:**
  - Ideal polling loop structure
  - Recommended concurrency pattern (async, threads, process-per-controller, etc)
  - Proto/gRPC usage optimizations

---

### 🔬 **Facts and Observed Patterns**

- **Common code highlights:**
  - `common.py:get_move()` uses unnecessary sleeps and creates new PSMove objects repeatedly.
  - `controller_util.py`, `controller_process.py`—heavy historical use of multiprocessing.
  - `piparty.py`, `Menu.remove_controller()`—complex, sometimes odd, resource cleanup.
- **Performance test script:** `joust_test.py`
  - Directly measures latency and buffer depth per controller.
- **psmoveapi**
  - Capable of ~800Hz polling **per controller** for new hardware—but downstream is often much slower.
- **gRPC streaming (per README):**
  - Supposed to “downsample” hardware poll to ~60Hz streams via `StreamControllerStates`
- **Observability:**
  - OpenTelemetry/Jaeger: Already sends traces with context propagation.
  - Prometheus: Can visualize polling, dropped update, and system resource histograms.
  - Loki: *Soon* will centralize all structured logs, with trace and span IDs attached.

---

### 🟩 **Sample Loki/Jaeger/Prometheus Correlation**

- **Loki LogQL** (for controller polling errors or slow ops):
  ```
  {container="controller_manager"} |= "error" | unwrap latency | latency > 100
  ```
  For a given trace/span:
  ```
  {container="controller_manager"} |~ "trace_id=XYZ"
  ```
- **Grafana Dashboards:**
  - Panel 1: Prometheus `controller_poll_rate` and `missed_controller_frame_total`
  - Panel 2: Jaeger traces, filter for `controller_manager` spans > 100ms
  - Panel 3: Loki logs filtered by trace ID, errant serials, or latency

---

### �� **INVESTIGATION CHECKLIST**

1. **Baseline actual polling and streaming rates** using Prometheus (`controller_poll_rate`, `grpc_stream_latency`). Compare to expected (~800Hz for new, ~176Hz for old).
2. **Audit code for delays and inefficiencies** (unnecessary `sleep`, excessive object re-creation, single-threaded bottlenecks, blocking calls).
3. **Check concurrency**: Confirm if you handle each controller on its own thread/process, and if you batch or serialize controller state delivery over gRPC.
4. **Trace spans:** Use Jaeger to find slowest streaming RPCs and longest polling cycles; record trace IDs.
5. **Deep dive logs:**
  - In Loki: Find all logs for a problematic span.
  - Look for error spikes, buffer overflow, or device disconnect messages.
6. **Cross-check with historic results:**
  - Use `joust_test.py` (or adapt it) on both old monolith & new microservice pipelines; compare per-controller latency/buffer stats!
7. **Test under load:**
  - In mock mode, rapidly scale up controller count, run a game (see README for scripts like `simulate_game.py`), watch for lags, frame loss, or CPU spikes.
8. **Validate observability overhead:**
  - Remove or sample noisy logs/tracing in the highest-frequency code paths and check for performance improvement.

---

### 🏁 **EXPECTED OUTCOME**

**A prioritized diagnosis:**
- Where is performance lost (hardware, Python runtime, gRPC, or system limits)?
- What config/code/infra changes will restore “close-to-monolith” or better performance for real hardware under real load?
- How can the observability stack (metrics, traces, logs) help fleeting issues *now and in the future*?
- Clear list of Loki/Jaeger/Prometheus queries and UI dashboards to share with the team

---

**Repository for Reference:**
https://github.com/WatchMeJoustMyFlags/JoustMania/tree/dev-refactor
(ControllerManager: `services/controller_manager/`, all proto schemas in `/proto/`)

---

**Please answer with detailed step-by-step diagnostics, code/infra recommendations, and precise queries for the Loki/Jaeger/Prometheus stack. Benchmark improvement advice vs. the old monolith is especially welcome.**

---


