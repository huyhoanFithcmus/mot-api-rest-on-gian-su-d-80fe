```python
"""
Đây là application factory chính cho ứng dụng Flask.
Nó chịu trách nhiệm khởi tạo và cấu hình các thành phần cốt lõi của ứng dụng,
bao gồm Flask app instance, cơ sở dữ liệu (SQLAlchemy) và Marshmallow,
cũng như đăng ký các blueprint.
Mô hình này hỗ trợ việc tạo các instance ứng dụng độc lập, hữu ích cho testing
và quản lý cấu hình.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow

# Import lớp cấu hình mặc định
from config import Config
# Import blueprint chính của ứng dụng
from app.main import bp as main_bp

# Khởi tạo các extension ở cấp độ global.
# Chúng sẽ được liên kết với một instance app cụ thể sau này bằng init_app.
db = SQLAlchemy()
ma = Marshmallow()

def create_app(config_class=Config):
    """
    Tạo và cấu hình một instance ứng dụng Flask.

    Hàm này triển khai mô hình Application Factory, cho phép tạo ra
    các instance ứng dụng Flask độc lập với các cấu hình khác nhau.

    Args:
        config_class: Lớp cấu hình được sử dụng để tải cấu hình cho ứng dụng.
                      Mặc định là lớp Config từ module config.py.

    Returns:
        Một instance của ứng dụng Flask đã được cấu hình và sẵn sàng sử dụng.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Liên kết các extension với instance ứng dụng Flask
    db.init_app(app)
    ma.init_app(app)

    # Đăng ký các blueprint của ứng dụng
    # Nếu có nhiều blueprint, có thể cân nhắc tạo một danh sách và lặp qua chúng.
    app.register_blueprint(main_bp)

    return app

```