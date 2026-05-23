def exec_shell(command: str) -> dict:
    return {"command": command, "status": "not_executed_in_demo"}


def kubectl_apply(manifest: str) -> dict:
    return {"manifest": manifest, "status": "not_applied_in_demo"}


def delete_resource(resource: str, name: str) -> dict:
    return {"resource": resource, "name": name, "status": "not_deleted_in_demo"}

