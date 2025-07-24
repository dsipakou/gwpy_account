from categories.models import Category
from django.db import transaction


class CategoryService:
    @classmethod
    def reorder_categories(cls, target_category_uuid, new_index: int):
        target_category = Category.objects.get(uuid=target_category_uuid)
        all_categories = Category.objects.filter(
            parent=target_category.parent
        ).order_by("position")
        if len(all_categories) == 0:
            return

        if new_index == len(all_categories) - 1:
            target_category.position = all_categories[new_index].position + 100
            target_category.save()
            return

        if new_index == 0:
            first_category = all_categories[0]
            new_position = first_category.position // 2
            if new_position == 0:
                cls._reset_positions(all_categories)
                new_position = 50

            target_category.position = new_position
            target_category.save()
            return

        # If the target category position is smaller than the new index, we need to increment the new index
        if target_category.position < all_categories[new_index].position:
            new_index += 1

        previous_category = all_categories[new_index - 1]
        next_category = all_categories[new_index]

        # Get the positions of the categories between which we want to insert
        prev_position = previous_category.position
        next_position = next_category.position

        # Calculate the exact position between the two categories
        new_position = prev_position + ((next_position - prev_position) // 2)
        if new_position == prev_position:
            cls._reset_positions(all_categories)
            prev_position = previous_category.position
            new_position = prev_position + 50

        target_category.position = new_position
        target_category.save()

    @classmethod
    def _reset_positions(cls, categories):
        # Reset the positions of the categories to the default values in decreasing order
        with transaction.atomic():
            for i in range(len(categories) - 1, -1, -1):
                category = categories[i]
                category.position = (i + 1) * 100
                category.save()
