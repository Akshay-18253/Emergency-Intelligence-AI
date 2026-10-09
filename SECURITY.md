# Security Policy

## 1. Supported Versions

Security fixes and stability patches are applied to the latest releases on the `main` branch.

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| < 0.2.0 | :x:                |

---

## 2. Reporting a Vulnerability

If you discover a security vulnerability, algorithmic flaw that could cause denial-of-service, or data integrity issue in Emergency Intelligence AI, please report it responsibly:

1. **Do not open a public GitHub issue.**
2. Send an email to the project maintainers with the prefix `[SECURITY VULNERABILITY]` in the subject line.
3. Include:
   - Description of the vulnerability.
   - Minimal reproducible proof-of-concept (Python script or malformed GeoJSON/OSM dataset).
   - Expected vs actual behavior.
   - Potential impact on emergency routing systems.

Maintainers will acknowledge receipt within **48 hours** and provide a patch timeline.

---

## 3. Security Considerations for Emergency Routing

Emergency vehicle routing systems operate in safety-critical domains. This project implements defensive engineering practices to mitigate common routing vulnerabilities:

### 3.1 Zero-Dependency Supply Chain Hardening
The core library (`src/emergency_intelligence`) maintains **zero external runtime dependencies**. By relying exclusively on the audited Python Standard Library, the project eliminates supply-chain risks, malicious dependency injection, and transitive package vulnerabilities.

### 3.2 Defensive Input Validation
- **WGS 84 Coordinate Bounds:** Latitude and longitude are strictly validated to prevent coordinate wrap-around errors or out-of-bounds geographic anomalies (`validate_wgs84_coordinates`).
- **Graph Cost Non-Negativity:** Negative edge weights are rejected at initialization (`Edge.__post_init__`), guaranteeing termination and preventing infinite cycling in Dijkstra and A* routines.
- **Resource Exhaustion / Algorithmic DoS:** Priority queue min-heaps maintain cycle detection via closed/visited sets to ensure worst-case termination on cyclic or disconnected graphs.

### 3.3 Offline & Deterministic Execution
All routing computations are completely local and offline. The system performs zero unexpected outbound network calls during runtime, safeguarding responder location data from external telemetry interception.
