```python
from flask import Flask, jsonify, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from werkzeug.exceptions import HTTPException, InternalServerError # Import InternalServerError
from config import Config

# Khởi tạo các đối tượng mở rộng Flask
db = SQLAlchemy()
ma = Marshmallow()

def create_app(config_class=Config):
    """
    Khởi tạo và cấu hình ứng dụng Flask.

    Args:
        config_class: Lớp cấu hình để sử dụng (mặc định là Config).

    Returns:
        Đối tượng ứng dụng Flask đã được cấu hình.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Khởi tạo các đối tượng mở rộng với ứng dụng Flask
    db.init_app(app)
    ma.init_app(app)

    # Đăng ký Blueprints
    # Đảm bảo rằng 'app.api' có thể được import.
    # Nếu 'app' là thư mục gốc của ứng dụng, thì 'app.api' sẽ là 'project_root/app/api'.
    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    # --- Xử lý lỗi toàn cục ---

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        """
        Xử lý các lỗi HTTP (ví dụ: 400 Bad Request, 404 Not Found, 401 Unauthorized)
        và trả về phản hồi JSON nhất quán.

        Args:
            e (HTTPException): Đối tượng ngoại lệ HTTP.

        Returns:
            flask.Response: Phản hồi JSON với thông tin lỗi và mã trạng thái HTTP.
        """
        # Lấy thông tin lỗi từ HTTPException, cung cấp giá trị mặc định an toàn
        code = e.code if hasattr(e, 'code') else 500
        name = e.name if hasattr(e, 'name') else 'Internal Server Error'
        description = e.description if hasattr(e, 'description') else 'An unexpected error occurred.'

        # Trả về phản hồi JSON trực tiếp với mã trạng thái HTTP
        return jsonify({
            "code": code,
            "name": name,
            "description": description,
        }), code

    @app.errorhandler(500)
    def handle_internal_server_error(e):
        """
        Xử lý lỗi 500 Internal Server Error (lỗi server nội bộ)
        phát sinh từ các ngoại lệ Python thông thường và trả về phản hồi JSON.
        Ghi log lỗi để dễ dàng debug trong môi trường production.

        Args:
            e (Exception): Đối tượng ngoại lệ gây ra lỗi 500.

        Returns:
            flask.Response: Phản hồi JSON với thông tin lỗi và mã trạng thái 500.
        """
        # Ghi log lỗi đầy đủ để debug. current_app được sử dụng để truy cập logger của ứng dụng
        # một cách an toàn trong ngữ cảnh xử lý lỗi.
        current_app.logger.error(f"Internal Server Error: {e}", exc_info=True)

        return jsonify({
            "code": 500,
            "name": "Internal Server Error",
            "description": "An unexpected error occurred on the server. Please try again later.",
        }), 500

    return app
```