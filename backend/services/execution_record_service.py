"""
智能体执行记录服务
"""

import time
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.database_models import AgentExecutionRecord


class ExecutionRecordService:
    """执行记录服务"""

    @staticmethod
    async def create_record(
        db: AsyncSession,
        agent_id: Optional[int],
        agent_name: str,
        query: str,
        template_id: int,
        execution_pattern: str,
        session_id: str,
        user_id: Optional[int] = None,
    ) -> AgentExecutionRecord:
        """
        创建执行记录

        Args:
            db: 数据库会话
            agent_id: Agent ID
            agent_name: Agent名称
            query: 用户查询
            template_id: 模板ID
            execution_pattern: 执行模式
            session_id: 会话ID
            user_id: 用户ID

        Returns:
            创建的执行记录
        """
        record = AgentExecutionRecord(
            agent_id=agent_id,
            agent_name=agent_name,
            query=query,
            template_id=template_id,
            execution_pattern=execution_pattern,
            session_id=session_id,
            user_id=user_id,
            status="running",
            start_time=int(time.time()),
        )

        db.add(record)
        await db.commit()
        await db.refresh(record)

        logger.info(
            f"创建执行记录 ID={record.id}, Agent={agent_name}, user_id={user_id}")
        return record

    @staticmethod
    async def update_record(
        db: AsyncSession,
        record_id: int,
        **kwargs,
    ) -> Optional[AgentExecutionRecord]:
        """
        更新执行记录

        Args:
            db: 数据库会话
            record_id: 记录ID
            **kwargs: 更新字段

        Returns:
            更新后的记录
        """
        result = await db.execute(
            select(AgentExecutionRecord).where(
                AgentExecutionRecord.id == record_id)
        )
        record = result.scalar_one_or_none()

        if not record:
            logger.warning(f"执行记录不存在 ID={record_id}")
            return None

        for key, value in kwargs.items():
            if hasattr(record, key):
                setattr(record, key, value)

        await db.commit()
        await db.refresh(record)

        logger.info(f"更新执行记录 ID={record_id}")
        return record

    @staticmethod
    async def complete_record(
        db: AsyncSession,
        record_id: int,
        execution_plan: List[Dict],
        step_history: List[Dict],
        final_result: Dict,
        report_data: Dict,
        html_report: str,
        markdown_report: str,
        status: str = "completed",
    ) -> Optional[AgentExecutionRecord]:
        """
        完成执行记录

        Args:
            db: 数据库会话
            record_id: 记录ID
            execution_plan: 执行计划
            step_history: 步骤历史
            final_result: 最终结果
            report_data: 报告数据
            html_report: HTML报告
            markdown_report: Markdown报告
            status: 状态

        Returns:
            更新后的记录
        """
        result = await db.execute(
            select(AgentExecutionRecord).where(
                AgentExecutionRecord.id == record_id)
        )
        record = result.scalar_one_or_none()

        if not record:
            logger.warning(f"执行记录不存在 ID={record_id}")
            return None

        # 计算统计信息
        statistics = report_data.get("statistics", {})

        # 更新记录
        record.status = status
        record.execution_plan = execution_plan
        record.step_history = step_history
        record.final_result = final_result
        record.report_data = report_data
        record.html_report = html_report
        record.markdown_report = markdown_report
        record.end_time = int(time.time())
        record.duration_seconds = record.end_time - record.start_time

        # 统计信息
        record.total_steps = statistics.get("total_steps", 0)
        record.executed_steps = statistics.get("executed_steps", 0)
        record.successful_steps = statistics.get("successful_steps", 0)
        record.failed_steps = statistics.get("failed_steps", 0)
        record.success_rate = int(statistics.get("success_rate", 0))

        await db.commit()
        await db.refresh(record)

        logger.info(f"完成执行记录 ID={record_id}, 状态={status}")
        return record

    @staticmethod
    async def get_record(
        db: AsyncSession,
        record_id: int,
    ) -> Optional[AgentExecutionRecord]:
        """
        获取执行记录

        Args:
            db: 数据库会话
            record_id: 记录ID

        Returns:
            执行记录
        """
        result = await db.execute(
            select(AgentExecutionRecord).where(
                AgentExecutionRecord.id == record_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_records(
        db: AsyncSession,
        user_id: Optional[int] = None,
        agent_id: Optional[int] = None,
        status: Optional[str] = None,
        template_id: Optional[int] = None,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[AgentExecutionRecord], int]:
        """
        获取执行记录列表

        Args:
            db: 数据库会话
            user_id: 用户ID筛选
            agent_id: Agent ID筛选
            status: 状态筛选
            template_id: 模板ID筛选
            start_date: 开始时间戳
            end_date: 结束时间戳
            page: 页码
            page_size: 每页数量

        Returns:
            (记录列表, 总数)
        """
        # 构建查询条件
        conditions = []
        if user_id is not None:
            conditions.append(AgentExecutionRecord.user_id == user_id)
        if agent_id is not None:
            conditions.append(AgentExecutionRecord.agent_id == agent_id)
        if status:
            conditions.append(AgentExecutionRecord.status == status)
        if template_id is not None:
            conditions.append(AgentExecutionRecord.template_id == template_id)
        if start_date is not None:
            conditions.append(AgentExecutionRecord.start_time >= start_date)
        if end_date is not None:
            conditions.append(AgentExecutionRecord.start_time <= end_date)

        # 查询总数
        count_query = select(func.count(AgentExecutionRecord.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))

        count_result = await db.execute(count_query)
        total = count_result.scalar()

        # 查询记录
        query = select(AgentExecutionRecord)
        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(desc(AgentExecutionRecord.created_at))
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        records = result.scalars().all()

        logger.info(f"查询执行记录: user_id={user_id}, 找到{len(records)}条, 总数{total}")
        return list(records), total

    @staticmethod
    async def delete_record(
        db: AsyncSession,
        record_id: int,
    ) -> bool:
        """
        删除执行记录

        Args:
            db: 数据库会话
            record_id: 记录ID

        Returns:
            是否成功删除
        """
        result = await db.execute(
            select(AgentExecutionRecord).where(
                AgentExecutionRecord.id == record_id)
        )
        record = result.scalar_one_or_none()

        if not record:
            logger.warning(f"执行记录不存在 ID={record_id}")
            return False

        await db.delete(record)
        await db.commit()

        logger.info(f"删除执行记录 ID={record_id}")
        return True

    @staticmethod
    async def get_statistics(
        db: AsyncSession,
        user_id: Optional[int] = None,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        获取执行统计信息

        Args:
            db: 数据库会话
            user_id: 用户ID筛选
            start_date: 开始时间戳
            end_date: 结束时间戳

        Returns:
            统计信息
        """
        conditions = []
        if user_id is not None:
            conditions.append(AgentExecutionRecord.user_id == user_id)
        if start_date is not None:
            conditions.append(AgentExecutionRecord.start_time >= start_date)
        if end_date is not None:
            conditions.append(AgentExecutionRecord.start_time <= end_date)

        # 总执行次数
        count_query = select(func.count(AgentExecutionRecord.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        count_result = await db.execute(count_query)
        total_executions = count_result.scalar()

        # 按状态分组统计
        status_query = select(
            AgentExecutionRecord.status,
            func.count(AgentExecutionRecord.id).label("count")
        ).group_by(AgentExecutionRecord.status)
        if conditions:
            status_query = status_query.where(and_(*conditions))

        status_result = await db.execute(status_query)
        status_stats = {row.status: row.count for row in status_result}

        # 平均成功率
        avg_query = select(func.avg(AgentExecutionRecord.success_rate))
        if conditions:
            avg_query = avg_query.where(and_(*conditions))
        avg_result = await db.execute(avg_query)
        avg_success_rate = avg_result.scalar() or 0

        # 平均执行时长
        avg_duration_query = select(
            func.avg(AgentExecutionRecord.duration_seconds))
        if conditions:
            avg_duration_query = avg_duration_query.where(and_(*conditions))
        avg_duration_result = await db.execute(avg_duration_query)
        avg_duration = avg_duration_result.scalar() or 0

        return {
            "total_executions": total_executions,
            "by_status": status_stats,
            "avg_success_rate": round(avg_success_rate, 2),
            "avg_duration_seconds": round(avg_duration, 2),
        }
