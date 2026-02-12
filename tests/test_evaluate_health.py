"""
Contract test for health evaluation thresholds
"""

from agent.collectors.cpu import CpuResult
from agent.collectors.disk import DiskResult
from agent.collectors.memory import MemoryResult
from agent.evaluate import evaluate_health


def test_evaluate_health_signal_thresholds() -> None:
    """
    Critical thresholds yield UNHEALTHY and signal reasons
    """
    cpu = CpuResult(loadavg_1m=10.0, loadavg_5m=None, loadavg_15m=None, cpu_count_logical=4)
    memory = MemoryResult(mem_total_bytes=100, mem_available_bytes=5)
    disk = DiskResult(disk_total_bytes=100, disk_used_bytes=0, disk_free_bytes=4)

    health, reasons = evaluate_health(cpu, memory, disk, [])

    assert health == "UNHEALTHY"
    assert "signal:cpu_critical" in reasons
    assert "signal:mem_available_critical" in reasons
    assert "signal:disk_free_critical" in reasons
