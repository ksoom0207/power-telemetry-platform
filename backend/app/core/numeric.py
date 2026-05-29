from decimal import ROUND_HALF_UP, Decimal

WATT_DISPLAY_QUANT = Decimal("0.1")
KWH_DISPLAY_QUANT = Decimal("0.001")


def quantize_watts(value: Decimal) -> Decimal:
    return value.quantize(WATT_DISPLAY_QUANT, rounding=ROUND_HALF_UP)


def quantize_kwh(value: Decimal) -> Decimal:
    return value.quantize(KWH_DISPLAY_QUANT, rounding=ROUND_HALF_UP)
