# Phase 12 Implementation Plan - Dependency Updates

**Date:** 2026-01-10
**Status:** 📋 Planning
**Goal:** Update infrastructure and application dependencies to latest stable versions

---

## Context

Current dependencies are pinned to `:latest` or unspecified versions, which can lead to:
- Reproducibility issues (different builds get different versions)
- Security vulnerabilities (missing security patches)
- Missing performance improvements
- Incompatibility surprises

Phase 12 systematically updates all dependencies to latest stable versions with explicit version pinning.

---

## Current Versions

### Infrastructure (docker-compose.yml)

| Service | Current | Notes |
|---------|---------|-------|
| Jaeger | `jaegertracing/all-in-one:latest` | Unpinned |
| OTel Collector | `otel/opentelemetry-collector-contrib:latest` | Unpinned |
| Redis | `redis:7-alpine` | Major version pinned |

### Application Base Images

| Component | Current | Notes |
|-----------|---------|-------|
| Python | `python:3.11-slim` | Minor version pinned |
| uv | Installed via pip (unpinned) | No version specified |

### Python Packages (pyproject.toml)

Most packages unpinned or using `>=` constraints.

---

## Target Versions

### Infrastructure

| Service | Target | Reason |
|---------|--------|--------|
| Jaeger | `jaegertracing/all-in-one:2.0.0` | Latest stable v2 (improved performance) |
| OTel Collector | `otel/opentelemetry-collector-contrib:0.110.0` | Latest stable |
| Redis | `redis:7.4-alpine` | Latest 7.x patch version |

### Application

| Component | Target | Reason |
|-----------|--------|--------|
| Python | `python:3.11-slim` | Keep 3.11 (stable, tested) |
| uv | `0.5.11` | Latest stable |

### Python Packages

Update to latest compatible versions:
- grpcio, grpcio-tools
- opentelemetry-* packages
- Flask
- PyYAML
- pytest

---

## Implementation Tasks

### Task 1: Create Phase 12 Implementation Plan

Document current versions, target versions, and update strategy.

**Commit:** `docs: Add Phase 12 implementation plan`

---

### Task 2: Update Jaeger to v2

**File:** `docker-compose.yml`

**Change:**
```yaml
# Before
jaeger:
  image: jaegertracing/all-in-one:latest

# After
jaeger:
  image: jaegertracing/all-in-one:2.0.0
```

**Verification:**
- Check Jaeger UI still accessible
- Verify traces still appear
- Test all services send traces

**Commit:** `chore: Upgrade Jaeger to v2.0.0`

---

### Task 3: Pin OpenTelemetry Collector Version

**File:** `docker-compose.yml`

**Change:**
```yaml
# Before
otel-collector:
  image: otel/opentelemetry-collector-contrib:latest

# After
otel-collector:
  image: otel/opentelemetry-collector-contrib:0.110.0
```

**Verification:**
- Check collector health endpoint
- Verify trace collection
- Check Prometheus metrics export

**Commit:** `chore: Pin OpenTelemetry Collector to v0.110.0`

---

### Task 4: Update Redis Version

**File:** `docker-compose.yml`

**Change:**
```yaml
# Before
redis:
  image: redis:7-alpine

# After
redis:
  image: redis:7.4-alpine
```

**Verification:**
- Check Redis health
- Verify connection from services (if used)

**Commit:** `chore: Update Redis to 7.4-alpine`

---

### Task 5: Pin uv Version in Dockerfiles

**Files:** All service Dockerfiles

**Change:**
```dockerfile
# Before
RUN pip install --no-cache-dir uv

# After
RUN pip install --no-cache-dir uv==0.5.11
```

**Services to update:**
- services/settings/Dockerfile
- services/controller_manager/Dockerfile
- services/game_coordinator/Dockerfile
- services/menu/Dockerfile
- services/supervisor/Dockerfile
- services/webui/Dockerfile
- services/audio/Dockerfile

**Commit:** `chore: Pin uv to v0.5.11 in all Dockerfiles`

---

### Task 6: Update Python Package Dependencies

**Strategy:** Update to latest compatible versions while maintaining compatibility.

**Files:** All `pyproject.toml` files

**Key packages to update:**

1. **gRPC packages**
   ```toml
   grpcio = ">=1.70.0"
   grpcio-tools = ">=1.70.0"
   ```

2. **OpenTelemetry packages**
   ```toml
   opentelemetry-api = ">=1.28.0"
   opentelemetry-sdk = ">=1.28.0"
   opentelemetry-instrumentation-grpc = ">=0.49b0"
   opentelemetry-exporter-otlp = ">=1.28.0"
   ```

3. **Web frameworks**
   ```toml
   flask = ">=3.0.0"
   ```

4. **Other packages**
   ```toml
   pyyaml = ">=6.0"
   pytest = ">=8.0.0"
   ```

**Approach:**
- Update one service at a time
- Test after each update
- Use `uv lock` to lock dependencies

**Commit (per service):** `chore: Update Python dependencies in <service>`

---

### Task 7: Update Root pyproject.toml

**File:** `pyproject.toml` (workspace root)

Update dependencies for shared packages and development tools.

**Commit:** `chore: Update workspace dependencies in root pyproject.toml`

---

### Task 8: Rebuild and Test All Services

**Actions:**
1. Rebuild all Docker images
2. Start full stack
3. Verify all services start
4. Test gRPC APIs with grpcurl
5. Check Jaeger UI for traces
6. Run test suite
7. Verify integration

