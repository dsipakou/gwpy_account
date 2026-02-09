from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from budget import constants
from budget.models import Budget, BudgetSeries, BudgetSeriesException


class BudgetSerializer(serializers.ModelSerializer):
    number_of_repetitions = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        help_text="Number of times this budget should repeat. Null means infinite.",
    )

    class Meta:
        model = Budget
        fields = (
            "uuid",
            "user",
            "category",
            "currency",
            "title",
            "amount",
            "recurrent",
            "budget_date",
            "description",
            "is_completed",
            "number_of_repetitions",
            "created_at",
            "modified_at",
        )

    def to_representation(self, instance):
        """Use model's recurrent_type property for output

        Returns:
        - "weekly" or "monthly" for budgets with series
        - None for non-recurrent budgets (no series)
        """
        data = super().to_representation(instance)
        # Replace database recurrent field with calculated property
        # (can be "weekly", "monthly", or None)
        data["recurrent"] = instance.recurrent_type

        # Add number_of_repetitions from series
        if instance.series:
            data["number_of_repetitions"] = instance.series.count
        else:
            data["number_of_repetitions"] = None

        return data

    def create(self, validated_data):
        """Create a new budget and optionally a new BudgetSeries.

        Series Creation Rules:
        - Weekly/Monthly budgets: Always creates a NEW independent series
        - Occasional budgets: No series created
        - Each budget gets its own series, even with same title/user/frequency

        This design allows users to:
        1. Create separate budgets with same title for different time periods
        2. Stop/modify one series without affecting others
        3. Change amounts/categories over time without conflict
        4. Have multiple independent lifecycles for same budget title
        """
        workspace = validated_data["user"].active_workspace
        if not workspace:
            raise ValidationError("User has no active workspace")

        # Extract number_of_repetitions before creating Budget instance
        # (it's not a Budget model field, only used for BudgetSeries)
        number_of_repetitions = validated_data.pop("number_of_repetitions", None)

        # Handle BudgetSeries creation for WEEKLY and MONTHLY budgets
        series = None
        recurrent = validated_data.get("recurrent")

        # Only create series for weekly/monthly
        if recurrent in (
            constants.BudgetDuplicateType.WEEKLY.value,
            constants.BudgetDuplicateType.MONTHLY.value,
        ):
            # Map recurrent value to BudgetSeries frequency
            frequency_map = {
                constants.BudgetDuplicateType.WEEKLY.value: BudgetSeries.Frequency.WEEKLY,
                constants.BudgetDuplicateType.MONTHLY.value: BudgetSeries.Frequency.MONTHLY,
            }
            frequency = frequency_map[recurrent]

            # Always create a new BudgetSeries for this budget
            # Each budget gets its own independent series, even with the same title
            series = BudgetSeries.objects.create(
                user=validated_data["user"],
                workspace=workspace,
                title=validated_data["title"],
                category=validated_data["category"],
                currency=validated_data["currency"],
                amount=validated_data["amount"],
                start_date=validated_data["budget_date"],
                frequency=frequency,
                interval=1,
                count=number_of_repetitions,
                until=None,
            )

        data = {
            **validated_data,
            "workspace": workspace,
            "series": series,
        }
        budget = super().create(data)

        # If this budget has a series and date, remove any skip exception
        # (user is "un-skipping" this date by manually creating a budget)
        if budget.series and budget.budget_date:
            BudgetSeriesException.objects.filter(
                series=budget.series, date=budget.budget_date, is_skipped=True
            ).delete()

        return budget


class TransactionSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    currency = serializers.UUIDField()
    currency_code = serializers.CharField()
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    spent_in_currencies = serializers.DictField()
    transaction_date = serializers.CharField()


class TransactionV2Serializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    currency = serializers.UUIDField()
    currency_code = serializers.CharField()
    spent = serializers.FloatField()
    spent_in_currencies = serializers.DictField()
    transaction_date = serializers.CharField()


class BudgetUsageSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    title = serializers.CharField()
    planned = serializers.FloatField()
    planned_in_currencies = serializers.DictField()
    budget_date = serializers.DateField()
    category = serializers.UUIDField()
    currency = serializers.UUIDField()
    user = serializers.UUIDField()
    is_completed = serializers.BooleanField()
    recurrent = serializers.CharField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    transactions = serializers.ListField(child=TransactionSerializer())
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    spent_in_currencies = serializers.DictField()
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()


class BudgetUsageV2Serializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    title = serializers.CharField()
    budget_date = serializers.DateField()
    category = serializers.UUIDField()
    currency = serializers.UUIDField()
    user = serializers.UUIDField()
    is_completed = serializers.BooleanField()
    recurrent = serializers.CharField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    transactions = serializers.ListField(child=TransactionV2Serializer())
    planned = serializers.FloatField()
    spent = serializers.FloatField()
    planned_in_currencies = serializers.DictField()
    spent_in_currencies = serializers.DictField()
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()


class WeeklyBudgetUsageSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    title = serializers.CharField()
    budget_date = serializers.DateField()
    planned = serializers.FloatField(source="amount")
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    is_completed = serializers.BooleanField()
    budget_transactions = serializers.ListField(child=TransactionSerializer())
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()


class BudgetGroupedUsageSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    user = serializers.UUIDField()
    title = serializers.CharField()
    planned = serializers.IntegerField()
    planned_in_currencies = serializers.DictField()
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    spent_in_currencies = serializers.DictField()
    items = serializers.ListField(child=BudgetUsageSerializer())


class BudgetGroupedUsageV2Serializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    user = serializers.UUIDField()
    title = serializers.CharField()
    planned = serializers.IntegerField()
    spent = serializers.FloatField()
    is_another_category = serializers.BooleanField()
    is_another_month = serializers.BooleanField()
    planned_in_currencies = serializers.DictField()
    spent_in_currencies = serializers.DictField()
    spent_in_currencies_overall = serializers.DictField()
    items = serializers.ListField(child=BudgetUsageV2Serializer())


class CategoryBudgetSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    category_name = serializers.CharField()
    budgets = serializers.ListField(child=BudgetGroupedUsageSerializer())
    planned = serializers.FloatField()
    planned_in_currencies = serializers.DictField()
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    spent_in_currencies = serializers.DictField()


class CategoryBudgetV2Serializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    category_name = serializers.CharField()
    budgets = serializers.ListField(child=BudgetGroupedUsageV2Serializer())
    planned = serializers.FloatField()
    spent = serializers.FloatField()
    planned_in_currencies = serializers.DictField()
    spent_in_currencies = serializers.DictField()


class LastMonthsUsageSerializer(serializers.Serializer):
    month = serializers.DateField()
    amount = serializers.FloatField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["amount"] = round(data["amount"], 0)
        return data


class DuplicateRequestSerializer(serializers.Serializer):
    budgets = serializers.ListField()

    def validate_type(self, value):
        if value not in constants.ALLOWED_BUDGET_RECURRENT_TYPE:
            return ValidationError("Unsupported budget reccurent type")
        return value


class DuplicateResponseSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    date = serializers.DateField()
    title = serializers.CharField()
    amount = serializers.FloatField()
    currency = serializers.CharField()
    recurrent = serializers.CharField()
