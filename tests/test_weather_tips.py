from datetime import date, timedelta

from kapibara.features.weather import tips
from kapibara.features.weather.tips import clothes_tip

DAY = date(2026, 11, 18)


def test_every_phrase_fits_the_app_parser():
    pools = [p for _, p in tips._BY_FEELS] + [tips._STORM, tips._RAIN_COLD, tips._RAIN_WARM,
                                              tips._SNOW, tips._WIND_COLD, tips._WIND_WARM, tips._HAIL,
                                              tips._RAIN_HEAVY, tips._SNOW_HEAVY, tips._FOG, tips._FEELS_GAP]
    for pool in pools:
        assert len(pool) >= 2
        for phrase in pool:
            assert phrase[0].islower() and "·" not in phrase
            assert all(ord(ch) < 0x2000 for ch in phrase), "без эмодзи"
            assert len(phrase) <= 34, phrase


def test_feels_beats_thermometer():
    assert clothes_tip(-8, feels=-12, day=DAY) in tips._BY_FEELS[2][1]
    assert clothes_tip(-3, feels=-5, day=DAY) in tips._BY_FEELS[3][1]
    assert clothes_tip(20, feels=20, day=DAY) in tips._BY_FEELS[8][1]
    assert clothes_tip(35, day=DAY) in tips._BY_FEELS[-1][1]
    assert clothes_tip(-32, feels=-35, day=DAY) in tips._BY_FEELS[0][1]


def test_weather_overrides():
    assert clothes_tip(15, code=95, day=DAY) in tips._STORM
    assert clothes_tip(1, feels=-2, code=73, day=DAY) in tips._SNOW
    assert clothes_tip(4, feels=2, code=63, day=DAY) in tips._RAIN_COLD
    assert clothes_tip(18, code=61, day=DAY) in tips._RAIN_WARM
    assert clothes_tip(6, feels=1, wind=40, day=DAY) in tips._WIND_COLD
    assert clothes_tip(15, wind=40, day=DAY) in tips._WIND_WARM
    assert clothes_tip(20, code=96, day=DAY) in tips._HAIL
    assert clothes_tip(12, code=65, day=DAY) in tips._RAIN_HEAVY
    assert clothes_tip(-3, feels=-8, code=75, day=DAY) in tips._SNOW_HEAVY
    assert clothes_tip(3, feels=1, code=45, day=DAY) in tips._FOG
    assert clothes_tip(5, feels=-2, day=DAY) in tips._FEELS_GAP
    assert clothes_tip(25, wind=40, day=DAY) in tips._BY_FEELS[9][1]   # в жару ветер не в счёт


def test_phrase_is_stable_within_a_day_and_changes_between_days():
    assert clothes_tip(4, day=DAY) == clothes_tip(4, day=DAY)
    seen = {clothes_tip(4, day=DAY + timedelta(days=i)) for i in range(3)}
    assert len(seen) == 3  # пять фраз на ситуацию


def test_storm_and_hail_change_by_the_hour():
    storm = {clothes_tip(15, code=95, day=DAY, hour=h) for h in range(3)}
    hail = {clothes_tip(15, code=96, day=DAY, hour=h) for h in range(3)}
    assert len(storm) == 3 and len(hail) == 3
    assert clothes_tip(1, feels=-2, code=75, day=DAY, hour=3) == clothes_tip(1, feels=-2, code=75, day=DAY, hour=9)


def test_snow_showers_get_snow_phrases():
    assert clothes_tip(2, feels=1, code=85, day=DAY) in tips._SNOW
    assert clothes_tip(2, feels=1, code=86, day=DAY) in tips._SNOW_HEAVY
