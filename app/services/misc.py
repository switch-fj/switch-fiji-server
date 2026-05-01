from app.utils.tz import grouped_cities


class MiscService:
    @staticmethod
    async def get_cities_by_regions():
        return grouped_cities()
