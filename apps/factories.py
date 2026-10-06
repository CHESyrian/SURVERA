"""Factory Boy factories for SURVERA tests."""
import factory
from django.contrib.auth import get_user_model
from factory.django import DjangoModelFactory

from apps.companies.models import Company, CompanyMembership
from apps.responses.models import Answer, Response
from apps.surveys.models import Question, Survey

User = get_user_model()


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.Sequence(lambda n: f"user{n}")
    user_type = User.UserType.PERSON
    is_email_verified = True
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        raw = extracted if extracted is not None else "pass12345"
        self.set_password(raw)
        if create:
            self.save(update_fields=["password"])


class CompanyFactory(DjangoModelFactory):
    class Meta:
        model = Company

    name = factory.Sequence(lambda n: f"Company {n}")


class CompanyMembershipFactory(DjangoModelFactory):
    class Meta:
        model = CompanyMembership

    company = factory.SubFactory(CompanyFactory)
    user = factory.SubFactory(UserFactory)
    role = CompanyMembership.Role.PARTICIPANT
    is_active = True


class SurveyFactory(DjangoModelFactory):
    class Meta:
        model = Survey

    title = factory.Sequence(lambda n: f"Survey {n}")
    company = factory.SubFactory(CompanyFactory)
    status = Survey.Status.DRAFT
    is_paid = False
    points_reward = 0
    visibility = Survey.Visibility.PUBLIC
    created_by = factory.SubFactory(UserFactory)


class QuestionFactory(DjangoModelFactory):
    class Meta:
        model = Question

    survey = factory.SubFactory(SurveyFactory)
    order = factory.Sequence(lambda n: n + 1)
    type = Question.Type.TEXT
    text = factory.Sequence(lambda n: f"Question {n}?")
    is_required = True
    config = factory.LazyFunction(dict)


class ResponseFactory(DjangoModelFactory):
    class Meta:
        model = Response

    survey = factory.SubFactory(SurveyFactory)
    participant = factory.SubFactory(UserFactory)
    status = Response.Status.IN_PROGRESS


class AnswerFactory(DjangoModelFactory):
    class Meta:
        model = Answer

    response = factory.SubFactory(ResponseFactory)
    question = factory.SubFactory(QuestionFactory)
    value = "yes"
