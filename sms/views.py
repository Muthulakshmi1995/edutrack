from io import BytesIO

from django.contrib import messages
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from .forms import AttendanceForm, StudentForm
from .models import Attendance, Batch, Certificate, Course, Student


def register_student(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('student_list')
    else:
        form = StudentForm()

    return render(request, 'sms/register_student.html', {'form': form})


def student_list(request):
    students = Student.objects.select_related('batch').all()
    return render(request, 'sms/student_list.html', {'students': students})


def batch_list(request):
    batches = Batch.objects.all()
    return render(request, 'sms/batch_list.html', {'batches': batches})


def take_attendance(request, batch_id):
    batch = get_object_or_404(Batch, pk=batch_id)
    students = list(
        Student.objects.filter(batch=batch).order_by('last_name', 'first_name')
    )
    today = timezone.localdate()
    attendance_rows = [
        (student, AttendanceForm(prefix=str(student.pk))) for student in students
    ]

    if Attendance.objects.filter(student__batch=batch, date=today).exists():
        messages.error(
            request, f'Attendance for {batch.name} has already been recorded today.'
        )
        return render(
            request,
            'sms/take_attendance.html',
            {
                'batch': batch,
                'attendance_rows': attendance_rows,
                'attendance_already_recorded': True,
            },
        )

    if request.method == 'POST':
        attendance_rows = [
            (
                student,
                AttendanceForm(request.POST, prefix=str(student.pk)),
            )
            for student in students
        ]
        forms_are_valid = [form.is_valid() for _, form in attendance_rows]
        if all(forms_are_valid):
            with transaction.atomic():
                if Attendance.objects.filter(student__batch=batch, date=today).exists():
                    messages.error(
                        request,
                        f'Attendance for {batch.name} has already been recorded today.',
                    )
                    return render(
                        request,
                        'sms/take_attendance.html',
                        {
                            'batch': batch,
                            'attendance_rows': attendance_rows,
                            'attendance_already_recorded': True,
                        },
                    )

                for student, form in attendance_rows:
                    attendance = form.save(commit=False)
                    attendance.student = student
                    attendance.date = today
                    attendance.save()

            messages.success(request, f'Attendance recorded for {batch.name}.')
            return redirect('batch_list')

    return render(
        request,
        'sms/take_attendance.html',
        {'batch': batch, 'attendance_rows': attendance_rows},
    )


def attendance_report(request, batch_id):
    batch = get_object_or_404(Batch, pk=batch_id)
    summary = {
        student.pk: {
            'student': student,
            'present': 0,
            'absent': 0,
            'late': 0,
        }
        for student in batch.students.order_by('last_name', 'first_name')
    }
    attendance_records = Attendance.objects.filter(
        student__batch=batch
    ).select_related('student')
    for attendance in attendance_records:
        summary[attendance.student_id][attendance.status.lower()] += 1

    return render(
        request,
        'sms/attendance_report.html',
        {'batch': batch, 'attendance_summary': summary.values()},
    )


def student_attendance_report(request, student_id):
    student = get_object_or_404(
        Student.objects.select_related('batch'), pk=student_id
    )
    attendance_records = student.attendance_records.order_by('date', 'pk')
    return render(
        request,
        'sms/student_attendance_report.html',
        {
            'student': student,
            'attendance_records': attendance_records,
            'courses': student.courses.order_by('name'),
        },
    )


def issue_certificate(request, student_id, course_id):
    student = get_object_or_404(Student, pk=student_id)
    course = get_object_or_404(Course, pk=course_id, students=student)
    certificate_record, _ = Certificate.objects.get_or_create(
        student=student,
        course=course,
        defaults={'date_issued': timezone.localdate()},
    )

    buffer = BytesIO()
    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height), pageCompression=0)
    pdf.setFillColor(colors.HexColor('#F7F9FC'))
    pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor('#2457C5'))
    pdf.setLineWidth(4)
    pdf.rect(28, 28, page_width - 56, page_height - 56, fill=0, stroke=1)

    pdf.setFillColor(colors.HexColor('#14213D'))
    pdf.setFont('Helvetica-Bold', 28)
    pdf.drawCentredString(page_width / 2, page_height - 125, 'CERTIFICATE OF COMPLETION')
    pdf.setFont('Helvetica', 17)
    pdf.drawCentredString(
        page_width / 2,
        page_height - 190,
        'This certificate is proudly presented to',
    )
    student_name = f'{student.first_name} {student.last_name}'
    pdf.setFont('Helvetica-Bold', 32)
    pdf.drawCentredString(page_width / 2, page_height - 245, student_name)
    pdf.setFont('Helvetica', 17)
    pdf.drawCentredString(page_width / 2, page_height - 295, 'for successfully completing')
    pdf.setFont('Helvetica-Bold', 25)
    pdf.drawCentredString(page_width / 2, page_height - 340, course.name)
    pdf.setFont('Helvetica', 13)
    pdf.drawCentredString(
        page_width / 2,
        95,
        f'Date issued: {certificate_record.date_issued:%B %d, %Y}',
    )
    pdf.save()
    buffer.seek(0)

    return FileResponse(
        buffer,
        as_attachment=True,
        filename=f'certificate-{student.pk}-{course.pk}.pdf',
    )
