```python
"""
Định nghĩa Marshmallow schemas để serialize/deserialize dữ liệu.

Mô-đun này chứa các Marshmallow schemas cho các đối tượng dữ liệu khác nhau
(ví dụ: User, Item). Các schemas này được sử dụng để:
-   **Serialize:** Chuyển đổi các đối tượng Python thành các định dạng có thể
    truyền tải (ví dụ: JSON) để gửi đến client.
-   **Deserialize:** Chuyển đổi dữ liệu nhận được từ client (ví dụ: JSON)
    thành các đối tượng Python để xử lý trong ứng dụng.

Các cải tiến chính được áp dụng:
1.  **Base Schema:** Giới thiệu `BaseSchema` để tái sử dụng các trường chung
    như `id`, `created_at`, `updated_at`, giúp giảm trùng lặp mã và tăng
    tính nhất quán.
2.  **Context-specific Schemas:** Chia nhỏ các schema thành các phiên bản
    chuyên biệt cho từng ngữ cảnh (ví dụ: `UserCreateSchema`, `UserUpdateSchema`,
    `UserDetailSchema`) để tránh over-fetching/under-fetching và kiểm soát
    tốt hơn các trường `load_only`/`dump_only`.
3.  **Validators:** Áp dụng các validator phù hợp (`Length`, `Email`, `Range`)
    để đảm bảo tính toàn vẹn dữ liệu ngay từ tầng deserialization.
4.  **`load_only` và `dump_only`:** Sử dụng chính xác cho các trường như
    `password` (chỉ ghi) và `id`, `created_at`, `updated_at` (chỉ đọc).
5.  **Nested Schemas:** Minh họa cách lồng các schema (`fields.Nested`)
    để biểu diễn mối quan hệ giữa các đối tượng (ví dụ: một Item thuộc về một User).
6.  **Readability:** Thêm docstrings rõ ràng cho các lớp và sử dụng `metadata`
    để cung cấp mô tả cho các trường, hữu ích cho việc tạo tài liệu API tự động.
7.  **PEP8 Compliance:** Đảm bảo tuân thủ các quy tắc PEP8 về đặt tên,
    sắp xếp import và khoảng trắng.
"""

from marshmallow import Schema, fields
from marshmallow.validate import Email, Length, Range


class BaseSchema(Schema):
    """
    Schema cơ sở cho các trường chung như ID, thời gian tạo và cập nhật.
    Các trường này thường chỉ đọc (dump_only).
    """
    id = fields.Int(
        dump_only=True,
        metadata={"description": "Unique identifier of the resource"}
    )
    created_at = fields.DateTime(
        dump_only=True,
        metadata={"description": "Timestamp when the resource was created"}
    )
    updated_at = fields.DateTime(
        dump_only=True,
        metadata={"description": "Timestamp when the resource was last updated"}
    )


class UserSchema(BaseSchema):
    """
    Schema cơ sở cho đối tượng User, định nghĩa các trường chung cho việc hiển thị.
    """
    username = fields.Str(
        required=True,
        validate=Length(min=3, max=50),
        metadata={"description": "Unique username for the user (3-50 characters)"}
    )
    email = fields.Email(
        required=True,
        validate=Email(),
        metadata={"description": "Unique email address for the user"}
    )


class UserCreateSchema(UserSchema):
    """
    Schema để tạo người dùng mới. Bao gồm trường 'password' chỉ để ghi (load_only).
    """
    password = fields.Str(
        required=True,
        load_only=True,  # Mật khẩu chỉ nên được cung cấp khi tạo/cập nhật, không được trả về.
        validate=Length(min=8, max=128),
        metadata={"description": "User's password (min 8 characters)"}
    )


class UserUpdateSchema(UserSchema):
    """
    Schema để cập nhật người dùng hiện có. Tất cả các trường đều là tùy chọn
    vì không phải lúc nào cũng cần cập nhật tất cả.
    """
    username = fields.Str(
        required=False,  # Tùy chọn khi cập nhật
        validate=Length(min=3, max=50),
        metadata={"description": "New username for the user (3-50 characters)"}
    )
    email = fields.Email(
        required=False,  # Tùy chọn khi cập nhật
        validate=Email(),
        metadata={"description": "New email address for the user"}
    )
    password = fields.Str(
        required=False,  # Mật khẩu là tùy chọn khi cập nhật
        load_only=True,
        validate=Length(min=8, max=128),
        metadata={"description": "New password for the user (min 8 characters)"}
    )


class UserDetailSchema(UserSchema):
    """
    Schema để hiển thị thông tin chi tiết của một người dùng.
    Có thể bao gồm các mối quan hệ lồng ghép nếu cần.
    """
    # Ví dụ: nếu User có nhiều Items, có thể thêm:
    # items = fields.Nested('ItemSchema', many=True, dump_only=True)
    pass


class UserListSchema(UserSchema):
    """
    Schema để hiển thị danh sách người dùng.
    Có thể được tùy chỉnh để chỉ bao gồm các trường cần thiết cho danh sách
    nhằm tối ưu hiệu năng (tránh over-fetching).
    """
    # Hiện tại giống UserSchema, nhưng có thể loại bỏ các trường không cần thiết
    # hoặc thêm các trường tóm tắt nếu cần.
    pass


class ItemSchema(BaseSchema):
    """
    Schema cơ sở cho đối tượng Item, định nghĩa các trường chung.
    """
    name = fields.Str(
        required=True,
        validate=Length(min=3, max=100),
        metadata={"description": "Name of the item (3-100 characters)"}
    )
    description = fields.Str(
        allow_none=True,  # Cho phép giá trị null
        metadata={"description": "Optional description of the item"}
    )
    price = fields.Float(
        required=True,
        validate=Range(min=0.01),  # Giá phải là số dương
        metadata={"description": "Price of the item (must be positive)"}
    )
    # user_id là khóa ngoại. Nó được cung cấp khi tạo/cập nhật Item,
    # nhưng không được trả về trực tiếp nếu đối tượng user được lồng ghép.
    user_id = fields.Int(
        required=True,
        load_only=True,
        metadata={"description": "ID of the user who owns this item"}
    )


class ItemCreateSchema(ItemSchema):
    """
    Schema để tạo một Item mới.
    """
    # Kế thừa tất cả các trường từ ItemSchema, bao gồm user_id (load_only).
    pass


class ItemUpdateSchema(ItemSchema):
    """
    Schema để cập nhật một Item hiện có. Tất cả các trường đều là tùy chọn.
    """
    name = fields.Str(required=False, validate=Length(min=3, max=100))
    description = fields.Str(allow_none=True, required=False)
    price = fields.Float(required=False, validate=Range(min=0.01))
    user_id = fields.Int(required=False, load_only=True)


class ItemDetailSchema(ItemSchema):
    """
    Schema để hiển thị thông tin chi tiết của một Item, bao gồm thông tin về người sở hữu.
    """
    # Lồng schema UserListSchema để hiển thị thông tin người sở hữu.
    # dump_only=True vì đối tượng user được lấy từ database, không phải từ input.
    user = fields.Nested(
        UserListSchema,
        dump_only=True,
        metadata={"description": "Owner of the item"}
    )


class ItemListSchema(ItemSchema):
    """
    Schema để hiển thị danh sách các Item.
    Có thể được tùy chỉnh để chỉ bao gồm các trường cần thiết cho danh sách.
    """
    # Đối với danh sách, chúng ta có thể chỉ muốn ID hoặc một phiên bản đơn giản hơn của người dùng.
    # Để tránh vấn đề N+1 khi truy vấn database, thường chỉ hiển thị user_id hoặc một UserSimpleSchema.
    # Ở đây, chúng ta sẽ chỉ hiển thị user_id như một trường dump_only để client biết ai sở hữu nó.
    user_id = fields.Int(
        dump_only=True,  # Hiển thị user_id khi dump, nhưng không yêu cầu khi load
        metadata={"description": "ID of the user who owns this item"}
    )
    # Hoặc nếu muốn hiển thị tên người dùng:
    # user_username = fields.Method("get_user_username", dump_only=True)
    # def get_user_username(self, obj):
    #     return obj.user.username if obj.user else None
```