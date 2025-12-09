import { request } from "../utils/request";
import type {
    PaginatedResponse,
    ExecutionRecord,
    ExecutionRecordListRequest,
    ExecutionRecordStatistics,
} from "../types";

// 获取执行记录列表
export const getExecutionRecords = (
    params: ExecutionRecordListRequest
) => {
    return request.get<PaginatedResponse<ExecutionRecord>>(
        "/execution-records/list",
        { params }
    );
};

// 获取执行记录详情
export const getExecutionRecordDetail = (recordId: number) => {
    return request.get<ExecutionRecord>(
        `/execution-records/${recordId}`
    );
};

// 删除执行记录
export const deleteExecutionRecord = (recordId: number) => {
    return request.delete<{ message: string }>(`/execution-records/${recordId}`);
};

// 获取执行记录统计信息
export const getExecutionStatistics = () => {
    return request.get<ExecutionRecordStatistics>(
        "/execution-records/statistics/summary"
    );
};

// 获取HTML报告
export const getHTMLReport = (recordId: number) => {
    return request.get<string>(
        `/execution-records/${recordId}/html`,
        { responseType: "text" }
    );
};

// 获取Markdown报告
export const getMarkdownReport = (recordId: number) => {
    return request.get<string>(
        `/execution-records/${recordId}/markdown`,
        { responseType: "text" }
    );
};

export const executionRecordService = {
    getExecutionRecords,
    getExecutionRecordDetail,
    deleteExecutionRecord,
    getExecutionStatistics,
    getHTMLReport,
    getMarkdownReport,
};
