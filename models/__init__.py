from .user import User
from .room import Room
from .dorm import Dorm
from .utility_room_meter import UtilityMeterReading  # 新增：抄表记录模型
from .log import OperationLog
from .system_config import SystemConfig  # 关键：添加这行导出
from .room_bed import Bed  #床位管理模型
from .room_facility import RoomFacility  # 房间设施模型
from .utility_room_bill_record import RoomUtilityRecord  #房间费用核算主表模型
from .utility_room_bill_occupant import RoomUtilityOccupant #人员费用核算子表模型
from .utility_room_bill_checkout import CheckoutUtilityRecord #退宿人员费用核算子表模型
from .fee_subsidy import FeeSubsidy #补贴模型
from .fee_subsidy_usage import FeeSubsidyUsage #补贴子表
from .ticket import Ticket # 留言模型
from .ticket_reply import TicketReply # 留言回复模型
from .todo import Todo # 待办事项模型
from .todo_progress import TodoProgress # 待办事项进度记录模型
from .chat_session import ChatSession  # 聊天会话模型
from .chat_participant import ChatParticipant  # 聊天参与者模型
from .chat_message import ChatMessage  # 聊天消息模型
from .fixed_asset import FixedAsset  # 固定资产模型
from .fixed_asset import AssetOperationRecord  # 资产操作记录模型
from .user_operation_record import UserOperationRecord  # 用户操作记录模型
from .fixed_asset import AssetInventory  # 资产盘点主表模型
from .fixed_asset import AssetInventoryDetail  # 资产盘点明细模型
from .department import Department  # 部门管理模型
from .supply import Supplier, SupplierOperationRecord, SupplyItem, StorageLocation, SupplyStockDetail, StockIn, StockInDetail, StockOut, StockOutDetail, SupplyInventory, SupplyInventoryDetail, SupplyStockRecord  # 低值易耗品进销存模型
from .role import Role, RolePermission  # 角色权限模型
from .contract import Contract, ContractOperationRecord
from .maintenance import MaintenanceOrder, MaintenanceReply