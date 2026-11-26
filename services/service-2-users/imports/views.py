from django.shortcuts import render

# Create your views here.
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdmin

from .models import ImportJob
from .serializers import ImportJobSerializer, ImportUploadSerializer
from .tasks import start_import


class ImportCreateView(APIView):
    """POST /api/users/import/ : dépose un fichier, le traitement se fait en arrière-plan."""

    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser]

    @extend_schema(request=ImportUploadSerializer, responses={202: ImportJobSerializer})
    def post(self, request):
        serializer = ImportUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        job = ImportJob.objects.create(
            file=upload, filename=upload.name, created_by=request.user.id
        )
        transaction.on_commit(lambda: start_import(job.id))
        return Response(ImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class ImportDetailView(generics.RetrieveAPIView):
    """GET /api/users/import/{id}/ : statut, compteurs et rapport d'erreurs."""

    queryset = ImportJob.objects.all()
    serializer_class = ImportJobSerializer
    permission_classes = [IsAdmin]
