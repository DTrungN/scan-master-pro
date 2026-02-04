import os
import sys
import webbrowser
import glob
import json
import shutil
import zipfile
import time
import datetime
import uuid
import threading
from flask import Flask, render_template, jsonify, request, send_from_directory, send_file
from core.hardware import HardwareController
from core.processing import PBRProcessor

# Cấu hình
UPLOAD_FOLDER = 'scans'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Global Task Registry
TASKS = {}

# Khởi tạo modules
hw_controller = HardwareController(upload_folder=UPLOAD_FOLDER)
processor = PBRProcessor(output_dir=UPLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Kiểm tra trạng thái kết nối thiết bị"""
    device_type = request.args.get('device', 'mi13')
    if device_type == 'z30':
        device_status = hw_controller.nikon.check_connection()
    else:
        device_status = hw_controller.adb.check_connection()
    return jsonify(device_status)

@app.route('/api/camera/config', methods=['GET', 'POST'])
def camera_config():
    """Get or Set Camera Configuration (ISO, Aperture, etc.)"""
    device_type = request.args.get('device', 'z30')
    # Use helper if available or access directly if we know it's Nikon
    # hw_controller.get_device_handler is available
    device = hw_controller.get_device_handler(device_type)
    
    # Only Nikon supports these configs via this API for now
    # if device_type != 'z30':
    #      return jsonify({'success': False, 'error': 'Device does not support config'}), 400

    if request.method == 'GET':
        config_name = request.args.get('config')
        if config_name:
            val = device.get_config(config_name)
            return jsonify({'config': config_name, 'value': val})
        else:
            # Return all common configs
            configs = {
                'iso': device.get_config('iso'),
                'aperture': device.get_config('aperture'),
                'shutterspeed': device.get_config('shutterspeed'),
                'imagesize': device.get_config('imagesize')
            }
            return jsonify(configs)
            
    elif request.method == 'POST':
        data = request.json
        config_name = data.get('config')
        value = data.get('value')
        
        if device.set_config(config_name, value):
             return jsonify({'success': True, 'message': f'Set {config_name} to {value}'})
        else:
             return jsonify({'success': False, 'error': 'Failed to set config'}), 500

@app.route('/api/preview')
def get_preview():
    """Get live preview image"""
    device_type = request.args.get('device', 'mi13')
    
    if device_type == 'z30':
        # Ensure correct device is active? 
        # For Nikon, we might need to wake it up or switch modes.
        pass
        
    # Capture preview
    # Use a temp path
    preview_path = os.path.join(UPLOAD_FOLDER, 'preview.jpg')
    
    if device_type == 'z30':
        result_path = hw_controller.nikon.capture_preview(preview_path)
    else:
        result_path = hw_controller.adb.capture_preview()
        # ADB handler returns a path to its own temp file usually, 
        # or we might need to move it.
        # My implementation of adb.capture_preview returns local_path
        
    if result_path and os.path.exists(result_path):
        return send_file(result_path, mimetype='image/png')
    else:
        return jsonify({'error': 'Failed to capture preview from device'}), 500

@app.route('/api/progress/<task_id>')
def get_progress(task_id):
    task = TASKS.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)

def update_progress(task_id, percent, message):
    if task_id in TASKS:
        TASKS[task_id]['percent'] = percent
        TASKS[task_id]['message'] = message

def task_scan_process(task_id, data):
    TASKS[task_id]['status'] = 'processing'
    update_progress(task_id, 0, 'Starting scan...')
    
    try:
        device_type = data.get('device_type', 'mi13')
        raw_name = data.get('name', '').strip() or data.get('material_name', '').strip()
        tags = data.get('tags', '') # Tags from user input
        
        # 0. Prepare Folder Structure
        # Name convention: MaterialName (if duplicate, append timestamp)
        # But user wants "PBR -> TEN VAI".
        
        if not raw_name:
            raw_name = f"Material_{int(time.time())}"
            
        safe_name = "".join([c for c in raw_name if c.isalpha() or c.isdigit() or c==' ' or c=='_']).rstrip()
        safe_name = safe_name.replace(' ', '_')
        
        # Check if folder exists
        material_folder = os.path.join(UPLOAD_FOLDER, safe_name)
        if os.path.exists(material_folder):
            # Append timestamp to avoid overwrite
            safe_name = f"{safe_name}_{int(time.time())}"
            material_folder = os.path.join(UPLOAD_FOLDER, safe_name)
            
        os.makedirs(material_folder, exist_ok=True)
        
        # 1. Capture Images
        update_progress(task_id, 10, 'Capturing images...')
        
        scan_mode = data.get('scan_mode', 'single')
        
        if scan_mode == 'focus_stack':
            # Default 5 steps, step size can be tweaked in hardware.py or via params
            steps = 5
            focus_step = -20
            
            params = data.get('params', {})
            if params:
                steps = int(params.get('steps', 5))
                # focus_step can be int or string
                fs = params.get('focus_step', -20)
                try:
                    focus_step = int(fs)
                except:
                    focus_step = str(fs)
            
            captured_files = hw_controller.capture_focus_stack(device_type=device_type, steps=steps, focus_step=focus_step)
        elif scan_mode == 'photometric':
            captured_files = hw_controller.capture_photometric_sequence(device_type=device_type)
        else:
            # Single
            captured_files = hw_controller.capture_single(device_type=device_type)
            
        update_progress(task_id, 40, 'Images captured. Moving files...')
        
        # Move captured files to material_folder
        new_captured_files = {}
        
        # If captured_files is dict (photometric)
        if isinstance(captured_files, dict):
            for key, path in captured_files.items():
                if path and os.path.exists(path):
                    filename = os.path.basename(path)
                    new_path = os.path.join(material_folder, filename)
                    shutil.move(path, new_path)
                    new_captured_files[key] = new_path
        # If list (focus stack)
        elif isinstance(captured_files, list):
            new_list = []
            for path in captured_files:
                if path and os.path.exists(path):
                    filename = os.path.basename(path)
                    new_path = os.path.join(material_folder, filename)
                    shutil.move(path, new_path)
                    new_list.append(new_path)
            new_captured_files = new_list # Store list
            
        # If single file (string) - fallback
        elif isinstance(captured_files, str) and os.path.exists(captured_files):
             filename = os.path.basename(captured_files)
             new_path = os.path.join(material_folder, filename)
             shutil.move(captured_files, new_path)
             new_captured_files = new_path # Treat as single path
        
        captured_files = new_captured_files
        
        # 2. Process PBR
        # Only process PBR if we have photometric data or single image (as base)
        # If focus stack, we currently don't have a stacking algorithm in python here yet,
        # so we might skip PBR or just process the first image?
        # User requirement says "Create PBR map" is step 4.
        # If focus stack is used, likely they want the merged result to be PBR'd?
        # For now, if it's a list, we take the middle or first image as "BaseColor" for simple PBR
        # or skip if user didn't ask for PBR on stack (which is complex without merging).
        
        results = {}
        if scan_mode == 'photometric' and isinstance(captured_files, dict):
            update_progress(task_id, 50, 'Generating PBR maps...')
            def pbr_progress(p, m):
                total_p = 50 + (p * 0.45) 
                update_progress(task_id, int(total_p), f"Processing: {m}")
            
            results = processor.process_photometric(
                captured_files, 
                selected_maps=data.get('maps'), 
                params=data.get('params'), 
                progress_callback=pbr_progress,
                output_dir=material_folder
            )
        elif scan_mode == 'single' or (scan_mode == 'focus_stack' and captured_files):
            update_progress(task_id, 50, 'Generating PBR maps (Single/Stack)...')
            
            # For stack, pick the first one for now as Base
            target_file = captured_files
            if isinstance(captured_files, list):
                if len(captured_files) > 0:
                    target_file = captured_files[0]
                else:
                    target_file = None
            
            if target_file:
                def pbr_progress(p, m):
                    total_p = 50 + (p * 0.45) 
                    update_progress(task_id, int(total_p), f"Processing: {m}")
                
                results = processor.process_image(
                    target_file,
                    selected_maps=data.get('maps'),
                    params=data.get('params'),
                    progress_callback=pbr_progress,
                    output_dir=material_folder
                )
            
        # 3. Create Metadata JSON
        metadata = {
            "id": str(uuid.uuid4()),
            "name": raw_name, # Original user input name
            "folder_name": safe_name,
            "created_at": time.time(),
            "tags": [t.strip() for t in tags.split(',') if t.strip()],
            "device": device_type,
            "scan_mode": scan_mode,
            "maps": results,
            "source_files": captured_files if isinstance(captured_files, (list, dict)) else [captured_files]
        }
        
        with open(os.path.join(material_folder, "info.json"), 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)
        
        TASKS[task_id]['result'] = results
        TASKS[task_id]['status'] = 'completed'
        update_progress(task_id, 100, 'Scan completed successfully')
        
    except Exception as e:
        print(f"Task Failed: {e}")
        TASKS[task_id]['status'] = 'failed'
        TASKS[task_id]['error'] = str(e)

def task_reprocess_process(task_id, data):
    TASKS[task_id]['status'] = 'processing'
    update_progress(task_id, 0, 'Starting reprocessing...')
    
    try:
        # folder_name should be passed now, or we infer from filename path
        folder_name = data.get('folder_name')
        
        if not folder_name:
             # Fallback: try to find from filename
             filename = data.get('filename') # e.g. "Material/file.jpg"
             if filename and '/' in filename:
                 folder_name = os.path.dirname(filename)
             else:
                 raise ValueError("No folder_name provided")
                 
        target_dir = os.path.join(UPLOAD_FOLDER, folder_name)
        if not os.path.exists(target_dir):
             raise FileNotFoundError(f"Folder {folder_name} not found")

        # Load info.json if exists to get base name
        info_path = os.path.join(target_dir, "info.json")
        base_name = folder_name # Default
        if os.path.exists(info_path):
            try:
                with open(info_path, 'r') as f:
                    meta = json.load(f)
                    base_name = meta.get('folder_name', folder_name)
            except: pass
            
        # Look for the 4 files (north/east/south/west) in target_dir
        directions = ['north', 'east', 'south', 'west']
        found_files = {}
        missing_files = []
        
        # We need to find the specific files. 
        # Strategy: Look for files ending with _north.jpg, etc.
        files_in_dir = os.listdir(target_dir)
        
        for d in directions:
            # Find file ending with _{d}.jpg or _{d}.png
            match = next((f for f in files_in_dir if f.lower().endswith(f"_{d}.jpg") or f.lower().endswith(f"_{d}.png")), None)
            if match:
                found_files[d] = os.path.join(target_dir, match)
            else:
                missing_files.append(d)
        
        if not missing_files:
            # Photometric
            update_progress(task_id, 20, 'Found photometric sequence. Processing...')
            
            def pbr_progress(p, m):
                total_p = 20 + (p * 0.8)
                update_progress(task_id, int(total_p), f"Processing: {m}")
                
            results = processor.process_photometric(
                found_files, 
                selected_maps=data.get('maps'), 
                params=data.get('params'), 
                progress_callback=pbr_progress,
                output_dir=target_dir
            )
        else:
            # Single Image
            # Find a suitable base image
            base_img = next((f for f in files_in_dir if "BaseColor" in f), None)
            if not base_img:
                # Try finding any image that is not a map
                candidates = [f for f in files_in_dir if f.lower().endswith(('.jpg', '.png'))]
                # Filter out likely maps
                candidates = [f for f in candidates if not any(x in f for x in ['_Normal', '_Roughness', '_Displacement', '_AO', '_Metallic'])]
                if candidates:
                    base_img = candidates[0]
            
            if not base_img:
                raise FileNotFoundError("No suitable source image found for reprocessing")
                
            filepath = os.path.join(target_dir, base_img)
            
            update_progress(task_id, 20, 'Processing single image...')
            
            def pbr_progress(p, m):
                total_p = 20 + (p * 0.8)
                update_progress(task_id, int(total_p), f"Processing: {m}")
            
            results = processor.process_image(
                filepath,
                selected_maps=data.get('maps'),
                params=data.get('params'),
                progress_callback=pbr_progress,
                output_dir=target_dir
            )
            
        # Update info.json with new maps
        if os.path.exists(info_path):
            with open(info_path, 'r+') as f:
                meta = json.load(f)
                meta['maps'] = results
                f.seek(0)
                json.dump(meta, f, indent=4)
                f.truncate()
            
        TASKS[task_id]['result'] = results
        TASKS[task_id]['status'] = 'completed'
        update_progress(task_id, 100, 'Reprocessing completed')
        
    except Exception as e:
        print(f"Reprocess Task Failed: {e}")
        TASKS[task_id]['status'] = 'failed'
        TASKS[task_id]['error'] = str(e)

@app.route('/api/scan', methods=['POST'])
def scan():
    """Quy trình 1-Click: Chụp -> Tải về -> Xử lý (Async)"""
    try:
        data = request.json
        
        task_id = str(uuid.uuid4())
        TASKS[task_id] = {
            'status': 'processing',
            'percent': 0,
            'message': 'Starting...',
            'created_at': time.time()
        }
        
        thread = threading.Thread(target=task_scan_process, args=(task_id, data))
        thread.start()
        
        return jsonify({'task_id': task_id})
    except Exception as e:
        print(f"Scan Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Lấy danh sách các file scan đã chụp (Gom nhóm theo vật liệu)"""
    history = []
    
    if os.path.exists(UPLOAD_FOLDER):
        # Get all subdirectories
        entries = [os.path.join(UPLOAD_FOLDER, d) for d in os.listdir(UPLOAD_FOLDER) if os.path.isdir(os.path.join(UPLOAD_FOLDER, d))]
        
        # Sort by modification time (newest first)
        entries.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        for entry_path in entries:
            folder_name = os.path.basename(entry_path)
            info_path = os.path.join(entry_path, "info.json")
            
            item = None
            
            if os.path.exists(info_path):
                try:
                    with open(info_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        
                        # Fix map paths to be web-accessible
                        maps = metadata.get("maps", {})
                        
                        item = {
                            "id": metadata.get("id", folder_name),
                            "name": metadata.get("name", folder_name),
                            "folder_name": folder_name,
                            "created_at": metadata.get("created_at", os.path.getctime(entry_path)),
                            "tags": metadata.get("tags", []),
                            "device": metadata.get("device", "unknown"),
                            "maps": maps
                        }
                except Exception as e:
                    print(f"Error reading info.json in {folder_name}: {e}")
            
            # Fallback for legacy folders (no info.json)
            if not item:
                 # Check if it looks like a scan folder (has images)
                 files = os.listdir(entry_path)
                 images = [f for f in files if f.lower().endswith(('.jpg', '.png'))]
                 if images:
                     # Try to find base color
                     base_color = next((f for f in images if "BaseColor" in f), None)
                     if not base_color:
                         base_color = images[0] if images else None
                         
                     if base_color:
                         item = {
                            "id": folder_name,
                            "name": folder_name,
                            "folder_name": folder_name,
                            "created_at": os.path.getctime(entry_path),
                            "tags": ["legacy"],
                            "device": "unknown",
                            "maps": {
                                "base_color": f"/scans/{folder_name}/{base_color}"
                            }
                         }

            if item:
                history.append(item)
                
    return jsonify(history)

@app.route('/api/reprocess', methods=['POST'])
def reprocess():
    """Tạo lại map cho ảnh cũ (Async)"""
    try:
        data = request.json
        
        task_id = str(uuid.uuid4())
        TASKS[task_id] = {
            'status': 'processing',
            'percent': 0,
            'message': 'Starting...',
            'created_at': time.time()
        }
        
        thread = threading.Thread(target=task_reprocess_process, args=(task_id, data))
        thread.start()
        
        return jsonify({'task_id': task_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export/u3m', methods=['POST'])
def export_u3m():
    """Xuất file U3M (Zip)"""
    try:
        data = request.json
        folder_name = data.get('folder_name')
        
        if not folder_name:
             # Backward compat
             filename = data.get('filename')
             if filename and '/' in filename:
                 folder_name = os.path.dirname(filename)
             elif filename:
                 folder_name = filename # Treat as folder
             else:
                 return jsonify({'success': False, 'error': 'No folder_name provided'}), 400

        target_dir = os.path.join(UPLOAD_FOLDER, folder_name)
        if not os.path.exists(target_dir):
            return jsonify({'success': False, 'error': 'Folder not found'}), 404
            
        # Get base name from info.json or folder name
        name_no_ext = folder_name
        info_path = os.path.join(target_dir, "info.json")
        if os.path.exists(info_path):
             with open(info_path, 'r') as f:
                 meta = json.load(f)
                 name_no_ext = meta.get('name', folder_name).replace(' ', '_')
        
        # Tạo thư mục temp để zip
        temp_dir = os.path.join(target_dir, 'temp_export')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Danh sách file cần zip
        files_to_zip = []
        
        # Scan dir for maps
        # We need to map our filenames to U3M standard roles
        files = os.listdir(target_dir)
        
        map_files = {}
        
        for f in files:
            lower = f.lower()
            if 'basecolor' in lower: map_files['diffuse'] = f
            elif 'normal' in lower: map_files['normal'] = f
            elif 'roughness' in lower: map_files['roughness'] = f
            elif 'displacement' in lower: map_files['height'] = f
            elif 'ao' in lower: map_files['ambientocclusion'] = f
            elif 'metallic' in lower: map_files['metallic'] = f
        
        for key, fname in map_files.items():
            files_to_zip.append(fname)

        # Tạo file JSON metadata .u3m
        u3m_data = {
            "name": name_no_ext,
            "version": "1.0",
            "maps": map_files
        }
        
        u3m_json_path = os.path.join(temp_dir, f"{name_no_ext}.u3m")
        with open(u3m_json_path, 'w') as f:
            json.dump(u3m_data, f, indent=4)
            
        # Zip tất cả lại
        zip_path = os.path.join(target_dir, f"{name_no_ext}_export.u3m")
        
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            zipf.write(u3m_json_path, arcname=f"{name_no_ext}.u3m")
            for f in files_to_zip:
                zipf.write(os.path.join(target_dir, f), arcname=f)
                
        # Dọn dẹp temp
        shutil.rmtree(temp_dir)
        
        return jsonify({
            'success': True,
            'download_url': f"/scans/{folder_name}/{os.path.basename(zip_path)}"
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete', methods=['POST'])
def delete_scan():
    """Xóa file scan và các map liên quan"""
    try:
        data = request.json
        folder_name = data.get('folder_name')
        
        if not folder_name:
             # Backward compat
             base_name = data.get('base_name')
             if base_name:
                 folder_name = base_name
             else:
                 return jsonify({'success': False, 'error': 'No folder_name provided'}), 400
            
        target_dir = os.path.join(UPLOAD_FOLDER, folder_name)
        
        if os.path.exists(target_dir) and os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
            return jsonify({'success': True, 'message': f'Deleted folder {folder_name}'})
        else:
            return jsonify({'success': False, 'error': 'Folder not found'}), 404
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/scans/<path:filename>')
def serve_scan_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    webbrowser.open('http://127.0.0.1:5000')
    app.run(debug=True, port=5000, use_reloader=False)
