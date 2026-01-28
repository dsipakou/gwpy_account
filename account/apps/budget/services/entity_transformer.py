"""Budget Entity Transformer Service.

Handles transformation of budget and transaction Django models into
TypedDict/Pydantic entities for API responses.
"""

import structlog

from budget.entities import BudgetGroupedItem, BudgetItem, BudgetTransactionItem

logger = structlog.get_logger()


class BudgetEntityTransformer:
    """Service for transforming budget entities for API responses."""

    @classmethod
    def transform_to_budget_items(
        cls, budgets, latest_rates, available_currencies, base_currency
    ) -> list[BudgetItem]:
        """Transform budget QuerySet into BudgetItem TypedDicts.

        Args:
            budgets: QuerySet of Budget models with transactions prefetched
            latest_rates: Dict mapping currency codes to latest exchange rates
            available_currencies: QuerySet of currency dicts with code and is_base
            base_currency: Base currency code string

        Returns:
            List of BudgetItem TypedDicts with multicurrency calculations
        """
        budgets_list = []
        for budget in budgets:
            multicurrency_map = (
                budget.multicurrency.amount_map
                if hasattr(budget, "multicurrency")
                else {}
            )
            planned_in_base_currency = multicurrency_map.get(
                base_currency, budget.amount
            )
            transactions = cls.transform_transactions(
                budget.transactions, latest_rates, base_currency
            )
            spent_in_original_currency = 0
            spent_in_base_currency = 0
            spent_in_currencies = {}
            planned_in_currencies = {}
            logger.debug("budget.services.make_budgets.currencies.start")
            for currency in available_currencies:
                if (
                    hasattr(budget, "multicurrency")
                    and currency["code"] in budget.multicurrency.amount_map
                ):
                    planned_in_currencies[currency["code"]] = (
                        budget.multicurrency.amount_map[currency["code"]]
                    )
                elif currency["is_base"]:
                    planned_in_currencies[currency["code"]] = planned_in_base_currency
                else:
                    try:
                        planned_in_currencies[currency["code"]] = round(
                            planned_in_base_currency
                            / latest_rates.get(currency["code"], 0),
                            5,
                        )
                    except ZeroDivisionError:
                        planned_in_currencies[currency["code"]] = 0
            logger.debug("budget.services.make_budgets.currencies.end")
            if len(transactions) > 0:
                spent_in_base_currency = sum(
                    item["spent_in_base_currency"] for item in transactions
                )
                spent_in_original_currency = sum(
                    item["spent_in_original_currency"] for item in transactions
                )
                logger.debug(
                    "budget.services.make_budgets.transactions.currencies.start"
                )
                for currency in available_currencies:
                    spent_in_currencies[currency["code"]] = sum(
                        transaction["spent_in_currencies"].get(currency["code"], 0)
                        for transaction in transactions
                    )
                logger.debug("budget.services.make_budgets.transactions.currencies.end")
            logger.debug("budget.services.make_budgets.budget_item.start")
            budget_item = BudgetItem(
                uuid=budget.uuid,
                category=budget.category.uuid,
                currency=budget.currency.uuid,
                user=budget.user.uuid,
                title=budget.title,
                budget_date=budget.budget_date,
                transactions=transactions,
                description=budget.description,
                recurrent=budget.recurrent_type,
                is_completed=budget.is_completed,
                planned=budget.amount,
                planned_in_currencies=planned_in_currencies,
                spent_in_base_currency=spent_in_base_currency,
                spent_in_original_currency=spent_in_original_currency,
                spent_in_currencies=spent_in_currencies,
                created_at=budget.created_at,
                modified_at=budget.modified_at,
            )
            budgets_list.append(budget_item)
            logger.debug("budget.services.make_budgets.budget_item.end")
        return budgets_list

    @classmethod
    def group_budgets(
        cls, budgets, latest_rates, available_currencies, base_currency
    ) -> list[BudgetGroupedItem]:
        """Group budgets by title and aggregate spending/planning.

        Args:
            budgets: QuerySet of Budget models
            latest_rates: Dict mapping currency codes to latest exchange rates
            available_currencies: QuerySet of currency dicts with code and is_base
            base_currency: Base currency code string

        Returns:
            List of BudgetGroupedItem TypedDicts with aggregated data
        """
        budgets_list = []
        grouped_dict = {}
        for budget in cls.transform_to_budget_items(
            budgets, latest_rates, available_currencies, base_currency
        ):
            if budget["title"] not in grouped_dict:
                grouped_dict[budget["title"]] = {
                    "uuid": budget["uuid"],
                    "user": budget["user"],
                    "title": budget["title"],
                    "planned": budget["planned"],
                    "planned_in_currencies": budget["planned_in_currencies"].copy(),
                    "spent_in_base_currency": budget["spent_in_base_currency"],
                    "spent_in_original_currency": budget["spent_in_original_currency"],
                    "spent_in_currencies": budget["spent_in_currencies"].copy(),
                    "items": [budget],
                }
            else:
                grouped_dict[budget["title"]]["planned"] += budget["planned"]
                grouped_dict[budget["title"]]["spent_in_base_currency"] += budget[
                    "spent_in_base_currency"
                ]
                grouped_dict[budget["title"]]["spent_in_original_currency"] += budget[
                    "spent_in_original_currency"
                ]
                for currency in available_currencies:
                    grouped_dict[budget["title"]]["spent_in_currencies"][
                        currency["code"]
                    ] = grouped_dict[budget["title"]]["spent_in_currencies"].get(
                        currency["code"], 0
                    ) + budget["spent_in_currencies"].get(currency["code"], 0)

                    grouped_dict[budget["title"]]["planned_in_currencies"][
                        currency["code"]
                    ] = grouped_dict[budget["title"]]["planned_in_currencies"].get(
                        currency["code"], 0
                    ) + budget["planned_in_currencies"].get(currency["code"], 0)
                grouped_dict[budget["title"]]["items"].append(budget)

        for value in grouped_dict.values():
            budgets_list.append(BudgetGroupedItem(**value))
        return budgets_list

    @classmethod
    def transform_transactions(
        cls, transactions, latest_rates, base_currency_code: str
    ) -> list[dict]:
        """Transform transaction QuerySet into TypedDict list.

        Args:
            transactions: QuerySet of Transaction models
            latest_rates: Dict mapping currency codes to latest exchange rates
            base_currency_code: Base currency code string

        Returns:
            List of BudgetTransactionItem TypedDicts sorted by transaction_date
        """
        transactions_list = []
        for transaction in transactions:
            multicurrency_map = (
                transaction.multicurrency.amount_map
                if hasattr(transaction, "multicurrency")
                else {}
            )
            spent_in_base_currency = transaction.amount
            for currency_code in latest_rates:
                if currency_code not in multicurrency_map:
                    try:
                        multicurrency_map[currency_code] = round(
                            spent_in_base_currency / latest_rates.get(currency_code, 0),
                            5,
                        )
                    except ZeroDivisionError:
                        multicurrency_map[currency_code] = 0
            logger.debug("budget.services.make_transactions.append_item.start")
            transactions_list.append(
                BudgetTransactionItem(
                    uuid=transaction.uuid,
                    currency=transaction.currency.uuid,
                    currency_code=transaction.currency.code,
                    spent_in_base_currency=spent_in_base_currency,
                    spent_in_original_currency=transaction.amount,
                    spent_in_currencies=multicurrency_map,
                    transaction_date=transaction.transaction_date,
                )
            )
            logger.debug("budget.services.make_transactions.append_item.end")
        transactions_list.sort(key=lambda x: x["transaction_date"])
        return transactions_list
