import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider, theme as antdTheme } from "antd";
import "./index.css";
import "./App.css";
import App from "./App.tsx";

const themeConfig = {
  algorithm: [antdTheme.defaultAlgorithm],
  token: {
    colorPrimary: '#7551ff',
    colorInfo: '#7551ff',
    colorSuccess: '#05c6b4',
    colorWarning: '#ffb547',
    colorError: '#ff5a7a',
    colorText: '#1b2559',
    colorTextSecondary: '#6b7a99',
    colorBgLayout: '#f6f8ff',
    colorBgContainer: '#ffffff',
    borderRadius: 14,
    fontFamily: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  components: {
    Button: {
      controlHeight: 38,
      controlHeightLG: 44,
      controlOutlineWidth: 0,
      colorLink: '#7551ff',
    },
    Layout: {
      headerHeight: 68,
      headerPadding: '0 20px',
      siderBg: 'rgba(255,255,255,0.82)',
      bodyBg: '#f6f8ff',
    },
    Card: {
      borderRadiusLG: 18,
      boxShadowTertiary: '0 20px 60px rgba(20, 32, 80, 0.08)',
    },
  },
};

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConfigProvider theme={themeConfig}>
      <App />
    </ConfigProvider>
  </StrictMode>
);
