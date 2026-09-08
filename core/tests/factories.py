"""Test factories — realistic Palestinian data, no Lorem Ipsum (spec §61)."""

from __future__ import annotations

import factory
from django.contrib.auth import get_user_model
from faker import Faker

fake = Faker("ar_AA")

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    first_name = factory.LazyFunction(lambda: fake.first_name())
    last_name = factory.LazyFunction(lambda: fake.last_name())
    email = factory.Sequence(lambda n: f"user{n}@maktab-aladala.ps")
    is_active = True

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or "correct-horse-staple-11")
        if create:
            obj.save()


class SuperuserFactory(UserFactory):
    is_staff = True
    is_superuser = True
    email = factory.Sequence(lambda n: f"admin{n}@maktab-aladala.ps")


def make_user_in_group(group_name: str, **kwargs):
    from django.contrib.auth.models import Group

    user = UserFactory(**kwargs)
    user.groups.add(Group.objects.get_or_create(name=group_name)[0])
    return user
