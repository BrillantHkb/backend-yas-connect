"""ANNUAIRE-D : vues self (/me) + admin, skills et certifications (ANN-14, 15, 17, 18)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.annuaire.serializers.competences import (
    CertificationCreateSerializer,
    CertificationPatchSerializer,
    SkillCreateSerializer,
    SkillPatchSerializer,
)
from apps.annuaire.services.assignment import get_target_user_or_404
from apps.annuaire.services.competences import (
    create_certification,
    create_skill,
    delete_certification,
    delete_skill,
    get_certification_or_404,
    get_own_certification_or_404,
    get_own_skill_or_404,
    get_skill_or_404,
    list_certifications,
    list_skills,
    patch_certification,
    patch_skill,
    serialize_certification,
    serialize_skill,
)
from apps.iam.services.auth_service import client_ip

# --- Self : /me/skills --------------------------------------------------------


class MeSkillListCreateView(APIView):
    required_permissions = {"GET": "annuaire.skill.read", "POST": "annuaire.skill.manage"}

    @extend_schema(tags=["Me"], responses={200: OpenApiResponse(description="Mes compétences")})
    def get(self, request):
        return Response({"success": True, "data": list_skills(request.user)})

    @extend_schema(
        tags=["Me"],
        request=SkillCreateSerializer,
        responses={
            201: OpenApiResponse(description="Compétence créée"),
            409: OpenApiResponse(description="SKILL_TAKEN"),
        },
    )
    def post(self, request):
        ser = SkillCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = create_skill(
            user=request.user, data=ser.validated_data, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data}, status=201)


class MeSkillDetailView(APIView):
    required_permissions = {
        "GET": "annuaire.skill.read",
        "PATCH": "annuaire.skill.manage",
        "DELETE": "annuaire.skill.manage",
    }

    @extend_schema(tags=["Me"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        row = get_own_skill_or_404(request.user, pk)
        return Response({"success": True, "data": serialize_skill(row)})

    @extend_schema(
        tags=["Me"],
        request=SkillPatchSerializer,
        responses={200: OpenApiResponse(), 400: OpenApiResponse(description="SKILL_LEVEL_INVALID")},
    )
    def patch(self, request, pk):
        row = get_own_skill_or_404(request.user, pk)
        data = patch_skill(
            row=row, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})

    @extend_schema(tags=["Me"], responses={204: OpenApiResponse()})
    def delete(self, request, pk):
        row = get_own_skill_or_404(request.user, pk)
        delete_skill(row=row, actor=request.user, ip=client_ip(request))
        return Response(status=204)


# --- Self : /me/certifications -------------------------------------------------


class MeCertificationListCreateView(APIView):
    required_permissions = {
        "GET": "annuaire.certification.read",
        "POST": "annuaire.certification.manage",
    }

    @extend_schema(tags=["Me"], responses={200: OpenApiResponse(description="Mes certifications")})
    def get(self, request):
        return Response({"success": True, "data": list_certifications(request.user)})

    @extend_schema(
        tags=["Me"],
        request=CertificationCreateSerializer,
        responses={
            201: OpenApiResponse(description="Certification créée"),
            400: OpenApiResponse(description="CERT_DATE_INVALID / CERT_DOCUMENT_INVALID"),
        },
    )
    def post(self, request):
        ser = CertificationCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = create_certification(
            user=request.user, data=ser.validated_data, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data}, status=201)


class MeCertificationDetailView(APIView):
    required_permissions = {
        "GET": "annuaire.certification.read",
        "PATCH": "annuaire.certification.manage",
        "DELETE": "annuaire.certification.manage",
    }

    @extend_schema(tags=["Me"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        row = get_own_certification_or_404(request.user, pk)
        return Response({"success": True, "data": serialize_certification(row)})

    @extend_schema(
        tags=["Me"],
        request=CertificationPatchSerializer,
        responses={
            200: OpenApiResponse(),
            400: OpenApiResponse(description="CERT_DOCUMENT_INVALID"),
        },
    )
    def patch(self, request, pk):
        row = get_own_certification_or_404(request.user, pk)
        data = patch_certification(
            row=row, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})

    @extend_schema(tags=["Me"], responses={204: OpenApiResponse()})
    def delete(self, request, pk):
        row = get_own_certification_or_404(request.user, pk)
        delete_certification(row=row, actor=request.user, ip=client_ip(request))
        return Response(status=204)


# --- Admin : /admin/users/{id}/skills + /admin/user-skills/{id} --------------


class AdminUserSkillListCreateView(APIView):
    required_permissions = {
        "GET": "annuaire.user_skill.read",
        "POST": "annuaire.user_skill.manage",
    }

    @extend_schema(tags=["Admin"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, user_id):
        user = get_target_user_or_404(user_id)
        return Response({"success": True, "data": list_skills(user)})

    @extend_schema(
        tags=["Admin"],
        request=SkillCreateSerializer,
        responses={201: OpenApiResponse(), 409: OpenApiResponse(description="SKILL_TAKEN")},
    )
    def post(self, request, user_id):
        user = get_target_user_or_404(user_id)
        ser = SkillCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = create_skill(
            user=user, data=ser.validated_data, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data}, status=201)


class AdminUserSkillDetailView(APIView):
    required_permissions = {
        "GET": "annuaire.user_skill.read",
        "PATCH": "annuaire.user_skill.manage",
        "DELETE": "annuaire.user_skill.manage",
    }

    @extend_schema(tags=["Admin"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        row = get_skill_or_404(pk)
        return Response({"success": True, "data": serialize_skill(row)})

    @extend_schema(tags=["Admin"], request=SkillPatchSerializer, responses={200: OpenApiResponse()})
    def patch(self, request, pk):
        row = get_skill_or_404(pk)
        data = patch_skill(
            row=row, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})

    @extend_schema(tags=["Admin"], responses={204: OpenApiResponse()})
    def delete(self, request, pk):
        row = get_skill_or_404(pk)
        delete_skill(row=row, actor=request.user, ip=client_ip(request))
        return Response(status=204)


# --- Admin : /admin/users/{id}/certifications + /admin/user-certifications/{id}


class AdminUserCertificationListCreateView(APIView):
    required_permissions = {
        "GET": "annuaire.user_certification.read",
        "POST": "annuaire.user_certification.manage",
    }

    @extend_schema(tags=["Admin"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, user_id):
        user = get_target_user_or_404(user_id)
        return Response({"success": True, "data": list_certifications(user)})

    @extend_schema(
        tags=["Admin"],
        request=CertificationCreateSerializer,
        responses={
            201: OpenApiResponse(),
            400: OpenApiResponse(description="CERT_DATE_INVALID / CERT_DOCUMENT_INVALID"),
        },
    )
    def post(self, request, user_id):
        user = get_target_user_or_404(user_id)
        ser = CertificationCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = create_certification(
            user=user, data=ser.validated_data, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data}, status=201)


class AdminUserCertificationDetailView(APIView):
    required_permissions = {
        "GET": "annuaire.user_certification.read",
        "PATCH": "annuaire.user_certification.manage",
        "DELETE": "annuaire.user_certification.manage",
    }

    @extend_schema(tags=["Admin"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        row = get_certification_or_404(pk)
        return Response({"success": True, "data": serialize_certification(row)})

    @extend_schema(
        tags=["Admin"], request=CertificationPatchSerializer, responses={200: OpenApiResponse()}
    )
    def patch(self, request, pk):
        row = get_certification_or_404(pk)
        data = patch_certification(
            row=row, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})

    @extend_schema(tags=["Admin"], responses={204: OpenApiResponse()})
    def delete(self, request, pk):
        row = get_certification_or_404(pk)
        delete_certification(row=row, actor=request.user, ip=client_ip(request))
        return Response(status=204)
