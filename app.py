Dưới đây là mã nguồn đã được sửa đổi theo các nhận xét và gợi ý, tập trung vào việc khắc phục lỗi, cải thiện hiệu năng (trong giới hạn của mô hình blocking hiện tại), tăng cường khả năng đọc, bảo trì và bảo mật.

Để thực hiện các thay đổi này, tôi đã tạo thêm hai file mới: `config.py` để quản lý cấu hình và `utils.py` để chứa các hàm tiện ích, giúp `app.py` trở nên gọn gàng và dễ quản lý hơn.

---

**Cấu trúc file mới:**

```
project_root/
├── app.py
├── config.py
└── utils.py
```

---

### File: `config.py`

```python
import os

class Config:
    """
    Lớp cấu hình cho ứng dụng Flask.
    Sử dụng biến môi trường để linh hoạt trong các môi trường triển khai khác nhau.
    """
    # Thư mục gốc để lưu trữ các file tải lên
    # Mặc định là 'uploads', có thể ghi đè bằng biến môi trường UPLOAD_FOLDER
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')

    # Các phần mở rộng file được phép tải lên
    ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}

    # Đường dẫn đến script xử lý chính (ví dụ: main.py)
    # Mặc định là 'main.py', có thể ghi đè bằng biến môi trường MAIN_SCRIPT_PATH
    MAIN_SCRIPT_PATH = os.environ.get('MAIN_SCRIPT_PATH', 'main.py')

    # Trình thông dịch Python để chạy script xử lý
    # Mặc định là 'python', có thể ghi đè bằng biến môi trường PYTHON_EXECUTABLE
    PYTHON_EXECUTABLE = os.environ.get('PYTHON_EXECUTABLE', 'python')

    # Chế độ Debug của Flask.
    # CỰC KỲ QUAN TRỌNG: LUÔN ĐẶT LÀ False TRONG MÔI TRƯỜNG PRODUCTION!
    # Mặc định là False, có thể ghi đè bằng biến môi trường FLASK_DEBUG (ví dụ: 'True', '1')
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')

    # Host và Port cho ứng dụng Flask
    FLASK_HOST = os.environ.get('FLASK_HOST', '0.0.0.0')
    FLASK_PORT = int(os.environ.get('FLASK_PORT', 5000))

    # Cấu hình logging (có thể mở rộng thêm nếu cần)
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
```

---

### File: `utils.py`

