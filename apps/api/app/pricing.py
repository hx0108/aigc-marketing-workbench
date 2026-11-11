"""Versioned video reservation pricing shared by quotes and worker execution."""
from decimal import Decimal, InvalidOperation
from math import ceil

from .ledger import money

MINIMAX_SECOND_PRICE = Decimal('0.50')
HAILUO_FAST_MODEL = 'MiniMax-Hailuo-2.3-Fast'
HAILUO_FAST_PRICE_VERSION = 'minimax-cn-hailuo-fast-2026-11-11'
HAILUO_FAST_PRICE = Decimal('1.35')


def hailuo_fast_seconds(duration):
    try:
        seconds = Decimal(str(duration))
    except InvalidOperation:
        raise ValueError('invalid_minimax_video_duration') from None
    if not seconds.is_finite() or not 0 < seconds <= 6:
        raise ValueError('invalid_minimax_video_duration')
    return 6


def hailuo_fast_bound(authorization, maximum):
    params = authorization.get('provider_parameters', {}).get('video', {})
    if authorization.get('price_version') != HAILUO_FAST_PRICE_VERSION or params.get('resolution') != '768P' or params.get('duration') != 6 or maximum < HAILUO_FAST_PRICE:
        raise ValueError('dynamic_cost_exceeds_configured_bound')
    return HAILUO_FAST_PRICE


def uses_minimax_video_tariff(authorization):
    return (authorization.get('price_version') == 'minimax-cn-2026-11-11' and
            authorization.get('providers', {}).get('video') == 'MiniMax-H3' and
            authorization.get('provider_parameters', {}).get('video', {}).get('resolution') == '768P')


def minimax_video_seconds(duration):
    try:
        seconds = Decimal(str(duration))
    except InvalidOperation:
        raise ValueError('invalid_minimax_video_duration') from None
    if not seconds.is_finite() or not 0 < seconds <= 15:
        raise ValueError('invalid_minimax_video_duration')
    return max(4, ceil(seconds))


def dynamic_bound(authorization, duration):
    maximum = money(authorization['bounds']['dynamic'])
    if authorization.get('providers', {}).get('video') == HAILUO_FAST_MODEL:
        hailuo_fast_seconds(duration)
        return hailuo_fast_bound(authorization, maximum)
    if not uses_minimax_video_tariff(authorization):
        return maximum
    amount = MINIMAX_SECOND_PRICE * minimax_video_seconds(duration)
    if amount > maximum:
        raise ValueError('dynamic_cost_exceeds_configured_bound')
    return amount


def creation_reservation_floor(authorization, duration, platform_count):
    """Smallest reservation for the full automatic pipeline, before shot planning."""
    bounds = authorization['bounds']
    maximum = money(bounds['dynamic'])
    if authorization.get('providers', {}).get('video') == HAILUO_FAST_MODEL:
        video = hailuo_fast_bound(authorization, maximum) * ((duration + 5) // 6)
    elif uses_minimax_video_tariff(authorization):
        maximum_seconds = min(15, int(maximum / MINIMAX_SECOND_PRICE))
        if maximum_seconds < 4:
            raise ValueError('dynamic_cost_exceeds_configured_bound')
        minimum_shots = (duration + maximum_seconds - 1) // maximum_seconds
        video = MINIMAX_SECOND_PRICE * max(duration, 4 * minimum_shots)
    else:
        video = maximum
    return (money(bounds['text']) + 2 * money(bounds['product_image']) +
            platform_count * (money(bounds['tts']) + video))
