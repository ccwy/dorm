from .user import User, UserOperationRecord  # 用户模型及操作记录
from .room import Room, RoomStatus, Bed, BedStatus, RoomFacility  # 房间管理模型

from .fee_subsidy import FeeSubsidy, FeeSubsidyUsage  # 补贴模型
from .ticket import Ticket, TicketReply  # 留言模型
from .todo import Todo, TodoProgress # 待办事项模型及进度记录模型
from .chat import ChatSession, ChatParticipant, ChatMessage  # 聊天模型
from .fixed_asset import FixedAsset, AssetOperationRecord, AssetInventory, AssetInventoryDetail  # 固定资产管理模型
from .department import Department  # 部门管理模型
from .supply import Supplier, SupplierOperationRecord, SupplyItem, StorageLocation, SupplyStockDetail, StockIn, StockInDetail, StockOut, StockOutDetail, SupplyInventory, SupplyInventoryDetail, SupplyStockRecord  # 低值易耗品进销存模型
from .role import Role, RolePermission  # 角色权限模型
from .contract import Contract, ContractOperationRecord
from .maintenance import MaintenanceOrder, MaintenanceReply