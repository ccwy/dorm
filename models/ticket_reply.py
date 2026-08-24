from datetime import datetime
from utils.db import db

class TicketReply(db.Model):
    __tablename__ = 'ticket_replies'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False, comment='留言ID')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='回复用户ID')
    content = db.Column(db.Text, nullable=False, comment='回复内容')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='回复时间')
    
    # 外键关联
    ticket = db.relationship('Ticket', overlaps="replies")
    user = db.relationship('User')
    
    def __repr__(self):
        return f'<TicketReply {self.id} for Ticket {self.ticket_id}>'
    
    @classmethod
    def create(cls, ticket_id, user_id, content):
        """创建留言回复"""
        reply = cls(
            ticket_id=ticket_id,
            user_id=user_id,
            content=content
        )
        db.session.add(reply)
        db.session.commit()
        
        # 更新留言的更新时间
        from models.ticket import Ticket
        ticket = Ticket.get_by_id(ticket_id)
        if ticket:
            ticket.updated_at = datetime.now()
            db.session.commit()
            
        return reply