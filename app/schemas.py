from marshmallow import Schema, fields
from flask_marshmallow import SQLAlchemyAutoSchema

# Định nghĩa Schema cho đối tượng Todo
# Sử dụng Marshmallow để định nghĩa cách các đối tượng Todo sẽ được serialize (chuyển đổi thành JSON)
# và deserialize (chuyển đổi từ JSON).
# Điều này giúp kiểm soát định dạng dữ liệu trả về và dữ liệu đầu vào.
class TodoSchema(Schema):
    # ID của công việc, chỉ đọc (dump_only=True) vì nó được tạo tự động bởi database.
    id = fields.Int(dump_only=True, required=True, description="ID duy nhất của công việc")
    # Tiêu đề của công việc, là một chuỗi và là trường bắt buộc.
    title = fields.Str(required=True, description="Tiêu đề của công việc")
    # Mô tả chi tiết của công việc, là một chuỗi và không bắt buộc.
    description = fields.Str(required=False, allow_none=True, description="Mô tả chi tiết công việc")
    # Trạng thái hoàn thành của công việc, là một boolean, mặc định là False.
    completed = fields.Bool(required=False, load_default=False, description="Trạng thái hoàn thành (true/false)")
    # Thời gian tạo công việc, chỉ đọc và được định dạng theo ISO 8601.
    created_at = fields.DateTime(dump_only=True, format='%Y-%m-%dT%H:%M:%S%z', description="Thời gian tạo công việc (ISO 8601)")
    # Thời gian cập nhật công việc lần cuối, chỉ đọc và được định dạng theo ISO 8601.
    updated_at = fields.DateTime(dump_only=True, format='%Y-%m-%dT%H:%M:%S%z', description="Thời gian cập nhật công việc (ISO 8601)")

    # Cấu hình Meta cho Schema (tùy chọn, nhưng hữu ích cho các tùy chỉnh nâng cao)
    class Meta:
        # Sắp xếp các trường theo thứ tự cụ thể khi serialize.
        fields = ('id', 'title', 'description', 'completed', 'created_at', 'updated_at')
        # Đảm bảo rằng các trường không được định nghĩa trong schema sẽ không được bao gồm
        # khi deserialize (load) dữ liệu đầu vào.
        unknown = 'exclude'

# Khởi tạo một instance của TodoSchema để sử dụng cho một đối tượng Todo duy nhất.
# Ví dụ: todo_schema.dump(todo_object)
todo_schema = TodoSchema()

# Khởi tạo một instance của TodoSchema để sử dụng cho một danh sách các đối tượng Todo.
# 'many=True' chỉ ra rằng schema này sẽ xử lý một danh sách các đối tượng.
# Ví dụ: todos_schema.dump(list_of_todo_objects)
todos_schema = TodoSchema(many=True)
