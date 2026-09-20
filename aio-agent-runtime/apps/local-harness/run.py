import uvicorn

from app.config import Settings
from app.platform_settings import DeploymentMode, PlatformSettings, deployment_mode


if __name__ == "__main__":
    settings = (Settings.from_env() if deployment_mode() is DeploymentMode.LEGACY_LOCAL
                else PlatformSettings.from_env())
    # OAuth callback URLs contain one-use authorization codes. Platform access logs must not record query strings.
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False,
                access_log=deployment_mode() is DeploymentMode.LEGACY_LOCAL)

