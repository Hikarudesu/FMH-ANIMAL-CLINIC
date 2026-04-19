from django.db.models import Count
from patients.models import Pet
from employees.models import StaffMember
for s in StaffMember.objects.all():
    print(s.user.username, Pet.objects.filter(appointments__preferred_vet=s).distinct().count(), list(Pet.objects.filter(appointments__preferred_vet=s).values('clinical_status__name').annotate(c=Count('id', distinct=True)).order_by('-c')))
