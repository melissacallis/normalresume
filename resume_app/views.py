from django.shortcuts import render

import os
import io
from django.shortcuts import render
from django.http import HttpResponse, FileResponse
from google.generativeai import configure, GenerativeModel
from .forms import JobDescriptionForm

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from django.views.decorators.csrf import csrf_exempt
from django.templatetags.static import static
from weasyprint import HTML, CSS

import tempfile
from django.template.loader import render_to_string
import re
import os
from dotenv import load_dotenv

load_dotenv()  # this reads .env into os.environ

API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError("GOOGLE_API_KEY not set in environment")

# Use client-based initialization instead of genai.configure
from google import genai
client = genai.Client(api_key=API_KEY)
model = client.models.get(model="gemini-2.0-flash")


def generate_job_c(job_a, job_b):
    prompt = f"""
You are an assistant helping transform a user's resume to align with a job description. 

The user's current experience (Job A) is:

'{job_a}'

The target job description (Job B) is:

'{job_b}'

Instructions:

1. **Don’t copy**: Don’t use any parts of Job B word-for-word, except for technical terms or job titles.  
2. **Be honest**: Don’t make up any new skills or experience that aren’t already listed in Job A. Just focus on making their existing experience sound closer to Job B. 
3. **Reword**: Take what Job B asks for and reword what the person has done in Job A to match it.  
4. **Make it sound better**: Adjust the skills and tasks from Job A to match about 80% of what Job B wants. Use fancy words or industry terms from Job B where it makes sense.  
5. **Professional Summary**: Start with a 3 sentence paragraph about the person’s skills, accomplishments, and goals. This should be based on Job A but written to match what Job B is asking for. 
6. **Key Skills and Accomplishments**: After the summary, make a section called **'Key Skills and Accomplishments'** with bullet points. Each point should list something the person did in Job A, but make it sound like it fits Job B.  
7. **Keep it real**: Stay true to what the person really did in Job A. If Job B mentions tasks that are way more advanced, simplify them to match what the person actually did.  
8. **Simplify advanced stuff**: If Job B talks about leading a big team but Job A only involves working with small groups or alone, make sure to reflect that difference.  
9. **Use easy language**: Rewrite the descriptions of Job A and Job B so they sound simple and easy to understand, like a high school student wrote them.
10. **Limit the bullet points**: Only include **five (5)** bullet points under **Key Skills and Accomplishments**. Choose the five most relevant or impressive ones based on Job B.

Make sure the output format strictly follows this structure:

**Professional Summary:**

[The professional summary as a single paragraph in first person with approximately 100 words]

**Key Skills and Accomplishments:**

- [Skill or accomplishment 1]
- [Skill or accomplishment 2]
- [Skill or accomplishment 3]
- [Skill or accomplishment 4]
- [Skill or accomplishment 5]

Ensure that both sections are distinct and follow the format above. No other structure should be included.
    """

    # Use client.models.generate_content instead of outdated method
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    print(response.text)  # useful for debugging in logs
    return response.text

