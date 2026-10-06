"""Forms for creating and editing surveys and questions."""
from django import forms
from django.utils.translation import gettext_lazy as _

from apps.common.constants import SURVEY_CATEGORY_CHOICES

from .models import Question, Survey


class SurveyForm(forms.ModelForm):
    target_members_only = forms.BooleanField(
        label=_("Members only"),
        required=False,
        help_text=_("Only company members can take this survey."),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    target_min_level = forms.IntegerField(
        label=_("Minimum level"),
        required=False,
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0}),
    )
    target_min_age = forms.IntegerField(
        label=_("Minimum age"),
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0}),
    )
    target_max_age = forms.IntegerField(
        label=_("Maximum age"),
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0}),
    )
    target_genders = forms.MultipleChoiceField(
        label=_("Gender"),
        required=False,
        choices=[
            ("female", _("Female")),
            ("male", _("Male")),
            ("other", _("Other")),
        ],
        widget=forms.CheckboxSelectMultiple,
    )
    target_min_trust = forms.IntegerField(
        label=_("Minimum reputation level"),
        required=False,
        min_value=0,
        max_value=7,
        initial=0,
        help_text=_(
            "1–7 (Newcomer→Distinguished). 0 = no filter. "
            "Reputation is honor_points; level is derived from it."
        ),
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 7}),
    )

    class Meta:
        model = Survey
        fields = (
            "title",
            "description",
            "is_paid",
            "visibility",
            "points_reward",
            "response_target",
            "expires_at",
            "category",
        )
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "visibility": forms.Select(attrs={"class": "form-select"}),
            "points_reward": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "response_target": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "expires_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "category": forms.Select(
                attrs={"class": "form-select"},
                choices=SURVEY_CATEGORY_CHOICES,
            ),
            "is_paid": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "points_reward": _("Coins reward"),
        }

    def __init__(self, *args, free_mode: bool = False, company_mode: bool = False, **kwargs):
        self.survey_instance = kwargs.get("instance")
        self.free_mode = free_mode
        self.company_mode = company_mode
        super().__init__(*args, **kwargs)
        if "points_reward" in self.fields:
            self.fields["points_reward"].label = _("Coins reward")
            self.fields["points_reward"].help_text = _(
                "Coins given to participant on successful completion (paid surveys only)."
            )
        if "category" in self.fields:
            # Combobox: fixed choices; keep legacy free-text values selectable when editing
            choices = list(SURVEY_CATEGORY_CHOICES)
            current = ""
            if self.survey_instance and getattr(self.survey_instance, "category", None):
                current = (self.survey_instance.category or "").strip()
            if current and current not in {v for v, _ in choices}:
                choices.append((current, current))
            self.fields["category"] = forms.ChoiceField(
                label=_("Category"),
                required=False,
                choices=choices,
                widget=forms.Select(attrs={"class": "form-select"}),
            )
        if "expires_at" in self.fields:
            self.fields["expires_at"].input_formats = [
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ]
            self.fields["expires_at"].required = False
        targeting_fields = [
            "target_members_only",
            "target_min_level",
            "target_min_age",
            "target_max_age",
            "target_genders",
            "target_min_trust",
        ]
        if not company_mode:
            for name in targeting_fields:
                self.fields.pop(name, None)
        elif self.survey_instance and self.survey_instance.targeting:
            from apps.surveys.targeting import normalize_targeting

            tg = normalize_targeting(self.survey_instance.targeting)
            self.fields["target_members_only"].initial = tg["members_only"]
            self.fields["target_min_level"].initial = tg["min_level"]
            self.fields["target_min_age"].initial = tg["min_age"]
            self.fields["target_max_age"].initial = tg["max_age"]
            self.fields["target_genders"].initial = tg["genders"]
            self.fields["target_min_trust"].initial = tg["min_trust"]

        if free_mode:
            for name in ("is_paid", "visibility", "points_reward", "response_target"):
                self.fields.pop(name, None)
        elif company_mode:
            self.fields["is_paid"].label = _("Paid survey (can reward points)")
            self.fields["is_paid"].help_text = _(
                "If unchecked, this is a free survey (XP only; public; no points or response target)."
            )
            if "visibility" in self.fields:
                self.fields["visibility"].help_text = _(
                    "Public surveys appear on Discover. Private surveys are invite/targeted only."
                )
                if not (self.survey_instance and self.survey_instance.pk):
                    self.fields["visibility"].initial = Survey.Visibility.PUBLIC
        else:
            for name in ("is_paid", "visibility", "points_reward", "response_target"):
                self.fields.pop(name, None)

        if self.survey_instance and self.survey_instance.is_frozen:
            for name in list(self.fields):
                self.fields[name].disabled = True

    def clean(self):
        cleaned = super().clean()
        if self.free_mode:
            return cleaned

        is_paid = cleaned.get("is_paid", False)
        if not is_paid:
            cleaned["points_reward"] = 0
            cleaned["response_target"] = None
            cleaned["visibility"] = Survey.Visibility.PUBLIC

        if self.company_mode:
            if cleaned.get("target_members_only"):
                # Members-only: ignore demographic/progress targeting.
                cleaned["target_min_level"] = 0
                cleaned["target_min_age"] = None
                cleaned["target_max_age"] = None
                cleaned["target_genders"] = []
                cleaned["target_min_trust"] = 0
            else:
                min_age = cleaned.get("target_min_age")
                max_age = cleaned.get("target_max_age")
                if min_age is not None and max_age is not None and min_age > max_age:
                    self.add_error(
                        "target_max_age",
                        _("Maximum age must be greater than or equal to minimum age."),
                    )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.company_mode and not self.free_mode:
            from apps.surveys.targeting import targeting_from_form

            instance.targeting = targeting_from_form(self.cleaned_data)
            if "is_paid" in self.cleaned_data:
                instance.is_paid = bool(self.cleaned_data["is_paid"])
            if "visibility" in self.cleaned_data:
                instance.visibility = self.cleaned_data["visibility"]
            if "points_reward" in self.cleaned_data:
                instance.points_reward = self.cleaned_data.get("points_reward") or 0
            if "response_target" in self.cleaned_data:
                instance.response_target = self.cleaned_data.get("response_target")
            if instance.visibility == Survey.Visibility.PRIVATE:
                instance.allow_anonymous = False
            else:
                instance.allow_anonymous = True
            if not instance.is_paid:
                instance.points_reward = 0
                instance.response_target = None
                instance.visibility = Survey.Visibility.PUBLIC
                instance.targeting = {}
                instance.allow_anonymous = True
        else:
            instance.is_paid = False
            instance.points_reward = 0
            instance.response_target = None
            instance.visibility = Survey.Visibility.PUBLIC
            instance.targeting = {}
            instance.allow_anonymous = True
        if commit:
            instance.save()
        return instance


