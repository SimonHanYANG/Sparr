from rest_framework import serializers

from .models import Resume, ResumeVersion


class ResumeVersionSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeVersion
        fields = ["id", "version_no", "change_note", "created_at"]


class ResumeVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeVersion
        fields = ["id", "version_no", "structured_json", "change_note", "created_at"]


class ResumeSerializer(serializers.ModelSerializer):
    current_version = ResumeVersionSummarySerializer(read_only=True)

    class Meta:
        model = Resume
        fields = ["id", "title", "source_filename", "parse_status", "parse_error",
                  "mineru_batch_id", "current_version", "created_at", "updated_at"]
        read_only_fields = fields


class ResumeDetailSerializer(serializers.ModelSerializer):
    current_version = ResumeVersionSerializer(read_only=True)
    versions = ResumeVersionSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Resume
        fields = ["id", "title", "source_filename", "parse_status", "parse_error",
                  "mineru_markdown", "mineru_batch_id", "current_version", "versions",
                  "created_at", "updated_at"]
        read_only_fields = fields


class VersionCreateSerializer(serializers.Serializer):
    """Manual save/rollback — always creates a NEW version (PLAN.md §5.1)."""

    structured_json = serializers.JSONField()
    change_note = serializers.CharField(required=False, allow_blank=True, max_length=300)

    def validate_structured_json(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("structured_json must be an object")
        for key in ("basics", "education", "skills", "projects", "work_experiences", "awards"):
            if key not in value:
                raise serializers.ValidationError(f"missing field: {key}")
        return value
