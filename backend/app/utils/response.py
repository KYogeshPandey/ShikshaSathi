# For consistent JSON API responses

def success(data=None, message="Success"):
    return {"success": True, "data": data, "message": message}

def error(message="Error", code=400):
    return {"success": False, "message": message}, code
