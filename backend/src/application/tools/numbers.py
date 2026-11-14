from decimal import Decimal, getcontext

MAX_NUMBER = Decimal("1e18")


def validate_number(number: Decimal) -> Decimal:
    # copy_abs and adjusted do not round in the active arithmetic context.
    if not number.is_finite() or number.copy_abs() > MAX_NUMBER:
        raise ValueError("Number outside the supported range")
    if number and number.adjusted() < getcontext().Emin:
        raise ValueError("Number is below the supported exponent range")
    return number
