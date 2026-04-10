import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("modbus")


class Bus:
    def __init__(self):
        self.nodes: dict[str, Any] = {}
        self.transaction_log: list[dict] = []

    def register_node(self, node_id: str, node_instance: Any):
        self.nodes[node_id] = node_instance

    def read_sensor(self, node_id: str, sensor_name: str) -> Any:
        """Read a sensor value from a registered node."""
        node = self.nodes.get(node_id)
        if node is None:
            logger.warning(f"[MODBUS] Read failed: node {node_id} not registered")
            return None

        if hasattr(node, sensor_name):
            value = getattr(node, sensor_name)
            self._log_transaction(node_id, None, "READ", sensor_name, value)
            return value
        else:
            logger.warning(f"[MODBUS] Read failed: {node_id} has no sensor '{sensor_name}'")
            return None

    def write_command(self, node_id: str, command: str, value: Any) -> bool:
        """Write a command to a registered node."""
        node = self.nodes.get(node_id)
        if node is None:
            logger.warning(f"[MODBUS] Write failed: node {node_id} not registered")
            return False

        method_name = command
        if hasattr(node, method_name):
            method = getattr(node, method_name)
            if callable(method):
                method(value) if value is not None else method()
                self._log_transaction(node_id, None, "WRITE", command, value)
                return True
        logger.warning(f"[MODBUS] Write failed: {node_id} has no command '{command}'")
        return False

    def _log_transaction(self, from_node: str, to_node: str | None, func_code: str, address: str, value: Any):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "from": from_node,
            "to": to_node,
            "func_code": func_code,
            "address": address,
            "value": value,
        }
        self.transaction_log.append(entry)
        # Keep log bounded
        if len(self.transaction_log) > 1000:
            self.transaction_log = self.transaction_log[-500:]
        logger.debug(f"[MODBUS] {func_code} {from_node}/{address} = {value}")
