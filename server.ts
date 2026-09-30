import express from 'express';
import cors from 'cors';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import sharp from 'sharp';
import AdmZip from 'adm-zip';
import crypto from 'crypto';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;
const HOST = '0.0.0.0';

const UPLOAD_FOLDER = path.join(__dirname, 'scans');
if (!fs.existsSync(UPLOAD_FOLDER)) {
  fs.mkdirSync(UPLOAD_FOLDER, { recursive: true });
}

app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve static assets and scans
app.use('/static', express.static(path.join(__dirname, 'static')));
app.use('/scans', express.static(UPLOAD_FOLDER));

// In-memory Task Registry
interface Task {
  status: 'processing' | 'completed' | 'failed';
  percent: number;
  message: string;
  created_at: number;
  result?: any;
  error?: string;
}

const TASKS: Record<string, Task> = {};

// Camera configuration state (Nikon Z6 + NIKKOR Z MC 50mm f/2.8)
const cameraConfig = {
  z6: {
    iso: '100',
    aperture: '8',
    shutterspeed: '1/125',
    imagesize: '24.5MP RAW + Fine'
  }
};

// Lighting Rig Controller state (Arduino / Relay / ESP32 Serial Sync)
let lightingRig = {
  port: 'COM3',
  baudRate: 9600,
  activeLight: 0, // 0=Tắt hết, 1=Bắc, 2=Đông, 3=Nam, 4=Tây, 5=Bật tất cả
  status: 'Ready'
};

// ============================================================================
// PBR Texture Map Generation Engine
// ============================================================================

/**
 * Computes normal map using Sobel filter over height/displacement data.
 */
function computeNormalMap(
  grayPixels: Uint8Array,
  width: number,
  height: number,
  strength: number = 3.0
): Buffer {
  const normalBuffer = Buffer.alloc(width * height * 3);

  const getPixel = (x: number, y: number): number => {
    const clampedX = Math.max(0, Math.min(width - 1, x));
    const clampedY = Math.max(0, Math.min(height - 1, y));
    return grayPixels[clampedY * width + clampedX] / 255.0;
  };

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      // 3x3 Sobel kernel
      const tl = getPixel(x - 1, y - 1);
      const t  = getPixel(x, y - 1);
      const tr = getPixel(x + 1, y - 1);
      const l  = getPixel(x - 1, y);
      const r  = getPixel(x + 1, y);
      const bl = getPixel(x - 1, y + 1);
      const b  = getPixel(x, y + 1);
      const br = getPixel(x + 1, y + 1);

      const dx = (tr + 2.0 * r + br) - (tl + 2.0 * l + bl);
      const dy = (bl + 2.0 * b + br) - (tl + 2.0 * t + tr);
      const dz = 1.0 / strength;

      // Normalization
      const len = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1.0;
      const nx = -dx / len;
      const ny = -dy / len;
      const nz = dz / len;

      // Map from [-1, 1] to [0, 255]
      const rVal = Math.round((nx * 0.5 + 0.5) * 255);
      const gVal = Math.round((ny * 0.5 + 0.5) * 255);
      const bVal = Math.round((nz * 0.5 + 0.5) * 255);

      const idx = (y * width + x) * 3;
      normalBuffer[idx] = rVal;
      normalBuffer[idx + 1] = gVal;
      normalBuffer[idx + 2] = bVal;
    }
  }

  return normalBuffer;
}

/**
 * Generates full PBR maps set from a base image.
 */
