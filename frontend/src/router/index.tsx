import { createBrowserRouter, Navigate } from "react-router-dom";
import Error from "./Error";
import AppLayout from "../layout";
import Login from "../pages/Login";
import Dashboard from "../pages/Dashboard";
import TemplatePage from "../pages/Template";
import DocumentPage from "../pages/Document";
import QAPage from "../pages/QA";
import LLMLogPage from "../pages/LLMLog";
import TemplateConfigPage from "../pages/TemplateConfig";

export const router = createBrowserRouter([
    {
        path: "/login",
        element: <Login />,
    },
    {
        path: "/",
        element: <AppLayout />,
        children: [
            { index: true, element: <Navigate to="/dashboard" replace /> },
            { path: '/dashboard', element: <Dashboard /> },
            { path: '/templates', element: <TemplatePage /> },
            { path: '/documents', element: <DocumentPage /> },
            // { path: '/search', element: <SearchPage /> },
            { path: '/qa', element: <QAPage /> },
            { path: '/llm-logs', element: <LLMLogPage /> },
            { path: '/template-configs', element: <TemplateConfigPage /> },
        ],
    },
    { path: '*', element: <Error /> },
]);