```python
import os
import subprocess
import json
import logging
import time
from werkzeug.utils import secure_filename
from typing import Tuple, Set

# Lấy logger cho module utils
logger = logging.getLogger(__name__)

def allowed_file(filename: str, allowed_extensions: Set[str]) -> bool:
    """
    Kiểm tra xem tên file có phần mở rộng được phép hay không.

    Args:
        filename (str): Tên của file.
        allowed_extensions (Set[str]): Một tập hợp các phần mở rộng file được phép.

    Returns:
        bool: True nếu phần mở rộng được phép, ngược lại là False.
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_and_organize_file(
    file_storage,  # Kiểu FileStorage từ werkzeug
    upload_folder: str,
    allowed_extensions: Set[str]
) -> Tuple[str, str]:
    """
    Lưu file đã tải lên, tạo một thư mục có dấu thời gian và di chuyển file vào đó.

    Args:
        file_storage: Đối tượng file đã tải lên từ request.files của Flask.
        upload_folder (str): Thư mục cơ sở để lưu trữ các file tải lên.
        allowed_extensions (Set[str]): Một tập hợp các phần mở rộng file được phép.

    Returns:
        Tuple[str, str]: Một tuple chứa (đường dẫn file cuối cùng, đường dẫn thư mục dấu thời gian).

    Raises:
        ValueError: Nếu không có file được chọn, tên file trống hoặc loại file không được phép.
        IOError: Nếu có vấn đề khi lưu hoặc di chuyển file, hoặc tạo thư mục.
    """
    if not file_storage or file_storage.filename == '':
        logger.error("Không có file được chọn hoặc tên file trống.")
        raise ValueError("Không có file được chọn hoặc tên file trống.")

    if not allowed_file(file_storage.filename, allowed_extensions):
        logger.error(f"Loại file không được phép cho: {file_storage.filename}")
        raise ValueError(f"Loại file '{file_storage.filename.rsplit('.', 1)[1]}' không được phép.")

    filename = secure_filename(file_storage.filename)
    initial_file_path = os.path.join(upload_folder, filename)

    try:
        file_storage.save(initial_file_path)
        logger.info(f"File ban đầu đã được lưu tại: {initial_file_path}")
    except Exception as e:
        logger.exception(f"Lỗi khi lưu file ban đầu {initial_file_path}")
        raise IOError(f"Không thể lưu file ban đầu: {e}")

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    timestamp_folder_path = os.path.join(upload_folder, timestamp)

    try:
        os.makedirs(timestamp_folder_path, exist_ok=True)
        logger.info(f"Thư mục dấu thời gian đã được tạo: {timestamp_folder_path}")
    except Exception as e:
        logger.exception(f"Lỗi khi tạo thư mục dấu thời gian {timestamp_folder_path}")
        # Cố gắng dọn dẹp file đã lưu ban đầu nếu việc tạo thư mục thất bại
        if os.path.exists(initial_file_path):
            os.remove(initial_file_path)
            logger.warning(f"Đã dọn dẹp file ban đầu {initial_file_path} do lỗi tạo thư mục.")
        raise IOError(f"Không thể tạo thư mục dấu thời gian: {e}")

    final_file_path = os.path.join(timestamp_folder_path, filename)

    try:
        os.rename(initial_file_path, final_file_path)
        logger.info(f"File đã được di chuyển từ {initial_file_path} đến: {final_file_path}")
    except Exception as e:
        logger.exception(f"Lỗi khi di chuyển file từ {initial_file_path} đến {final_file_path}")
        # Cố gắng dọn dẹp file ban đầu nếu việc đổi tên thất bại
        if os.path.exists(initial_file_path):
            os.remove(initial_file_path)
            logger.warning(f"Đã dọn dẹp file ban đầu {initial_file_path} do lỗi di chuyển file.")
        # Xóa thư mục dấu thời gian rỗng nếu nó được tạo
        if os.path.exists(timestamp_folder_path) and not os.listdir(timestamp_folder_path):
            os.rmdir(timestamp_folder_path)
            logger.warning(f"Đã dọn dẹp thư mục dấu thời gian rỗng {timestamp_folder_path}.")
        raise IOError(f"Không thể di chuyển file: {e}")

    return final_file_path, timestamp_folder_path

def run_processing_script(
    script_path: str,
    python_executable: str,
    input_file_path: str,
    output_folder: str
) -> subprocess.CompletedProcess:
    """
    Chạy một script Python bên ngoài với các đối số được chỉ định.

    Args:
        script_path (str): Đường dẫn đến script Python (ví dụ: 'main.py').
        python_executable (str): Trình thông dịch Python (ví dụ: 'python', 'python3').
        input_file_path (str): Đường dẫn đến file đầu vào cho script.
        output_folder (str): Đường dẫn đến thư mục đầu ra cho script.

    Returns:
        subprocess.CompletedProcess: Đối tượng kết quả từ subprocess.run.

    Raises:
        FileNotFoundError: Nếu script_path hoặc python_executable không tìm thấy.
        subprocess.CalledProcessError: Nếu script trả về mã lỗi khác 0.
        Exception: Đối với các lỗi không mong muốn khác.
    """
    command = [python_executable, script_path, input_file_path, output_folder]
    logger.info(f"Đang chạy lệnh: {' '.join(command)}")

    try:
        # Sử dụng text=True để xử lý xuống dòng phổ quát và giải mã stdout/stderr
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        logger.info(f"stdout của script: {result.stdout.strip()}")
        if result.stderr:
            logger.warning(f"stderr của script: {result.stderr.strip()}")
        return result
    except FileNotFoundError:
        logger.exception(f"Không tìm thấy trình thông dịch Python '{python_executable}' hoặc script '{script_path}'.")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"Script '{script_path}' thất bại với mã thoát {e.returncode}.")
        logger.error(f"stdout của script: {e.stdout.strip()}")
        logger.error(f"stderr của script: {e.stderr.strip()}")
        raise
    except Exception as e:
        logger.exception(f"Một lỗi không mong muốn đã xảy ra khi chạy script '{script_path}'.")
        raise

def load_output_json(output_folder: str) -> dict:
    """
    Tải file 'output.json' từ thư mục được chỉ định.

    Args:
        output_folder (str): Thư mục nơi 'output.json' được mong đợi.

    Returns:
        dict: Dữ liệu JSON đã được phân tích cú pháp.

    Raises:
        FileNotFoundError: Nếu 'output.json' không tìm thấy.
        json.JSONDecodeError: Nếu 'output.json' bị lỗi định dạng.
        IOError: Đối với các vấn đề liên quan đến file khác.
    """
    output_json_path = os.path.join(output_folder, "output.json")
    logger.info(f"Đang cố gắng tải JSON đầu ra từ: {output_json_path}")
    try:
        with open(output_json_path, 'r', encoding='utf-8') as f:
            output_data = json.load(f)
        logger.info(f"JSON đầu ra đã được tải thành công từ: {output_json_path}")
        return output_data
    except FileNotFoundError:
        logger.error(f"Không tìm thấy file đầu ra: {output_json_path}")
        raise
    except json.JSONDecodeError:
        logger.error(f"Lỗi giải mã JSON từ {output_json_path}. File có thể bị lỗi định dạng.")
        raise
    except Exception as e:
        logger.exception(f"Một lỗi không mong muốn đã xảy ra khi đọc hoặc phân tích cú pháp {output_json_path}.")
        raise IOError(f"Không thể đọc hoặc phân tích cú pháp JSON đầu ra: {e}")

```

