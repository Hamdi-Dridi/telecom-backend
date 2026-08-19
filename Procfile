release: python manage.py migrate
web: gunicorn telecom_analytics.wsgi --log-file - --forwarded-allow-ips="*" 
