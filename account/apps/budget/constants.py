import enum


class BudgetDuplicateType(str, enum.Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    OCCASIONAL = "occasional"


ALLOWED_BUDGET_RECURRENT_TYPE = (
    BudgetDuplicateType.WEEKLY,
    BudgetDuplicateType.MONTHLY,
    BudgetDuplicateType.OCCASIONAL,
)
