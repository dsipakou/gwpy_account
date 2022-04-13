from django.db import models


class Account(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    source = models.CharField(max_length=30)
    amount = models.IntegerField()
    description = models.CharField(max_length=255, blank=True)
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
