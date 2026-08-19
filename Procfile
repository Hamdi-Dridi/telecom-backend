release: python manage.py migrate && python manage.py collectstatic --noinput
web: gunicorn telecom_analytics.wsgi --log-file - --forwarded-allow-ips="*" 
