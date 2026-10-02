"""Job catalog browse API."""
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import JobPosition


@api_view(["GET"])
def job_list(request):
    qs = JobPosition.objects.filter(is_active=True)
    category = request.query_params.get("category")
    level = request.query_params.get("level")
    if category:
        qs = qs.filter(category=category)
    if level:
        qs = qs.filter(level=level)
    return Response([
        {
            "id": j.id, "category": j.category, "title": j.title, "level": j.level,
            "description": j.description,
            "skill_requirements": j.skill_requirements,
            "affinity_tags": j.affinity_tags,
            "knowledge_points": j.knowledge_points,
            "coding_topics": j.coding_topics,
            "interview_focus": j.interview_focus,
        }
        for j in qs
    ])
