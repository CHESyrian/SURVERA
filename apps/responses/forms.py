"""Forms for responses / reporting."""
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Report


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ("type", "note")
        widgets = {
            "type": forms.Select(attrs={"class": "form-control"}),
            "note": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": _("Describe the issue…"),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["type"].label = _("Report type")
        self.fields["note"].label = _("Note")
        self.fields["note"].required = True
