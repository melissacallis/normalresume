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
model = client.models.get(model="gemini-2.5-flash")


def generate_job_c(job_1, job_2, target_job):
    prompt = f"""
You are an assistant helping transform a user's resume to align with a job description. 

The user's FIRST past experience (Job 1) is:
'{job_1}'

The user's SECOND past experience (Job 2) is:
'{job_2}'

The target job description (Target Job) is:
'{target_job}'

Instructions:
1. Don't copy: Don't use the Target Job word-for-word, except for technical terms.
2. Reword: Reword Job 1 and Job 2 to match the Target Job's needs, staying honest to what the person actually did.
3. Professional Summary: Generate a single 3-sentence summary based on both jobs to match the Target Job.
4. Job 1: Generate exactly 5 tailored bullet points for Job 1.
5. Job 2: Generate exactly 5 tailored bullet points for Job 2.
6. No Management: Do not mention managing staff.

Strictly use this exact format with these exact headers:

**Professional Summary:**
[Insert summary here]

**Job 1:**
- [Job 1 bullet]
- [Job 1 bullet]
- [Job 1 bullet]
- [Job 1 bullet]
- [Job 1 bullet]

**Job 2:**
- [Job 2 bullet]
- [Job 2 bullet]
- [Job 2 bullet]
- [Job 2 bullet]
- [Job 2 bullet]
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text

def generate_skills_match(skills, target_job):
    prompt = f"""
You are a career coach helping someone see how their real skills and experience line up with a target job. This is an honesty exercise, not a sales pitch: every item you produce must be something the person could truthfully defend if asked about it in an interview. Never invent a tool, certification, or experience they did not list.

The person's skills and experience are:
'{skills}'

The target job description is:
'{target_job}'

Instructions:
1. Direct Matches: List skills/tools the person already listed that also appear (or clearly correspond) in the target job description. Use the person's own wording.
2. Transferable Skills: For real experience the person listed that isn't named the same way in the job description but genuinely applies, write one sentence each in the form "Your experience with [what they actually did] transfers to [what the job wants] because [true, specific reason]." Only use skills/experience actually listed — do not add new ones.
3. Real Gaps: List things the target job asks for that the person's listed skills do not cover. Be direct and specific. Do not soften or omit real gaps.
4. Stay grounded strictly in what was provided above. If a bucket has nothing to list, leave it empty rather than inventing content.

Strictly use this exact format with these exact headers:

**Direct Matches:**
- [match]

**Transferable Skills:**
- [reframe]

**Real Gaps:**
- [gap]
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text

def parse_skills_match_output(skills_match_output):
    if not skills_match_output:
        return [], [], []

    direct_matches = []
    transferable_skills = []
    real_gaps = []

    try:
        parts = skills_match_output.split("**Transferable Skills:**")
        if len(parts) == 2:
            direct_text = parts[0].replace("**Direct Matches:**", "").strip()
            direct_matches = [line.strip('- ').strip() for line in direct_text.split('\n') if line.strip()]

            gap_parts = parts[1].split("**Real Gaps:**")
            if len(gap_parts) == 2:
                transferable_text = gap_parts[0].strip()
                gaps_text = gap_parts[1].strip()

                transferable_skills = [line.strip('- ').strip() for line in transferable_text.split('\n') if line.strip()]
                real_gaps = [line.strip('- ').strip() for line in gaps_text.split('\n') if line.strip()]
    except Exception as e:
        print("Warning: Unexpected Gemini output format for skills match.", e)

    return direct_matches, transferable_skills, real_gaps

def parse_job_c_output(job_c_output):
    if not job_c_output:
        return "", [], []

    professional_summary = ""
    responsibilities_1 = []
    responsibilities_2 = []

    try:
        parts = job_c_output.split("**Job 1:**")
        if len(parts) == 2:
            professional_summary = parts[0].replace("**Professional Summary:**", "").strip()
            
            job_parts = parts[1].split("**Job 2:**")
            if len(job_parts) == 2:
                job_1_text = job_parts[0].strip()
                job_2_text = job_parts[1].strip()
                
                responsibilities_1 = [resp.strip('- ') for resp in job_1_text.split('\n') if resp.strip()]
                responsibilities_2 = [resp.strip('- ') for resp in job_2_text.split('\n') if resp.strip()]
    except Exception as e:
        print("Warning: Unexpected Gemini output format.", e)
        
    return professional_summary, responsibilities_1, responsibilities_2

