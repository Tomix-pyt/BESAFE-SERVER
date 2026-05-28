from flask import jsonify


def ok_response(message=None, data=None):
    return jsonify({"data": data, "message": message}), 200


def created_response(message=None, data=None):
    return jsonify({"data": data, "message": message}), 201
