import os

# Lấy đường dẫn thư mục gốc của ứng dụng
# Điều này giúp đảm bảo đường dẫn cơ sở dữ liệu luôn đúng dù ứng dụng được chạy từ đâu
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """
    Lớp cấu hình cơ bản cho ứng dụng Flask.
    Chứa các cài đặt chung cho tất cả các môi trường.
    """
    # Chế độ Debug: Bật/Tắt chế độ gỡ lỗi. Nên TẮT trong môi trường production.
    DEBUG = False
    TESTING = False
    
    # Khóa bí mật (Secret Key) cho Flask.
    # Rất quan trọng để bảo mật các phiên (sessions) và các tính năng khác.
    # Nên được tạo ngẫu nhiên và giữ bí mật. Trong production, nên lấy từ biến môi trường.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'mot_khoa_bi_mat_rat_kho_doan_va_an_toan'

    # Cấu hình SQLAlchemy
    # URI kết nối đến cơ sở dữ liệu SQLite.
    # 'sqlite:///' + os.path.join(basedir, 'app.db') sẽ tạo file 'app.db' trong thư mục gốc của ứng dụng.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
                              'sqlite:///' + os.path.join(basedir, 'app.db')
    
    # Tắt tính năng theo dõi các thay đổi của đối tượng SQLAlchemy và gửi tín hiệu.
    # Việc này giúp tiết kiệm tài nguyên và được khuyến nghị là False trừ khi bạn thực sự cần.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevelopmentConfig(Config):
    """
    Lớp cấu hình cho môi trường phát triển.
    Kế thừa từ Config và ghi đè các cài đặt cần thiết cho dev.
    """
    DEBUG = True
    # Có thể thêm các cài đặt riêng cho dev ở đây, ví dụ: database khác, logging level khác.

class TestingConfig(Config):
    """
    Lớp cấu hình cho môi trường kiểm thử.
    Kế thừa từ Config và ghi đè các cài đặt cần thiết cho testing.
    """
    TESTING = True
    # Sử dụng cơ sở dữ liệu trong bộ nhớ hoặc một file db riêng cho testing để không ảnh hưởng đến dev/prod db.
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Cơ sở dữ liệu trong bộ nhớ cho testing nhanh hơn

class ProductionConfig(Config):
    """
    Lớp cấu hình cho môi trường production.
    Kế thừa từ Config và ghi đè các cài đặt cần thiết cho production.
    """
    # DEBUG nên là False trong production
    DEBUG = False
    # TESTING nên là False trong production
    TESTING = False
    # Trong production, SECRET_KEY và DATABASE_URL nên được lấy từ biến môi trường để bảo mật.
    # Ví dụ: SECRET_KEY = os.environ.get('SECRET_KEY')
    #         SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    # Đảm bảo các biến môi trường này được thiết lập trên server production.

# Dictionary để dễ dàng truy cập các cấu hình theo tên môi trường
config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig # Cấu hình mặc định nếu không chỉ định rõ
}