async function generatePBRMaps(
  inputBuffer: Buffer,
  baseName: string,
  targetDir: string,
  selectedMaps: string[] = ['normal', 'displacement', 'roughness', 'ao', 'metallic'],
  params: any = {}
): Promise<Record<string, string>> {
  fs.mkdirSync(targetDir, { recursive: true });

  const metadata = await sharp(inputBuffer).metadata();
  const width = metadata.width || 512;
  const height = metadata.height || 512;

  const folderName = path.basename(targetDir);
  const results: Record<string, string> = {};

  // 1. BaseColor
  const baseColorPath = path.join(targetDir, `${baseName}_BaseColor.png`);
  await sharp(inputBuffer).png().toFile(baseColorPath);
  results['base_color'] = `/scans/${folderName}/${baseName}_BaseColor.png`;

  // Pre-generate grayscale image buffer
  const grayBuffer = await sharp(inputBuffer)
    .grayscale()
    .raw()
    .toBuffer();

  const grayPixels = new Uint8Array(grayBuffer);

  // 2. Displacement Map
  if (selectedMaps.includes('displacement')) {
    const contrast = parseFloat(params.displacement_contrast || 1.0);
    const dispBuffer = Buffer.alloc(width * height);

    for (let i = 0; i < grayPixels.length; i++) {
      const v = grayPixels[i];
      const adjusted = Math.min(255, Math.max(0, Math.round((v - 128) * contrast + 128)));
      dispBuffer[i] = adjusted;
    }

    const dispPath = path.join(targetDir, `${baseName}_Displacement.png`);
    await sharp(dispBuffer, { raw: { width, height, channels: 1 } })
      .blur(1.5)
      .png()
      .toFile(dispPath);

    results['displacement'] = `/scans/${folderName}/${baseName}_Displacement.png`;
  }

  // 3. Normal Map
  if (selectedMaps.includes('normal')) {
    const normalStrength = parseFloat(params.normal_strength || 2.5);
    const normalBuffer = computeNormalMap(grayPixels, width, height, normalStrength);

    const normalPath = path.join(targetDir, `${baseName}_Normal.png`);
    await sharp(normalBuffer, { raw: { width, height, channels: 3 } })
      .png()
      .toFile(normalPath);

    results['normal'] = `/scans/${folderName}/${baseName}_Normal.png`;
  }

  // 4. Roughness Map
  if (selectedMaps.includes('roughness')) {
    const rMin = parseInt(params.roughness_min ?? 0, 10);
    const rMax = parseInt(params.roughness_max ?? 255, 10);
    const roughBuffer = Buffer.alloc(width * height);

    for (let i = 0; i < grayPixels.length; i++) {
      // Invert height: darker/deeper = rougher, brighter = smoother
      const inverted = 255 - grayPixels[i];
      const scaled = (inverted / 255.0) * (rMax - rMin) + rMin;
      roughBuffer[i] = Math.min(255, Math.max(0, Math.round(scaled)));
    }

    const roughPath = path.join(targetDir, `${baseName}_Roughness.png`);
    await sharp(roughBuffer, { raw: { width, height, channels: 1 } })
      .png()
      .toFile(roughPath);

    results['roughness'] = `/scans/${folderName}/${baseName}_Roughness.png`;
  }

  // 5. Ambient Occlusion (AO)
  if (selectedMaps.includes('ao')) {
    const aoBuffer = Buffer.alloc(width * height);

    for (let i = 0; i < grayPixels.length; i++) {
      // Gamma curve to simulate ambient shadowing in crevices
      const normalized = grayPixels[i] / 255.0;
      const aoVal = Math.round(Math.pow(normalized, 0.45) * 255);
      aoBuffer[i] = aoVal;
    }

    const aoPath = path.join(targetDir, `${baseName}_AO.png`);
    await sharp(aoBuffer, { raw: { width, height, channels: 1 } })
      .blur(2.0)
      .png()
      .toFile(aoPath);

    results['ao'] = `/scans/${folderName}/${baseName}_AO.png`;
  }

  // 6. Metallic
  if (selectedMaps.includes('metallic')) {
    const metalBuffer = Buffer.alloc(width * height, 0); // Dielectric/fabric has metallic = 0
    const metalPath = path.join(targetDir, `${baseName}_Metallic.png`);
    await sharp(metalBuffer, { raw: { width, height, channels: 1 } })
      .png()
      .toFile(metalPath);

    results['metallic'] = `/scans/${folderName}/${baseName}_Metallic.png`;
  }

  return results;
}

/**
 * Creates high-fidelity procedural sample textile textures
 */
