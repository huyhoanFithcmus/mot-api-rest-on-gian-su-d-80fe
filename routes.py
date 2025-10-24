```python
from flask import Blueprint, request, jsonify, current_app, abort
from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from app.models import db, Todo # Giả định db và Todo model được định nghĩa trong app.models
from app.schemas import TodoSchema # Giả định TodoSchema được định nghĩa trong app.schemas


# Tạo một Blueprint cho các API routes
bp = Blueprint('api', __name__, url_prefix='/api')
todo_schema = TodoSchema()
todos_schema = TodoSchema(many=True)


# --- Centralized Error Handlers ---
@bp.app_errorhandler(SQLAlchemyError)
def handle_db_error(e):
    """
    Xử lý các lỗi liên quan đến cơ sở dữ liệu SQLAlchemy.
    """
    db.session.rollback()
    current_app.logger.error(f"Database error: {e}", exc_info=True)
    return jsonify({"message": "Lỗi máy chủ nội bộ khi thao tác với cơ sở dữ liệu."}), 500

@bp.app_errorhandler(ValidationError)
def handle_validation_error(err):
    """
    Xử lý lỗi validation từ Marshmallow.
    """
    current_app.logger.warning(f"Validation error: {err.messages}")
    return jsonify({"message": "Dữ liệu đầu vào không hợp lệ", "errors": err.messages}), 400

@bp.app_errorhandler(404)
def handle_not_found_error(error):
    """
    Xử lý lỗi 404 Not Found.
    """
    return jsonify({"message": error.description or "Tài nguyên không tìm thấy"}), 404

@bp.app_errorhandler(400)
def handle_bad_request_error(error):
    """
    Xử lý lỗi 400 Bad Request chung.
    """
    return jsonify({"message": error.description or "Yêu cầu không hợp lệ"}), 400


@bp.route('/todos', methods=['GET'])
def get_todos():

    """
    Lấy tất cả các công việc (todo items) với phân trang.
    Trả về danh sách các công việc và thông tin phân trang.
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # Truy vấn tất cả các công việc từ cơ sở dữ liệu với phân trang
    # error_out=False sẽ không raise 404 nếu page hoặc per_page không hợp lệ,
    # thay vào đó trả về một đối tượng Pagination rỗng.
    pagination = Todo.query.paginate(page=page, per_page=per_page, error_out=False)
    all_todos = pagination.items
    
    # Serialize danh sách các công việc thành JSON
    result = todos_schema.dump(all_todos)
    
    return jsonify({
        "todos": result,
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page,
        "per_page": pagination.per_page,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev
    }), 200


@bp.route('/todos/<int:id>', methods=['GET'])
def get_todo(id):

    """
    Lấy một công việc cụ thể bằng ID.
    Trả về thông tin của công việc hoặc lỗi 404 nếu không tìm thấy.
    """
    # Tìm công việc theo ID
    todo = Todo.query.get(id)
    if not todo:
        # Sử dụng abort để kích hoạt trình xử lý lỗi 404 toàn cục
        abort(404, description="Không tìm thấy công việc")
    
    # Serialize công việc thành JSON
    return jsonify(todo_schema.dump(todo)), 200


@bp.route('/todos', methods=['POST'])
def add_todo():

    """
    Thêm một công việc mới.
    Nhận dữ liệu JSON, validate và lưu vào cơ sở dữ liệu.
    Trả về công việc đã tạo với status 201 Created hoặc lỗi 400/500.
    """
    json_data = request.get_json()
    if not json_data:
        # Sử dụng abort để kích hoạt trình xử lý lỗi 400 toàn cục
        abort(400, description="Dữ liệu JSON không được cung cấp hoặc Content-Type không phải application/json")

    # Validate và load dữ liệu bằng schema.
    # Lỗi ValidationError sẽ được xử lý bởi @bp.app_errorhandler(ValidationError)
    validated_data = todo_schema.load(json_data)

    # Tạo một đối tượng Todo mới
    new_todo = Todo(
        title=validated_data['title'],
        description=validated_data.get('description'),
        completed=validated_data.get('completed', False) # Mặc định là False nếu không có
    )
    
    # Thêm vào session và commit vào cơ sở dữ liệu
    db.session.add(new_todo)
    db.session.commit()

    # Serialize công việc mới và trả về với status 201 Created
    return jsonify(todo_schema.dump(new_todo)), 201


@bp.route('/todos/<int:id>', methods=['PUT'])
def update_todo(id):

    """
    Cập nhật một công việc hiện có bằng ID.
    Nhận dữ liệu JSON, validate và cập nhật công việc trong cơ sở dữ liệu.
    Trả về công việc đã cập nhật hoặc lỗi 400/404/500.
    """
    # Tìm công việc theo ID
    todo = Todo.query.get(id)
    if not todo:
        # Sử dụng abort để kích hoạt trình xử lý lỗi 404 toàn cục
        abort(404, description="Không tìm thấy công việc")

    json_data = request.get_json()
    if not json_data:
        # Sử dụng abort để kích hoạt trình xử lý lỗi 400 toàn cục
        abort(400, description="Dữ liệu JSON không được cung cấp hoặc Content-Type không phải application/json")

    # Validate và load dữ liệu bằng schema. partial=True cho phép cập nhật một phần.
    # Lỗi ValidationError sẽ được xử lý bởi @bp.app_errorhandler(ValidationError)
    validated_data = todo_schema.load(json_data, partial=True)

    # Cập nhật các trường của công việc nếu chúng tồn tại trong dữ liệu đã validate
    for key, value in validated_data.items():
        setattr(todo, key, value)
    
    # Commit các thay đổi vào cơ sở dữ liệu
    db.session.commit()

    # Serialize công việc đã cập nhật và trả về
    return jsonify(todo_schema.dump(todo)), 200


@bp.route('/todos/<int:id>', methods=['DELETE'])
def delete_todo(id):

    """
    Xóa một công việc bằng ID.
    Xóa công việc khỏi cơ sở dữ liệu.
    Trả về status 204 No Content nếu thành công hoặc lỗi 404/500.
    """
    # Tìm công việc theo ID
    todo = Todo.query.get(id)
    if not todo:
        # Sử dụng abort để kích hoạt trình xử lý lỗi 404 toàn cục
        abort(404, description="Không tìm thấy công việc")

    # Xóa công việc khỏi session và commit
    db.session.delete(todo)
    db.session.commit()

    # Trả về phản hồi rỗng với status 204 No Content (đã xóa thành công)
    return '', 204
```