**Verification checklist:**
- [ ] All services build successfully
- [ ] All services start without errors
- [ ] gRPC health checks pass
- [ ] Traces appear in Jaeger v2 UI
- [ ] Prometheus metrics exported
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] No breaking changes detected

**Commit:** `test: Verify all services after dependency updates`

---

### Task 9: Update Documentation

**Files to update:**
- README.md (if version references exist)
- ARCHITECTURE.md (update version table)
- docker-compose.yml comments

**Commit:** `docs: Update version references in documentation`

---

### Task 10: Create Completion Document

**File:** `PHASE_12_COMPLETED.md`

Document:
- All updated dependencies (before/after)
- Verification results
- Any breaking changes
- Performance improvements observed
- Migration notes

**Commit:** `docs: Add Phase 12 completion summary`

---

## Version Matrix

### Before Phase 12

| Component | Version |
|-----------|---------|
| Jaeger | `latest` (unknown) |
| OTel Collector | `latest` (unknown) |
| Redis | `7-alpine` |
| Python | `3.11-slim` |
| uv | unpinned |
| grpcio | unpinned |
| opentelemetry-* | unpinned |

### After Phase 12

| Component | Version |
|-----------|---------|
| Jaeger | `2.0.0` |
| OTel Collector | `0.110.0` |
| Redis | `7.4-alpine` |
| Python | `3.11-slim` |
| uv | `0.5.11` |
| grpcio | `>=1.70.0` |
| opentelemetry-* | `>=1.28.0` |

---

## Testing Strategy

### Infrastructure Testing

1. **Jaeger v2**
   - UI accessible at :16686
   - Traces from all services appear
   - Query functionality works
   - No UI breaking changes

2. **OTel Collector**
   - Health check responds
   - Receives traces from services
   - Exports to Jaeger
   - Exports Prometheus metrics

3. **Redis**
   - Service starts
   - Health check passes
   - (Future: Test pub/sub if used)

### Application Testing

1. **Build Tests**
   - All services build without errors
   - No dependency conflicts
   - Image sizes reasonable

2. **Runtime Tests**
   - All services start
   - gRPC servers respond
   - No startup errors
   - Health checks pass

3. **Integration Tests**
   - Service-to-service communication works
   - gRPC calls succeed
   - Traces propagate correctly
   - Settings persistence works

4. **Unit Tests**
   - Run test suite: `scripts/testing/run_tests.sh`
   - All tests pass
   - No regressions

---

## Risk Assessment

### Low Risk

- **Redis update** - Patch version update, backward compatible
- **uv pinning** - Already working, just pinning version
- **Python packages** - Using `>=` constraints, not hard pins

### Medium Risk

- **OTel Collector** - New version may have config changes
- **Jaeger v2** - Major version upgrade, UI changes possible

### Mitigation

- Test each change individually
- Verify after each commit
- Keep git history clean for easy rollback
- Document any breaking changes

---

## Python 3.12/3.13 Decision

**Question:** Should we upgrade from Python 3.11 to 3.12 or 3.13?

**Analysis:**

**Pros (3.12):**
- Performance improvements (5-10% faster)
- Better error messages
- Type hints improvements
- Stable (released Oct 2023)

**Pros (3.13):**
- Even better performance
- More features
- Cutting edge

**Cons (both):**
- Need to test all dependencies
- Potential compatibility issues
- Rebuild all images
- More changes = more risk

**Decision for Phase 12:** **Stay on Python 3.11**

**Reasons:**
1. 3.11 is stable and well-tested
2. All dependencies confirmed compatible
3. Keep Phase 12 focused on version pinning
4. Python upgrade can be separate phase (12b)
5. Minimize risk

**Future:** Can upgrade to 3.12 in Phase 12b after Phase 12 successful.

---

## Success Criteria

- ✅ All infrastructure versions pinned (no `:latest`)
- ✅ uv version pinned in all Dockerfiles
- ✅ Python packages updated to latest compatible versions
- ✅ All services build successfully
- ✅ All services start without errors
- ✅ Traces appear in Jaeger v2
- ✅ Test suite passes
- ✅ No regressions detected
- ✅ Documentation updated
- ✅ Reproducible builds (same versions each time)

---

## Git Commits

Planned commits (~10-12):
1. Create implementation plan
2. Update Jaeger to v2
3. Pin OTel Collector version
4. Update Redis version
5. Pin uv in all Dockerfiles (may be single commit or per-service)
6-7. Update Python dependencies (may be batched or per-service)
8. Test services after updates
9. Update documentation
10. Create completion summary

**Total:** ~10 commits

---

## Timeline

**Estimated effort:** 1-2 hours
- Planning: 15 min ✅
- Updates: 30 min
- Testing: 30 min
- Documentation: 15 min

---

## References

- [Jaeger v2 Release Notes](https://www.jaegertracing.io/)
- [OTel Collector Releases](https://github.com/open-telemetry/opentelemetry-collector-contrib/releases)
- [Redis Release Notes](https://redis.io/download)
- [uv Releases](https://github.com/astral-sh/uv/releases)
- [Python Release Schedule](https://peps.python.org/pep-0596/)

---

## Next Steps After Phase 12

- **Phase 12b (optional):** Python 3.12 upgrade
- **Phase 13:** Game modes refactoring (gRPC-based)
- **Phase 11b (optional):** Extended documentation