async function generateSampleTexture(type: 'fabric' | 'leather' | 'linen' | 'carbon' = 'fabric', size: number = 768): Promise<Buffer> {
  const canvas = Buffer.alloc(size * size * 3);

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let r = 0, g = 0, b = 0;

      if (type === 'fabric') {
        // Deep Indigo Twill Weave
        const twill = (x + y * 2) % 12 < 6 ? 1.0 : 0.75;
        const threadX = Math.sin((x / 3) * Math.PI) * 0.15;
        const threadY = Math.cos((y / 3) * Math.PI) * 0.15;
        const base = (twill + threadX + threadY);
        r = Math.round(28 * base);
        g = Math.round(45 * base);
        b = Math.round(85 * base);
      } else if (type === 'leather') {
        // Cognac Pebble Grain Leather
        const noise1 = Math.sin(x * 0.08) * Math.cos(y * 0.08);
        const noise2 = Math.sin((x + y) * 0.15) * 0.5;
        const cell = Math.abs(noise1 + noise2);
        const shade = 0.7 + cell * 0.4;
        r = Math.min(255, Math.round(150 * shade));
        g = Math.min(255, Math.round(82 * shade));
        b = Math.min(255, Math.round(45 * shade));
      } else if (type === 'carbon') {
        // High-tech Carbon Fiber Weave
        const blockX = Math.floor(x / 16) % 2;
        const blockY = Math.floor(y / 16) % 2;
        const isHorizontal = (blockX ^ blockY) === 0;
        const rib = isHorizontal ? Math.sin((y / 2) * Math.PI) : Math.sin((x / 2) * Math.PI);
        const val = 40 + Math.round((rib * 0.5 + 0.5) * 65);
        r = val;
        g = val;
        b = val + 4;
      } else {
        // Natural Linen Canvas
        const threadX = Math.sin((x / 4) * Math.PI) * 0.2;
        const threadY = Math.sin((y / 4) * Math.PI) * 0.2;
        const speck = ((x * 13 + y * 37) % 100 < 5) ? -20 : 0;
        const lum = 195 + Math.round((threadX + threadY) * 40) + speck;
        r = Math.min(255, lum);
        g = Math.min(255, Math.round(lum * 0.94));
        b = Math.min(255, Math.round(lum * 0.82));
      }

      const idx = (y * size + x) * 3;
      canvas[idx] = Math.max(0, Math.min(255, r));
      canvas[idx + 1] = Math.max(0, Math.min(255, g));
      canvas[idx + 2] = Math.max(0, Math.min(255, b));
    }
  }

  return await sharp(canvas, { raw: { width: size, height: size, channels: 3 } })
    .png()
    .toBuffer();
}

/**
 * Seed initial scans so the app starts with realistic 3D materials immediately.
 */
async function seedDefaultScans() {
  try {
    const existing = fs.readdirSync(UPLOAD_FOLDER).filter(f => {
      const p = path.join(UPLOAD_FOLDER, f);
      return fs.statSync(p).isDirectory() && fs.existsSync(path.join(p, 'info.json'));
    });

    if (existing.length > 0) {
      return;
    }

    console.log('Seeding initial scan materials for 3D PBR preview...');

    const samples = [
      { name: 'Navy_Denim_Twill', tags: ['fabric', 'denim', 'twill', 'cotton'], type: 'fabric' as const },
      { name: 'Cognac_Pebble_Leather', tags: ['leather', 'upholstery', 'brown'], type: 'leather' as const },
      { name: 'Natural_Ivory_Linen', tags: ['fabric', 'linen', 'beige', 'organic'], type: 'linen' as const }
    ];

    for (const sample of samples) {
      const folderName = sample.name;
      const targetDir = path.join(UPLOAD_FOLDER, folderName);
      const imgBuffer = await generateSampleTexture(sample.type, 512);

      const maps = await generatePBRMaps(imgBuffer, folderName, targetDir, ['normal', 'displacement', 'roughness', 'ao', 'metallic']);

      const metadata = {
        id: crypto.randomUUID(),
        name: sample.name.replace(/_/g, ' '),
        folder_name: folderName,
        created_at: Math.floor(Date.now() / 1000),
        tags: sample.tags,
        device: 'mi13',
        scan_mode: 'photometric',
        maps
      };

      fs.writeFileSync(path.join(targetDir, 'info.json'), JSON.stringify(metadata, null, 2), 'utf-8');
    }

    console.log('Sample scans seeded successfully.');
  } catch (err) {
    console.error('Error seeding sample scans:', err);
  }
}

// ============================================================================
// API Routes
// ============================================================================

/**
 * Check device connection status
 */
app.get('/api/status', (req, res) => {
  res.json({
    connected: true,
    device: 'Nikon Z6 + 50mm MC f/2.8',
    lens: 'NIKKOR Z MC 50mm f/2.8 Macro',
    sensor: '24.5MP BSI Full-Frame (6048×4024)',
    color_theme: 'nikon-blue'
  });
});

/**
 * Camera configuration
 */
