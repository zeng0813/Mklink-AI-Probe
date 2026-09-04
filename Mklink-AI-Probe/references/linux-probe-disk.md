# Linux 探针 U 盘识别

仅在 Linux/macOS 上 MICROKEEN U 盘找不到、脱机烧录报 `MICROKEEN disk is
unavailable`，或需要固定挂载位置时读取。


## 发现顺序

`find_microkeen_disk()` 在 POSIX 平台按下列顺序查找，返回第一个可写目录：

1. `MKLINK_MICROKEEN_DISK` 环境变量指向的目录（存在即用，不再校验卷标）。
2. `lsblk --json --output LABEL,MOUNTPOINT` 中卷标等于 `MICROKEEN` 的挂载点，
   大小写不敏感，覆盖任意挂载位置。
3. 常见挂载根下名为 `MICROKEEN` 的目录：`/media/<user>`、`/run/media/<user>`、
   `/media`、`/run/media`、`/mnt`、`/Volumes`。`<user>` 取 `SUDO_USER`、
   `USER` 或家目录名，因此 `sudo` 会话也能命中登录用户的 udisks2 挂载点。

全部候选都不可写时，退回第一个可读目录；都不存在则返回 `None`，Web GUI 显示
"MICROKEEN 未找到"。

macOS 同样走这条路径，实际挂载点通常是 `/Volumes/MICROKEEN`。

## Debian 13 排障

先让工具自己说明为什么找不到，一条命令即可：

```bash
python -m mklink microkeen-disk
```

输出包含平台、磁盘路径、是否可写、FLM 目录、原因、检查过的候选路径和 lsblk
报告的全部挂载点。`reason` 的含义：

| reason | 含义 | 处理 |
|--------|------|------|
| `found` | 已找到且可写 | 正常 |
| `read-only` | 已挂载但不可写 | 重新挂载并加 `uid`/`gid`/`umask` |
| `no-access` | 候选存在但不可读也不可写 | 检查挂载点权限与服务运行用户 |
| `no-mount` | 未挂载，或卷标不是 `MICROKEEN` | 见下节；或用 `MKLINK_MICROKEEN_DISK` 指定 |
| `configured-root` | 使用环境变量指定的路径 | — |
| `configured-root-missing` | 环境变量指向的目录不存在 | 修正路径，或先挂载 |
| `not-found` | Windows 上无卷标匹配的盘 | 检查盘符与卷标 |

`/api/microkeen` 返回同样的字段（`platform`、`reason`、`candidates`、
`mounted_volumes`、`writable`），可用于脚本化排查。

再确认系统层面：

```bash
lsblk -J -o NAME,LABEL,MOUNTPOINT,FSTYPE,RM,SIZE   # 看卷标与是否已挂载
udisksctl status                                   # udisks2 视角的设备
dmesg -w                                           # 插入瞬间的内核日志
```

按结果处理：

| 现象 | 处理 |
|------|------|
| `lsblk` 无设备 | 检查线缆与 USB 口；`dmesg` 看是否有 `device descriptor read` 或枚举失败 |
| 有设备、无 `MOUNTPOINT` | 未自动挂载，见下节 |
| 卷标不是 `MICROKEEN` | 用 `MKLINK_MICROKEEN_DISK` 指定挂载点，或用 `fatlabel` 改卷标 |
| 已挂载但 GUI 仍显示未找到 | 权限或服务运行用户问题，见下节 |
| 需要刷 UF2 固件 | 卷标不是 `MICROKEEN`，用 `MKLINK_BOOTLOADER_DISK` |

### 未自动挂载

无桌面环境的 Debian 默认不 automount。用 udisks2 挂载，无需 root，且挂载点正好
落在自动发现的候选里：

```bash
udisksctl mount -b /dev/sdb1        # 挂载到 /media/$USER/<LABEL>
udisksctl unmount -b /dev/sdb1      # 用完后卸载
```

需要固定位置时手动挂载，注意 FAT 无 Unix 权限位，要显式给当前用户写权限：

```bash
sudo mkdir -p /mnt/microkeen
sudo mount -t vfat -o uid=$USER,gid=$USER,umask=002 /dev/sdb1 /mnt/microkeen
```

### 权限与服务运行用户

- Web GUI 后端以哪个用户运行，就以哪个用户的权限访问挂载点。用 `sudo` 启动的
  服务能读写 udisks2 的用户挂载点，但 `MKLINK_MICROKEEN_DISK` 里的 `~` 不会展开。
- 以 systemd 服务运行时，写死挂载点并显式声明环境变量：

  ```ini
  [Service]
  Environment=MKLINK_MICROKEEN_DISK=/mnt/microkeen
  ```

- 目录可读不可写时，自动发现仍会返回该路径，但脱机烧录会在写阶段失败。这种
  情况优先修挂载参数（`uid`/`gid`/`umask`），不要直接 `chmod` FAT 挂载点。

### ModemManager 抢占

命令行口被 ModemManager 抓走时，U 盘不受影响但同设备的串口会消失。加 udev
规则忽略 MKLink：

```text
# /etc/udev/rules.d/99-mklink.rules
ATTRS{idVendor}=="0d28", ATTRS{idProduct}=="0202", ENV{ID_MM_DEVICE_IGNORE}="1"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## 固定挂载位置

自动发现无法确定时，直接指定挂载根目录：

```bash
export MKLINK_MICROKEEN_DISK=/media/$USER/MICROKEEN
python -m mklink gui
```

UF2 升级时进 bootloader 后卷标会变，用另一个变量：

```bash
export MKLINK_BOOTLOADER_DISK=/media/$USER/<bootloader-label>
```

## 已知限制

- 只识别文件系统卷标或目录名为 `MICROKEEN` 的卷。卷标被改写后必须显式指定
  `MKLINK_MICROKEEN_DISK`。
- `lsblk` 缺失或超时（3 秒）时静默跳过，仅靠挂载根扫描兜底。
- 多分区探针只返回第一个可写挂载点，不做多盘选择。
- 设备已枚举但完全未挂载时返回 `None`，不会尝试代为挂载。
