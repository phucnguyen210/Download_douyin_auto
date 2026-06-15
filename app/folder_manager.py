"""
folder_manager.py - Quản lý thư mục với giới hạn video

Sử dụng: 
    from app.folder_manager import get_dated_dir_with_limit
    
    dated_dir = get_dated_dir_with_limit(
        base_target_dir=target_dir,
        publish_date=publish_date,
        max_videos_per_folder=10,
        logger=self.logger,
    )
"""

from pathlib import Path
from typing import Optional
from app.logger import Logger


def get_dated_dir_with_limit(
    base_target_dir: Path,
    publish_date: str,
    max_videos_per_folder: int = 10,
    logger: Optional[Logger] = None,
) -> Path:
    """
    Lấy thư mục ngày để lưu video, tự động tạo subfolder khi đầy.
    
    Cấu trúc:
        - downloads/2024-12-25/           (max 10 video)
        - downloads/2024-12-25_1/         (khi đầy)
        - downloads/2024-12-25_2/         (nếu tiếp tục)
    
    Args:
        base_target_dir (Path): Thư mục gốc (vd: Path("/downloads"))
        publish_date (str): Ngày xuất bản (vd: "2024-12-25")
        max_videos_per_folder (int): Max video mỗi folder (default: 10)
        logger (Optional): Logger để log thông tin (optional)
    
    Returns:
        Path: Đường dẫn thư mục để lưu video
    
    Example:
        >>> dated_dir = get_dated_dir_with_limit(
        ...     base_target_dir=Path("./downloads"),
        ...     publish_date="2024-12-25",
        ...     max_videos_per_folder=10,
        ... )
        >>> # Returns: Path("./downloads/2024-12-25")
        >>> # Or: Path("./downloads/2024-12-25_1") nếu đầy
    """
    
    # Thư mục ngày cơ bản
    base_dated_dir = base_target_dir / publish_date
    
    # Nếu thư mục chưa tồn tại, tạo mới và trả về
    if not base_dated_dir.exists():
        base_dated_dir.mkdir(parents=True, exist_ok=True)
        if logger:
            logger.info(
                f"[green]Tạo folder ngày mới:[/green] {publish_date}"
            )
        return base_dated_dir
    
    # Đếm file .mp4 trong thư mục ngày
    video_count = len(list(base_dated_dir.glob("*.mp4")))
    
    # Nếu chưa đầy, trả về thư mục hiện tại
    if video_count < max_videos_per_folder:
        if logger:
            logger.info(
                f"[cyan]Folder ngày:[/cyan] {publish_date} "
                f"({video_count}/{max_videos_per_folder})"
            )
        return base_dated_dir
    
    # Thư mục đầy, tìm subfolder tiếp theo
    if logger:
        logger.info(
            f"[yellow]Folder {publish_date} đầy,[/yellow] "
            f"tìm subfolder tiếp theo..."
        )
    
    counter = 1
    while True:
        subfolder_name = f"{publish_date}_{counter}"
        subfolder_path = base_target_dir / subfolder_name
        
        # Subfolder mới chưa tồn tại
        if not subfolder_path.exists():
            subfolder_path.mkdir(parents=True, exist_ok=True)
            if logger:
                logger.info(
                    f"[yellow]Tạo subfolder:[/yellow] {subfolder_name}"
                )
            return subfolder_path
        
        # Đếm video trong subfolder hiện tại
        video_count_in_sub = len(list(subfolder_path.glob("*.mp4")))
        
        # Nếu chưa đầy, dùng subfolder này
        if video_count_in_sub < max_videos_per_folder:
            if logger:
                logger.info(
                    f"[cyan]Subfolder:[/cyan] {subfolder_name} "
                    f"({video_count_in_sub}/{max_videos_per_folder})"
                )
            return subfolder_path
        
        counter += 1


def get_folder_info(folder_path: Path) -> dict:
    """
    Lấy thông tin về folder (số lượng video, dung lượng, etc).
    
    Args:
        folder_path (Path): Đường dẫn folder
    
    Returns:
        dict: Thông tin folder
            - video_count: Số lượng video .mp4
            - total_size: Tổng dung lượng (bytes)
            - is_full: Có đầy không (dựa trên 10 video)
    
    Example:
        >>> info = get_folder_info(Path("./downloads/2024-12-25"))
        >>> print(info)
        {
            'video_count': 10,
            'total_size': 5368709120,
            'is_full': True,
        }
    """
    
    if not folder_path.exists():
        return {
            "video_count": 0,
            "total_size": 0,
            "is_full": False,
        }
    
    video_files = list(folder_path.glob("*.mp4"))
    total_size = sum(f.stat().st_size for f in video_files)
    
    return {
        "video_count": len(video_files),
        "total_size": total_size,
        "is_full": len(video_files) >= 10,
    }


def cleanup_empty_folders(base_target_dir: Path, logger: Optional[Logger] = None) -> int:
    """
    Xóa các folder rỗng trong thư mục downloads.
    
    Args:
        base_target_dir (Path): Thư mục gốc
        logger (Optional): Logger
    
    Returns:
        int: Số folder được xóa
    
    Example:
        >>> cleaned = cleanup_empty_folders(Path("./downloads"))
        >>> print(f"Xóa {cleaned} folder rỗng")
    """
    
    removed_count = 0
    
    for folder in base_target_dir.iterdir():
        if not folder.is_dir():
            continue
        
        # Bỏ qua folder _tmp
        if folder.name == "_tmp":
            continue
        
        video_count = len(list(folder.glob("*.mp4")))
        
        if video_count == 0:
            try:
                folder.rmdir()
                removed_count += 1
                if logger:
                    logger.info(
                        f"[dim]Xóa folder rỗng:[/dim] {folder.name}"
                    )
            except Exception as e:
                if logger:
                    logger.error(
                        f"Lỗi xóa folder {folder.name}: {e}"
                    )
    
    return removed_count