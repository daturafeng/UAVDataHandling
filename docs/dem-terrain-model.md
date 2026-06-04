# DEM 地形求交说明

## 1. 适用范围

本模块用于替代首阶段的“单一水平地面”假设，在已知无人机位置、姿态和相机内参的前提下，使用 `DEM` 栅格高程与像素射线求交。

当前实现目标：

- 输入图像像素坐标 `(u, v)`
- 输入无人机 `WGS84` 经纬度与绝对高度
- 输入相机姿态角 `yaw / pitch / roll`
- 输入 `GeoTIFF DEM`
- 输出射线与地形表面的交点 `WGS84` 经纬度和高程

## 2. 坐标系与单位

- 无人机地理坐标：`WGS84`
- DEM 平面坐标：按栅格文件自身 `CRS` 读取，内部通过 `pyproj` 从 `WGS84` 转到 DEM 坐标系
- 局部计算坐标：`ENU`
- 水平与垂直距离单位：米
- 像素坐标原点：图像左上角，`u` 向右增大，`v` 向下增大

## 3. 求交链路

1. 将像素点转换为相机坐标系中的单位射线
2. 根据云台姿态把射线旋转到世界 `ENU` 坐标系
3. 沿射线按固定步长前进
4. 每一步把 `ENU` 偏移转换为 `WGS84` 经纬度与高度
5. 在 DEM 上做双线性插值采样，得到当前位置地表高程
6. 当“射线点高度 - DEM 高程”从正变负时，说明已经穿过地形表面
7. 在穿越区间内做二分逼近，得到更稳定的交点

## 4. 当前假设

- DEM 栅格高程单位为米
- 无人机 `absolute_altitude_m` 与 DEM 使用同一高程基准
- DEM 分辨率足以支撑当前地图标注场景

如果无人机绝对高度和 DEM 高程基准不一致，即使引入 DEM，仍然会出现系统性偏差。

## 5. 失败条件

以下情况不会静默回退到平地模型，而是直接报错：

- 未提供 `dem_path`
- 射线没有朝向地面
- 无人机位置不在 DEM 覆盖范围内
- 射线离开 DEM 覆盖范围后仍未找到交点
- 无人机高度低于或等于 DEM 地表高程

## 6. 接口

Python API 示例：

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
```

CLI 示例：

```powershell
python UAVDataHandling.py point `
  "G:\DJIImage\drone_images\example.jpeg" `
  2016 1512 `
  --dem-path "G:\GIS\Data\Dem\重庆市\不统计\南岸区\重庆市_不统计_南岸区.tif"
```
