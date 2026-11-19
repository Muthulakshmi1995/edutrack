from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Attendance, Batch, Certificate, Course, Student


class CourseCertificateModelTests(TestCase):
    def setUp(self):
        batch = Batch.objects.create(name='Spring', start_date=date(2026, 1, 1))
        self.student = Student.objects.create(
            first_name='Alex',
            last_name='Rivera',
            email='alex@example.com',
            phone_number='5551234567',
            batch=batch,
        )
        self.course = Course.objects.create(
            name='Python Fundamentals',
            description='Core Python programming',
        )

    def test_student_can_enroll_in_multiple_courses(self):
        second_course = Course.objects.create(
            name='Django Basics',
            description='Django web development',
        )
        self.student.courses.add(self.course, second_course)

        self.assertSetEqual(
            set(self.student.courses.all()), {self.course, second_course}
        )

    def test_certificate_records_issue_details_and_rejects_duplicates(self):
        certificate = Certificate.objects.create(
            student=self.student,
            course=self.course,
            date_issued=date(2026, 11, 18),
        )

        self.assertEqual(certificate.student, self.student)
        self.assertEqual(certificate.course, self.course)
        self.assertEqual(certificate.date_issued, date(2026, 11, 18))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Certificate.objects.create(
                    student=self.student,
                    course=self.course,
                    date_issued=date(2026, 11, 19),
                )


