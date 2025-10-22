from flask import Blueprint, request, jsonify
from marshmallow import ValidationError
from app.models import db, Todo # Giả định db và Todo model được định nghĩa trong app.models
from app.schemas import TodoSchema # Giả định TodoSchema được định nghĩa trong app.schemas

# Tạo một Blueprint cho các API routes
bp = Blueprint('api', __name__, url_prefix='/api')

# Khởi tạo schema cho một đối tượng Todo và một danh sách các đối tượng Todo
todo_schema = TodoSchema()
todos_schema = TodoSchema(many=True)

@bp.route('/todos', methods=['GET'])
def get_todos():
    """
    Lấy tất cả các công việc (todo items).
    Trả về danh sách các công việc.
    """
    try:
        # Truy vấn tất cả các công việc từ cơ sở dữ liệu
        all_todos = Todo.query.all()
        # Serialize danh sách các công việc thành JSON
        result = todos_schema.dump(all_todos)
        return jsonify(result), 200
    except Exception as e:
        # Xử lý lỗi nếu có vấn đề khi truy vấn cơ sở dữ liệu
        # Trả về lỗi 500 Internal Server Error
        return jsonify({"message": f"Lỗi máy chủ nội bộ khi lấy danh sách công việc: {str(e)}"}), 500

@bp.route('/todos/<int:id>', methods=['GET'])
def get_todo(id):
    """
    Lấy một công việc cụ thể bằng ID.
    Trả về thông tin của công việc hoặc lỗi 404 nếu không tìm thấy.
    """
    try:
        # Tìm công việc theo ID
        todo = Todo.query.get(id)
        if not todo:
            # Trả về lỗi 404 Not Found nếu không tìm thấy công việc
            return jsonify({"message": "Không tìm thấy công việc"}), 404
        # Serialize công việc thành JSON
        return jsonify(todo_schema.dump(todo)), 200
    except Exception as e:
        # Xử lý lỗi nếu có vấn đề khi truy vấn cơ sở dữ liệu
        # Trả về lỗi 500 Internal Server Error
        return jsonify({"message": f"Lỗi máy chủ nội bộ khi lấy công việc: {str(e)}"}), 500

@bp.route('/todos', methods=['POST'])
def add_todo():
    """
    Thêm một công việc mới.
    Nhận dữ liệu JSON, validate và lưu vào cơ sở dữ liệu.
    Trả về công việc đã tạo với status 201 Created hoặc lỗi 400/500.
    """
    try:
        # Lấy dữ liệu JSON từ request
        json_data = request.get_json()
        if not json_data:
            # Trả về lỗi 400 Bad Request nếu không có dữ liệu JSON
            return jsonify({"message": "Dữ liệu JSON không được cung cấp"}), 400

        # Validate và load dữ liệu bằng schema
        # `load` sẽ trả về một dictionary đã được validate
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
    except ValidationError as err:
        # Xử lý lỗi validation từ Marshmallow
        # Trả về lỗi 400 Bad Request với chi tiết lỗi
        return jsonify({"message": "Dữ liệu đầu vào không hợp lệ", "errors": err.messages}), 400
    except Exception as e:
        # Xử lý lỗi cơ sở dữ liệu hoặc các lỗi khác
        db.session.rollback() # Hoàn tác các thay đổi nếu có lỗi
        # Trả về lỗi 500 Internal Server Error
        return jsonify({"message": f"Lỗi máy chủ nội bộ khi thêm công việc: {str(e)}"}), 500

@bp.route('/todos/<int:id>', methods=['PUT'])
def update_todo(id):
    """
    Cập nhật một công việc hiện có bằng ID.
    Nhận dữ liệu JSON, validate và cập nhật công việc trong cơ sở dữ liệu.
    Trả về công việc đã cập nhật hoặc lỗi 400/404/500.
    """
    try:
        # Tìm công việc theo ID
        todo = Todo.query.get(id)
        if not todo:
            # Trả về lỗi 404 Not Found nếu không tìm thấy công việc
            return jsonify({"message": "Không tìm thấy công việc"}), 404

        # Lấy dữ liệu JSON từ request
        json_data = request.get_json()
        if not json_data:
            # Trả về lỗi 400 Bad Request nếu không có dữ liệu JSON
            return jsonify({"message": "Dữ liệu JSON không được cung cấp"}), 400

        # Validate và load dữ liệu bằng schema. partial=True cho phép cập nhật một phần
        validated_data = todo_schema.load(json_data, partial=True)

        # Cập nhật các trường của công việc nếu chúng tồn tại trong dữ liệu đã validate
        if 'title' in validated_data:
            todo.title = validated_data['title']
        if 'description' in validated_data:
            todo.description = validated_data['description']
        if 'completed' in validated_data:
            todo.completed = validated_data['completed']
        
        # Commit các thay đổi vào cơ sở dữ liệu
        db.session.commit()

        # Serialize công việc đã cập nhật và trả về
        return jsonify(todo_schema.dump(todo)), 200
    except ValidationError as err:
        # Xử lý lỗi validation từ Marshmallow
        db.session.rollback() # Hoàn tác các thay đổi nếu có lỗi
        # Trả về lỗi 400 Bad Request với chi tiết lỗi
        return jsonify({"message": "Dữ liệu đầu vào không hợp lệ", "errors": err.messages}), 400
    except Exception as e:
        # Xử lý lỗi cơ sở dữ liệu hoặc các lỗi khác
        db.session.rollback() # Hoàn tác các thay đổi nếu có lỗi
        # Trả về lỗi 500 Internal Server Error
        return jsonify({"message": f"Lỗi máy chủ nội bộ khi cập nhật công việc: {str(e)}"}), 500

@bp.route('/todos/<int:id>', methods=['DELETE'])
def delete_todo(id):
    """
    Xóa một công việc bằng ID.
    Xóa công việc khỏi cơ sở dữ liệu.
    Trả về status 204 No Content nếu thành công hoặc lỗi 404/500.
    """
    try:
        # Tìm công việc theo ID
        todo = Todo.query.get(id)
        if not todo:
            # Trả về lỗi 404 Not Found nếu không tìm thấy công việc
            return jsonify({"message": "Không tìm thấy công việc"}), 404

        # Xóa công việc khỏi session và commit
        db.session.delete(todo)
        db.session.commit()

        # Trả về phản hồi rỗng với status 204 No Content (đã xóa thành công)
        return '', 204
    except Exception as e:
        # Xử lý lỗi cơ sở dữ liệu
        db.session.rollback() # Hoàn tác các thay đổi nếu có lỗi
        # Trả về lỗi 500 Internal Server Error
        return jsonify({"message": f"Lỗi máy chủ nội bộ khi xóa công việc: {str(e)}"}), 500