class QuestionForm(forms.ModelForm):
    choices_text = forms.CharField(
        label=_("Choices / items (one per line)"),
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        help_text=_("Used for single/multiple choice and ranking items."),
    )
    matrix_rows = forms.CharField(
        label=_("Matrix rows (one per line)"),
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    matrix_columns = forms.CharField(
        label=_("Matrix columns (one per line)"),
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    rating_max = forms.IntegerField(
        label=_("Rating max"),
        required=False,
        min_value=2,
        max_value=10,
        initial=5,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    scale_min = forms.IntegerField(
        label=_("Scale / number min"),
        required=False,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    scale_max = forms.IntegerField(
        label=_("Scale / number max"),
        required=False,
        initial=10,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    text_multiline = forms.BooleanField(
        label=_("Multi-line text"),
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    condition_source = forms.ModelChoiceField(
        label=_("Show only if question"),
        queryset=Question.objects.none(),
        required=False,
        help_text=_("Leave empty to always show this question."),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    condition_op = forms.ChoiceField(
        label=_("Condition"),
        required=False,
        choices=[
            ("eq", _("Equals")),
            ("neq", _("Does not equal")),
            ("in", _("Is one of (comma-separated)")),
            ("gte", _("≥ number")),
            ("lte", _("≤ number")),
            ("answered", _("Was answered")),
            ("not_answered", _("Was not answered")),
        ],
        initial="eq",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    condition_value = forms.CharField(
        label=_("Value"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = Question
        fields = ("type", "text", "help_text", "is_required", "order")
        widgets = {
            "type": forms.Select(attrs={"class": "form-select"}),
            "text": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "help_text": forms.TextInput(attrs={"class": "form-control"}),
            "is_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def __init__(self, *args, survey=None, **kwargs):
        super().__init__(*args, **kwargs)
        survey = survey or (self.instance.survey if self.instance and self.instance.pk else None)
        if survey:
            qs = survey.questions.all()
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields["condition_source"].queryset = qs
            self.fields["condition_source"].label_from_instance = (
                lambda obj: f"{obj.order}. {obj.text[:60]}"
            )
        if self.instance and self.instance.pk:
            cfg = self.instance.config or {}
            if "choices" in cfg:
                self.fields["choices_text"].initial = "\n".join(cfg["choices"])
            if "items" in cfg:
                self.fields["choices_text"].initial = "\n".join(cfg["items"])
            if "rows" in cfg:
                self.fields["matrix_rows"].initial = "\n".join(cfg["rows"])
            if "columns" in cfg:
                self.fields["matrix_columns"].initial = "\n".join(cfg["columns"])
            if self.instance.type == Question.Type.RATING and "max" in cfg:
                self.fields["rating_max"].initial = cfg["max"]
            if self.instance.type in {Question.Type.SCALE, Question.Type.NUMBER}:
                self.fields["scale_min"].initial = cfg.get("min", 1)
                self.fields["scale_max"].initial = cfg.get("max", 10)
            if self.instance.type == Question.Type.TEXT:
                self.fields["text_multiline"].initial = cfg.get("multiline", False)
            # Load existing conditional rule into form fields
            rules = self.instance.conditions or []
            if rules and isinstance(rules, list) and isinstance(rules[0], dict):
                rule = rules[0]
                src_id = rule.get("source_id")
                if src_id is not None:
                    try:
                        self.fields["condition_source"].initial = int(src_id)
                    except (TypeError, ValueError):
                        pass
                op = rule.get("op") or "eq"
                if op in dict(self.fields["condition_op"].choices):
                    self.fields["condition_op"].initial = op
                expected = rule.get("value")
                if expected is not None:
                    if isinstance(expected, list):
                        self.fields["condition_value"].initial = ", ".join(
                            str(v) for v in expected
                        )
                    else:
                        self.fields["condition_value"].initial = str(expected)

    @staticmethod
    def _config_from_cleaned(cleaned: dict) -> dict:
        qtype = cleaned.get("type")
        config: dict = {}
        if qtype in {Question.Type.SINGLE_CHOICE, Question.Type.MULTIPLE_CHOICE}:
            config["choices"] = cleaned.get("_choices", [])
        elif qtype == Question.Type.RANKING:
            config["items"] = cleaned.get("_items", [])
        elif qtype == Question.Type.MATRIX:
            config["rows"] = cleaned.get("_rows", [])
            config["columns"] = cleaned.get("_cols", [])
        elif qtype == Question.Type.RATING:
            config["max"] = cleaned.get("_rating_max", 5)
            config["style"] = "stars"
        elif qtype == Question.Type.SCALE:
            config["min"] = cleaned.get("_scale_min", 1)
            config["max"] = cleaned.get("_scale_max", 10)
        elif qtype == Question.Type.NUMBER:
            if cleaned.get("_scale_min") is not None:
                config["min"] = cleaned["_scale_min"]
            if cleaned.get("_scale_max") is not None:
                config["max"] = cleaned["_scale_max"]
        elif qtype == Question.Type.TEXT:
            config["multiline"] = cleaned.get("_multiline", False)
        elif qtype == Question.Type.YES_NO:
            config["choices"] = ["Yes", "No"]
        return config

    def clean(self):
        cleaned = super().clean()
        qtype = cleaned.get("type")
        if qtype in {Question.Type.SINGLE_CHOICE, Question.Type.MULTIPLE_CHOICE}:
            raw = cleaned.get("choices_text") or ""
            choices = [c.strip() for c in raw.splitlines() if c.strip()]
            if len(choices) < 2:
                self.add_error("choices_text", _("Provide at least 2 choices."))
            cleaned["_choices"] = choices
        elif qtype == Question.Type.RANKING:
            raw = cleaned.get("choices_text") or ""
            items = [c.strip() for c in raw.splitlines() if c.strip()]
            if len(items) < 2:
                self.add_error("choices_text", _("Provide at least 2 items to rank."))
            cleaned["_items"] = items
        elif qtype == Question.Type.MATRIX:
            rows = [r.strip() for r in (cleaned.get("matrix_rows") or "").splitlines() if r.strip()]
            cols = [
                c.strip()
                for c in (cleaned.get("matrix_columns") or "").splitlines()
                if c.strip()
            ]
            if len(rows) < 1 or len(cols) < 2:
                self.add_error("matrix_rows", _("Matrix needs rows and at least 2 columns."))
            cleaned["_rows"] = rows
            cleaned["_cols"] = cols
        elif qtype == Question.Type.RATING:
            cleaned["_rating_max"] = cleaned.get("rating_max") or 5
        elif qtype == Question.Type.SCALE:
            smin = cleaned.get("scale_min") or 1
            smax = cleaned.get("scale_max") or 10
            if smin >= smax:
                self.add_error("scale_max", _("Max must be greater than min."))
            cleaned["_scale_min"] = smin
            cleaned["_scale_max"] = smax
        elif qtype == Question.Type.NUMBER:
            cleaned["_scale_min"] = cleaned.get("scale_min")
            cleaned["_scale_max"] = cleaned.get("scale_max")
        elif qtype == Question.Type.TEXT:
            cleaned["_multiline"] = cleaned.get("text_multiline", False)

        src = cleaned.get("condition_source")
        op = cleaned.get("condition_op") or "eq"
        val = (cleaned.get("condition_value") or "").strip()
        if src and op in {"eq", "neq", "in", "gte", "lte"} and not val:
            self.add_error("condition_value", _("Provide a value for this condition."))

        config = self._config_from_cleaned(cleaned)
        cleaned["_config"] = config
        if self.instance is not None:
            self.instance.config = config
            if cleaned.get("type"):
                self.instance.type = cleaned["type"]
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.config = self.cleaned_data.get("_config") or self._config_from_cleaned(
            self.cleaned_data
        )
        src = self.cleaned_data.get("condition_source")
        if src:
            op = self.cleaned_data.get("condition_op") or "eq"
            val = (self.cleaned_data.get("condition_value") or "").strip()
            rule = {"source_id": src.id, "op": op}
            if op == "in":
                rule["value"] = [v.strip() for v in val.split(",") if v.strip()]
            elif op not in {"answered", "not_answered"}:
                try:
                    rule["value"] = int(val)
                except ValueError:
                    try:
                        rule["value"] = float(val)
                    except ValueError:
                        rule["value"] = val
            instance.conditions = [rule]
        else:
            instance.conditions = []
        if commit:
            instance.save()
        return instance
