TTS_SPEED_STEPS = (
    (0.6, -8),
    (0.8, -4),
    (1.0, 0),
)


def tts_speed_label(rate):
    for multiplier, configured_rate in TTS_SPEED_STEPS:
        if rate == configured_rate:
            return f"{multiplier:.1f}X"
    return "1.0X"


def next_tts_speed_rate(rate):
    for index, (_, configured_rate) in enumerate(TTS_SPEED_STEPS):
        if rate == configured_rate:
            return TTS_SPEED_STEPS[(index + 1) % len(TTS_SPEED_STEPS)][1]
    return TTS_SPEED_STEPS[0][1]


def is_learning_tts_rate(rate):
    return any(rate == configured_rate for _, configured_rate in TTS_SPEED_STEPS)
