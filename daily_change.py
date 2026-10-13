"""Short-lived daily price references; no provider calls or synthetic history."""
import math

REFERENCE_TTL = 180


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def preserve(current, previous, now):
    """A same-pool live quote may update a recent provider's daily baseline.

    The baseline expires at the original provider observation, not each tick.
    Pool switches, expired references and invalid changes stay unknown.
    """
    result = dict(current)
    price, change = number(current.get('price')), number(current.get('change'))
    observed = number(current.get('fetchedAt'))
    if price is None or price <= 0 or observed is None:
        return result
    if change is not None and change > -100:
        result.update(changeReferencePrice=price / (1 + change / 100),
                      changeObservedAt=observed,
                      changeSource=current.get('priceSource', 'Provider daily change'))
        return result
    result['change'] = None
    same_pool = bool(current.get('pair')) and str(current['pair']).lower() == str(previous.get('pair', '')).lower()
    if not same_pool:
        return result
    stamp = number(previous.get('changeObservedAt', previous.get('fetchedAt')))
    if stamp is None or not 0 <= now - stamp <= REFERENCE_TTL:
        return result
    baseline = number(previous.get('changeReferencePrice'))
    if baseline is None:
        old_price, old_change = number(previous.get('price')), number(previous.get('change'))
        if old_price is not None and old_price > 0 and old_change is not None and old_change > -100:
            baseline = old_price / (1 + old_change / 100)
    if baseline is None or baseline <= 0:
        return result
    value = (price / baseline - 1) * 100
    if not math.isfinite(value):
        return result
    result.update(change=value, changeReferencePrice=baseline, changeObservedAt=stamp,
                  changeSource=previous.get('changeSource') or previous.get('priceSource', 'Provider daily change'))
    return result
