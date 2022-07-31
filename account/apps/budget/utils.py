import datetime


def get_first_day_of_current_month() -> datetime:
    return datetime.date.today().replace(day=1)


def get_first_day_of_prev_month() -> datetime:
    first_day_of_month = get_first_day_of_current_month()
    return first_day_of_month.replace(month=first_day_of_month.month - 1)


def get_last_day_of_prev_month() -> datetime:
    return get_first_day_of_current_month() - datetime.timedelta(days=1)


def get_first_day_of_current_week() -> datetime:
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def get_last_day_of_current_week() -> datetime:
    return get_first_day_of_current_week() + datetime.timedelta(days=6)


def get_first_day_of_prev_week() -> datetime:
    return get_first_day_of_current_week() - datetime.timedelta(days=7)


def get_last_day_of_prev_week() -> datetime:
    return get_first_day_of_prev_week() + datetime.timedelta(days=6)
