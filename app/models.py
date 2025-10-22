from datetime import datetime
from app import db, ma

# Định nghĩa SQLAlchemy Model cho đối tượng Todo
class Todo(db.Model):
    __tablename__ = 'todos'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(self, title, description=None, completed=False):
        self.title = title
        self.description = description
        self.completed = completed

    def __repr__(self):
        return f'<Todo {self.id}: {self.title}>'

    # Phương thức để lưu một đối tượng Todo vào cơ sở dữ liệu
    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
            return self
        except Exception as e:
            db.session.rollback()
            raise Exception(f"Lỗi khi lưu Todo: {e}")

    # Phương thức để xóa một đối tượng Todo khỏi cơ sở dữ liệu
    def delete(self):
        try:
            db.session.delete(self)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise Exception(f"Lỗi khi xóa Todo: {e}")

    # Phương thức để cập nhật một đối tượng Todo
    def update(self, **kwargs):
        try:
            for key, value in kwargs.items():
                setattr(self, key, value)
            self.updated_at = datetime.utcnow # Cập nhật thủ công updated_at nếu cần
            db.session.commit()
            return self
        except Exception as e:
            db.session.rollback()
            raise Exception(f"Lỗi khi cập nhật Todo: {e}")


# Định nghĩa Marshmallow Schema cho đối tượng Todo
# Schema này dùng để serialize (chuyển đổi từ object Python sang JSON) và deserialize (từ JSON sang object Python)
class TodoSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Todo
        # Sử dụng db.session để Marshmallow có thể tương tác với SQLAlchemy
        load_instance = True  # Cho phép load dữ liệu vào một instance của model
        sqla_session = db.session
        # Các trường sẽ được hiển thị trong JSON
        fields = ('id', 'title', 'description', 'completed', 'created_at', 'updated_at')

    # Thêm validation cho trường 'title' để đảm bảo nó không rỗng
    # (Mặc dù nullable=False trong model đã xử lý ở mức DB, đây là validation ở mức ứng dụng)
    title = ma.fields.String(required=True, error_messages={"required": "Trường 'title' là bắt buộc."})

# Khởi tạo các instance của Schema để sử dụng dễ dàng
todo_schema = TodoSchema()
todos_schema = TodoSchema(many=True) # Dùng cho danh sách các Todo
