from flask import Blueprint, jsonify, request

from ad_service import ADOperationError, ad_service

api = Blueprint("api", __name__)


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required")
    return data


def success(data=None, message=None, status=200):
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    if message:
        payload["message"] = message
    return jsonify(payload), status


@api.errorhandler(ValueError)
def invalid_request(exc):
    return jsonify(success=False, error=str(exc)), 400


@api.errorhandler(LookupError)
def not_found(exc):
    return jsonify(success=False, error=str(exc)), 404


@api.errorhandler(ADOperationError)
def ldap_error(exc):
    return jsonify(success=False, error=str(exc)), 502


@api.get("/dashboard")
def dashboard():
    users, ous, groups = ad_service.list_users(), ad_service.list_ous(), ad_service.list_groups()
    return success({"users": len(users), "enabledUsers": sum(user["enabled"] for user in users), "ous": len(ous), "groups": len(groups)})


@api.get("/users")
def users_list(): return success(ad_service.list_users())


@api.post("/users")
def users_create(): return success(ad_service.create_user(body()), "User created successfully", 201)


@api.get("/users/<path:identifier>")
def users_get(identifier): return success(ad_service.get_user(identifier))


@api.put("/users/<path:identifier>")
def users_update(identifier): return success(ad_service.update_user(identifier, body()), "User updated successfully")


@api.patch("/users/<path:identifier>/status")
def users_status(identifier):
    data = body()
    if not isinstance(data.get("enabled"), bool): raise ValueError("enabled must be true or false")
    return success(ad_service.set_user_status(identifier, data["enabled"]), "Account status updated")


@api.post("/users/<path:identifier>/password")
def users_password(identifier):
    ad_service.reset_password(identifier, body().get("password"))
    return success(message="Password reset successfully")


@api.get("/ous")
def ous_list(): return success(ad_service.list_ous())


@api.post("/ous")
def ous_create(): return success(ad_service.create_ou(body()), "OU created successfully", 201)


@api.get("/ous/<path:identifier>")
def ous_get(identifier): return success(ad_service.get_ou(identifier))


@api.get("/groups")
def groups_list(): return success(ad_service.list_groups())


@api.post("/groups")
def groups_create(): return success(ad_service.create_group(body()), "Group created successfully", 201)


@api.get("/groups/<path:identifier>")
def groups_get(identifier): return success(ad_service.get_group(identifier))


@api.put("/groups/<path:identifier>")
def groups_update(identifier): return success(ad_service.update_group(identifier, body()), "Group updated successfully")


@api.post("/groups/<path:identifier>/members")
def groups_add_member(identifier): return success(ad_service.change_group_member(identifier, body().get("userId"), True), "User added to group")


@api.delete("/groups/<path:identifier>/members")
def groups_remove_member(identifier): return success(ad_service.change_group_member(identifier, body().get("userId"), False), "User removed from group")
