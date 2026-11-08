from decimal import Decimal
from typing import Any


def summarize(operation: str, values: list[Decimal], labels: list[dict[str, str]]) -> Any:
    mean = sum(values, Decimal(0)) / len(values)
    ordered = sorted(values)
    mid = len(values) // 2
    basic = {
        "sum": sum(values, Decimal(0)),
        "mean": mean,
        "min": min(values),
        "max": max(values),
        "median": ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2,
        "count": len(values),
    }
    if operation in basic:
        return basic[operation]
    if operation in {"difference", "percent_change", "ratio"}:
        return compare_numbers(operation, values)
    if operation == "stdev":
        return (sum(((v - mean) ** 2 for v in values), Decimal(0)) / len(values)).sqrt()
    if operation == "rank":
        return [
            {**labels[i], "value": str(values[i])}
            for i in sorted(range(len(values)), key=lambda i: values[i], reverse=True)
        ]
    if operation == "distribution":
        return {str(v): values.count(v) for v in sorted(set(values))}
    raise ValueError("Unknown statistical operation")


def compare_numbers(operation: str, values: list[Decimal]) -> Decimal:
    if len(values) != 2:
        raise ValueError("This operation requires exactly two values, in order")
    if operation == "difference":
        return values[1] - values[0]
    if values[0] == 0:
        raise ValueError("The baseline cannot be zero")
    if operation == "ratio":
        return values[1] / values[0]
    return (values[1] - values[0]) / abs(values[0]) * 100
