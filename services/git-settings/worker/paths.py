def settings_relpath(
    addon_name: str,
    addon_version: str,
    variant: str,
    project_name: str | None = None,
) -> str:
    if project_name:
        return (
            f"projects/{project_name}/{addon_name}/"
            f"{addon_version}/{variant}.yaml"
        )
    return f"studio/{addon_name}/{addon_version}/{variant}.yaml"


def bundle_relpath(bundle_name: str) -> str:
    return f"bundles/{bundle_name}.yaml"
