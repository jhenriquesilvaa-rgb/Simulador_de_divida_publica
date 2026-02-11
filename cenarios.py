from dataclasses import dataclass


@dataclass
class CenarioMercado:
    nome: str
    choque_cdi_bps: float = 0.0
    choque_ipca_bps: float = 0.0
    choque_cambio_pct: float = 0.0
    choque_spread_bps: float = 0.0


CENARIO_BASE = CenarioMercado(nome="Base")

CENARIO_ESTRESSE = CenarioMercado(
    nome="Estresse",
    choque_cdi_bps=200,
    choque_ipca_bps=150,
    choque_cambio_pct=0.20,
    choque_spread_bps=100,
)

CENARIO_OTIMISTA = CenarioMercado(
    nome="Otimista",
    choque_cdi_bps=-100,
    choque_ipca_bps=-50,
    choque_cambio_pct=-0.05,
    choque_spread_bps=-50,
)
