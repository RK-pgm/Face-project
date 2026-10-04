from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .models import Person

SESSION_KEY = "person_id"


def person_login_required(view):

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        person_id = request.session.get(SESSION_KEY)
        person = Person.objects.filter(pk=person_id).first() if person_id else None
        if person is None:
            request.session.flush()
            messages.warning(request, "Please sign in first.")
            return redirect("login")
        request.person = person
        response = view(request, *args, **kwargs)

        response["Cache-Control"] = "private, no-store"
        return response

    return wrapper
