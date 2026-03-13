"""In-process request metrics collector."""

request_metrics = {
    "total_requests": 0,
    "total_errors": 0,
    "total_latency_ms": 0,
}


def record_request(latency_ms: float, error: bool = False) -> None:
    request_metrics["total_requests"] += 1
    request_metrics["total_latency_ms"] += latency_ms
    if error:
        request_metrics["total_errors"] += 1


def get_metrics() -> dict:
    avg_latency = 0.0
    if request_metrics["total_requests"] > 0:
        avg_latency = request_metrics["total_latency_ms"] / request_metrics["total_requests"]
    return {
        "total_requests": request_metrics["total_requests"],
        "total_errors": request_metrics["total_errors"],
        "average_latency_ms": avg_latency,
    }
