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


def get_first_day_of_current_week(current_date: str | None = None) -> datetime:
    if current_date:
        pivot_date = datetime.datetime.strptime(current_date, DATE_FORMAT)
    else:
        pivot_date = datetime.date.today()
    return pivot_date - datetime.timedelta(days=pivot_date.weekday())


def get_last_day_of_current_week(current_date: str | None = None) -> datetime:
    return get_first_day_of_current_week(current_date) + datetime.timedelta(days=6)


def get_first_day_of_prev_week(current_date: str | None = None) -> datetime:
    return get_first_day_of_current_week(current_date) - datetime.timedelta(days=7)


def get_last_day_of_prev_week(current_date: str | None = None) -> datetime:
    return get_first_day_of_prev_week(current_date) + datetime.timedelta(days=6)
