"""Creative direction for the workbench's two platform branches."""

STYLES = {
    'douyin': {
        'copy': 'Lead with a short visual hook, demonstrate one verified benefit early, and end with a direct next step.',
        'scenes': (
            'A high-contrast studio set, clean bold color blocks, hard side light, and clear central product space.',
            'A minimal demonstration set with strong directional light and a crisp geometric surface.',
        ),
        'motion': 'Open on a clear focal point. Use a brisk push-in or quick reveal, then hold the verified product detail in focus.',
        'layout': 'classic',
    },
    'xiaohongshu': {
        'copy': 'Lead with a specific everyday use context. Explain practical selection details and use a save-worthy closing without inventing personal experience.',
        'scenes': (
            'An editorial everyday tabletop, soft window light, muted natural colors and subtle real-world texture.',
            'A quiet lifestyle interior with diffuse daylight, warm neutral materials and uncluttered negative space.',
        ),
        'motion': 'Establish the everyday context, then use a gentle drift or a stable close-up. Leave time to inspect the product detail.',
        'layout': 'product_top',
    },
}


def scene_owners(platforms):
    if len(platforms) == 1:
        return {'scene_1': platforms[0], 'scene_2': platforms[0]}
    return {'scene_1': 'douyin', 'scene_2': 'xiaohongshu'}


def poster_slot(platform, platforms):
    return next(slot for slot, owner in scene_owners(platforms).items() if owner == platform)
