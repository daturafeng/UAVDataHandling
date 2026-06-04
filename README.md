# UAVDataHandling

[中文](#中文) | [English](#english)

---

## 中文

无人机图像坐标解算项目。

当前阶段的核心目标是：

- 读取单张无人机图片中的元数据
- 支持外部参数覆盖图像元数据
- 输入像素坐标 `(u, v)`
- 输出对应目标点的 `WGS84` 经纬度
- 支持平地模型和 `DEM` 地形模型两种求交方式
- 提供最小可验证的 `Python API`、`CLI` 和本地网页端

### 当前能力

- DJI 图片 `EXIF / XMP` 元数据读取
- 像素点、线、面批量地理解算
- 平地假设下的射线与地面求交
- 基于 `GeoTIFF DEM` 的射线与地形求交
- 本地网页端图片标注与地图定位
- CLI 单点与标注解算
- 单元测试与真实样例测试

### 目录结构

- `src/uav_geo/`：核心代码
- `src/uav_geo/readers/`：元数据读取
- `src/uav_geo/terrain.py`：DEM 地形采样与求交
- `tests/`：单元测试和样例测试
- `docs/`：算法与模型说明
- `web/`：本地网页端

### 环境依赖

建议使用 `Python 3.11+`。

安装依赖：

```powershell
pip install -r requirements.txt
```

主要依赖：

- `numpy`
- `Pillow`
- `pyproj`
- `rasterio`
- `pytest`

### 数据目录

- 图片样例目录：`G:\DJIImage\drone_images`
- DEM 根目录：`G:\GIS\Data\Dem\重庆市\不统计`

网页端会从 DEM 根目录递归扫描 `*.tif / *.tiff`，并在下拉框中供用户选择。

### 启动网页端

```powershell
python UAVDataHandling.py serve
```

默认参数：

- 图片根目录：`G:\DJIImage\drone_images`
- DEM 根目录：`G:\GIS\Data\Dem\重庆市\不统计`
- 默认 DEM：`G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif`
- 服务地址：`http://127.0.0.1:8765`

自定义目录示例：

```powershell
python UAVDataHandling.py serve `
  --sample-root "G:\DJIImage\drone_images" `
  --dem-root "G:\GIS\Data\Dem\重庆市\不统计" `
  --dem-path "G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif"
```

### 网页端使用方式

1. 从图片下拉框选择图片。
2. 从 DEM 下拉框选择地形文件，或选择“不使用 DEM（平地假设）”。
3. 点击“加载图片”。
4. 在图片上绘制点、线、面。
5. 结果会自动解算并显示在左侧地图上。

说明：

- 切换 DEM 后，已绘制标注会自动重新解算。
- 如果图片区域超出所选 DEM 覆盖范围，页面会显示明确错误。

### CLI 用法

单点解算：

```powershell
python UAVDataHandling.py point `
  "G:\DJIImage\drone_images\example.jpeg" `
  2016 1512
```

使用 DEM 进行单点解算：

```powershell
python UAVDataHandling.py point `
  "G:\DJIImage\drone_images\example.jpeg" `
  2016 1512 `
  --dem-path "G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif"
```

标注批量解算：

```powershell
python UAVDataHandling.py batch `
  "G:\DJIImage\drone_images\example.jpeg" `
  --annotation-file ".\temp_annotation.json"
```

### Python API 示例

```python
from uav_geo.models import ImagePoint, TerrainOptions
from uav_geo.service import solve_image_point

result = solve_image_point(
    image_path=r"G:\DJIImage\drone_images\example.jpeg",
    point=ImagePoint(u=2016, v=1512),
    terrain_options=TerrainOptions(
        dem_path=r"G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif"
    ),
)

print(result.to_dict())
```

### 坐标与单位约定

- 地理坐标：`WGS84`
- 经纬度单位：十进制度数
- 局部坐标：`ENU`
- 距离单位：米
- 像素坐标原点：左上角
- `u` 向右增大
- `v` 向下增大

当前姿态角约定：

- `yaw` 以正北为 `0`
- `yaw` 顺时针为正
- `pitch` 向下为负

### DEM 求交说明

DEM 模式下的求交链路：

1. 像素点转相机射线
2. 相机射线转世界 `ENU` 射线
3. 沿射线按固定步长推进
4. 将每个采样点转换为 `WGS84`
5. 在 `DEM` 上做双线性插值采样
6. 用二分逼近求出射线与地形表面的交点

详细说明见 `docs/dem-terrain-model.md`。

### 测试

运行全部测试：

```powershell
pytest -q
```

### 当前边界

- 当前默认仍基于针孔相机模型
- 尚未引入镜头畸变校正
- 尚未接入 `DSM / 正射 / 多视重建`
- 如果无人机绝对高度与 DEM 高程基准不一致，仍可能出现系统性偏差
- 如果姿态角语义与机型字段定义不一致，也会造成落点偏差

---

## English

UAV image geolocation project.

The current phase focuses on:

- Reading metadata from a single UAV image
- Allowing external overrides for image metadata
- Taking a pixel coordinate `(u, v)` as input
- Returning the target location in `WGS84`
- Supporting both a flat-ground model and a `DEM` terrain model
- Providing a minimal but verifiable `Python API`, `CLI`, and local web UI

### Features

- DJI `EXIF / XMP` metadata extraction
- Batch geolocation for points, polylines, and polygons
- Ray-to-ground intersection under a flat-ground assumption
- Ray-to-terrain intersection using `GeoTIFF DEM`
- Local web UI for image annotation and map display
- CLI for single-point and annotation solving
- Unit tests and real-sample integration tests

### Project Structure

- `src/uav_geo/`: core code
- `src/uav_geo/readers/`: metadata readers
- `src/uav_geo/terrain.py`: DEM sampling and terrain intersection
- `tests/`: unit and integration tests
- `docs/`: algorithm and model documentation
- `web/`: local web UI

### Requirements

Recommended Python version: `Python 3.11+`

Install dependencies:

```powershell
pip install -r requirements.txt
```

Main dependencies:

- `numpy`
- `Pillow`
- `pyproj`
- `rasterio`
- `pytest`

### Data Directories

- Sample image root: `G:\DJIImage\drone_images`
- DEM root: `G:\GIS\Data\Dem\重庆市\不统计`

The web UI recursively scans the DEM root for `*.tif / *.tiff` files and exposes them in a dropdown list.

### Start the Web UI

```powershell
python UAVDataHandling.py serve
```

Default values:

- Sample image root: `G:\DJIImage\drone_images`
- DEM root: `G:\GIS\Data\Dem\重庆市\不统计`
- Default DEM: `G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif`
- Server URL: `http://127.0.0.1:8765`

Custom example:

```powershell
python UAVDataHandling.py serve `
  --sample-root "G:\DJIImage\drone_images" `
  --dem-root "G:\GIS\Data\Dem\重庆市\不统计" `
  --dem-path "G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif"
```

### Web UI Usage

1. Choose an image from the image dropdown.
2. Choose a DEM from the terrain dropdown, or select flat-ground mode.
3. Click `加载图片`.
4. Draw points, polylines, or polygons on the image.
5. The results are solved automatically and shown on the map.

Notes:

- Existing annotations are recomputed automatically when the DEM changes.
- If the image area falls outside the selected DEM coverage, the UI shows a clear error message.

### CLI Usage

Single point:

```powershell
python UAVDataHandling.py point `
  "G:\DJIImage\drone_images\example.jpeg" `
  2016 1512
```

Single point with DEM:

```powershell
python UAVDataHandling.py point `
  "G:\DJIImage\drone_images\example.jpeg" `
  2016 1512 `
  --dem-path "G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif"
```

Batch annotation solving:

```powershell
python UAVDataHandling.py batch `
  "G:\DJIImage\drone_images\example.jpeg" `
  --annotation-file ".\temp_annotation.json"
```

### Python API Example

```python
from uav_geo.models import ImagePoint, TerrainOptions
from uav_geo.service import solve_image_point

result = solve_image_point(
    image_path=r"G:\DJIImage\drone_images\example.jpeg",
    point=ImagePoint(u=2016, v=1512),
    terrain_options=TerrainOptions(
        dem_path=r"G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif"
    ),
)

print(result.to_dict())
```

### Coordinate and Unit Conventions

- Geographic CRS: `WGS84`
- Longitude/latitude unit: decimal degrees
- Local frame: `ENU`
- Distance unit: meters
- Pixel origin: image top-left
- `u` increases to the right
- `v` increases downward

Current attitude convention:

- `yaw = 0` points to true north
- positive `yaw` is clockwise
- negative `pitch` points downward

### DEM Intersection

The DEM workflow is:

1. Convert a pixel into a camera ray
2. Rotate the ray into the world `ENU` frame
3. March along the ray with a fixed step size
4. Convert each sample point into `WGS84`
5. Bilinearly sample the `DEM`
6. Refine the intersection using binary search

See `docs/dem-terrain-model.md` for more details.

### Tests

Run all tests:

```powershell
pytest -q
```

### Current Limitations

- The current implementation still assumes a pinhole camera model
- Lens distortion correction is not yet included
- `DSM / orthorectification / multi-view reconstruction` are not included yet
- A vertical datum mismatch between UAV altitude and DEM elevation can still produce systematic offsets
- A mismatch in attitude semantics across UAV models can also cause offsets
