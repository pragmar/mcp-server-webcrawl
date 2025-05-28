import datetime

# obscene to place this everywhere, contain it
try:
    UTC = datetime.UTC
except AttributeError:
    # python <=3.10
    from datetime import timezone
    UTC = timezone.utc

# this is what is acceptable metadata content for crawl results
METADATA_VALUE_TYPE = str | int | float | bool | list[str] | list[int] | list[float] | None
