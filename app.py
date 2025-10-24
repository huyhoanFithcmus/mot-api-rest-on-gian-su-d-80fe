```python
import os
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash, g
from functools import wraps
from models import User, db, add_user, get_user_by_username, get_all_users # Giả định các hàm này đã được tối ưu hoặc sẽ được tối ưu trong models.py

# --- Docstring cho module ---
"""
File chính để chạy ứng dụng Flask.
Quản lý các route, xác thực người dùng, và tương tác cơ sở dữ liệu.
"""

app = Flask(__name__)

# --- Cấu hình ứng dụng ---
# SECRET_KEY: Cần được tạo ngẫu nhiên, đủ mạnh và được lưu trữ trong biến môi trường.
# Đây là khóa bí mật dùng để ký các session cookie.
# Cung cấp giá trị mặc định chỉ cho mục đích phát triển, KHÔNG SỬ DỤNG TRONG MÔI TRƯỜNG SẢN XUẤT.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_very_insecure_default_key_for_dev_only_CHANGE_ME_IN_PROD')
if app.config['SECRET_KEY'] == 'a_very_insecure_default_key_for_dev_only_CHANGE_ME_IN_PROD':
    print("CẢNH BÁO: SECRET_KEY đang sử dụng giá trị mặc định không an toàn. Vui lòng đặt biến môi trường SECRET_KEY trong môi trường sản xuất.")

# Cấu hình cơ sở dữ liệu
# SQLALCHEMY_DATABASE_URI: Có thể được cấu hình qua biến môi trường để dễ dàng thay đổi giữa các môi trường (dev/prod).
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Khởi tạo SQLAlchemy với ứng dụng Flask
db.init_app(app)

# Tạo các bảng cơ sở dữ liệu nếu chúng chưa tồn tại.
# CHÚ Ý: Trong môi trường sản xuất, nên sử dụng Flask-Migrate (hoặc Alembic)
# để quản lý các thay đổi schema cơ sở dữ liệu một cách an toàn và có kiểm soát,
# thay vì gọi db.create_all() trực tiếp mỗi khi ứng dụng khởi động.
with app.app_context():
    # Chỉ tạo bảng trong môi trường phát triển hoặc khi debug được bật.
    # Điều này ngăn chặn việc ghi đè hoặc xung đột trong môi trường sản xuất.
    if app.debug or os.environ.get('FLASK_ENV') == 'development':
        db.create_all()


# --- Helper Functions / Decorators ---

def login_required(f):
    """
    Decorator để yêu cầu người dùng phải đăng nhập để truy cập route.
    Nếu người dùng chưa đăng nhập, sẽ chuyển hướng đến trang đăng nhập và hiển thị thông báo.
    Lưu đối tượng người dùng hiện tại vào `flask.g.user` để các hàm route có thể truy cập
    mà không cần thay đổi chữ ký hàm.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Vui lòng đăng nhập để truy cập trang này.', 'info')
            return redirect(url_for('login'))
        
        current_user = User.query.get(user_id)
        if not current_user:
            # Xử lý trường hợp user_id có trong session nhưng user không tồn tại trong DB
            session.pop('user_id', None) # Xóa user_id không hợp lệ khỏi session
            flash('Tài khoản của bạn không còn tồn tại hoặc đã bị xóa. Vui lòng đăng nhập lại.', 'warning')
            return redirect(url_for('login'))

        g.user = current_user # Lưu đối tượng người dùng vào flask.g
        return f(*args, **kwargs) # Gọi hàm gốc mà không truyền current_user làm đối số
    return decorated_function


def user_to_dict_safe(user):
    """
    Chuyển đổi đối tượng User thành dictionary, loại bỏ các trường nhạy cảm.
    (Giả định hàm này sẽ nằm trong models.py hoặc là một phương thức của User model
    để đảm bảo tính nhất quán và dễ bảo trì).
    """
    if user:
        return {
            'id': user.id,
            'username': user.username,
            # KHÔNG bao gồm password_hash hoặc các thông tin nhạy cảm khác
            # Thêm các trường khác nếu cần, ví dụ: 'email': user.email
        }
    return None


# --- Routes ---

@app.route('/')
def index():
    """
    Route cho trang chủ của ứng dụng.
    """
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Route để đăng ký người dùng mới.
    - Xử lý hiển thị form đăng ký (GET).
    - Xử lý gửi dữ liệu đăng ký (POST).
    - Kiểm tra tên người dùng đã tồn tại và hiển thị thông báo thân thiện.
    - Sử dụng `flash` để hiển thị thông báo cho người dùng.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Vui lòng điền đầy đủ tên người dùng và mật khẩu.', 'danger')
            return render_template('register.html', username=username) # Giữ lại username đã nhập

        if get_user_by_username(username):
            flash('Tên người dùng đã tồn tại. Vui lòng chọn tên khác.', 'warning')
            return render_template('register.html', username=username) # Giữ lại username đã nhập
        
        new_user = User(username=username)
        new_user.set_password(password)
        add_user(new_user)
        flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Route để đăng nhập người dùng.
    - Xử lý hiển thị form đăng nhập (GET).
    - Xử lý gửi dữ liệu đăng nhập (POST).
    - Xác thực thông tin đăng nhập và thiết lập session.
    - Sử dụng `flash` để hiển thị thông báo cho người dùng.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = get_user_by_username(username)

        if user and user.check_password(password):
            session['user_id'] = user.id
            flash(f'Chào mừng trở lại, {user.username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Tên người dùng hoặc mật khẩu không đúng.', 'danger')
            return render_template('login.html', username=username) # Giữ lại username đã nhập
    return render_template('login.html')


@app.route('/logout')
def logout():
    """
    Route để đăng xuất người dùng.
    - Xóa `user_id` khỏi session.
    - Hiển thị thông báo đăng xuất thành công.
    """
    session.pop('user_id', None)
    flash('Bạn đã đăng xuất thành công.', 'info')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required # Yêu cầu người dùng phải đăng nhập để truy cập trang này
def dashboard():
    """
    Route cho trang bảng điều khiển của người dùng.
    - Yêu cầu người dùng phải đăng nhập thông qua decorator `login_required`.
    - Truy cập đối tượng người dùng hiện tại thông qua `g.user` (được thiết lập bởi decorator).
    """
    # Đối tượng người dùng hiện tại được lưu trong `g.user` bởi decorator `login_required`
    return render_template('dashboard.html', user=g.user)


@app.route('/api/data')
@login_required # BẢO MẬT: Yêu cầu người dùng phải đăng nhập để truy cập endpoint API này
def api_data():
    """
    Endpoint API trả về danh sách người dùng (có hỗ trợ phân trang).
    - Yêu cầu người dùng phải đăng nhập.
    - Triển khai phân trang để cải thiện hiệu năng khi số lượng người dùng lớn.
    - Chỉ trả về các trường dữ liệu an toàn, không nhạy cảm.
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # CHÚ Ý: Hàm `get_all_users` trong `models.py` nên được cập nhật để hỗ trợ phân trang
    # trực tiếp ở cấp độ cơ sở dữ liệu (ví dụ: sử dụng `User.query.paginate(...)`)
    # để tránh tải tất cả dữ liệu vào bộ nhớ, điều này rất quan trọng đối với hiệu năng.
    # Ví dụ về cách gọi hàm phân trang từ models.py (nếu đã được cập nhật):
    # paginated_users_obj = get_paginated_users(page=page, per_page=per_page)
    # users = paginated_users_obj.items
    # total_users = paginated_users_obj.total
    # total_pages = paginated_users_obj.pages

    # Tạm thời, nếu `get_all_users` chỉ trả về tất cả, ta sẽ thực hiện phân trang thủ công
    # (ít hiệu quả hơn nếu số lượng người dùng rất lớn, nhưng khắc phục vấn đề bảo mật và cung cấp phân trang cơ bản)
    all_users = get_all_users() # Giả định hàm này trả về một danh sách các đối tượng User
    
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    paginated_users = all_users[start_index:end_index]

    users_data = [user_to_dict_safe(user) for user in paginated_users]
    
    # Cung cấp thông tin phân trang trong phản hồi API để client có thể xử lý
    response = {
        'users': users_data,
        'page': page,
        'per_page': per_page,
        'total_users': len(all_users), # Cần lấy từ DB nếu dùng paginate hiệu quả
        'total_pages': (len(all_users) + per_page - 1) // per_page # Cần lấy từ DB nếu dùng paginate hiệu quả
    }
    return jsonify(response)


if __name__ == '__main__':
    # Chạy ứng dụng Flask.
    # `debug=True` chỉ nên dùng trong môi trường phát triển vì nó kích hoạt debugger
    # và tự động tải lại code khi có thay đổi, nhưng không an toàn cho môi trường sản xuất.
    # Trong môi trường sản xuất, hãy sử dụng một WSGI server như Gunicorn hoặc uWSGI.
    app.run(debug=True)
```