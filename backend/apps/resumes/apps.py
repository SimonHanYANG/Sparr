from django.apps import AppConfig


class ResumesConfig(AppConfig):
    name = 'apps.resumes'

    def ready(self):
        # Import task modules so @background registers them in the web process.
        from . import tasks  # noqa: F401
