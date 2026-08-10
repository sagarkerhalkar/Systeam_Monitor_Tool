from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from statistics import median
from typing import Any
import json
import math
import os
import threading
import time

SERVICE = "sagar-monitor-ai-ops"
MODEL = "robust-anomaly-v1"
PORT = int(os.getenv("PORT", "8081"))

_COUNTER_LOCK = threading.Lock()
_COUNTERS = {"requests": 0, "analyses": 0, "errors": 0}

FEATURES: dict[str, dict[str, float | str]] = {
    "cpu_pct": {"weight": 1.0, "warn": 80.0, "critical": 95.0, "direction": "high"},
    "memory_pct": {"weight": 1.0, "warn": 85.0, "critical": 95.0, "direction": "high"},
    "disk_pct": {"weight": 0.9, "warn": 85.0, "critical": 95.0, "direction": "high"},
    "latency_ms": {"weight": 1.2, "warn": 120.0, "critical": 250.0, "direction": "high"},
    "packet_loss_pct": {"weight": 1.4, "warn": 2.0, "critical": 5.0, "direction": "high"},
}


def _finite_number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _robust_z(value: float, history: list[float]) -> float:
    if len(history) < 5:
        return 0.0
    center = median(history)
    deviations = [abs(item - center) for item in history]
    mad = median(deviations)
    scale = max(1e-9, 1.4826 * mad)
    if scale <= 1e-8:
        spread = max(max(history) - min(history), abs(center) * 0.05, 1.0)
        scale = spread
    return (value - center) / scale


def _ewma(history: list[float], alpha: float = 0.35) -> float | None:
    if not history:
        return None
    value = history[0]
    for sample in history[1:]:
        value = alpha * sample + (1.0 - alpha) * value
    return value


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics")
    history_rows = payload.get("history", [])
    if not isinstance(metrics, dict):
        raise ValueError("metrics must be an object")
    if not isinstance(history_rows, list):
        raise ValueError("history must be an array")

    anomalies: list[dict[str, Any]] = []
    weighted_scores: list[float] = []
    features_used = 0

    for name, rule in FEATURES.items():
        current = _finite_number(metrics.get(name))
        if current is None:
            continue
        features_used += 1
        history = [
            number
            for row in history_rows[-120:]
            if isinstance(row, dict)
            for number in [_finite_number(row.get(name))]
            if number is not None
        ]
        z = _robust_z(current, history)
        baseline = _ewma(history)
        warn = float(rule["warn"])
        critical = float(rule["critical"])
        weight = float(rule["weight"])

        z_risk = min(abs(z) / 5.0, 1.0)
        threshold_risk = 0.0
        if current >= critical:
            threshold_risk = 1.0
        elif current >= warn:
            threshold_risk = 0.65 + 0.35 * min((current - warn) / max(critical - warn, 1e-9), 1.0)
        risk = max(z_risk, threshold_risk)
        weighted_scores.append(risk * weight)

        if risk >= 0.55:
            reasons: list[str] = []
            if abs(z) >= 3.0:
                reasons.append(f"robust z-score {z:.2f} differs from recent baseline")
            if current >= warn:
                reasons.append(f"value {current:.2f} exceeds warning threshold {warn:.2f}")
            anomalies.append(
                {
                    "feature": name,
                    "value": round(current, 4),
                    "baseline_ewma": None if baseline is None else round(baseline, 4),
                    "robust_z": round(z, 4),
                    "risk": round(risk, 4),
                    "reasons": reasons or ["combined anomaly score exceeded threshold"],
                }
            )

    if not features_used:
        raise ValueError("no supported telemetry features were supplied")

    max_weight = max(float(item["weight"]) for item in FEATURES.values())
    raw = max(weighted_scores, default=0.0) / max_weight
    if len(weighted_scores) > 1:
        raw = min(1.0, 0.72 * raw + 0.28 * (sum(weighted_scores) / (len(weighted_scores) * max_weight)))
    score = round(raw * 100.0, 2)

    if score >= 80:
        health = "critical"
    elif score >= 60:
        health = "degraded"
    elif score >= 35:
        health = "watch"
    else:
        health = "healthy"

    recommendations: list[str] = []
    names = {item["feature"] for item in anomalies}
    if "packet_loss_pct" in names or "latency_ms" in names:
        recommendations.append("Inspect ISP/VPN path, packet loss and upstream latency before live classes.")
    if "cpu_pct" in names or "memory_pct" in names:
        recommendations.append("Inspect top processes and recent software changes on the affected machine.")
    if "disk_pct" in names:
        recommendations.append("Free disk capacity or expand storage before write-heavy workloads continue.")
    if not recommendations:
        recommendations.append("No immediate remediation required; continue telemetry observation.")

    return {
        "ok": True,
        "service": SERVICE,
        "model": MODEL,
        "machine_id": str(payload.get("machine_id") or "unknown")[:160],
        "anomaly_score": score,
        "health": health,
        "features_used": features_used,
        "anomalies": sorted(anomalies, key=lambda item: item["risk"], reverse=True),
        "recommendations": recommendations,
        "generated_at_epoch": int(time.time()),
    }


def _inc(name: str) -> None:
    with _COUNTER_LOCK:
        _COUNTERS[name] += 1


class Handler(BaseHTTPRequestHandler):
    server_version = "SagarMonitorAIOps"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        _inc("requests")
        if self.path == "/healthz":
            self._send_json(HTTPStatus.OK, {"ok": True, "service": SERVICE, "model": MODEL})
            return
        if self.path == "/metrics":
            with _COUNTER_LOCK:
                counters = dict(_COUNTERS)
            text = (
                "# TYPE sagar_ai_ops_requests_total counter\n"
                f"sagar_ai_ops_requests_total {counters['requests']}\n"
                "# TYPE sagar_ai_ops_analyses_total counter\n"
                f"sagar_ai_ops_analyses_total {counters['analyses']}\n"
                "# TYPE sagar_ai_ops_errors_total counter\n"
                f"sagar_ai_ops_errors_total {counters['errors']}\n"
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(text)))
            self.end_headers()
            self.wfile.write(text)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        _inc("requests")
        if self.path != "/v1/analyze":
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 512 * 1024:
                raise ValueError("request body must be between 1 byte and 512 KiB")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            result = analyze(payload)
            _inc("analyses")
            self._send_json(HTTPStatus.OK, result)
        except (ValueError, json.JSONDecodeError) as exc:
            _inc("errors")
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception:
            _inc("errors")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "internal_error"})


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(json.dumps({"service": SERVICE, "port": PORT, "model": MODEL}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