@csrf_exempt
def home(request):
    if request.method == 'POST':
        # Prepare context with standard fields AND the new Job 1 and Job 2 fields
        context = {
            'name': request.POST.get('name', ''),
            'job_title': request.POST.get('job_title', ''),
            'linkedin': request.POST.get('linkedin', ''),
            'email': request.POST.get('email', ''),
            'phone': request.POST.get('phone', ''),
            'city': request.POST.get('city', ''),
            
            'job_1_title': request.POST.get('job_1_title', ''),
            'job_1_company': request.POST.get('job_1_company', ''),
            'job_1_dates': request.POST.get('job_1_dates', ''),
            
            'job_2_title': request.POST.get('job_2_title', ''),
            'job_2_company': request.POST.get('job_2_company', ''),
            'job_2_dates': request.POST.get('job_2_dates', ''),
            
            'certifications': [cert.strip() for cert in request.POST.getlist('certifications[]', []) if cert.strip()],
            'education': list(zip(request.POST.getlist('school[]', []), request.POST.getlist('degree[]', []), request.POST.getlist('start_date[]', []), request.POST.getlist('end_date[]', []))),
            'skills': request.POST.get('skills', '').split(','),
        }

        # Grab the duties and the target job description to send to the AI
        job_1_duties = request.POST.get('job_1_duties', '')
        job_2_duties = request.POST.get('job_2_duties', '')
        job_b = request.POST.get('job_b', '')
        skills_raw = request.POST.get('skills', '')

        # Generate the AI content
        job_c_output = generate_job_c(job_1_duties, job_2_duties, job_b)
        professional_summary, responsibilities_1, responsibilities_2 = parse_job_c_output(job_c_output)

        skills_match_output = generate_skills_match(skills_raw, job_b)
        direct_matches, transferable_skills, real_gaps = parse_skills_match_output(skills_match_output)

        # Add the AI generated results to the context
        context['professional_summary'] = professional_summary
        context['responsibilities_1'] = responsibilities_1
        context['responsibilities_2'] = responsibilities_2
        context['direct_matches'] = direct_matches
        context['transferable_skills'] = transferable_skills
        context['real_gaps'] = real_gaps

        return render(request, 'resume_app/output.html', context)

    return render(request, 'resume_app/home.html')

@csrf_exempt
def generate_pdf(request):
    if request.method == 'POST':
        context = {
            'name': request.POST.get('name', ''),
            'job_title': request.POST.get('job_title', ''),
            'linkedin': request.POST.get('linkedin', ''),
            'email': request.POST.get('email', ''),
            'phone': request.POST.get('phone', ''),
            'city': request.POST.get('city', ''),
            
            'job_1_title': request.POST.get('job_1_title', ''),
            'job_1_company': request.POST.get('job_1_company', ''),
            'job_1_dates': request.POST.get('job_1_dates', ''),
            'responsibilities_1': request.POST.get('responsibilities_1', '').split('|'),
            
            'job_2_title': request.POST.get('job_2_title', ''),
            'job_2_company': request.POST.get('job_2_company', ''),
            'job_2_dates': request.POST.get('job_2_dates', ''),
            'responsibilities_2': request.POST.get('responsibilities_2', '').split('|'),
            
            'professional_summary': request.POST.get('professional_summary', ''),
            'education': [tuple(edu.split('~~')) for edu in request.POST.get('education', '').split('|') if edu.strip()],
            'certifications': request.POST.get('certifications', '').split(','),
            'skills': request.POST.get('skills', '').split(','),
        }

        html_string = render_to_string('resume_app/resume_pdf.html', context)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{context["name"]}_Resume.pdf"'
        HTML(string=html_string).write_pdf(response)
        return response

    return redirect('home')

@csrf_exempt
def load_edit_resume(request):
    if request.method == 'POST':
        context = {
            'name': request.POST.get('name', ''),
            'job_title': request.POST.get('job_title', ''),
            'linkedin': request.POST.get('linkedin', ''),
            'email': request.POST.get('email', ''),
            'phone': request.POST.get('phone', ''),
            'city': request.POST.get('city', ''),
            
            'job_1_title': request.POST.get('job_1_title', ''),
            'job_1_company': request.POST.get('job_1_company', ''),
            'job_1_dates': request.POST.get('job_1_dates', ''),
            'responsibilities_1': request.POST.get('responsibilities_1', '').split('|'),
            
            'job_2_title': request.POST.get('job_2_title', ''),
            'job_2_company': request.POST.get('job_2_company', ''),
            'job_2_dates': request.POST.get('job_2_dates', ''),
            'responsibilities_2': request.POST.get('responsibilities_2', '').split('|'),
            
            'professional_summary': request.POST.get('professional_summary', ''),
            'education': [tuple(edu.split('~~')) for edu in request.POST.get('education', '').split('|') if edu.strip()],
            'certifications': request.POST.get('certifications', '').split(','),
            'skills': request.POST.get('skills', '').split(','),
        }
        return render(request, 'resume_app/edit_resume.html', context)

    return redirect('home')