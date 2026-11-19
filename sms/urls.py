from django.urls import path

from . import views


urlpatterns = [
    path('students/register/', views.register_student, name='register_student'),
    path('students/', views.student_list, name='student_list'),
    path('batches/', views.batch_list, name='batch_list'),
    path(
        'batches/<int:batch_id>/attendance/',
        views.take_attendance,
        name='take_attendance',
    ),
    path(
        'batches/<int:batch_id>/attendance/report/',
        views.attendance_report,
        name='attendance_report',
    ),
    path(
        'students/<int:student_id>/attendance/',
        views.student_attendance_report,
        name='student_attendance_report',
    ),
    path(
        'students/<int:student_id>/courses/<int:course_id>/certificate/',
        views.issue_certificate,
        name='issue_certificate',
    ),
]
