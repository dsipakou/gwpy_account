import uuid
from django.test import TestCase
from categories.models import Category
from categories.services import CategoryService
from workspaces.models import Workspace
from users.models import User
from parameterized import parameterized


class TestCategoryService(TestCase):
    # Predefined 3 categories with positions in increasing order
    @classmethod
    def setUp(self):
        owner = User.objects.create_user(username="testuser", password="testpassword")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=owner)
        self.parent_category = Category.objects.create(
            uuid=uuid.uuid4(), name="Parent Category", workspace=self.workspace
        )

    @parameterized.expand(
        [
            (2, 0, 100, 200, 300, 100, 200, 50),
            (0, 1, 100, 200, 300, 250, 200, 300),
            (0, 2, 100, 200, 300, 400, 200, 300),
            (2, 0, 0, 2, 3, 100, 200, 50),
            (2, 1, 0, 1, 2, 100, 200, 150),
            (2, 1, 10, 12, 13, 10, 12, 11),
        ]
    )
    def test_change_position_to_the_middle(
        self,
        old_index,
        new_index,
        initial_position_1,
        initial_position_2,
        initial_position_3,
        expected_position_1,
        expected_position_2,
        expected_position_3,
    ):
        category_1 = Category.objects.create(
            uuid=uuid.uuid4(),
            name="Category 1",
            position=initial_position_1,
            workspace=self.workspace,
            parent=self.parent_category,
        )
        category_2 = Category.objects.create(
            uuid=uuid.uuid4(),
            name="Category 2",
            position=initial_position_2,
            workspace=self.workspace,
            parent=self.parent_category,
        )
        category_3 = Category.objects.create(
            uuid=uuid.uuid4(),
            name="Category 3",
            position=initial_position_3,
            workspace=self.workspace,
            parent=self.parent_category,
        )
        CategoryService.reorder_categories(
            eval(f"category_{old_index + 1}").uuid, new_index
        )
        updated_category_1 = Category.objects.get(uuid=category_1.uuid)
        updated_category_2 = Category.objects.get(uuid=category_2.uuid)
        updated_category_3 = Category.objects.get(uuid=category_3.uuid)
        self.assertEqual(updated_category_1.position, expected_position_1)
        self.assertEqual(updated_category_2.position, expected_position_2)
        self.assertEqual(updated_category_3.position, expected_position_3)
