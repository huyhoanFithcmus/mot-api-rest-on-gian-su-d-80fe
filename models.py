```python
# app/models.py
from datetime import datetime, timezone
from app import db # Giả sử 'db' là một instance của SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from typing import List, Optional, Dict, Type

class BaseModel(db.Model):
    """
    Base model cung cấp các trường chung (id, dấu thời gian tạo/cập nhật)
    và các hoạt động CRUD cơ bản với xử lý lỗi.
    Các model khác có thể kế thừa từ BaseModel để tái sử dụng code.
    """
    __abstract__ = True # Đánh dấu là abstract, SQLAlchemy sẽ không tạo bảng riêng cho BaseModel

    id = db.Column(db.Integer, primary_key=True)
    # Sử dụng datetime.now(timezone.utc) để đảm bảo ngày giờ được lưu trữ dưới dạng UTC
    # và có nhận biết múi giờ (timezone-aware).
    # db.DateTime(timezone=True) cho phép SQLAlchemy lưu trữ thông tin múi giờ trong database.
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def save(self) -> bool:
        """
        Lưu đối tượng vào database.
        Trả về True nếu thành công, False nếu có lỗi.
        Bao gồm xử lý lỗi cơ bản và rollback transaction để đảm bảo tính toàn vẹn dữ liệu.
        """
        try:
            db.session.add(self)
            db.session.commit()
            return True
        except IntegrityError as e:
            db.session.rollback()
            # Trong ứng dụng thực tế, bạn nên sử dụng một hệ thống logging thích hợp
            # (ví dụ: `logging.error(...)`) thay vì `print()` để ghi lại lỗi.
            print(f"Lỗi toàn vẹn dữ liệu khi lưu {self.__class__.__name__}: {e}")
            return False
        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"Lỗi database khi lưu {self.__class__.__name__}: {e}")
            return False

    def delete(self) -> bool:
        """
        Xóa đối tượng khỏi database.
        Trả về True nếu thành công, False nếu có lỗi.
        Bao gồm xử lý lỗi cơ bản và rollback transaction.
        """
        try:
            db.session.delete(self)
            db.session.commit()
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"Lỗi database khi xóa {self.__class__.__name__}: {e}")
            return False

class Todo(BaseModel):
    """
    Định nghĩa model cho một mục công việc (Todo item).
    Kế thừa các trường ID, created_at, updated_at và các phương thức CRUD cơ bản từ BaseModel.
    """
    __tablename__ = 'todos' # Tên bảng trong database

    # id, created_at, updated_at được kế thừa từ BaseModel

    title = db.Column(db.String(128), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    completed = db.Column(db.Boolean, default=False, nullable=False, index=True)
    # Thêm index cho due_date để cải thiện hiệu năng truy vấn khi lọc hoặc sắp xếp theo ngày đến hạn.
    due_date = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    # user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) # Nếu có liên kết với User

    def __repr__(self) -> str:
        """
        Trả về biểu diễn chuỗi của đối tượng Todo, hữu ích cho việc debug.
        """
        return f'<Todo {self.id}: {self.title} (Completed: {self.completed})>'

    def to_dict(self) -> Dict[str, any]:
        """
        Chuyển đổi đối tượng Todo thành một dictionary, hữu ích cho API responses.
        Sử dụng isoformat() để đảm bảo định dạng ngày giờ chuẩn ISO 8601,
        bao gồm thông tin múi giờ nếu có.
        """
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'completed': self.completed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            # 'user_id': self.user_id,
        }

    @classmethod
    def get_all_incomplete(cls: Type['Todo']) -> List['Todo']:
        """
        Trả về tất cả các Todo chưa hoàn thành.
        """
        return cls.query.filter_by(completed=False).all()

    @classmethod
    def get_by_id(cls: Type['Todo'], todo_id: int) -> Optional['Todo']:
        """
        Tìm một Todo theo ID.
        """
        return cls.query.get(todo_id)

    # Các phương thức save() và delete() được kế thừa từ BaseModel.
    # Không cần định nghĩa lại ở đây trừ khi có logic đặc biệt cho Todo
    # mà không thể xử lý ở cấp BaseModel.
```