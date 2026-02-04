# SCAN MASTER PRO - HỆ THỐNG SỐ HÓA VẬT LIỆU 3D

## 1. GIỚI THIỆU CHUNG
**Scan Master Pro** là giải pháp phần mềm - phần cứng tích hợp giúp tự động hóa quy trình chuyển đổi mẫu vật liệu thực tế (vải, da, gỗ...) thành các bản đồ vật liệu kỹ thuật số (PBR Maps) chất lượng cao. Hệ thống được tối ưu hóa cho điện thoại **Xiaomi Mi 13 Pro** (cảm biến 1-inch) và máy ảnh **Nikon Z30**, kết hợp với sức mạnh xử lý của PC.

## 2. TÍNH NĂNG NỔI BẬT (UI/UX)
*   **Giao diện Web App Hiện đại:** Xây dựng trên nền tảng HTML/Tailwind CSS, chạy trực tiếp trên trình duyệt mà không cần cài đặt môi trường phức tạp.
*   **Adaptive Theme (Giao diện thích ứng):**
    *   🔴 **Theme Đỏ:** Tự động kích hoạt khi kết nối Xiaomi Mi 13 Pro (Leica Mode).
    *   🔵 **Theme Xanh:** Tự động kích hoạt khi kết nối Nikon Z30.
*   **Điều khiển ROI (Vùng quan tâm):** Thanh trượt cho phép cắt vùng scan (5x5cm, 10x10cm...) chính xác để loại bỏ các vùng mẫu vật bị lỗi.
*   **Tiến trình thời gian thực:** Thanh Progress Bar hiển thị trạng thái chụp, tải ảnh và xử lý map ngay dưới đáy màn hình.

## 3. CÔNG NGHỆ CỐT LÕI (TECH STACK)
### Phần mềm (Software)
*   **Frontend:** HTML5, JavaScript (Vanilla), Tailwind CSS.
*   **Backend:** Python 3.11 (Flask Server).
*   **Xử lý ảnh (Computer Vision):** OpenCV, NumPy. Sử dụng thuật toán **Photometric Stereo** (khi có đèn) hoặc **Single-Image Reconstruction** (khi không đèn) để tạo Normal/Displacement Map.
*   **Kết nối thiết bị:**
    *   **ADB (Android Debug Bridge):** Gửi lệnh chụp và tải ảnh gốc từ bộ nhớ điện thoại qua cáp USB.
    *   **PySerial:** Điều khiển hệ thống đèn qua Arduino.

### Phần cứng (Hardware)
*   **Camera chính:** Xiaomi Mi 13 Pro (Cảm biến Sony IMX989 1-inch, Lens Tele-Macro 3.2x).
*   **Camera nâng cao:** Nikon Z30 + Lens Macro (50mm hoặc 65mm).
*   **Hộp Scan (Scan Box):**
    *   Thiết kế in 3D dạng Module lắp ghép.
    *   Hệ thống 4 thanh đèn LED tam giác chiếu góc 45 độ.
    *   Ngăn kéo trượt tiện lợi để thay mẫu.

## 4. QUY TRÌNH VẬN HÀNH (WORKFLOW)
1.  **Bước 1: Kết nối**
    *   Cắm cáp USB nối điện thoại/máy ảnh vào PC.
    *   Trên điện thoại: Bật chế độ **USB Debugging** (Gỡ lỗi USB).
2.  **Bước 2: Thiết lập trên phần mềm**
    *   Khởi động `run.bat` để mở giao diện.
    *   Chọn thiết bị (**Mi 13 Pro** hoặc **Canon/Nikon**).
    *   Chọn chế độ (**Có hộp** hoặc **Không hộp**).
    *   Điều chỉnh thanh trượt **ROI** để chọn vùng vải sạch nhất trên màn hình preview.
3.  **Bước 3: Thực thi**
    *   Nhấn nút **BẮT ĐẦU QUÉT**.
    *   Nhập tên vật liệu (VD: `Vai_Jean_01`).
    *   Chọn các Map cần xuất (Base, Normal, Roughness, Displacement, Metallic, AO).
    *   Hệ thống tự động: Chụp -> Tải ảnh -> Xử lý Map -> Lưu vào thư mục.

## 5. CẤU HÌNH PHẦN CỨNG ĐỀ XUẤT (HỘP SCAN)
*   **Lens:** Viltrox 33mm f/1.4 (Cho hộp gọn nhẹ) hoặc Viltrox 56mm f/1.4 + Extension Tube (Cho chất lượng cao hơn).
*   **Kích thước hộp (cho Lens 56mm):** 35cm (Rộng) x 35cm (Sâu) x 46cm (Cao).
*   **Chất liệu in 3D:** Nhựa PLA/PETG màu đen nhám (Matte Black) để chống phản xạ ánh sáng.

## 6. LỘ TRÌNH PHÁT TRIỂN (ROADMAP)
*   **Giai đoạn 1 (Đã hoàn thành):**
    *   Hoàn thiện kết nối Android qua ADB.
    *   Xử lý ảnh tự động tạo 6 Map PBR.
    *   Đóng gói bộ cài đặt "1 Click" (`auto_setup.py`).
*   **Giai đoạn 2 (Đang triển khai):**
    *   Tích hợp điều khiển Nikon Z30 qua USB.
    *   Hoàn thiện phần cứng hộp scan in 3D (V8 - J-Slot Locking).
*   **Giai đoạn 3 (Tương lai):**
    *   Tích hợp AI để tự động xóa vết nối (Seamless Tiling) thông minh hơn OpenCV.
    *   Xây dựng thư viện vật liệu đám mây.