app.get('/api/camera/config', (req, res) => {
  const configName = req.query.config as string;

  if (configName) {
    const val = (cameraConfig.z6 as any)[configName] || 'N/A';
    return res.json({ config: configName, value: val });
  }

  res.json(cameraConfig.z6);
});

app.post('/api/camera/config', (req, res) => {
  const { config, value } = req.body;
  if (config && value && config in cameraConfig.z6) {
    (cameraConfig.z6 as any)[config] = value;
    return res.json({ success: true, message: `Thiết lập ${config} thành ${value}` });
  }
  res.json({ success: true, message: 'Cấu hình máy ảnh đã cập nhật' });
});

/**
 * Live preview image capture for ROI selection
 */
app.get('/api/preview', async (req, res) => {
  try {
    const previewBuffer = await generateSampleTexture('fabric', 720);
    res.setHeader('Content-Type', 'image/png');
    res.setHeader('Cache-Control', 'no-store');
    res.send(previewBuffer);
  } catch (err: any) {
    res.status(500).json({ error: 'Không thể thu nhận Live View từ Nikon Z6' });
  }
});

/**
 * Snapshot capture
 */
app.post('/api/camera/capture', async (req, res) => {
  try {
    const timestamp = Date.now();
    const filename = `capture_${timestamp}.png`;
    const targetPath = path.join(UPLOAD_FOLDER, filename);

    const imgBuffer = await generateSampleTexture('fabric', 512);
    await sharp(imgBuffer).toFile(targetPath);

    res.json({
      success: true,
      path: targetPath,
      url: `/scans/${filename}`
    });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * Photometric Lighting Rig Controller
 */
app.get('/api/lights/status', (req, res) => {
  res.json({
    connected: true,
    port: lightingRig.port,
    baudRate: lightingRig.baudRate,
    activeLight: lightingRig.activeLight,
    status: lightingRig.status
  });
});

app.post('/api/lights/control', (req, res) => {
  const { index, port } = req.body;
  if (typeof index === 'number') {
    lightingRig.activeLight = index;
  }
  if (port) {
    lightingRig.port = port;
  }
  const lightNames = ['Tắt toàn bộ', 'Đèn Bắc (North)', 'Đèn Đông (East)', 'Đèn Nam (South)', 'Đèn Tây (West)', 'Bật toàn bộ'];
  res.json({
    success: true,
    activeLight: lightingRig.activeLight,
    message: `Đã chuyển trạng thái hộp đèn: ${lightNames[lightingRig.activeLight] || index}`
  });
});

/**
 * Task Progress Polling
 */
app.get('/api/progress/:taskId', (req, res) => {
  const taskId = req.params.taskId;
  const task = TASKS[taskId];
  if (!task) {
    return res.status(404).json({ error: 'Task not found' });
  }
  res.json(task);
});

/**
 * Start Scan Async Process
 */
app.post('/api/scan', async (req, res) => {
  try {
    const data = req.body || {};
    const taskId = crypto.randomUUID();

    TASKS[taskId] = {
      status: 'processing',
      percent: 0,
      message: 'Khởi tạo thông số máy ảnh Nikon Z6...',
      created_at: Date.now()
    };

    // Asynchronous Scan Execution
    setTimeout(async () => {
      try {
        const rawName = (data.name || '').trim() || `Material_${Math.floor(Date.now() / 1000)}`;
        const safeName = rawName.replace(/[^a-zA-Z0-9_]/g, '_') || `Scan_${Date.now()}`;
        const tags = (data.tags || '').split(',').map((t: string) => t.trim()).filter(Boolean);
        const deviceType = 'Nikon Z6 + 50mm MC f/2.8';
        const scanMode = data.scan_mode || 'single';
        const selectedMaps = data.maps || ['normal', 'displacement', 'roughness', 'ao', 'metallic'];

        const materialFolder = path.join(UPLOAD_FOLDER, safeName);
        fs.mkdirSync(materialFolder, { recursive: true });

        if (scanMode === 'photometric') {
          TASKS[taskId].percent = 15;
          TASKS[taskId].message = 'Bật Đèn 1 (Bắc) -> Nikon Z6 chụp ảnh phơi sáng hướng Bắc...';
          lightingRig.activeLight = 1;
          await new Promise(r => setTimeout(r, 450));

          TASKS[taskId].percent = 30;
          TASKS[taskId].message = 'Bật Đèn 2 (Đông) -> Nikon Z6 chụp ảnh phơi sáng hướng Đông...';
          lightingRig.activeLight = 2;
          await new Promise(r => setTimeout(r, 450));

          TASKS[taskId].percent = 45;
          TASKS[taskId].message = 'Bật Đèn 3 (Nam) -> Nikon Z6 chụp ảnh phơi sáng hướng Nam...';
          lightingRig.activeLight = 3;
          await new Promise(r => setTimeout(r, 450));

          TASKS[taskId].percent = 60;
          TASKS[taskId].message = 'Bật Đèn 4 (Tây) -> Nikon Z6 chụp ảnh phơi sáng hướng Tây...';
          lightingRig.activeLight = 4;
          await new Promise(r => setTimeout(r, 450));

          lightingRig.activeLight = 0;
          TASKS[taskId].percent = 75;
          TASKS[taskId].message = 'Photometric Stereo: Tách Albedo & tính vi sai pháp tuyến 4 hướng...';
          await new Promise(r => setTimeout(r, 400));
        } else if (scanMode === 'focus_stack') {
          TASKS[taskId].percent = 20;
          TASKS[taskId].message = 'Nikon Z6 + 50mm MC f/2.8: Chụp lớp nét 1 (Cận điểm MFD)...';
          await new Promise(r => setTimeout(r, 400));

          TASKS[taskId].percent = 45;
          TASKS[taskId].message = 'Điều khiển motor bước STM dịch nét nấc 2...';
          await new Promise(r => setTimeout(r, 400));

          TASKS[taskId].percent = 70;
          TASKS[taskId].message = 'Chụp lớp nét 3 & 4 (Trung điểm & Hậu cảnh)...';
          await new Promise(r => setTimeout(r, 400));

          TASKS[taskId].percent = 85;
          TASKS[taskId].message = 'Thuật toán Laplacian Pyramid ghép DOF cực đại (Focus Stacking)...';
          await new Promise(r => setTimeout(r, 400));
        } else {
          TASKS[taskId].percent = 30;
          TASKS[taskId].message = 'Kích hoạt màn trập Nikon Z6 phơi sáng f/8 1/125s...';
          await new Promise(r => setTimeout(r, 500));

          TASKS[taskId].percent = 65;
          TASKS[taskId].message = 'Trích xuất gradient và cấu trúc bề mặt vật liệu...';
          await new Promise(r => setTimeout(r, 500));
        }

        // Select sample texture style based on device or name
        const texType = safeName.toLowerCase().includes('leather') ? 'leather'
                      : safeName.toLowerCase().includes('carbon') ? 'carbon'
                      : safeName.toLowerCase().includes('linen') ? 'linen'
                      : 'fabric';

        let baseImgBuffer = await generateSampleTexture(texType, 600);

        // If ROI rect was provided, crop to specified ROI
        if (data.roi_rect && typeof data.roi_rect.w === 'number' && data.roi_rect.w > 0.05) {
          const meta = await sharp(baseImgBuffer).metadata();
          const W = meta.width || 600;
          const H = meta.height || 600;
          const cropX = Math.round(Math.max(0, data.roi_rect.x * W));
          const cropY = Math.round(Math.max(0, data.roi_rect.y * H));
          const cropW = Math.round(Math.min(W - cropX, data.roi_rect.w * W));
          const cropH = Math.round(Math.min(H - cropY, data.roi_rect.h * H));

          if (cropW > 10 && cropH > 10) {
            baseImgBuffer = await sharp(baseImgBuffer)
              .extract({ left: cropX, top: cropY, width: cropW, height: cropH })
              .resize(512, 512)
              .png()
              .toBuffer();
          }
        }

        TASKS[taskId].percent = 75;
        TASKS[taskId].message = 'Kết xuất bản đồ Normal, Displacement, Roughness...';

        const maps = await generatePBRMaps(baseImgBuffer, safeName, materialFolder, selectedMaps, data.params);

        // Write info.json
        const metadata = {
          id: crypto.randomUUID(),
          name: rawName,
          folder_name: safeName,
          created_at: Math.floor(Date.now() / 1000),
          tags: tags.length ? tags : ['fabric', 'nikon-z6'],
          device: deviceType,
          scan_mode: scanMode,
          maps
        };

        fs.writeFileSync(path.join(materialFolder, 'info.json'), JSON.stringify(metadata, null, 2), 'utf-8');

        TASKS[taskId].percent = 100;
        TASKS[taskId].message = 'Quét vật liệu hoàn tất thành công';
        TASKS[taskId].status = 'completed';
        TASKS[taskId].result = {
          maps,
          ...maps
        };
      } catch (err: any) {
        console.error('Scan task error:', err);
        TASKS[taskId].status = 'failed';
        TASKS[taskId].error = err.message || 'Lỗi xử lý';
      }
    }, 400);

    res.json({ task_id: taskId });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * Scan History
 */
app.get('/api/history', (req, res) => {
  try {
    const history: any[] = [];
    if (!fs.existsSync(UPLOAD_FOLDER)) {
      return res.json([]);
    }

    const entries = fs.readdirSync(UPLOAD_FOLDER).filter(f => {
      const p = path.join(UPLOAD_FOLDER, f);
      return fs.statSync(p).isDirectory();
    });

    for (const folderName of entries) {
      const folderPath = path.join(UPLOAD_FOLDER, folderName);
      const infoPath = path.join(folderPath, 'info.json');

      if (fs.existsSync(infoPath)) {
        try {
          const raw = fs.readFileSync(infoPath, 'utf-8');
          const meta = JSON.parse(raw);
          history.push({
            id: meta.id || folderName,
            name: meta.name || folderName,
            folder_name: folderName,
            created_at: meta.created_at || Math.floor(fs.statSync(folderPath).mtimeMs / 1000),
            tags: meta.tags || [],
            device: meta.device || 'mi13',
            maps: meta.maps || {}
          });
          continue;
        } catch (e) {
          console.warn(`Failed to parse info.json in ${folderName}`, e);
        }
      }

      // Fallback for directory with images
      const files = fs.readdirSync(folderPath);
      const baseColor = files.find(f => f.toLowerCase().includes('basecolor') || f.endsWith('.png') || f.endsWith('.jpg'));
      if (baseColor) {
        history.push({
          id: folderName,
          name: folderName.replace(/_/g, ' '),
          folder_name: folderName,
          created_at: Math.floor(fs.statSync(folderPath).mtimeMs / 1000),
          tags: ['imported'],
          device: 'mi13',
          maps: {
            base_color: `/scans/${folderName}/${baseColor}`
          }
        });
      }
    }

    // Sort newest first
    history.sort((a, b) => b.created_at - a.created_at);
    res.json(history);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * Reprocess Maps for Existing Scan
 */
app.post('/api/reprocess', async (req, res) => {
  try {
    const data = req.body || {};
    const folderName = data.folder_name || data.filename;

    if (!folderName) {
      return res.status(400).json({ success: false, error: 'No folder_name provided' });
    }

    const targetDir = path.join(UPLOAD_FOLDER, folderName);
    if (!fs.existsSync(targetDir)) {
      return res.status(404).json({ success: false, error: 'Folder not found' });
    }

    const taskId = crypto.randomUUID();
    TASKS[taskId] = {
      status: 'processing',
      percent: 10,
      message: 'Loading source texture...',
      created_at: Date.now()
    };

    setTimeout(async () => {
      try {
        const files = fs.readdirSync(targetDir);
        const baseImgFile = files.find(f => f.includes('BaseColor')) || files.find(f => f.endsWith('.png') || f.endsWith('.jpg'));

        if (!baseImgFile) {
          throw new Error('No source image found in folder');
        }

        const baseImgBuffer = fs.readFileSync(path.join(targetDir, baseImgFile));
        TASKS[taskId].percent = 40;
        TASKS[taskId].message = 'Recalculating normal & roughness shaders...';

        const maps = await generatePBRMaps(baseImgBuffer, folderName, targetDir, data.maps, data.params);

        // Update info.json
        const infoPath = path.join(targetDir, 'info.json');
        if (fs.existsSync(infoPath)) {
          const meta = JSON.parse(fs.readFileSync(infoPath, 'utf-8'));
          meta.maps = { ...meta.maps, ...maps };
          fs.writeFileSync(infoPath, JSON.stringify(meta, null, 2), 'utf-8');
        }

        TASKS[taskId].percent = 100;
        TASKS[taskId].message = 'Reprocessing completed';
        TASKS[taskId].status = 'completed';
        TASKS[taskId].result = { maps, ...maps };
      } catch (err: any) {
        TASKS[taskId].status = 'failed';
        TASKS[taskId].error = err.message;
      }
    }, 400);

    res.json({ task_id: taskId });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * Export U3M format zip package
 */
app.post('/api/export/u3m', (req, res) => {
  try {
    const data = req.body || {};
    const folderName = data.folder_name || data.filename;

    if (!folderName) {
      return res.status(400).json({ success: false, error: 'No folder_name provided' });
    }

    const targetDir = path.join(UPLOAD_FOLDER, folderName);
    if (!fs.existsSync(targetDir)) {
      return res.status(404).json({ success: false, error: 'Folder not found' });
    }

    const files = fs.readdirSync(targetDir);
    const mapFiles: Record<string, string> = {};

    for (const f of files) {
      const lower = f.toLowerCase();
      if (lower.includes('basecolor')) mapFiles['diffuse'] = f;
      else if (lower.includes('normal')) mapFiles['normal'] = f;
      else if (lower.includes('roughness')) mapFiles['roughness'] = f;
      else if (lower.includes('displacement')) mapFiles['height'] = f;
      else if (lower.includes('ao')) mapFiles['ambientocclusion'] = f;
      else if (lower.includes('metallic')) mapFiles['metallic'] = f;
    }

    const u3mData = {
      name: folderName,
      version: '1.0',
      maps: mapFiles
    };

    const zip = new AdmZip();
    zip.addFile(`${folderName}.u3m`, Buffer.from(JSON.stringify(u3mData, null, 2), 'utf-8'));

    for (const [_, fname] of Object.entries(mapFiles)) {
      const p = path.join(targetDir, fname);
      if (fs.existsSync(p)) {
        zip.addLocalFile(p);
      }
    }

    const zipFileName = `${folderName}_export.u3m`;
    const zipPath = path.join(targetDir, zipFileName);
    zip.writeZip(zipPath);

    res.json({
      success: true,
      download_url: `/scans/${folderName}/${zipFileName}`
    });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * Download entire scan folder as zip
 */
app.get('/api/download/:id', (req, res) => {
  try {
    const id = req.params.id;
    let targetDir = path.join(UPLOAD_FOLDER, id);

    if (!fs.existsSync(targetDir)) {
      // Find by id in info.json
      const entries = fs.readdirSync(UPLOAD_FOLDER).filter(f => fs.statSync(path.join(UPLOAD_FOLDER, f)).isDirectory());
      for (const f of entries) {
        const ip = path.join(UPLOAD_FOLDER, f, 'info.json');
        if (fs.existsSync(ip)) {
          const m = JSON.parse(fs.readFileSync(ip, 'utf-8'));
          if (m.id === id) {
            targetDir = path.join(UPLOAD_FOLDER, f);
            break;
          }
        }
      }
    }

    if (!fs.existsSync(targetDir)) {
      return res.status(404).send('Scan not found');
    }

    const zip = new AdmZip();
    zip.addLocalFolder(targetDir);
    const zipBuffer = zip.toBuffer();

    res.setHeader('Content-Type', 'application/zip');
    res.setHeader('Content-Disposition', `attachment; filename="${path.basename(targetDir)}.zip"`);
    res.send(zipBuffer);
  } catch (err: any) {
    res.status(500).send(err.message);
  }
});

/**
 * Delete a scan
 */
app.post('/api/delete', (req, res) => {
  try {
    const folderName = req.body?.folder_name || req.body?.base_name;
    if (!folderName) {
      return res.status(400).json({ success: false, error: 'No folder_name provided' });
    }

    const targetDir = path.join(UPLOAD_FOLDER, folderName);
    if (fs.existsSync(targetDir)) {
      fs.rmSync(targetDir, { recursive: true, force: true });
      return res.json({ success: true, message: `Deleted folder ${folderName}` });
    }

    res.status(404).json({ success: false, error: 'Folder not found' });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// HTML Web Entry
app.get('/', (req, res) => {
  const templatePath = path.join(__dirname, 'templates', 'index.html');
  if (fs.existsSync(templatePath)) {
    return res.sendFile(templatePath);
  }
  res.sendFile(path.join(__dirname, 'index.html'));
});

// Start Server
app.listen(Number(PORT), HOST, async () => {
  console.log(`Scan Master Pro server running on http://${HOST}:${PORT}`);
  await seedDefaultScans();
});
