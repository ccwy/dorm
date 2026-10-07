import io
import logging
import traceback
from datetime import datetime
from flask import Blueprint, flash, redirect, url_for, send_file
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from utils.lazy_imports import pd
from models.payment.payment_record import PaymentRecord
from sqlalchemy.orm import joinedload

# 创建付款导出专用蓝图
payment_export_bp = Blueprint(
    'payment_export',
    __name__,
    url_prefix='/payment'
)


@payment_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('payment.view')
def export():
    """导出付款数据为Excel"""
    try:
        logging.debug('开始执行付款数据导出')

        # 获取付款数据，预加载合同关联
        payments = PaymentRecord.query.options(
            joinedload(PaymentRecord.contract)
        ).order_by(PaymentRecord.id).all()
        logging.debug(f'查询到{len(payments)}条付款数据')

        if not payments:
            logging.info('没有可导出的付款数据')
            flash('没有可导出的付款数据', 'info')
            return redirect(url_for('payment.index'))

        # 准备导出数据
        data = []
        for p in payments:
            try:
                data.append({
                    'ID': p.id,
                    '付款编号': p.payment_number or '',
                    '合同编号': p.contract.contract_number if p.contract else '',
                    '合同名称': p.contract.contract_name if p.contract else '',
                    '付款方式': p.payment_method or '',
                    '乙方收款方式': p.party_b_payment_method or '',
                    '乙方银行账号': p.party_b_bank_account or '',
                    '乙方开户行': p.party_b_bank_name or '',
                    '乙方收款银行': p.party_b_receiving_bank or '',
                    '乙方开户名称': p.party_b_account_name or '',
                    '乙方收款账号': p.party_b_payment_account or '',
                    '固定金额': float(p.fixed_amount) if p.fixed_amount else '',
                    '付款轮次': p.payment_rounds or '',
                    '当前轮次': p.current_round or '',
                    '对账日': p.reconciliation_day or '',
                    '付款截止日': p.payment_deadline_day or '',
                    '付款周期': p.payment_period or '',
                    '计划付款日期': p.planned_payment_date.strftime('%Y-%m-%d') if p.planned_payment_date else '',
                    '截止付款日期': p.deadline_date.strftime('%Y-%m-%d') if p.deadline_date else '',
                    '计划金额': float(p.planned_amount) if p.planned_amount else '',
                    '实际金额': float(p.actual_amount) if p.actual_amount else '',
                    '实际付款日期': p.payment_date.strftime('%Y-%m-%d') if p.payment_date else '',
                    '状态': p.status or '',
                    '备注': p.remark or '',
                    '操作人': p.operator_name or '',
                    '创建时间': p.create_time.strftime('%Y-%m-%d %H:%M:%S') if p.create_time else '',
                })
            except Exception as e:
                logging.error(f'处理付款ID={p.id}时出错: {str(e)}', exc_info=True)
                raise

        logging.debug(f'数据准备完成，共{len(data)}条记录')

        # 生成Excel
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='付款数据')

        output.seek(0)
        filename = f"付款数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='export',
            action=f"导出付款数据，共 {len(payments)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出付款数据')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出付款数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='export',
            action=f"尝试导出付款数据失败: {str(e)}",
            result="失败"
        )
        flash('导出失败，请联系管理员', 'danger')
        return redirect(url_for('payment.index'))