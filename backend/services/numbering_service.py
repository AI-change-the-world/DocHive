from sqlalchemy.orm import Session
from sqlalchemy import select, update
from typing import Dict, Optional
from models.database_models import NumberingRule, Document, ClassTemplate
from services.template_service import TemplateService
from services.document_service import DocumentService
from datetime import datetime
import re
from sqlalchemy.ext.asyncio import AsyncSession


class NumberingService:
    """编号与索引服务"""

    @staticmethod
    async def generate_document_number(
        db: AsyncSession,
        document_id: int,
    ) -> str:
        """
        为文档生成唯一编号

        Args:
            db: 数据库会话
            document_id: 文档ID

        Returns:
            生成的文档编号
        """
        # 获取文档
        document = await DocumentService.get_document(db, document_id)
        if not document:
            raise ValueError("文档不存在")

        if not document.template_id:
            raise ValueError("文档未关联分类模板")

        if not document.class_path:
            raise ValueError("文档尚未分类")

        # 获取编号规则
        rule = await NumberingService.get_numbering_rule(db, document.template_id)

        if not rule:
            # 如果没有规则，使用默认规则创建
            rule = await NumberingService.create_default_rule(db, document.template_id)

        # 生成编号
        doc_number = await NumberingService._generate_number(
            db, rule, document.class_path
        )

        # 更新文档编号
        document.class_code = doc_number
        await db.commit()

        return doc_number

    @staticmethod
    async def _generate_number(
        db: AsyncSession,
        rule: NumberingRule,
        class_path: Dict[str, str],
    ) -> str:
        """
        根据规则生成编号

        Args:
            db: 数据库会话
            rule: 编号规则
            class_path: 分类路径

        Returns:
            生成的编号
        """
        # 解析规则格式
        # 例如: {year}-{dept_code}-{type_code}-{seq:04d}
        format_str = rule.rule_format

        # 准备替换变量
        variables = {
            "year": str(datetime.now().year),
            "month": str(datetime.now().month).zfill(2),
            "day": str(datetime.now().day).zfill(2),
        }

        # 从分类路径中提取变量
        for key, value in class_path.items():
            # 将层级名称转为变量名（简化处理）
            var_name = key.lower().replace(" ", "_")
            variables[var_name] = value

            # 也可以使用代码形式
            if "_code" in var_name or "code" in var_name:
                variables[var_name] = NumberingService._get_code_from_value(value)

        # 处理序列号
        if "{seq" in format_str:
            if rule.auto_increment:
                # 自增序列号
                rule.current_sequence += 1
                await db.commit()

            seq_pattern = r"\{seq:(\d+)d\}"
            match = re.search(seq_pattern, format_str)
            if match:
                width = int(match.group(1))
                variables["seq"] = str(rule.current_sequence).zfill(width)
            else:
                variables["seq"] = str(rule.current_sequence)

        # 替换变量
        doc_number = format_str
        for var_name, var_value in variables.items():
            doc_number = doc_number.replace(f"{{{var_name}}}", str(var_value))
            # 支持格式化序列号
            doc_number = re.sub(rf"\{{{var_name}:\d+d\}}", str(var_value), doc_number)

        return doc_number

    @staticmethod
    def _get_code_from_value(value: str) -> str:
        """从值中提取代码（简化实现）"""
        # 可以实现更复杂的映射逻辑
        code_map = {
            "研发部": "RD",
            "市场部": "MK",
            "人力资源部": "HR",
            "财务部": "FN",
            "技术报告": "TECH",
            "计划": "PLN",
            "总结": "SUM",
            "简历": "CV",
        }
        return code_map.get(value, value[:2].upper())

    @staticmethod
    async def get_numbering_rule(
        db: AsyncSession,
        template_id: int,
    ) -> Optional[NumberingRule]:
        """获取模板的编号规则"""
        result = await db.execute(
            select(NumberingRule)
            .where(NumberingRule.template_id == template_id)
            .order_by(NumberingRule.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def create_numbering_rule(
        db: AsyncSession,
        template_id: int,
        rule_format: str,
        separator: str = "-",
        auto_increment: bool = True,
    ) -> NumberingRule:
        """创建编号规则"""
        rule = NumberingRule(
            template_id=template_id,
            rule_format=rule_format,
            separator=separator,
            auto_increment=auto_increment,
        )

        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def create_default_rule(
        db: AsyncSession,
        template_id: int,
    ) -> NumberingRule:
        """创建默认编号规则"""
        # 默认格式：年份-模板ID-序列号
        default_format = "{year}-TPL{template_id}-{seq:04d}"

        rule = NumberingRule(
            template_id=template_id,
            rule_format=default_format.replace("{template_id}", str(template_id)),
            separator="-",
            auto_increment=True,
        )

        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def reset_sequence(
        db: AsyncSession,
        rule_id: int,
        new_sequence: int = 0,
    ) -> bool:
        """重置序列号"""
        result = await db.execute(
            select(NumberingRule).where(NumberingRule.id == rule_id)
        )
        rule = result.scalar_one_or_none()

        if not rule:
            return False

        rule.current_sequence = new_sequence
        await db.commit()
        return True
