import datetime

from dateutil.relativedelta import relativedelta

DATE_FORMAT = "%Y-%m-%d"


def get_first_day_of_current_month(current_date: str | None = None) -> datetime:
    if current_date:
        formatted_date = datetime.datetime.strptime(current_date, DATE_FORMAT)
        return formatted_date.replace(day=1)
    return datetime.date.today().replace(day=1)


def get_first_day_of_prev_month(current_date: str | None = None) -> datetime:
    return get_first_day_of_current_month(current_date) - relativedelta(months=1)


def get_last_day_of_prev_month(current_date: str | None = None) -> datetime:
    return get_first_day_of_current_month(current_date) - relativedelta(days=1)


def get_first_day_of_current_week(current_date: str | None = None) -> datetime.date:
    if current_date:
        pivot_date = datetime.datetime.strptime(current_date, DATE_FORMAT)
    else:
        pivot_date = datetime.date.today()
    return pivot_date - datetime.timedelta(days=pivot_date.weekday())


def get_start_of_current_week_datetime(
    current_date: str | None = None,
) -> datetime.datetime:
    get_first_day = get_first_day_of_current_week(current_date)
    return datetime.datetime.combine(get_first_day, datetime.datetime.min.time())


def get_last_day_of_current_week(current_date: str | None = None) -> datetime.date:
    return get_first_day_of_current_week(current_date) + datetime.timedelta(days=6)


def get_end_of_current_week_datetime(
    current_date: str | None = None,
) -> datetime.datetime:
    get_last_day = get_last_day_of_current_week(current_date)
    return datetime.datetime.combine(get_last_day, datetime.datetime.max.time())


def get_first_day_of_prev_week(current_date: str | None = None) -> datetime.date:
    return get_first_day_of_current_week(current_date) - datetime.timedelta(days=7)


def get_last_day_of_prev_week(current_date: str | None = None) -> datetime.date:
    return get_first_day_of_prev_week(current_date) + datetime.timedelta(days=6)


def add_week_to_date(current_date: str, weeks: int = 1) -> datetime.date:
    formatted_date = datetime.datetime.strptime(current_date, DATE_FORMAT)
    return formatted_date + relativedelta(weeks=weeks)


def add_month_to_date(current_date: str, months: int = 1) -> datetime.date:
    formatted_date = datetime.datetime.strptime(current_date, DATE_FORMAT)
    return formatted_date + relativedelta(months=months)
