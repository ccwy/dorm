from datetime import datetime
from utils.db import db
import logging

class RoomFacility(db.Model):
    """房间设施物品模型"""
    __tablename__ = 'room_facilities'
    
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False, comment='关联的房间ID')
    name = db.Column(db.String(100), nullable=False, comment='设施名称')
    quantity = db.Column(db.Integer, default=1, nullable=False, comment='设施数量')
    status = db.Column(db.String(20), default="可用", nullable=False, comment='设施状态：可用、损坏、维护中、丢失')
    remark = db.Column(db.String(500), nullable=True, comment='设施备注')
    
    # 时间字段
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')
    

    def __repr__(self):
        return f"<RoomFacility {self.room.building}-{self.room.room_number}-{self.name}({self.quantity})>"

    @classmethod
    def create_facility(cls, room_id, name, quantity, status="可用", remark=None):
        """创建设施

        Args:
            room_id: 房间ID
            name: 设施名称
            quantity: 设施数量，默认为1
            status: 设施状态，默认为"可用"
            remark: 设施备注，可选
        """

        # 创建新设施
        facility = cls(
            room_id=room_id,
            name=name,
            quantity=quantity,
            status=status,
            remark=remark
        )

        db.session.add(facility)
        # 此处不提交，由调用方统一管理事务
        logging.info(f"创建设施成功:{name} : {quantity}")
        return facility

    def update_facility(self, quantity=None, status=None, remark=None):
        """更新设施信息"""
        # 检查是否需要删除设施
        if quantity is not None and quantity <= 0:
            self.delete_facility()
            logging.info(f"删除设施成功: {self.name}")
            return None

        # 记录是否有实际更新
        has_update = False

        # 更新数量（仅当数量有变化时）
        if quantity is not None and self.quantity != quantity:
            self.quantity = quantity
            has_update = True

        # 更新状态（仅当状态有变化时）
        if status is not None and self.status != status:
            valid_statuses = ['可用', '损坏', '维护中', '丢失']
            if status not in valid_statuses:
                logging.error(f"更新设施失败: 无效的设施状态: {status}")
                raise ValueError(f"无效的设施状态: {status}，有效状态为: {', '.join(valid_statuses)}")
            self.status = status
            has_update = True

        # 更新备注（仅当备注有变化时）
        if remark is not None and self.remark != remark:
            self.remark = remark
            has_update = True

        # 如果没有实际更新，返回原实例
        if not has_update:
            return self

        return self

    @classmethod
    def bulk_update_facilities(cls, room_id, facilities, remark=None):
        """
        批量更新房间设施
        
        Args:
            room_id: 房间ID
            facilities: 设施列表，每个元素为{"name": name, "quantity": quantity}
            remark: 自定义备注信息，可选参数
        Returns:
            bool: 操作是否成功
        """
        # 获取所有有效的设施名称
        valid_facilities = cls.get_all_valid_facilities()
        
        # 获取当前房间的所有设施
        current_facilities = cls.query.filter_by(room_id=room_id).all()
        current_facility_dict = {f.name: f for f in current_facilities}
        
        try:
            # 处理每个提交的设施
            for facility in facilities:
                name = facility.get('name', '').strip()
                quantity = facility.get('quantity', 0)
                
                # 验证数量是否为有效整数
                try:
                    quantity = int(quantity)
                except ValueError:
                    logging.warning(f"无效的设施数量: {quantity}，设施名称: {name}")
                    continue
                
                # 检查设施名称是否有效
                if name not in valid_facilities:
                    logging.warning(f"无效的设施名称: {name}，已跳过")
                    continue
                    
                # 检查设施是否已存在
                if name in current_facility_dict:
                    # 存在则更新
                    existing_facility = current_facility_dict[name]
                    if quantity <= 0:
                        # 数量<=0则删除
                        existing_facility.delete_facility()
                    else:
                        # 否则更新数量，使用自定义备注
                        existing_facility.update_facility(
                            quantity=quantity,
                            remark=remark  # 使用传入的自定义备注
                        )
                    del current_facility_dict[name]  # 从待处理字典中移除
                else:
                    # 不存在则创建新设施，使用自定义备注
                    if quantity > 0:  # 只创建数量为正的设施
                        cls.create_facility(
                            room_id=room_id, 
                            name=name, 
                            quantity=quantity,
                            remark=remark  # 使用传入的自定义备注
                        )
                    else:
                        logging.warning(f"创建设施失败: 数量为0，已跳过")
                        continue
            
            # 处理剩余的设施（前端未提交的，视为需要删除）
            for remaining_facility in current_facility_dict.values():
                remaining_facility.delete_facility()
            
            logging.info(f"批量更新房间{room_id}的设施成功")
            return True
        except Exception as e:
            logging.error(f"批量更新设施失败: {str(e)}")
            return False

    def delete_facility(self):
        """删除设施

        Returns:
            bool: 删除成功返回True
        """
        db.session.delete(self)
        db.session.commit()
        logging.info(f"删除设施成功: {self.name}")
        return True

    @classmethod
    def get_all_valid_facilities(cls):
        """从系统配置获取所有有效的房间设施（基础设施+自定义设施）"""
        from models.system_config import SystemConfig  # 导入系统配置模型
        base_facilities = SystemConfig.get_config_value('BASE_FACILITIES', [])
        custom_facilities = SystemConfig.get_config_value('CUSTOM_FACILITIES', [])
        
        # 合并并去重
        all_facilities = list(set(base_facilities + custom_facilities))
        # 排序
        all_facilities.sort()
        
        return all_facilities

    @classmethod
    def get_valid_facilities_for_display(cls):
        """
        将系统配置中的设施列表转换为前端选择控件所需的格式
        返回格式: [{"name": "设施名称", "label": "设施显示文本"}, ...]
        因设施名称本身为中文，故name和label取值相同
        """
        # 复用已有的系统配置设施获取逻辑
        all_valid_facilities = cls.get_all_valid_facilities()
        
        # 转换为前端需要的字典结构
        return [
            {"name": facility_name, "label": facility_name}
            for facility_name in all_valid_facilities
        ]