# Assuming the generate_job_c function is in a file called job_generation.py
@csrf_exempt
def home(request):
    if request.method == 'POST':
        # Collect and process form data
        name = request.POST.get('name', '')
        job_title = request.POST.get('job_title', '')
        linkedin = request.POST.get('linkedin', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        city = request.POST.get('city', '')
        job_a = request.POST.get('job_a', '')
        job_b = request.POST.get('job_b', '')

        # Retrieve certifications as a list
        certifications = request.POST.getlist('certifications[]', [])
        certifications = [cert.strip() for cert in certifications if cert.strip()]

        # Education processing
        schools = request.POST.getlist('school[]', [])
        degrees = request.POST.getlist('degree[]', [])
        start_dates = request.POST.getlist('start_date[]', [])
        end_dates = request.POST.getlist('end_date[]', [])
        education = list(zip(schools, degrees, start_dates, end_dates))

        # Skills
        skills = request.POST.get('skills', '').split(',')

        # Responsibilities and job content generation
        job_c_output = generate_job_c(job_a, job_b)
        professional_summary, responsibilities = parse_job_c_output(job_c_output)

        # Prepare context
        context = {
            'name': name,
            'job_title': job_title,
            'linkedin': linkedin,
            'email': email,
            'phone': phone,
            'city': city,
            'professional_summary': professional_summary,
            'responsibilities': responsibilities,
            'certifications': certifications,  # Certifications as a list
            'education': education,  # Education as a list of tuples
            'skills': skills,  # Skills as a list
        }

        # Render output.html
        return render(request, 'resume_app/output.html', context)

    return render(request, 'resume_app/home.html')




@csrf_exempt
def generate_pdf(request):
    if request.method == 'POST':
        # Retrieve context from POST
        context = {
            'name': request.POST.get('name', ''),
            'job_title': request.POST.get('job_title', ''),
            'linkedin': request.POST.get('linkedin', ''),
            'email': request.POST.get('email', ''),
            'phone': request.POST.get('phone', ''),
            'city': request.POST.get('city', ''),
            'professional_summary': request.POST.get('professional_summary', ''),
            'responsibilities': request.POST.get('responsibilities', '').split('|'),
            'education': [
                tuple(edu.split('~~')) for edu in request.POST.get('education', '').split('|') if edu.strip()
            ],
            'certifications': request.POST.get('certifications', '').split(','),  # Processed as a list
            'skills': request.POST.get('skills', '').split(','),
        }

        # Debugging certifications
        print("Certifications in generate_pdf:", context['certifications'])

        # Render PDF
        html_string = render_to_string('resume_app/resume_pdf.html', context)

        # Generate the PDF
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{context["name"]}_Resume.pdf"'
        HTML(string=html_string).write_pdf(response)

        return response

    return redirect('home')

def parse_job_c_output(job_c_output):
    if not job_c_output:
        return "", []  # Return empty values if there's no content

    # Use a flexible regex to split the text into the two main sections
    # Capture both "Professional Summary" and "Key Skills and Accomplishments" in separate groups
    match = re.search(r'\*\*Professional Summary:\*\*(.*?)\*\*Key Skills and Accomplishments:\*\*(.*)', job_c_output, re.DOTALL)

    if match:
        # Extract the professional summary and responsibilities sections
        professional_summary = match.group(1).strip()  # Group 1 is the professional summary text
        responsibilities_section = match.group(2).strip()  # Group 2 is the key skills and accomplishments

        # Split the responsibilities by newlines (each starting with a dash)
        responsibilities = [resp.strip('- ') for resp in responsibilities_section.split('\n') if resp.strip() and resp.endswith('.')]

        return professional_summary, responsibilities
    else:
        # If the structure is not as expected, log a warning for debugging
        print("Warning: Unexpected Gemini output format.")
        return "", []


@csrf_exempt
def load_edit_resume(request):
    if request.method == 'POST':
        # Collect data sent from output.html
        name = request.POST.get('name')
        job_title = request.POST.get('job_title')
        linkedin = request.POST.get('linkedin')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        city = request.POST.get('city')
        professional_summary = request.POST.get('professional_summary')
        responsibilities = request.POST.get('responsibilities', '').split('|')
        certifications = request.POST.get('certifications', '').split(',')
        education = [tuple(edu.split('~~')) for edu in request.POST.get('education', '').split('|')]
        skills = request.POST.get('skills', '').split(',')

        # Prepare context with the data to be passed to the edit_resume.html template
        context = {
            'name': name,
            'job_title': job_title,
            'linkedin': linkedin,
            'email': email,
            'phone': phone,
            'city': city,
            'professional_summary': professional_summary,
            'responsibilities': responsibilities,
            'certifications': certifications,
            'education': education,
            'skills': skills,
        }

        # Render the edit_resume.html template with the pre-filled data
        return render(request, 'resume_app/edit_resume.html', context)

    # If not a POST request, redirect to the home page or handle accordingly
    return redirect('home')
