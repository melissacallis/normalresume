from django import forms

class JobDescriptionForm(forms.Form):
    job_a = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10, 'cols': 80}),
        label='Job A Descriptions',
        help_text='Enter Job A descriptions here.'
    )
    job_b = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10, 'cols': 80}),
        label='Job B Descriptions',
        help_text='Enter Job B descriptions here.'
    )