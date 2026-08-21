from datetime import time


class Constants:
    BLOCKLIST_PREFIX = "blocked:key"
    CLIENT_SITES = "sites:client:uid"
    SITE_STATS_STREAM = "site_stats:stream:uid"
    SITE_STAT = "site_stat:uid"
    ENERGY_PORTFOLIO = "ep:m:y"
    MPPT_FN_CHECK = "mppt_fn_check:site_uid:date_at"
    BA3_SOC = "ba3_soc:site_uid:date_at"
    MPPT_BA3_SOC_LOCK = "mppt_ba3_soc:lock:site_uid:date_at"
    SITE_ENERGY_USAGE = "site_energy_usage:site_uid:date_at"
    SITE_ENERGY_USAGE_LOCK = "site_energy_usage:lock:site_uid:date_at"


ASSUMED_IRRADIANCE: dict[time, int] = {
    time(9, 0): 700,
    time(9, 30): 750,
    time(10, 0): 750,
    time(10, 30): 800,
    time(11, 0): 850,
    time(11, 30): 850,
    time(12, 0): 900,
    time(12, 30): 900,
    time(13, 0): 900,
    time(13, 30): 850,
    time(14, 0): 800,
    time(14, 30): 750,
    time(15, 0): 700,
}

TIME_FRAME = [
    time(0, 0),
    time(0, 30),
    time(1, 0),
    time(1, 30),
    time(2, 0),
    time(2, 30),
    time(3, 0),
    time(3, 30),
    time(4, 0),
    time(4, 30),
    time(5, 0),
    time(5, 30),
    time(6, 0),
    time(6, 30),
    time(7, 0),
    time(7, 30),
    time(8, 0),
    time(8, 30),
    time(9, 0),
    time(9, 30),
    time(10, 0),
    time(10, 30),
    time(11, 0),
    time(11, 30),
    time(12, 0),
    time(12, 30),
    time(13, 0),
    time(13, 30),
    time(14, 0),
    time(14, 30),
    time(15, 0),
    time(15, 30),
    time(16, 0),
    time(16, 30),
    time(17, 0),
    time(17, 30),
    time(18, 0),
    time(18, 30),
    time(19, 0),
    time(19, 30),
    time(20, 0),
    time(20, 30),
    time(21, 0),
    time(21, 30),
    time(22, 0),
    time(22, 30),
    time(23, 0),
    time(23, 30),
]
