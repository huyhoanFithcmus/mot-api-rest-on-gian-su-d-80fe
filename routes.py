Dưới đây là mã nguồn đã được sửa đổi, tập trung vào việc khắc phục các vấn đề đã nêu, cải thiện khả năng đọc và hiệu năng, đồng thời giữ nguyên cấu trúc gốc.

```python
import logging
from functools import wraps

from flask import Blueprint, request, jsonify
from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import NotFound # Được sử dụng bởi get_or_404

from app.models import db, Todo # Giả định db và Todo model được định nghĩa trong app.models
from app.schemas import TodoSchema # Giả định TodoSchema được định nghĩa trong app.schemas

# Cấu hình logging cơ bản để ghi lại các lỗi máy chủ nội bộ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Tạo một Blueprint cho các API routes
bp = Blueprint('api', __name__, url_prefix='/api')
todo_schema = TodoSchema()
todos_schema = TodoSchema(many=True)

# --- Hàm trợ giúp cho phản hồi API ---

def success_response(data, status_code=200):
    """
    Tạo một phản hồi JSON thành công với dữ liệu và mã trạng thái tùy chỉnh.
    """
    return jsonify(data), status_code

def error_response(message, status_code, errors=None):
    """
    Tạo một phản hồi JSON lỗi chuẩn hóa với thông báo, mã trạng thái và chi tiết lỗi (nếu có).
    """
    response_payload = {"message": message}
    if errors:
        response_payload["errors"] = errors
    return jsonify(response_payload), status_code

# --- Xử lý lỗi tập trung cho Blueprint ---
# Sử dụng bp.errorhandler để xử lý các loại lỗi cụ thể trên toàn bộ Blueprint.
# Điều này giúp giảm sự lặp lại của các khối try...except trong từng route.

@bp.errorhandler(ValidationError)
def handle_validation_error(err):
    """
    Xử lý lỗi Validation từ Marshmallow.
    Trả về lỗi 400 Bad Request với chi tiết lỗi.
    """
    db.session.rollback() # Hoàn tác các thay đổi nếu có lỗi validation
    logger.warning(f"Validation error: {err.messages}")
    return error_response(
        "Dữ liệu đầu vào không hợp lệ", 400, errors=err.messages
    )

@bp.errorhandler(SQLAlchemyError)
def handle_sqlalchemy_error(err):
    """
    Xử lý lỗi liên quan đến cơ sở dữ liệu từ SQLAlchemy.
    Trả về lỗi 500 Internal Server Error và ghi log chi tiết.
    """
    db.session.rollback() # Hoàn tác các thay đổi nếu có lỗi DB
    logger.error(f"Database error: {err}", exc_info=True) # Ghi log chi tiết lỗi
    return error_response(
        "Lỗi cơ sở dữ liệu: Vui lòng thử lại sau.", 500
    )

# Decorator để bắt các lỗi máy chủ nội bộ không mong muốn khác
def handle_unexpected_errors(func):
    """
    Decorator để bắt các lỗi máy chủ nội bộ không mong muốn (không phải validation hay DB).
    Ghi log lỗi và trả về phản hồi lỗi chung cho người dùng.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Rollback cho bất kỳ ngoại lệ nào chưa được xử lý có thể đã bắt đầu một transaction
            db.session.rollback()
            logger.error(f"Internal server error in {func.__name__}: {e}", exc_info=True)
            return error_response(
                "Lỗi máy chủ nội bộ: Vui lòng thử lại sau.", 500
            )
    return wrapper

# --- Các API Routes ---

@bp.route('/todos', methods=['GET'])
@handle_unexpected_errors # Áp dụng decorator xử lý lỗi chung
def get_todos():
    """
    Lấy tất cả các công việc (todo items) với phân trang.
    Trả về danh sách các công việc và thông tin phân trang.

    Tham số truy vấn:
    - page (int, tùy chọn): Số trang, mặc định là 1.
    - per_page (int, tùy chọn): Số lượng mục trên mỗi trang, mặc định là 10.
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # Truy vấn tất cả các công việc từ cơ sở dữ liệu với phân trang
    # Giả định Todo.query.paginate có sẵn từ Flask-SQLAlchemy.
    # error_out=False để tránh trả về 404 nếu số trang vượt quá giới hạn,
    # thay vào đó trả về một trang rỗng.
    pagination = Todo.query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Serialize danh sách các công việc thành JSON
    result = todos_schema.dump(pagination.items)

    # Thêm thông tin phân trang vào phản hồi
    pagination_info = {
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page,
        "per_page": pagination.per_page,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
        "next_num": pagination.next_num,
        "prev_num": pagination.prev_num,
    }
    
    # Gợi ý tối ưu hiệu năng (N+1 Query):
    # Nếu Todo model có các mối quan hệ (relationships) và bạn truy cập chúng
    # trong TodoSchema, hãy sử dụng joinedload hoặc selectinload của SQLAlchemy
    # để tải trước các mối quan hệ, tránh vấn đề N+1 query.
    # Ví dụ: Todo.query.options(db.joinedload(Todo.related_model)).paginate(...)

    return success_response({
        "todos": result,
        "pagination": pagination_info
    })

@bp.route('/todos/<int:id>', methods=['GET'])
@handle_unexpected_errors # Áp dụng decorator xử lý lỗi chung
def get_todo(id):
    """
    Lấy một công việc cụ thể bằng ID.
    Trả về thông tin của công việc hoặc lỗi 404 nếu không tìm thấy.
    """
    # Tìm công việc theo ID, sử dụng get_or_404 để tự động trả về 404
    # Giả định Todo.query.get_or_404 có sẵn từ Flask-SQLAlchemy.
    # Nó sẽ tự động raise NotFound (một loại HTTPException) nếu không tìm thấy,
    # và Flask sẽ xử lý NotFound thành phản hồi 404 Not Found.
    todo = Todo.query.get_or_404(id, description="Không tìm thấy công việc")
    
    # Serialize công việc thành JSON
    return success_response(todo_schema.dump(todo))

@bp.route('/todos', methods=['POST'])
@handle_unexpected_errors # Áp dụng decorator xử lý lỗi chung
def add_todo():
    """
    Thêm một công việc mới.
    Nhận dữ liệu JSON, validate và lưu vào cơ sở dữ liệu.
    Trả về công việc đã tạo với status 201 Created hoặc lỗi 400/500.
    """
    json_data = request.get_json()
    if not json_data:
        return error_response("Dữ liệu JSON không được cung cấp", 400)

    # Validate và load dữ liệu bằng schema.
    # Lỗi ValidationError sẽ được handle bởi bp.errorhandler(ValidationError).
    validated_data = todo_schema.load(json_data)

    # Tạo một đối tượng Todo mới
    new_todo = Todo(
        title=validated_data['title'],
        description=validated_data.get('description'),
        completed=validated_data.get('completed', False)
    )
    
    # Thêm vào session và commit vào cơ sở dữ liệu.
    # Lỗi SQLAlchemyError sẽ được handle bởi bp.errorhandler(SQLAlchemyError).
    db.session.add(new_todo)
    db.session.commit()

    # Serialize công việc mới và trả về với status 201 Created
    return success_response(todo_schema.dump(new_todo), 201)

@bp.route('/todos/<int:id>', methods=['PUT'])
@handle_unexpected_errors # Áp dụng decorator xử lý lỗi chung
def update_todo(id):
    """
    Cập nhật một công việc hiện có bằng ID.
    Nhận dữ liệu JSON, validate và cập nhật công việc trong cơ sở dữ liệu.
    Hỗ trợ cập nhật một phần (partial update) bằng cách sử dụng `partial=True` trong schema.
    Trả về công việc đã cập nhật hoặc lỗi 400/404/500.
    """
    # Tìm công việc theo ID, sử dụng get_or_404 để tự động trả về 404
    todo = Todo.query.get_or_404(id, description="Không tìm thấy công việc")

    json_data = request.get_json()
    if not json_data:
        return error_response("Dữ liệu JSON không được cung cấp", 400)

    # Validate và load dữ liệu bằng schema. partial=True cho phép cập nhật một phần.
    # Lỗi ValidationError sẽ được handle bởi bp.errorhandler(ValidationError).
    validated_data = todo_schema.load(json_data, partial=True)

    # Cập nhật các trường của công việc nếu chúng tồn tại trong dữ liệu đã validate.
    # Cách này ngắn gọn và dễ mở rộng hơn so với kiểm tra từng trường.
    for key, value in validated_data.items():
        setattr(todo, key, value)
    
    # Commit các thay đổi vào cơ sở dữ liệu.
    # Lỗi SQLAlchemyError sẽ được handle bởi bp.errorhandler(SQLAlchemyError).
    db.session.commit()

    # Serialize công việc đã cập nhật và trả về
    return success_response(todo_schema.dump(todo))

@bp.route('/todos/<int:id>', methods=['DELETE'])
@handle_unexpected_errors # Áp dụng decorator xử lý lỗi chung
def delete_todo(id):
    """
    Xóa một công việc bằng ID.
    Xóa công việc khỏi cơ sở dữ liệu.
    Trả về status 204 No Content nếu thành công hoặc lỗi 404/500.
    """
    # Tìm công việc theo ID, sử dụng get_or_404 để tự động trả về 404
    todo = Todo.query.get_or_404(id, description="Không tìm thấy công việc")

    # Xóa công việc khỏi session và commit.
    # Lỗi SQLAlchemyError sẽ được handle bởi bp.errorhandler(SQLAlchemyError).
    db.session.delete(todo)
    db.session.commit()

    # Trả về phản hồi rỗng với status 204 No Content (đã xóa thành công).
    # Không cần jsonify cho 204 vì không có nội dung.
    return '', 204
```