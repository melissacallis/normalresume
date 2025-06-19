
from django.urls import path
from .views import home, generate_pdf, load_edit_resume  # Import the necessary views

urlpatterns = [
    path('', home, name='home'),  # Directly use 'home' without 'views.'
    path('generate-pdf/', generate_pdf, name='generate_pdf'),  # Directly use 'generate_pdf'
    path('edit_resume/', load_edit_resume, name='load_edit_resume'),  # Directly use 'load_edit_resume'
]