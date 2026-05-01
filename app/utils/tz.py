import zoneinfo


def get_all_zones():
    all_zones = zoneinfo.available_timezones()
    return sorted(all_zones)


def grouped_cities():
    all_zones = get_all_zones()
    grouped_regions: dict[str, list[str]] = {"Others": []}

    for zone in all_zones:
        if "/" in zone:
            region, _ = zone.split("/", 1)
            if region not in grouped_regions:
                grouped_regions[region] = []
            grouped_regions[region].append(zone)
        else:
            grouped_regions["Others"].append(zone)

    sorted_regions = dict(sorted(grouped_regions.items(), key=lambda x: (x[0] == "Others", x[0])))

    return sorted_regions
