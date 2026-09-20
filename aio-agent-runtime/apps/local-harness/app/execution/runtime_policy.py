"""Current deployment approval for dependency-image capabilities; image bytes remain immutable."""

from ..platform_errors import PlatformError


def require_runtime(settings, profile_id, image_digest, manifest_digest):
    for profile in getattr(settings, "sandbox_profiles", ()):
        if profile["id"] == profile_id and profile["image_digest"] == image_digest:
            runtime = profile.get("runtime")
            if runtime and runtime.get("manifest_digest") == manifest_digest:
                return profile
    raise PlatformError("RUNTIME_PROFILE_WITHDRAWN", "The locked dependency runtime is not currently approved", 403)