class StudentViewsTests(TestCase):
    def setUp(self):
        self.batch = Batch.objects.create(name='Spring', start_date=date(2026, 1, 1))

    def test_homepage_redirects_to_student_list(self):
        response = self.client.get('/')

        self.assertRedirects(response, reverse('student_list'))

    def test_registration_page_renders_form(self):
        response = self.client.get(reverse('register_student'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="first_name"')
        self.assertContains(response, 'name="batch"')

    def test_valid_registration_saves_student_and_redirects(self):
        response = self.client.post(
            reverse('register_student'),
            {
                'first_name': 'Alex',
                'last_name': 'Rivera',
                'email': 'alex@example.com',
                'phone_number': '5551234567',
                'batch': self.batch.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('student_list'))
        self.assertTrue(Student.objects.filter(email='alex@example.com').exists())

    def test_invalid_registration_does_not_save_student(self):
        response = self.client.post(reverse('register_student'), {'email': 'not-an-email'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Student.objects.count(), 0)
        self.assertFormError(
            response.context['form'], 'email', 'Enter a valid email address.'
        )

    def test_student_list_shows_student_and_batch(self):
        Student.objects.create(
            first_name='Alex',
            last_name='Rivera',
            email='alex@example.com',
            phone_number='5551234567',
            batch=self.batch,
        )

        response = self.client.get(reverse('student_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alex Rivera')
        self.assertContains(response, 'alex@example.com')
        self.assertContains(response, 'Spring')
        self.assertContains(
            response,
            reverse(
                'student_attendance_report',
                args=[Student.objects.get(email='alex@example.com').pk],
            ),
        )


class AttendanceViewsTests(TestCase):
    def setUp(self):
        self.batch = Batch.objects.create(name='Spring', start_date=date(2026, 1, 1))
        self.student = Student.objects.create(
            first_name='Alex',
            last_name='Rivera',
            email='alex@example.com',
            phone_number='5551234567',
            batch=self.batch,
        )
        self.url = reverse('take_attendance', args=[self.batch.pk])

    def test_attendance_page_shows_students_and_status_choices(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alex Rivera')
        self.assertContains(response, 'Present')
        self.assertContains(response, 'Absent')
        self.assertContains(response, 'Late')

    def test_post_saves_attendance_for_today(self):
        response = self.client.post(
            self.url, {f'{self.student.pk}-status': Attendance.Status.PRESENT}
        )

        self.assertRedirects(response, reverse('batch_list'))
        attendance = Attendance.objects.get(student=self.student)
        self.assertEqual(attendance.date, timezone.localdate())
        self.assertEqual(attendance.status, Attendance.Status.PRESENT)

    def test_duplicate_attendance_is_blocked(self):
        Attendance.objects.create(
            student=self.student,
            date=timezone.localdate(),
            status=Attendance.Status.PRESENT,
        )

        get_response = self.client.get(self.url)
        post_response = self.client.post(
            self.url, {f'{self.student.pk}-status': Attendance.Status.ABSENT}
        )

        self.assertContains(get_response, 'already been recorded')
        self.assertNotContains(get_response, 'Save attendance')
        self.assertContains(post_response, 'already been recorded')
        self.assertEqual(Attendance.objects.count(), 1)

    def test_batch_list_links_to_attendance_page(self):
        response = self.client.get(reverse('batch_list'))

        self.assertContains(response, 'Spring')
        self.assertContains(response, self.url)

    def test_batch_report_counts_statuses_and_includes_students_without_records(self):
        second_student = Student.objects.create(
            first_name='Sam',
            last_name='Lee',
            email='sam@example.com',
            phone_number='5557654321',
            batch=self.batch,
        )
        for day, status in (
            (1, Attendance.Status.PRESENT),
            (2, Attendance.Status.PRESENT),
            (3, Attendance.Status.ABSENT),
            (4, Attendance.Status.LATE),
        ):
            Attendance.objects.create(
                student=self.student,
                date=date(2026, 1, day),
                status=status,
            )

        response = self.client.get(
            reverse('attendance_report', args=[self.batch.pk])
        )

        summary = {
            row['student'].pk: row for row in response.context['attendance_summary']
        }
        self.assertEqual(summary[self.student.pk]['present'], 2)
        self.assertEqual(summary[self.student.pk]['absent'], 1)
        self.assertEqual(summary[self.student.pk]['late'], 1)
        self.assertEqual(summary[second_student.pk]['present'], 0)
        self.assertContains(response, 'Sam Lee')

    def test_student_report_shows_attendance_in_chronological_order(self):
        later = Attendance.objects.create(
            student=self.student,
            date=date(2026, 1, 2),
            status=Attendance.Status.LATE,
        )
        earlier = Attendance.objects.create(
            student=self.student,
            date=date(2026, 1, 1),
            status=Attendance.Status.ABSENT,
        )

        response = self.client.get(
            reverse('student_attendance_report', args=[self.student.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context['attendance_records']), [earlier, later]
        )
        self.assertContains(response, 'status--absent')
        self.assertContains(response, 'status--late')


class CertificateViewsTests(TestCase):
    def setUp(self):
        batch = Batch.objects.create(name='Spring', start_date=date(2026, 1, 1))
        self.course = Course.objects.create(
            name='Python Fundamentals',
            description='Core Python programming',
        )
        self.student = Student.objects.create(
            first_name='Alex',
            last_name='Rivera',
            email='alex@example.com',
            phone_number='5551234567',
            batch=batch,
        )
        self.student.courses.add(self.course)
        self.url = reverse(
            'issue_certificate',
            args=[self.student.pk, self.course.pk],
        )

    def test_issue_certificate_downloads_pdf_and_does_not_duplicate_record(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])
        pdf_content = b''.join(response.streaming_content)
        self.assertTrue(pdf_content.startswith(b'%PDF-'))
        self.assertIn(b'Alex Rivera', pdf_content)
        self.assertIn(b'Python Fundamentals', pdf_content)
        self.assertIn(b'Date issued:', pdf_content)
        certificate = Certificate.objects.get(student=self.student, course=self.course)
        self.assertEqual(certificate.date_issued, timezone.localdate())

        self.client.get(self.url)
        self.assertEqual(Certificate.objects.count(), 1)

    def test_certificate_requires_course_enrollment(self):
        self.student.courses.clear()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Certificate.objects.exists())

    def test_student_report_links_to_enrolled_course_certificate(self):
        response = self.client.get(
            reverse('student_attendance_report', args=[self.student.pk])
        )

        self.assertContains(response, 'Issue Certificate')
        self.assertContains(response, self.url)
