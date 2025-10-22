import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow

# Khởi tạo các extension mà không gắn với app cụ thể.
# Chúng sẽ được gắn với app trong hàm factory create_app.
db = SQLAlchemy()
ma = Marshmallow()

class Config:
    """
    Lớp cấu hình cơ bản cho ứng dụng Flask.
    Chứa các biến cấu hình chung cho ứng dụng.
    """
    # Cấu hình cơ sở dữ liệu SQLite.
    # Ưu tiên biến môi trường DATABASE_URL (ví dụ cho Heroku/Docker).
    # Nếu không có, sử dụng SQLite trong thư mục 'app' của dự án.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
                              'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'site.db')
    # Tắt tính năng theo dõi thay đổi của SQLAlchemy để tiết kiệm tài nguyên và tránh cảnh báo.
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Có thể thêm các cấu hình khác ở đây, ví dụ: SECRET_KEY, DEBUG, v.v.
    # SECRET_KEY = os.environ.get('SECRET_KEY') or 'a_very_secret_key_for_dev'

def create_app(config_class=Config):
    """
    Hàm factory để tạo và cấu hình ứng dụng Flask.
    Sử dụng pattern factory giúp dễ dàng kiểm thử và quản lý các môi trường khác nhau.

    Args:
        config_class: Lớp cấu hình để sử dụng cho ứng dụng (mặc định là Config).

    Returns:
        Một đối tượng ứng dụng Flask đã được cấu hình.
    """
    app = Flask(__name__)

    try:
        # Tải cấu hình từ lớp Config đã cung cấp.
        app.config.from_object(config_class)
    except Exception as e:
        # Xử lý lỗi nếu có vấn đề khi tải cấu hình.
        # In thông báo lỗi và ném lại ngoại lệ để dừng quá trình khởi tạo ứng dụng.
        print(f"Lỗi khi tải cấu hình ứng dụng: {e}")
        raise # Ném lại lỗi để dừng ứng dụng nếu cấu hình không thành công

    # Gắn các extension đã khởi tạo vào đối tượng ứng dụng Flask.
    db.init_app(app)
    ma.init_app(app)

    # Đăng ký Blueprint (nếu có).
    # Trong một ứng dụng lớn hơn, các routes API sẽ được định nghĩa trong các Blueprint riêng biệt.
    # Ví dụ:
    # from app.api import bp as api_bp
    # app.register_blueprint(api_bp, url_prefix='/api')
    #
    # Để giữ cho file __init__.py này tập trung vào khởi tạo,
    # việc đăng ký Blueprint sẽ được thực hiện sau này,
    # có thể trong cùng file này sau khi import hoặc trong một file riêng (ví dụ: app/routes.py)
    # và được import vào đây.
    # Hiện tại, chúng ta chỉ chuẩn bị sẵn sàng cho việc đó.

    return app
