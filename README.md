# UAVDataHandling

无人机图像坐标解算项目。

当前阶段的核心目标是：

- 读取单张无人机图片中的元数据
- 支持外部参数覆盖图像元数据
- 输入像素坐标 `(u, v)`
- 输出对应目标点的 `WGS84` 经纬度
- 支持平地模型和 `DEM` 地形模型两种求交方式
- 提供最小可验证的 `Python API`、`CLI` 和本地网页端

## 1. 当前能力

项目目前已经实现：

- DJI 图片 `EXIF / XMP` 元数据读取
- 像素点、线、面批量地理解算
- 平地假设下的射线与地面求交
- 基于 `GeoTIFF DEM` 的射线与地形求交
- 本地网页端图片标注与地图定位
- CLI 单点与标注解算
- 单元测试与真实样例测试

## 2. 目录结构

- `src/uav_geo/`
  核心代码
- `src/uav_geo/readers/`
  元数据读取
- `src/uav_geo/terrain.py`
  DEM 地形采样与求交
- `tests/`
  单元测试和样例测试
- `docs/`
  算法与模型说明
- `web/`
  本地网页端

## 3. 依赖环境

建议使用 `Python 3.11+`。

安装依赖：

```powershell
pip install -r requirements.txt
```

当前主要依赖：

- `numpy`
- `Pillow`
- `pyproj`
- `rasterio`
- `pytest`

## 4. 已验证数据

图片样例目录：

`G:\DJIImage\drone_images`

DEM 根目录：

`G:\GIS\Data\Dem\重庆市\不统计`

网页端当前会从该目录递归扫描 `*.tif / *.tiff`，并提供下拉选择。

## 5. 启动网页端

```powershell
python UAVDataHandling.py serve
```

默认参数：

- 图片根目录：`G:\DJIImage\drone_images`
- DEM 根目录：`G:\GIS\Data\Dem\重庆市\不统计`
- 默认 DEM：`G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif`
- 地址：`http://127.0.0.1:8765`

如果需要自定义目录：

```powershell
python UAVDataHandling.py serve `
  --sample-root "G:\DJIImage\drone_images" `
  --dem-root "G:\GIS\Data\Dem\重庆市\不统计" `
  --dem-path "G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif"
```

## 6. 网页端使用方式

1. 从左上角图片下拉框选择图片
2. 从旁边 DEM 下拉框选择地形文件
3. 点击“加载图片”
4. 在图片上绘制点、线、面
5. 结果会自动解算并显示在左侧地图上

说明：

- 如果 DEM 下拉框选择“不使用 DEM（平地假设）”，系统会退回平地模型
- 如果切换 DEM，已绘制标注会自动重新解算
- 如果图片位置超出所选 DEM 范围，页面会显示明确错误

## 7. CLI 用法

### 7.1 单点解算

```powershell
python UAVDataHandling.py point `
  "G:\DJIImage\drone_images\example.jpeg" `
  2016 1512
```

### 7.2 指定 DEM 进行单点解算

```powershell
python UAVDataHandling.py point `
  "G:\DJIImage\drone_images\example.jpeg" `
  2016 1512 `
  --dem-path "G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif"
```

### 7.3 标注批量解算

```powershell
python UAVDataHandling.py batch `
  "G:\DJIImage\drone_images\example.jpeg" `
  --annotation-file ".\temp_annotation.json"
```

## 8. Python API 示例

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

## 9. 坐标与单位约定

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
- `roll` 按当前实现约定参与相机前向轴旋转

## 10. DEM 求交说明

DEM 模式下的求交链路：

1. 像素点转相机射线
2. 相机射线转世界 `ENU` 射线
3. 沿射线按固定步长推进
4. 将每个采样点转换为 `WGS84`
5. 在 `DEM` 上做双线性插值采样
6. 用二分逼近求出射线与地形表面的交点

更详细说明见：

[docs/dem-terrain-model.md](G:\code_python\UAVDataHandling\docs\dem-terrain-model.md)

## 11. 测试

运行全部测试：

```powershell
pytest -q
```

当前测试覆盖包括：

- 基础几何解算
- DEM 双线性采样
- DEM 地形求交
- DJI 样例图片集成验证

## 12. 当前已知边界

- 当前默认仍基于针孔相机模型
- 尚未引入镜头畸变校正
- 尚未接入 DEM 以外的 DSM / 正射 / 多视重建
- 如果无人机绝对高度与 DEM 高程基准不一致，仍可能出现系统性偏差
- 如果姿态角语义与机型字段定义不一致，也会造成落点偏差

## 13. 下一步建议

如果仍然存在明显偏差，建议继续按下面顺序排查：

1. 核对所选 DEM 是否覆盖当前照片区域
2. 核对 `absolute_altitude_m` 与 DEM 是否使用同一高程基准
3. 用图片中心点对比 `LRFTargetLon/Lat` 或已知地物点
4. 再进一步检查姿态角定义与旋转顺序
