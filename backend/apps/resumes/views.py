"""Resume APIs (PLAN.md §6): upload/parse, versions, edit, rollback, reparse."""
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from core.storage import save_upload
from core.tasks import dispatch

from .models import Resume, ResumeVersion
from .serializers import (
    ResumeDetailSerializer,
    ResumeSerializer,
    ResumeVersionSerializer,
    VersionCreateSerializer,
)

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


class ResumeViewSet(viewsets.ModelViewSet):
    serializer_class = ResumeSerializer
    http_method_names = ["get", "post", "delete"]
    pagination_class = None  # plain array — small personal lists

    def get_queryset(self):
        return Resume.objects.filter(user=self.request.user).select_related("current_version")

    def get_serializer_class(self):
        return ResumeDetailSerializer if self.action == "retrieve" else ResumeSerializer

    @action(detail=True, methods=["post"])
    def reparse(self, request, pk=None):
        """Re-run MinerU + extraction (e.g. after adding API keys)."""
        resume = self.get_object()
        resume.parse_status = Resume.ParseStatus.UPLOADED
        resume.parse_error = ""
        resume.save(update_fields=["parse_status", "parse_error", "updated_at"])
        dispatch("parse_resume_task", resume.pk)
        return Response(ResumeSerializer(resume).data)

    @action(detail=True, methods=["get", "post"], url_path="versions")
    def versions(self, request, pk=None):
        resume = self.get_object()
        if request.method == "GET":
            return Response(ResumeVersionSerializer(resume.versions.all(), many=True).data)
        # POST: manual save creates a new version
        serializer = VersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = _create_version(
            resume,
            serializer.validated_data["structured_json"],
            serializer.validated_data.get("change_note", "手动编辑"),
        )
        return Response(ResumeVersionSerializer(version).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="versions/(?P<vid>[0-9]+)")
    def version_detail(self, request, pk=None, vid=None):
        resume = self.get_object()
        version = get_object_or_404(ResumeVersion, resume=resume, pk=vid)
        return Response(ResumeVersionSerializer(version).data)

    @action(detail=True, methods=["post"], url_path="versions/(?P<vid>[0-9]+)/rollback")
    def rollback(self, request, pk=None, vid=None):
        resume = self.get_object()
        version = get_object_or_404(ResumeVersion, resume=resume, pk=vid)
        new_version = _create_version(
            resume, version.structured_json,
            f"回滚到 v{version.version_no}",
        )
        return Response(ResumeVersionSerializer(new_version).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_resume(request):
    """multipart/form-data: file=<pdf>, title=<optional> -> Resume + background parse."""
    upload = request.FILES.get("file")
    if upload is None:
        return Response({"file": ["required"]}, status=status.HTTP_400_BAD_REQUEST)
    if not upload.name.lower().endswith(".pdf"):
        return Response({"file": ["仅支持 PDF 文件"]}, status=status.HTTP_400_BAD_REQUEST)
    if upload.size > MAX_PDF_BYTES:
        return Response({"file": ["PDF 不能超过 10MB"]}, status=status.HTTP_400_BAD_REQUEST)

    path = save_upload(f"resumes/{request.user.id}/{upload.name}", upload.read())
    title = (request.data.get("title") or upload.name.removesuffix(".pdf"))[:200]
    resume = Resume.objects.create(
        user=request.user, title=title,
        source_path=path, source_filename=upload.name,
    )
    dispatch("parse_resume_task", resume.pk)
    return Response(ResumeSerializer(resume).data, status=status.HTTP_201_CREATED)


def _create_version(resume: Resume, structured_json: dict, change_note: str) -> ResumeVersion:
    next_no = (resume.versions.order_by("-version_no").first().version_no + 1
               if resume.versions.exists() else 1)
    version = ResumeVersion.objects.create(
        resume=resume, version_no=next_no,
        structured_json=structured_json, change_note=change_note[:300],
    )
    resume.current_version = version
    resume.save(update_fields=["current_version", "updated_at"])
    return version
