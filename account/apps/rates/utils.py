import datetime


def generate_date_seq(days_count):
    return [
        datetime.date.today() - datetime.timedelta(days=x) for x in range(days_count)
    ]
