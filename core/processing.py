import cv2
import numpy as np
import os
import json

class PBRProcessor:
    def __init__(self, output_dir):
        self.output_dir = output_dir

    def crop_image(self, image_path, roi_rect):
        """
        Crop image based on ROI rectangle (percentages).
        roi_rect: {x, y, w, h} float 0.0-1.0
        Returns path to cropped image.
        """
        if not roi_rect:
            return image_path
            
        img = cv2.imread(image_path)
        if img is None:
            return image_path
            
        H, W = img.shape[:2]
        x = int(roi_rect['x'] * W)
        y = int(roi_rect['y'] * H)
        w = int(roi_rect['w'] * W)
        h = int(roi_rect['h'] * H)
        
        # Boundary checks
        x = max(0, x)
        y = max(0, y)
        w = min(w, W - x)
        h = min(h, H - y)
        
        if w <= 0 or h <= 0:
            return image_path
            
        crop = img[y:y+h, x:x+w]
        
        dir_name = os.path.dirname(image_path)
        base_name = os.path.basename(image_path)
        name, ext = os.path.splitext(base_name)
        
        crop_path = os.path.join(dir_name, f"{name}_crop{ext}")
        cv2.imwrite(crop_path, crop)
        
        return crop_path

    def focus_stack(self, image_paths):
        """
        Merge multiple images using Focus Stacking (Depth of Field composition).
        Returns path to the merged image.
        """
        if not image_paths:
            return None
            
        print(f"Stacking {len(image_paths)} images...")
        
        # Load images
        images = []
        for path in image_paths:
            img = cv2.imread(path)
            if img is not None:
                images.append(img)
                
        if not images:
            return None
            
        # Align images (Simple ECC - taking first as reference)
        # Skipping heavy alignment for speed, assuming tripod.
        
        # Focus Stacking using Laplacian Pyramid / Max Gradient
        # Simple implementation:
        
        # 1. Compute Gradients
        laps = []
        for img in images:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Use Laplacian for sharpness metric
            lap = cv2.Laplacian(gray, cv2.CV_64F)
            laps.append(np.abs(lap))
            
        # 2. Select pixels
        laps = np.array(laps) # (N, H, W)
        # Find index of max laplacian at each pixel
        idx_map = np.argmax(laps, axis=0) # (H, W)
        
        # 3. Reconstruct
        h, w, c = images[0].shape
        output = np.zeros_like(images[0])
        
        # This pixel-wise selection can be noisy. 
        # A proper pyramid blend is better but complex.
        # Optimization: Use mask copying
        for i in range(len(images)):
            mask = (idx_map == i)
            output[mask] = images[i][mask]
            
        # Save result
        first_name = os.path.basename(image_paths[0])
        name_no_ext = os.path.splitext(first_name)[0].split('_stack_')[0]
        output_path = os.path.join(self.output_dir, f"{name_no_ext}_Stacked.jpg")
        cv2.imwrite(output_path, output)
        
        return output_path

    def process_photometric(self, images_dict, selected_maps=None, params=None, progress_callback=None, output_dir=None):
        """
        images_dict: {'north': path, 'east': path, ...}
        params: Dictionary chứa các tham số điều chỉnh
        progress_callback: function(percent, message)
        output_dir: Thư mục lưu kết quả (override self.output_dir)
        """
        if params is None:
            params = {}
            
        target_dir = output_dir if output_dir else self.output_dir
        os.makedirs(target_dir, exist_ok=True)

        if progress_callback:
            progress_callback(5, "Loading images...")

        # Determine Base Filename
        first_path = images_dict['north']
        filename = os.path.basename(first_path)
        # scan_timestamp_north.jpg -> scan_timestamp
        name_parts = filename.split('_')
        if len(name_parts) > 1:
            name_no_ext = "_".join(name_parts[:-1])
        else:
            name_no_ext = os.path.splitext(filename)[0]

        # Load images
        try:
            north_c = cv2.imread(images_dict['north'])
            east_c = cv2.imread(images_dict['east'])
            south_c = cv2.imread(images_dict['south'])
            west_c = cv2.imread(images_dict['west'])
            
            if north_c is None or east_c is None:
                raise ValueError("Cannot read source images")
                
            # Base Color: Average
            if progress_callback:
                progress_callback(10, "Generating Base Color...")
                
            base_color_img = cv2.addWeighted(north_c, 0.25, east_c, 0.25, 0)
            base_color_img = cv2.addWeighted(base_color_img, 1.0, south_c, 0.25, 0)
            base_color_img = cv2.addWeighted(base_color_img, 1.0, west_c, 0.25, 0)
            
            base_color_path = os.path.join(target_dir, f"{name_no_ext}_BaseColor.jpg")
            cv2.imwrite(base_color_path, base_color_img)
            
            # Return relative path for frontend (assuming target_dir is under scans/...)
            # We need to construct the URL path properly. 
            # If target_dir is "scans/MaterialName", we want "/scans/MaterialName/file.jpg"
            # Assuming target_dir is absolute or relative to app root.
            # Best is to return the relative part from 'scans' or just the filename if frontend handles it.
            # Current app uses "/scans/filename" which implies flat structure.
            # With subfolders, we should return "/scans/Subfolder/filename".
            
            # Simple hack: find 'scans' in path and take everything after
            rel_path = os.path.relpath(base_color_path, start=os.path.dirname(self.output_dir)) 
            # self.output_dir is usually 'scans'. 
            # If target_dir is 'scans/MaterialA', relpath is 'MaterialA/file.jpg'.
            # We want '/scans/MaterialA/file.jpg'.
            
            web_path = f"/scans/{os.path.relpath(base_color_path, self.output_dir).replace(os.sep, '/')}"
            if web_path.startswith("/scans/.."): # Handle case where output_dir wasn't 'scans'
                 web_path = f"/scans/{os.path.basename(target_dir)}/{os.path.basename(base_color_path)}"

            results = {
                "base_color": web_path
            }
            
            if not selected_maps:
                selected_maps = ['normal', 'displacement', 'roughness', 'ao', 'metallic']
                
            # Grayscale for calculations
            north = cv2.cvtColor(north_c, cv2.COLOR_BGR2GRAY).astype(np.float32)
            east = cv2.cvtColor(east_c, cv2.COLOR_BGR2GRAY).astype(np.float32)
            south = cv2.cvtColor(south_c, cv2.COLOR_BGR2GRAY).astype(np.float32)
            west = cv2.cvtColor(west_c, cv2.COLOR_BGR2GRAY).astype(np.float32)

            total_steps = len(selected_maps)
            current_step = 0

            # 2. Normal Map (Photometric Stereo - Difference Method)
            if 'normal' in selected_maps:
                if progress_callback:
                    progress_callback(20, "Generating Normal Map...")
                    
                strength = float(params.get('normal_strength', 1.0))
                nx = (east - west) * strength
                ny = (north - south) * strength
                nz = np.ones_like(nx) * 255.0 # Assume shallow depth
                
                # Normalize
                length = np.sqrt(nx**2 + ny**2 + nz**2)
                # Avoid division by zero
                length[length == 0] = 1.0
                
                nx, ny, nz = nx / length, ny / length, nz / length
                
                # Map -1..1 to 0..255
                # Normal map standard: R=X, G=Y, B=Z. OpenCV uses BGR.
                # So B=Z, G=Y, R=X.
                # X: -1 -> 0, 1 -> 255 => (x+1)/2 * 255
                
                normal_img = np.dstack(((nz + 1) / 2 * 255, (ny + 1) / 2 * 255, (nx + 1) / 2 * 255))
                normal_path = os.path.join(target_dir, f"{name_no_ext}_Normal.png")
                cv2.imwrite(normal_path, normal_img.astype(np.uint8))
                
                web_path = f"/scans/{os.path.relpath(normal_path, self.output_dir).replace(os.sep, '/')}"
                results["normal"] = web_path
            
            # Use averaged gray for other single-image maps
            gray = cv2.cvtColor(base_color_img, cv2.COLOR_BGR2GRAY)
            
            # 3. Displacement
            if 'displacement' in selected_maps:
                if progress_callback:
                    progress_callback(40, "Generating Displacement Map...")
                    
                displacement = gray
                
                # Optional contrast stretch for displacement
                contrast = float(params.get('displacement_contrast', 1.0))
                if contrast != 1.0:
                    # Simple contrast around mid-gray (127)
                    f = displacement.astype(np.float32)
                    f = (f - 127.0) * contrast + 127.0
                    displacement = np.clip(f, 0, 255).astype(np.uint8)

                disp_path = os.path.join(target_dir, f"{name_no_ext}_Displacement.jpg")
                cv2.imwrite(disp_path, displacement)
                web_path = f"/scans/{os.path.relpath(disp_path, self.output_dir).replace(os.sep, '/')}"
                results["displacement"] = web_path
            
            # 4. Roughness
            if 'roughness' in selected_maps:
                if progress_callback:
                    progress_callback(60, "Generating Roughness Map...")

                # Use simple edge detection on averaged image
                sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
                sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
                magnitude = np.sqrt(sobelx**2 + sobely**2)
                roughness = cv2.normalize(magnitude, None, 0, 255, cv2.NORM_MINMAX)
                roughness = 255 - roughness 
                
                # Apply min/max params
                r_min = int(params.get('roughness_min', 0))
                r_max = int(params.get('roughness_max', 255))
                rough_remapped = (roughness / 255.0) * (r_max - r_min) + r_min
                roughness = np.clip(rough_remapped, 0, 255).astype(np.uint8)

                rough_path = os.path.join(target_dir, f"{name_no_ext}_Roughness.jpg")
                cv2.imwrite(rough_path, roughness)
                web_path = f"/scans/{os.path.relpath(rough_path, self.output_dir).replace(os.sep, '/')}"
                results["roughness"] = web_path
            
            # 5. Ambient Occlusion
            if 'ao' in selected_maps:
                ao = cv2.GaussianBlur(gray, (0, 0), 3)
                ao = cv2.addWeighted(gray, 0.5, ao, 0.5, 0)
                ao_path = os.path.join(target_dir, f"{name_no_ext}_AO.jpg")
                cv2.imwrite(ao_path, ao)
                web_path = f"/scans/{os.path.relpath(ao_path, self.output_dir).replace(os.sep, '/')}"
                results["ao"] = web_path
            
            # 6. Metallic
            if 'metallic' in selected_maps:
                metallic = np.zeros_like(gray)
                meta_path = os.path.join(target_dir, f"{name_no_ext}_Metallic.jpg")
                cv2.imwrite(meta_path, metallic)
                web_path = f"/scans/{os.path.relpath(meta_path, self.output_dir).replace(os.sep, '/')}"
                results["metallic"] = web_path
                
            return results
            
        except Exception as e:
            print(f"Error in photometric processing: {e}")
            raise e

    def process_image(self, image_path, selected_maps=None, params=None, progress_callback=None, output_dir=None):
        """
        Xử lý ảnh đơn thành các PBR maps.
        Cập nhật theo thuật toán ScanMasterUSB (User Provided).
        output_dir: Thư mục lưu kết quả (override self.output_dir)
        """
        if params is None:
            params = {}
            
        target_dir = output_dir if output_dir else self.output_dir
        os.makedirs(target_dir, exist_ok=True)
        
        if progress_callback:
            progress_callback(5, "Loading image...")
            
        filename = os.path.basename(image_path)
        name_no_ext = os.path.splitext(filename)[0]
        
        # Đọc ảnh
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError("Không thể đọc ảnh")

        # 1. Base Color (Ảnh gốc)
        base_color_path = os.path.join(target_dir, f"{name_no_ext}_BaseColor.png") # User uses png
        # Convert to PNG if needed or just copy
        cv2.imwrite(base_color_path, img)

        web_path = f"/scans/{os.path.relpath(base_color_path, self.output_dir).replace(os.sep, '/')}"
        results = {
            "base_color": web_path
        }

        # User Code Logic:
        # Chuyển đổi sang float32 để tính toán độ chính xác cao
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        
        # Nếu selected_maps là None hoặc rỗng, mặc định chọn hết
        all_maps = ['normal', 'displacement', 'roughness', 'ao', 'metallic']
        if not selected_maps:
            selected_maps = all_maps

        # 2. Displacement Map (Độ sâu dựa trên độ sáng, khử nhiễu nhẹ)
        # disp = cv2.GaussianBlur(gray, (7, 7), 0)
        disp = cv2.GaussianBlur(gray, (7, 7), 0)
        
        if 'displacement' in selected_maps:
            if progress_callback: progress_callback(40, "Generating Displacement...")
            
            # User output: (disp * 255).astype(np.uint8)
            disp_uint8 = (disp * 255).astype(np.uint8)
            
            disp_path = os.path.join(target_dir, f"{name_no_ext}_Displacement.png")
            cv2.imwrite(disp_path, disp_uint8)
            web_path = f"/scans/{os.path.relpath(disp_path, self.output_dir).replace(os.sep, '/')}"
            results["displacement"] = web_path
        
        # 3. Normal Map (Sử dụng toán tử Sobel để tính vector bề mặt)
        if 'normal' in selected_maps:
            if progress_callback: progress_callback(20, "Generating Normal...")
            
            # strength = 3.0 # Độ mạnh của khối (User default)
            strength = float(params.get('normal_strength', 3.0)) 
            
            sx = cv2.Sobel(disp, cv2.CV_32F, 1, 0, ksize=3) 
            sy = cv2.Sobel(disp, cv2.CV_32F, 0, 1, ksize=3) 
            n_z = np.ones_like(disp) 
            
            # Chuẩn hóa vector Normal 
            norm = np.sqrt((sx*strength)**2 + (sy*strength)**2 + n_z**2) 
            
            # Avoid division by zero
            norm[norm == 0] = 1.0

            normal_map = np.zeros_like(img)
            normal_map[..., 0] = ((-sx * strength / norm) * 0.5 + 0.5) * 255 # Index 0
            normal_map[..., 1] = ((-sy * strength / norm) * 0.5 + 0.5) * 255 # Index 1
            normal_map[..., 2] = ((n_z / norm) * 0.5 + 0.5) * 255           # Index 2
            
            normal_path = os.path.join(target_dir, f"{name_no_ext}_Normal.png")
            cv2.imwrite(normal_path, normal_map.astype(np.uint8))
            web_path = f"/scans/{os.path.relpath(normal_path, self.output_dir).replace(os.sep, '/')}"
            results["normal"] = web_path
        
        # 4. Roughness Map (Độ nhám - nghịch đảo của độ bóng)
        if 'roughness' in selected_maps:
            if progress_callback: progress_callback(60, "Generating Roughness...")
            
            rough = 1.0 - disp 
            rough = np.clip(rough * 1.1, 0, 1) # Tăng nhẹ độ nhám cho bề mặt vải (User logic)
            
            rough_uint8 = (rough * 255).astype(np.uint8)
            rough_path = os.path.join(target_dir, f"{name_no_ext}_Roughness.png")
            cv2.imwrite(rough_path, rough_uint8)
            web_path = f"/scans/{os.path.relpath(rough_path, self.output_dir).replace(os.sep, '/')}"
            results["roughness"] = web_path
        
        # 5. Metallic Map (Mặc định bằng 0 cho vật liệu phi kim loại như vải)
        if 'metallic' in selected_maps:
            metal = np.zeros_like((gray * 255).astype(np.uint8)) 
            metal_path = os.path.join(target_dir, f"{name_no_ext}_Metallic.png")
            cv2.imwrite(metal_path, metal)
            web_path = f"/scans/{os.path.relpath(metal_path, self.output_dir).replace(os.sep, '/')}"
            results["metallic"] = web_path

        # 6. Ambient Occlusion (AO - Tạo bóng đổ hốc mắt)
        if 'ao' in selected_maps:
            ao = cv2.pow(disp, 0.5) # Giả lập AO bằng cách làm tối các vùng sâu 
            ao_uint8 = (ao * 255).astype(np.uint8)
            ao_path = os.path.join(target_dir, f"{name_no_ext}_AO.png")
            cv2.imwrite(ao_path, ao_uint8)
            web_path = f"/scans/{os.path.relpath(ao_path, self.output_dir).replace(os.sep, '/')}"
            results["ao"] = web_path
        
        return results

    def crop_image(self, image_path, roi_rect):
        """
        Crop image based on ROI rectangle (percentages).
        roi_rect: {x, y, w, h} float 0.0-1.0
        Returns path to cropped image.
        """
        if not roi_rect:
            return image_path
            
        img = cv2.imread(image_path)
        if img is None:
            return image_path
            
        H, W = img.shape[:2]
        x = int(roi_rect['x'] * W)
        y = int(roi_rect['y'] * H)
        w = int(roi_rect['w'] * W)
        h = int(roi_rect['h'] * H)
        
        # Boundary checks
        x = max(0, x)
        y = max(0, y)
        w = min(w, W - x)
        h = min(h, H - y)
        
        if w <= 0 or h <= 0:
            return image_path
            
        crop = img[y:y+h, x:x+w]
        
        dir_name = os.path.dirname(image_path)
        base_name = os.path.basename(image_path)
        name, ext = os.path.splitext(base_name)
        
        # Avoid creating multiple _crop_crop suffix
        if name.endswith('_crop'):
             name = name[:-5]
             
        crop_path = os.path.join(dir_name, f"{name}_crop{ext}")
        cv2.imwrite(crop_path, crop)
        
        return crop_path
