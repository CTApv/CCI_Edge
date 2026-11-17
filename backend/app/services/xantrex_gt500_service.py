"""Passive, bounded diagnostics for the European PVGT gateway only."""
from app.catalog.xantrex_gt500_catalog import GT500_E_MODELS, GT500_GATEWAY_DRIVER
from app.core.connection_settings import get_poll_timeout_seconds
from app.services.connection_manager import connection_manager


class XantrexGt500Service:
    def read_points(self, device, points):
        if device.brand != "Xantrex" or device.model not in GT500_E_MODELS:
            raise ValueError("La diagnostica PVGT12542EDI richiede il profilo GT500 E/GI dedicato.")
        if device.protocol != "modbus_tcp" or device.transport != "tcp":
            raise ValueError("PVGT12542EDI richiede Modbus TCP, non RTU o Xanbus.")
        from app.catalog.xantrex_gt500_catalog import build_gt500_gateway_points
        canonical = {p.key: p for p in build_gt500_gateway_points()}
        for point in points:
            expected = canonical.get(point.key)
            if (expected is None or point.address != expected.address or point.length != 1
                    or point.register_type != "holding" or point.datatype != "uint16"
                    or point.scale != 1.0 or point.unit != ""
                    or point.protocol_meta.get("driver") != GT500_GATEWAY_DRIVER):
                raise ValueError("Mappa diagnostica PVGT diversa da quella documentata.")
        settings = device.connection_settings
        host, port = str(settings.get("host", "")), int(settings.get("port", 502))
        unit = int(settings.get("unit_id", 1))
        if not host or not 1 <= port <= 65535 or not 1 <= unit <= 247:
            raise ValueError("Endpoint PVGT o Unit ID non valido; broadcast escluso.")

        def operation(client):
            response = client.read_holding_registers(0, count=8, device_id=unit)
            if response.isError() or len(response.registers) != 8:
                raise RuntimeError("Risposta diagnostica PVGT incompleta o non valida.")
            words = response.registers
            if words[0] != 0:
                raise RuntimeError(f"Gateway PVGT: dati inverter non validi (stato {words[0]}).")
            # A healthy gateway is not proof of inverter model or physical power.
            return {point.key: words[point.address] for point in points}

        return connection_manager.execute_modbus_tcp(host, port, timeout=get_poll_timeout_seconds(settings, transport="tcp"),
            retries=0, operation_kind="poll", operation=operation)


xantrex_gt500_service = XantrexGt500Service()