---

### File: `app.py`

```python
import os
import logging
import json
import subprocess
# Không cần import 'time' ở đây nữa vì nó đã được chuyển vào utils.py
# Không cần import 'secure_filename' ở đây nữa vì nó đã được chuyển vào utils.py

from flask import Flask, request, jsonify

# Import cấu hình và các hàm tiện ích
from config import Config
from utils import save_and_organize_file, run_processing_script, load_output_json

# --- Thiết lập ứng dụng Flask ---
app = Flask(__name__)
app.config.from_object(Config)

# --- Cấu hình Logging ---
# Cấu hình logging cơ bản cho ứng dụng.
# Trong môi trường production, có thể sử dụng cấu hình nâng cao hơn (ví dụ: ghi vào file, dịch vụ log).
logging.basicConfig(level=app.config['LOG_LEVEL'], format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
app.logger.info("Ứng dụng Flask đã được khởi tạo với cấu hình.")

# --- Routes ---
@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Xử lý việc tải lên file, lưu trữ file, chạy một script xử lý bên ngoài,
    và trả về kết quả của script.
    """
    app.logger.info("Đã nhận yêu cầu tải lên file.")

    # 1. Kiểm tra xem có phần 'file' trong request hay không
    if 'file' not in request.files:
        app.logger.warning("Không có phần 'file' trong yêu cầu.")
        return jsonify({"error": "Không có phần 'file' trong yêu cầu"}), 400

    file = request.files['file']

    # 2. Xử lý file và chạy script
    try:
        # Lưu và sắp xếp file đã tải lên
        final_file_path, timestamp_folder_path = save_and_organize_file(
            file, app.config['UPLOAD_FOLDER'], app.config['ALLOWED_EXTENSIONS']
        )
        app.logger.info(f"File '{file.filename}' đã được lưu và sắp xếp thành công trong '{timestamp_folder_path}'.")

        # Chạy script xử lý bên ngoài
        run_processing_script(
            app.config['MAIN_SCRIPT_PATH'],
            app.config['PYTHON_EXECUTABLE'],
            final_file_path,
            timestamp_folder_path
        )
        app.logger.info(f"Script xử lý '{app.config['MAIN_SCRIPT_PATH']}' đã được thực thi thành công.")

        # Tải dữ liệu JSON đầu ra từ thư mục có dấu thời gian
        output_data = load_output_json(timestamp_folder_path)
        app.logger.info("Dữ liệu JSON đầu ra đã được tải thành công.")

        return jsonify(output_data), 200

    except ValueError as e:
        # Lỗi trong quá trình xác thực file hoặc xử lý ban đầu (ví dụ: loại file không được phép)
        app.logger.error(f"Lỗi xử lý file từ phía client: {e}")
        return jsonify({"error": str(e)}), 400
    except IOError as e:
        # Lỗi trong quá trình lưu file, tạo thư mục hoặc di chuyển file
        app.logger.error(f"Lỗi hệ thống file phía máy chủ: {e}")
        return jsonify({"error": f"Thao tác hệ thống file thất bại: {str(e)}"}), 500
    except FileNotFoundError as e:
        # Lỗi cụ thể nếu main.py hoặc trình thông dịch python không tìm thấy, hoặc output.json bị thiếu
        app.logger.error(f"Không tìm thấy file hoặc trình thực thi bắt buộc: {e}")
        if "output.json" in str(e):
            return jsonify({"error": "Quá trình xử lý hoàn tất, nhưng không tìm thấy file đầu ra (output.json)."}), 500
        return jsonify({"error": f"Lỗi cấu hình máy chủ: {str(e)}. Vui lòng kiểm tra đường dẫn script hoặc trình thực thi Python."}), 500
    except subprocess.CalledProcessError as e:
        # Lỗi nếu script bên ngoài trả về mã lỗi khác 0
        app.logger.error(f"Script xử lý '{app.config['MAIN_SCRIPT_PATH']}' thất bại.")
        app.logger.error(f"stdout của script: {e.stdout.strip()}")
        app.logger.error(f"stderr của script: {e.stderr.strip()}")
        return jsonify({"error": f"Quá trình xử lý thất bại: {e.stderr.strip()}"}), 500
    except json.JSONDecodeError:
        # Lỗi nếu output.json bị lỗi định dạng
        app.logger.error(f"Lỗi giải mã output.json trong '{timestamp_folder_path}'. Định dạng JSON không hợp lệ.")
        return jsonify({"error": "Quá trình xử lý hoàn tất, nhưng file đầu ra bị lỗi định dạng."}), 500
    except Exception as e:
        # Bắt tất cả các lỗi không mong muốn khác
        app.logger.exception("Một lỗi không mong muốn đã xảy ra trong quá trình tải lên và xử lý file.")
        return jsonify({"error": f"Một lỗi máy chủ không mong muốn đã xảy ra: {str(e)}"}), 500

# --- Điểm vào ứng dụng ---
if __name__ == '__main__':
    # Đảm bảo thư mục upload tồn tại khi ứng dụng khởi động
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.logger.info(f"Đã đảm bảo thư mục UPLOAD_FOLDER '{app.config['UPLOAD_FOLDER']}' tồn tại.")

    # GHI CHÚ VỀ HIỆU NĂNG:
    # Việc gọi subprocess.run là một hoạt động blocking I/O.
    # Nếu script 'main.py' chạy lâu, nó sẽ chặn toàn bộ worker của Flask,
    # làm giảm khả năng xử lý các yêu cầu đồng thời.
    # Đối với các tác vụ nặng hoặc chạy lâu trong môi trường production,
    # nên cân nhắc sử dụng hàng đợi tác vụ (task queue) như Celery hoặc RQ.
    # Flask có thể trả về một ID tác vụ ngay lập tức, và client có thể thăm dò
    # một endpoint khác để kiểm tra trạng thái hoặc nhận kết quả khi tác vụ hoàn thành.

    # GHI CHÚ VỀ DỌN DẸP FILE:
    # Hiện tại, các thư mục có dấu thời gian và file bên trong không được tự động dọn dẹp.
    # Trong môi trường production, cần triển khai một cơ chế dọn dẹp định kỳ
    # (ví dụ: cron job) để xóa các thư mục cũ hơn một khoảng thời gian nhất định
    # nhằm tránh làm đầy dung lượng lưu trữ.

    # Chạy ứng dụng Flask
    # CẢNH BÁO: debug=True KHÔNG BAO GIỜ được sử dụng trong môi trường production.
    # Nó cho phép thực thi mã tùy ý từ trình duyệt và là một rủi ro bảo mật lớn.
    app.run(
        debug=app.config['DEBUG'],
        host=app.config['FLASK_HOST'],
        port=app.config['FLASK_PORT']
    )
    app.logger.info("Ứng dụng Flask đã dừng.")

```