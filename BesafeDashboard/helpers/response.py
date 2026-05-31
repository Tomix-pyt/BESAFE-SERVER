from flask import jsonify


def ok_response(message=None, data=None):
    body = data or {}
    if message:
        body["message"] = message
    return jsonify({"success": True, "data": body}), 200


def created_response(message=None, data=None):
    body = data or {}
    if message:
        body["message"] = message
    return jsonify({"success": True, "data": body}), 201
