"""Package serializers IAM (auth, register, devices)."""

from apps.iam.serializers.auth import (
    AuthSuccessSerializer,
    BackupRegenSerializer,
    LoginSerializer,
    MfaChallengeEnvelopeSerializer,
    MfaChallengeSerializer,
    MfaVerifySerializer,
    RefreshSerializer,
    UserPublicSerializer,
)
from apps.iam.serializers.compliance import (
    OnboardingEnvelopeSerializer,
    OnboardingPatchSerializer,
    TosAcceptSerializer,
    TosEnvelopeSerializer,
)
from apps.iam.serializers.devices import (
    DeviceCurrentPatchSerializer,
    DeviceLinkConfirmSerializer,
    DeviceLinkStartSerializer,
    DeviceListEnvelopeSerializer,
    DeviceOutSerializer,
    DevicePatchSerializer,
    DeviceSpecSerializer,
)
from apps.iam.serializers.register import (
    CheckAdSerializer,
    RegisterAdSerializer,
    RegisterLocalSerializer,
    RejectUserSerializer,
    ResendVerificationSerializer,
    VerifyEmailSerializer,
)

__all__ = [
    "AuthSuccessSerializer",
    "BackupRegenSerializer",
    "CheckAdSerializer",
    "DeviceCurrentPatchSerializer",
    "DeviceLinkConfirmSerializer",
    "DeviceLinkStartSerializer",
    "DeviceListEnvelopeSerializer",
    "DeviceOutSerializer",
    "DevicePatchSerializer",
    "DeviceSpecSerializer",
    "LoginSerializer",
    "MfaChallengeEnvelopeSerializer",
    "MfaChallengeSerializer",
    "MfaVerifySerializer",
    "OnboardingEnvelopeSerializer",
    "OnboardingPatchSerializer",
    "RefreshSerializer",
    "RegisterAdSerializer",
    "RegisterLocalSerializer",
    "RejectUserSerializer",
    "ResendVerificationSerializer",
    "TosAcceptSerializer",
    "TosEnvelopeSerializer",
    "UserPublicSerializer",
    "VerifyEmailSerializer",
]
