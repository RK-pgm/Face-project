from .models import Person
def current_person(request):
    person_id = request.session.get("person_id") if hasattr(request, "session") else None
    person = Person.objects.filter(pk=person_id).first() if person_id else None
    return {"person": person}
