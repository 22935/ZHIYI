"""本地资源商店：管理可安装内容，不参与资源调度裁决。"""

from .contracts import CatalogItem, CustomResourceRequest, InstallationJob, InstallationStatus

__all__ = ["CatalogItem", "CustomResourceRequest", "InstallationJob", "InstallationStatus"]
