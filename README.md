# Face Sign-in and Sales Counter

A local Django application that verifies members using their name, PIN, and face. Successful sign-ins can be recorded in Google Sheets. Staff can record a sale for each visit and review daily totals.

## Features

- Face detection and matching in the browser with face-api.js.
- Django 5 and SQLite for member records and sign-in history.
- PINs stored as password hashes.
- Member dashboard and face-photo updates.
- Staff-only sales queue, sale entry, and daily reports.
- Local copies of face-api.js, its models, Bootstrap, and fonts.

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies with `python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set any desired configuration.
4. Run `python manage.py migrate`.
5. Create a staff account with `python manage.py createsuperuser`.
6. Start the site with `python manage.py runserver` and open `http://localhost:8000`.

Use `/counter/` and `/reports/daily/` while signed in with a Django staff account. Member sign-in uses a separate name, PIN, and face session.

## Google Sheets

Google Sheets integration is optional. Configure the sheet ID and a service-account credential in `.env`, then share the sheet with the service account. When Sheets is not configured, local sign-in continues to work.

## Face data

The application stores a face photo and a 128-value face descriptor after the member gives consent. Do not publish member photos, descriptors, database files, or service-account credentials. The default settings are intended for local development, not public deployment.

## Troubleshooting

- Camera access requires `http://localhost:8000` or HTTPS.
- If a model file is missing, run `python scripts/download_face_api.py`.
- If Django is missing, activate the virtual environment and reinstall `requirements.txt`.
- Inspect the Django admin for sign-in and Google Sheets delivery status.
