from datetime import datetime

def isoformat_zulu(dt: datetime):
    # python 3.10 considerations, needs this 
    return dt.isoformat().replace("+00:00", "Z")
